import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, SecureConfig
from app.credentials_store import (
    get_telegram_credentials,
    get_telegram_credentials_public,
    save_telegram_credentials,
)
from app.secrets import decrypt_text, encrypt_text, mask_secret

FAKE_API_ID = 12345678
FAKE_API_HASH = "0123456789abcdef0123456789abcdef"
TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def creds_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def patch_cred_session(creds_engine, monkeypatch):
    factory = async_sessionmaker(creds_engine, class_=AsyncSession, expire_on_commit=False)
    import app.credentials_store as cs
    monkeypatch.setattr(cs, "async_session", factory)


class TestSecrets:
    def test_encrypt_decrypt_roundtrip(self):
        plain = FAKE_API_HASH
        assert decrypt_text(encrypt_text(plain)) == plain

    def test_mask_secret(self):
        masked = mask_secret(FAKE_API_HASH)
        assert masked.startswith("0123")
        assert masked.endswith("cdef")
        assert "*" in masked


class TestCredentialsStore:
    @pytest.mark.asyncio
    async def test_save_and_load_encrypted(self, patch_cred_session):
        public = await save_telegram_credentials(
            FAKE_API_ID,
            FAKE_API_HASH,
            app_name="mesaj",
            short_name="mesaj",
            phone="+905551234567",
        )
        assert public["configured"] is True
        assert public["api_id"] == FAKE_API_ID
        assert "0123" in public["api_hash_masked"]
        assert "api_hash" not in public

        creds = await get_telegram_credentials()
        assert creds is not None
        assert creds.api_hash == FAKE_API_HASH

    @pytest.mark.asyncio
    async def test_db_value_is_encrypted(self, patch_cred_session, creds_engine):
        await save_telegram_credentials(1, "a" * 32)
        async with creds_engine.connect() as conn:
            from sqlalchemy import text
            row = (await conn.execute(text("SELECT value_encrypted FROM secure_config WHERE key='telegram_1'"))).fetchone()
        assert row is not None
        assert row[0] != "a" * 32
        assert "api_hash" not in row[0]

    @pytest.mark.asyncio
    async def test_public_endpoint_shape(self, patch_cred_session):
        await save_telegram_credentials(FAKE_API_ID, FAKE_API_HASH)
        public = await get_telegram_credentials_public()
        assert public["storage"] == "encrypted_db"
        assert "api_hash_masked" in public
