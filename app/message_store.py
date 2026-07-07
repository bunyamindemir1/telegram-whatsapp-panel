from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.account_service import get_default_account_id, resolve_account_id
from app.database import async_session
from app.models import ChatMessage, Conversation


def _is_phone_like(name: str) -> bool:
    if not name:
        return True
    s = str(name).strip()
    if "@" in s:
        return True
    digits = "".join(c for c in s if c.isdigit())
    plain = s.replace(" ", "").replace("+", "").replace("-", "")
    if not digits or len(digits) < 10:
        return False
    return len(digits) >= len(plain) * 0.85


def _format_phone_hint(chat_id: str, chat_name: str) -> Optional[str]:
    """Numara gibi görünen isimler için +90 formatı."""
    if not chat_id or not _is_phone_like(chat_name or chat_id):
        return None
    digits = "".join(c for c in chat_id.split("@")[0] if c.isdigit())
    if len(digits) < 10:
        return None
    local = digits[-10:]
    if local.startswith("5"):
        return f"+90 {local[:3]} {local[3:6]} {local[6:8]} {local[8:10]}"
    return f"+{digits}"


def _better_chat_name(current: Optional[str], new: Optional[str], fallback: str) -> str:
    cur = (current or "").strip()
    nxt = (new or "").strip()
    if not nxt:
        return cur or fallback
    if not cur or cur == fallback:
        return nxt
    if _is_phone_like(cur) and not _is_phone_like(nxt):
        return nxt
    if _is_phone_like(nxt) and not _is_phone_like(cur):
        return cur
    return nxt if len(nxt) > len(cur) else cur


def _msg_to_dict(m: ChatMessage) -> dict[str, Any]:
    d = {
        "id": m.id,
        "message_id": m.message_id,
        "platform": m.platform,
        "account_id": m.account_id,
        "chat_id": m.chat_id,
        "from_me": m.from_me,
        "sender_name": m.sender_name,
        "text": m.text,
        "message_type": getattr(m, "message_type", None) or "text",
        "timestamp": m.timestamp.isoformat() + "Z",
    }
    if m.media_path:
        d["media_path"] = m.media_path
        d["media_mime"] = m.media_mime
        d["media_filename"] = m.media_filename
        d["media_size"] = m.media_size
        d["caption"] = m.caption
    return d


async def save_message(
    platform: str,
    chat_id: str,
    message_id: str,
    text: str,
    from_me: bool,
    timestamp: datetime,
    sender_name: Optional[str] = None,
    chat_name: Optional[str] = None,
    chat_type: str = "unknown",
    account_id: Optional[int] = None,
    *,
    message_type: str = "text",
    media_path: Optional[str] = None,
    media_mime: Optional[str] = None,
    media_filename: Optional[str] = None,
    media_size: Optional[int] = None,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
) -> dict[str, Any]:
    aid = await resolve_account_id(platform, account_id)
    async with async_session() as session:
        values = {
            "account_id": aid,
            "platform": platform,
            "chat_id": chat_id,
            "message_id": str(message_id),
            "text": text,
            "from_me": from_me,
            "sender_name": sender_name,
            "timestamp": timestamp,
            "message_type": message_type,
            "media_path": media_path,
            "media_mime": media_mime,
            "media_filename": media_filename,
            "media_size": media_size,
            "caption": caption,
            "reply_to_message_id": reply_to_message_id,
        }
        stmt = sqlite_insert(ChatMessage).values(**values)
        update_set = {
            "text": text,
            "timestamp": timestamp,
            "sender_name": sender_name,
            "message_type": message_type,
            "media_path": media_path,
            "media_mime": media_mime,
            "media_filename": media_filename,
            "media_size": media_size,
            "caption": caption,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id", "chat_id", "message_id"],
            set_=update_set,
        )
        await session.execute(stmt)

        existing_conv = await session.scalar(
            select(Conversation).where(
                Conversation.account_id == aid,
                Conversation.chat_id == chat_id,
            )
        )
        if existing_conv and existing_conv.chat_name_custom:
            resolved_name = existing_conv.chat_name
        else:
            resolved_name = _better_chat_name(
                existing_conv.chat_name if existing_conv else None,
                chat_name,
                chat_id,
            )

        conv_stmt = sqlite_insert(Conversation).values(
            account_id=aid,
            platform=platform,
            chat_id=chat_id,
            chat_name=resolved_name,
            chat_type=chat_type,
            last_message=text[:500] if text else None,
            last_message_at=timestamp,
            unread_count=0 if from_me else 1,
            updated_at=datetime.utcnow(),
        )
        conv_stmt = conv_stmt.on_conflict_do_update(
            index_elements=["account_id", "chat_id"],
            set_={
                "chat_name": resolved_name,
                "chat_type": chat_type,
                "last_message": text[:500] if text else None,
                "last_message_at": timestamp,
                "updated_at": datetime.utcnow(),
                "unread_count": Conversation.unread_count + (0 if from_me else 1),
            },
        )
        await session.execute(conv_stmt)
        await session.commit()

        result = await session.execute(
            select(ChatMessage).where(
                ChatMessage.account_id == aid,
                ChatMessage.chat_id == chat_id,
                ChatMessage.message_id == str(message_id),
            )
        )
        row = result.scalar_one()
        return _msg_to_dict(row)


