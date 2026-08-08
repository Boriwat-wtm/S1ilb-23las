"""Tests for the Thai slip text parser.

The HTTP call to Google Vision cannot be exercised without a key and a stack
of real slips. The parsing can, and it is where the bugs live — so the
provider is deliberately thin and everything interesting is tested here
against text shaped like what the major Thai banks actually print.

Run: python -m tests.test_slip_parser     (from backend/)
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never reach a live provider from a test: Settings reads backend/.env,
# so a real key sitting there would otherwise be spent by a test run.
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("GOOGLE_VISION_API_KEY", "")
os.environ.setdefault("TAGGER_PROVIDER", "none")
os.environ.setdefault("GEMINI_API_KEY", "")

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

print("\n== one parser, seven banks ==")
# The claim this section defends: no per-bank schema. Banks differ in
# *vocabulary*, not in where things sit, so a label-anchored parser covers
# them all and a new bank is a word added to a list, not a template.
BANKS = {
    "K PLUS": ("โอนเงินสำเร็จ\n08 ส.ค. 68 14:23\nไปยัง บริษัท ซีพี ออลล์\n"
               "จำนวนเงิน 45.00 บาท", "45.00", "บริษัท ซีพี ออลล์"),
    "SCB EASY": ("รายการสำเร็จ\n8 สิงหาคม 2568 09:05\nไปยัง ฝน สายบัว\n"
                 "จำนวน 1,250.75 บาท", "1250.75", "ฝน สายบัว"),
    "BBL": ("08/08/2568 20:15\nถึง ร้านกาแฟดอยช้าง\nยอดเงิน 89.50 THB",
            "89.50", "ร้านกาแฟดอยช้าง"),
    "KTB": ("โอนเงินสำเร็จ\n08 ส.ค. 2568 11:30\nผู้รับเงิน สมชาย ใจดี\n"
            "จำนวนเงิน 320.00 บาท", "320.00", "สมชาย ใจดี"),
    "TTB": ("8 ส.ค. 68 16:45\nบัญชีปลายทาง นางสาว ฝน ส\nจำนวนเงิน 1,000.00 บาท",
            "1000.00", "นางสาว ฝน ส"),
    "GSB": ("สลิปโอนเงิน\n08-08-2568 08:12\nไปที่ การไฟฟ้านครหลวง\n฿2,340.00",
            "2340.00", "การไฟฟ้านครหลวง"),
    "English UI": ("Transfer Successful\n2025-08-08 19:04\nTo: Grab Thailand\n"
                   "Total 189.00 THB", "189.00", "Grab Thailand"),
}
for bank, (text, want_amount, want_payee) in BANKS.items():
    r = parse_slip_text(text)
    check(f"{bank}: amount", r["amount"] == Decimal(want_amount), r["amount"])
    check(f"{bank}: date", r["occurred_at"] is not None, r["occurred_at"])
    check(f"{bank}: payee", r["description"] == want_payee, repr(r["description"]))

print("\n== payee labels that used to be wrong ==")
# "ผู้รับ" tried before "ผู้รับเงิน" left "เงิน" glued to the name.
check("ผู้รับเงิน does not leak เงิน into the name",
      parse_payee("ผู้รับเงิน สมชาย ใจดี") == "สมชาย ใจดี",
      parse_payee("ผู้รับเงิน สมชาย ใจดี"))
check("ผู้รับโอน likewise",
      parse_payee("ผู้รับโอน ร้านข้าวมันไก่") == "ร้านข้าวมันไก่",
      parse_payee("ผู้รับโอน ร้านข้าวมันไก่"))
check("บัญชีปลายทาง is recognised",
      parse_payee("บัญชีปลายทาง นางสาว ฝน ส") == "นางสาว ฝน ส",
      parse_payee("บัญชีปลายทาง นางสาว ฝน ส"))
# An unanchored bare "to" matched inside these and returned the line's tail.
check("'Total' is not a payee line", parse_payee("Total 189.00 THB") is None,
      parse_payee("Total 189.00 THB"))
check("'Autopay' is not a payee line", parse_payee("Autopay 500.00") is None,
      parse_payee("Autopay 500.00"))
check("but a real English To: line still works",
      parse_payee("To: Grab Thailand") == "Grab Thailand")

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
