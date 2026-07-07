import pytest


@pytest.fixture(autouse=True)
def disable_panel_auth_for_unit_tests(monkeypatch, request):
    """Çoğu testte panel girişi kapalı — panel auth testleri hariç."""
    if request.node.get_closest_marker("panel_auth"):
        return

    async def _allow(_request):
        return None

    monkeypatch.setattr("app.panel_auth.auth_required", lambda: False)
    monkeypatch.setattr("app.panel_auth.check_panel_auth", _allow)


def pytest_configure(config):
    config.addinivalue_line("markers", "panel_auth: panel authentication tests")
