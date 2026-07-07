from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select, update

from app.database import async_session
from app.models import Webhook

logger = logging.getLogger(__name__)

EVENT_TYPES = (
    "message.received",
    "message.sent",
    "account.connected",
    "account.disconnected",
    "scheduled.sent",
    "scheduled.failed",
    "follow_up.triggered",
)


async def list_webhooks() -> list[dict[str, Any]]:
    async with async_session() as session:
        rows = (await session.execute(
            select(Webhook).where(Webhook.is_active == True).order_by(Webhook.created_at.desc())  # noqa: E712
        )).scalars().all()
        return [
            {
                "id": w.id,
                "name": w.name,
                "url": w.url,
                "events": json.loads(w.events_json or "[]"),
                "created_at": w.created_at.isoformat() + "Z",
            }
            for w in rows
        ]


async def create_webhook(name: str, url: str, events: list[str], secret: str = "") -> Webhook:
    filtered = [e for e in events if e in EVENT_TYPES]
    if not filtered:
        filtered = ["message.received"]
    async with async_session() as session:
        row = Webhook(
            name=name.strip(),
            url=url.strip(),
            events_json=json.dumps(filtered),
            secret=secret.strip() or None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def delete_webhook(webhook_id: int) -> bool:
    async with async_session() as session:
        row = await session.get(Webhook, webhook_id)
        if not row:
            return False
        row.is_active = False
        await session.commit()
        return True


def _sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def dispatch_webhook(event: str, payload: dict[str, Any]) -> None:
    async with async_session() as session:
        rows = (await session.execute(
            select(Webhook).where(Webhook.is_active == True)  # noqa: E712
        )).scalars().all()

    body = {"event": event, "timestamp": datetime.utcnow().isoformat() + "Z", "data": payload}
    raw = json.dumps(body, default=str).encode()

    for hook in rows:
        try:
            events = json.loads(hook.events_json or "[]")
            if event not in events:
                continue
            headers = {"Content-Type": "application/json", "User-Agent": "MesajPanel-Webhook/1.0"}
            if hook.secret:
                headers["X-Mesaj-Signature"] = _sign_payload(hook.secret, raw)
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(hook.url, content=raw, headers=headers)
        except Exception as exc:
            logger.warning("Webhook %s failed: %s", hook.id, exc)
