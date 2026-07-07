from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app import error_codes as E
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.account_service import list_accounts, resolve_account_id
from app.api_keys import create_api_key, list_api_keys, revoke_api_key
from app.auth_deps import check_panel_auth, require_v1_auth, validate_platform
from app.media_service import resolve_media_path, save_upload
from app.message_store import get_messages, list_conversations
from app.messaging import list_platform_chats, send_platform_media, send_platform_message
from app.models import Platform
from app.database import async_session
from app.models import JobStatus, ScheduledMessage
from app.scheduler_service import schedule_message
from app.serializers import serialize_job
from app.utils.datetime_utils import from_client_datetime, utc_now

from app.auto_reply_service import create_auto_reply_rule, delete_auto_reply_rule, list_auto_reply_rules
from app.follow_up_service import create_follow_up, list_follow_ups
from app.webhook_service import EVENT_TYPES, create_webhook, delete_webhook, list_webhooks

router = APIRouter(tags=["API v1"])


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class V1SendMessageRequest(BaseModel):
    platform: str
    account_id: Optional[int] = None
    chat_id: str
    message: str = Field(min_length=1, max_length=4096)
    chat_name: str = ""
    chat_type: str = "unknown"


class V1ScheduleRequest(BaseModel):
    platform: str = Platform.TELEGRAM.value
    account_id: Optional[int] = None
    chat_id: str
    chat_name: str
    chat_type: str = "unknown"
    message_text: str = Field(min_length=1, max_length=4096)
    scheduled_at: datetime


class V1BroadcastRequest(BaseModel):
    platform: str
    account_id: Optional[int] = None
    chat_ids: list[str] = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=4096)


class V1AutoReplyRequest(BaseModel):
    platform: str
    account_id: Optional[int] = None
    keyword: str = Field(min_length=1, max_length=120)
    response_text: str = Field(min_length=1, max_length=4096)
    match_mode: str = "contains"
    cooldown_minutes: int = Field(default=60, ge=1, le=1440)


class V1FollowUpRequest(BaseModel):
    platform: str
    account_id: Optional[int] = None
    chat_id: str
    chat_name: str = ""
    reminder_text: str = Field(min_length=1, max_length=4096)
    wait_hours: int = Field(default=24, ge=1, le=168)


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=512)
    events: list[str] = Field(default_factory=lambda: ["message.received"])
    secret: str = Field(default="", max_length=128)


@router.get("/health")
async def v1_health():
    return {"ok": True, "version": "1"}


@router.get("/accounts", dependencies=[Depends(require_v1_auth)])
async def v1_list_accounts(platform: Optional[str] = Query(None)):
    if platform:
        validate_platform(platform)
        return await list_accounts(platform)
    tg = await list_accounts(Platform.TELEGRAM.value)
    wa = await list_accounts(Platform.WHATSAPP.value)
    return {"telegram": tg, "whatsapp": wa}


@router.get("/conversations", dependencies=[Depends(require_v1_auth)])
async def v1_conversations(
    platform: str = Query(Platform.TELEGRAM.value),
    account_id: Optional[int] = Query(None),
    refresh: bool = Query(False),
):
    validate_platform(platform)
    aid = await resolve_account_id(platform, account_id)
    if refresh:
        return await list_platform_chats(platform, refresh=True, account_id=aid)
    return await list_conversations(platform, account_id=aid)


@router.get("/messages/{platform}/{chat_id}", dependencies=[Depends(require_v1_auth)])
async def v1_messages(
    platform: str,
    chat_id: str,
    account_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None),
):
    validate_platform(platform)
    aid = await resolve_account_id(platform, account_id)
    return await get_messages(platform, chat_id, account_id=aid, limit=limit, before_id=before_id)


@router.post("/messages/send", dependencies=[Depends(require_v1_auth)])
async def v1_send_message(body: V1SendMessageRequest):
    validate_platform(body.platform)
    result = await send_platform_message(
        body.platform,
        body.chat_id,
        body.message,
        chat_name=body.chat_name,
        chat_type=body.chat_type,
        account_id=body.account_id,
    )
    return {"ok": True, "result": result}


@router.post("/messages/send-media", dependencies=[Depends(require_v1_auth)])
async def v1_send_media(
    platform: str = Query(...),
    account_id: int = Query(...),
    chat_id: str = Query(...),
    caption: str = Query(""),
    chat_name: str = Query(""),
    chat_type: str = Query("unknown"),
    file: UploadFile = File(...),
):
    validate_platform(platform)
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


@router.get("/media/{media_path:path}", dependencies=[Depends(require_v1_auth)])
async def v1_serve_media(media_path: str):
    from fastapi.responses import FileResponse

    path = resolve_media_path(media_path)
    return FileResponse(path, filename=path.name)


