"""Production secret policy and timing-safe token checks."""

from __future__ import annotations

import secrets

from app.config import BRIDGE_SECRET, DEFAULT_BRIDGE_SECRET, PANEL_ADMIN_PASSWORD, SESSION_SECRET

# Placeholder / documented example values — must never run in production
WEAK_BRIDGE_SECRETS = frozenset({
    DEFAULT_BRIDGE_SECRET,
    "degistirin-guclu-kopru-anahtari",
    "degistirin-kopru-anahtari",
    "change-me-bridge",
})

WEAK_SESSION_SECRETS = frozenset({
    "degistirin-guclu-rastgele-en-az-32-karakter",
    "degistirin-guclu-rastgele-32-karakter",
    "changeme",
    "change-me",
    "secret",
})

WEAK_ADMIN_PASSWORDS = frozenset({
    "degistirin-guclu-sifre-min-8",
    "changeme",
    "admin123",
    "password",
    "password1",
})


def _is_placeholder_secret(value: str) -> bool:
    upper = value.upper()
    return upper.startswith("CHANGE_ME") or upper.startswith("DEGISTIRIN-")


def verify_bridge_token(header_token: str, expected: str) -> bool:
    if not header_token or not expected:
        return False
    return secrets.compare_digest(header_token, expected)


def is_weak_bridge_secret(value: str) -> bool:
    v = (value or "").strip()
    return not v or v in WEAK_BRIDGE_SECRETS or _is_placeholder_secret(v)


def is_weak_session_secret(value: str) -> bool:
    v = (value or "").strip()
    return not v or len(v) < 16 or v in WEAK_SESSION_SECRETS or _is_placeholder_secret(v)


def is_weak_admin_password(value: str) -> bool:
    v = (value or "").strip()
    return not v or v in WEAK_ADMIN_PASSWORDS or _is_placeholder_secret(v)
