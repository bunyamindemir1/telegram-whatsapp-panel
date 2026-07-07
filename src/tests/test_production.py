import pytest
from httpx import ASGITransport, AsyncClient

from app.outbound_guard import OutboundBlockedError, outbound_allowed, simulated_send_result


class TestOutboundGuard:
    def test_default_is_blocked(self, monkeypatch):
        monkeypatch.setattr("app.outbound_guard.ALLOW_OUTBOUND_MESSAGES", False)
        from app.outbound_guard import ensure_outbound_allowed, outbound_allowed
        assert outbound_allowed() is False
        with pytest.raises(OutboundBlockedError):
            ensure_outbound_allowed()

    def test_simulated_send_has_no_real_id(self):
        r = simulated_send_result("telegram", "123", "hello")
        assert r["dry_run"] is True
        assert r["simulated"] is True


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_public(self):
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "dry_run" in data
