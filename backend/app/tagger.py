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
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import settings

log = logging.getLogger("bank.tagger")

TAG_TIMEOUT_SECONDS = 8.0


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
            },
        }

        async with httpx.AsyncClient(timeout=TAG_TIMEOUT_SECONDS - 1) as client:
            resp = await client.post(
                self.endpoint,
                params={"key": settings.gemini_api_key},
                json=payload,
            )

        if resp.status_code != 200:
            # 404 here almost always means the model id is wrong or retired,
            # which is worth saying out loud rather than reporting as a
            # generic failure — it is fixed by editing GEMINI_MODEL.
            hint = (
                f" (ไม่พบโมเดล {self.model!r} — แก้ GEMINI_MODEL ใน .env)"
                if resp.status_code == 404
                else ""
            )
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


async def suggest_tag(description: str, categories: list[str]) -> TagSuggestion:
    """Run the configured tagger. Always returns; never raises.

    A category guess is a convenience. If the model is down, slow, or
    nonsensical, the user picks from a dropdown exactly as they do today —
    nothing about saving an entry depends on this working.
    """
    tagger = get_tagger()
    try:
        return await asyncio.wait_for(
            tagger.tag(description, categories), timeout=TAG_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return TagSuggestion(provider=tagger.name, error="เดาหมวดหมู่นานเกินไป")
    except Exception as exc:  # noqa: BLE001
        log.warning("tagger failed", exc_info=True)
        return TagSuggestion(provider=tagger.name, error=f"เดาหมวดหมู่ไม่สำเร็จ ({type(exc).__name__})")
