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
from .model_pool import ESTIMATED_TOKENS_PER_CALL, ModelPool

log = logging.getLogger("bank.tagger")

TAG_TIMEOUT_SECONDS = 8.0
CACHE_MAX = 2048


@dataclass
class TagSuggestion:
    category_name: str | None = None
    keyword: str | None = None
    provider: str = "none"
    error: str | None = None
    # Which pool member answered, and what it cost — the pool needs both to
    # meter correctly, and /health shows the model so a bad answer can be
    # traced to the one that gave it.
    model: str | None = None
    tokens: int = 0
    rate_limited: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.category_name)


class Tagger(Protocol):
    name: str

    async def tag(
        self, description: str, categories: list[str], note: str = ""
    ) -> TagSuggestion: ...


class NullTagger:
    """Default. A keyword miss simply stays a miss and the user picks."""

    name = "none"

    async def tag(
        self, description: str, categories: list[str], note: str = ""
    ) -> TagSuggestion:
        return TagSuggestion(provider=self.name)


PROMPT = """คุณกำลังช่วยจัดหมวดหมู่รายการใช้จ่ายในสมุดบัญชีส่วนตัว

หมวดหมู่ที่มีให้เลือก (ต้องตอบเป็นหนึ่งในนี้เท่านั้น):
{categories}

รายการ: "{description}"{note_line}

ตอบเป็น JSON อย่างเดียว ไม่ต้องมีคำอธิบายหรือ markdown:
{{"category": "<ชื่อหมวดจากรายการข้างบน>", "keyword": "<คำสั้นๆ ที่ใช้จำร้านนี้>"}}

กติกาของ keyword:
- เอาเฉพาะชื่อร้าน/แบรนด์ ตัดคำว่า ค่า ซื้อ จ่าย ร้าน บริษัท จำกัด มหาชน สาขา ออก
- ห้ามเป็นคำกว้างที่ใช้กับร้านไหนก็ได้
- ยาว 3-40 ตัวอักษร ตัวพิมพ์เล็ก
- ถ้าคิดคำที่ใช้ซ้ำได้ไม่ออก ให้ใส่ null
- ถ้าโน้ตบอกชัดกว่าชื่อรายการ (เช่น ชื่อร้านเป็นชื่อบริษัท แต่โน้ตเขียนว่า "ผัดกะเพรา")
  ให้ยึดโน้ตเป็นหลัก และเอาคำจากโน้ตมาเป็น keyword"""


