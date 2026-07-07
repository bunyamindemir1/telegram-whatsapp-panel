"""Platform hesapları — çoklu Telegram / WhatsApp yönetimi."""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from sqlalchemy import select, update

from app.config import DATA_DIR, SESSIONS_DIR
from app.database import async_session
from app.models import Platform, PlatformAccount
from app.security import mask_phone

DEFAULT_LABELS = {
    Platform.TELEGRAM.value: "Telegram 1",
    Platform.WHATSAPP.value: "WhatsApp 1",
}


def _slug_bridge_id(account_id: int) -> str:
    return str(account_id)


def serialize_account(acc: PlatformAccount) -> dict[str, Any]:
    return {
        "id": acc.id,
        "platform": acc.platform,
        "label": acc.label,
        "display_name": acc.display_name,
        "phone_masked": acc.phone_masked,
        "external_id": acc.external_id,
        "status": acc.status or "disconnected",
        "is_default": bool(acc.is_default),
        "bridge_id": acc.bridge_id or _slug_bridge_id(acc.id),
        "created_at": acc.created_at.isoformat() + "Z" if acc.created_at else None,
    }


async def list_accounts(platform: Optional[str] = None) -> list[dict[str, Any]]:
    async with async_session() as session:
        q = select(PlatformAccount).where(PlatformAccount.is_active.is_(True))
        if platform:
            q = q.where(PlatformAccount.platform == platform)
        q = q.order_by(PlatformAccount.platform, PlatformAccount.id)
        rows = (await session.execute(q)).scalars().all()
        return [serialize_account(r) for r in rows]


async def get_account(account_id: int) -> Optional[PlatformAccount]:
    async with async_session() as session:
        return await session.get(PlatformAccount, account_id)


async def get_default_account_id(platform: str) -> int:
    async with async_session() as session:
        row = await session.scalar(
            select(PlatformAccount)
            .where(
                PlatformAccount.platform == platform,
                PlatformAccount.is_active.is_(True),
                PlatformAccount.is_default.is_(True),
            )
            .limit(1)
        )
        if row:
            return row.id
        row = await session.scalar(
            select(PlatformAccount)
            .where(PlatformAccount.platform == platform, PlatformAccount.is_active.is_(True))
            .order_by(PlatformAccount.id)
            .limit(1)
        )
        if row:
            return row.id
    acc = await create_account(platform, DEFAULT_LABELS.get(platform, "Hesap 1"), make_default=True)
    return acc["id"]


async def resolve_whatsapp_panel_account(bridge_id: Union[str, int]) -> int:
    """Köprü hesap kimliğini (bridge_id) panel PlatformAccount.id değerine çevirir."""
    bid = str(bridge_id)
    async with async_session() as session:
        row = await session.scalar(
            select(PlatformAccount.id)
            .where(
                PlatformAccount.platform == Platform.WHATSAPP.value,
                PlatformAccount.is_active.is_(True),
                PlatformAccount.bridge_id == bid,
            )
            .limit(1)
        )
        if row:
            return row
    try:
        aid = int(bridge_id)
        acc = await get_account(aid)
        if acc and acc.is_active and acc.platform == Platform.WHATSAPP.value:
            return aid
    except (TypeError, ValueError):
        pass
    return await get_default_account_id(Platform.WHATSAPP.value)


async def resolve_account_id(platform: str, account_id: Optional[int] = None) -> int:
    if account_id is not None:
        acc = await get_account(account_id)
        if not acc or not acc.is_active or acc.platform != platform:
            raise ValueError("Geçersiz hesap")
        return account_id
    return await get_default_account_id(platform)


async def create_account(
    platform: str,
    label: str,
    *,
    make_default: bool = False,
) -> dict[str, Any]:
    label = (label or "").strip() or DEFAULT_LABELS.get(platform, "Hesap")
    async with async_session() as session:
        if make_default:
            await session.execute(
                update(PlatformAccount)
                .where(PlatformAccount.platform == platform)
                .values(is_default=False)
            )
        has_any = await session.scalar(
            select(PlatformAccount.id)
            .where(PlatformAccount.platform == platform, PlatformAccount.is_active.is_(True))
            .limit(1)
        )
        acc = PlatformAccount(
            platform=platform,
            label=label,
            status="disconnected",
            is_default=make_default or not has_any,
            is_active=True,
        )
        session.add(acc)
        await session.flush()
        acc.session_name = f"account_{acc.id}"
        if platform == Platform.WHATSAPP.value and not has_any:
            acc.bridge_id = "1"
        else:
            acc.bridge_id = _slug_bridge_id(acc.id)
        acc.credentials_key = f"telegram_{acc.id}" if platform == Platform.TELEGRAM.value else None
        await session.commit()
        await session.refresh(acc)
        return serialize_account(acc)


