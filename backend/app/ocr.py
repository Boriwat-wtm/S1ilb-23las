"""Slip extraction seam.

OCR is deliberately *not* implemented yet — Google Cloud Vision goes in later.
What matters now is that the boundary exists and the rest of the app is already
written against it, so switching `OCR_PROVIDER` from "none" to "google" is a
config change and not a refactor.

Two invariants every provider must uphold:

  * `extract()` never raises. A slip it cannot read returns an empty
    SlipExtraction with `error` set. OCR is a convenience on top of a form the
    user can always fill in by hand; it is never on the critical path.
  * `extract()` is wrapped in a timeout by the caller. A provider that hangs
    must not hold the request open.

Note on Thai slip QR codes: the mini-QR printed on a completed transfer slip
encodes a *slip verification reference* (sending bank + transaction ref), not
the amount or date. Its real value here is `slip_ref` — a natural unique key
that stops the same slip being logged twice by two people. Amount and date
still have to come from OCR or from a slip-verification API.
"""

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import httpx

from .config import settings
from .slip_parser import confidence_for, parse_slip_text

EXTRACT_TIMEOUT_SECONDS = 15.0


@dataclass
class SlipExtraction:
    amount: Decimal | None = None
    occurred_at: datetime | None = None
    description: str | None = None
    slip_ref: str | None = None
    raw_text: str | None = None
    # "manual" when nothing usable came back, otherwise "qr" or "ocr"
    source: str = "manual"
    confidence: str = "low"
    provider: str = "none"
    error: str | None = None
    fields: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.amount is not None or self.occurred_at is not None


class OcrProvider(Protocol):
    name: str

    async def extract(self, image_bytes: bytes) -> SlipExtraction: ...


class NullProvider:
    """Current default: upload and store the slip, extract nothing.

    The entry form opens blank and the user types the two fields in. This is
    the same code path every other provider falls back to on failure, so it
    gets exercised constantly rather than rotting until the day it is needed.
    """

    name = "none"

    async def extract(self, image_bytes: bytes) -> SlipExtraction:
        return SlipExtraction(
            provider=self.name,
            source="manual",
            confidence="low",
            error=None,
        )


class GoogleVisionProvider:
    """Google Cloud Vision, DOCUMENT_TEXT_DETECTION.

    Deliberately thin. All it does is turn an image into text; every judgement
    about what that text means lives in app/slip_parser.py, which is a pure
    function with its own tests. That split is the point — the HTTP call
    cannot be tested without a key and a pile of real slips, so as little
    logic as possible sits on this side of the line.

    Free tier is 1,000 units/month, comfortably above a two-person household,
    but it needs a GCP project with billing enabled.

    NOT YET EXERCISED AGAINST A REAL SLIP. The parser is well covered; this
    request/response shape is written from the API docs and needs one real
    photograph through it before anyone should trust the numbers it fills in.
    """

    name = "google"
    endpoint = "https://vision.googleapis.com/v1/images:annotate"

    async def extract(self, image_bytes: bytes) -> SlipExtraction:
        if not settings.google_vision_api_key:
            return SlipExtraction(
                provider=self.name,
                error="ยังไม่ได้ใส่ GOOGLE_VISION_API_KEY — กรอกเองไปก่อน",
            )

        payload = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    # Thai first, English second: slips mix both, and the hint
                    # order matters for how Vision segments the lines.
                    "imageContext": {"languageHints": ["th", "en"]},
                }
            ]
        }

        async with httpx.AsyncClient(timeout=EXTRACT_TIMEOUT_SECONDS - 2) as client:
            resp = await client.post(
                self.endpoint,
                params={"key": settings.google_vision_api_key},
                json=payload,
            )

        if resp.status_code != 200:
            return SlipExtraction(
                provider=self.name,
                error=f"Google Vision ตอบ {resp.status_code} — กรอกเองไปก่อน",
            )

        body = resp.json()
        first = (body.get("responses") or [{}])[0]
        if "error" in first:
            return SlipExtraction(
                provider=self.name,
                error=f"Google Vision: {first['error'].get('message', 'unknown')} — กรอกเองไปก่อน",
            )

        text = (first.get("fullTextAnnotation") or {}).get("text", "")
        if not text.strip():
            return SlipExtraction(
                provider=self.name,
                raw_text=text or None,
                error="อ่านตัวหนังสือจากรูปไม่ได้เลย — กรอกเอง",
            )

        parsed = parse_slip_text(text)
        return SlipExtraction(
            amount=parsed["amount"],
            occurred_at=parsed["occurred_at"],
            description=parsed["description"],
            # The reference goes in as slip_ref, which is what stops the same
            # slip being filed twice in one ledger.
            slip_ref=parsed["reference"],
            raw_text=text,
            provider=self.name,
            source="ocr" if (parsed["amount"] or parsed["occurred_at"]) else "manual",
            confidence=confidence_for(parsed),
        )


_PROVIDERS: dict[str, type] = {
    "none": NullProvider,
    "google": GoogleVisionProvider,
}


def get_provider() -> OcrProvider:
    cls = _PROVIDERS.get(settings.ocr_provider.lower(), NullProvider)
    return cls()


async def extract_slip(image_bytes: bytes) -> SlipExtraction:
    """Run the configured provider. Always returns; never raises."""
    provider = get_provider()
    try:
        return await asyncio.wait_for(
            provider.extract(image_bytes), timeout=EXTRACT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return SlipExtraction(
            provider=provider.name,
            error="อ่านสลิปนานเกินไป — กรอกเองไปก่อน",
        )
    except Exception as exc:  # noqa: BLE001 - a broken provider must not 500
        return SlipExtraction(
            provider=provider.name,
            error=f"อ่านสลิปไม่สำเร็จ ({type(exc).__name__}) — กรอกเองไปก่อน",
        )
