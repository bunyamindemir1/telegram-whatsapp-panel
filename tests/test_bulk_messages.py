"""Toplu mesaj kaydı testleri."""
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Platform
from app.account_service import create_account
from app.message_store import get_messages, list_conversations, save_messages_bulk

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def bulk_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def bulk_session(bulk_engine, monkeypatch):
    factory = async_sessionmaker(bulk_engine, class_=AsyncSession, expire_on_commit=False)
    import app.account_service as acc_mod
    import app.message_store as ms_mod
    monkeypatch.setattr(acc_mod, "async_session", factory)
    monkeypatch.setattr(ms_mod, "async_session", factory)


class TestBulkMessageSave:
    @pytest.mark.asyncio
    async def test_bulk_save_many_messages_fast(self, bulk_session):
        wa = await create_account(Platform.WHATSAPP.value, "WA", make_default=True)
        ts = datetime.utcnow()
        messages = []
        for i in range(250):
            messages.append({
                "platform": "whatsapp",
                "account_id": wa["id"],
                "chat_id": "905353884340@s.whatsapp.net",
                "message_id": str(i),
                "text": f"mesaj {i}",
                "from_me": i % 2 == 0,
                "timestamp": ts,
                "chat_name": "Annem",
                "chat_type": "private",
            })
        count = await save_messages_bulk(messages, chunk_size=100)
        assert count == 250
        stored = await get_messages("whatsapp", "905353884340@s.whatsapp.net", limit=300, account_id=wa["id"])
        assert len(stored) == 250
        convs = await list_conversations("whatsapp", account_id=wa["id"])
        assert len(convs) == 1
        assert convs[0]["name"] == "Annem"
