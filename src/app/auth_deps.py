from __future__ import annotations

from app import error_codes as E
from fastapi import HTTPException, Request

from app import panel_auth
from app.api_keys import verify_api_key
from app.models import Platform


def validate_platform(platform: str) -> str:
    allowed = {Platform.TELEGRAM.value, Platform.WHATSAPP.value}
    if platform not in allowed:
        raise HTTPException(status_code=400, detail=E.INVALID_PLATFORM)
    return platform


async def check_panel_auth(request: Request) -> None:
    await panel_auth.check_panel_auth(request)


async def require_v1_auth(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        raw = auth[7:].strip()
        key = await verify_api_key(raw)
        if key:
            request.state.api_key_id = key.id
            return
        raise HTTPException(status_code=401, detail=E.API_KEY_INVALID)
    await check_panel_auth(request)
