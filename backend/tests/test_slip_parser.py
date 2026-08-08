"""Tests for the Thai slip text parser.

The HTTP call to Google Vision cannot be exercised without a key and a stack
of real slips. The parsing can, and it is where the bugs live — so the
provider is deliberately thin and everything interesting is tested here
against text shaped like what the major Thai banks actually print.

Run: python -m tests.test_slip_parser     (from backend/)
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.slip_parser import (  # noqa: E402
    BKK,
    confidence_for,
    parse_amount,
    parse_datetime,
    parse_payee,
    parse_reference,
    parse_slip_text,
)

passed = failed = 0


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


# --------------------------------------------------------------------------
# Text shaped like the real thing. Layout varies per bank, which is the whole
# reason the parser matches on labels rather than positions.
# --------------------------------------------------------------------------
KBANK = """K PLUS
โอนเงินสำเร็จ
08 ส.ค. 68 14:23
จาก นาย บอริวัฒน์ ว
ธนาคารกสิกรไทย xxx-x-x1234-x
ไปยัง บริษัท ซีพี ออลล์ จำกัด (มหาชน)
พร้อมเพย์ 010556xxxx
จำนวนเงิน 45.00 บาท
ค่าธรรมเนียม 0.00 บาท
รหัสอ้างอิง 015082568142312345
"""

SCB = """SCB EASY
รายการสำเร็จ
8 สิงหาคม 2568 09:05
ไปยัง ฝน สายบัว
จำนวน 1,250.75 บาท
เลขที่รายการ 20250808SCB0099123
"""

BBL_NUMERIC = """Bualuang
08/08/2568 20:15 น.
ถึง ร้านกาแฟดอยช้าง
ยอดเงิน 89.50 THB
"""

# No label anywhere — the loose rule has to earn its place, and must not pick
# the account number or the reference.
UNLABELLED = """TRANSFER COMPLETED
2025-08-08 07:40
Acc 1234567890
Ref 998877665544
320.00
15.00
"""

OCR_MANGLED = """โอนเงินสําเร็จ
08 สค 68 14:23
จํานวนเงิน 2,480.00 บาท
"""

print("\n== amount ==")
check("labelled จำนวนเงิน", parse_amount(KBANK) == Decimal("45.00"), parse_amount(KBANK))
check("thousands separator", parse_amount(SCB) == Decimal("1250.75"), parse_amount(SCB))
check("THB suffix", parse_amount(BBL_NUMERIC) == Decimal("89.50"), parse_amount(BBL_NUMERIC))
check("picks the transfer, not the fee",
      parse_amount(KBANK) == Decimal("45.00") and "0.00" in KBANK)
check("unlabelled -> largest money-shaped figure",
      parse_amount(UNLABELLED) == Decimal("320.00"), parse_amount(UNLABELLED))
check("ignores the account number", parse_amount(UNLABELLED) != Decimal("1234567890"))
check("ignores the reference number", parse_amount(UNLABELLED) != Decimal("998877665544"))
check("handles OCR dropping the vowel in จํานวน",
      parse_amount(OCR_MANGLED) == Decimal("2480.00"), parse_amount(OCR_MANGLED))
check("no digits -> None", parse_amount("โอนเงินสำเร็จ") is None)
check("empty -> None", parse_amount("") is None)
check("zero is not an amount", parse_amount("จำนวนเงิน 0.00 บาท") is None)
check("integers without decimals are not trusted alone",
      parse_amount("Acc 1234567890\nRef 5566778899") is None,
      parse_amount("Acc 1234567890\nRef 5566778899"))

print("\n== date ==")
d = parse_datetime(KBANK)
check("Thai abbreviated month + 2-digit BE year",
      d == datetime(2025, 8, 8, 14, 23, tzinfo=BKK), d)
d = parse_datetime(SCB)
check("full Thai month + 4-digit BE year",
      d == datetime(2025, 8, 8, 9, 5, tzinfo=BKK), d)
d = parse_datetime(BBL_NUMERIC)
check("numeric d/m/BE", d == datetime(2025, 8, 8, 20, 15, tzinfo=BKK), d)
d = parse_datetime(UNLABELLED)
check("ISO date, already Gregorian",
      d == datetime(2025, 8, 8, 7, 40, tzinfo=BKK), d)
d = parse_datetime(OCR_MANGLED)
check("month abbreviation with the full stops dropped",
      d == datetime(2025, 8, 8, 14, 23, tzinfo=BKK), d)
check("result is Bangkok-aware, never naive",
      parse_datetime(KBANK).tzinfo is not None)
check("2568 -> 2025", parse_datetime("1 ม.ค. 2568").year == 2025)
check("68 -> 2025, not 1968", parse_datetime("1 ม.ค. 68").year == 2025)
check("no date -> None", parse_datetime("จำนวนเงิน 45.00 บาท") is None)
check("impossible day rejected", parse_datetime("32 ม.ค. 2568") is None)
check("impossible month rejected", parse_datetime("08/13/2568") is None)
check("no time -> midnight", parse_datetime("8 สิงหาคม 2568").hour == 0)

print("\n== payee ==")
check("ไปยัง", parse_payee(KBANK) == "บริษัท ซีพี ออลล์ จำกัด (มหาชน)", parse_payee(KBANK))
check("ไปยัง, personal name", parse_payee(SCB) == "ฝน สายบัว", parse_payee(SCB))
check("ถึง", parse_payee(BBL_NUMERIC) == "ร้านกาแฟดอยช้าง", parse_payee(BBL_NUMERIC))
check("strips a trailing masked account",
      parse_payee("ไปยัง สมชาย ใจดี xxx-x-x9999-x") == "สมชาย ใจดี",
      parse_payee("ไปยัง สมชาย ใจดี xxx-x-x9999-x"))
check("does not return the bank's own furniture",
      parse_payee("โอนเงินสำเร็จ\nจำนวนเงิน 45.00 บาท") is None)
check("no payee line -> None", parse_payee(UNLABELLED) is None)

print("\n== reference ==")
check("รหัสอ้างอิง", parse_reference(KBANK) == "015082568142312345", parse_reference(KBANK))
check("เลขที่รายการ", parse_reference(SCB) == "20250808SCB0099123", parse_reference(SCB))
check("no reference -> None", parse_reference(BBL_NUMERIC) is None)

print("\n== whole slip ==")
r = parse_slip_text(KBANK)
check("all four fields off a K PLUS slip",
      r["amount"] == Decimal("45.00")
      and r["occurred_at"] == datetime(2025, 8, 8, 14, 23, tzinfo=BKK)
      and r["description"] == "บริษัท ซีพี ออลล์ จำกัด (มหาชน)"
      and r["reference"] == "015082568142312345",
      r)
check("empty text is a clean miss, not a crash",
      parse_slip_text("") == {"amount": None, "occurred_at": None,
                              "description": None, "reference": None})
check("garbage is a clean miss",
      all(v is None for v in parse_slip_text("▓▒░ ▚▞ ░▒▓").values()),
      parse_slip_text("▓▒░ ▚▞ ░▒▓"))

print("\n== confidence ==")
check("amount + date -> high", confidence_for(parse_slip_text(KBANK)) == "high")
check("amount only -> medium",
      confidence_for({"amount": Decimal("1"), "occurred_at": None}) == "medium")
check("date only -> medium",
      confidence_for({"amount": None, "occurred_at": datetime.now(BKK)}) == "medium")
check("neither -> low", confidence_for({"amount": None, "occurred_at": None}) == "low")

print(f"\n{'=' * 52}\n  {passed} passed, {failed} failed\n{'=' * 52}")
sys.exit(1 if failed else 0)
