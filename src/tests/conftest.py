"""Shared pytest fixtures for the test suite."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

TEST_DB = "sqlite+aiosqlite:///:memory:"
FAKE_API_ID = 12345678
FAKE_API_HASH = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def disable_panel_auth_for_unit_tests(monkeypatch, request):
    """Most tests run without panel login — except @pytest.mark.panel_auth."""
    if request.node.get_closest_marker("panel_auth"):
        return

    async def _allow(_request):
        return None

    monkeypatch.setattr("app.panel_auth.auth_required", lambda: False)
    monkeypatch.setattr("app.panel_auth.check_panel_auth", _allow)


def pytest_configure(config):
    config.addinivalue_line("markers", "panel_auth: panel authentication tests")


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def make_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def panel_client(test_engine, monkeypatch):
    """FastAPI test client with in-memory DB and panel auth disabled."""
    import app.account_service as acs
    import app.activity_log as al
    import app.auto_reply_service as ars
    import app.credentials_store as cred_module
    import app.database as db_module
    import app.follow_up_service as fus
    import app.main as main_module
    import app.message_store as ms

    factory = make_session_factory(test_engine)
    for mod in (db_module, main_module, cred_module, ms, acs, ars, fus, al):
        mod.async_session = factory

    monkeypatch.setenv("PANEL_PASSWORD", "")

    async with factory() as session:
        from app.credentials_store import save_telegram_credentials
        await save_telegram_credentials(FAKE_API_ID, FAKE_API_HASH)

    from app.account_service import ensure_default_accounts
    await ensure_default_accounts()

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
