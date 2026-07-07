import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_ROOT = process.env.DATA_DIR || path.join(__dirname, "..", "data");
const DEFAULT_DB_PATH = path.join(DATA_ROOT, "whatsapp.db");

function isDigitsOnly(value) {
  const s = String(value || "").trim();
  if (!s) return false;
  const digits = s.replace(/\D/g, "");
  return digits.length >= 10 && digits.length <= 15 && /^\d+$/.test(digits);
}

function isPhoneLike(value) {
  const s = String(value || "").trim();
  if (!s) return false;
  if (s.includes("@")) return true;
  const digits = s.replace(/\D/g, "");
  return digits.length >= 10 && digits.length / Math.max(s.replace(/\s/g, "").length, 1) >= 0.85;
}

export function normalizePhoneKey(value) {
  const digits = String(value || "").replace(/\D/g, "");
  if (digits.length >= 10) return digits.slice(-10);
  return digits || "";
}

export function pickBetterName(a, b) {
  if (!a || a === b) return b || a || "";
  if (!b) return a;
  const aPhone = isPhoneLike(a) || isDigitsOnly(a);
  const bPhone = isPhoneLike(b) || isDigitsOnly(b);
  if (aPhone && !bPhone) return b;
  if (bPhone && !aPhone) return a;
  if (a.includes("@") && !b.includes("@")) return b;
  if (b.includes("@") && !a.includes("@")) return a;
  return a.length >= b.length ? a : b;
}

function preferJid(a, b) {
  if (a?.includes("@s.whatsapp.net")) return a;
  if (b?.includes("@s.whatsapp.net")) return b;
  return a || b;
}

function mergeChatGroup(group) {
  let merged = { ...group[0] };
  for (const c of group.slice(1)) {
    merged = {
      ...merged,
      jid: preferJid(merged.jid, c.jid),
      name: pickBetterName(merged.name, c.name),
      unread_count: Math.max(merged.unread_count || 0, c.unread_count || 0),
      last_message: merged.last_message || c.last_message,
      last_timestamp: Math.max(merged.last_timestamp || 0, c.last_timestamp || 0),
    };
  }
  return merged;
}

export function dedupeChats(chats) {
  const groups = new Map();
  const ungrouped = [];

  for (const c of chats) {
    if (c.type === "private" && c.last_timestamp && c.last_message) {
      const fp = `${c.last_timestamp}:${c.last_message}`;
      if (!groups.has(fp)) groups.set(fp, []);
      groups.get(fp).push(c);
    } else {
      ungrouped.push(c);
    }
  }

  const deduped = [];
  for (const group of groups.values()) {
    deduped.push(group.length === 1 ? group[0] : mergeChatGroup(group));
  }

  return [...deduped, ...ungrouped].sort(
    (a, b) => (b.last_timestamp || 0) - (a.last_timestamp || 0)
  );
}

