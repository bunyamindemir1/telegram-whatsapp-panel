from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select

from app.database import async_session
from app import error_codes as E
from app.models import JobStatus, RepeatType, ScheduledMessage
from app.messaging import send_platform_message
from app.random_window import compute_next_random_daily
from app.template_engine import build_template_context, render_template
from app.utils.datetime_utils import ensure_future, to_utc_naive, utc_now

scheduler = AsyncIOScheduler(timezone="UTC")
_job_locks: set[int] = set()


def _job_webhook_payload(job: ScheduledMessage, **extra: object) -> dict:
    return {
        "job_id": job.id,
        "platform": job.platform,
        "account_id": job.account_id,
        "chat_id": job.chat_id,
        "chat_name": job.chat_name,
        "chat_type": job.chat_type,
        "message_text": job.message_text,
        "status": job.status,
        "repeat_type": job.repeat_type,
        "send_count": job.send_count or 0,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        **extra,
    }


async def _dispatch_scheduled_webhook(event: str, job: ScheduledMessage, **extra: object) -> None:
    from app.webhook_service import dispatch_webhook

    await dispatch_webhook(event, _job_webhook_payload(job, **extra))


def compute_next_run(job: ScheduledMessage, after: Optional[datetime] = None) -> Optional[datetime]:
    base = to_utc_naive(after or utc_now())
    anchor = to_utc_naive(job.scheduled_at)

    if job.repeat_type == RepeatType.NONE.value:
        return None

    if job.repeat_type == RepeatType.HOURLY.value:
        return base + timedelta(hours=1)

    if job.repeat_type == RepeatType.DAILY.value:
        nxt = base + timedelta(days=1)
        return nxt.replace(hour=anchor.hour, minute=anchor.minute, second=0, microsecond=0)

    if job.repeat_type == RepeatType.WEEKLY.value:
        nxt = base + timedelta(weeks=1)
        return nxt.replace(hour=anchor.hour, minute=anchor.minute, second=0, microsecond=0)

    if job.repeat_type == RepeatType.CUSTOM.value and job.repeat_interval_minutes:
        return base + timedelta(minutes=job.repeat_interval_minutes)

    if job.repeat_type == RepeatType.RANDOM_DAILY.value:
        if not job.window_start_time or not job.window_end_time:
            return None
        return compute_next_random_daily(
            job.window_start_time,
            job.window_end_time,
            after_utc=base,
            last_run_utc=job.last_run_at,
        )

    return None


def _schedule_db_job(job: ScheduledMessage) -> None:
    run_at = ensure_future(to_utc_naive(job.next_run_at or job.scheduled_at))
    # APScheduler naive datetime'ı yerel saat sanıyor — UTC aware kullan
    run_at_aware = run_at.replace(tzinfo=timezone.utc)

    scheduler.add_job(
        _execute_job,
        trigger=DateTrigger(run_date=run_at_aware),
        args=[job.id],
        id=f"msg_{job.id}",
        replace_existing=True,
        misfire_grace_time=86400,
        coalesce=True,
        max_instances=1,
    )


async def _execute_job(job_id: int) -> None:
    if job_id in _job_locks:
        return

    _job_locks.add(job_id)
    try:
        async with async_session() as session:
            job = await session.get(ScheduledMessage, job_id)
            if not job or not job.is_active:
                return

            if job.status == JobStatus.RUNNING.value:
                return

            job.status = JobStatus.RUNNING.value
            job.error_message = None
            await session.commit()

        async with async_session() as session:
            job = await session.get(ScheduledMessage, job_id)
            if not job or not job.is_active:
                return

            try:
                ctx = build_template_context(
                    chat_name=job.chat_name or job.chat_id,
                    chat_id=job.chat_id,
                    platform=job.platform,
                )
                rendered = render_template(job.message_text, ctx)
                result = await send_platform_message(
                    job.platform,
                    job.chat_id,
                    rendered,
                    chat_name=job.chat_name,
                    chat_type=job.chat_type,
                    allow_simulate=True,
                    account_id=job.account_id,
                )
                now = utc_now()
                job.last_run_at = now
                if result.get("dry_run"):
                    job.error_message = None
                else:
                    job.error_message = None
                    await _dispatch_scheduled_webhook(
                        "scheduled.sent",
                        job,
                        rendered_text=rendered,
                        dry_run=False,
                    )
                job.send_count = (job.send_count or 0) + 1

                next_run = compute_next_run(job, now)
                if next_run:
                    job.next_run_at = next_run
                    job.scheduled_at = next_run
                    job.status = JobStatus.PENDING.value
                    await session.commit()
                    _schedule_db_job(job)
                else:
                    job.status = JobStatus.SENT.value
                    job.is_active = False
                    job.next_run_at = None
                    await session.commit()
            except Exception as exc:
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)

                if job.repeat_type != RepeatType.NONE.value:
                    retry_at = utc_now() + timedelta(minutes=5)
                    job.next_run_at = retry_at
                    job.status = JobStatus.PENDING.value
                    await session.commit()
                    _schedule_db_job(job)
                else:
                    job.is_active = False
                    await session.commit()
                    await _dispatch_scheduled_webhook(
                        "scheduled.failed",
                        job,
                        error=str(exc),
                    )
    finally:
        _job_locks.discard(job_id)


