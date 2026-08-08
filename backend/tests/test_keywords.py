"""Tests for keyword hygiene.

This module is the guard between two automatic writers — the correction
learner and the LLM tagger — and a table where one bad row silently misfiles
every future entry. Matching is substring-based, so a keyword like "ร้าน"
swallows the whole ledger, and because longest-match wins the tie it swallows
it *confidently*. These tests are the reason it is safe to let anything write
here without a human in the loop.

Run: python -m tests.test_keywords     (from backend/)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never reach a live provider from a test: Settings reads backend/.env,
# so a real key sitting there would otherwise be spent by a test run.
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("GOOGLE_VISION_API_KEY", "")
os.environ.setdefault("TAGGER_PROVIDER", "none")
os.environ.setdefault("GEMINI_API_KEY", "")

from app.keywords import normalise, sanitise_keyword, stem, would_shadow  # noqa: E402

passed = failed = 0


def check(label: str, cond: bool, extra: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {extra}")


print("\n== normalise ==")
check("lowercases", normalise("After You") == "after you")
check("collapses whitespace", normalise("  MK   Restaurant ") == "mk restaurant")
check("empty stays empty", normalise("") == "")
check("None-ish input does not crash", normalise(None) == "")

print("\n== stem ==")
cases = [
    ("ค่ากาแฟ After You สาขาสยาม", "กาแฟ after you"),
    ("ร้านลุงหนวดข้าวหมูแดง", "ลุงหนวดข้าวหมูแดง"),
    ("บริษัท ซีพี ออลล์ จำกัด (มหาชน)", "ซีพี ออลล์"),
    ("MK Restaurant สาขาเซ็นทรัลลาดพร้าว", "mk restaurant"),
    ("Tops Daily Branch 12", "tops daily"),
    ("ซื้อของ Villa Market", "ของ villa market"),
    ("โอนให้ ฝน สายบัว", "ฝน สายบัว"),
    ("After You", "after you"),
]
for raw, want in cases:
    check(f"{raw!r} -> {want!r}", stem(raw) == want, repr(stem(raw)))

long_name = "ร้านอาหารตามสั่งเจ๊หมวยข้างซอยแยกที่สามเลยปากทางเข้าหมู่บ้านไปอีกนิด"
check("over-long stems are cut, not stored whole", len(stem(long_name)) <= 40, stem(long_name))

print("\n== sanitise: the words that would ruin a ledger ==")
for bad in ("ร้าน", "ค่า", "บริษัท", "จำกัด", "สาขา", "โอน", "เงิน", "total", "payment", "shop"):
    check(f"refuses generic {bad!r}", sanitise_keyword(bad) is None, sanitise_keyword(bad))
check("refuses an all-generic phrase", sanitise_keyword("ค่า ร้าน") is None,
      sanitise_keyword("ค่า ร้าน"))

print("\n== sanitise: shape ==")
check("refuses too short", sanitise_keyword("ก") is None)
check("refuses 2 chars", sanitise_keyword("ab") is None)
check("accepts 3 chars", sanitise_keyword("mkr") == "mkr")
check("refuses digits only", sanitise_keyword("1234567") is None)
check("refuses an amount", sanitise_keyword("1,250.75") is None)
check("refuses a masked account", sanitise_keyword("xxx-x-x1234-x") is not None
      or sanitise_keyword("123-4-56789-0") is None)
check("refuses punctuation only", sanitise_keyword("--- ---") is None)
check("refuses over-long", sanitise_keyword("ก" * 60) is None)
check("normalises what it accepts", sanitise_keyword("  After   You ") == "after you")
check("empty -> None", sanitise_keyword("") is None)

print("\n== sanitise: already spoken for ==")
existing = {"after you": 1, "เซเว่น": 2}
check("refuses a word already mapped", sanitise_keyword("After You", existing) is None)
check("accepts an unused word", sanitise_keyword("tops daily", existing) == "tops daily")

print("\n== would_shadow ==")
# Substring matching plus longest-wins means a longer new word sits on top of
# every shorter word inside it.
existing = {"กาแฟ": 1, "grab": 2}
check("a longer word containing another category's word is refused",
      would_shadow("กาแฟสด", existing, category_id=3) is True)
check("...but not when it points at the same category",
      would_shadow("กาแฟสด", existing, category_id=1) is False)
check("a shorter word inside another category's word is refused too",
      would_shadow("gra", existing, category_id=3) is True)
check("an unrelated word is fine",
      would_shadow("tops daily", existing, category_id=3) is False)
check("no existing keywords, nothing to shadow",
      would_shadow("anything", {}, category_id=1) is False)

print("\n== the case this all exists for ==")
# A tagger returning "ร้าน" for "ร้านลุงหนวด" would, unguarded, make every
# description containing "ร้าน" resolve to whatever category that call
# happened to pick.
check("a tagger returning a generic word is refused outright",
      sanitise_keyword("ร้าน", {"เซเว่น": 1}) is None)
check("the useful part of the same name is accepted",
      sanitise_keyword(stem("ร้านลุงหนวดข้าวหมูแดง")) == "ลุงหนวดข้าวหมูแดง")

print(f"\n{'=' * 52}\n  {passed} passed, {failed} failed\n{'=' * 52}")
sys.exit(1 if failed else 0)