async def save_messages_batch(messages: list[dict[str, Any]]) -> int:
    """Geriye uyumluluk — toplu kayda yönlendirir."""
    return await save_messages_bulk(messages)


def _parse_message_timestamp(m: dict[str, Any]) -> datetime:
    ts = m.get("timestamp")
    if isinstance(ts, (int, float)):
        return datetime.utcfromtimestamp(ts)
    if isinstance(ts, datetime):
        return ts
    return datetime.utcnow()


async def save_messages_bulk(
    messages: list[dict[str, Any]],
    *,
    chunk_size: int = 1000,
) -> int:
    """Binlerce mesajı tek transaction bloklarında hızlı kaydeder."""
    if not messages:
        return 0

    saved = 0
    for start in range(0, len(messages), chunk_size):
        chunk = messages[start : start + chunk_size]
        async with async_session() as session:
            msg_rows: list[dict[str, Any]] = []
            chat_latest: dict[tuple[int, str], dict[str, Any]] = {}

            for m in chunk:
                platform = m["platform"]
                aid = m.get("account_id")
                if aid is None:
                    aid = await resolve_account_id(platform, None)
                chat_id = m["chat_id"]
                ts = _parse_message_timestamp(m)
                text = m.get("text") or ""

                msg_rows.append({
                    "account_id": aid,
                    "platform": platform,
                    "chat_id": chat_id,
                    "message_id": str(m["message_id"]),
                    "text": text,
                    "from_me": bool(m.get("from_me")),
                    "sender_name": m.get("sender_name"),
                    "timestamp": ts,
                    "message_type": m.get("message_type") or "text",
                    "media_path": m.get("media_path"),
                    "media_mime": m.get("media_mime"),
                    "media_filename": m.get("media_filename"),
                    "media_size": m.get("media_size"),
                    "caption": m.get("caption"),
                })

                key = (aid, chat_id)
                prev = chat_latest.get(key)
                if not prev or ts >= prev["timestamp"]:
                    chat_latest[key] = {
                        "platform": platform,
                        "account_id": aid,
                        "chat_id": chat_id,
                        "text": text,
                        "timestamp": ts,
                        "chat_name": m.get("chat_name"),
                        "chat_type": m.get("chat_type", "unknown"),
                        "from_me": bool(m.get("from_me")),
                    }

            if msg_rows:
                stmt = sqlite_insert(ChatMessage).values(msg_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "chat_id", "message_id"],
                    set_={
                        "text": stmt.excluded.text,
                        "timestamp": stmt.excluded.timestamp,
                        "sender_name": stmt.excluded.sender_name,
                        "message_type": stmt.excluded.message_type,
                        "media_path": stmt.excluded.media_path,
                        "media_mime": stmt.excluded.media_mime,
                        "media_filename": stmt.excluded.media_filename,
                        "media_size": stmt.excluded.media_size,
                        "caption": stmt.excluded.caption,
                    },
                )
                await session.execute(stmt)

            if chat_latest:
                keys = list(chat_latest.keys())
                existing_map: dict[tuple[int, str], Conversation] = {}
                for aid, chat_id in keys:
                    conv = await session.scalar(
                        select(Conversation).where(
                            Conversation.account_id == aid,
                            Conversation.chat_id == chat_id,
                        )
                    )
                    if conv:
                        existing_map[(aid, chat_id)] = conv

                conv_rows = []
                for key, meta in chat_latest.items():
                    existing = existing_map.get(key)
                    if existing and existing.chat_name_custom:
                        resolved_name = existing.chat_name
                    else:
                        resolved_name = _better_chat_name(
                            existing.chat_name if existing else None,
                            meta.get("chat_name"),
                            meta["chat_id"],
                        )
                    conv_rows.append({
                        "account_id": meta["account_id"],
                        "platform": meta["platform"],
                        "chat_id": meta["chat_id"],
                        "chat_name": resolved_name,
                        "chat_type": meta.get("chat_type", "unknown"),
                        "last_message": (meta["text"] or "")[:500],
                        "last_message_at": meta["timestamp"],
                        "unread_count": 0,
                        "updated_at": datetime.utcnow(),
                    })

                conv_stmt = sqlite_insert(Conversation).values(conv_rows)
                conv_stmt = conv_stmt.on_conflict_do_update(
                    index_elements=["account_id", "chat_id"],
                    set_={
                        "chat_name": conv_stmt.excluded.chat_name,
                        "chat_type": conv_stmt.excluded.chat_type,
                        "last_message": conv_stmt.excluded.last_message,
                        "last_message_at": conv_stmt.excluded.last_message_at,
                        "updated_at": conv_stmt.excluded.updated_at,
                    },
                )
                await session.execute(conv_stmt)

            await session.commit()
        saved += len(chunk)
    return saved


