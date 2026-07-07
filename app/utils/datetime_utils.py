from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import TIMEZONE

IST = ZoneInfo(TIMEZONE)
UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def istanbul_now() -> datetime:
    return datetime.now(IST)


def to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def from_client_datetime(dt: datetime) -> datetime:
    """İstemciden gelen zamanı UTC naive'e çevir (Türkiye saati varsayılan)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC).replace(tzinfo=None)


def utc_to_istanbul_iso(dt: datetime) -> str:
    aware = dt.replace(tzinfo=UTC)
    return aware.astimezone(IST).isoformat()


def format_istanbul(dt: datetime, with_seconds: bool = False) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    fmt = "%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M"
    return dt.astimezone(IST).strftime(fmt)


def ensure_future(run_at: datetime, buffer_seconds: int = 2) -> datetime:
    run_at = to_utc_naive(run_at)
    now = utc_now()
    if run_at <= now:
        return now + timedelta(seconds=buffer_seconds)
    return run_at
