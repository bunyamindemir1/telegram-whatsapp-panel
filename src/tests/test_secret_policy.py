"""Production secret policy tests."""

import pytest

from app.panel_auth import validate_production_settings
from app.secret_policy import (
    is_weak_admin_password,
    is_weak_bridge_secret,
    is_weak_session_secret,
    verify_bridge_token,
)


class TestSecretPolicy:
    def test_weak_bridge_defaults(self):
        assert is_weak_bridge_secret("mesaj-bridge-local-secret")
        assert is_weak_bridge_secret("degistirin-kopru-anahtari")
        assert not is_weak_bridge_secret("xK9mP2nQ7vR4sT8uW1yZ3aB6cD0eF5g")

    def test_weak_session_defaults(self):
        assert is_weak_session_secret("degistirin-guclu-rastgele-32-karakter")
        assert is_weak_session_secret("short")
        assert not is_weak_session_secret("a" * 32)

    def test_weak_admin_passwords(self):
        assert is_weak_admin_password("degistirin-guclu-sifre-min-8")
        assert is_weak_admin_password("password1")
        assert not is_weak_admin_password("SecurePass9")

    def test_timing_safe_bridge_token(self):
        assert verify_bridge_token("secret-value-12345", "secret-value-12345")
        assert not verify_bridge_token("secret-value-12345", "secret-value-12346")
        assert not verify_bridge_token("", "secret")


class TestProductionValidation:
    def test_rejects_placeholder_secrets(self, monkeypatch):
        monkeypatch.setattr("app.panel_auth.ENV", "production")
        monkeypatch.setattr("app.panel_auth.SESSION_SECRET", "degistirin-guclu-rastgele-32-karakter")
        monkeypatch.setattr("app.panel_auth.BRIDGE_SECRET", "degistirin-kopru-anahtari")
        monkeypatch.setattr("app.panel_auth.PANEL_ADMIN_PASSWORD", "SecurePass9")
        monkeypatch.setattr("app.panel_auth.PANEL_PASSWORD", "")

        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            validate_production_settings()

    def test_accepts_strong_secrets(self, monkeypatch):
        monkeypatch.setattr("app.panel_auth.ENV", "production")
        monkeypatch.setattr("app.panel_auth.SESSION_SECRET", "a" * 32)
        monkeypatch.setattr("app.panel_auth.BRIDGE_SECRET", "b" * 32)
        monkeypatch.setattr("app.panel_auth.PANEL_ADMIN_PASSWORD", "SecurePass9")
        monkeypatch.setattr("app.panel_auth.PANEL_PASSWORD", "")
        validate_production_settings()
