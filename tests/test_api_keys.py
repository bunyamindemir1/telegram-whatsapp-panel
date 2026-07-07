import pytest
from httpx import ASGITransport, AsyncClient

from app.api_keys import create_api_key, revoke_api_key, verify_api_key
from app.database import init_db


@pytest.mark.asyncio
async def test_api_key_lifecycle():
    await init_db()
    row, raw = await create_api_key("test-integration")
    assert raw.startswith("mp_")
    assert row.key_prefix == raw[:12]

    verified = await verify_api_key(raw)
    assert verified is not None
    assert verified.id == row.id

    assert await verify_api_key("mp_invalid_key") is None

    assert await revoke_api_key(row.id) is True
    assert await verify_api_key(raw) is None


@pytest.mark.asyncio
async def test_v1_health_public():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["version"] == "1"


@pytest.mark.asyncio
async def test_v1_requires_auth(monkeypatch):
    from fastapi import HTTPException

    async def _deny(_request):
        raise HTTPException(status_code=401, detail="Giriş gerekli")

    monkeypatch.setattr("app.auth_deps.check_panel_auth", _deny)

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/accounts")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_v1_bearer_auth(monkeypatch):
    monkeypatch.setattr("app.panel_auth.auth_required", lambda: True)
    await init_db()
    _, raw = await create_api_key("bearer-test")

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/accounts",
            headers={"Authorization": f"Bearer {raw}"},
        )
    assert res.status_code == 200
    data = res.json()
    assert "telegram" in data
    assert "whatsapp" in data
