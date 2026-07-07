from datetime import datetime
from typing import Any, Optional

from app.account_service import resolve_account_id
from app.message_store import save_message
from app.models import Platform
from app.outbound_guard import ensure_outbound_allowed, outbound_allowed, simulated_send_result
from app.realtime import realtime_hub
from app.telegram_service import telegram_service
from app.template_engine import build_template_context, render_template
from app.whatsapp_service import whatsapp_service


async def send_platform_message(
    platform: str,
    chat_id: str,
    message: str,
    *,
    chat_name: str = "",
    chat_type: str = "unknown",
    allow_simulate: bool = False,
    account_id: Optional[int] = None,
    reply_to_message_id: Optional[str] = None,
) -> dict[str, Any]:
    if not outbound_allowed():
        if allow_simulate:
            return simulated_send_result(platform, chat_id, message)
        ensure_outbound_allowed()

    aid = await resolve_account_id(platform, account_id)
    ctx = build_template_context(
        chat_name=chat_name or chat_id,
        chat_id=chat_id,
        platform=platform,
    )
    rendered = render_template(message, ctx)

    if platform == Platform.WHATSAPP.value:
        wa_result = await whatsapp_service.send_message(chat_id, rendered, account_id=aid)
        saved = await save_message(
            platform="whatsapp",
            chat_id=chat_id,
            message_id=wa_result.get("message_id", str(datetime.utcnow().timestamp())),
            text=rendered,
            from_me=True,
            timestamp=datetime.utcnow(),
            chat_name=chat_name or chat_id,
            chat_type=chat_type,
            account_id=aid,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        return {"message_id": wa_result.get("message_id"), "saved": saved}

    return await telegram_service.send_message(
        chat_id,
        rendered,
        chat_name,
        chat_type,
        account_id=aid,
        reply_to_message_id=reply_to_message_id,
    )


async def list_platform_chats(
    platform: str,
    *,
    refresh: bool = False,
    account_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    aid = await resolve_account_id(platform, account_id)
    if platform == Platform.WHATSAPP.value:
        return await whatsapp_service.list_chats(aid)
    return await telegram_service.list_chats(account_id=aid, refresh=refresh)


async def send_platform_media(
    platform: str,
    chat_id: str,
    file_path: str,
    *,
    caption: str = "",
    chat_name: str = "",
    chat_type: str = "unknown",
    account_id: Optional[int] = None,
    media_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not outbound_allowed():
        ensure_outbound_allowed()

    aid = await resolve_account_id(platform, account_id)
    meta = media_meta or {}

    if platform == Platform.WHATSAPP.value:
        wa_result = await whatsapp_service.send_media(
            chat_id,
            meta.get("media_path", ""),
            caption,
            meta.get("media_mime", "application/octet-stream"),
            account_id=aid,
        )
        display = caption or meta.get("media_filename") or f"[{meta.get('message_type', 'media')}]"
        saved = await save_message(
            platform="whatsapp",
            chat_id=chat_id,
            message_id=wa_result.get("message_id", str(datetime.utcnow().timestamp())),
            text=display,
            from_me=True,
            timestamp=datetime.utcnow(),
            chat_name=chat_name or chat_id,
            chat_type=chat_type,
            account_id=aid,
            message_type=meta.get("message_type", "document"),
            media_path=meta.get("media_path"),
            media_mime=meta.get("media_mime"),
            media_filename=meta.get("media_filename"),
            media_size=meta.get("media_size"),
            caption=caption or None,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        return {"message_id": wa_result.get("message_id"), "saved": saved}

    return await telegram_service.send_media(
        chat_id,
        file_path,
        caption=caption,
        chat_name=chat_name,
        chat_type=chat_type,
        account_id=aid,
        media_meta=meta,
    )
