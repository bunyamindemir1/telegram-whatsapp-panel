import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Platform
from app.account_service import create_account, list_accounts, set_default_account

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def account_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def account_session(account_engine, monkeypatch):
    factory = async_sessionmaker(account_engine, class_=AsyncSession, expire_on_commit=False)
    import app.account_service as acc_mod
    import app.database as db_mod
    monkeypatch.setattr(acc_mod, "async_session", factory)
    monkeypatch.setattr(db_mod, "async_session", factory)


class TestAccountService:
    @pytest.mark.asyncio
    async def test_create_and_list_accounts(self, account_session):
        a1 = await create_account(Platform.TELEGRAM.value, "İş")
        a2 = await create_account(Platform.TELEGRAM.value, "Kişisel")
        assert a1["id"] != a2["id"]
        listed = await list_accounts(Platform.TELEGRAM.value)
        assert len(listed) == 2

    @pytest.mark.asyncio
    async def test_set_default_account(self, account_session):
        a1 = await create_account(Platform.WHATSAPP.value, "WA 1", make_default=True)
        a2 = await create_account(Platform.WHATSAPP.value, "WA 2")
        await set_default_account(a2["id"])
        listed = await list_accounts(Platform.WHATSAPP.value)
        default = next(x for x in listed if x["is_default"])
        assert default["id"] == a2["id"]

    @pytest.mark.asyncio
    async def test_first_whatsapp_uses_bridge_id_one(self, account_session):
        a1 = await create_account(Platform.WHATSAPP.value, "WA 1", make_default=True)
        a2 = await create_account(Platform.WHATSAPP.value, "WA 2")
        from app.account_service import get_bridge_id, normalize_whatsapp_bridge_ids

        await normalize_whatsapp_bridge_ids()
        assert await get_bridge_id(a1["id"]) == "1"
        assert await get_bridge_id(a2["id"]) == str(a2["id"])
