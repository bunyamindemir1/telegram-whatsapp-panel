"""Merge-field rendering for message templates and scheduled sends."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def build_template_context(
    *,
    chat_name: str = "",
    chat_id: str = "",
    platform: str = "",
    now: Optional[datetime] = None,
) -> dict[str, str]:
    moment = now or datetime.now()
    return {
        "date": moment.strftime("%Y-%m-%d"),
        "time": moment.strftime("%H:%M"),
        "datetime": moment.strftime("%Y-%m-%d %H:%M"),
        "chat_name": chat_name or "",
        "chat_id": chat_id or "",
        "platform": platform or "",
    }


def render_template(text: str, context: dict[str, str]) -> str:
    if not text or "{{" not in text:
        return text

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return context.get(key, match.group(0))

    return _VAR_PATTERN.sub(repl, text)
