from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Optional

import bcrypt
from fastapi import HTTPException, Request, WebSocket
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy import func, select

from app import error_codes as E
from app.config import (
    ENV,
    PANEL_ADMIN_PASSWORD,
    PANEL_ADMIN_USER,
    PANEL_PASSWORD,
    REQUIRE_PANEL_AUTH,
    SESSION_SECRET,
    BRIDGE_SECRET,
)
from app import database
from app.models import PanelUser
from app.security import (
    DUMMY_BCRYPT_HASH,
    get_client_ip,
    login_rate_limiter,
    validate_password_strength,
)
from app.secret_policy import (
    is_weak_admin_password,
    is_weak_bridge_secret,
    is_weak_session_secret,
)

logger = logging.getLogger(__name__)

SESSION_MAX_AGE = 14 * 24 * 3600
SESSION_COOKIE_NAME = "mesaj_panel"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def count_users() -> int:
    async with database.async_session() as session:
        return await session.scalar(select(func.count()).select_from(PanelUser)) or 0


async def get_user_by_username(username: str) -> Optional[PanelUser]:
    async with database.async_session() as session:
        result = await session.execute(select(PanelUser).where(PanelUser.username == username))
        return result.scalar_one_or_none()


async def create_user(username: str, password: str, *, is_admin: bool = True) -> PanelUser:
    validate_password_strength(password)
    name = username.strip().lower()
    if not name or len(name) < 3:
        raise ValueError("Kullanıcı adı en az 3 karakter olmalı")
    if not re.match(r"^[a-z0-9._-]+$", name):
        raise ValueError("Kullanıcı adı yalnızca harf, rakam, nokta, tire ve alt çizgi içerebilir")
    async with database.async_session() as session:
        user = PanelUser(
            username=name,
            password_hash=hash_password(password),
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def ensure_admin_from_env() -> bool:
    if not PANEL_ADMIN_USER or not PANEL_ADMIN_PASSWORD:
        return False
    if await count_users() > 0:
        return False
    await create_user(PANEL_ADMIN_USER, PANEL_ADMIN_PASSWORD, is_admin=True)
    logger.info("Panel admin kullanıcısı oluşturuldu: %s", PANEL_ADMIN_USER)
    return True


def auth_required() -> bool:
    if REQUIRE_PANEL_AUTH:
        return True
    return bool(PANEL_PASSWORD)


async def setup_required() -> bool:
    users = await count_users()
    return users == 0 and not PANEL_PASSWORD


def _session_from_cookie(cookie: Optional[str]) -> dict[str, Any]:
    if not cookie:
        return {}
    signer = TimestampSigner(str(SESSION_SECRET))
    try:
        data = signer.unsign(cookie.encode("utf-8"), max_age=SESSION_MAX_AGE)
        return json.loads(base64.b64decode(data))
    except (BadSignature, SignatureExpired, json.JSONDecodeError, Exception):
        return {}


def is_session_authenticated(session: dict[str, Any]) -> bool:
    return bool(session.get("authenticated"))


def set_session_user(request: Request, user: PanelUser) -> None:
    request.session["authenticated"] = True
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["is_admin"] = user.is_admin


def set_legacy_session(request: Request) -> None:
    request.session["authenticated"] = True
    request.session["username"] = "legacy"
    request.session["is_admin"] = True


def clear_session(request: Request) -> None:
    request.session.clear()


async def authenticate(request: Request, username: Optional[str], password: str) -> PanelUser:
    ip = get_client_ip(request)
    login_rate_limiter.check_allowed(ip)

    users = await count_users()
    if users == 0:
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail=E.AUTH_INVALID)
    if not username:
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=400, detail=E.AUTH_USERNAME_REQUIRED)

    user = await get_user_by_username(username.strip().lower())
    password_hash = user.password_hash if user else DUMMY_BCRYPT_HASH
    valid = verify_password(password, password_hash)

    if not user or not valid:
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail=E.AUTH_INVALID)
    if not user.is_active:
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=403, detail=E.AUTH_ACCOUNT_DISABLED)

    login_rate_limiter.record_success(ip)
    return user


async def check_panel_auth(request: Request) -> None:
    if not auth_required():
        return

    if is_session_authenticated(dict(request.session)):
        return

    if await setup_required():
        raise HTTPException(status_code=401, detail=E.AUTH_SETUP_REQUIRED)

    raise HTTPException(status_code=401, detail=E.AUTH_LOGIN_REQUIRED)


async def ws_authenticated(websocket: WebSocket) -> bool:
    if not auth_required():
        return True
    session = _session_from_cookie(websocket.cookies.get(SESSION_COOKIE_NAME))
    return is_session_authenticated(session)


def validate_production_settings() -> None:
    if ENV != "production":
        return
    if is_weak_session_secret(SESSION_SECRET):
        raise RuntimeError(
            "Production: SESSION_SECRET güçlü ve benzersiz olmalı (setup.sh ile üretin)"
        )
    if is_weak_bridge_secret(BRIDGE_SECRET):
        raise RuntimeError(
            "Production: BRIDGE_SECRET güçlü ve benzersiz olmalı (varsayılan/örnek değer kullanılamaz)"
        )
    if not PANEL_ADMIN_PASSWORD and not PANEL_PASSWORD:
        raise RuntimeError("Production: PANEL_ADMIN_USER/PASSWORD veya PANEL_PASSWORD zorunlu")
    if PANEL_ADMIN_PASSWORD:
        if is_weak_admin_password(PANEL_ADMIN_PASSWORD):
            raise RuntimeError("Production: PANEL_ADMIN_PASSWORD örnek/varsayılan değer olamaz")
        validate_password_strength(PANEL_ADMIN_PASSWORD)
    if PANEL_PASSWORD:
        if len(PANEL_PASSWORD) < 8:
            raise RuntimeError("Production: PANEL_PASSWORD en az 8 karakter olmalı")
        if is_weak_admin_password(PANEL_PASSWORD):
            raise RuntimeError("Production: PANEL_PASSWORD örnek/varsayılan değer olamaz")
