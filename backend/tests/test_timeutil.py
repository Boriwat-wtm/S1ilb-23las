"""Timezone maths, tested directly.

This is the part of the app most likely to be quietly wrong in production —
Render and Neon run in UTC, the household lives in UTC+7 — and it is also the
part the SQLite smoke harness *cannot* check, because SQLite drops the offset
and stores local wall-clock text. So it gets verified here, against pure
functions, where the assertions actually mean something.

Run: python -m tests.test_timeutil     (from backend/)
"""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Never reach a live provider from a test: Settings reads backend/.env,
# so a real key sitting there would otherwise be spent by a test run.
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("GOOGLE_VISION_API_KEY", "")
os.environ.setdefault("TAGGER_PROVIDER", "none")
os.environ.setdefault("GEMINI_API_KEY", "")

from app.timeutil import (  # noqa: E402
    LOCAL_TZ,
    day_end_utc,
    day_start_utc,
    month_bounds_utc,
    parse_month,
    to_local,
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


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


print("== parse_month ==")
check("valid", parse_month("2026-08") == (2026, 8))
for bad in ("2026-13", "2026", "aug", "", "2026-00", None):
    try:
        parse_month(bad)  # type: ignore[arg-type]
        check(f"rejects {bad!r}", False, "no error raised")
    except ValueError:
        check(f"rejects {bad!r}", True)

print("\n== month_bounds_utc ==")
start, end = month_bounds_utc("2026-08")
# 1 Aug 00:00 +07:00 is 31 Jul 17:00 UTC
check("august starts 31 Jul 17:00Z", start == utc(2026, 7, 31, 17), start)
check("august ends 31 Aug 17:00Z", end == utc(2026, 8, 31, 17), end)

start, end = month_bounds_utc("2026-12")
check("december rolls the year", end == utc(2026, 12, 31, 17), end)

start, end = month_bounds_utc("2024-02")
check("leap february is 29 days", (end - start).days == 29, (end - start))

print("\n== day bounds ==")
d = date(2026, 8, 6)
check("day starts 5 Aug 17:00Z", day_start_utc(d) == utc(2026, 8, 5, 17), day_start_utc(d))
check("day ends 6 Aug 17:00Z", day_end_utc(d) == utc(2026, 8, 6, 17), day_end_utc(d))
check("day window is exactly 24h", day_end_utc(d) - day_start_utc(d) == (utc(2026, 8, 6, 17) - utc(2026, 8, 5, 17)))

print("\n== the bug this all exists to prevent ==")
# An expense entered at 20:00 on 6 Aug Bangkok time is 13:00Z the same day.
evening = datetime(2026, 8, 6, 20, 0, tzinfo=LOCAL_TZ)
check("20:00 local -> 13:00Z", evening.astimezone(timezone.utc) == utc(2026, 8, 6, 13))
check("evening tx falls inside its own local day",
      day_start_utc(d) <= evening.astimezone(timezone.utc) < day_end_utc(d))

# And one at 01:00 on 6 Aug local is 18:00Z on 5 Aug — the classic off-by-a-day.
after_midnight = datetime(2026, 8, 6, 1, 0, tzinfo=LOCAL_TZ)
check("01:00 local is previous UTC day",
      after_midnight.astimezone(timezone.utc) == utc(2026, 8, 5, 18))
check("after-midnight tx still counts as 6 Aug",
      day_start_utc(d) <= after_midnight.astimezone(timezone.utc) < day_end_utc(d))
check("...and is not counted on 5 Aug",
      not (day_start_utc(date(2026, 8, 5))
           <= after_midnight.astimezone(timezone.utc)
           < day_end_utc(date(2026, 8, 5))))

# Month edges: 1 Aug 06:00 local is 31 Jul 23:00Z — must count as August.
first_morning = datetime(2026, 8, 1, 6, 0, tzinfo=LOCAL_TZ)
aug_start, aug_end = month_bounds_utc("2026-08")
jul_start, jul_end = month_bounds_utc("2026-07")
inst = first_morning.astimezone(timezone.utc)
check("1 Aug 06:00 local counts as August", aug_start <= inst < aug_end, inst)
check("...and not as July", not (jul_start <= inst < jul_end))
check("month windows are contiguous, no gap or overlap", jul_end == aug_start)

print("\n== to_local ==")
check("naive is read as UTC then converted",
      to_local(datetime(2026, 8, 6, 13, 0)).hour == 20)
check("aware is converted", to_local(utc(2026, 8, 6, 13)).hour == 20)
check("to_local keeps the instant",
      to_local(utc(2026, 8, 6, 13)).astimezone(timezone.utc) == utc(2026, 8, 6, 13))

print(f"\n{'=' * 46}\n  {passed} passed, {failed} failed\n{'=' * 46}")
sys.exit(1 if failed else 0)
