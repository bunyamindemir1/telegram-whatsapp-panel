from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, ChatMessage, Conversation
from app.message_store import get_messages, list_conversations, save_message

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def store_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def patch_store_session(store_engine, monkeypatch):
    factory = async_sessionmaker(store_engine, class_=AsyncSession, expire_on_commit=False)
    import app.account_service as acc_mod
    import app.message_store as ms
    monkeypatch.setattr(acc_mod, "async_session", factory)
    monkeypatch.setattr(ms, "async_session", factory)


class TestMessageStore:
    @pytest.mark.asyncio
    async def test_save_and_get_messages(self, patch_store_session):
        ts = datetime(2026, 7, 7, 12, 0, 0)
        saved = await save_message(
            platform="telegram",
            chat_id="123",
            message_id="1",
            text="naber",
            from_me=True,
            timestamp=ts,
            chat_name="Test User",
            chat_type="user",
        )
        assert saved["text"] == "naber"
        msgs = await get_messages("telegram", "123")
        assert len(msgs) == 1
        assert msgs[0]["from_me"] is True

    @pytest.mark.asyncio
    async def test_list_conversations(self, patch_store_session):
        ts = datetime.utcnow()
        await save_message("telegram", "1", "m1", "Merhaba", False, ts, chat_name="Ali", chat_type="user")
        await save_message("whatsapp", "jid@s.whatsapp.net", "w1", "Selam", True, ts, chat_name="Veli", chat_type="private")
        tg = await list_conversations("telegram")
        assert len(tg) == 1
        assert tg[0]["name"] == "Ali"
        all_conv = await list_conversations()
        assert len(all_conv) == 2

    @pytest.mark.asyncio
    async def test_upsert_message(self, patch_store_session):
        ts = datetime.utcnow()
        await save_message("telegram", "99", "1", "v1", True, ts)
        await save_message("telegram", "99", "1", "v2", True, ts)
        msgs = await get_messages("telegram", "99")
        assert len(msgs) == 1
        assert msgs[0]["text"] == "v2"

    @pytest.mark.asyncio
    async def test_unread_increments_on_incoming(self, patch_store_session):
        ts = datetime.utcnow()
        await save_message("telegram", "1", "m1", "Merhaba", False, ts, chat_name="Ali")
        await save_message("telegram", "1", "m2", "Naber", False, ts, chat_name="Ali")
        convs = await list_conversations("telegram")
        assert convs[0]["unread_count"] == 2
