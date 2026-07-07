"""Sohbet listeleme, mesaj depolama ve hesap izolasyonu testleri."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import BRIDGE_SECRET
from app.models import Base, Platform
from app.account_service import (
    create_account,
    resolve_whatsapp_panel_account,
)
from app.message_store import (
    get_messages,
    list_conversations,
    save_message,
    search_messages,
)
from tests.test_app import _make_session_factory

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def scoped_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def scoped_session(scoped_engine, monkeypatch):
    factory = _make_session_factory(scoped_engine)
    import app.account_service as acc_module
    import app.message_store as ms_module
    monkeypatch.setattr(acc_module, "async_session", factory)
    monkeypatch.setattr(ms_module, "async_session", factory)


@pytest_asyncio.fixture
async def api_client(scoped_engine):
    import app.account_service as acc_module
    import app.credentials_store as cred_module
    import app.database as db_module
    import app.main as main_module
    import app.message_store as ms_module

    factory = _make_session_factory(scoped_engine)
    for mod in (db_module, main_module, cred_module, acc_module, ms_module):
        mod.async_session = factory

    with patch.object(main_module.telegram_service, "start_account_background", new_callable=AsyncMock):
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestBridgePanelAccountMapping:
    @pytest.mark.asyncio
    async def test_bridge_id_one_maps_to_whatsapp_panel_account(self, scoped_session):
        await create_account(Platform.TELEGRAM.value, "TG", make_default=True)
        wa = await create_account(Platform.WHATSAPP.value, "WA", make_default=True)
        panel_id = await resolve_whatsapp_panel_account("1")
        assert panel_id == wa["id"]
        assert panel_id != 1

    @pytest.mark.asyncio
    async def test_second_whatsapp_maps_by_bridge_id(self, scoped_session):
        await create_account(Platform.WHATSAPP.value, "WA 1", make_default=True)
        wa2 = await create_account(Platform.WHATSAPP.value, "WA 2")
        assert await resolve_whatsapp_panel_account("1") != wa2["id"]
        assert await resolve_whatsapp_panel_account(str(wa2["id"])) == wa2["id"]


class TestConversationIsolation:
    @pytest.mark.asyncio
    async def test_same_chat_id_different_accounts(self, scoped_session):
        tg1 = await create_account(Platform.TELEGRAM.value, "A1", make_default=True)
        tg2 = await create_account(Platform.TELEGRAM.value, "A2")
        ts = datetime.utcnow()
        chat_id = "999888"

        await save_message(
            "telegram", chat_id, "m1", "Hesap 1", False, ts,
            chat_name="Ali", account_id=tg1["id"],
        )
        await save_message(
            "telegram", chat_id, "m2", "Hesap 2", False, ts,
            chat_name="Veli", account_id=tg2["id"],
        )

        conv1 = await list_conversations("telegram", account_id=tg1["id"])
        conv2 = await list_conversations("telegram", account_id=tg2["id"])
        assert len(conv1) == 1
        assert len(conv2) == 1
        assert conv1[0]["name"] == "Ali"
        assert conv2[0]["name"] == "Veli"
        assert conv1[0]["id"] == conv2[0]["id"] == chat_id

    @pytest.mark.asyncio
    async def test_list_conversations_does_not_leak_without_platform_filter(self, scoped_session):
        tg = await create_account(Platform.TELEGRAM.value, "TG", make_default=True)
        wa = await create_account(Platform.WHATSAPP.value, "WA", make_default=True)
        ts = datetime.utcnow()
        await save_message("telegram", "1", "m1", "tg msg", False, ts, account_id=tg["id"])
        await save_message("whatsapp", "jid@s.whatsapp.net", "w1", "wa msg", False, ts, account_id=wa["id"])

        tg_only = await list_conversations("telegram", account_id=tg["id"])
        wa_only = await list_conversations("whatsapp", account_id=wa["id"])
        assert len(tg_only) == 1
        assert len(wa_only) == 1
        assert tg_only[0]["platform"] == "telegram"
        assert wa_only[0]["platform"] == "whatsapp"

    @pytest.mark.asyncio
    async def test_search_scoped_to_account(self, scoped_session):
        tg1 = await create_account(Platform.TELEGRAM.value, "A1", make_default=True)
        tg2 = await create_account(Platform.TELEGRAM.value, "A2")
        ts = datetime.utcnow()
        await save_message("telegram", "1", "m1", "unique-alpha-text", False, ts, account_id=tg1["id"])
        await save_message("telegram", "2", "m2", "unique-beta-text", False, ts, account_id=tg2["id"])

        r1 = await search_messages("unique-alpha", platform="telegram", account_id=tg1["id"])
        r2 = await search_messages("unique-alpha", platform="telegram", account_id=tg2["id"])
        assert len(r1) == 1
        assert len(r2) == 0

    @pytest.mark.asyncio
    async def test_save_message_rejects_wrong_platform_account(self, scoped_session):
        tg = await create_account(Platform.TELEGRAM.value, "TG", make_default=True)
        with pytest.raises(ValueError, match="Geçersiz hesap"):
            await save_message(
                "whatsapp", "jid@s.whatsapp.net", "m1", "x", False, datetime.utcnow(),
                account_id=tg["id"],
            )


class TestWhatsAppInternalSync:
    @pytest.mark.asyncio
    async def test_sync_whatsapp_stores_under_panel_account_not_bridge_id(self, api_client, scoped_session):
        await create_account(Platform.TELEGRAM.value, "TG", make_default=True)
        wa = await create_account(Platform.WHATSAPP.value, "WA", make_default=True)

        payload = {
            "account_id": "1",
            "chats": [{"jid": "905551111111@s.whatsapp.net", "name": "Test", "type": "private"}],
            "messages": [{
                "id": "msg1",
                "jid": "905551111111@s.whatsapp.net",
                "from_me": False,
                "text": "Merhaba bridge",
                "timestamp": 1700000000,
                "push_name": "Test",
            }],
        }
        res = await api_client.post(
            "/api/internal/sync-whatsapp",
            json=payload,
            headers={"X-Bridge-Token": BRIDGE_SECRET},
        )
        assert res.status_code == 200
        assert res.json()["synced"] == 1

        msgs = await get_messages("whatsapp", "905551111111@s.whatsapp.net", account_id=wa["id"])
        assert len(msgs) == 1
        assert msgs[0]["text"] == "Merhaba bridge"

        with pytest.raises(ValueError, match="Geçersiz hesap"):
            await get_messages("whatsapp", "905551111111@s.whatsapp.net", account_id=1)


class TestChatListAPI:
    @pytest.mark.asyncio
    async def test_conversations_scoped_per_account(self, api_client, scoped_session):
        tg1 = await create_account(Platform.TELEGRAM.value, "A1", make_default=True)
        tg2 = await create_account(Platform.TELEGRAM.value, "A2")
        ts = datetime.utcnow()
        await save_message("telegram", "111", "m1", "msg1", False, ts, chat_name="Chat A1", account_id=tg1["id"])
        await save_message("telegram", "222", "m2", "msg2", False, ts, chat_name="Chat A2", account_id=tg2["id"])

        r1 = await api_client.get(f"/api/conversations?platform=telegram&account_id={tg1['id']}")
        r2 = await api_client.get(f"/api/conversations?platform=telegram&account_id={tg2['id']}")
        assert r1.status_code == 200
        assert r2.status_code == 200
        ids1 = {c["id"] for c in r1.json()}
        ids2 = {c["id"] for c in r2.json()}
        assert ids1 == {"111"}
        assert ids2 == {"222"}

    @pytest.mark.asyncio
    async def test_chats_endpoint_uses_account_id(self, api_client, scoped_session):
        tg1 = await create_account(Platform.TELEGRAM.value, "A1", make_default=True)
        tg2 = await create_account(Platform.TELEGRAM.value, "A2")

        with patch("app.main.telegram_service.list_chats", new_callable=AsyncMock) as mock_list:
            async def side_effect(account_id=1, refresh=False):
                if account_id == tg1["id"]:
                    return [{"id": "live-1", "name": "Live 1", "type": "user"}]
                return [{"id": "live-2", "name": "Live 2", "type": "user"}]

            mock_list.side_effect = side_effect
            r1 = await api_client.get(f"/api/chats?platform=telegram&account_id={tg1['id']}")
            r2 = await api_client.get(f"/api/chats?platform=telegram&account_id={tg2['id']}")

        assert r1.json()[0]["id"] == "live-1"
        assert r2.json()[0]["id"] == "live-2"

    @pytest.mark.asyncio
    async def test_sync_all_whatsapp_uses_account_id(self, api_client, scoped_session):
        wa1 = await create_account(Platform.WHATSAPP.value, "WA1", make_default=True)
        wa2 = await create_account(Platform.WHATSAPP.value, "WA2")

        export_data = {
            "chats": [{"jid": "905551111111@s.whatsapp.net", "name": "X", "type": "private"}],
            "messages": [{
                "id": "bulk1",
                "jid": "905551111111@s.whatsapp.net",
                "from_me": False,
                "text": "bulk sync",
                "timestamp": 1700000001,
            }],
        }

        with patch("app.main.whatsapp_service.export_all", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = {
                **export_data,
                "total_messages": 1,
                "offset": 0,
                "count": 1,
                "has_more": False,
            }
            res = await api_client.post(f"/api/messages/sync-all/whatsapp?account_id={wa2['id']}")
            assert res.status_code == 200
            mock_export.assert_called_once_with(wa2["id"], offset=0, limit=3000)

        msgs = await get_messages("whatsapp", "905551111111@s.whatsapp.net", account_id=wa2["id"])
        assert len(msgs) == 1
        assert msgs[0]["text"] == "bulk sync"
        assert len(await get_messages("whatsapp", "905551111111@s.whatsapp.net", account_id=wa1["id"])) == 0

    @pytest.mark.asyncio
    async def test_custom_label_not_overwritten_by_sync(self, scoped_session):
        from app.message_store import update_conversation_label

        tg = await create_account(Platform.TELEGRAM.value, "A1", make_default=True)
        ts = datetime.utcnow()
        await save_message("telegram", "111", "m1", "msg", False, ts, chat_name="905551111111", account_id=tg["id"])
        await update_conversation_label("telegram", "111", "Annem", account_id=tg["id"])
        await save_message("telegram", "111", "m2", "msg2", False, ts, chat_name="905551111111", account_id=tg["id"])
        convs = await list_conversations("telegram", account_id=tg["id"])
        assert convs[0]["name"] == "Annem"

    @pytest.mark.asyncio
    async def test_send_message_uses_query_account_id(self, api_client, scoped_session):
        tg2 = await create_account(Platform.TELEGRAM.value, "A2")
        with patch("app.main.send_platform_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"message_id": 1}
            res = await api_client.post(
                f"/api/messages/send?account_id={tg2['id']}",
                json={
                    "platform": "telegram",
                    "chat_id": "123",
                    "message": "test",
                    "chat_name": "Test",
                    "chat_type": "user",
                },
            )
            assert res.status_code == 200
            mock_send.assert_called_once()
            assert mock_send.call_args.kwargs["account_id"] == tg2["id"]
