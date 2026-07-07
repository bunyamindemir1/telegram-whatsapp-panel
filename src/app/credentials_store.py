from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.config import TELEGRAM_API_HASH, TELEGRAM_API_ID, TELEGRAM_PHONE
from app.database import async_session
from app.models import SecureConfig
from app.secrets import decrypt_text, encrypt_text, mask_secret
from app.security import mask_phone

TELEGRAM_CONFIG_KEY = "telegram"


def telegram_config_key(account_id: int) -> str:
    return f"telegram_{account_id}"


@dataclass
class TelegramCredentials:
    api_id: int
    api_hash: str
    app_name: str = "mesaj"
    short_name: str = "mesaj"
    phone: str = TELEGRAM_PHONE

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "TelegramCredentials":
        data = json.loads(raw)
        return cls(
            api_id=int(data["api_id"]),
            api_hash=str(data["api_hash"]),
            app_name=str(data.get("app_name", "mesaj")),
            short_name=str(data.get("short_name", "mesaj")),
            phone=str(data.get("phone", TELEGRAM_PHONE)),
        )


async def _read_row(key: str) -> Optional[SecureConfig]:
    async with async_session() as session:
        return await session.get(SecureConfig, key)


async def save_telegram_credentials(
    api_id: int,
    api_hash: str,
    *,
    account_id: int = 1,
    app_name: str = "mesaj",
    short_name: str = "mesaj",
    phone: str = TELEGRAM_PHONE,
) -> dict[str, Any]:
    creds = TelegramCredentials(
        api_id=api_id,
        api_hash=api_hash,
        app_name=app_name,
        short_name=short_name,
        phone=phone,
    )
    encrypted = encrypt_text(creds.to_json())
    key = telegram_config_key(account_id)
    async with async_session() as session:
        row = await session.get(SecureConfig, key)
        if row:
            row.value_encrypted = encrypted
            row.updated_at = datetime.utcnow()
        else:
            session.add(SecureConfig(key=key, value_encrypted=encrypted))
        await session.commit()
    return telegram_credentials_masked(creds)


def telegram_credentials_masked(creds: TelegramCredentials) -> dict[str, Any]:
    return {
        "configured": True,
        "api_id": creds.api_id,
        "api_hash_masked": mask_secret(creds.api_hash),
        "app_name": creds.app_name,
        "short_name": creds.short_name,
        "phone_masked": mask_phone(creds.phone),
        "storage": "encrypted_db",
    }


async def get_telegram_credentials(account_id: int = 1) -> Optional[TelegramCredentials]:
    row = await _read_row(telegram_config_key(account_id))
    if not row and account_id == 1:
        row = await _read_row(TELEGRAM_CONFIG_KEY)
    if row:
        return TelegramCredentials.from_json(decrypt_text(row.value_encrypted))

    if account_id == 1 and TELEGRAM_API_ID and TELEGRAM_API_HASH:
        return TelegramCredentials(
            api_id=int(TELEGRAM_API_ID),
            api_hash=TELEGRAM_API_HASH,
            phone=TELEGRAM_PHONE,
        )
    return None


async def get_telegram_credentials_public(account_id: int = 1) -> dict[str, Any]:
    creds = await get_telegram_credentials(account_id)
    if not creds:
        return {
            "configured": False,
            "storage": "encrypted_db",
            "phone_masked": mask_phone(TELEGRAM_PHONE),
            "account_id": account_id,
        }
    data = telegram_credentials_masked(creds)
    data["account_id"] = account_id
    return data


async def migrate_legacy_credentials_to_account(account_id: int = 1) -> bool:
    legacy = await _read_row(TELEGRAM_CONFIG_KEY)
    if not legacy:
        return False
    if await _read_row(telegram_config_key(account_id)):
        return False
    async with async_session() as session:
        session.add(SecureConfig(key=telegram_config_key(account_id), value_encrypted=legacy.value_encrypted))
        await session.commit()
    return True


async def seed_telegram_credentials_if_missing() -> bool:
    existing = await _read_row(TELEGRAM_CONFIG_KEY)
    if existing:
        return False

    if TELEGRAM_API_ID and TELEGRAM_API_HASH:
        await save_telegram_credentials(
            int(TELEGRAM_API_ID),
            TELEGRAM_API_HASH,
            phone=TELEGRAM_PHONE,
        )
        return True

    return False
