"""Rastgele günlük zaman penceresi — her gün farklı dakika/saniyede gönderim."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app import error_codes as E
from app.utils.datetime_utils import IST, UTC

MAX_PICK_ATTEMPTS = 200


def parse_hhmm(value: str) -> Tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(E.SCHEDULE_TIME_FORMAT)
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(E.SCHEDULE_INVALID_TIME)
    return hour, minute


def time_to_seconds(hour: int, minute: int, second: int = 0) -> int:
    return hour * 3600 + minute * 60 + second


def seconds_to_time(total: int) -> Tuple[int, int, int]:
    hour = total // 3600
    rem = total % 3600
    minute = rem // 60
    second = rem % 60
    return hour, minute, second


def validate_window(start: str, end: str) -> None:
    sh, sm = parse_hhmm(start)
    eh, em = parse_hhmm(end)
    start_sec = time_to_seconds(sh, sm)
    end_sec = time_to_seconds(eh, em, 59)
    if end_sec <= start_sec:
        raise ValueError(E.SCHEDULE_WINDOW_ORDER)
    if end_sec - start_sec < 59:
        raise ValueError(E.SCHEDULE_WINDOW_MIN)


def utc_naive_to_istanbul(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC).astimezone(IST)


def istanbul_to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC).replace(tzinfo=None)


def _exclude_second_of_day(exclude_utc: Optional[datetime]) -> Optional[int]:
    if not exclude_utc:
        return None
    ist = utc_naive_to_istanbul(exclude_utc)
    return time_to_seconds(ist.hour, ist.minute, ist.second)


def pick_random_in_window(
    window_start: str,
    window_end: str,
    target_day_ist: datetime,
    *,
    exclude_utc: Optional[datetime] = None,
    not_before_ist: Optional[datetime] = None,
    rng: random.Random | None = None,
) -> datetime:
    """Pencere içinde rastgele saniye seç; önceki günle aynı saniye olmasın."""
    rng = rng or random.Random()
    sh, sm = parse_hhmm(window_start)
    eh, em = parse_hhmm(window_end)
    start_sec = time_to_seconds(sh, sm)
    end_sec = time_to_seconds(eh, em, 59)
    exclude_sec = _exclude_second_of_day(exclude_utc)

    min_sec = start_sec
    if not_before_ist is not None:
        same_day = (
            not_before_ist.year == target_day_ist.year
            and not_before_ist.month == target_day_ist.month
            and not_before_ist.day == target_day_ist.day
        )
        if same_day:
            min_sec = max(min_sec, time_to_seconds(
                not_before_ist.hour, not_before_ist.minute, not_before_ist.second
            ) + 1)

    if min_sec > end_sec:
        raise ValueError(E.SCHEDULE_WINDOW_PAST)

    candidates = [
        sec for sec in range(min_sec, end_sec + 1)
        if sec != exclude_sec
    ]
    if not candidates:
        raise ValueError(E.SCHEDULE_WINDOW_SLOT)

    pick_sec = rng.choice(candidates)
    hour, minute, second = seconds_to_time(pick_sec)
    local = target_day_ist.replace(
        hour=hour, minute=minute, second=second, microsecond=0, tzinfo=IST
    )
    return istanbul_to_utc_naive(local)


def compute_initial_random_run(
    window_start: str,
    window_end: str,
    *,
    after_utc: Optional[datetime] = None,
    exclude_utc: Optional[datetime] = None,
    rng: random.Random | None = None,
) -> datetime:
    """İlk gönderim: bugün pencerede yer varsa bugün, yoksa yarın."""
    from app.utils.datetime_utils import utc_now

    after_utc = after_utc or utc_now()
    now_ist = utc_naive_to_istanbul(after_utc)
    day_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=IST)

    try:
        return pick_random_in_window(
            window_start,
            window_end,
            day_start,
            exclude_utc=exclude_utc,
            not_before_ist=now_ist,
            rng=rng,
        )
    except ValueError:
        tomorrow = day_start + timedelta(days=1)
        return pick_random_in_window(
            window_start,
            window_end,
            tomorrow,
            exclude_utc=exclude_utc,
            rng=rng,
        )


def compute_next_random_daily(
    window_start: str,
    window_end: str,
    *,
    after_utc: datetime,
    last_run_utc: Optional[datetime] = None,
    rng: random.Random | None = None,
) -> datetime:
    """Her başarılı gönderimden sonra ertesi gün için yeni rastgele zaman."""
    after_ist = utc_naive_to_istanbul(after_utc)
    next_day = (after_ist + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=IST
    )
    return pick_random_in_window(
        window_start,
        window_end,
        next_day,
        exclude_utc=last_run_utc,
        rng=rng,
    )


def format_window_label(start: str, end: str) -> str:
    return f"{start}–{end} arası rastgele"