async def sync_conversations_from_chats(
    chats: list[dict[str, Any]],
    platform: str,
    account_id: int,
) -> int:
    """Köprüden gelen sohbet listesini hızlıca conversations tablosuna yazar."""
    if not chats:
        return 0
    async with async_session() as session:
        rows = []
        for c in chats:
            jid = c.get("jid") or c.get("id")
            if not jid:
                continue
            existing = await session.scalar(
                select(Conversation).where(
                    Conversation.account_id == account_id,
                    Conversation.chat_id == jid,
                )
            )
            if existing and existing.chat_name_custom:
                name = existing.chat_name
            else:
                name = _better_chat_name(
                    existing.chat_name if existing else None,
                    c.get("name"),
                    jid,
                )
            ts = c.get("last_timestamp")
            last_at = datetime.utcfromtimestamp(ts) if ts else None
            rows.append({
                "account_id": account_id,
                "platform": platform,
                "chat_id": jid,
                "chat_name": name,
                "chat_type": c.get("type", "private"),
                "last_message": (c.get("last_message") or "")[:500] or None,
                "last_message_at": last_at,
                "unread_count": c.get("unread_count") or 0,
                "updated_at": datetime.utcnow(),
            })
        if rows:
            stmt = sqlite_insert(Conversation).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id", "chat_id"],
                set_={
                    "chat_name": stmt.excluded.chat_name,
                    "chat_type": stmt.excluded.chat_type,
                    "last_message": stmt.excluded.last_message,
                    "last_message_at": stmt.excluded.last_message_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()
    return len(chats)


async def count_stored_messages(
    platform: str,
    account_id: Optional[int] = None,
) -> int:
    aid = await resolve_account_id(platform, account_id)
    async with async_session() as session:
        from sqlalchemy import func
        return await session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.account_id == aid, ChatMessage.platform == platform)
        ) or 0


