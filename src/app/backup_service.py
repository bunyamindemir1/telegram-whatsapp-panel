from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.database import async_session
from app.models import AutoReplyRule, FollowUpReminder, MessageTemplate, ScheduledMessage


async def export_panel_backup() -> dict[str, Any]:
    async with async_session() as session:
        templates = (await session.execute(select(MessageTemplate))).scalars().all()
        rules = (
            await session.execute(select(AutoReplyRule).where(AutoReplyRule.is_active.is_(True)))
        ).scalars().all()
        jobs = (
            await session.execute(
                select(ScheduledMessage).where(ScheduledMessage.is_active.is_(True))
            )
        ).scalars().all()
        follow_ups = (
            await session.execute(
                select(FollowUpReminder).where(FollowUpReminder.status == "pending")
            )
        ).scalars().all()

    return {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "templates": [
            {
                "title": t.title,
                "message_text": t.message_text,
                "category": getattr(t, "category", None) or "general",
            }
            for t in templates
        ],
        "auto_replies": [
            {
                "platform": r.platform,
                "account_id": r.account_id,
                "keyword": r.keyword,
                "response_text": r.response_text,
                "match_mode": r.match_mode,
                "cooldown_minutes": r.cooldown_minutes,
            }
            for r in rules
        ],
        "scheduled": [
            {
                "platform": j.platform,
                "account_id": j.account_id,
                "chat_id": j.chat_id,
                "chat_name": j.chat_name,
                "chat_type": j.chat_type,
                "message_text": j.message_text,
                "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
                "repeat_type": j.repeat_type,
                "repeat_interval_minutes": j.repeat_interval_minutes,
                "window_start_time": j.window_start_time,
                "window_end_time": j.window_end_time,
            }
            for j in jobs
        ],
        "follow_ups": [
            {
                "platform": f.platform,
                "account_id": f.account_id,
                "chat_id": f.chat_id,
                "chat_name": f.chat_name,
                "wait_hours": f.wait_hours,
                "reminder_text": f.reminder_text,
                "due_at": f.due_at.isoformat() if f.due_at else None,
            }
            for f in follow_ups
        ],
    }


async def import_panel_backup(data: dict[str, Any], *, merge: bool = True) -> dict[str, int]:
    from app.auto_reply_service import create_auto_reply_rule
    from app.follow_up_service import create_follow_up
    from app.scheduler_service import schedule_message

    counts = {"templates": 0, "auto_replies": 0, "scheduled": 0, "follow_ups": 0}

    if not merge:
        from app.scheduler_service import cancel_job

        async with async_session() as session:
            job_ids = [
                j.id
                for j in (await session.execute(select(ScheduledMessage))).scalars().all()
            ]
        for jid in job_ids:
            await cancel_job(jid)
        async with async_session() as session:
            for model in (MessageTemplate, AutoReplyRule, ScheduledMessage, FollowUpReminder):
                for row in (await session.execute(select(model))).scalars().all():
                    await session.delete(row)
            await session.commit()

    async with async_session() as session:
        for tpl in data.get("templates") or []:
            if not tpl.get("title") or not tpl.get("message_text"):
                continue
            session.add(
                MessageTemplate(
                    title=tpl["title"][:120],
                    message_text=tpl["message_text"],
                    category=(tpl.get("category") or "general")[:64],
                )
            )
            counts["templates"] += 1
        await session.commit()

    for rule in data.get("auto_replies") or []:
        if not rule.get("keyword") or not rule.get("response_text"):
            continue
        await create_auto_reply_rule(
            platform=rule.get("platform", "telegram"),
            keyword=rule["keyword"],
            response_text=rule["response_text"],
            account_id=rule.get("account_id"),
            match_mode=rule.get("match_mode", "contains"),
            cooldown_minutes=int(rule.get("cooldown_minutes") or 60),
        )
        counts["auto_replies"] += 1

    for job in data.get("scheduled") or []:
        if not job.get("chat_id") or not job.get("message_text"):
            continue
        scheduled_at = datetime.fromisoformat(job["scheduled_at"].replace("Z", "")) if job.get("scheduled_at") else datetime.utcnow()
        row = ScheduledMessage(
            platform=job.get("platform", "telegram"),
            account_id=job.get("account_id"),
            chat_id=job["chat_id"],
            chat_name=job.get("chat_name") or job["chat_id"],
            chat_type=job.get("chat_type", "unknown"),
            message_text=job["message_text"],
            scheduled_at=scheduled_at,
            repeat_type=job.get("repeat_type", "none"),
            repeat_interval_minutes=job.get("repeat_interval_minutes"),
            window_start_time=job.get("window_start_time"),
            window_end_time=job.get("window_end_time"),
            status="pending",
            is_active=True,
            next_run_at=scheduled_at,
            send_count=0,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            jid = row.id
        async with async_session() as session:
            db_job = await session.get(ScheduledMessage, jid)
            if db_job:
                from app.models import RepeatType
                from app.scheduler_service import prepare_random_daily_job, schedule_message

                if db_job.repeat_type == RepeatType.RANDOM_DAILY.value:
                    prepare_random_daily_job(db_job)
                    await session.commit()
                await schedule_message(db_job)
                await session.commit()
        counts["scheduled"] += 1

    for fu in data.get("follow_ups") or []:
        if not fu.get("chat_id") or not fu.get("reminder_text"):
            continue
        wait_hours = int(fu.get("wait_hours") or 24)
        due_at = None
        anchor_at = None
        if fu.get("due_at"):
            due_at = datetime.fromisoformat(fu["due_at"].replace("Z", ""))
            anchor_at = due_at - timedelta(hours=wait_hours)
        await create_follow_up(
            platform=fu.get("platform", "telegram"),
            chat_id=fu["chat_id"],
            reminder_text=fu["reminder_text"],
            wait_hours=wait_hours,
            account_id=fu.get("account_id"),
            chat_name=fu.get("chat_name") or fu["chat_id"],
            due_at=due_at,
            anchor_at=anchor_at,
        )
        counts["follow_ups"] += 1

    return counts
