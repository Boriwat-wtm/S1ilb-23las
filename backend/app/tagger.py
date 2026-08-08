"""Guessing a category for a description the keyword table does not know.

The keyword table answers instantly, for free, and gives the same answer every
time. On a set of realistic Thai merchant names it covers about a third of
them cold — the rest are names nobody thought to seed. This is the fallback
for that third-to-two-thirds, and it is deliberately shaped as a *cache miss
handler*, not as a step in the request:

    keyword hit   -> done, no network, no cost
    keyword miss  -> ask the model once, use the answer, and write the
                     keyword it suggests back into the table
    next time     -> keyword hit

So the cost decays. A household shops at the same forty places; after a couple
of months almost every description resolves locally and the model is asked
only about somewhere genuinely new.

Two things this must not do, both encoded below:

  * It must never touch an amount. A wrong category is visible in a summary
    and takes one tap to fix; a hallucinated digit in a figure is invisible
    and permanent. Amounts come from OCR text via a deterministic parser that
    returns null when it cannot read them.

  * It must never write a keyword unchecked. Everything it returns goes
    through app/keywords.sanitise_keyword first, because one generic word in
    that table silently misfiles every future entry.
"""

import asyncio
import json
import logging
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import settings

log = logging.getLogger("bank.tagger")

TAG_TIMEOUT_SECONDS = 8.0
CACHE_MAX = 2048


@dataclass
class TagSuggestion:
    category_name: str | None = None
    keyword: str | None = None
    provider: str = "none"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.category_name)


class Tagger(Protocol):
    name: str

    async def tag(self, description: str, categories: list[str]) -> TagSuggestion: ...


class NullTagger:
    """Default. A keyword miss simply stays a miss and the user picks."""

    name = "none"

    async def tag(self, description: str, categories: list[str]) -> TagSuggestion:
        return TagSuggestion(provider=self.name)


PROMPT = """คุณกำลังช่วยจัดหมวดหมู่รายการใช้จ่ายในสมุดบัญชีส่วนตัว

หมวดหมู่ที่มีให้เลือก (ต้องตอบเป็นหนึ่งในนี้เท่านั้น):
{categories}

รายการ: "{description}"

ตอบเป็น JSON อย่างเดียว ไม่ต้องมีคำอธิบายหรือ markdown:
{{"category": "<ชื่อหมวดจากรายการข้างบน>", "keyword": "<คำสั้นๆ ที่ใช้จำร้านนี้>"}}

กติกาของ keyword:
- เอาเฉพาะชื่อร้าน/แบรนด์ ตัดคำว่า ค่า ซื้อ จ่าย ร้าน บริษัท จำกัด มหาชน สาขา ออก
- ห้ามเป็นคำกว้างที่ใช้กับร้านไหนก็ได้
- ยาว 3-40 ตัวอักษร ตัวพิมพ์เล็ก
- ถ้าคิดคำที่ใช้ซ้ำได้ไม่ออก ให้ใส่ null"""


class GeminiTagger:
    """Google Gemini, via the generateContent REST endpoint.

    Thin on purpose, like the OCR provider: it turns a name into a category
    label, and every decision about whether that label is usable happens in
    the caller. The model is given the ledger's own category names and told to
    answer with one of them; anything else is discarded.

    NOT YET EXERCISED AGAINST THE LIVE API — there is no key here to test
    with. The request shape follows the documented generateContent contract
    and the response is parsed defensively, but it needs one real call before
    anyone relies on it.
    """

    name = "gemini"

    @property
    def model(self) -> str:
        return settings.gemini_model

    @property
    def endpoint(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )

    async def tag(self, description: str, categories: list[str]) -> TagSuggestion:
        if not settings.gemini_api_key:
            return TagSuggestion(provider=self.name, error="ยังไม่ได้ใส่ GEMINI_API_KEY")
        if not categories:
            return TagSuggestion(provider=self.name, error="สมุดนี้ยังไม่มีหมวดหมู่")

        prompt = PROMPT.format(
            categories="\n".join(f"- {c}" for c in categories),
            description=description.replace('"', "'")[:200],
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                # Deterministic: the same shop should not land in a different
                # category depending on the day.
                "temperature": 0,
                "maxOutputTokens": 120,
                "responseMimeType": "application/json",
                # The enum is what actually stops a wrong tag, far more than
                # picking a bigger model would. Constrained decoding means the
                # category cannot come back as something this ledger does not
                # have — no invented "ค่าเดินทาง" next to an existing "เดินทาง",
                # no English translation of a Thai category, no prose. The
                # check against `categories` below stays as a belt-and-braces
                # guard for the case where a model ignores the schema.
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "category": {"type": "STRING", "enum": categories},
                        "keyword": {"type": "STRING", "nullable": True},
                    },
                    "required": ["category"],
                },
            },
        }

        async with httpx.AsyncClient(timeout=TAG_TIMEOUT_SECONDS - 1) as client:
            resp = await client.post(
                self.endpoint,
                params={"key": settings.gemini_api_key},
                json=payload,
            )

        if resp.status_code != 200:
            # Two failures are common enough to name, because both are fixed
            # by a config change rather than by debugging: a retired model id,
            # and the free tier's per-minute cap during a burst of uploads.
            hint = ""
            if resp.status_code == 404:
                hint = f" (ไม่พบโมเดล {self.model!r} — แก้ GEMINI_MODEL ใน .env)"
            elif resp.status_code == 429:
                hint = " (ชน rate limit ของ free tier — เดี๋ยวค่อยลองใหม่ ระหว่างนี้เลือกหมวดเอง)"
            return TagSuggestion(
                provider=self.name, error=f"Gemini ตอบ {resp.status_code}{hint}"
            )

        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            return TagSuggestion(provider=self.name, error="รูปแบบคำตอบจาก Gemini ไม่ตรงที่คาด")

        data = _extract_json(text)
        if data is None:
            return TagSuggestion(provider=self.name, error="Gemini ไม่ได้ตอบเป็น JSON")

        name = data.get("category")
        # Only a category this ledger actually has. A model inventing
        # "ค่าเดินทาง" when the book says "เดินทาง" must not create one.
        if not isinstance(name, str) or name.strip() not in categories:
            return TagSuggestion(
                provider=self.name, error=f"Gemini ตอบหมวดที่ไม่มีในสมุดนี้: {name!r}"
            )

        keyword = data.get("keyword")
        return TagSuggestion(
            category_name=name.strip(),
            keyword=keyword.strip() if isinstance(keyword, str) else None,
            provider=self.name,
        )


