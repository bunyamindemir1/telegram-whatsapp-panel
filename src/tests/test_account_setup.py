"""Account setup snapshot for first-run UX."""

import pytest

from app.account_service import account_setup_snapshot


class _DisconnectedSvc:
    async def get_status(self, _aid):
        return {"connected": False}


class _ConnectedSvc:
    async def get_status(self, _aid):
        return {"connected": True}


@pytest.mark.asyncio
async def test_account_setup_snapshot_empty(monkeypatch):
    async def _empty(_platform=None):
        return []

    monkeypatch.setattr("app.account_service.list_accounts", _empty)
    snap = await account_setup_snapshot()
    assert snap["accounts_total"] == 0
    assert snap["needs_account_setup"] is True
    assert snap["needs_first_account"] is True


@pytest.mark.asyncio
async def test_account_setup_snapshot_disconnected_defaults(monkeypatch):
    async def _accounts(_platform=None):
        return [
            {"id": 1, "platform": "telegram", "label": "Telegram 1"},
            {"id": 2, "platform": "whatsapp", "label": "WhatsApp 1"},
        ]

    monkeypatch.setattr("app.account_service.list_accounts", _accounts)
    import app.telegram_service as tg
    import app.whatsapp_service as wa

    monkeypatch.setattr(tg, "telegram_service", _DisconnectedSvc())
    monkeypatch.setattr(wa, "whatsapp_service", _DisconnectedSvc())

    snap = await account_setup_snapshot()
    assert snap["accounts_total"] == 2
    assert snap["needs_account_setup"] is True
    assert snap["needs_first_account"] is False


@pytest.mark.asyncio
async def test_account_setup_snapshot_one_connected(monkeypatch):
    async def _accounts(_platform=None):
        return [
            {"id": 1, "platform": "telegram", "label": "Telegram 1"},
            {"id": 2, "platform": "whatsapp", "label": "WhatsApp 1"},
        ]

    monkeypatch.setattr("app.account_service.list_accounts", _accounts)
    import app.telegram_service as tg
    import app.whatsapp_service as wa

    monkeypatch.setattr(tg, "telegram_service", _ConnectedSvc())
    monkeypatch.setattr(wa, "whatsapp_service", _DisconnectedSvc())

    snap = await account_setup_snapshot()
    assert snap["needs_account_setup"] is False
    assert snap["telegram_connected"] is True
