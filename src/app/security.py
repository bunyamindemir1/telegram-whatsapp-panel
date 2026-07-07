from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Sabit bcrypt hash — kullanıcı yokken zamanlama saldırısını zorlaştırır
DUMMY_BCRYPT_HASH = "$2b$12$wNtitwKppLvwGihcNHOhXei0nFnO8HIY8kcvzXmIG5VqDEA2WujD."

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60

_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


def mask_phone(phone: str) -> str:
    """Kişisel telefon numarasını kısmen maskele."""
    if not phone:
        return ""
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 4:
        return "***"
    if raw.startswith("+"):
        prefix = raw[:4]
    else:
        prefix = digits[:3]
    suffix = digits[-2:]
    return f"{prefix}***{suffix}"


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Şifre en az 8 karakter olmalı")
    if len(password) > 128:
        raise ValueError("Şifre en fazla 128 karakter olabilir")
    if not _PASSWORD_HAS_LETTER.search(password):
        raise ValueError("Şifre en az bir harf içermeli")
    if not _PASSWORD_HAS_DIGIT.search(password):
        raise ValueError("Şifre en az bir rakam içermeli")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class LoginRateLimiter:
    """IP bazlı giriş denemesi sınırlayıcı (bellek içi)."""

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
        lockout_seconds: int = LOGIN_LOCKOUT_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._locked_until: dict[str, float] = {}

    def _prune(self, ip: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._attempts[ip] = [t for t in self._attempts[ip] if t > cutoff]

    def check_allowed(self, ip: str) -> None:
        now = time.monotonic()
        locked = self._locked_until.get(ip, 0)
        if locked > now:
            wait = int(locked - now)
            raise HTTPException(
                status_code=429,
                detail=f"Çok fazla başarısız deneme. {max(wait, 1)} saniye sonra tekrar deneyin.",
            )
        self._prune(ip, now)

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        self._prune(ip, now)
        self._attempts[ip].append(now)
        if len(self._attempts[ip]) >= self.max_attempts:
            self._locked_until[ip] = now + self.lockout_seconds
            self._attempts[ip].clear()

    def record_success(self, ip: str) -> None:
        self._attempts.pop(ip, None)
        self._locked_until.pop(ip, None)


login_rate_limiter = LoginRateLimiter()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["X-DNS-Prefetch-Control"] = "off"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response


def sanitize_user_info(user: dict | None) -> dict | None:
    if not user:
        return None
    safe = dict(user)
    if safe.get("phone"):
        safe["phone"] = mask_phone(str(safe["phone"]))
    return safe
