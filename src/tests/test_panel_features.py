"""Panel feature integration tests."""

from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_session_factory
from app.models import JobStatus, Platform, RepeatType, ScheduledMessage


@pytest.mark.asyncio
async def test_conversation_pin_notes_tags(panel_client):
    res = await panel_client.patch(
        "/api/conversations/telegram/123/meta?account_id=1",
        json={"is_pinned": True, "notes": "VIP customer", "tags": ["work", "vip"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_pinned"] is True
    assert data["notes"] == "VIP customer"
    assert "work" in data["tags"]

    listed = await panel_client.get("/api/conversations?platform=telegram&account_id=1")
    assert listed.status_code == 200
    conv = next((c for c in listed.json() if str(c.get("id")) == "123"), None)
    if conv:
        assert conv.get("is_pinned") is True
        assert "work" in (conv.get("tags") or [])


@pytest.mark.asyncio
async def test_mute_and_snooze(panel_client):
    res = await panel_client.patch(
        "/api/conversations/telegram/555/meta?account_id=1",
        json={"is_muted": True, "snooze_hours": 4},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_muted"] is True
    assert data["snoozed_until"]


@pytest.mark.asyncio
async def test_list_tags(panel_client):
    await panel_client.patch(
        "/api/conversations/telegram/777/meta?account_id=1",
        json={"tags": ["sales", "vip"]},
    )
    tags = await panel_client.get("/api/conversations/tags?platform=telegram&account_id=1")
    assert tags.status_code == 200
    assert "sales" in tags.json()


@pytest.mark.asyncio
async def test_mark_all_read(panel_client):
    from app.message_store import save_message

    await save_message(
        "telegram", "111", "m1", "hi", False, datetime.utcnow(),
        chat_name="A", account_id=1,
    )
    res = await panel_client.post("/api/conversations/telegram/mark-all-read?account_id=1")
    assert res.status_code == 200
    assert res.json()["cleared"] >= 1


@pytest.mark.asyncio
async def test_broadcast_send(panel_client):
    with patch("app.main.send_platform_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"message_id": "1"}
        res = await panel_client.post(
            "/api/messages/broadcast?account_id=1",
            json={"platform": "telegram", "chat_ids": ["111", "222"], "message": "Hello all"},
        )
        assert res.status_code == 200
        assert res.json()["sent"] == 2


@pytest.mark.asyncio
async def test_broadcast_csv(panel_client):
    csv_body = "chat_id,message\n111,Hello from csv\n"
    with patch("app.main.send_platform_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"message_id": "1"}
        res = await panel_client.post(
            "/api/messages/broadcast/csv?platform=telegram&account_id=1",
            files={"file": ("recipients.csv", BytesIO(csv_body.encode()), "text/csv")},
        )
        assert res.status_code == 200
        assert res.json()["sent"] == 1


@pytest.mark.asyncio
async def test_template_update_and_category(panel_client):
    created = await panel_client.post(
        "/api/templates",
        json={"title": "Sale", "message_text": "Hi", "category": "sales"},
    )
    assert created.status_code == 200
    tid = created.json()["id"]
    res = await panel_client.put(
        f"/api/templates/{tid}",
        json={"title": "New title", "message_text": "Updated {{date}}", "category": "sales"},
    )
    assert res.status_code == 200
    listed = await panel_client.get("/api/templates?category=sales")
    assert any(t["category"] == "sales" for t in listed.json())


@pytest.mark.asyncio
async def test_duplicate_scheduled(panel_client, test_engine):
    from tests.conftest import make_session_factory
    import app.main as main_module

    factory = make_session_factory(test_engine)
    main_module.async_session = factory

    with patch("app.main.schedule_message", new_callable=AsyncMock) as mock_sched:
        mock_sched.side_effect = lambda j: j
        async with factory() as session:
            job = ScheduledMessage(
                account_id=1,
                platform=Platform.TELEGRAM.value,
                chat_id="99",
                chat_name="Test",
                chat_type="user",
                message_text="Copy me",
                scheduled_at=datetime.utcnow() + timedelta(hours=2),
                repeat_type=RepeatType.DAILY.value,
                status=JobStatus.PENDING.value,
                is_active=True,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            src_id = job.id

        res = await panel_client.post(f"/api/scheduled/{src_id}/duplicate")
        assert res.status_code == 200
        assert res.json()["id"] != src_id


@pytest.mark.asyncio
async def test_auto_reply_crud_and_update(panel_client):
    res = await panel_client.post(
        "/api/auto-replies",
        json={"platform": "telegram", "keyword": "hello", "response_text": "Hi!", "cooldown_minutes": 5},
    )
    assert res.status_code == 200
    rid = res.json()["id"]

    updated = await panel_client.put(
        f"/api/auto-replies/{rid}",
        json={"keyword": "new", "response_text": "Updated", "match_mode": "regex"},
    )
    assert updated.status_code == 200

    deleted = await panel_client.delete(f"/api/auto-replies/{rid}")
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_auto_reply_regex_match():
    from app.auto_reply_service import _matches

    assert _matches("hello", "Say hello world", "contains")
    assert _matches(r"^ping$", "ping", "regex")
    assert not _matches(r"^ping$", "ping pong", "regex")


@pytest.mark.asyncio
async def test_star_message(panel_client):
    from app.message_store import save_message

    await save_message("telegram", "888", "m1", "hello", False, datetime.utcnow(), account_id=1)
    res = await panel_client.patch(
        "/api/messages/telegram/888/m1/star?account_id=1",
        json={"starred": True},
    )
    assert res.status_code == 200
    starred = await panel_client.get("/api/messages/starred?platform=telegram&account_id=1")
    assert len(starred.json()) >= 1


@pytest.mark.asyncio
async def test_follow_up_crud(panel_client):
    res = await panel_client.post(
        "/api/follow-ups",
        json={
            "platform": "telegram",
            "chat_id": "999",
            "reminder_text": "Follow up please",
            "wait_hours": 2,
        },
    )
    assert res.status_code == 200
    fid = res.json()["id"]
    deleted = await panel_client.delete(f"/api/follow-ups/{fid}")
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_scheduled_calendar(panel_client, test_engine):
    from tests.conftest import make_session_factory

    factory = make_session_factory(test_engine)
    async with factory() as session:
        job = ScheduledMessage(
            account_id=1,
            platform="telegram",
            chat_id="1",
            chat_name="Test",
            chat_type="user",
            message_text="Hi",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            status="pending",
            is_active=True,
            next_run_at=datetime.utcnow() + timedelta(days=1),
        )
        session.add(job)
        await session.commit()

    month = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m")
    res = await panel_client.get(f"/api/scheduled/calendar?month={month}")
    assert res.status_code == 200
    assert res.json()["total"] >= 1


@pytest.mark.asyncio
async def test_backup_export_import(panel_client):
    await panel_client.post(
        "/api/templates",
        json={"title": "B", "message_text": "Body", "category": "general"},
    )
    export = await panel_client.get("/api/admin/backup")
    assert export.status_code == 200
    data = export.json()
    restored = await panel_client.post("/api/admin/restore", json={"data": data, "merge": True})
    assert restored.status_code == 200


@pytest.mark.asyncio
async def test_activity_log(panel_client):
    from app.activity_log import log_activity

    await log_activity("test.action", {"ok": True})
    res = await panel_client.get("/api/activity?limit=5")
    assert any(r["action"] == "test.action" for r in res.json())


@pytest.mark.asyncio
async def test_search_with_tag(panel_client):
    from app.message_store import save_message

    await panel_client.patch(
        "/api/conversations/telegram/321/meta?account_id=1",
        json={"tags": ["billing"]},
    )
    await save_message("telegram", "321", "m9", "invoice due", False, datetime.utcnow(), account_id=1)
    res = await panel_client.get(
        "/api/messages/search?q=invoice&platform=telegram&account_id=1&tag=billing"
    )
    assert len(res.json()) >= 1


@pytest.mark.asyncio
async def test_unified_conversations(panel_client):
    from app.account_service import get_default_account_id
    from app.message_store import save_message

    wa_id = await get_default_account_id(Platform.WHATSAPP.value)
    await save_message("telegram", "tg1", "m1", "tg", False, datetime.utcnow(), account_id=1)
    await save_message("whatsapp", "wa1@s.whatsapp.net", "m2", "wa", False, datetime.utcnow(), account_id=wa_id)

    res = await panel_client.get("/api/conversations?unified=true")
    platforms = {c["platform"] for c in res.json()}
    assert "telegram" in platforms
    assert "whatsapp" in platforms


@pytest.mark.asyncio
async def test_stats_extended(panel_client):
    res = await panel_client.get("/api/stats")
    data = res.json()
    assert "conversations_total" in data
    assert "starred_messages" in data


@pytest.mark.asyncio
async def test_get_messages_route(panel_client):
    from app.message_store import save_message

    await save_message(
        "telegram", "999", "m-get", "hello thread", False, datetime.utcnow(),
        chat_name="Test", account_id=1,
    )
    res = await panel_client.get("/api/messages/telegram/999?account_id=1")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert any(m.get("text") == "hello thread" for m in data)


@pytest.mark.asyncio
async def test_unread_not_inflated_on_resync(panel_client):
    from app.message_store import save_message

    ts = datetime.utcnow()
    await save_message("telegram", "888", "m-resync", "once", False, ts, account_id=1)
    listed = await panel_client.get("/api/conversations?platform=telegram&account_id=1")
    conv = next((c for c in listed.json() if str(c.get("id")) == "888"), None)
    assert conv is not None
    unread_after_first = conv.get("unread_count", 0)

    await save_message("telegram", "888", "m-resync", "once", False, ts, account_id=1)
    listed2 = await panel_client.get("/api/conversations?platform=telegram&account_id=1")
    conv2 = next((c for c in listed2.json() if str(c.get("id")) == "888"), None)
    assert conv2.get("unread_count", 0) == unread_after_first


@pytest.mark.asyncio
async def test_auto_reply_not_found_error_code(panel_client):
    res = await panel_client.delete("/api/auto-replies/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "error.autoReply.notFound"


@pytest.mark.asyncio
async def test_empty_label_returns_i18n_key(panel_client):
    res = await panel_client.patch(
        "/api/conversations/telegram/123/label?account_id=1",
        json={"label": "   "},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "error.conversation.labelRequired"


@pytest.mark.asyncio
async def test_scheduler_renders_template_before_send(test_engine):
    from app.scheduler_service import _execute_job

    factory = make_session_factory(test_engine)

    async with factory() as session:
        job = ScheduledMessage(
            platform="telegram",
            chat_id="999",
            chat_name="Ali",
            message_text="Merhaba {{chat_name}}",
            scheduled_at=datetime.utcnow(),
            repeat_type=RepeatType.NONE.value,
            status=JobStatus.PENDING.value,
            is_active=True,
            next_run_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        async with factory() as s:
            yield s

    with patch("app.scheduler_service.async_session", mock_session):
        with patch("app.scheduler_service.send_platform_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"message_id": "1"}
            await _execute_job(job_id)
            mock_send.assert_called_once()
            assert mock_send.call_args.args[2] == "Merhaba Ali"


@pytest.mark.asyncio
async def test_auto_reply_respects_mute(panel_client):
    from unittest.mock import AsyncMock, patch

    await panel_client.patch(
        "/api/conversations/telegram/444/meta?account_id=1",
        json={"is_muted": True},
    )
    with patch("app.auto_reply_service.send_platform_message", new_callable=AsyncMock) as mock_send:
        from app.auto_reply_service import try_auto_reply

        result = await try_auto_reply(
            platform="telegram",
            account_id=1,
            chat_id="444",
            text="hello keyword",
            chat_name="Muted",
        )
        assert result is None
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_follow_up_dedup_per_chat(panel_client):
    await panel_client.post(
        "/api/follow-ups",
        json={
            "platform": "telegram",
            "chat_id": "555",
            "chat_name": "X",
            "reminder_text": "Ping",
            "wait_hours": 24,
            "account_id": 1,
        },
    )
    await panel_client.post(
        "/api/follow-ups",
        json={
            "platform": "telegram",
            "chat_id": "555",
            "chat_name": "X",
            "reminder_text": "Ping 2",
            "wait_hours": 24,
            "account_id": 1,
        },
    )
    listed = await panel_client.get("/api/follow-ups?platform=telegram&status=pending")
    pending = [f for f in listed.json() if f["chat_id"] == "555"]
    assert len(pending) == 1
    assert pending[0]["reminder_text"] == "Ping 2"


@pytest.mark.asyncio
async def test_send_with_reply_to(panel_client):
    with patch("app.main.send_platform_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"message_id": "42"}
        res = await panel_client.post(
            "/api/messages/send?account_id=1",
            json={
                "platform": "telegram",
                "chat_id": "123",
                "message": "Reply text",
                "reply_to_message_id": "99",
            },
        )
        assert res.status_code == 200
        assert mock_send.call_args.kwargs["reply_to_message_id"] == "99"
