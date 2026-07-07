from typing import Any, Optional

import httpx

from urllib.parse import quote

from app.account_service import get_bridge_id
from app.config import BRIDGE_SECRET, WHATSAPP_BRIDGE_URL
from app.outbound_guard import ensure_outbound_allowed, outbound_allowed


class WhatsAppService:
    def __init__(self) -> None:
        self.base_url = WHATSAPP_BRIDGE_URL.rstrip("/")
        self.timeout = 30.0

    def _headers(self) -> dict[str, str]:
        return {"X-Bridge-Token": BRIDGE_SECRET}

    async def _account_path(self, account_id: int, suffix: str) -> str:
        bridge_id = await get_bridge_id(account_id)
        return f"/api/accounts/{bridge_id}{suffix}"

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.get(f"{self.base_url}{path}", headers=self._headers())
            if res.status_code >= 400:
                try:
                    data = res.json()
                except Exception:
                    data = {}
                raise RuntimeError(data.get("error", res.text[:120] or res.reason_phrase))
            try:
                return res.json()
            except Exception as exc:
                raise RuntimeError(f"Geçersiz köprü yanıtı: {path}") from exc

    async def _post(self, path: str, json: Optional[dict] = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}{path}", json=json or {}, headers=self._headers())
            if res.status_code >= 400:
                data = res.json() if res.content else {}
                raise RuntimeError(data.get("error", res.text))
            return res.json()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/health")
                return res.status_code == 200
        except Exception:
            return False

    async def list_accounts(self) -> list[dict[str, Any]]:
        return await self._get("/api/accounts")

    async def get_status(self, account_id: int = 1) -> dict[str, Any]:
        if not await self.health():
            return {"connected": False, "bridge_running": False, "status": "offline", "user": None}
        try:
            data = await self._get(await self._account_path(account_id, "/status"))
        except Exception:
            return {"connected": False, "bridge_running": True, "status": "disconnected", "user": None}
        return {
            "connected": data.get("connected", False),
            "bridge_running": True,
            "status": data.get("status"),
            "user": data.get("user"),
            "has_qr": data.get("has_qr", False),
        }

    async def get_qr(self, account_id: int = 1) -> dict[str, Any]:
        return await self._get(await self._account_path(account_id, "/qr"))

    async def start(self, account_id: int = 1) -> dict[str, Any]:
        return await self._post(await self._account_path(account_id, "/start"))

    async def logout(self, account_id: int = 1) -> None:
        await self._post(await self._account_path(account_id, "/logout"))

    async def list_chats(self, account_id: int = 1) -> list[dict[str, Any]]:
        chats = await self._get(await self._account_path(account_id, "/chats"))
        return [
            {
                "id": c["id"],
                "name": c.get("name") or c["id"].split("@")[0],
                "type": c.get("type", "private"),
                "username": None,
                "last_message": c.get("last_message"),
                "last_timestamp": c.get("last_timestamp"),
                "unread_count": c.get("unread_count", 0),
            }
            for c in chats
        ]

    async def get_messages(self, jid: str, limit: int = 50, account_id: int = 1) -> list[dict[str, Any]]:
        encoded = quote(jid, safe="")
        path = await self._account_path(account_id, f"/chats/{encoded}/messages")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.get(
                f"{self.base_url}{path}",
                params={"limit": limit},
                headers=self._headers(),
            )
            if res.status_code >= 400:
                data = res.json() if res.content else {}
                raise RuntimeError(data.get("error", res.text))
            return res.json()

    async def export_all(
        self,
        account_id: int = 1,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        path = await self._account_path(account_id, "/export")
        params: dict[str, Any] = {"offset": offset}
        if limit is not None:
            params["limit"] = limit
        async with httpx.AsyncClient(timeout=300.0) as client:
            res = await client.get(f"{self.base_url}{path}", params=params, headers=self._headers())
            if res.status_code >= 400:
                raise RuntimeError(res.text)
            return res.json()

    async def trigger_panel_sync(self, account_id: int = 1) -> None:
        async with httpx.AsyncClient(timeout=120.0) as client:
            path = await self._account_path(account_id, "/sync-panel")
            await client.post(f"{self.base_url}{path}", headers=self._headers())

    async def mark_read(self, jid: str, account_id: int = 1) -> None:
        encoded = quote(jid, safe="")
        path = await self._account_path(account_id, f"/chats/{encoded}/read")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await client.post(f"{self.base_url}{path}", headers=self._headers())

    async def get_bridge_stats(self, account_id: int = 1) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            path = await self._account_path(account_id, "/stats")
            res = await client.get(f"{self.base_url}{path}", headers=self._headers())
            if res.status_code >= 400:
                return {}
            return res.json()

    async def send_message(self, chat_id: str, message: str, account_id: int = 1) -> dict[str, Any]:
        if not outbound_allowed():
            ensure_outbound_allowed()
        path = await self._account_path(account_id, "/send")
        return await self._post(path, {"jid": chat_id, "message": message})

    async def send_media(
        self,
        chat_id: str,
        media_path: str,
        caption: str,
        mime: str,
        account_id: int = 1,
    ) -> dict[str, Any]:
        if not outbound_allowed():
            ensure_outbound_allowed()
        path = await self._account_path(account_id, "/send/media")
        return await self._post(
            path,
            {
                "jid": chat_id,
                "media_path": media_path,
                "caption": caption,
                "mime": mime,
            },
        )


whatsapp_service = WhatsAppService()
