"""Request/response models for the panel HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import Platform, RepeatType


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
    reply_to_message_id: Optional[str] = None


class BroadcastRequest(BaseModel):
    platform: str
    chat_ids: list[str] = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=4096)
    chat_names: Optional[dict[str, str]] = None


class ConversationMetaRequest(BaseModel):
    is_pinned: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=2000)
    tags: Optional[list[str]] = None
    is_muted: Optional[bool] = None
    snooze_hours: Optional[int] = Field(None, ge=1, le=168)
    clear_snooze: bool = False


class TemplateUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    message_text: Optional[str] = Field(None, min_length=1, max_length=4096)
    category: Optional[str] = Field(None, max_length=64)


class AutoReplyUpdateRequest(BaseModel):
    keyword: Optional[str] = Field(None, min_length=1, max_length=120)
    response_text: Optional[str] = Field(None, min_length=1, max_length=4096)
    match_mode: Optional[str] = None
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=1440)
    is_active: Optional[bool] = None


class FollowUpRequest(BaseModel):
    platform: str
    chat_id: str
    reminder_text: str = Field(min_length=1, max_length=4096)
    wait_hours: int = Field(default=24, ge=1, le=168)
    account_id: Optional[int] = None
    chat_name: str = ""


class StarMessageRequest(BaseModel):
    starred: bool = True


class BackupImportRequest(BaseModel):
    data: dict
    merge: bool = True


class AutoReplyRequest(BaseModel):
    platform: str
    keyword: str = Field(min_length=1, max_length=120)
    response_text: str = Field(min_length=1, max_length=4096)
    account_id: Optional[int] = None
    match_mode: str = "contains"
    cooldown_minutes: int = Field(default=60, ge=1, le=1440)


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
    category: str = Field(default="general", max_length=64)


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
