import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, JobStatus, RepeatType, ScheduledMessage
from app.scheduler_service import compute_next_run
from app.utils.datetime_utils import ensure_future, to_utc_naive, utc_now

FAKE_API_ID = 12345678
FAKE_API_HASH = "0123456789abcdef0123456789abcdef"
TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def sample_job():
    return ScheduledMessage(
        id=1,
        chat_id="123",
        chat_name="Test",
        chat_type="user",
        message_text="Hello",
        scheduled_at=datetime(2026, 7, 7, 9, 0, 0),
        repeat_type=RepeatType.DAILY.value,
        is_active=True,
        status=JobStatus.PENDING.value,
    )


class TestDateTimeUtils:
    def test_to_utc_naive_from_aware(self):
        aware = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))
        result = to_utc_naive(aware)
        assert result.tzinfo is None
        assert result.hour == 9

    def test_to_utc_naive_from_naive(self):
        naive = datetime(2026, 7, 7, 12, 0, 0)
        assert to_utc_naive(naive) == naive

    def test_ensure_future_pushes_past_dates(self):
        past = utc_now() - timedelta(hours=1)
        result = ensure_future(past)
        assert result > utc_now()


class TestComputeNextRun:
    def test_none_repeat_returns_none(self, sample_job):
        sample_job.repeat_type = RepeatType.NONE.value
        assert compute_next_run(sample_job) is None

    def test_hourly_adds_one_hour(self, sample_job):
        sample_job.repeat_type = RepeatType.HOURLY.value
        base = datetime(2026, 7, 7, 10, 0, 0)
        result = compute_next_run(sample_job, base)
        assert result == datetime(2026, 7, 7, 11, 0, 0)

    def test_daily_preserves_time(self, sample_job):
        sample_job.scheduled_at = datetime(2026, 7, 7, 9, 30, 0)
        sample_job.repeat_type = RepeatType.DAILY.value
        base = datetime(2026, 7, 7, 10, 0, 0)
        result = compute_next_run(sample_job, base)
        assert result.hour == 9
        assert result.minute == 30

    def test_custom_interval(self, sample_job):
        sample_job.repeat_type = RepeatType.CUSTOM.value
        sample_job.repeat_interval_minutes = 15
        base = datetime(2026, 7, 7, 10, 0, 0)
        result = compute_next_run(sample_job, base)
        assert result == datetime(2026, 7, 7, 10, 15, 0)


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def _make_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class TestSchedulerExecution:
    @pytest.mark.asyncio
    async def test_execute_job_sends_and_marks_sent(self, test_engine):
        from app.scheduler_service import _execute_job

        factory = _make_session_factory(test_engine)

        async with factory() as session:
            job = ScheduledMessage(
                chat_id="999",
                chat_name="Test User",
                message_text="Test message",
                scheduled_at=utc_now(),
                repeat_type=RepeatType.NONE.value,
                status=JobStatus.PENDING.value,
                is_active=True,
                next_run_at=utc_now(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        @asynccontextmanager
        async def mock_session():
            async with factory() as s:
                yield s

        with patch("app.scheduler_service.async_session", mock_session):
            with patch("app.scheduler_service.send_platform_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {"message_id": 1}
                await _execute_job(job_id)

        async with factory() as session:
            job = await session.get(ScheduledMessage, job_id)
            assert job.status == JobStatus.SENT.value
            assert job.is_active is False
            assert job.send_count == 1
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_recurring_job_stays_active(self, test_engine):
        from app.scheduler_service import _execute_job, scheduler

        if not scheduler.running:
            scheduler.start()

        factory = _make_session_factory(test_engine)

        async with factory() as session:
            job = ScheduledMessage(
                chat_id="999",
                chat_name="Group",
                message_text="Recurring",
                scheduled_at=datetime(2026, 7, 7, 9, 0, 0),
                repeat_type=RepeatType.HOURLY.value,
                status=JobStatus.PENDING.value,
                is_active=True,
                next_run_at=utc_now(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        @asynccontextmanager
        async def mock_session():
            async with factory() as s:
                yield s

        with patch("app.scheduler_service.async_session", mock_session):
            with patch("app.scheduler_service.send_platform_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = {"message_id": 1}
                await _execute_job(job_id)

        async with factory() as session:
            job = await session.get(ScheduledMessage, job_id)
            assert job.send_count == 1
            assert job.status == JobStatus.PENDING.value
            assert job.is_active is True
            assert job.next_run_at is not None


class TestAPI:
    @pytest_asyncio.fixture
    async def client(self, test_engine):
        import app.account_service as acs
        import app.activity_log as al
        import app.auto_reply_service as ars
        import app.credentials_store as cred_module
        import app.database as db_module
        import app.follow_up_service as fus
        import app.main as main_module
        import app.message_store as ms

        factory = _make_session_factory(test_engine)
        db_module.engine = test_engine
        for mod in (db_module, main_module, cred_module, ms, acs, ars, fus, al):
            mod.async_session = factory

        async with factory() as session:
            from app.credentials_store import save_telegram_credentials
            await save_telegram_credentials(FAKE_API_ID, FAKE_API_HASH)

        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_panel_status(self, client):
        res = await client.get("/api/panel/status")
        assert res.status_code == 200
        data = res.json()
        assert "authenticated" in data
        assert "dry_run" in data
        assert "needs_account_setup" in data
        assert "telegram_connected" in data
        assert "whatsapp_connected" in data

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, client):
        res = await client.get("/api/stats")
        assert res.status_code == 200
        data = res.json()
        assert "pending" in data
        assert "scheduler" in data

    @pytest.mark.asyncio
    async def test_create_scheduled_rejects_past_date(self, client):
        past = (utc_now() - timedelta(hours=1)).isoformat() + "Z"
        res = await client.post("/api/scheduled", json={
            "chat_id": "1",
            "chat_name": "Test",
            "message_text": "Hi",
            "scheduled_at": past,
            "repeat_type": "none",
        })
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_create_scheduled_accepts_future(self, client):
        future = (utc_now() + timedelta(hours=1)).isoformat() + "Z"
        with patch("app.main.schedule_message", new_callable=AsyncMock):
            res = await client.post("/api/scheduled", json={
                "chat_id": "1",
                "chat_name": "Test",
                "message_text": "Hi",
                "scheduled_at": future,
                "repeat_type": "none",
            })
        assert res.status_code == 200
        assert "id" in res.json()

    @pytest.mark.asyncio
    async def test_templates_crud(self, client):
        res = await client.post("/api/templates", json={
            "title": "Test Template",
            "message_text": "Hello world",
        })
        assert res.status_code == 200
        tid = res.json()["id"]

        res = await client.get("/api/templates")
        assert res.status_code == 200
        assert len(res.json()) == 1

        res = await client.delete(f"/api/templates/{tid}")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_homepage_loads(self, client):
        res = await client.get("/")
        assert res.status_code == 200
        assert "brand.name" in res.text or "Message Panel" in res.text or "Mesaj Paneli" in res.text
        assert "lang-select" in res.text
        assert "mobile-bottom-nav" in res.text
        assert "viewport-fit=cover" in res.text

    @pytest.mark.asyncio
    async def test_config_includes_credentials_meta(self, client):
        res = await client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "telegram_credentials" in data
        assert data["telegram_credentials"]["configured"] is True
        assert "api_hash_masked" in data["telegram_credentials"]
        assert "api_hash" not in data["telegram_credentials"]

    @pytest.mark.asyncio
    async def test_credentials_endpoint_masked(self, client):
        res = await client.get("/api/credentials/telegram")
        assert res.status_code == 200
        data = res.json()
        assert data["api_id"] == FAKE_API_ID
        assert "api_hash_masked" in data
        assert "api_hash" not in data
        assert data["storage"] == "encrypted_db"

    @pytest.mark.asyncio
    async def test_internal_event_requires_bridge_token(self, client):
        res = await client.post("/api/internal/event", json={
            "type": "message",
            "data": {
                "chat_id": "x@s.whatsapp.net",
                "message_id": "1",
                "text": "fake",
            },
        })
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_create_scheduled_rejects_invalid_platform(self, client):
        future = (utc_now() + timedelta(hours=1)).isoformat() + "Z"
        res = await client.post("/api/scheduled", json={
            "platform": "invalid",
            "chat_id": "1",
            "chat_name": "Test",
            "message_text": "Hi",
            "scheduled_at": future,
            "repeat_type": "none",
        })
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_create_random_daily_scheduled(self, client):
        with patch("app.main.schedule_message", new_callable=AsyncMock):
            res = await client.post("/api/scheduled", json={
                "platform": "telegram",
                "chat_id": "1",
                "chat_name": "İş Grubu",
                "message_text": "Günaydın",
                "repeat_type": "random_daily",
                "window_start_time": "07:00",
                "window_end_time": "07:30",
            })
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert data["repeat_type"] == "random_daily"
        assert data["scheduled_at_tr"]
        assert data["window_label"] == "07:00–07:30"

    @pytest.mark.asyncio
    async def test_create_random_daily_requires_window(self, client):
        res = await client.post("/api/scheduled", json={
            "chat_id": "1",
            "chat_name": "Test",
            "message_text": "Hi",
            "repeat_type": "random_daily",
        })
        assert res.status_code == 400

    def test_from_client_datetime_istanbul(self):
        from app.utils.datetime_utils import from_client_datetime, utc_now
        # 09:00 Istanbul = 06:00 UTC (summer time UTC+3)
        dt = datetime(2026, 7, 7, 9, 0, 0)  # naive, treated as Istanbul
        utc = from_client_datetime(dt)
        assert utc.hour == 6