async def schedule_message(job: ScheduledMessage) -> ScheduledMessage:
    job.scheduled_at = to_utc_naive(job.scheduled_at)
    job.next_run_at = to_utc_naive(job.next_run_at or job.scheduled_at)
    job.status = JobStatus.PENDING.value
    job.is_active = True
    _schedule_db_job(job)
    return job


def prepare_random_daily_job(job: ScheduledMessage) -> None:
    """random_daily işleri için ilk çalıştırma zamanını hesapla."""
    from app.random_window import compute_initial_random_run, validate_window

    if not job.window_start_time or not job.window_end_time:
        raise ValueError(E.SCHEDULE_RANDOM_WINDOW)
    validate_window(job.window_start_time, job.window_end_time)
    run_at = compute_initial_random_run(
        job.window_start_time,
        job.window_end_time,
        after_utc=utc_now(),
    )
    job.scheduled_at = run_at
    job.next_run_at = run_at


async def cancel_job(job_id: int) -> None:
    try:
        scheduler.remove_job(f"msg_{job_id}")
    except Exception:
        pass

    async with async_session() as session:
        job = await session.get(ScheduledMessage, job_id)
        if job:
            job.is_active = False
            job.status = JobStatus.CANCELLED.value
            await session.commit()


async def retry_job(job_id: int) -> None:
    async with async_session() as session:
        job = await session.get(ScheduledMessage, job_id)
        if not job:
            raise ValueError(E.MESSAGE_NOT_FOUND)

        job.is_active = True
        job.status = JobStatus.PENDING.value
        job.error_message = None
        job.next_run_at = ensure_future(utc_now())
        await session.commit()
        _schedule_db_job(job)


async def load_pending_jobs() -> None:
    from app.follow_up_service import register_follow_up_checker, reset_stale_processing_follow_ups

    await reset_stale_processing_follow_ups()
    register_follow_up_checker(scheduler)
    async with async_session() as session:
        result = await session.execute(
            select(ScheduledMessage).where(
                ScheduledMessage.is_active.is_(True),
                ScheduledMessage.status.in_(
                    [JobStatus.PENDING.value, JobStatus.RUNNING.value]
                ),
            )
        )
        jobs = result.scalars().all()

        for job in jobs:
            if job.status == JobStatus.RUNNING.value:
                job.status = JobStatus.PENDING.value
            if not job.next_run_at:
                job.next_run_at = job.scheduled_at
            await session.commit()
            _schedule_db_job(job)


async def send_now(job_id: int) -> None:
    if job_id in _job_locks:
        raise RuntimeError(E.MESSAGE_SENDING)

    async with async_session() as session:
        job = await session.get(ScheduledMessage, job_id)
        if not job:
            raise ValueError(E.MESSAGE_NOT_FOUND)
        job.next_run_at = ensure_future(utc_now())
        job.is_active = True
        job.status = JobStatus.PENDING.value
        await session.commit()

    await _execute_job(job_id)


def get_scheduler_status() -> dict:
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "active_jobs": len(jobs),
        "next_run": min((j.next_run_time.isoformat() for j in jobs if j.next_run_time), default=None),
    }
