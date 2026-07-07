from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.bridge_manager import start_whatsapp_bridge, stop_whatsapp_bridge
from app import error_codes as E
from app.config import (
    ALLOW_OUTBOUND_MESSAGES,
    BASE_DIR,
    BRIDGE_SECRET,
    ENABLE_OPENAPI,
    ENV,
    SESSION_SECRET,
    TELEGRAM_PHONE,
    TELEGRAM_TEST_PHONE,
    TIMEZONE,
)
from app.secret_policy import verify_bridge_token
from app.i18n import SUPPORTED_LOCALES, list_locales, load_messages, locale_meta, resolve_locale
from app.outbound_guard import OutboundBlockedError
import app.panel_auth as panel_auth
from app.security import SecurityHeadersMiddleware, get_client_ip, login_rate_limiter, mask_phone, sanitize_user_info
from app.account_service import (
    account_setup_snapshot,
    create_account,
    delete_account,
    ensure_default_accounts,
    list_accounts,
    resolve_account_id,
    resolve_whatsapp_panel_account,
    set_default_account,
    update_account_meta,
)
from app.credentials_store import (
    get_telegram_credentials_public,
    migrate_legacy_credentials_to_account,
    save_telegram_credentials,
    seed_telegram_credentials_if_missing,
)
from app.database import async_session, init_db
from app.message_store import (
    count_stored_messages,
    get_messages,
    list_conversations,
    mark_read,
    save_message,
    save_messages_batch,
    save_messages_bulk,
    search_messages,
    sync_conversations_from_chats,
    update_conversation_label,
)
from app.realtime import realtime_hub
from app.models import JobStatus, MessageTemplate, Platform, RepeatType, ScheduledMessage
from app.scheduler_service import (
    cancel_job,
    get_scheduler_status,
    load_pending_jobs,
    prepare_random_daily_job,
    retry_job,
    schedule_message,
    scheduler,
    send_now,
)
from app.messaging import list_platform_chats, send_platform_media, send_platform_message
from app.media_service import resolve_media_path, save_upload
from app.telegram_service import telegram_service
from app.utils.datetime_utils import format_istanbul, from_client_datetime, utc_now
from app.whatsapp_service import whatsapp_service
from app.api_v1 import router as api_v1_router

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class CreateAccountRequest(BaseModel):
    platform: str
    label: str = Field(min_length=1, max_length=120)


class UpdateAccountRequest(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=120)


class AuthStartRequest(BaseModel):
    phone: Optional[str] = None
    api_id: Optional[int] = None
    api_hash: Optional[str] = None


class SendMessageRequest(BaseModel):
    platform: str
    chat_id: str
    message: str = Field(min_length=1, max_length=4096)
    chat_name: str = ""
    chat_type: str = "unknown"


class AuthCodeRequest(BaseModel):
    code: str


class AuthPasswordRequest(BaseModel):
    password: str


class ScheduleRequest(BaseModel):
    platform: str = Platform.TELEGRAM.value
    account_id: Optional[int] = None
    chat_id: str
    chat_name: str
    chat_type: str = "unknown"
    message_text: str = Field(min_length=1, max_length=4096)
    scheduled_at: Optional[datetime] = None
    repeat_type: str = RepeatType.NONE.value
    repeat_interval_minutes: Optional[int] = None
    window_start_time: Optional[str] = None
    window_end_time: Optional[str] = None


class ScheduleUpdateRequest(BaseModel):
    message_text: Optional[str] = Field(None, min_length=1, max_length=4096)
    scheduled_at: Optional[datetime] = None
    repeat_type: Optional[str] = None
    repeat_interval_minutes: Optional[int] = None
    window_start_time: Optional[str] = None
    window_end_time: Optional[str] = None


class TemplateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message_text: str = Field(min_length=1, max_length=4096)


class PanelLoginRequest(BaseModel):
    username: Optional[str] = None
    password: str = Field(min_length=1)


class PanelSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class ConversationLabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class TelegramCredentialsRequest(BaseModel):
    api_id: int = Field(gt=0)
    api_hash: str = Field(min_length=16, max_length=64)
    app_name: str = Field(default="mesaj", max_length=64)
    short_name: str = Field(default="mesaj", max_length=32)
    phone: Optional[str] = None


class InternalMessageData(BaseModel):
    chat_id: str
    message_id: str
    text: str = ""
    from_me: bool = False
    timestamp: Optional[float] = None
    sender_name: Optional[str] = None
    chat_name: Optional[str] = None
    chat_type: str = "private"
    message_type: Optional[str] = None
    media_path: Optional[str] = None
    media_mime: Optional[str] = None
    media_filename: Optional[str] = None
    media_size: Optional[int] = None
    caption: Optional[str] = None


class InternalEventRequest(BaseModel):
    type: str
    platform: Optional[str] = None
    account_id: Optional[int] = None
    status: Optional[str] = None
    user: Optional[dict] = None
    data: Optional[InternalMessageData] = None


class WhatsAppSyncChat(BaseModel):
    jid: str
    name: Optional[str] = None
    type: str = "private"
    last_message: Optional[str] = None
    last_timestamp: Optional[int] = None
    unread_count: int = 0


