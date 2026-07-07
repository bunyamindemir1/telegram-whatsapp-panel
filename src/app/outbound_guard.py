from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.config import ALLOW_OUTBOUND_MESSAGES

logger = logging.getLogger(__name__)


class OutboundBlockedError(PermissionError):
    """Giden mesajlar test modunda kapalı."""


def outbound_allowed() -> bool:
    return ALLOW_OUTBOUND_MESSAGES


def ensure_outbound_allowed() -> None:
    if not outbound_allowed():
        raise OutboundBlockedError(
            "Giden mesajlar kapalı (test modu). Canlı gönderim için ALLOW_OUTBOUND_MESSAGES=true ayarlayın."
        )


def simulated_send_result(platform: str, chat_id: str, message: str) -> dict[str, Any]:
    logger.info(
        "[DRY-RUN] Simüle gönderim engellendi | platform=%s chat=%s len=%d",
        platform,
        chat_id,
        len(message),
    )
    return {
        "dry_run": True,
        "simulated": True,
        "message_id": f"dry-{int(datetime.utcnow().timestamp())}",
        "detail": "Test modu: mesaj gönderilmedi",
    }
