from datetime import datetime

from app.template_engine import build_template_context, render_template


def test_render_known_variables():
    ctx = build_template_context(
        chat_name="Alice",
        chat_id="123",
        platform="telegram",
        now=datetime(2026, 7, 8, 15, 30),
    )
    text = "Hi {{chat_name}} on {{platform}} at {{time}} ({{date}})"
    assert render_template(text, ctx) == "Hi Alice on telegram at 15:30 (2026-07-08)"


def test_unknown_variable_left_unchanged():
    ctx = build_template_context()
    assert render_template("Hello {{unknown}}", ctx) == "Hello {{unknown}}"


def test_no_variables_passthrough():
    assert render_template("Plain text", {}) == "Plain text"
