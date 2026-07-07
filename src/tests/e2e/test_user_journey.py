"""Extended user-journey E2E against live server."""

import pytest


E2E_PASSWORD = "SecurePass9"


def login(page, live_server):
    page.goto(f"{live_server}/?lang=en")
    page.wait_for_function("() => typeof fetch === 'function'")
    page.evaluate(
        """async (c) => {
      const st = await (await fetch('/api/panel/status')).json();
      if (st.setup_required) {
        const r = await fetch('/api/panel/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ username: c.u, password: c.p }),
        });
        if (!r.ok) throw new Error('setup failed: ' + await r.text());
      }
      const login = await fetch('/api/panel/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username: c.u, password: c.p }),
      });
      if (!login.ok) throw new Error('login failed: ' + await login.text());
      localStorage.setItem('mesaj_account_setup_dismissed', '1');
      localStorage.setItem('mesaj_onboarded', '1');
    }""",
        {"u": "admin", "p": E2E_PASSWORD},
    )
    page.reload()
    page.wait_for_function(
        "() => document.getElementById('login-overlay')?.classList.contains('hidden')",
        timeout=15000,
    )
    page.wait_for_selector("#tab-dashboard", timeout=10000)


def dismiss_first_run_overlays(page):
    page.evaluate("""() => {
      localStorage.setItem('mesaj_account_setup_dismissed', '1');
      localStorage.setItem('mesaj_onboarded', '1');
      if (!document.getElementById('account-setup-overlay')?.classList.contains('hidden')) {
        if (typeof dismissAccountSetup === 'function') dismissAccountSetup();
      }
      if (!document.getElementById('onboarding-overlay')?.classList.contains('hidden')) {
        if (typeof finishOnboarding === 'function') finishOnboarding('skip');
      }
    }""")
    page.wait_for_function(
        "() => document.getElementById('account-setup-overlay')?.classList.contains('hidden')",
        timeout=5000,
    )


@pytest.mark.e2e
def test_full_user_journey(page, live_server):
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    login(page, live_server)
    dismiss_first_run_overlays(page)

    page.wait_for_timeout(800)
    assert page.locator("#stat-pending").inner_text() != ""

    page.wait_for_function("() => typeof switchTab === 'function'", timeout=10000)

    for tab in ("chats", "compose", "scheduled", "templates", "account"):
        page.evaluate(f"(t) => switchTab(t)", tab)
        page.wait_for_selector(f"#tab-{tab}.active", timeout=5000)

    page.select_option("#lang-select", "tr")
    page.wait_for_function("() => window.getLocale() === 'tr'")
    assert page.evaluate("() => window.t('nav.chats')") == "Sohbetler"

    page.select_option("#lang-select", "en")
    page.wait_for_function("() => window.getLocale() === 'en'")

    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#sidebar-toggle").click()
    page.wait_for_selector("#sidebar.open", timeout=3000)
    assert "sidebar-open" in page.evaluate("() => document.body.className")
    page.evaluate("() => closeMobileSidebar()")
    page.wait_for_selector("#sidebar:not(.open)", timeout=3000)

    page.evaluate("() => switchTab('compose')")
    page.wait_for_selector("#tab-compose.active", timeout=5000)

    page.evaluate("() => switchTab('account')")
    assert "collapsed" in page.locator("#developer-card").get_attribute("class")

    page.evaluate("() => window.toggleTheme()")
    assert page.evaluate("() => document.documentElement.dataset.theme") in ("light", "dark")

    wrong = page.evaluate(
        """async () => {
      const r = await fetch('/api/panel/logout', { method: 'POST', credentials: 'include' });
      return r.ok;
    }"""
    )
    assert wrong is True

    js_errors = [e for e in console_errors if "favicon" not in e.lower()]
    assert not js_errors, f"Console errors: {js_errors[:5]}"
