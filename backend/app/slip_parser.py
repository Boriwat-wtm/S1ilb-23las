"""Pull an amount, a date and a payee out of the raw text of a Thai bank slip.

This is a pure function on purpose. It is the part of OCR most likely to be
wrong, and the only part that can be tested without an API key and a stack of
real slips — so it lives away from the HTTP call and has its own test file.

What Thai slips actually look like, and why each rule below exists:

  * Amounts are labelled "จำนวนเงิน" or "จำนวน" and followed by "บาท" or "THB".
    An unanchored "largest number on the page" rule picks up account numbers
    and reference codes, so the label is tried first and the loose rule is
    only a fallback — and even then it demands two decimal places.

  * Years are Buddhist. 2568 is 2025. Some banks print two digits ("68"),
    which is 2568, not 1968 and not 2068.

  * Months are Thai abbreviations with full stops: ม.ค. ก.พ. มี.ค. …
    OCR frequently drops those stops, so both forms are matched.

  * Everything is Bangkok wall-clock time; the caller gets a tz-aware value so
    nothing downstream has to guess.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

BKK = ZoneInfo("Asia/Bangkok")

THAI_MONTHS = {
    "ม.ค.": 1, "มค": 1, "มกราคม": 1,
    "ก.พ.": 2, "กพ": 2, "กุมภาพันธ์": 2,
    "มี.ค.": 3, "มีค": 3, "มีนาคม": 3,
    "เม.ย.": 4, "เมย": 4, "เมษายน": 4,
    "พ.ค.": 5, "พค": 5, "พฤษภาคม": 5,
    "มิ.ย.": 6, "มิย": 6, "มิถุนายน": 6,
    "ก.ค.": 7, "กค": 7, "กรกฎาคม": 7,
    "ส.ค.": 8, "สค": 8, "สิงหาคม": 8,
    "ก.ย.": 9, "กย": 9, "กันยายน": 9,
    "ต.ค.": 10, "ตค": 10, "ตุลาคม": 10,
    "พ.ย.": 11, "พย": 11, "พฤศจิกายน": 11,
    "ธ.ค.": 12, "ธค": 12, "ธันวาคม": 12,
}

_MONTH_ALT = "|".join(sorted((re.escape(m) for m in THAI_MONTHS), key=len, reverse=True))

# "จำนวนเงิน 1,234.56 บาท" — the label may sit on the line above the figure,
# so a little whitespace (including newlines) is allowed between them.
_AMOUNT_LABELLED = re.compile(
    r"(?:จำนวนเงิน|จํานวนเงิน|จำนวน|จํานวน|ยอดเงิน|amount)\s*[:：]?\s*"
    r"([0-9][0-9,\s]*\.?\d{0,2})",
    re.IGNORECASE,
)
# Any figure immediately followed by the currency.
_AMOUNT_CURRENCY = re.compile(r"([0-9][0-9,]*\.\d{2})\s*(?:บาท|THB|฿)", re.IGNORECASE)
# Last resort: anything money-shaped. Two decimals required, which is what
# keeps account and reference numbers out.
_AMOUNT_LOOSE = re.compile(r"\b(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})\b")

_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?:[:.]([0-5]\d))?\b")

# 08 ส.ค. 68 / 8 สิงหาคม 2568
_DATE_THAI = re.compile(rf"\b(\d{{1,2}})\s*({_MONTH_ALT})\s*(\d{{2}}|\d{{4}})\b")
# 08/08/2568 or 08-08-2568 or 2568-08-08
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_PAYEE = re.compile(
    r"(?:ไปยัง|ไปที่|ถึง|ผู้รับ|to)\s*[:：]?\s*(.+)", re.IGNORECASE
)
_REF = re.compile(
    r"(?:รหัสอ้างอิง|เลขที่รายการ|หมายเลขอ้างอิง|reference|ref\.?\s*no\.?|ref)\s*[:：]?\s*"
    r"([A-Za-z0-9]{6,40})",
    re.IGNORECASE,
)

# Lines that are the bank's own furniture, never a payee name.
_NOISE = re.compile(
    r"(โอนเงิน|สำเร็จ|สําเร็จ|สแกน|ตรวจสอบ|slip|verified|จำนวนเงิน|จํานวนเงิน|ค่าธรรมเนียม|บาท)",
    re.IGNORECASE,
)


def _to_decimal(raw: str) -> Decimal | None:
    cleaned = raw.replace(",", "").replace(" ", "").rstrip(".")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    # A slip for zero baht is not a slip, and eight figures is an account
    # number that slipped through.
    if value <= 0 or value >= Decimal("100000000"):
        return None
    return value.quantize(Decimal("0.01"))


def _normalise_year(year: int) -> int:
    """Buddhist Era to Gregorian, tolerating the two-digit form banks print."""
    if year < 100:
        year += 2500
    if year > 2400:
        year -= 543
    return year


def parse_amount(text: str) -> Decimal | None:
    for pattern in (_AMOUNT_LABELLED, _AMOUNT_CURRENCY):
        for match in pattern.finditer(text):
            value = _to_decimal(match.group(1))
            if value is not None:
                return value

    # Nothing labelled: take the largest money-shaped figure. On a transfer
    # slip the fee, if printed, is smaller than the transfer.
    candidates = [
        v for v in (_to_decimal(m.group(1)) for m in _AMOUNT_LOOSE.finditer(text))
        if v is not None
    ]
    return max(candidates) if candidates else None


def parse_datetime(text: str) -> datetime | None:
    day = month = year = None

    match = _DATE_THAI.search(text)
    if match:
        day = int(match.group(1))
        month = THAI_MONTHS[match.group(2)]
        year = _normalise_year(int(match.group(3)))
    else:
        match = _DATE_ISO.search(text)
        if match:
            year, month, day = (int(g) for g in match.groups())
        else:
            match = _DATE_NUMERIC.search(text)
            if match:
                day, month = int(match.group(1)), int(match.group(2))
                year = _normalise_year(int(match.group(3)))

    if not (day and month and year) or not (1 <= month <= 12) or not (1 <= day <= 31):
        return None

    hour = minute = 0
    time_match = _TIME.search(text)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))

    try:
        return datetime(year, month, day, hour, minute, tzinfo=BKK)
    except ValueError:
        return None


def parse_payee(text: str) -> str | None:
    for line in text.splitlines():
        match = _PAYEE.search(line.strip())
        if not match:
            continue
        name = match.group(1).strip(" -:•\t")
        # Strip a masked account number trailing the name.
        name = re.sub(r"\s*[xX*]{2,}[-\dxX*]*\s*$", "", name).strip()
        if name and not _NOISE.search(name) and len(name) <= 120:
            return name
    return None


def parse_reference(text: str) -> str | None:
    match = _REF.search(text)
    return match.group(1) if match else None


def parse_slip_text(text: str) -> dict:
    """Best effort. Every field is independently optional — a slip that only
    yields an amount is still worth returning, because it saves the one bit of
    typing that is most error-prone."""
    if not text or not text.strip():
        return {"amount": None, "occurred_at": None, "description": None, "reference": None}

    return {
        "amount": parse_amount(text),
        "occurred_at": parse_datetime(text),
        "description": parse_payee(text),
        "reference": parse_reference(text),
    }


def confidence_for(parsed: dict) -> str:
    """How much of the entry the user still has to type."""
    if parsed.get("amount") and parsed.get("occurred_at"):
        return "high"
    if parsed.get("amount") or parsed.get("occurred_at"):
        return "medium"
    return "low"