def _extract_json(text: str) -> dict | None:
    """Parse the model's answer, tolerating a fenced code block around it."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


_TAGGERS: dict[str, type] = {"none": NullTagger, "gemini": GeminiTagger}


def get_tagger() -> Tagger:
    return _TAGGERS.get(settings.tagger_provider.lower(), NullTagger)()


class _Budget:
    """Self-imposed call ceiling, per minute and per day.

    Not a copy of the provider's limit — a lower one. Collecting a 429 means
    the request already went out and was refused; refusing it here means the
    user sees a category they have to pick themselves, which is the same
    outcome they get today with the tagger switched off. One is a failure, the
    other is just the feature not firing.

    In-process, like the auth rate limiter: counters reset on deploy and are
    not shared across instances. Render free runs one instance, so it holds.
    """

    def __init__(self) -> None:
        self._minute: deque[float] = deque()
        self._day: deque[float] = deque()
        self._lock = threading.Lock()

    def take(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._minute and self._minute[0] < now - 60:
                self._minute.popleft()
            while self._day and self._day[0] < now - 86_400:
                self._day.popleft()
            if len(self._minute) >= settings.tagger_max_per_minute:
                return False
            if len(self._day) >= settings.tagger_max_per_day:
                return False
            self._minute.append(now)
            self._day.append(now)
            return True

    def snapshot(self) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            minute = sum(1 for t in self._minute if t >= now - 60)
            day = sum(1 for t in self._day if t >= now - 86_400)
        return {
            "used_this_minute": minute,
            "used_today": day,
            "limit_per_minute": settings.tagger_max_per_minute,
            "limit_per_day": settings.tagger_max_per_day,
        }

    def clear(self) -> None:
        with self._lock:
            self._minute.clear()
            self._day.clear()


budget = _Budget()

# Same shop, same answer — asking twice is pure waste. Negative results are
# cached too: a description the model could not place will not become
# placeable by asking again, and re-asking is exactly what a user retyping the
# same thing would trigger.
_cache: OrderedDict[tuple, TagSuggestion] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(description: str, categories: list[str]) -> tuple:
    return (" ".join(description.lower().split()), tuple(categories))


def cache_stats() -> dict[str, int]:
    with _cache_lock:
        return {"cached": len(_cache)}


def reset_state() -> None:
    """Test hook — clears the cache and the budget.

    Clears the budget in place rather than replacing it. main.py binds this
    object at import time for /health, so rebinding the name here would leave
    the health endpoint reporting a detached counter that never moves again —
    which is exactly what it did before this was fixed.
    """
    with _cache_lock:
        _cache.clear()
    budget.clear()


async def suggest_tag(description: str, categories: list[str]) -> TagSuggestion:
    """Run the configured tagger. Always returns; never raises.

    A category guess is a convenience. If the model is down, slow, throttled
    or nonsensical, the user picks from a dropdown exactly as they do today —
    nothing about saving an entry depends on this working.
    """
    tagger = get_tagger()
    if isinstance(tagger, NullTagger):
        return TagSuggestion(provider=tagger.name)

    key = _cache_key(description, categories)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    if not budget.take():
        # Deliberately not an error: the caller shows no suggestion, which is
        # indistinguishable from the model having nothing to say.
        log.info("tagger budget exhausted; skipping %r", description[:40])
        return TagSuggestion(provider=tagger.name)

    try:
        result = await asyncio.wait_for(
            tagger.tag(description, categories), timeout=TAG_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        result = TagSuggestion(provider=tagger.name, error="เดาหมวดหมู่นานเกินไป")
    except Exception as exc:  # noqa: BLE001
        log.warning("tagger failed", exc_info=True)
        result = TagSuggestion(
            provider=tagger.name, error=f"เดาหมวดหมู่ไม่สำเร็จ ({type(exc).__name__})"
        )

    # Transport failures are not cached — the next attempt may well succeed,
    # and caching a timeout would make one bad minute permanent.
    if result.ok or result.error is None:
        with _cache_lock:
            _cache[key] = result
            _cache.move_to_end(key)
            while len(_cache) > CACHE_MAX:
                _cache.popitem(last=False)

    return result
