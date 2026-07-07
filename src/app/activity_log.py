from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.database import async_session
from app.models import ActivityLog


async def log_activity(action: str, detail: Optional[dict[str, Any]] = None) -> None:
    row = ActivityLog(
        action=action[:64],
        detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
        created_at=datetime.utcnow(),
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()


async def list_activity(limit: int = 50) -> list[dict[str, Any]]:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
            )
        ).scalars().all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "detail": json.loads(r.detail_json or "{}"),
            "created_at": r.created_at.isoformat() + "Z",
        }
        for r in rows
    ]
