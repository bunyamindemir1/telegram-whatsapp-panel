from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RepeatType(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    HOURLY = "hourly"
    CUSTOM = "custom"
    RANDOM_DAILY = "random_daily"


class JobStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"


class Platform(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    OTHER = "other"


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone_masked: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    credentials_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bridge_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PanelUser(Base):
    __tablename__ = "panel_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    events_json: Mapped[str] = mapped_column(Text, default="[]")
    secret: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), default=Platform.TELEGRAM.value)
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chat_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_type: Mapped[str] = mapped_column(String(32), default="unknown")
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    repeat_type: Mapped[str] = mapped_column(String(32), default=RepeatType.NONE.value)
    repeat_interval_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    window_start_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    window_end_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("account_id", "chat_id", name="uq_conv_account_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chat_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_name_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_type: Mapped[str] = mapped_column(String(32), default="unknown")
    last_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SecureConfig(Base):
    __tablename__ = "secure_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("account_id", "chat_id", "message_id", name="uq_msg_account_chat_mid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_me: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default=MessageType.TEXT.value)
    media_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    media_mime: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    media_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    media_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_to_message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
