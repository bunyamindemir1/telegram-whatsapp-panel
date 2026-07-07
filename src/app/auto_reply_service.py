from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select

from app.database import async_session
from app.message_store import conversation_notifications_blocked
from app.messaging import send_platform_message
from app.models import AutoReplyRule

logger = logging.getLogger(__name__)


def _matches(keyword: str, text: str, mode: str) -> bool:
    kw = keyword.strip()
    body = text or ""
    if not kw or not body.strip():
        return False
    if mode == "exact":
        return body.strip().lower() == kw.lower()
    if mode == "regex":
        try:
            return re.search(kw, body, re.IGNORECASE) is not None
        except re.error:
            return False
    return kw.lower() in body.lower()


def _load_chat_cooldowns(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


async def list_auto_reply_rules(platform: Optional[str] = None) -> list[dict[str, Any]]:
    async with async_session() as session:
        query = select(AutoReplyRule).where(AutoReplyRule.is_active.is_(True)).order_by(
            AutoReplyRule.created_at.desc()
        )
        if platform:
            query = query.where(AutoReplyRule.platform == platform)
        rows = (await session.execute(query)).scalars().all()
        return [
            {
                "id": r.id,
                "account_id": r.account_id,
                "platform": r.platform,
                "keyword": r.keyword,
                "response_text": r.response_text,
                "match_mode": r.match_mode,
                "cooldown_minutes": r.cooldown_minutes,
                "is_active": r.is_active,
                "last_triggered_at": (
                    r.last_triggered_at.isoformat() + "Z" if r.last_triggered_at else None
                ),
            }
            for r in rows
        ]


async def create_auto_reply_rule(
    *,
    platform: str,
    keyword: str,
    response_text: str,
    account_id: Optional[int] = None,
    match_mode: str = "contains",
    cooldown_minutes: int = 60,
) -> dict[str, Any]:
    row = AutoReplyRule(
        platform=platform,
        keyword=keyword.strip(),
        response_text=response_text.strip(),
        account_id=account_id,
        match_mode=match_mode if match_mode in ("contains", "exact", "regex") else "contains",
        cooldown_minutes=max(1, cooldown_minutes),
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"id": row.id}


async def update_auto_reply_rule(
    rule_id: int,
    *,
    keyword: Optional[str] = None,
    response_text: Optional[str] = None,
    match_mode: Optional[str] = None,
    cooldown_minutes: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> bool:
    async with async_session() as session:
        row = await session.get(AutoReplyRule, rule_id)
        if not row:
            return False
        if keyword is not None:
            row.keyword = keyword.strip()
        if response_text is not None:
            row.response_text = response_text.strip()
        if match_mode is not None:
            row.match_mode = match_mode if match_mode in ("contains", "exact", "regex") else row.match_mode
        if cooldown_minutes is not None:
            row.cooldown_minutes = max(1, cooldown_minutes)
        if is_active is not None:
            row.is_active = is_active
        await session.commit()
        return True


async def delete_auto_reply_rule(rule_id: int) -> bool:
    async with async_session() as session:
        row = await session.get(AutoReplyRule, rule_id)
        if not row:
            return False
        row.is_active = False
        await session.commit()
        return True


async def try_auto_reply(
    *,
    platform: str,
    account_id: int,
    chat_id: str,
    text: str,
    chat_name: str = "",
    chat_type: str = "unknown",
) -> Optional[dict[str, Any]]:
    if not text or not text.strip():
        return None
    if await conversation_notifications_blocked(platform, chat_id, account_id):
        return None

    async with async_session() as session:
        result = await session.execute(
            select(AutoReplyRule).where(
                AutoReplyRule.is_active.is_(True),
                AutoReplyRule.platform == platform,
            )
        )
        rules = result.scalars().all()

    now = datetime.utcnow()
    for rule in rules:
        if rule.account_id is not None and rule.account_id != account_id:
            continue
        if not _matches(rule.keyword, text, rule.match_mode):
            continue

        cooldown = timedelta(minutes=rule.cooldown_minutes or 60)
        async with async_session() as session:
            db_rule = await session.get(AutoReplyRule, rule.id)
            if not db_rule:
                continue
            chat_cooldowns = _load_chat_cooldowns(getattr(db_rule, "chat_cooldowns_json", None))
            last_raw = chat_cooldowns.get(chat_id)
            if last_raw:
                try:
                    last_at = datetime.fromisoformat(last_raw.replace("Z", ""))
                    if now - last_at < cooldown:
                        continue
                except ValueError:
                    pass

        try:
            sent = await send_platform_message(
                platform,
                chat_id,
                rule.response_text,
                chat_name=chat_name,
                chat_type=chat_type,
                account_id=account_id,
            )
            async with async_session() as session:
                db_rule = await session.get(AutoReplyRule, rule.id)
                if db_rule:
                    chat_cooldowns = _load_chat_cooldowns(getattr(db_rule, "chat_cooldowns_json", None))
                    chat_cooldowns[chat_id] = now.isoformat()
                    db_rule.chat_cooldowns_json = json.dumps(chat_cooldowns)
                    db_rule.last_triggered_at = now
                    await session.commit()
            return {"rule_id": rule.id, "sent": sent}
        except Exception as exc:
            logger.warning("Auto-reply failed rule %s: %s", rule.id, exc)
    return None