class WhatsAppSyncMessage(BaseModel):
    id: str
    jid: str
    from_me: bool = False
    text: str = ""
    timestamp: int = 0
    push_name: Optional[str] = None
    message_type: Optional[str] = None
    media_path: Optional[str] = None
    media_mime: Optional[str] = None
    media_filename: Optional[str] = None
    media_size: Optional[int] = None
    caption: Optional[str] = None


class WhatsAppSyncRequest(BaseModel):
    account_id: Optional[int] = None
    chats: list[WhatsAppSyncChat] = []
    messages: list[WhatsAppSyncMessage] = []
    offset: int = 0
    total_messages: int = 0
    has_more: bool = False


def _check_bridge_auth(request: Request) -> None:
    token = request.headers.get("X-Bridge-Token", "")
    if not verify_bridge_token(token, BRIDGE_SECRET):
        raise HTTPException(status_code=403, detail=E.BRIDGE_INVALID_SECRET)


def _validate_platform(platform: str) -> str:
    allowed = {Platform.TELEGRAM.value, Platform.WHATSAPP.value}
    if platform not in allowed:
        raise HTTPException(status_code=400, detail=E.INVALID_PLATFORM)
    return platform


async def _resolve_telegram_account(account_id: Optional[int] = None) -> int:
    try:
        return await resolve_account_id(Platform.TELEGRAM.value, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _resolve_whatsapp_account(account_id: Optional[int] = None) -> int:
    try:
        return await resolve_account_id(Platform.WHATSAPP.value, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _resolve_platform_account(platform: str, account_id: Optional[int] = None) -> int:
    try:
        return await resolve_account_id(platform, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _check_panel_auth(request: Request) -> None:
    await panel_auth.check_panel_auth(request)


def _serialize_job(j: ScheduledMessage) -> dict:
    return {
        "id": j.id,
        "platform": j.platform or Platform.TELEGRAM.value,
        "account_id": j.account_id,
        "chat_id": j.chat_id,
        "chat_name": j.chat_name,
        "chat_type": j.chat_type,
        "message_text": j.message_text,
        "scheduled_at": j.scheduled_at.isoformat() + "Z",
        "scheduled_at_tr": format_istanbul(
            j.scheduled_at, with_seconds=j.repeat_type == RepeatType.RANDOM_DAILY.value
        ),
        "next_run_at": (j.next_run_at.isoformat() + "Z") if j.next_run_at else None,
        "next_run_at_tr": (
            format_istanbul(j.next_run_at, with_seconds=j.repeat_type == RepeatType.RANDOM_DAILY.value)
            if j.next_run_at else None
        ),
        "repeat_type": j.repeat_type,
        "repeat_interval_minutes": j.repeat_interval_minutes,
        "window_start_time": j.window_start_time,
        "window_end_time": j.window_end_time,
        "window_label": (
            f"{j.window_start_time}–{j.window_end_time} rastgele"
            if j.repeat_type == RepeatType.RANDOM_DAILY.value and j.window_start_time and j.window_end_time
            else None
        ),
        "status": j.status,
        "is_active": j.is_active,
        "send_count": j.send_count or 0,
        "last_run_at": (j.last_run_at.isoformat() + "Z") if j.last_run_at else None,
        "error_message": j.error_message,
        "created_at": j.created_at.isoformat() + "Z",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    panel_auth.validate_production_settings()
    await init_db()
    await migrate_legacy_credentials_to_account(1)
    await seed_telegram_credentials_if_missing()
    await panel_auth.ensure_admin_from_env()
    await start_whatsapp_bridge()
    await telegram_service.start_background()
    if not scheduler.running:
        scheduler.start()
    await load_pending_jobs()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await telegram_service.disconnect()
    stop_whatsapp_bridge()


app = FastAPI(
    title="Message Panel — Telegram & WhatsApp",
    description="Self-hosted messaging panel with REST API v1. Docs: /docs",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_OPENAPI else None,
    redoc_url="/redoc" if ENABLE_OPENAPI else None,
    openapi_url="/openapi.json" if ENABLE_OPENAPI else None,
)
app.include_router(api_v1_router, prefix="/api/v1")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="mesaj_panel",
    max_age=panel_auth.SESSION_MAX_AGE,
    same_site="lax",
    https_only=ENV == "production",
)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/api/health")
async def health():
    wa_ok = await whatsapp_service.health()
    payload = {
        "ok": True,
        "outbound_enabled": ALLOW_OUTBOUND_MESSAGES,
        "dry_run": not ALLOW_OUTBOUND_MESSAGES,
        "whatsapp_bridge": wa_ok,
    }
    if ENV != "production":
        payload["env"] = ENV
    return payload


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    static_dir = BASE_DIR / "static"
    js_mtime = max(
        int((static_dir / "js" / "app.js").stat().st_mtime),
        int((static_dir / "js" / "icons.js").stat().st_mtime),
        int((static_dir / "js" / "i18n.js").stat().st_mtime),
    )
    css_mtime = int((static_dir / "css" / "style.css").stat().st_mtime)
    locale = resolve_locale(
        cookie_locale=request.cookies.get("mesaj_locale"),
        accept_language=request.headers.get("accept-language"),
        query_locale=request.query_params.get("lang"),
    )
    i18n = load_messages(locale)
    fallback = load_messages("en") if locale != "en" else {}
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "js_v": js_mtime,
            "css_v": css_mtime,
            "locale": locale,
            "locale_rtl": SUPPORTED_LOCALES.get(locale, {}).get("rtl", False),
            "i18n_json": i18n,
            "i18n_fallback_json": fallback,
            "locales_json": list_locales(),
        },
    )


@app.get("/api/i18n/locales")
async def api_i18n_locales():
    return {"locales": list_locales(), "default": "en"}


@app.get("/api/i18n/{locale_code}")
async def api_i18n_messages(locale_code: str):
    if locale_code not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=404, detail="Locale not supported")
    return {
        "locale": locale_code,
        "meta": locale_meta(locale_code),
        "messages": load_messages(locale_code),
    }


