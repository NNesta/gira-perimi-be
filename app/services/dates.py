from datetime import date, datetime, time, timedelta, timezone

# Rwanda is UTC+2 all year (no daylight saving), so a fixed offset is exact.
KIGALI = timezone(timedelta(hours=2), "CAT")


def local_day(moment: datetime) -> date:
    return moment.astimezone(KIGALI).date()


def day_start(day: date) -> datetime:
    """Midnight in Kigali at the start of `day`, as an aware datetime."""
    return datetime.combine(day, time.min, tzinfo=KIGALI)
