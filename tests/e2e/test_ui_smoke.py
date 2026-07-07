"""E2E smoke tests — requires: pip install pytest-playwright && playwright install chromium"""

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {"headless": True}


def test_homepage_loads(page, live_server):
    page.goto(f"{live_server}/")
    assert page.locator(".brand").is_visible()
    assert page.locator("#lang-select").is_visible()
    assert page.locator("#account-setup-overlay").count() == 1


def test_login_icons_render(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_selector(".login-icon svg", timeout=8000)
    page.wait_for_selector(".login-brand-icon svg", timeout=8000)
    assert page.locator(".login-icon svg").count() >= 1
    assert page.locator(".nav-icon svg").first.is_visible()


def test_default_english_nav(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_function("() => typeof window.t === 'function'")
    nav = page.locator('.nav-btn[data-tab="dashboard"] span[data-i18n="nav.dashboard"]')
    expect_text = page.evaluate("() => window.t('nav.dashboard')")
    assert expect_text in ("Dashboard", "Gösterge Paneli") or nav.is_visible()


def test_turkish_locale_switch(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_selector("#lang-select")
    page.select_option("#lang-select", "tr")
    page.wait_for_function("() => window.getLocale() === 'tr'")
    title = page.evaluate("() => window.t('nav.chats')")
    assert title == "Sohbetler"


def test_language_persists_after_reload(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_selector("#lang-select")
    page.select_option("#lang-select", "de")
    page.wait_for_function("() => window.getLocale() === 'de'")
    page.reload()
    page.wait_for_function("() => window.getLocale() === 'de'")
    dash = page.evaluate("() => window.t('nav.dashboard')")
    assert dash == "Dashboard"


def test_lang_select_has_15_options(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_selector("#lang-select")
    count = page.locator("#lang-select option").count()
    assert count == 15


def test_arabic_rtl(page, live_server):
    page.goto(f"{live_server}/?lang=ar")
    page.wait_for_function("() => window.getLocale() === 'ar'")
    dir_attr = page.evaluate("() => document.documentElement.dir")
    assert dir_attr == "rtl"


def test_theme_applied_before_auth(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.evaluate("() => { localStorage.setItem('mesaj_theme', 'light'); document.documentElement.dataset.theme = 'light'; }")
    page.reload()
    theme = page.evaluate("() => document.documentElement.dataset.theme")
    assert theme == "light"


def test_theme_toggle_switches_mode(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_function("() => typeof window.toggleTheme === 'function'")
    page.evaluate("() => { localStorage.setItem('mesaj_theme', 'dark'); document.documentElement.dataset.theme = 'dark'; window.updateThemeUI(); }")
    page.evaluate("() => window.toggleTheme()")
    theme = page.evaluate("() => document.documentElement.dataset.theme")
    assert theme == "light"
    assert page.locator("#theme-icon svg").count() >= 1


def test_theme_persists_on_reload(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.evaluate("() => localStorage.setItem('mesaj_theme', 'light')")
    page.reload()
    theme = page.evaluate("() => document.documentElement.dataset.theme")
    stored = page.evaluate("() => localStorage.getItem('mesaj_theme')")
    assert theme == "light"
    assert stored == "light"


def test_theme_label_updates(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_function("() => typeof window.updateThemeUI === 'function'")
    page.evaluate("() => { document.documentElement.dataset.theme = 'dark'; window.updateThemeUI(); }")
    label = page.locator("#theme-label").inner_text()
    assert label == "Light theme"
    page.evaluate("() => { document.documentElement.dataset.theme = 'light'; window.updateThemeUI(); }")
    label = page.locator("#theme-label").inner_text()
    assert label == "Dark theme"


def test_health_api(page, live_server):
    resp = page.request.get(f"{live_server}/api/health")
    assert resp.ok
    data = resp.json()
    assert data.get("ok") is True


def test_german_nav_label(page, live_server):
    page.goto(f"{live_server}/?lang=de")
    page.wait_for_function("() => window.getLocale() === 'de'")
    dash = page.evaluate("() => window.t('nav.dashboard')")
    assert dash == "Dashboard"


def test_i18n_api_lists_15_locales(page, live_server):
    resp = page.request.get(f"{live_server}/api/i18n/locales")
    assert resp.ok
    data = resp.json()
    assert len(data["locales"]) == 15