export function createStore(dbPath = DEFAULT_DB_PATH) {
  const resolved = path.isAbsolute(dbPath) ? dbPath : path.join(DATA_ROOT, dbPath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  const db = new Database(resolved);

  db.exec(`
    CREATE TABLE IF NOT EXISTS chats (
      jid TEXT PRIMARY KEY,
      name TEXT,
      type TEXT DEFAULT 'private',
      unread_count INTEGER DEFAULT 0,
      last_message TEXT,
      last_timestamp INTEGER,
      updated_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS contacts (
      jid TEXT PRIMARY KEY,
      phone_key TEXT,
      name TEXT,
      notify TEXT,
      verified_name TEXT,
      updated_at INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone_key);
    CREATE TABLE IF NOT EXISTS messages (
      id TEXT,
      jid TEXT,
      from_me INTEGER,
      text TEXT,
      timestamp INTEGER,
      push_name TEXT,
      PRIMARY KEY (jid, id)
    );
    CREATE INDEX IF NOT EXISTS idx_messages_jid_ts ON messages(jid, timestamp DESC);
  `);

  const msgCols = db.prepare("PRAGMA table_info(messages)").all().map((c) => c.name);
  for (const [col, def] of [
    ["message_type", "TEXT DEFAULT 'text'"],
    ["media_path", "TEXT"],
    ["media_mime", "TEXT"],
    ["media_filename", "TEXT"],
    ["media_size", "INTEGER"],
    ["caption", "TEXT"],
  ]) {
    if (!msgCols.includes(col)) db.exec(`ALTER TABLE messages ADD COLUMN ${col} ${def}`);
  }

  const upsertChat = db.prepare(`
    INSERT INTO chats (jid, name, type, unread_count, last_message, last_timestamp, updated_at)
    VALUES (@jid, @name, @type, @unread_count, @last_message, @last_timestamp, @updated_at)
    ON CONFLICT(jid) DO UPDATE SET
      name = @resolved_name,
      type = COALESCE(excluded.type, chats.type),
      unread_count = CASE
        WHEN excluded.unread_count > 0 THEN chats.unread_count + excluded.unread_count
        ELSE chats.unread_count
      END,
      last_message = COALESCE(excluded.last_message, chats.last_message),
      last_timestamp = CASE
        WHEN excluded.last_timestamp IS NOT NULL AND (chats.last_timestamp IS NULL OR excluded.last_timestamp >= chats.last_timestamp)
        THEN excluded.last_timestamp ELSE chats.last_timestamp
      END,
      updated_at = excluded.updated_at
  `);

  const upsertContact = db.prepare(`
    INSERT INTO contacts (jid, phone_key, name, notify, verified_name, updated_at)
    VALUES (@jid, @phone_key, @name, @notify, @verified_name, @updated_at)
    ON CONFLICT(jid) DO UPDATE SET
      phone_key = COALESCE(excluded.phone_key, contacts.phone_key),
      name = COALESCE(excluded.name, contacts.name),
      notify = COALESCE(excluded.notify, contacts.notify),
      verified_name = COALESCE(excluded.verified_name, contacts.verified_name),
      updated_at = excluded.updated_at
  `);

  const findContactByPhone = db.prepare(`
    SELECT jid, name, notify, verified_name FROM contacts
    WHERE phone_key = ? AND phone_key != ''
    ORDER BY updated_at DESC LIMIT 1
  `);

  const findContactByJid = db.prepare(`
    SELECT jid, name, notify, verified_name FROM contacts WHERE jid = ?
  `);

  const upsertMessage = db.prepare(`
    INSERT INTO messages (id, jid, from_me, text, timestamp, push_name, message_type, media_path, media_mime, media_filename, media_size, caption)
    VALUES (@id, @jid, @from_me, @text, @timestamp, @push_name, @message_type, @media_path, @media_mime, @media_filename, @media_size, @caption)
    ON CONFLICT(jid, id) DO UPDATE SET
      text = excluded.text,
      timestamp = excluded.timestamp,
      push_name = COALESCE(excluded.push_name, messages.push_name),
      message_type = COALESCE(excluded.message_type, messages.message_type),
      media_path = COALESCE(excluded.media_path, messages.media_path),
      media_mime = COALESCE(excluded.media_mime, messages.media_mime),
      media_filename = COALESCE(excluded.media_filename, messages.media_filename),
      media_size = COALESCE(excluded.media_size, messages.media_size),
      caption = COALESCE(excluded.caption, messages.caption)
  `);

  const getChatsRaw = db.prepare(`
    SELECT jid, name, type, unread_count, last_message, last_timestamp
    FROM chats
    ORDER BY last_timestamp DESC NULLS LAST
  `);

  const getMessages = db.prepare(`
    SELECT id, jid, from_me, text, timestamp, push_name, message_type, media_path, media_mime, media_filename, media_size, caption
    FROM messages WHERE jid = ?
    ORDER BY timestamp DESC
    LIMIT ?
  `);

  const getMessagesMulti = db.prepare(`
    SELECT id, jid, from_me, text, timestamp, push_name
    FROM messages WHERE jid IN (SELECT value FROM json_each(?))
    ORDER BY timestamp DESC
    LIMIT ?
  `);

  const getAllMessages = db.prepare(`
    SELECT id, jid, from_me, text, timestamp, push_name
    FROM messages
    ORDER BY timestamp ASC
    LIMIT ?
  `);

  const getAllMessagesPaginated = db.prepare(`
    SELECT id, jid, from_me, text, timestamp, push_name
    FROM messages
    ORDER BY rowid ASC
    LIMIT ? OFFSET ?
  `);

  const countAllMessages = db.prepare(`SELECT COUNT(*) as c FROM messages`);

  const getMessageForRetry = db.prepare(`
    SELECT text FROM messages WHERE jid = ? AND id = ? AND from_me = ?
  `);

  function resolveAliasJids(jid) {
    const all = dedupeChats(getChatsRaw.all());
    const chat = all.find((c) => c.jid === jid);
    if (!chat || chat.type !== "private" || !chat.last_timestamp || !chat.last_message) {
      return [jid];
    }
    const fp = `${chat.last_timestamp}:${chat.last_message}`;
    const aliases = getChatsRaw.all().filter(
      (c) =>
        c.type === "private" &&
        c.last_timestamp === chat.last_timestamp &&
        c.last_message === chat.last_message
    );
    const jids = [...new Set(aliases.map((c) => c.jid))];
    return jids.length ? jids : [jid];
  }

  return {
    saveContact(contact) {
      const jid = contact.jid || contact.id;
      if (!jid) return;
      const label = contact.name || contact.notify || contact.verifiedName || contact.verified_name || "";
      upsertContact.run({
        jid,
        phone_key: normalizePhoneKey(jid),
        name: contact.name || null,
        notify: contact.notify || null,
        verified_name: contact.verifiedName || contact.verified_name || null,
        updated_at: Date.now(),
      });
      if (label) {
        const existing = db.prepare("SELECT name, unread_count, last_message, last_timestamp, type FROM chats WHERE jid = ?").get(jid);
        const resolved = pickBetterName(existing?.name, label);
        if (resolved) {
          upsertChat.run({
            jid,
            name: resolved,
            resolved_name: resolved,
            type: existing?.type || contact.type || "private",
            unread_count: existing?.unread_count || 0,
            last_message: existing?.last_message || null,
            last_timestamp: existing?.last_timestamp || null,
            updated_at: Date.now(),
          });
        }
      }
      const pk = normalizePhoneKey(jid);
      if (pk && label) {
        const chats = db.prepare("SELECT jid, name FROM chats").all();
        for (const ch of chats) {
          if (normalizePhoneKey(ch.jid) === pk && ch.jid !== jid) {
            const merged = pickBetterName(ch.name, label);
            if (merged && merged !== ch.name) {
              upsertChat.run({
                jid: ch.jid,
                name: merged,
                resolved_name: merged,
                type: "private",
                unread_count: 0,
                last_message: null,
                last_timestamp: null,
                updated_at: Date.now(),
              });
            }
          }
        }
      }
    },
    resolveDisplayName(jid, fallback = "") {
      const direct = findContactByJid.get(jid);
      const fromDirect = direct?.name || direct?.notify || direct?.verified_name;
      const pk = normalizePhoneKey(jid);
      const byPhone = pk ? findContactByPhone.get(pk) : null;
      const fromPhone = byPhone?.name || byPhone?.notify || byPhone?.verified_name;
      const existing = db.prepare("SELECT name FROM chats WHERE jid = ?").get(jid);
      return pickBetterName(
        pickBetterName(existing?.name || fallback, fromDirect || ""),
        fromPhone || ""
      ) || fallback || jid.split("@")[0];
    },
    rehydrateAllChatNames() {
      const chats = getChatsRaw.all();
      for (const ch of chats) {
        const resolved = this.resolveDisplayName(ch.jid, ch.name);
        if (resolved && resolved !== ch.name) {
          upsertChat.run({
            jid: ch.jid,
            name: resolved,
            resolved_name: resolved,
            type: ch.type || "private",
            unread_count: ch.unread_count || 0,
            last_message: ch.last_message,
            last_timestamp: ch.last_timestamp,
            updated_at: Date.now(),
          });
        }
      }
    },
    saveChat(chat) {
      const existing = db.prepare("SELECT name FROM chats WHERE jid = ?").get(chat.jid);
      const fromContact = this.resolveDisplayName(chat.jid, "");
      const resolved_name = pickBetterName(
        pickBetterName(existing?.name, chat.name),
        fromContact
      );
      upsertChat.run({ ...chat, resolved_name });
    },
    saveMessage(msg) {
      upsertMessage.run({
        message_type: "text",
        media_path: null,
        media_mime: null,
        media_filename: null,
        media_size: null,
        caption: null,
        ...msg,
      });
    },
    listChats() {
      return dedupeChats(getChatsRaw.all());
    },
    listChatsRaw() {
      return getChatsRaw.all();
    },
    listMessages(jid, limit = 50) {
      const aliases = resolveAliasJids(jid);
      let rows;
      if (aliases.length === 1) {
        rows = getMessages.all(jid, limit);
      } else {
        rows = getMessagesMulti.all(JSON.stringify(aliases), limit);
      }
      const seen = new Set();
      const unique = [];
      for (const r of rows) {
        const key = `${r.id}:${r.from_me}`;
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(r);
      }
      return unique.reverse();
    },
    listAllMessages(limit = null) {
      if (limit == null) {
        return db.prepare(`
          SELECT id, jid, from_me, text, timestamp, push_name, message_type, media_path, media_mime, media_filename, media_size, caption
          FROM messages ORDER BY rowid ASC
        `).all();
      }
      return getAllMessages.all(limit);
    },
    listAllMessagesPaginated(offset, limit) {
      return getAllMessagesPaginated.all(limit, offset);
    },
    countAllMessages() {
      return countAllMessages.get().c;
    },
    getMessage(key) {
      const row = getMessageForRetry.get(key.remoteJid, key.id, key.fromMe ? 1 : 0);
      if (!row) return undefined;
      return { conversation: row.text };
    },
    clearAll() {
      db.exec("DELETE FROM messages; DELETE FROM chats;");
    },
    markRead(jid) {
      db.prepare("UPDATE chats SET unread_count = 0 WHERE jid = ?").run(jid);
      const aliases = resolveAliasJids(jid);
      for (const j of aliases) {
        db.prepare("UPDATE chats SET unread_count = 0 WHERE jid = ?").run(j);
      }
    },
    countMessages() {
      return db.prepare("SELECT COUNT(*) as c FROM messages").get().c;
    },
    pickBetterName,
    dedupeChats,
  };
}
