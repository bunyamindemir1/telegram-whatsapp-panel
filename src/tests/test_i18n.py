"""i18n API and locale file integrity tests."""

from pathlib import Path

import pytest

from app.config import BASE_DIR
from app.i18n import SUPPORTED_LOCALES, load_messages, resolve_locale


@pytest.mark.parametrize("code", list(SUPPORTED_LOCALES.keys()))
def test_locale_file_exists_and_loads(code):
    msgs = load_messages(code)
    assert len(msgs) >= 100
    assert "nav.dashboard" in msgs
    assert "login.title" in msgs


def test_all_locales_share_en_keys():
    en = load_messages("en")
    keys = set(en.keys())
    assert len(keys) >= 350
    for code in SUPPORTED_LOCALES:
        if code == "en":
            continue
        loc = load_messages(code)
        missing = keys - set(loc.keys())
        assert not missing, f"{code} missing keys: {sorted(missing)[:5]}"


def test_resolve_locale_prefers_query():
    assert resolve_locale(query_locale="tr", cookie_locale="en", accept_language="en") == "tr"


def test_resolve_locale_cookie_over_accept():
    assert resolve_locale(cookie_locale="ar", accept_language="en") == "ar"


def test_resolve_locale_fallback_en():
    assert resolve_locale(accept_language="xx-unknown") == "en"


def test_locale_json_valid_utf8():
    for path in (BASE_DIR / "locales").glob("*.json"):
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
