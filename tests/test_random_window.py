import random
from datetime import datetime

import pytest

from app.models import JobStatus, RepeatType, ScheduledMessage
from app.random_window import (
    compute_initial_random_run,
    compute_next_random_daily,
    pick_random_in_window,
    utc_naive_to_istanbul,
    validate_window,
)
from app.scheduler_service import compute_next_run
from app.utils.datetime_utils import IST


def _ist_day(year, month, day):
    return datetime(year, month, day, tzinfo=IST)


class TestRandomWindow:
    def test_validate_window_rejects_inverted(self):
        with pytest.raises(ValueError, match="sonra"):
            validate_window("08:00", "07:00")

    def test_validate_window_allows_one_minute_slot(self):
        validate_window("07:00", "07:00")  # 07:00:00–07:00:59

    def test_pick_excludes_previous_second(self):
        rng = random.Random(42)
        target = _ist_day(2026, 7, 8)
        exclude = datetime(2026, 7, 7, 4, 15, 30)  # 07:15:30 TR ≈ 04:15:30 UTC
        picked = pick_random_in_window(
            "07:00", "07:30", target, exclude_utc=exclude, rng=rng
        )
        ist = utc_naive_to_istanbul(picked)
        assert ist.hour == 7
        assert ist.minute >= 0
        assert not (ist.hour == 7 and ist.minute == 15 and ist.second == 30)

    def test_pick_two_days_never_same_second(self):
        rng = random.Random(7)
        day1 = pick_random_in_window("07:00", "07:30", _ist_day(2026, 7, 8), rng=rng)
        day2 = pick_random_in_window(
            "07:00", "07:30", _ist_day(2026, 7, 9), exclude_utc=day1, rng=rng
        )
        t1 = utc_naive_to_istanbul(day1)
        t2 = utc_naive_to_istanbul(day2)
        assert (t1.hour, t1.minute, t1.second) != (t2.hour, t2.minute, t2.second)

    def test_compute_next_random_daily_is_next_day(self):
        rng = random.Random(99)
        after = datetime(2026, 7, 7, 4, 0, 0)
        last = datetime(2026, 7, 7, 4, 12, 5)
        nxt = compute_next_random_daily(
            "07:00", "07:30", after_utc=after, last_run_utc=last, rng=rng
        )
        ist = utc_naive_to_istanbul(nxt)
        assert ist.day == 8
        assert 7 <= ist.hour <= 7
        assert ist.minute <= 30

    def test_compute_next_run_random_daily(self):
        job = ScheduledMessage(
            id=1,
            chat_id="1",
            chat_name="Grup",
            message_text="Günaydın",
            scheduled_at=datetime(2026, 7, 7, 4, 10, 0),
            repeat_type=RepeatType.RANDOM_DAILY.value,
            window_start_time="07:00",
            window_end_time="07:30",
            last_run_at=datetime(2026, 7, 7, 4, 10, 0),
            status=JobStatus.PENDING.value,
            is_active=True,
        )
        nxt = compute_next_run(job, datetime(2026, 7, 7, 4, 10, 0))
        assert nxt is not None
        ist = utc_naive_to_istanbul(nxt)
        assert ist.day == 8

    def test_initial_run_respects_future_today(self):
        rng = random.Random(1)
        # Sabah 06:00 TR = 03:00 UTC — pencere 07:00-07:30 henüz açılmadı
        after = datetime(2026, 7, 7, 3, 0, 0)
        run = compute_initial_random_run(
            "07:00", "07:30", after_utc=after, rng=rng
        )
        ist = utc_naive_to_istanbul(run)
        assert ist.day == 7
        assert ist.hour == 7