@router.post("/scheduled", dependencies=[Depends(require_v1_auth)])
async def v1_schedule(body: V1ScheduleRequest):
    validate_platform(body.platform)
    aid = await resolve_account_id(body.platform, body.account_id)
    scheduled_at = from_client_datetime(body.scheduled_at)
    if scheduled_at <= utc_now():
        raise HTTPException(status_code=400, detail=E.SCHEDULE_FUTURE_REQUIRED)

    job = ScheduledMessage(
        platform=body.platform,
        account_id=aid,
        chat_id=body.chat_id,
        chat_name=body.chat_name,
        chat_type=body.chat_type,
        message_text=body.message_text,
        scheduled_at=scheduled_at,
        repeat_type="none",
        status=JobStatus.PENDING.value,
        is_active=True,
        next_run_at=scheduled_at,
        send_count=0,
    )
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
    return serialize_job(job)


@router.get("/scheduled", dependencies=[Depends(require_v1_auth)])
async def v1_list_scheduled(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    async with async_session() as session:
        query = select(ScheduledMessage).order_by(ScheduledMessage.scheduled_at.desc())
        if platform:
            validate_platform(platform)
            query = query.where(ScheduledMessage.platform == platform)
        if status:
            query = query.where(ScheduledMessage.status == status)
        jobs = (await session.execute(query)).scalars().all()
    return [serialize_job(j) for j in jobs]


@router.post("/messages/broadcast", dependencies=[Depends(require_v1_auth)])
async def v1_broadcast(body: V1BroadcastRequest):
    validate_platform(body.platform)
    aid = await resolve_account_id(body.platform, body.account_id)
    sent = 0
    errors: list[dict] = []
    for chat_id in body.chat_ids[:50]:
        try:
            await send_platform_message(body.platform, chat_id, body.message, account_id=aid)
            sent += 1
        except Exception as exc:
            errors.append({"chat_id": chat_id, "error": str(exc)})
    return {"ok": not errors, "sent": sent, "failed": len(errors), "errors": errors}


@router.get("/auto-replies", dependencies=[Depends(require_v1_auth)])
async def v1_list_auto_replies(platform: Optional[str] = Query(None)):
    if platform:
        validate_platform(platform)
    return await list_auto_reply_rules(platform)


@router.post("/auto-replies", dependencies=[Depends(require_v1_auth)])
async def v1_create_auto_reply(body: V1AutoReplyRequest):
    validate_platform(body.platform)
    aid = await resolve_account_id(body.platform, body.account_id)
    return await create_auto_reply_rule(
        platform=body.platform,
        keyword=body.keyword,
        response_text=body.response_text,
        account_id=aid,
        match_mode=body.match_mode,
        cooldown_minutes=body.cooldown_minutes,
    )


@router.delete("/auto-replies/{rule_id}", dependencies=[Depends(require_v1_auth)])
async def v1_delete_auto_reply(rule_id: int):
    if not await delete_auto_reply_rule(rule_id):
        raise HTTPException(status_code=404, detail=E.AUTO_REPLY_NOT_FOUND)
    return {"ok": True}


@router.post("/follow-ups", dependencies=[Depends(require_v1_auth)])
async def v1_create_follow_up(body: V1FollowUpRequest):
    validate_platform(body.platform)
    aid = await resolve_account_id(body.platform, body.account_id)
    return await create_follow_up(
        platform=body.platform,
        chat_id=body.chat_id,
        reminder_text=body.reminder_text,
        wait_hours=body.wait_hours,
        account_id=aid,
        chat_name=body.chat_name,
    )


@router.get("/follow-ups", dependencies=[Depends(require_v1_auth)])
async def v1_list_follow_ups_endpoint(
    platform: Optional[str] = Query(None),
    status: str = Query("pending"),
):
    if platform:
        validate_platform(platform)
    return await list_follow_ups(platform, status=status)


@router.get("/keys", dependencies=[Depends(check_panel_auth)])
async def v1_list_keys():
    return await list_api_keys()


@router.post("/keys", dependencies=[Depends(check_panel_auth)])
async def v1_create_key(body: ApiKeyCreateRequest, request: Request):
    user_id = request.session.get("user_id")
    row, raw = await create_api_key(body.name, user_id)
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "api_key": raw,
        "message": "API anahtarını şimdi kaydedin; bir daha gösterilmeyecek.",
    }


@router.delete("/keys/{key_id}", dependencies=[Depends(check_panel_auth)])
async def v1_revoke_key(key_id: int):
    if not await revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail=E.API_KEY_NOT_FOUND)
    return {"ok": True}


@router.get("/webhooks", dependencies=[Depends(check_panel_auth)])
async def v1_list_webhooks():
    return await list_webhooks()


@router.get("/webhooks/events", dependencies=[Depends(check_panel_auth)])
async def v1_webhook_events():
    return list(EVENT_TYPES)


@router.post("/webhooks", dependencies=[Depends(check_panel_auth)])
async def v1_create_webhook(body: WebhookCreateRequest):
    row = await create_webhook(body.name, body.url, body.events, body.secret)
    return {"id": row.id, "name": row.name, "url": row.url}


@router.delete("/webhooks/{webhook_id}", dependencies=[Depends(check_panel_auth)])
async def v1_delete_webhook(webhook_id: int):
    if not await delete_webhook(webhook_id):
        raise HTTPException(status_code=404, detail=E.WEBHOOK_NOT_FOUND)
    return {"ok": True}