class GeminiTagger:
    """Google Gemini, via the generateContent REST endpoint.

    Thin on purpose, like the OCR provider: it turns a name into a category
    label, and every decision about whether that label is usable happens in
    the caller. The model is given the ledger's own category names and told to
    answer with one of them; anything else is discarded.

    Verified against the live API. Note that the 31B variant only produces
    usable output when responseSchema is set — with only responseMimeType, or
    with neither, it answers in prose.
    """

    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        # The pool decides which model this call uses; the default is only for
        # direct use from scripts.
        self.model = model or (settings.gemini_model_list or ["gemma-4-26b-a4b-it"])[0]

    @property
    def endpoint(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )

    async def tag(
        self, description: str, categories: list[str], note: str = ""
    ) -> TagSuggestion:
        if not settings.gemini_api_key:
            return TagSuggestion(provider=self.name, model=self.model, error="ยังไม่ได้ใส่ GEMINI_API_KEY")
        if not categories:
            return TagSuggestion(provider=self.name, model=self.model, error="สมุดนี้ยังไม่มีหมวดหมู่")

        # The two fields go in labelled separately rather than glued together.
        # Knowing which string is the payee and which is the person's own note
        # is the whole reason the note helps: it lets the model prefer
        # "ผัดกะเพรา" over the holding company that processed the payment.
        clean_note = (note or "").replace('"', "'").strip()[:200]
        prompt = PROMPT.format(
            categories="\n".join(f"- {c}" for c in categories),
            description=description.replace('"', "'")[:200],
            note_line=f'\nโน้ตที่ผู้ใช้เขียน: "{clean_note}"' if clean_note else "",
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
                hint = f" (ไม่พบโมเดล {self.model!r} — แก้ GEMINI_MODELS ใน .env)"
            elif resp.status_code == 429:
                hint = " (ชน rate limit — พักโมเดลนี้แล้วสลับไปอีกตัว)"
            return TagSuggestion(
                provider=self.name,
                model=self.model,
                error=f"{self.model} ตอบ {resp.status_code}{hint}",
                rate_limited=resp.status_code == 429,
            )

        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            return TagSuggestion(provider=self.name, model=self.model,
                                 error="รูปแบบคำตอบไม่ตรงที่คาด")

        data = _extract_json(text)
        if data is None:
            return TagSuggestion(provider=self.name, model=self.model,
                                 error=f"{self.model} ไม่ได้ตอบเป็น JSON")

        name = data.get("category")
        # Only a category this ledger actually has. A model inventing
        # "ค่าเดินทาง" when the book says "เดินทาง" must not create one.
        if not isinstance(name, str) or name.strip() not in categories:
            return TagSuggestion(
                provider=self.name,
                model=self.model,
                error=f"{self.model} ตอบหมวดที่ไม่มีในสมุดนี้: {name!r}",
            )

        keyword = data.get("keyword")
        usage = resp.json().get("usageMetadata") or {}
        return TagSuggestion(
            category_name=name.strip(),
            keyword=keyword.strip() if isinstance(keyword, str) else None,
            provider=self.name,
            model=self.model,
            # Real usage, not the estimate the pool reserved up front.
            tokens=int(usage.get("totalTokenCount") or 0),
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


def make_tagger(model: str | None = None) -> Tagger:
    """The single seam through which a tagger is constructed.

    Production and the tests both go through here — the tests replace this
    function to count calls, which only works while nothing else instantiates
    a provider directly.
    """
    cls = _TAGGERS.get(settings.tagger_provider.lower(), NullTagger)
    return cls(model) if cls is GeminiTagger else cls()


def tagger_enabled() -> bool:
    return settings.tagger_provider.lower() not in ("", "none")


# Two Gemma variants, each with its own 30 requests and 16,000 tokens a minute
# on the same key. See app/model_pool.py for why they are metered separately
# and why a model that runs out sleeps rather than collecting 429s.
pool = ModelPool(
    settings.gemini_model_list,
    requests_per_minute=settings.tagger_requests_per_minute,
    tokens_per_minute=settings.tagger_tokens_per_minute,
    cooldown_seconds=settings.tagger_cooldown_seconds,
)


class _Budget:
    """The whole-day stop.

    Per-minute pacing belongs to the pool, which meters each model separately
    against its own allowance — duplicating it here would just mean two
    limiters disagreeing about the same calls. What is left is a single daily
    ceiling, well under the 14,400 the account permits, so a loop that gets
    away from us cannot spend the allowance overnight.

    In-process, like the auth rate limiter: counters reset on deploy and are
    not shared across instances. Render free runs one instance, so it holds.
    """

    def __init__(self) -> None:
        self._day: deque[float] = deque()
        self._lock = threading.Lock()

    def take(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._day and self._day[0] < now - 86_400:
                self._day.popleft()
            if len(self._day) >= settings.tagger_max_per_day:
                return False
            self._day.append(now)
            return True

    def snapshot(self) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            day = sum(1 for t in self._day if t >= now - 86_400)
        return {"used_today": day, "limit_per_day": settings.tagger_max_per_day}

    def clear(self) -> None:
        with self._lock:
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
    pool.clear()


async def suggest_tag(
    description: str, categories: list[str], wait: bool = False, note: str = ""
) -> TagSuggestion:
    """Run the configured tagger. Always returns; never raises.

    `wait` is the difference between a person and a queue. A person is
    standing in front of the form, so if both models are cooling the answer is
    "no suggestion" and they pick from the dropdown — same as today with the
    tagger off. The background draft worker sets wait=True instead, because
    nobody is watching it and a ninety-second pause costs nothing.
    """
    if not tagger_enabled():
        return TagSuggestion(provider="none")

    # The note is part of the question, so it is part of the cache key:
    # the same shop with a different note may deserve a different answer.
    key = _cache_key(f"{description} \u241f {note}", categories)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    if not budget.take():
        log.info("tagger daily budget exhausted; skipping %r", description[:40])
        return TagSuggestion(provider="gemini")

    model = pool.acquire(ESTIMATED_TOKENS_PER_CALL)
    if model is None:
        if not wait:
            # Not an error: indistinguishable to the caller from the model
            # having nothing to say.
            return TagSuggestion(provider="gemini")
        delay = pool.wait_seconds()
        log.info("all models cooling; waiting %.0fs", delay)
        await asyncio.sleep(min(delay + 0.5, settings.tagger_cooldown_seconds + 5))
        model = pool.acquire(ESTIMATED_TOKENS_PER_CALL)
        if model is None:
            return TagSuggestion(provider="gemini")

    tagger = make_tagger(model)
    try:
        result = await asyncio.wait_for(
            tagger.tag(description, categories, note), timeout=TAG_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        result = TagSuggestion(provider="gemini", model=model, error="เดาหมวดหมู่นานเกินไป")
    except Exception as exc:  # noqa: BLE001
        log.warning("tagger failed", exc_info=True)
        result = TagSuggestion(
            provider="gemini", model=model, error=f"เดาหมวดหมู่ไม่สำเร็จ ({type(exc).__name__})"
        )

    if result.tokens:
        pool.record(model, result.tokens)
    if result.rate_limited:
        # The provider refused despite our own accounting saying there was
        # room, so trust theirs and stand this model down.
        pool.trip(model)

    # Transport failures are not cached — the next attempt may well succeed,
    # and caching a timeout would make one bad minute permanent.
    if result.ok or result.error is None:
        with _cache_lock:
            _cache[key] = result
            _cache.move_to_end(key)
            while len(_cache) > CACHE_MAX:
                _cache.popitem(last=False)

    return result
