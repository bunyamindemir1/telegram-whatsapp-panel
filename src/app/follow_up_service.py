from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update

from app.database import async_session
from app.message_store import conversation_notifications_blocked
from app.messaging import send_platform_message
from app.models import ChatMessage, FollowUpReminder

logger = logging.getLogger(__name__)


async def create_follow_up(
    *,
    platform: str,
    chat_id: str,
    reminder_text: str,
    wait_hours: int = 24,
    account_id: Optional[int] = None,
    chat_name: str = "",
    due_at: Optional[datetime] = None,
    anchor_at: Optional[datetime] = None,
) -> dict[str, Any]:
    await cancel_follow_ups_for_chat(platform, chat_id, account_id)
    now = datetime.utcnow()
    anchor = anchor_at or now
    due = due_at or (now + timedelta(hours=max(1, wait_hours)))
    row = FollowUpReminder(
        platform=platform,
        account_id=account_id,
        chat_id=chat_id,
        chat_name=chat_name or chat_id,
        wait_hours=max(1, wait_hours),
        reminder_text=reminder_text.strip(),
        status="pending",
        due_at=due,
        anchor_at=anchor,
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"id": row.id, "due_at": row.due_at.isoformat() + "Z"}


async def list_follow_ups(
    platform: Optional[str] = None,
    status: str = "pending",
) -> list[dict[str, Any]]:
    async with async_session() as session:
        query = select(FollowUpReminder).order_by(FollowUpReminder.due_at.asc())
        if platform:
            query = query.where(FollowUpReminder.platform == platform)
        if status:
            query = query.where(FollowUpReminder.status == status)
        rows = (await session.execute(query)).scalars().all()
    return [
        {
            "id": r.id,
            "platform": r.platform,
            "account_id": r.account_id,
            "chat_id": r.chat_id,
            "chat_name": r.chat_name,
            "wait_hours": r.wait_hours,
            "reminder_text": r.reminder_text,
            "status": r.status,
            "due_at": r.due_at.isoformat() + "Z",
            "anchor_at": r.anchor_at.isoformat() + "Z",
        }
        for r in rows
    ]


async def cancel_follow_up(follow_up_id: int) -> bool:
    async with async_session() as session:
        row = await session.get(FollowUpReminder, follow_up_id)
        if not row or row.status != "pending":
            return False
        row.status = "cancelled"
        await session.commit()
        return True


async def cancel_follow_ups_for_chat(
    platform: str,
    chat_id: str,
    account_id: Optional[int] = None,
) -> int:
    async with async_session() as session:
        query = select(FollowUpReminder).where(
            FollowUpReminder.platform == platform,
            FollowUpReminder.chat_id == chat_id,
            FollowUpReminder.status == "pending",
        )
        if account_id is not None:
            query = query.where(FollowUpReminder.account_id == account_id)
        rows = (await session.execute(query)).scalars().all()
        for row in rows:
            row.status = "cancelled"
        await session.commit()
        return len(rows)


async def _has_inbound_since(
    platform: str,
    chat_id: str,
    account_id: Optional[int],
    since: datetime,
) -> bool:
    async with async_session() as session:
        stmt = select(ChatMessage.id).where(
            ChatMessage.platform == platform,
            ChatMessage.chat_id == chat_id,
            ChatMessage.from_me.is_(False),
            ChatMessage.timestamp > since,
        )
        if account_id is not None:
            stmt = stmt.where(ChatMessage.account_id == account_id)
        return (await session.scalar(stmt.limit(1))) is not None


async def _claim_follow_up(follow_up_id: int) -> Optional[FollowUpReminder]:
    async with async_session() as session:
        result = await session.execute(
            update(FollowUpReminder)
            .where(
                FollowUpReminder.id == follow_up_id,
                FollowUpReminder.status == "pending",
            )
            .values(status="processing")
        )
        if not result.rowcount:
            return None
        await session.commit()
        return await session.get(FollowUpReminder, follow_up_id)


async def process_due_follow_ups() -> int:
    now = datetime.utcnow()
    triggered = 0
    async with async_session() as session:
        rows = (
            await session.execute(
                select(FollowUpReminder.id).where(
                    FollowUpReminder.status == "pending",
                    FollowUpReminder.due_at <= now,
                )
            )
        ).scalars().all()

    for follow_up_id in rows:
        row = await _claim_follow_up(follow_up_id)
        if not row:
            continue

        if await _has_inbound_since(row.platform, row.chat_id, row.account_id, row.anchor_at):
            async with async_session() as session:
                db_row = await session.get(FollowUpReminder, row.id)
                if db_row:
                    db_row.status = "cancelled"
                    await session.commit()
            continue

        if await conversation_notifications_blocked(row.platform, row.chat_id, row.account_id):
            async with async_session() as session:
                db_row = await session.get(FollowUpReminder, row.id)
                if db_row:
                    db_row.status = "cancelled"
                    await session.commit()
            continue

        try:
            await send_platform_message(
                row.platform,
                row.chat_id,
                row.reminder_text,
                chat_name=row.chat_name,
                account_id=row.account_id,
            )
            async with async_session() as session:
                db_row = await session.get(FollowUpReminder, row.id)
                if db_row:
                    db_row.status = "triggered"
                    await session.commit()
            from app.webhook_service import dispatch_webhook

            await dispatch_webhook(
                "follow_up.triggered",
                {
                    "follow_up_id": row.id,
                    "platform": row.platform,
                    "account_id": row.account_id,
                    "chat_id": row.chat_id,
                    "chat_name": row.chat_name,
                    "reminder_text": row.reminder_text,
                },
            )
            triggered += 1
        except Exception as exc:
            logger.warning("Follow-up %s failed: %s", row.id, exc)
            async with async_session() as session:
                db_row = await session.get(FollowUpReminder, row.id)
                if db_row:
                    db_row.status = "pending"
                    await session.commit()
    return triggered


def register_follow_up_checker(scheduler) -> None:
    if scheduler.get_job("follow_up_checker"):
        return
    scheduler.add_job(
        process_due_follow_ups,
        "interval",
        minutes=15,
        id="follow_up_checker",
        replace_existing=True,
    )
