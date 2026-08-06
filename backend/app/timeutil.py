"""Everything is stored as UTC and reasoned about in Asia/Bangkok.

Render and Neon both run in UTC. Bangkok is UTC+7, so anything logged between
midnight and 07:00 local lands on the *previous* UTC day — which is exactly how
a month-filtered dashboard ends up quietly dropping rows. Month and day ranges
are therefore computed as local wall-clock boundaries and converted to UTC
instants, which also keeps the query index-friendly (a plain range scan on
occurred_at, no per-row AT TIME ZONE).
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings

LOCAL_TZ = ZoneInfo(settings.app_timezone)


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def current_month() -> str:
    return now_local().strftime("%Y-%m")


def parse_month(month: str) -> tuple[int, int]:
    try:
        year_s, mon_s = month.split("-")
        year, mon = int(year_s), int(mon_s)
        if not (1 <= mon <= 12) or not (2000 <= year <= 2999):
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"รูปแบบเดือนต้องเป็น YYYY-MM (ได้รับ {month!r})") from exc
    return year, mon


def month_bounds_utc(month: str) -> tuple[datetime, datetime]:
    """[start, end) in UTC covering the given local month."""
    year, mon = parse_month(month)
    start_local = datetime(year, mon, 1, tzinfo=LOCAL_TZ)
    end_local = (
        datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ)
        if mon == 12
        else datetime(year, mon + 1, 1, tzinfo=LOCAL_TZ)
    )
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def day_start_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def day_end_utc(d: date) -> datetime:
    """Exclusive upper bound — the start of the next local day."""
    nxt = d + timedelta(days=1)
    return day_start_utc(nxt)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)
