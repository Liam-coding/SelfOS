"""Comparable sourced instants and explicit UTC calendar-day boundaries."""
from datetime import datetime, timezone, date, time


def instant(value):
    if not isinstance(value,str) or 'T' not in value:return None
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def boundary(value):
    precise=instant(value)
    if precise is not None:return precise
    if not isinstance(value,str):return None
    try:day=date.fromisoformat(value)
    except ValueError:return None
    return datetime.combine(day,time.min,tzinfo=timezone.utc) if day.isoformat()==value else None
