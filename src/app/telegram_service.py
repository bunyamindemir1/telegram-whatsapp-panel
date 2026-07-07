from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from telethon import TelegramClient, events
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.types import Channel, Chat, User

from app.config import MEDIA_DIR, TELEGRAM_PHONE
from app.account_service import (
    list_accounts,
    mask_account_phone,
    session_path_for_account,
    update_account_meta,
)
from app.credentials_store import get_telegram_credentials
from app.media_service import telegram_message_type
from app.message_store import list_conversations, save_message
from app.outbound_guard import ensure_outbound_allowed, outbound_allowed
from app.realtime import realtime_hub
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AuthState:
    phone: str
    api_id: int
    api_hash: str
    client: TelegramClient


class ConnectionState:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class _AccountRuntime:
    client: Optional[TelegramClient] = None
    pending_auth: Optional[AuthState] = None
    connection_state: str = ConnectionState.DISCONNECTED
    handlers_registered: bool = False
    user_info: Optional[dict[str, Any]] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TelegramService:
    def __init__(self) -> None:
        self._runtimes: dict[int, _AccountRuntime] = {}
        self._background_tasks: dict[int, asyncio.Task] = {}
        self._reconnect_attempts: dict[int, int] = {}

    def _get_runtime(self, account_id: int) -> _AccountRuntime:
        if account_id not in self._runtimes:
            self._runtimes[account_id] = _AccountRuntime()
        return self._runtimes[account_id]

    @property
    def connection_state(self) -> str:
        return self._get_runtime(1).connection_state

    def _build_client(self, account_id: int, api_id: int, api_hash: str) -> TelegramClient:
        return TelegramClient(session_path_for_account(account_id), api_id, api_hash)

    async def _resolve_credentials(self, account_id: int) -> tuple[Optional[int], Optional[str], str]:
        creds = await get_telegram_credentials(account_id)
        if creds:
            return creds.api_id, creds.api_hash, creds.phone
        return None, None, TELEGRAM_PHONE

    async def _set_state(self, account_id: int, state: str) -> None:
        runtime = self._get_runtime(account_id)
        if runtime.connection_state != state:
            runtime.connection_state = state
            await realtime_hub.broadcast({
                "type": "connection",
                "platform": "telegram",
                "account_id": account_id,
                "status": state,
                "user": runtime.user_info,
            })

    async def _mark_connected(self, account_id: int, me) -> None:
        runtime = self._get_runtime(account_id)
        runtime.user_info = {
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "",
            "phone": me.phone or "",
        }
        display_name = " ".join(
            p for p in (me.first_name or "", me.last_name or "") if p
        ).strip() or (me.username or "")
        await update_account_meta(
            account_id,
            status=ConnectionState.CONNECTED,
            display_name=display_name,
            phone_masked=mask_account_phone(me.phone),
        )
        await self._set_state(account_id, ConnectionState.CONNECTED)

    def _extract_text(self, message) -> str:
        return message.message or message.text or ""

    async def _ingest_message(
        self, account_id: int, msg, chat_id: str, chat_name: str, chat_type: str, sender_name: str
    ) -> dict:
        ts = msg.date.replace(tzinfo=timezone.utc) if msg.date else datetime.now(timezone.utc)
        ts_naive = ts.replace(tzinfo=None)
        text = self._extract_text(msg)
        media_kwargs: dict = {}

        if msg.media:
            client = await self._ensure_client(account_id)
            dest_dir = MEDIA_DIR / "telegram" / str(account_id)
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                saved_path = await client.download_media(msg, file=str(dest_dir))
                if saved_path:
                    p = Path(saved_path)
                    rel = str(p.relative_to(MEDIA_DIR))
                    mime = "application/octet-stream"
                    if msg.photo:
                        mime = "image/jpeg"
                    elif msg.video:
                        mime = "video/mp4"
                    elif msg.voice:
                        mime = "audio/ogg"
                    elif msg.audio:
                        mime = "audio/mpeg"
                    elif msg.document:
                        mime = getattr(msg.document, "mime_type", None) or "application/octet-stream"
                    media_kwargs = {
                        "message_type": telegram_message_type(msg),
                        "media_path": rel,
                        "media_mime": mime,
                        "media_filename": p.name,
                        "media_size": p.stat().st_size if p.exists() else None,
                    }
            except Exception as exc:
                logger.warning("Telegram media download failed: %s", exc)
        if not text and media_kwargs:
            text = f"[{media_kwargs.get('message_type', 'media')}]"
        elif not text:
            text = "[Medya]"

        return await save_message(
            platform="telegram",
            chat_id=chat_id,
            message_id=str(msg.id),
            text=text,
            from_me=bool(msg.out),
            timestamp=ts_naive,
            sender_name=sender_name,
            chat_name=chat_name,
            chat_type=chat_type,
            account_id=account_id,
            **media_kwargs,
        )

    def _entity_meta(self, entity) -> tuple[str, str]:
        if isinstance(entity, User):
            return "user", entity.username or ""
        if isinstance(entity, Chat):
            return "group", ""
        if isinstance(entity, Channel):
            return "channel" if entity.broadcast else "supergroup", entity.username or ""
        return "unknown", ""

    async def _on_new_message(self, account_id: int, event: events.NewMessage.Event) -> None:
        try:
            msg = event.message
            if not msg or not event.chat_id:
                return
            chat_id = str(event.chat_id)
            sender = await event.get_sender()
            sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or ""
            chat = await event.get_chat()
            chat_name = getattr(chat, "title", None) or getattr(chat, "first_name", None) or chat_id
            chat_type, _ = self._entity_meta(chat)

            saved = await self._ingest_message(account_id, msg, chat_id, chat_name, chat_type, sender_name)
            await realtime_hub.broadcast({"type": "message", "data": saved})
            from app.webhook_service import dispatch_webhook
            await dispatch_webhook(
                "message.received" if not saved.get("from_me") else "message.sent",
                saved,
            )
            if not saved.get("from_me"):
                from app.auto_reply_service import try_auto_reply
                await try_auto_reply(
                    platform="telegram",
                    account_id=account_id,
                    chat_id=chat_id,
                    text=saved.get("text") or "",
                    chat_name=chat_name,
                    chat_type=chat_type,
                )
            await realtime_hub.broadcast({
                "type": "conversation_update",
                "platform": "telegram",
                "account_id": account_id,
                "chat_id": chat_id,
                "chat_name": chat_name,
            })
        except Exception as exc:
            logger.exception("Telegram message handler error (account %s): %s", account_id, exc)

    def _register_handlers(self, client: TelegramClient, account_id: int) -> None:
        runtime = self._get_runtime(account_id)
        if runtime.handlers_registered:
            return

        async def handler(event: events.NewMessage.Event) -> None:
            await self._on_new_message(account_id, event)

        client.add_event_handler(handler, events.NewMessage(incoming=True))
        client.add_event_handler(handler, events.NewMessage(outgoing=True))
        runtime.handlers_registered = True

    async def start_account_background(self, account_id: int) -> None:
        task = self._background_tasks.get(account_id)
        if task and not task.done():
            return
        self._background_tasks[account_id] = asyncio.create_task(
            self._connection_loop(account_id)
        )

    async def start_background(self) -> None:
        accounts = await list_accounts("telegram")
        for acc in accounts:
            await self.start_account_background(acc["id"])

    async def _connection_loop(self, account_id: int) -> None:
        runtime = self._get_runtime(account_id)
        while True:
            try:
                if runtime.pending_auth:
                    await asyncio.sleep(2)
                    continue

                api_id, api_hash, _ = await self._resolve_credentials(account_id)
                if not api_id or not api_hash:
                    await self._set_state(account_id, ConnectionState.DISCONNECTED)
                    await asyncio.sleep(10)
                    continue

                attempts = self._reconnect_attempts.get(account_id, 0)
                await self._set_state(
                    account_id,
                    ConnectionState.RECONNECTING if attempts else ConnectionState.CONNECTING,
                )

                async with runtime.lock:
                    if runtime.client and runtime.client.is_connected():
                        if await runtime.client.is_user_authorized():
                            await self._set_state(account_id, ConnectionState.CONNECTED)
                            await asyncio.sleep(5)
                            continue

                    client = self._build_client(account_id, api_id, api_hash)
                    await client.connect()

                    if not await client.is_user_authorized():
                        await client.disconnect()
                        await self._set_state(account_id, ConnectionState.DISCONNECTED)
                        await asyncio.sleep(15)
                        continue

                    me = await client.get_me()
                    runtime.client = client
                    self._register_handlers(client, account_id)
                    self._reconnect_attempts[account_id] = 0
                    await self._mark_connected(account_id, me)

                await asyncio.sleep(3)
                if runtime.client and not runtime.client.is_connected():
                    raise ConnectionError("Telegram bağlantısı koptu")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Telegram bağlantı döngüsü (account %s): %s", account_id, exc)
                self._reconnect_attempts[account_id] = self._reconnect_attempts.get(account_id, 0) + 1
                await self._set_state(account_id, ConnectionState.RECONNECTING)
                delay = min(60, 2 ** min(self._reconnect_attempts[account_id], 5))
                async with runtime.lock:
                    if runtime.client:
                        try:
                            await runtime.client.disconnect()
                        except Exception:
                            pass
                        runtime.client = None
                await asyncio.sleep(delay)

    async def get_status(self, account_id: int = 1) -> dict[str, Any]:
        runtime = self._get_runtime(account_id)
        api_id, api_hash, default_phone = await self._resolve_credentials(account_id)
        if not api_id or not api_hash:
            return {
                "connected": False,
                "configured": False,
                "user": None,
                "connection_state": runtime.connection_state,
                "default_phone": default_phone,
                "account_id": account_id,
            }

        connected = False
        if runtime.client and runtime.client.is_connected():
            try:
                connected = await runtime.client.is_user_authorized()
            except Exception:
                connected = False

        return {
            "connected": connected,
            "configured": True,
            "user": runtime.user_info if connected else None,
            "connection_state": runtime.connection_state,
            "default_phone": default_phone,
            "account_id": account_id,
        }

    async def _ensure_client(self, account_id: int) -> TelegramClient:
        runtime = self._get_runtime(account_id)

        if runtime.client and runtime.client.is_connected():
            if await runtime.client.is_user_authorized():
                return runtime.client

        async with runtime.lock:
            if (
                runtime.client
                and runtime.client.is_connected()
                and await runtime.client.is_user_authorized()
            ):
                return runtime.client

            api_id, api_hash, _ = await self._resolve_credentials(account_id)
            if not api_id or not api_hash:
                raise RuntimeError("Telegram API bilgileri yapılandırılmamış. Hesap sekmesinden kaydedin.")

            client = self._build_client(account_id, api_id, api_hash)
            await client.connect()

            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError("Telegram hesabı bağlı değil. Önce giriş yapın.")

            runtime.client = client
            self._register_handlers(client, account_id)
            me = await client.get_me()
            await self._mark_connected(account_id, me)
            return client

    async def start_auth(
        self,
        phone: Optional[str] = None,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        account_id: int = 1,
    ) -> dict:
        runtime = self._get_runtime(account_id)
        stored_api_id, stored_api_hash, stored_phone = await self._resolve_credentials(account_id)
        phone = phone or stored_phone
        resolved_api_id = api_id or stored_api_id
        resolved_api_hash = api_hash or stored_api_hash

        if not resolved_api_id or not resolved_api_hash:
            raise ValueError("API ID ve API Hash gerekli")

        async with runtime.lock:
            if runtime.pending_auth:
                await runtime.pending_auth.client.disconnect()
                runtime.pending_auth = None

            if runtime.client:
                try:
                    await runtime.client.disconnect()
                except Exception:
                    pass
                runtime.client = None
                runtime.handlers_registered = False

            client = self._build_client(account_id, resolved_api_id, resolved_api_hash)
            await client.connect()

            if await client.is_user_authorized():
                runtime.client = client
                self._register_handlers(client, account_id)
                me = await client.get_me()
                await self._mark_connected(account_id, me)
                return {"status": "already_authorized", "user": runtime.user_info}

            await client.send_code_request(phone)
            runtime.pending_auth = AuthState(
                phone=phone,
                api_id=resolved_api_id,
                api_hash=resolved_api_hash,
                client=client,
            )
            return {"status": "code_sent", "phone": phone}

    async def verify_code(self, code: str, account_id: int = 1) -> dict:
        runtime = self._get_runtime(account_id)
        if not runtime.pending_auth:
            raise ValueError("Önce telefon numarası ile giriş başlatın")
        auth = runtime.pending_auth
        try:
            await auth.client.sign_in(auth.phone, code)
        except SessionPasswordNeededError:
            return {"status": "password_required"}
        except PhoneCodeInvalidError:
            raise ValueError("Doğrulama kodu hatalı")
        except PhoneCodeExpiredError:
            raise ValueError("Doğrulama kodunun süresi doldu")

        runtime.client = auth.client
        runtime.pending_auth = None
        self._register_handlers(auth.client, account_id)
        me = await auth.client.get_me()
        await self._mark_connected(account_id, me)
        return {"status": "authorized", "user": runtime.user_info}

    async def verify_password(self, password: str, account_id: int = 1) -> dict:
        runtime = self._get_runtime(account_id)
        if not runtime.pending_auth:
            raise ValueError("Önce doğrulama kodunu girin")
        auth = runtime.pending_auth
        try:
            await auth.client.sign_in(password=password)
        except PasswordHashInvalidError:
            raise ValueError("2FA şifresi hatalı")
        runtime.client = auth.client
        runtime.pending_auth = None
        self._register_handlers(auth.client, account_id)
        me = await auth.client.get_me()
        await self._mark_connected(account_id, me)
        return {"status": "authorized", "user": runtime.user_info}

    async def logout(self, account_id: int = 1) -> None:
        runtime = self._get_runtime(account_id)

        task = self._background_tasks.pop(account_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with runtime.lock:
            if runtime.pending_auth:
                await runtime.pending_auth.client.disconnect()
                runtime.pending_auth = None
            if runtime.client:
                await runtime.client.log_out()
                await runtime.client.disconnect()
                runtime.client = None
            runtime.handlers_registered = False
            runtime.user_info = None

            session_file = f"{session_path_for_account(account_id)}.session"
            if os.path.exists(session_file):
                os.remove(session_file)

        self._reconnect_attempts.pop(account_id, None)
        await update_account_meta(account_id, status=ConnectionState.DISCONNECTED)
        await self._set_state(account_id, ConnectionState.DISCONNECTED)

    async def list_chats(self, account_id: int = 1, refresh: bool = False) -> list[dict[str, Any]]:
        try:
            client = await self._ensure_client(account_id)
        except Exception:
            return await list_conversations("telegram", account_id=account_id)

        chats: list[dict[str, Any]] = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            chat_type, username = self._entity_meta(entity)
            chats.append({
                "id": str(dialog.id),
                "name": dialog.name or "İsimsiz",
                "type": chat_type,
                "username": username,
                "unread_count": dialog.unread_count,
                "last_message": self._extract_text(dialog.message) if dialog.message else None,
                "last_timestamp": int(dialog.date.timestamp()) if dialog.date else None,
            })

        if not refresh:
            stored = await list_conversations("telegram", account_id=account_id)
            if stored and not chats:
                return stored

        return chats

    async def sync_chat_history(
        self,
        chat_id: str,
        limit: int = 80,
        account_id: int = 1,
    ) -> int:
        client = await self._ensure_client(account_id)
        entity = await client.get_entity(int(chat_id))
        chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or chat_id
        chat_type, _ = self._entity_meta(entity)
        count = 0
        async for msg in client.iter_messages(entity, limit=limit):
            text = self._extract_text(msg)
            if not text and not msg.media:
                continue
            await self._ingest_message(
                account_id, msg, chat_id, chat_name, chat_type,
                sender_name=getattr(entity, "first_name", None) or getattr(entity, "title", None) or "",
            )
            count += 1
        return count

    async def resolve_phone_chat(self, phone: str, account_id: int = 1) -> dict[str, Any]:
        client = await self._ensure_client(account_id)
        normalized = phone.replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            normalized = "+" + normalized
        entity = await client.get_entity(normalized)
        chat_type, username = self._entity_meta(entity)
        chat_id = str(entity.id)
        name = getattr(entity, "first_name", None) or getattr(entity, "title", None) or normalized
        return {"chat_id": chat_id, "chat_name": name, "chat_type": chat_type, "username": username}

    async def send_message(
        self,
        chat_id: str,
        message: str,
        chat_name: str = "",
        chat_type: str = "unknown",
        account_id: int = 1,
        reply_to_message_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not outbound_allowed():
            ensure_outbound_allowed()

        client = await self._ensure_client(account_id)
        entity = await client.get_entity(int(chat_id))
        if not chat_name:
            chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or chat_id
        if chat_type == "unknown":
            chat_type, _ = self._entity_meta(entity)

        result = await client.send_message(
            entity,
            message,
            reply_to=int(reply_to_message_id) if reply_to_message_id else None,
        )
        ts = result.date.replace(tzinfo=timezone.utc) if result.date else datetime.now(timezone.utc)
        saved = await save_message(
            platform="telegram",
            chat_id=chat_id,
            message_id=str(result.id),
            text=message,
            from_me=True,
            timestamp=ts.replace(tzinfo=None),
            chat_name=chat_name,
            chat_type=chat_type,
            account_id=account_id,
            reply_to_message_id=reply_to_message_id,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        return {"message_id": result.id, "date": saved["timestamp"], "saved": saved}

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        chat_name: str = "",
        chat_type: str = "unknown",
        account_id: int = 1,
        media_meta: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not outbound_allowed():
            ensure_outbound_allowed()

        meta = media_meta or {}
        client = await self._ensure_client(account_id)
        entity = await client.get_entity(int(chat_id))
        if not chat_name:
            chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", None) or chat_id
        if chat_type == "unknown":
            chat_type, _ = self._entity_meta(entity)

        voice_note = meta.get("message_type") == "voice"
        result = await client.send_file(entity, file_path, caption=caption or None, voice_note=voice_note)
        ts = result.date.replace(tzinfo=timezone.utc) if result.date else datetime.now(timezone.utc)
        display = caption or meta.get("media_filename") or f"[{meta.get('message_type', 'media')}]"
        saved = await save_message(
            platform="telegram",
            chat_id=chat_id,
            message_id=str(result.id),
            text=display,
            from_me=True,
            timestamp=ts.replace(tzinfo=None),
            chat_name=chat_name,
            chat_type=chat_type,
            account_id=account_id,
            message_type=meta.get("message_type", "document"),
            media_path=meta.get("media_path"),
            media_mime=meta.get("media_mime"),
            media_filename=meta.get("media_filename"),
            media_size=meta.get("media_size"),
            caption=caption or None,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        return {"message_id": result.id, "date": saved["timestamp"], "saved": saved}

    async def disconnect(self) -> None:
        for account_id, task in list(self._background_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._background_tasks.clear()

        for account_id, runtime in self._runtimes.items():
            if runtime.client and runtime.client.is_connected():
                try:
                    await runtime.client.disconnect()
                except Exception:
                    pass


telegram_service = TelegramService()
