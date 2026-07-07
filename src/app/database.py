from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DATABASE_URL
from app.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate_chat_unique_constraints(conn) -> None:
    """Eski (platform, chat_id) unique → (account_id, chat_id) çoklu hesap şeması."""
    for table, old_uq, new_uq in (
        (
            "chat_messages",
            "uq_msg_platform_chat_mid",
            "uq_msg_account_chat_mid",
        ),
        (
            "conversations",
            "uq_conv_platform_chat",
            "uq_conv_account_chat",
        ),
    ):
        result = await conn.execute(
            text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
        )
        row = result.fetchone()
        ddl = row[0] if row else ""
        if not ddl or new_uq in ddl:
            continue
        if old_uq not in ddl:
            continue

        if table == "chat_messages":
            await conn.execute(text("""
                CREATE TABLE chat_messages_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER,
                    platform VARCHAR(32) NOT NULL,
                    chat_id VARCHAR(128) NOT NULL,
                    message_id VARCHAR(64) NOT NULL,
                    from_me BOOLEAN NOT NULL,
                    sender_name VARCHAR(255),
                    text TEXT NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    media_path TEXT,
                    media_mime TEXT,
                    media_filename TEXT,
                    media_size INTEGER,
                    caption TEXT,
                    reply_to_message_id TEXT,
                    is_starred INTEGER DEFAULT 0,
                    timestamp DATETIME NOT NULL,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_msg_account_chat_mid UNIQUE (account_id, chat_id, message_id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO chat_messages_new
                    (id, account_id, platform, chat_id, message_id, from_me, sender_name, text,
                     message_type, media_path, media_mime, media_filename, media_size, caption,
                     reply_to_message_id, is_starred, timestamp, created_at)
                SELECT id, account_id, platform, chat_id, message_id, from_me, sender_name, text,
                       COALESCE(message_type, 'text'), media_path, media_mime, media_filename,
                       media_size, caption, reply_to_message_id, COALESCE(is_starred, 0),
                       timestamp, created_at
                FROM chat_messages
            """))
        else:
            await conn.execute(text("""
                CREATE TABLE conversations_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER,
                    platform VARCHAR(32) NOT NULL,
                    chat_id VARCHAR(128) NOT NULL,
                    chat_name VARCHAR(255) NOT NULL,
                    chat_name_custom INTEGER DEFAULT 0,
                    chat_type VARCHAR(32) NOT NULL,
                    last_message TEXT,
                    last_message_at DATETIME,
                    unread_count INTEGER NOT NULL,
                    is_pinned INTEGER DEFAULT 0,
                    pinned_at DATETIME,
                    notes TEXT,
                    tags_json TEXT DEFAULT '[]',
                    is_muted INTEGER DEFAULT 0,
                    snoozed_until DATETIME,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_conv_account_chat UNIQUE (account_id, chat_id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO conversations_new
                    (id, account_id, platform, chat_id, chat_name, chat_name_custom, chat_type,
                     last_message, last_message_at, unread_count, is_pinned, pinned_at, notes,
                     tags_json, is_muted, snoozed_until, updated_at)
                SELECT id, account_id, platform, chat_id, chat_name,
                       COALESCE(chat_name_custom, 0), chat_type, last_message, last_message_at,
                       unread_count, COALESCE(is_pinned, 0), pinned_at, notes,
                       COALESCE(tags_json, '[]'), COALESCE(is_muted, 0), snoozed_until, updated_at
                FROM conversations
            """))

        await conn.execute(text(f"DROP TABLE {table}"))
        await conn.execute(text(f"ALTER TABLE {table}_new RENAME TO {table}"))


