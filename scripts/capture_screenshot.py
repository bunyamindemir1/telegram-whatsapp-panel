#!/usr/bin/env python3
"""Capture README screenshots (requires: pip install playwright && playwright install chromium)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
LOGIN_OUT = ASSETS / "screenshot-login.png"
DASHBOARD_OUT = ASSETS / "screenshot-dashboard.png"
SETUP_OUT = ASSETS / "screenshot-setup.png"
# Back-compat alias for README badges / external links
HERO_OUT = ASSETS / "screenshot.png"


def _set_demo_env() -> None:
    os.environ.setdefault("ENV", "development")
    os.environ.setdefault("REQUIRE_PANEL_AUTH", "true")
    os.environ.setdefault("PANEL_ADMIN_USER", "admin")
    os.environ.setdefault("PANEL_ADMIN_PASSWORD", "ScreenshotDemo9!")
    os.environ.setdefault("SESSION_SECRET", "screenshot-session-secret-min-32-chars")
    os.environ.setdefault("BRIDGE_SECRET", "screenshot-bridge-secret-min-32-chars")
    os.environ.setdefault("ALLOW_OUTBOUND_MESSAGES", "false")


def _use_isolated_data_dir() -> Path:
    import tempfile
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    tmpdir = Path(tempfile.mkdtemp(prefix="mp-screenshot-"))
    import app.config as cfg

    cfg.DATA_DIR = tmpdir
    cfg.DB_PATH = tmpdir / "telegram_panel.db"
    cfg.MEDIA_DIR = tmpdir / "media"
    cfg.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.DATABASE_URL = f"sqlite+aiosqlite:///{cfg.DB_PATH}"

    import app.database as db

    db.engine = create_async_engine(cfg.DATABASE_URL, echo=False)
    db.async_session = async_sessionmaker(db.engine, class_=AsyncSession, expire_on_commit=False)
    return tmpdir


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    _set_demo_env()
    _use_isolated_data_dir()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Install: pip install playwright && playwright install chromium") from exc

    from app.main import app

    host, port = "127.0.0.1", 8766
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://{host}:{port}"
    for _ in range(60):
        try:
            import urllib.request

            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.15)
    else:
        raise SystemExit("Server did not start")

    ASSETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)

        page.goto(f"{url}/?lang=en")
        page.wait_for_selector("#login-overlay")
        page.wait_for_selector(".login-icon svg", timeout=8000)
        page.wait_for_selector(".login-brand-icon svg", timeout=8000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(LOGIN_OUT), full_page=False)
        HERO_OUT.write_bytes(LOGIN_OUT.read_bytes())

        page.fill("#panel-username-login", "admin")
        page.fill("#panel-password", "ScreenshotDemo9!")
        page.click("#panel-login-btn")
        page.wait_for_selector("#login-overlay.hidden", state="attached", timeout=8000)
        page.wait_for_selector(".sidebar .nav-icon svg", timeout=8000)
        page.wait_for_selector(".sidebar")
        page.wait_for_timeout(800)
        setup_visible = page.locator("#account-setup-overlay:not(.hidden)")
        if setup_visible.count():
            page.screenshot(path=str(SETUP_OUT), full_page=False)
        later_btn = page.locator("#account-setup-overlay:not(.hidden) button[onclick='dismissAccountSetup()']")
        if later_btn.count():
            later_btn.click()
            page.wait_for_selector("#account-setup-overlay.hidden", state="attached", timeout=5000)
        page.wait_for_timeout(500)
        page.screenshot(path=str(DASHBOARD_OUT), full_page=False)
        browser.close()

    server.should_exit = True
    print(f"Saved {LOGIN_OUT}")
    if SETUP_OUT.exists():
        print(f"Saved {SETUP_OUT}")
    print(f"Saved {DASHBOARD_OUT}")
    print(f"Saved {HERO_OUT} (hero alias)")


if __name__ == "__main__":
    main()
