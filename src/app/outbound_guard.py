from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app import error_codes as E
from app.config import ALLOW_OUTBOUND_MESSAGES

logger = logging.getLogger(__name__)


class OutboundBlockedError(PermissionError):
    """Giden mesajlar test modunda kapalı."""


def outbound_allowed() -> bool:
    return ALLOW_OUTBOUND_MESSAGES


def ensure_outbound_allowed() -> None:
    if not outbound_allowed():
        raise OutboundBlockedError(E.OUTBOUND_BLOCKED)


def simulated_send_result(platform: str, chat_id: str, message: str) -> dict[str, Any]:
    logger.info(
        "[DRY-RUN] Outbound blocked | platform=%s chat=%s len=%d",
        platform,
        chat_id,
        len(message),
    )
    return {
        "dry_run": True,
        "simulated": True,
        "message_id": f"dry-{int(datetime.utcnow().timestamp())}",
        "detail": E.OUTBOUND_DRY_RUN,
    }