async def _migrate(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info(scheduled_messages)"))
    columns = {row[1] for row in result.fetchall()}
    if "send_count" not in columns:
        await conn.execute(text("ALTER TABLE scheduled_messages ADD COLUMN send_count INTEGER DEFAULT 0"))
    if "platform" not in columns:
        await conn.execute(text("ALTER TABLE scheduled_messages ADD COLUMN platform TEXT DEFAULT 'telegram'"))
    if "window_start_time" not in columns:
        await conn.execute(text("ALTER TABLE scheduled_messages ADD COLUMN window_start_time TEXT"))
    if "window_end_time" not in columns:
        await conn.execute(text("ALTER TABLE scheduled_messages ADD COLUMN window_end_time TEXT"))
    if "account_id" not in columns:
        await conn.execute(text("ALTER TABLE scheduled_messages ADD COLUMN account_id INTEGER"))

    for table in ("conversations", "chat_messages"):
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        cols = {row[1] for row in result.fetchall()}
        if "account_id" not in cols:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN account_id INTEGER"))

    result = await conn.execute(text("PRAGMA table_info(conversations)"))
    conv_cols = {row[1] for row in result.fetchall()}
    if "chat_name_custom" not in conv_cols:
        await conn.execute(text(
            "ALTER TABLE conversations ADD COLUMN chat_name_custom INTEGER DEFAULT 0"
        ))
    if "is_pinned" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN is_pinned INTEGER DEFAULT 0"))
    if "pinned_at" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN pinned_at DATETIME"))
    if "notes" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN notes TEXT"))
    if "tags_json" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN tags_json TEXT DEFAULT '[]'"))
    if "is_muted" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN is_muted INTEGER DEFAULT 0"))
    if "snoozed_until" not in conv_cols:
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN snoozed_until DATETIME"))

    result = await conn.execute(text("PRAGMA table_info(chat_messages)"))
    msg_cols = {row[1] for row in result.fetchall()}
    for col, typedef in (
        ("message_type", "TEXT DEFAULT 'text'"),
        ("media_path", "TEXT"),
        ("media_mime", "TEXT"),
        ("media_filename", "TEXT"),
        ("media_size", "INTEGER"),
        ("caption", "TEXT"),
        ("reply_to_message_id", "TEXT"),
        ("is_starred", "INTEGER DEFAULT 0"),
    ):
        if col not in msg_cols:
            await conn.execute(text(f"ALTER TABLE chat_messages ADD COLUMN {col} {typedef}"))

    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'")
    )
    if not result.fetchone():
        await conn.execute(text("""
            CREATE TABLE api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER,
                is_active INTEGER DEFAULT 1,
                last_used_at DATETIME,
                created_at DATETIME
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix)"
        ))

    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='webhooks'")
    )
    if not result.fetchone():
        await conn.execute(text("""
            CREATE TABLE webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                events_json TEXT DEFAULT '[]',
                secret TEXT,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME
            )
        """))

    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='platform_accounts'")
    )
    if not result.fetchone():
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


    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_reply_rules'")
    )
    if not result.fetchone():
        await conn.execute(text("""
            CREATE TABLE auto_reply_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                platform TEXT NOT NULL,
                keyword TEXT NOT NULL,
                response_text TEXT NOT NULL,
                match_mode TEXT DEFAULT 'contains',
                cooldown_minutes INTEGER DEFAULT 60,
                is_active INTEGER DEFAULT 1,
                last_triggered_at DATETIME,
                created_at DATETIME
            )
        """))

    tmpl = await conn.execute(text("PRAGMA table_info(message_templates)"))
    tmpl_cols = {row[1] for row in tmpl.fetchall()}
    if "updated_at" not in tmpl_cols:
        await conn.execute(text("ALTER TABLE message_templates ADD COLUMN updated_at DATETIME"))
    if "category" not in tmpl_cols:
        await conn.execute(text("ALTER TABLE message_templates ADD COLUMN category TEXT DEFAULT 'general'"))

    ar = await conn.execute(text("PRAGMA table_info(auto_reply_rules)"))
    ar_cols = {row[1] for row in ar.fetchall()}
    if ar_cols and "chat_cooldowns_json" not in ar_cols:
        await conn.execute(text(
            "ALTER TABLE auto_reply_rules ADD COLUMN chat_cooldowns_json TEXT DEFAULT '{}'"
        ))

    for table, ddl in (
        ("follow_up_reminders", """
            CREATE TABLE follow_up_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                platform TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                chat_name TEXT DEFAULT '',
                wait_hours INTEGER DEFAULT 24,
                reminder_text TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                due_at DATETIME NOT NULL,
                anchor_at DATETIME NOT NULL,
                created_at DATETIME
            )
        """),
        ("activity_logs", """
            CREATE TABLE activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail_json TEXT DEFAULT '{}',
                created_at DATETIME
            )
        """),
    ):
        result = await conn.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        )
        if not result.fetchone():
            await conn.execute(text(ddl))

    await _migrate_chat_unique_constraints(conn)


async def _apply_sqlite_pragmas_and_indexes(conn) -> None:
    await conn.execute(text("PRAGMA journal_mode=WAL"))
    await conn.execute(text("PRAGMA synchronous=NORMAL"))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_acct_chat_ts "
        "ON chat_messages(account_id, chat_id, timestamp DESC)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_acct_platform "
        "ON chat_messages(account_id, platform)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_conversations_acct_last "
        "ON conversations(account_id, last_message_at DESC)"
    ))


async def assign_legacy_account_ids() -> None:
    """Mevcut mesajları varsayılan hesaba bağla."""
    from app.account_service import (
        ensure_default_accounts,
        get_default_account_id,
        migrate_legacy_whatsapp_files,
        normalize_whatsapp_bridge_ids,
    )
    from app.models import Platform

    await ensure_default_accounts()
    await migrate_legacy_whatsapp_files()
    await normalize_whatsapp_bridge_ids()
    tg_id = await get_default_account_id(Platform.TELEGRAM.value)
    wa_id = await get_default_account_id(Platform.WHATSAPP.value)

    async with async_session() as session:
        await session.execute(
            text("UPDATE conversations SET account_id = :aid WHERE platform = 'telegram' AND account_id IS NULL"),
            {"aid": tg_id},
        )
        await session.execute(
            text("UPDATE conversations SET account_id = :aid WHERE platform = 'whatsapp' AND account_id IS NULL"),
            {"aid": wa_id},
        )
        await session.execute(
            text("UPDATE chat_messages SET account_id = :aid WHERE platform = 'telegram' AND account_id IS NULL"),
            {"aid": tg_id},
        )
        await session.execute(
            text("UPDATE chat_messages SET account_id = :aid WHERE platform = 'whatsapp' AND account_id IS NULL"),
            {"aid": wa_id},
        )
        await session.execute(
            text("UPDATE scheduled_messages SET account_id = :aid WHERE platform = 'telegram' AND account_id IS NULL"),
            {"aid": tg_id},
        )
        await session.execute(
            text("UPDATE scheduled_messages SET account_id = :aid WHERE platform = 'whatsapp' AND account_id IS NULL"),
            {"aid": wa_id},
        )
        await session.commit()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)
    async with engine.begin() as conn:
        await _apply_sqlite_pragmas_and_indexes(conn)
    await assign_legacy_account_ids()


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