async def get_messages(
    platform: str,
    chat_id: str,
    limit: int = 80,
    before_id: Optional[int] = None,
    account_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    aid = await resolve_account_id(platform, account_id)
    async with async_session() as session:
        query = (
            select(ChatMessage)
            .where(ChatMessage.account_id == aid, ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
        )
        if before_id:
            query = query.where(ChatMessage.id < before_id)
        result = await session.execute(query)
        rows = list(reversed(result.scalars().all()))
        return [_msg_to_dict(m) for m in rows]


async def search_messages(
    query: str,
    platform: Optional[str] = None,
    limit: int = 50,
    account_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    aid = None
    if platform:
        aid = await resolve_account_id(platform, account_id)
    elif account_id is not None:
        aid = account_id

    async with async_session() as session:
        stmt = (
            select(ChatMessage, Conversation.chat_name)
            .outerjoin(
                Conversation,
                (Conversation.account_id == ChatMessage.account_id)
                & (Conversation.chat_id == ChatMessage.chat_id),
            )
            .where(
                or_(
                    ChatMessage.text.ilike(pattern),
                    Conversation.chat_name.ilike(pattern),
                    ChatMessage.chat_id.ilike(pattern),
                )
            )
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
        )
        if platform:
            stmt = stmt.where(ChatMessage.platform == platform)
        if aid is not None:
            stmt = stmt.where(ChatMessage.account_id == aid)
        result = await session.execute(stmt)
        items = []
        for msg, chat_name in result.all():
            d = _msg_to_dict(msg)
            d["chat_name"] = chat_name or msg.chat_id
            items.append(d)
        return items


def _dedupe_conversations(convs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []

    for c in convs:
        if c.get("type") == "private" and c.get("last_timestamp") and c.get("last_message"):
            fp = f"{c['last_timestamp']}:{c['last_message']}"
            groups.setdefault(fp, []).append(c)
        else:
            ungrouped.append(c)

    deduped: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        best = group[0]
        for other in group[1:]:
            best_name = _better_chat_name(best.get("name"), other.get("name"), best.get("id", ""))
            prefer_id = best["id"]
            if "@s.whatsapp.net" in other.get("id", "") and "@s.whatsapp.net" not in prefer_id:
                prefer_id = other["id"]
            best = {
                **best,
                "id": prefer_id,
                "name": best_name,
                "unread_count": max(best.get("unread_count") or 0, other.get("unread_count") or 0),
            }
        deduped.append(best)

    merged = deduped + ungrouped
    merged.sort(key=lambda x: x.get("last_timestamp") or 0, reverse=True)
    return merged


async def update_conversation_label(
    platform: str,
    chat_id: str,
    label: str,
    account_id: Optional[int] = None,
) -> dict[str, Any]:
    """Kullanıcının verdiği özel isim (ör. Annem) — senkron ile ezilmez."""
    aid = await resolve_account_id(platform, account_id)
    clean = (label or "").strip()
    if not clean:
        raise ValueError("İsim boş olamaz")
    async with async_session() as session:
        conv = await session.scalar(
            select(Conversation).where(
                Conversation.account_id == aid,
                Conversation.chat_id == chat_id,
                Conversation.platform == platform,
            )
        )
        if not conv:
            conv = Conversation(
                account_id=aid,
                platform=platform,
                chat_id=chat_id,
                chat_name=clean,
                chat_name_custom=True,
                chat_type="private",
                unread_count=0,
                updated_at=datetime.utcnow(),
            )
            session.add(conv)
        else:
            conv.chat_name = clean
            conv.chat_name_custom = True
            conv.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(conv)
    return {
        "id": conv.chat_id,
        "platform": conv.platform,
        "account_id": conv.account_id,
        "name": conv.chat_name,
        "type": conv.chat_type,
        "chat_name_custom": bool(conv.chat_name_custom),
    }


async def list_conversations(
    platform: Optional[str] = None,
    account_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    async with async_session() as session:
        query = select(Conversation).order_by(Conversation.last_message_at.desc().nullslast())
        if platform:
            query = query.where(Conversation.platform == platform)
            aid = await resolve_account_id(platform, account_id)
            query = query.where(Conversation.account_id == aid)
        elif account_id is not None:
            query = query.where(Conversation.account_id == account_id)
        result = await session.execute(query)
        convs = result.scalars().all()
        items = [
            {
                "id": c.chat_id,
                "platform": c.platform,
                "account_id": c.account_id,
                "name": c.chat_name,
                "display_phone": _format_phone_hint(c.chat_id, c.chat_name),
                "chat_name_custom": bool(c.chat_name_custom),
                "type": c.chat_type,
                "last_message": c.last_message,
                "last_timestamp": int(c.last_message_at.timestamp()) if c.last_message_at else None,
                "unread_count": c.unread_count or 0,
            }
            for c in convs
        ]
        if platform == "whatsapp":
            return _dedupe_conversations(items)
        return items


async def mark_read(
    platform: str,
    chat_id: str,
    account_id: Optional[int] = None,
) -> None:
    aid = await resolve_account_id(platform, account_id)
    async with async_session() as session:
        await session.execute(
            update(Conversation)
            .where(Conversation.account_id == aid, Conversation.chat_id == chat_id)
            .values(unread_count=0)
        )
        await session.commit()