@app.post("/api/panel/setup")
async def panel_setup(request: Request, body: PanelSetupRequest):
    if await panel_auth.count_users() > 0:
        raise HTTPException(status_code=400, detail=E.SETUP_ALREADY_DONE)
    ip = get_client_ip(request)
    login_rate_limiter.check_allowed(ip)
    try:
        user = await panel_auth.create_user(body.username, body.password, is_admin=True)
    except ValueError as exc:
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    login_rate_limiter.record_success(ip)
    panel_auth.set_session_user(request, user)
    return {"ok": True, "username": user.username}


@app.post("/api/panel/login")
async def panel_login(request: Request, body: PanelLoginRequest):
    users = await panel_auth.count_users()
    if users > 0:
        user = await panel_auth.authenticate(request, body.username, body.password)
        panel_auth.set_session_user(request, user)
        return {"ok": True, "username": user.username}

    from app.config import PANEL_PASSWORD
    ip = get_client_ip(request)
    login_rate_limiter.check_allowed(ip)
    if PANEL_PASSWORD and body.password == PANEL_PASSWORD:
        login_rate_limiter.record_success(ip)
        panel_auth.set_legacy_session(request)
        return {"ok": True, "username": "admin", "legacy": True}

    login_rate_limiter.record_failure(ip)
    if await panel_auth.setup_required():
        raise HTTPException(status_code=400, detail=E.PANEL_SETUP_REQUIRED)

    raise HTTPException(status_code=401, detail=E.AUTH_INVALID)


@app.post("/api/panel/logout")
async def panel_logout(request: Request):
    panel_auth.clear_session(request)
    return {"ok": True}


@app.get("/api/panel/status")
async def panel_status(request: Request):
    users = await panel_auth.count_users()
    from app.config import PANEL_PASSWORD
    authenticated = panel_auth.is_session_authenticated(dict(request.session))
    protected = panel_auth.auth_required() or users > 0 or bool(PANEL_PASSWORD)
    setup_needed = await panel_auth.setup_required()
    setup = await account_setup_snapshot()
    return {
        "authenticated": authenticated,
        "protected": protected,
        "setup_required": setup_needed,
        "username": request.session.get("username"),
        "outbound_enabled": ALLOW_OUTBOUND_MESSAGES,
        "dry_run": not ALLOW_OUTBOUND_MESSAGES,
        "env": ENV,
        **setup,
    }


@app.get("/api/stats")
async def get_stats(request: Request):
    await _check_panel_auth(request)
    async with async_session() as session:
        total = await session.scalar(select(func.count()).select_from(ScheduledMessage))
        pending = await session.scalar(
            select(func.count()).select_from(ScheduledMessage).where(
                ScheduledMessage.is_active.is_(True),
                ScheduledMessage.status == JobStatus.PENDING.value,
            )
        )
        sent = await session.scalar(
            select(func.count()).select_from(ScheduledMessage).where(
                ScheduledMessage.status == JobStatus.SENT.value
            )
        )
        failed = await session.scalar(
            select(func.count()).select_from(ScheduledMessage).where(
                ScheduledMessage.status == JobStatus.FAILED.value
            )
        )

    sched = get_scheduler_status()
    tg_auth = await telegram_service.get_status()
    wa_auth = await whatsapp_service.get_status()

    return {
        "total": total or 0,
        "pending": pending or 0,
        "sent": sent or 0,
        "failed": failed or 0,
        "scheduler": sched,
        "timezone": TIMEZONE,
        "telegram_connected": tg_auth.get("connected", False),
        "telegram_connection_state": tg_auth.get("connection_state"),
        "whatsapp_connected": wa_auth.get("connected", False),
        "whatsapp_bridge": wa_auth.get("bridge_running", False),
    }


@app.get("/api/accounts")
async def api_list_accounts(
    request: Request,
    platform: Optional[str] = Query(None),
):
    await _check_panel_auth(request)
    if platform:
        _validate_platform(platform)
    return await list_accounts(platform)


