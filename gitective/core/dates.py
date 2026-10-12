"""Date helpers: DD/MM/YYYY parsing, local timezone, period shortcuts."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"

Period = tuple[datetime, datetime]


def now_local() -> datetime:
    """Current time, timezone-aware, in the PC's local zone."""
    return datetime.now().astimezone()


def to_local(value: datetime) -> datetime:
    """Convert an aware datetime to the PC's local zone."""
    return value.astimezone()


def parse_date(text: str) -> date:
    """Parse a DD/MM/YYYY date; raise ValueError when malformed."""
    return datetime.strptime(text.strip(), DATE_FORMAT).date()


def format_date(value: date) -> str:
    return value.strftime(DATE_FORMAT)


def format_datetime(value: datetime | None) -> str:
    """Format a datetime in local time, or an empty string."""
    return to_local(value).strftime(DATETIME_FORMAT) if value else ""


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min).astimezone()


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time.max).astimezone()


def business_days(start: datetime, end: datetime) -> float:
    """Elapsed days between two datetimes, local Saturdays and Sundays excluded."""
    cursor, end = to_local(start), to_local(end)
    seconds = 0.0
    while cursor < end:
        segment_end = min(end, start_of_day(cursor.date() + timedelta(days=1)))
        if cursor.weekday() < 5:
            seconds += (segment_end - cursor).total_seconds()
        cursor = segment_end
    return seconds / 86400


def day_range(start: date, end: date) -> Period:
    """Whole days, both included: start 00:00:00 to end 23:59:59."""
    if end < start:
        raise ValueError("End date is before start date")
    return start_of_day(start), end_of_day(end)


def since_yesterday(now: datetime | None = None) -> Period:
    """Yesterday 00:00 to now."""
    current = now or now_local()
    return start_of_day(current.date() - timedelta(days=1)), current


def last_days(days: int, now: datetime | None = None) -> Period:
    """The last N days including today."""
    current = now or now_local()
    return start_of_day(current.date() - timedelta(days=days - 1)), end_of_day(current.date())


def current_month(now: datetime | None = None) -> Period:
    current = now or now_local()
    return start_of_day(current.date().replace(day=1)), end_of_day(current.date())


def current_year(now: datetime | None = None) -> Period:
    current = now or now_local()
    return start_of_day(current.date().replace(month=1, day=1)), end_of_day(current.date())


def in_period(value: datetime | None, period: Period | None) -> bool:
    """True when value lies within period (None period means no limit)."""
    if value is None:
        return False
    if period is None:
        return True
    return period[0] <= value <= period[1]


def week_key(value: datetime) -> tuple[int, int]:
    """ISO (year, week) of a datetime in local time."""
    iso = to_local(value).isocalendar()
    return iso.year, iso.week


def week_label(key: tuple[int, int]) -> str:
    return f"S{key[1]:02d}"