async def update_account_meta(
    account_id: int,
    *,
    label: Optional[str] = None,
    display_name: Optional[str] = None,
    phone_masked: Optional[str] = None,
    external_id: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    async with async_session() as session:
        acc = await session.get(PlatformAccount, account_id)
        if not acc or not acc.is_active:
            raise ValueError("Hesap bulunamadı")
        if label is not None:
            acc.label = label.strip() or acc.label
        if display_name is not None:
            acc.display_name = display_name
        if phone_masked is not None:
            acc.phone_masked = phone_masked
        if external_id is not None:
            acc.external_id = external_id
        if status is not None:
            acc.status = status
        acc.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(acc)
        return serialize_account(acc)


async def set_default_account(account_id: int) -> dict[str, Any]:
    async with async_session() as session:
        acc = await session.get(PlatformAccount, account_id)
        if not acc or not acc.is_active:
            raise ValueError("Hesap bulunamadı")
        await session.execute(
            update(PlatformAccount)
            .where(PlatformAccount.platform == acc.platform)
            .values(is_default=False)
        )
        acc.is_default = True
        acc.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(acc)
        return serialize_account(acc)


async def delete_account(account_id: int) -> None:
    platform = None
    was_default = False
    async with async_session() as session:
        acc = await session.get(PlatformAccount, account_id)
        if not acc:
            return
        platform = acc.platform
        was_default = acc.is_default
        acc.is_active = False
        acc.status = "disconnected"
        acc.updated_at = datetime.utcnow()
        await session.commit()

    if was_default and platform:
        remaining = await list_accounts(platform)
        if remaining:
            await set_default_account(remaining[0]["id"])


def session_path_for_account(account_id: int) -> str:
    return str(SESSIONS_DIR / f"account_{account_id}")


def legacy_session_exists() -> bool:
    legacy = SESSIONS_DIR / "user_session.session"
    return legacy.exists()


async def get_bridge_id(account_id: int) -> str:
    acc = await get_account(account_id)
    if not acc or not acc.is_active:
        raise ValueError("Geçersiz hesap")
    return acc.bridge_id or _slug_bridge_id(account_id)


async def normalize_whatsapp_bridge_ids() -> None:
    """İlk WhatsApp hesabı köprüde her zaman '1' (legacy uyumu)."""
    async with async_session() as session:
        rows = (
            await session.execute(
                select(PlatformAccount)
                .where(
                    PlatformAccount.platform == Platform.WHATSAPP.value,
                    PlatformAccount.is_active.is_(True),
                )
                .order_by(PlatformAccount.id)
            )
        ).scalars().all()
        if not rows:
            return
        rows[0].bridge_id = "1"
        used = {"1"}
        for acc in rows[1:]:
            bid = acc.bridge_id or _slug_bridge_id(acc.id)
            if bid in used:
                bid = _slug_bridge_id(acc.id)
            acc.bridge_id = bid
            used.add(bid)
        await session.commit()


async def migrate_legacy_whatsapp_files() -> None:
    """Eski whatsapp-auth / whatsapp.db dosyalarını köprü hesabı 1 dizinine taşı."""
    legacy_auth = DATA_DIR / "whatsapp-auth"
    target_auth = DATA_DIR / "whatsapp-auth-1"
    legacy_db = DATA_DIR / "whatsapp.db"
    target_db = DATA_DIR / "whatsapp-1.db"
    try:
        if legacy_auth.is_dir() and not target_auth.exists():
            shutil.copytree(legacy_auth, target_auth)
        if legacy_db.is_file() and not target_db.exists():
            shutil.copy2(legacy_db, target_db)
    except OSError:
        pass


async def migrate_legacy_sessions() -> None:
    """Eski tek hesap oturumunu account_1'e taşı."""
    legacy = SESSIONS_DIR / "user_session.session"
    target = SESSIONS_DIR / "account_1.session"
    if legacy.exists() and not target.exists():
        try:
            os.rename(legacy, target)
        except OSError:
            pass


async def ensure_default_accounts() -> None:
    await migrate_legacy_sessions()
    async with async_session() as session:
        for platform in (Platform.TELEGRAM.value, Platform.WHATSAPP.value):
            exists = await session.scalar(
                select(PlatformAccount.id)
                .where(PlatformAccount.platform == platform, PlatformAccount.is_active.is_(True))
                .limit(1)
            )
            if not exists:
                await create_account(platform, DEFAULT_LABELS[platform], make_default=True)
    await normalize_whatsapp_bridge_ids()


async def account_setup_snapshot() -> dict[str, Any]:
    """First-run state: whether the user still needs to connect a messaging account."""
    from app.telegram_service import telegram_service
    from app.whatsapp_service import whatsapp_service

    accounts = await list_accounts()
    tg_count = wa_count = 0
    tg_connected = wa_connected = False

    for acc in accounts:
        if acc["platform"] == Platform.TELEGRAM.value:
            tg_count += 1
            try:
                st = await telegram_service.get_status(acc["id"])
                if st.get("connected"):
                    tg_connected = True
            except Exception:
                pass
        elif acc["platform"] == Platform.WHATSAPP.value:
            wa_count += 1
            try:
                st = await whatsapp_service.get_status(acc["id"])
                if st.get("connected"):
                    wa_connected = True
            except Exception:
                pass

    any_connected = tg_connected or wa_connected
    return {
        "accounts_total": len(accounts),
        "telegram_accounts": tg_count,
        "whatsapp_accounts": wa_count,
        "telegram_connected": tg_connected,
        "whatsapp_connected": wa_connected,
        "needs_account_setup": len(accounts) == 0 or not any_connected,
        "needs_first_account": len(accounts) == 0,
    }


def account_initials(acc: dict[str, Any]) -> str:
    name = acc.get("display_name") or acc.get("label") or "?"
    parts = re.split(r"\s+", str(name).strip())
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return str(name)[:2].upper()


def mask_account_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    return mask_phone(phone)
