"""Çoklu hesap API ve veri izolasyonu testleri."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Platform
from app.message_store import get_messages, list_conversations, save_message
from tests.test_app import _make_session_factory

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def multi_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(multi_engine):
    import app.account_service as acc_module
    import app.credentials_store as cred_module
    import app.database as db_module
    import app.main as main_module
    import app.message_store as ms_module

    factory = _make_session_factory(multi_engine)
    db_module.engine = multi_engine
    db_module.async_session = factory
    main_module.async_session = factory
    cred_module.async_session = factory
    acc_module.async_session = factory
    ms_module.async_session = factory

    with patch.object(main_module.telegram_service, "start_account_background", new_callable=AsyncMock):
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestMultiAccountAPI:
    @pytest.mark.asyncio
    async def test_create_multiple_telegram_accounts(self, api_client):
        r1 = await api_client.post("/api/accounts", json={"platform": "telegram", "label": "İş"})
        r2 = await api_client.post("/api/accounts", json={"platform": "telegram", "label": "Kişisel"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        a1, a2 = r1.json(), r2.json()
        assert a1["id"] != a2["id"]
        assert a1["platform"] == "telegram"

        listed = await api_client.get("/api/accounts?platform=telegram")
        assert listed.status_code == 200
        assert len(listed.json()) == 2

    @pytest.mark.asyncio
    async def test_create_multiple_whatsapp_accounts(self, api_client):
        r1 = await api_client.post("/api/accounts", json={"platform": "whatsapp", "label": "WA 1"})
        r2 = await api_client.post("/api/accounts", json={"platform": "whatsapp", "label": "WA 2"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] != r2.json()["id"]

    @pytest.mark.asyncio
    async def test_account_status_scoped_by_query(self, api_client):
        acc = (await api_client.post("/api/accounts", json={"platform": "telegram", "label": "TG"})).json()
        with patch("app.main.telegram_service.get_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {"connected": False, "configured": True, "account_id": acc["id"]}
            res = await api_client.get(f"/api/auth/status?account_id={acc['id']}")
            assert res.status_code == 200
            mock_status.assert_called_once_with(acc["id"])

    @pytest.mark.asyncio
    async def test_credentials_per_account(self, api_client):
        a1 = (await api_client.post("/api/accounts", json={"platform": "telegram", "label": "A1"})).json()
        a2 = (await api_client.post("/api/accounts", json={"platform": "telegram", "label": "A2"})).json()

        await api_client.put(
            f"/api/credentials/telegram?account_id={a1['id']}",
            json={"api_id": 111, "api_hash": "a" * 32, "app_name": "m", "short_name": "m", "phone": "+905551111111"},
        )
        await api_client.put(
            f"/api/credentials/telegram?account_id={a2['id']}",
            json={"api_id": 222, "api_hash": "b" * 32, "app_name": "m", "short_name": "m", "phone": "+905552222222"},
        )

        c1 = (await api_client.get(f"/api/credentials/telegram?account_id={a1['id']}")).json()
        c2 = (await api_client.get(f"/api/credentials/telegram?account_id={a2['id']}")).json()
        assert c1["api_id"] == 111
        assert c2["api_id"] == 222

    @pytest.mark.asyncio
    async def test_auth_start_uses_account_query(self, api_client):
        acc = (await api_client.post("/api/accounts", json={"platform": "telegram", "label": "Auth"})).json()
        with patch("app.main.telegram_service.start_auth", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = {"status": "code_sent", "phone": "+905551111111"}
            res = await api_client.post(
                f"/api/auth/start?account_id={acc['id']}",
                json={"phone": "+905551111111", "api_id": 1, "api_hash": "x" * 32},
            )
            assert res.status_code == 200
            mock_start.assert_called_once()
            assert mock_start.call_args.kwargs["account_id"] == acc["id"]

    @pytest.mark.asyncio
    async def test_set_default_account(self, api_client):
        a1 = (await api_client.post("/api/accounts", json={"platform": "whatsapp", "label": "One"})).json()
        a2 = (await api_client.post("/api/accounts", json={"platform": "whatsapp", "label": "Two"})).json()
        res = await api_client.post(f"/api/accounts/{a2['id']}/default")
        assert res.status_code == 200
        assert res.json()["is_default"] is True
        listed = (await api_client.get("/api/accounts?platform=whatsapp")).json()
        default = next(x for x in listed if x["is_default"])
        assert default["id"] == a2["id"]
        assert a1["id"] != default["id"]

    @pytest.mark.asyncio
    async def test_delete_account(self, api_client):
        acc = (await api_client.post("/api/accounts", json={"platform": "whatsapp", "label": "Del"})).json()
        with patch("app.main.whatsapp_service.logout", new_callable=AsyncMock):
            res = await api_client.delete(f"/api/accounts/{acc['id']}")
        assert res.status_code == 200
        listed = await api_client.get("/api/accounts?platform=whatsapp")
        assert all(x["id"] != acc["id"] for x in listed.json())

    @pytest.mark.asyncio
    async def test_create_telegram_starts_background_loop(self, api_client, multi_engine):
        import app.main as main_module

        with patch.object(main_module.telegram_service, "start_account_background", new_callable=AsyncMock) as mock_bg:
            acc = (await api_client.post("/api/accounts", json={"platform": "telegram", "label": "Loop"})).json()
            mock_bg.assert_called_once_with(acc["id"])


class TestMessageStoreAccountIsolation:
    @pytest_asyncio.fixture
    async def store_session(self, multi_engine, monkeypatch):
        factory = _make_session_factory(multi_engine)
        import app.account_service as acc_module
        import app.message_store as ms_module
        monkeypatch.setattr(acc_module, "async_session", factory)
        monkeypatch.setattr(ms_module, "async_session", factory)

    @pytest.mark.asyncio
    async def test_messages_isolated_by_account(self, store_session):
        from app.account_service import create_account

        a1 = await create_account(Platform.TELEGRAM.value, "Acc1", make_default=True)
        a2 = await create_account(Platform.TELEGRAM.value, "Acc2")
        ts = datetime.utcnow()
        chat_id = "12345"

        await save_message(
            "telegram", chat_id, "m1", "Hesap 1 mesaj", False, ts,
            chat_name="Ali", account_id=a1["id"],
        )
        await save_message(
            "telegram", chat_id, "m2", "Hesap 2 mesaj", False, ts,
            chat_name="Ali", account_id=a2["id"],
        )

        msgs1 = await get_messages("telegram", chat_id, account_id=a1["id"])
        msgs2 = await get_messages("telegram", chat_id, account_id=a2["id"])
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0]["text"] == "Hesap 1 mesaj"
        assert msgs2[0]["text"] == "Hesap 2 mesaj"

        conv1 = await list_conversations("telegram", account_id=a1["id"])
        conv2 = await list_conversations("telegram", account_id=a2["id"])
        assert len(conv1) == 1
        assert len(conv2) == 1
