"""Internationalization — 15 locales for panel UI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

LOCALES_DIR = BASE_DIR / "locales"
DEFAULT_LOCALE = "en"
FALLBACK_LOCALE = "en"

SUPPORTED_LOCALES: dict[str, dict[str, Any]] = {
    "en": {"name": "English", "native": "English", "rtl": False},
    "tr": {"name": "Turkish", "native": "Türkçe", "rtl": False},
    "ar": {"name": "Arabic", "native": "العربية", "rtl": True},
    "ru": {"name": "Russian", "native": "Русский", "rtl": False},
    "de": {"name": "German", "native": "Deutsch", "rtl": False},
    "fr": {"name": "French", "native": "Français", "rtl": False},
    "es": {"name": "Spanish", "native": "Español", "rtl": False},
    "pt": {"name": "Portuguese", "native": "Português", "rtl": False},
    "it": {"name": "Italian", "native": "Italiano", "rtl": False},
    "nl": {"name": "Dutch", "native": "Nederlands", "rtl": False},
    "pl": {"name": "Polish", "native": "Polski", "rtl": False},
    "uk": {"name": "Ukrainian", "native": "Українська", "rtl": False},
    "zh": {"name": "Chinese", "native": "中文", "rtl": False},
    "ja": {"name": "Japanese", "native": "日本語", "rtl": False},
    "ko": {"name": "Korean", "native": "한국어", "rtl": False},
}

_locale_cache: dict[str, dict[str, str]] = {}


def _parse_accept_language(header: str) -> list[str]:
    if not header:
        return []
    out: list[tuple[float, str]] = []
    for part in header.split(","):
        piece = part.strip()
        if not piece:
            continue
        lang = piece.split(";")[0].strip().lower()
        q = 1.0
        if ";" in piece:
            m = re.search(r"q=([0-9.]+)", piece)
            if m:
                q = float(m.group(1))
        base = lang.split("-")[0]
        out.append((q, lang))
        if base != lang:
            out.append((q - 0.001, base))
    out.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    ordered: list[str] = []
    for _, code in out:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def resolve_locale(
    cookie_locale: str | None = None,
    accept_language: str | None = None,
    query_locale: str | None = None,
) -> str:
    for candidate in (query_locale, cookie_locale):
        if candidate and candidate in SUPPORTED_LOCALES:
            return candidate
    for code in _parse_accept_language(accept_language or ""):
        if code in SUPPORTED_LOCALES:
            return code
        base = code.split("-")[0]
        if base in SUPPORTED_LOCALES:
            return base
    return DEFAULT_LOCALE


def load_messages(locale: str) -> dict[str, str]:
    if locale in _locale_cache:
        return _locale_cache[locale]
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        path = LOCALES_DIR / f"{FALLBACK_LOCALE}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fallback = {}
    if locale != FALLBACK_LOCALE:
        fb_path = LOCALES_DIR / f"{FALLBACK_LOCALE}.json"
        if fb_path.exists():
            fallback = json.loads(fb_path.read_text(encoding="utf-8"))
    merged = {**fallback, **data}
    _locale_cache[locale] = merged
    return merged


def locale_meta(locale: str) -> dict[str, Any]:
    return {
        "code": locale,
        **SUPPORTED_LOCALES.get(locale, SUPPORTED_LOCALES[DEFAULT_LOCALE]),
    }


def list_locales() -> list[dict[str, Any]]:
    return [{"code": code, **meta} for code, meta in SUPPORTED_LOCALES.items()]
