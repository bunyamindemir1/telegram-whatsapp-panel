import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
import app.panel_auth as panel_auth

TEST_DB = "sqlite+aiosqlite:///:memory:"


pytestmark = pytest.mark.panel_auth


@pytest_asyncio.fixture
async def auth_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def auth_client(auth_engine, monkeypatch):
    import app.account_service as acc_module
    import app.credentials_store as cred_module
    import app.database as db_module
    import app.main as main_module
    import app.message_store as ms_module

    factory = async_sessionmaker(auth_engine, class_=AsyncSession, expire_on_commit=False)
    db_module.engine = auth_engine
    db_module.async_session = factory
    main_module.async_session = factory
    cred_module.async_session = factory
    acc_module.async_session = factory
    ms_module.async_session = factory

    monkeypatch.setattr(panel_auth, "auth_required", lambda: True)

    async def _no_admin_seed():
        return False

    monkeypatch.setattr(panel_auth, "ensure_admin_from_env", _no_admin_seed)
    monkeypatch.setattr("app.main.seed_telegram_credentials_if_missing", _no_admin_seed)

    from app.account_service import create_account
    from app.models import Platform

    await create_account(Platform.TELEGRAM.value, "Telegram 1", make_default=True)

    async with factory() as session:
        from app.credentials_store import save_telegram_credentials
        await save_telegram_credentials(12345678, "0123456789abcdef0123456789abcdef", account_id=1)

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPanelAuth:
    @pytest.mark.asyncio
    async def test_setup_and_login(self, auth_client):
        res = await auth_client.post("/api/panel/setup", json={
            "username": "admin",
            "password": "securepass1",
        })
        assert res.status_code == 200

        res = await auth_client.get("/api/stats")
        assert res.status_code == 200

        await auth_client.post("/api/panel/logout")
        res = await auth_client.get("/api/stats")
        assert res.status_code == 401

        res = await auth_client.post("/api/panel/login", json={
            "username": "admin",
            "password": "securepass1",
        })
        assert res.status_code == 200
        res = await auth_client.get("/api/stats")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_send_blocked_in_dry_run(self, auth_client, monkeypatch):
        monkeypatch.setattr("app.outbound_guard.ALLOW_OUTBOUND_MESSAGES", False)
        monkeypatch.setattr("app.main.ALLOW_OUTBOUND_MESSAGES", False)
        await auth_client.post("/api/panel/setup", json={
            "username": "testadmin",
            "password": "securepass1",
        })
        res = await auth_client.post("/api/messages/send", json={
            "platform": "telegram",
            "chat_id": "1",
            "message": "test",
        })
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_login_generic_error(self, auth_client):
        await auth_client.post("/api/panel/setup", json={
            "username": "admin",
            "password": "securepass1",
        })
        res = await auth_client.post("/api/panel/login", json={
            "username": "admin",
            "password": "wrongpass1",
        })
        assert res.status_code == 401
        assert "Hatalı" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_weak_setup_password_rejected(self, auth_client):
        res = await auth_client.post("/api/panel/setup", json={
            "username": "admin",
            "password": "short",
        })
        assert res.status_code == 422 or res.status_code == 400

    @pytest.mark.asyncio
    async def test_security_headers(self, auth_client):
        res = await auth_client.get("/api/health")
        assert res.headers.get("X-Frame-Options") == "DENY"
        assert res.headers.get("X-Content-Type-Options") == "nosniff"

    @pytest.mark.asyncio
    async def test_credentials_phone_masked(self, auth_client):
        await auth_client.post("/api/panel/setup", json={
            "username": "admin2",
            "password": "securepass1",
        })
        res = await auth_client.get("/api/credentials/telegram")
        assert res.status_code == 200
        data = res.json()
        assert "phone_masked" in data
        assert "phone" not in data
        if data["phone_masked"]:
            assert "***" in data["phone_masked"]