@app.post("/api/accounts")
async def api_create_account(request: Request, body: CreateAccountRequest):
    await _check_panel_auth(request)
    platform = _validate_platform(body.platform)
    try:
        acc = await create_account(platform, body.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if platform == Platform.TELEGRAM.value:
        await telegram_service.start_account_background(acc["id"])
    return acc


@app.patch("/api/accounts/{account_id}")
async def api_update_account(request: Request, account_id: int, body: UpdateAccountRequest):
    await _check_panel_auth(request)
    try:
        return await update_account_meta(account_id, label=body.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/accounts/{account_id}/default")
async def api_set_default_account(request: Request, account_id: int):
    await _check_panel_auth(request)
    try:
        return await set_default_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/accounts/{account_id}")
async def api_delete_account(request: Request, account_id: int):
    await _check_panel_auth(request)
    accounts = await list_accounts()
    acc = next((a for a in accounts if a["id"] == account_id), None)
    if not acc:
        raise HTTPException(status_code=404, detail=E.ACCOUNT_NOT_FOUND)
    if acc["platform"] == Platform.TELEGRAM.value:
        await telegram_service.logout(account_id)
    elif acc["platform"] == Platform.WHATSAPP.value:
        await whatsapp_service.logout(account_id)
    await delete_account(account_id)
    return {"ok": True}


@app.get("/api/accounts/{account_id}/status")
async def api_account_status(request: Request, account_id: int):
    await _check_panel_auth(request)
    accounts = await list_accounts()
    acc = next((a for a in accounts if a["id"] == account_id), None)
    if not acc:
        raise HTTPException(status_code=404, detail=E.ACCOUNT_NOT_FOUND)
    if acc["platform"] == Platform.TELEGRAM.value:
        status = await telegram_service.get_status(account_id)
    else:
        status = await whatsapp_service.get_status(account_id)
    if status.get("user"):
        status = {**status, "user": sanitize_user_info(status["user"])}
    if status.get("default_phone"):
        status["default_phone_masked"] = mask_phone(status["default_phone"])
        del status["default_phone"]
    return status


@app.get("/api/auth/status")
async def auth_status(request: Request, account_id: Optional[int] = Query(None)):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    status = await telegram_service.get_status(aid)
    if status.get("user"):
        status = {**status, "user": sanitize_user_info(status["user"])}
    if status.get("default_phone"):
        status["default_phone_masked"] = mask_phone(status["default_phone"])
        del status["default_phone"]
    return status


@app.post("/api/auth/start")
async def auth_start(
    request: Request,
    body: AuthStartRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    try:
        result = await telegram_service.start_auth(
            body.phone, body.api_id, body.api_hash, account_id=aid
        )
        if result.get("phone"):
            result["phone_masked"] = mask_phone(result.pop("phone"))
        if result.get("user", {}).get("phone"):
            result["user"] = sanitize_user_info(result["user"])
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/verify-code")
async def auth_verify_code(
    request: Request,
    body: AuthCodeRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    try:
        return await telegram_service.verify_code(body.code, account_id=aid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/verify-password")
async def auth_verify_password(
    request: Request,
    body: AuthPasswordRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    try:
        return await telegram_service.verify_password(body.password, account_id=aid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/logout")
async def auth_logout(request: Request, account_id: Optional[int] = Query(None)):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    await telegram_service.logout(aid)
    return {"ok": True}


@app.get("/api/config")
async def get_config(request: Request):
    await _check_panel_auth(request)
    creds = await get_telegram_credentials_public()
    return {
        "timezone": TIMEZONE,
        "telegram_phone_masked": creds.get("phone_masked") or mask_phone(TELEGRAM_PHONE),
        "telegram_credentials": creds,
        "ws_path": "/ws",
        "outbound_enabled": ALLOW_OUTBOUND_MESSAGES,
        "dry_run": not ALLOW_OUTBOUND_MESSAGES,
    }


@app.get("/api/credentials/telegram")
async def get_telegram_credentials_api(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    return await get_telegram_credentials_public(aid)


@app.put("/api/credentials/telegram")
async def update_telegram_credentials_api(
    request: Request,
    body: TelegramCredentialsRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_telegram_account(account_id)
    try:
        return await save_telegram_credentials(
            body.api_id,
            body.api_hash.strip(),
            app_name=body.app_name.strip(),
            short_name=body.short_name.strip(),
            phone=(body.phone or TELEGRAM_PHONE).strip(),
            account_id=aid,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not await panel_auth.ws_authenticated(websocket):
        await websocket.close(code=4401, reason=E.AUTH_LOGIN_REQUIRED)
        return
    await realtime_hub.connect(websocket)
    try:
        for acc in await list_accounts():
            if acc["platform"] == Platform.TELEGRAM.value:
                tg = await telegram_service.get_status(acc["id"])
                await websocket.send_json({
                    "type": "connection",
                    "platform": "telegram",
                    "account_id": acc["id"],
                    "status": tg.get("connection_state", "disconnected"),
                    "user": tg.get("user"),
                })
            elif acc["platform"] == Platform.WHATSAPP.value:
                wa = await whatsapp_service.get_status(acc["id"])
                wa_status = "connected" if wa.get("connected") else wa.get("status", "disconnected")
                await websocket.send_json({
                    "type": "connection",
                    "platform": "whatsapp",
                    "account_id": acc["id"],
                    "status": wa_status,
                    "user": wa.get("user"),
                })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_hub.disconnect(websocket)


@app.get("/api/conversations")
async def api_conversations(
    request: Request,
    platform: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    refresh: bool = Query(False),
):
    await _check_panel_auth(request)
    if platform:
        _validate_platform(platform)

    stored = await list_conversations(platform, account_id=account_id)

    if platform == Platform.WHATSAPP.value:
        aid = await _resolve_whatsapp_account(account_id)
        live: list[dict] = []
        try:
            live = await whatsapp_service.list_chats(aid)
        except Exception:
            pass
        if refresh and live:
            try:
                await whatsapp_service.trigger_panel_sync(aid)
            except Exception:
                pass
            stored = await list_conversations(platform, account_id=aid)
        if stored:
            return stored
        return live

    if platform == Platform.TELEGRAM.value:
        try:
            aid = await _resolve_telegram_account(account_id)
            live = await telegram_service.list_chats(account_id=aid, refresh=refresh)
            if live:
                return live
        except Exception:
            pass

    return stored


@app.patch("/api/conversations/{platform}/{chat_id}/label")
async def api_rename_conversation(
    request: Request,
    platform: str,
    chat_id: str,
    body: ConversationLabelRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    _validate_platform(platform)
    try:
        aid = await _resolve_platform_account(platform, account_id)
        return await update_conversation_label(platform, chat_id, body.label, account_id=aid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/messages/{platform}/{chat_id}")
async def api_get_messages(
    request: Request,
    platform: str,
    chat_id: str,
    limit: int = Query(80, le=200),
    before_id: Optional[int] = Query(None),
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    if platform == Platform.WHATSAPP.value and not before_id:
        aid = await _resolve_whatsapp_account(account_id)
        try:
            raw = await whatsapp_service.get_messages(chat_id, limit, account_id=aid)
            chat_name = chat_id.split("@")[0]
            chat_type = "private"
            for c in await whatsapp_service.list_chats(aid):
                if c["id"] == chat_id:
                    chat_name = c.get("name") or chat_name
                    chat_type = c.get("type", "private")
                    break
            batch = []
            from datetime import datetime as dt
            for m in raw:
                ts_val = m.get("timestamp") or 0
                batch.append({
                    "platform": "whatsapp",
                    "account_id": aid,
                    "chat_id": chat_id,
                    "message_id": m["id"],
                    "text": m.get("text") or "",
                    "from_me": m.get("from_me", False),
                    "timestamp": dt.utcfromtimestamp(ts_val) if ts_val else dt.utcnow(),
                    "sender_name": m.get("push_name"),
                    "chat_name": chat_name,
                    "chat_type": chat_type,
                })
            if batch:
                await save_messages_batch(batch)
            await whatsapp_service.mark_read(chat_id, account_id=aid)
        except Exception:
            pass

    msgs = await get_messages(platform, chat_id, limit, before_id=before_id, account_id=account_id)
    if not msgs and platform == Platform.TELEGRAM.value:
        try:
            aid = await _resolve_telegram_account(account_id)
            await telegram_service.sync_chat_history(chat_id, limit, account_id=aid)
            msgs = await get_messages(platform, chat_id, limit, before_id=before_id, account_id=aid)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await mark_read(platform, chat_id, account_id=account_id)
    return msgs


@app.post("/api/messages/sync/{platform}/{chat_id}")
async def api_sync_messages(
    request: Request,
    platform: str,
    chat_id: str,
    limit: int = Query(200),
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    _validate_platform(platform)
    if platform == Platform.TELEGRAM.value:
        aid = await _resolve_telegram_account(account_id)
        count = await telegram_service.sync_chat_history(chat_id, limit, account_id=aid)
        return {"synced": count}
    if platform == Platform.WHATSAPP.value:
        aid = await _resolve_whatsapp_account(account_id)
        raw = await whatsapp_service.get_messages(chat_id, limit, account_id=aid)
        chat_name = chat_id.split("@")[0]
        batch = []
        from datetime import datetime as dt
        for m in raw:
            ts_val = m.get("timestamp") or 0
            batch.append({
                "platform": "whatsapp",
                "account_id": aid,
                "chat_id": chat_id,
                "message_id": m["id"],
                "text": m.get("text") or "",
                "from_me": m.get("from_me", False),
                "timestamp": dt.utcfromtimestamp(ts_val) if ts_val else dt.utcnow(),
                "sender_name": m.get("push_name"),
                "chat_name": chat_name,
                "chat_type": "private",
            })
        count = await save_messages_batch(batch) if batch else 0
        return {"synced": count}
    raise HTTPException(status_code=400, detail=E.UNSUPPORTED_PLATFORM)


@app.post("/api/messages/sync-all/{platform}")
async def api_sync_all_messages(
    request: Request,
    platform: str,
    offset: int = Query(0, ge=0),
    chunk_size: int = Query(3000, ge=100, le=50000),
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    if platform != Platform.WHATSAPP.value:
        raise HTTPException(status_code=400, detail=E.SYNC_WHATSAPP_ONLY)
    aid = await _resolve_whatsapp_account(account_id)
    try:
        data = await whatsapp_service.export_all(aid, offset=offset, limit=chunk_size)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if offset == 0 and data.get("chats"):
        await sync_conversations_from_chats(data["chats"], platform, aid)

    chat_map = {c.get("jid") or c.get("id"): c for c in data.get("chats", [])}
    batch = []
    from datetime import datetime as dt
    for m in data.get("messages", []):
        jid = m.get("jid")
        c = chat_map.get(jid, {})
        ts_val = m.get("timestamp") or 0
        batch.append({
            "platform": "whatsapp",
            "account_id": aid,
            "chat_id": jid,
            "message_id": m.get("id"),
            "text": m.get("text") or "",
            "from_me": bool(m.get("from_me")),
            "timestamp": dt.utcfromtimestamp(ts_val) if ts_val else dt.utcnow(),
            "sender_name": m.get("push_name"),
            "chat_name": c.get("name") if isinstance(c, dict) else None,
            "chat_type": c.get("type", "private") if isinstance(c, dict) else "private",
        })
    synced = await save_messages_bulk(batch) if batch else 0
    total_bridge = data.get("total_messages", 0)
    next_offset = offset + len(data.get("messages", []))
    stored_total = await count_stored_messages(platform, aid)
    return {
        "synced": synced,
        "offset": offset,
        "next_offset": next_offset,
        "total_messages": total_bridge,
        "stored_messages": stored_total,
        "has_more": data.get("has_more", next_offset < total_bridge),
        "progress_pct": (
            min(100, int(next_offset / total_bridge * 100)) if total_bridge else 100
        ),
        "chats": len(data.get("chats", [])) if offset == 0 else 0,
    }


@app.get("/api/messages/search")
async def api_search_messages(
    request: Request,
    q: str = Query(min_length=1),
    platform: Optional[str] = None,
    account_id: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
):
    await _check_panel_auth(request)
    if platform:
        _validate_platform(platform)
    return await search_messages(q, platform, limit, account_id=account_id)


@app.post("/api/messages/send")
async def api_send_message(
    request: Request,
    body: SendMessageRequest,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    _validate_platform(body.platform)
    try:
        if body.platform == Platform.TELEGRAM.value:
            aid = await _resolve_telegram_account(account_id)
            result = await telegram_service.send_message(
                body.chat_id, body.message, body.chat_name, body.chat_type, account_id=aid
            )
        else:
            aid = await _resolve_whatsapp_account(account_id)
            wa_result = await whatsapp_service.send_message(body.chat_id, body.message, account_id=aid)
            from datetime import datetime as dt
            saved = await save_message(
                platform="whatsapp",
                chat_id=body.chat_id,
                message_id=wa_result.get("message_id", str(dt.utcnow().timestamp())),
                text=body.message,
                from_me=True,
                timestamp=dt.utcnow(),
                chat_name=body.chat_name or body.chat_id,
                chat_type=body.chat_type,
                account_id=aid,
            )
            await realtime_hub.broadcast({"type": "message", "data": saved})
            result = {"message_id": wa_result.get("message_id"), "saved": saved}
        return {"ok": True, **result}
    except OutboundBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/media/{media_path:path}")
async def panel_serve_media(request: Request, media_path: str):
    await _check_panel_auth(request)
    path = resolve_media_path(media_path)
    return FileResponse(path, filename=path.name)


@app.post("/api/messages/send-media")
async def panel_send_media(
    request: Request,
    platform: str = Query(...),
    account_id: int = Query(...),
    chat_id: str = Query(...),
    caption: str = Query(""),
    chat_name: str = Query(""),
    chat_type: str = Query("unknown"),
    file: UploadFile = File(...),
):
    await _check_panel_auth(request)
    _validate_platform(platform)
    try:
        meta = await save_upload(file, platform, account_id)
        result = await send_platform_media(
            platform,
            chat_id,
            meta["absolute_path"],
            caption=caption,
            chat_name=chat_name,
            chat_type=chat_type,
            account_id=account_id,
            media_meta=meta,
        )
        return {"ok": True, "result": result}
    except OutboundBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/internal/event")
async def internal_event(request: Request, body: InternalEventRequest):
    """WhatsApp köprüsünden gelen anlık olaylar."""
    _check_bridge_auth(request)

    if body.type == "message":
        if not body.data:
            raise HTTPException(status_code=422, detail="message event requires data")
        data = body.data
        panel_account_id = await resolve_whatsapp_panel_account(body.account_id or "1")
        from datetime import datetime as dt
        timestamp = dt.utcfromtimestamp(data.timestamp) if data.timestamp else dt.utcnow()
        saved = await save_message(
            platform="whatsapp",
            chat_id=data.chat_id,
            message_id=str(data.message_id),
            text=data.text,
            from_me=data.from_me,
            timestamp=timestamp,
            sender_name=data.sender_name,
            chat_name=data.chat_name or data.chat_id,
            chat_type=data.chat_type,
            account_id=panel_account_id,
            message_type=data.message_type or "text",
            media_path=data.media_path,
            media_mime=data.media_mime,
            media_filename=data.media_filename,
            media_size=data.media_size,
            caption=data.caption,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        from app.webhook_service import dispatch_webhook
        await dispatch_webhook(
            "message.received" if not saved.get("from_me") else "message.sent",
            saved,
        )
        await realtime_hub.broadcast({
            "type": "conversation_update",
            "platform": "whatsapp",
            "account_id": panel_account_id,
            "chat_id": data.chat_id,
        })
    elif body.type == "connection":
        payload = body.model_dump(exclude_none=True)
        if body.platform == Platform.WHATSAPP.value:
            panel_account_id = await resolve_whatsapp_panel_account(body.account_id or "1")
            payload["account_id"] = panel_account_id
        await realtime_hub.broadcast(payload)
        if body.platform == "whatsapp" and body.status == "connected":
            try:
                panel_account_id = await resolve_whatsapp_panel_account(body.account_id or "1")
                await whatsapp_service.trigger_panel_sync(panel_account_id)
            except Exception:
                pass
    return {"ok": True}


@app.post("/api/internal/sync-whatsapp")
async def internal_sync_whatsapp(request: Request, body: WhatsAppSyncRequest):
    """WhatsApp köprüsünden toplu mesaj içe aktarımı."""
    _check_bridge_auth(request)
    panel_account_id = await resolve_whatsapp_panel_account(body.account_id or "1")
    if body.chats and (body.offset or 0) == 0:
        await sync_conversations_from_chats(
            [{"jid": c.jid, "name": c.name, "type": c.type, "last_message": c.last_message,
              "last_timestamp": c.last_timestamp, "unread_count": 0} for c in body.chats],
            Platform.WHATSAPP.value,
            panel_account_id,
        )
    chat_map = {c.jid: c for c in body.chats}
    batch = []
    from datetime import datetime as dt
    for m in body.messages:
        c = chat_map.get(m.jid)
        ts_val = m.timestamp or 0
        batch.append({
            "platform": "whatsapp",
            "account_id": panel_account_id,
            "chat_id": m.jid,
            "message_id": m.id,
            "text": m.text or "",
            "from_me": m.from_me,
            "timestamp": dt.utcfromtimestamp(ts_val) if ts_val else dt.utcnow(),
            "sender_name": m.push_name,
            "chat_name": c.name if c else None,
            "chat_type": c.type if c else "private",
            "message_type": m.message_type,
            "media_path": m.media_path,
            "media_mime": m.media_mime,
            "media_filename": m.media_filename,
            "media_size": m.media_size,
            "caption": m.caption,
        })
    synced = await save_messages_bulk(batch) if batch else 0
    return {"ok": True, "synced": synced}


@app.post("/api/test/send-naber")
async def test_send_naber(request: Request):
    if ENV == "production":
        raise HTTPException(status_code=404, detail="Not found")
    await _check_panel_auth(request)
    if not TELEGRAM_TEST_PHONE:
        raise HTTPException(status_code=400, detail=E.TEST_PHONE_NOT_SET)
    if not ALLOW_OUTBOUND_MESSAGES:
        raise HTTPException(
            status_code=403,
            detail=E.OUTBOUND_TEST_MODE,
        )
    try:
        target = await telegram_service.resolve_phone_chat(TELEGRAM_TEST_PHONE)
        result = await telegram_service.send_message(
            target["chat_id"],
            "naber",
            target["chat_name"],
            target["chat_type"],
        )
        return {"ok": True, "target": target, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/chats")
async def list_chats(
    request: Request,
    platform: str = Query(Platform.TELEGRAM.value),
    type: Optional[str] = Query(None),
    refresh: bool = Query(False),
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    _validate_platform(platform)
    try:
        aid = await _resolve_platform_account(platform, account_id)
        chats = await list_platform_chats(platform, refresh=refresh, account_id=aid)
        if type:
            chats = [c for c in chats if c["type"] == type]
        return chats
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/whatsapp/auth/status")
async def whatsapp_auth_status(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    status = await whatsapp_service.get_status(aid)
    if status.get("user"):
        status = {**status, "user": sanitize_user_info(status["user"])}
    return status


@app.get("/api/whatsapp/stats")
async def whatsapp_stats(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    bridge = await whatsapp_service.get_bridge_stats(aid)
    stored = await list_conversations("whatsapp", account_id=aid)
    return {
        "connected": bridge.get("connected", False),
        "bridge_chats": bridge.get("chats", 0),
        "bridge_messages": bridge.get("messages", 0),
        "panel_conversations": len(stored),
    }


@app.get("/api/whatsapp/auth/qr")
async def whatsapp_qr(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    try:
        return await whatsapp_service.get_qr(aid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/whatsapp/auth/start")
async def whatsapp_start(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    try:
        return await whatsapp_service.start(aid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/whatsapp/auth/logout")
async def whatsapp_logout(
    request: Request,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    await whatsapp_service.logout(aid)
    return {"ok": True}


@app.get("/api/whatsapp/chats/{jid}/messages")
async def whatsapp_messages(
    request: Request,
    jid: str,
    limit: int = Query(50, le=200),
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    try:
        return await whatsapp_service.get_messages(jid, limit, account_id=aid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/whatsapp/send")
async def whatsapp_send_now(
    request: Request,
    body: dict,
    account_id: Optional[int] = Query(None),
):
    await _check_panel_auth(request)
    aid = await _resolve_whatsapp_account(account_id)
    try:
        wa_result = await whatsapp_service.send_message(body["jid"], body["message"], account_id=aid)
        from datetime import datetime as dt
        saved = await save_message(
            platform="whatsapp",
            chat_id=body["jid"],
            message_id=wa_result.get("message_id", "0"),
            text=body["message"],
            from_me=True,
            timestamp=dt.utcnow(),
            account_id=aid,
        )
        await realtime_hub.broadcast({"type": "message", "data": saved})
        return {"ok": True, "saved": saved}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/chats/telegram")
async def list_telegram_chats(request: Request, type: Optional[str] = Query(None)):
    await _check_panel_auth(request)
    try:
        chats = await telegram_service.list_chats()
        if type:
            chats = [c for c in chats if c["type"] == type]
        return chats
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/scheduled")
async def list_scheduled(request: Request, status: Optional[str] = Query(None)):
    await _check_panel_auth(request)
    async with async_session() as session:
        query = select(ScheduledMessage).order_by(ScheduledMessage.scheduled_at.desc())
        if status:
            query = query.where(ScheduledMessage.status == status)
        result = await session.execute(query)
        jobs = result.scalars().all()

    return [_serialize_job(j) for j in jobs]


@app.post("/api/scheduled")
async def create_scheduled(request: Request, body: ScheduleRequest):
    await _check_panel_auth(request)
    _validate_platform(body.platform)

    from app.random_window import validate_window

    is_random_daily = body.repeat_type == RepeatType.RANDOM_DAILY.value

    if is_random_daily:
        if not body.window_start_time or not body.window_end_time:
            raise HTTPException(status_code=400, detail=E.SCHEDULE_RANDOM_WINDOW)
        try:
            validate_window(body.window_start_time, body.window_end_time)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        scheduled_at = utc_now()
    else:
        if body.scheduled_at is None:
            raise HTTPException(status_code=400, detail=E.SCHEDULE_TIME_REQUIRED)
        scheduled_at = from_client_datetime(body.scheduled_at)
        if scheduled_at <= utc_now() and body.repeat_type == RepeatType.NONE.value:
            raise HTTPException(status_code=400, detail=E.SCHEDULE_FUTURE_REQUIRED)

    if body.repeat_type == RepeatType.CUSTOM.value and not body.repeat_interval_minutes:
        raise HTTPException(status_code=400, detail=E.SCHEDULE_CUSTOM_INTERVAL)

    job_account_id = await _resolve_platform_account(body.platform, body.account_id)

    job = ScheduledMessage(
        platform=body.platform,
        account_id=job_account_id,
        chat_id=body.chat_id,
        chat_name=body.chat_name,
        chat_type=body.chat_type,
        message_text=body.message_text,
        scheduled_at=scheduled_at,
        repeat_type=body.repeat_type,
        repeat_interval_minutes=body.repeat_interval_minutes,
        window_start_time=body.window_start_time,
        window_end_time=body.window_end_time,
        status=JobStatus.PENDING.value,
        is_active=True,
        next_run_at=scheduled_at,
        send_count=0,
    )

    if is_random_daily:
        try:
            prepare_random_daily_job(job)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    async with async_session() as session:
        job = await session.get(ScheduledMessage, job_id)
        await schedule_message(job)
        await session.commit()
        await session.refresh(job)
        scheduled_at_tr = format_istanbul(job.scheduled_at)

    return {
        "id": job_id,
        "status": "scheduled",
        "scheduled_at_tr": scheduled_at_tr,
        "repeat_type": body.repeat_type,
        "window_label": (
            f"{body.window_start_time}–{body.window_end_time}"
            if is_random_daily else None
        ),
    }


@app.put("/api/scheduled/{job_id}")
async def update_scheduled(request: Request, job_id: int, body: ScheduleUpdateRequest):
    await _check_panel_auth(request)

    async with async_session() as session:
        job = await session.get(ScheduledMessage, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=E.MESSAGE_NOT_FOUND)
        if not job.is_active:
            raise HTTPException(status_code=400, detail=E.MESSAGE_NOT_EDITABLE)

        if body.message_text is not None:
            job.message_text = body.message_text
        if body.scheduled_at is not None:
            job.scheduled_at = from_client_datetime(body.scheduled_at)
            job.next_run_at = job.scheduled_at
        if body.repeat_type is not None:
            job.repeat_type = body.repeat_type
        if body.repeat_interval_minutes is not None:
            job.repeat_interval_minutes = body.repeat_interval_minutes
        if body.window_start_time is not None:
            job.window_start_time = body.window_start_time
        if body.window_end_time is not None:
            job.window_end_time = body.window_end_time

        if job.repeat_type == RepeatType.RANDOM_DAILY.value:
            from app.random_window import validate_window
            try:
                validate_window(job.window_start_time or "", job.window_end_time or "")
                prepare_random_daily_job(job)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        job.status = JobStatus.PENDING.value
        await session.commit()
        await schedule_message(job)
        await session.commit()

    return {"ok": True}


@app.post("/api/scheduled/{job_id}/send-now")
async def send_scheduled_now(request: Request, job_id: int):
    await _check_panel_auth(request)
    try:
        await send_now(job_id)
        return {"ok": True}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scheduled/{job_id}/retry")
async def retry_scheduled(request: Request, job_id: int):
    await _check_panel_auth(request)
    try:
        await retry_job(job_id)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/scheduled/{job_id}")
async def delete_scheduled(request: Request, job_id: int):
    await _check_panel_auth(request)
    await cancel_job(job_id)
    return {"ok": True}


@app.get("/api/templates")
async def list_templates(request: Request):
    await _check_panel_auth(request)
    async with async_session() as session:
        result = await session.execute(
            select(MessageTemplate).order_by(MessageTemplate.created_at.desc())
        )
        templates_list = result.scalars().all()

    return [
        {
            "id": t.id,
            "title": t.title,
            "message_text": t.message_text,
            "created_at": t.created_at.isoformat() + "Z",
        }
        for t in templates_list
    ]


@app.post("/api/templates")
async def create_template(request: Request, body: TemplateRequest):
    await _check_panel_auth(request)
    template = MessageTemplate(title=body.title, message_text=body.message_text)
    async with async_session() as session:
        session.add(template)
        await session.commit()
        await session.refresh(template)
    return {"id": template.id}


@app.delete("/api/templates/{template_id}")
async def delete_template(request: Request, template_id: int):
    await _check_panel_auth(request)
    async with async_session() as session:
        template = await session.get(MessageTemplate, template_id)
        if template:
            await session.delete(template)
            await session.commit()
    return {"ok": True}
