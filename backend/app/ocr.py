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
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from .config import settings

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
    """Placeholder for Google Cloud Vision `DOCUMENT_TEXT_DETECTION`.

    Sketch for when this gets built:
      1. POST the JPEG (base64) to
         https://vision.googleapis.com/v1/images:annotate?key=<API_KEY>
      2. Take `responses[0].fullTextAnnotation.text` as `raw_text`.
      3. Regex the amount (largest THB-looking number, usually the biggest
         glyphs on the slip) and the Thai/So-lar date, and set
         source="ocr" with confidence based on how many fields parsed.
      4. Anything unparsed stays None — the form asks the user.

    Free tier is 1,000 units/month, comfortably above a two-person household,
    but it does require a GCP project with billing enabled.
    """

    name = "google"

    async def extract(self, image_bytes: bytes) -> SlipExtraction:
        return SlipExtraction(
            provider=self.name,
            source="manual",
            confidence="low",
            error="ยังไม่ได้ต่อ Google Vision — กรอกเองไปก่อน",
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
