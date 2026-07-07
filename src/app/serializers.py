from __future__ import annotations

from app.models import ScheduledMessage
from app.utils.datetime_utils import format_istanbul


def serialize_job(j: ScheduledMessage) -> dict:
    return {
        "id": j.id,
        "platform": j.platform,
        "account_id": j.account_id,
        "chat_id": j.chat_id,
        "chat_name": j.chat_name,
        "chat_type": j.chat_type,
        "message_text": j.message_text,
        "scheduled_at": j.scheduled_at.isoformat() + "Z",
        "scheduled_at_tr": format_istanbul(j.scheduled_at),
        "repeat_type": j.repeat_type,
        "repeat_interval_minutes": j.repeat_interval_minutes,
        "window_start_time": j.window_start_time,
        "window_end_time": j.window_end_time,
        "status": j.status,
        "is_active": j.is_active,
        "send_count": j.send_count or 0,
        "last_run_at": (j.last_run_at.isoformat() + "Z") if j.last_run_at else None,
        "error_message": j.error_message,
        "created_at": j.created_at.isoformat() + "Z",
    }
