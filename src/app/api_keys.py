from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, update

from app.database import async_session
from app.models import ApiKey


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, prefix, hash)."""
    raw = f"mp_{secrets.token_urlsafe(32)}"
    return raw, raw[:12], _hash_key(raw)


async def create_api_key(name: str, user_id: Optional[int] = None) -> tuple[ApiKey, str]:
    raw, prefix, key_hash = generate_api_key()
    async with async_session() as session:
        row = ApiKey(name=name.strip(), key_prefix=prefix, key_hash=key_hash, user_id=user_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row, raw


async def list_api_keys() -> list[dict[str, Any]]:
    async with async_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.is_active == True).order_by(ApiKey.created_at.desc())  # noqa: E712
        )
        keys = result.scalars().all()
        return [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None,
                "created_at": k.created_at.isoformat() + "Z",
            }
            for k in keys
        ]


async def revoke_api_key(key_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.id == key_id))
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_active = False
        await session.commit()
        return True


async def verify_api_key(raw_key: str) -> Optional[ApiKey]:
    if not raw_key or not raw_key.startswith("mp_"):
        return None
    key_hash = _hash_key(raw_key)
    async with async_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        await session.execute(
            update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=datetime.utcnow())
        )
        await session.commit()
        return row
