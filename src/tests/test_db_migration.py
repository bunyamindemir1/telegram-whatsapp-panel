"""Veritabanı migration testleri — çoklu hesap unique constraint."""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import init_db
from app.models import Base

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def legacy_engine():
    """Eski şema: platform+chat_id unique (account_id sonradan eklenmiş)."""
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform VARCHAR(32) NOT NULL,
                chat_id VARCHAR(128) NOT NULL,
                message_id VARCHAR(64) NOT NULL,
                from_me BOOLEAN NOT NULL,
                sender_name VARCHAR(255),
                text TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                created_at DATETIME NOT NULL,
                account_id INTEGER,
                CONSTRAINT uq_msg_platform_chat_mid UNIQUE (platform, chat_id, message_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform VARCHAR(32) NOT NULL,
                chat_id VARCHAR(128) NOT NULL,
                chat_name VARCHAR(255) NOT NULL,
                chat_type VARCHAR(32) NOT NULL,
                last_message TEXT,
                last_message_at DATETIME,
                unread_count INTEGER NOT NULL,
                updated_at DATETIME NOT NULL,
                account_id INTEGER,
                CONSTRAINT uq_conv_platform_chat UNIQUE (platform, chat_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE platform_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                label TEXT NOT NULL,
                display_name TEXT,
                phone_masked TEXT,
                external_id TEXT,
                status TEXT DEFAULT 'disconnected',
                is_default INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                credentials_key TEXT,
                session_name TEXT,
                bridge_id TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
    yield engine
    await engine.dispose()


class TestDbMigration:
    @pytest.mark.asyncio
    async def test_migrates_legacy_unique_constraints(self, legacy_engine, monkeypatch):
        import app.database as db_mod
        import app.account_service as acc_mod

        factory = async_sessionmaker(legacy_engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(db_mod, "engine", legacy_engine)
        monkeypatch.setattr(db_mod, "async_session", factory)
        monkeypatch.setattr(acc_mod, "async_session", factory)

        await init_db()

        async with legacy_engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE type='table' AND name='chat_messages'")
                )
            ).fetchone()
        ddl = row[0] or ""
        assert "uq_msg_account_chat_mid" in ddl
        assert "uq_msg_platform_chat_mid" not in ddl
