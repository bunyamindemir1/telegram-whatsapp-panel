"""i18n API and locale file integrity tests."""

from pathlib import Path

import pytest

from app.config import BASE_DIR
from app.i18n import SUPPORTED_LOCALES, load_messages, resolve_locale

# Values intentionally identical across EN/TR (proper nouns, numeric placeholders)
TR_SAME_OK = frozenset({
    "account.apiHash",
    "account.apiIdPlaceholder",
    "account.phonePlaceholder",
    "account.telegramApi",
    "compose.broadcastPlaceholder",
    "compose.charCount",
})

TR_MUST_DIFFER_PREFIXES = (
    "nav.", "dashboard.", "chats.", "compose.", "scheduled.", "templates.",
    "account.", "login.", "toast.", "backup.", "followUp.", "autoReply.",
)


@pytest.mark.parametrize("code", list(SUPPORTED_LOCALES.keys()))
def test_locale_file_exists_and_loads(code):
    msgs = load_messages(code)
    assert len(msgs) >= 100
    assert "nav.dashboard" in msgs
    assert "login.title" in msgs


def test_all_locales_share_en_keys():
    en = load_messages("en")
    keys = set(en.keys())
    assert len(keys) >= 500
    for code in SUPPORTED_LOCALES:
        if code == "en":
            continue
        loc = load_messages(code)
        missing = keys - set(loc.keys())
        assert not missing, f"{code} missing keys: {sorted(missing)[:5]}"


def test_turkish_ui_strings_differ_from_english():
    """Turkish locale must not copy English for primary UI keys."""
    en = load_messages("en")
    tr = load_messages("tr")
    same = []
    for key, en_val in en.items():
        if key in TR_SAME_OK:
            continue
        if not any(key.startswith(p) for p in TR_MUST_DIFFER_PREFIXES):
            continue
        tr_val = tr.get(key)
        if tr_val == en_val:
            same.append(key)
    assert not same, f"TR copies EN for {len(same)} UI keys, e.g. {same[:8]}"


def test_turkish_error_messages_differ_from_english():
    en = load_messages("en")
    tr = load_messages("tr")
    for key in en:
        if not key.startswith("error."):
            continue
        assert tr.get(key) != en[key], f"{key} not translated in TR"


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
