import express from "express";
import fs from "fs";
import path from "path";
import crypto from "crypto";
import { fileURLToPath } from "url";
import QRCode from "qrcode";
import pino from "pino";
import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  isJidGroup,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import { createStore, pickBetterName } from "./store.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_ROOT = process.env.DATA_DIR || path.join(__dirname, "..", "data");
const PORT = parseInt(process.env.WHATSAPP_BRIDGE_PORT || "3001", 10);
const HOST = process.env.BRIDGE_HOST || "127.0.0.1";
const PANEL_URL = process.env.PANEL_URL || "http://127.0.0.1:8000";
const BRIDGE_SECRET = process.env.BRIDGE_SECRET || "mesaj-bridge-local-secret";
const OUTBOUND_ALLOWED = ["1", "true", "yes"].includes(
  String(process.env.ALLOW_OUTBOUND_MESSAGES || "false").toLowerCase()
);

const WEAK_BRIDGE_SECRETS = new Set([
  "mesaj-bridge-local-secret",
  "degistirin-guclu-kopru-anahtari",
  "degistirin-kopru-anahtari",
  "change-me-bridge",
]);

function bridgeTokenValid(headerToken) {
  if (!headerToken || !BRIDGE_SECRET) return false;
  try {
    const a = Buffer.from(String(headerToken));
    const b = Buffer.from(String(BRIDGE_SECRET));
    if (a.length !== b.length) return false;
    return crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

function assertProductionBridgeSecret() {
  const env = String(process.env.ENV || "development").toLowerCase();
  if (env !== "production") return;
  const weak =
    WEAK_BRIDGE_SECRETS.has(BRIDGE_SECRET) ||
    BRIDGE_SECRET.startsWith("degistirin-") ||
    BRIDGE_SECRET.length < 16;
  if (weak) {
    console.error("Production: set a strong BRIDGE_SECRET in .env (run ./setup.sh)");
    process.exit(1);
  }
}

// Legacy migration: whatsapp-auth -> whatsapp-auth-1, whatsapp.db -> whatsapp-1.db
function migrateLegacyWhatsAppData() {
  const legacyAuth = path.join(DATA_ROOT, "whatsapp-auth");
  const acc1Auth = path.join(DATA_ROOT, "whatsapp-auth-1");
  const legacyDb = path.join(DATA_ROOT, "whatsapp.db");
  const acc1Db = path.join(DATA_ROOT, "whatsapp-1.db");
  try {
    if (fs.existsSync(legacyAuth) && !fs.existsSync(acc1Auth)) {
      fs.cpSync(legacyAuth, acc1Auth, { recursive: true });
      console.log("WhatsApp: legacy auth migrated to whatsapp-auth-1");
    }
    if (fs.existsSync(legacyDb) && !fs.existsSync(acc1Db)) {
      fs.copyFileSync(legacyDb, acc1Db);
      console.log("WhatsApp: legacy db migrated to whatsapp-1.db");
    }
  } catch (err) {
    console.warn("WhatsApp legacy migration skipped:", err.message);
  }
}

/** @type {Map<string, { id: string, sock: any, qrData: string|null, connectionStatus: string, userInfo: object|null, store: ReturnType<typeof createStore>, authDir: string, starting: boolean, syncTimer: ReturnType<typeof setTimeout>|null }>} */
const accounts = new Map();

async function notifyPanel(payload) {
  try {
    await fetch(`${PANEL_URL}/api/internal/event`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Bridge-Token": BRIDGE_SECRET,
      },
      body: JSON.stringify(payload),
    });
  } catch (_) {
    /* panel offline */
  }
}

const logger = pino({ level: "warn" });

function getAccount(id) {
  const accountId = String(id);
  let account = accounts.get(accountId);
  if (account) return account;

  const authDir = path.join(DATA_ROOT, `whatsapp-auth-${accountId}`);
  const dbPath = path.join(DATA_ROOT, `whatsapp-${accountId}.db`);
  fs.mkdirSync(authDir, { recursive: true });

  account = {
    id: accountId,
    sock: null,
    qrData: null,
    connectionStatus: "disconnected",
    userInfo: null,
    store: createStore(dbPath),
    authDir,
    starting: false,
    syncTimer: null,
  };
  accounts.set(accountId, account);
  return account;
}

function accountStatus(account) {
  return {
    id: account.id,
    connected: account.connectionStatus === "connected",
    status: account.connectionStatus,
    user: account.userInfo,
    has_qr: Boolean(account.qrData),
  };
}

function extractText(message) {
  if (!message) return "";
  const m = message.message || message;
  if (m.conversation) return m.conversation;
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text;
  if (m.imageMessage) return m.imageMessage.caption ? `[Photo] ${m.imageMessage.caption}` : "Photo";
  if (m.videoMessage) return m.videoMessage.caption ? `[Video] ${m.videoMessage.caption}` : "Video";
  if (m.audioMessage) return "Audio";
  if (m.documentMessage) return m.documentMessage.fileName || "File";
  if (m.stickerMessage) return "Sticker";
  if (m.locationMessage) return "Location";
  if (m.contactMessage) return "Contact";
  return "Message";
}

function classifyMessage(message) {
  const m = message?.message || {};
  if (m.imageMessage) {
    return { type: "image", mime: m.imageMessage.mimetype || "image/jpeg", ext: ".jpg", caption: m.imageMessage.caption || "" };
  }
  if (m.videoMessage) {
    return { type: "video", mime: m.videoMessage.mimetype || "video/mp4", ext: ".mp4", caption: m.videoMessage.caption || "" };
  }
  if (m.audioMessage) {
    const ptt = m.audioMessage.ptt;
    return { type: ptt ? "voice" : "audio", mime: m.audioMessage.mimetype || "audio/ogg", ext: ptt ? ".ogg" : ".mp3", caption: "" };
  }
  if (m.documentMessage) {
    const name = m.documentMessage.fileName || "dosya";
    const ext = path.extname(name) || "";
    return { type: "document", mime: m.documentMessage.mimetype || "application/octet-stream", ext, caption: m.documentMessage.caption || "", filename: name };
  }
  if (m.stickerMessage) {
    return { type: "sticker", mime: m.stickerMessage.mimetype || "image/webp", ext: ".webp", caption: "" };
  }
  return null;
}

function saveMediaBuffer(buffer, accountId, mime, ext) {
  const dir = path.join(DATA_ROOT, "media", "whatsapp", String(accountId));
  fs.mkdirSync(dir, { recursive: true });
  const name = `${Date.now()}_${crypto.randomBytes(4).toString("hex")}${ext || ""}`;
  const full = path.join(dir, name);
  fs.writeFileSync(full, buffer);
  return `whatsapp/${accountId}/${name}`;
}

async function buildMessageRecord(msg, sock, accountId) {
  const text = extractText(msg);
  const base = {
    text,
    message_type: "text",
    media_path: null,
    media_mime: null,
    media_filename: null,
    media_size: null,
    caption: null,
  };
  const info = classifyMessage(msg);
  if (!info || !sock) return base;
  try {
    const buffer = await downloadMediaMessage(msg, "buffer", {}, { logger, reuploadRequest: sock.updateMediaMessage });
    if (!buffer?.length) return { ...base, message_type: info.type, text: text || info.caption || info.type };
    const rel = saveMediaBuffer(buffer, accountId, info.mime, info.ext);
    return {
      text: text || info.caption || `[${info.type}]`,
      message_type: info.type,
      media_path: rel,
      media_mime: info.mime,
      media_filename: info.filename || path.basename(rel),
      media_size: buffer.length,
      caption: info.caption || null,
    };
  } catch (err) {
    console.warn("WA media download:", err.message);
    return { ...base, message_type: info.type, text: text || `[${info.type}]` };
  }
}

function chatType(jid) {
  if (isJidGroup(jid)) return "group";
  if (jid.endsWith("@broadcast")) return "broadcast";
  return "private";
}

function chatName(jid, msg, existing, store) {
  const fromMsg = msg?.pushName || msg?.verifiedBizName;
  const fromContact = store?.resolveDisplayName ? store.resolveDisplayName(jid, "") : "";
  const candidate = pickBetterName(fromMsg || "", fromContact || "");
  if (candidate) return pickBetterName(existing, candidate);
  if (existing && !/^\d{10,}$/.test(String(existing).replace(/\D/g, ""))) return existing;
  const num = jid.split("@")[0];
  return num || jid;
}

async function syncHistoryToPanel(accountId) {
  const account = getAccount(accountId);
  if (account.connectionStatus !== "connected") return;
  const chats = account.store.listChats();
  const total = account.store.countAllMessages();
  const CHUNK = 3000;
  let offset = 0;
  try {
    while (offset < total || (offset === 0 && total === 0)) {
      const messages = total
        ? account.store.listAllMessagesPaginated(offset, CHUNK)
        : [];
      await fetch(`${PANEL_URL}/api/internal/sync-whatsapp`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Bridge-Token": BRIDGE_SECRET,
        },
        body: JSON.stringify({
          account_id: accountId,
          chats: offset === 0 ? chats : [],
          messages,
          offset,
          total_messages: total,
          has_more: offset + messages.length < total,
        }),
      });
      if (!messages.length) break;
      offset += messages.length;
      if (messages.length < CHUNK) break;
    }
  } catch (_) {
    /* panel offline */
  }
}

function schedulePanelSync(accountId) {
  const account = getAccount(accountId);
  if (account.syncTimer) clearTimeout(account.syncTimer);
  account.syncTimer = setTimeout(() => {
    account.syncTimer = null;
    syncHistoryToPanel(accountId);
  }, 3000);
}

async function startSocket(accountId) {
  const account = getAccount(accountId);
  if (account.starting) return;
  account.starting = true;

  const { store, authDir } = account;

  try {
    const { state, saveCreds } = await useMultiFileAuthState(authDir);
    const { version } = await fetchLatestBaileysVersion();

    account.sock = makeWASocket({
      version,
      auth: state,
      logger,
      printQRInTerminal: false,
      syncFullHistory: true,
      getMessage: async (key) => store.getMessage(key),
    });

    const sock = account.sock;

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        account.qrData = await QRCode.toDataURL(qr, { margin: 1, width: 280 });
        account.connectionStatus = "qr";
      }

      if (connection === "connecting") {
        account.connectionStatus = sock?.user ? "connecting" : account.connectionStatus;
      }

      if (connection === "open") {
        account.connectionStatus = "connected";
        account.qrData = null;
        account.userInfo = {
          id: sock.user?.id,
          name: sock.user?.name || sock.user?.verifiedName || "WhatsApp",
          phone: sock.user?.id?.split(":")[0]?.split("@")[0] || "",
        };
        notifyPanel({
          type: "connection",
          platform: "whatsapp",
          account_id: accountId,
          status: "connected",
          user: account.userInfo,
        });
        store.rehydrateAllChatNames();
        schedulePanelSync(accountId);
      }

      if (connection === "close") {
        const code = lastDisconnect?.error?.output?.statusCode;
        account.connectionStatus = "disconnected";
        notifyPanel({
          type: "connection",
          platform: "whatsapp",
          account_id: accountId,
          status: "disconnected",
        });
        account.userInfo = null;
        account.qrData = null;
        account.sock = null;
        account.starting = false;

        if (code !== DisconnectReason.loggedOut) {
          setTimeout(() => startSocket(accountId), 3000);
        }
      }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      const live = type === "notify";
      const account = getAccount(accountId);
      for (const msg of messages) {
        if (!msg.key?.remoteJid || msg.key.remoteJid === "status@broadcast") continue;

        const jid = msg.key.remoteJid;
        const ts = Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000);
        const media = await buildMessageRecord(msg, account.sock, accountId);

        store.saveMessage({
          id: msg.key.id,
          jid,
          from_me: msg.key.fromMe ? 1 : 0,
          text: media.text,
          timestamp: ts,
          push_name: msg.pushName || "",
          message_type: media.message_type,
          media_path: media.media_path,
          media_mime: media.media_mime,
          media_filename: media.media_filename,
          media_size: media.media_size,
          caption: media.caption,
        });

        const existing = store.listChats().find((c) => c.jid === jid);
        store.saveChat({
          jid,
          name: chatName(jid, msg, existing?.name, store),
          type: chatType(jid),
          unread_count: msg.key.fromMe ? 0 : 1,
          last_message: media.text,
          last_timestamp: ts,
          updated_at: Date.now(),
        });

        if (!live) continue;

        notifyPanel({
          type: "message",
          account_id: accountId,
          data: {
            chat_id: jid,
            message_id: msg.key.id,
            text: media.text,
            from_me: !!msg.key.fromMe,
            timestamp: ts,
            sender_name: msg.pushName || "",
            chat_name: chatName(jid, msg, existing?.name, store),
            chat_type: chatType(jid),
            message_type: media.message_type,
            media_path: media.media_path,
            media_mime: media.media_mime,
            media_filename: media.media_filename,
            media_size: media.media_size,
            caption: media.caption,
          },
        });
      }
    });

    sock.ev.on("messaging-history.set", ({ chats, messages, contacts }) => {
      if (contacts) {
        for (const c of contacts) {
          store.saveContact(c);
        }
      }
      if (chats) {
        for (const c of chats) {
          const jid = c.id;
          if (!jid || jid === "status@broadcast") continue;
          const existing = store.listChatsRaw().find((ch) => ch.jid === jid);
          store.saveChat({
            jid,
            name: pickBetterName(existing?.name, c.name || c.subject || jid.split("@")[0]),
            type: chatType(jid),
            unread_count: c.unreadCount || 0,
            last_message: c.messages?.[0] ? extractText(c.messages[0]) : existing?.last_message || null,
            last_timestamp: c.conversationTimestamp
              ? Number(c.conversationTimestamp)
              : existing?.last_timestamp || null,
            updated_at: Date.now(),
          });
        }
      }
      if (messages) {
        for (const msg of messages) {
          if (!msg.key?.remoteJid) continue;
          const jid = msg.key.remoteJid;
          store.saveMessage({
            id: msg.key.id,
            jid,
            from_me: msg.key.fromMe ? 1 : 0,
            text: extractText(msg),
            timestamp: Number(msg.messageTimestamp) || 0,
            push_name: msg.pushName || "",
          });
        }
      }
      schedulePanelSync(accountId);
      store.rehydrateAllChatNames();
    });

    sock.ev.on("contacts.upsert", (contacts) => {
      for (const c of contacts) {
        store.saveContact(c);
        updateContactChat(c);
      }
      store.rehydrateAllChatNames();
      schedulePanelSync(accountId);
    });

    sock.ev.on("contacts.update", (contacts) => {
      for (const c of contacts) {
        store.saveContact(c);
        updateContactChat(c);
      }
      store.rehydrateAllChatNames();
    });

    function updateContactChat(c) {
      const jid = c.id;
      if (!jid) return;
      const existing = store.listChatsRaw().find((ch) => ch.jid === jid);
      const name = pickBetterName(
        existing?.name,
        c.name || c.notify || c.verifiedName || store.resolveDisplayName(jid, "")
      );
      if (name) {
        store.saveChat({
          jid,
          name,
          type: chatType(jid),
          unread_count: existing?.unread_count || 0,
          last_message: existing?.last_message || null,
          last_timestamp: existing?.last_timestamp || null,
          updated_at: Date.now(),
        });
      }
    }

    sock.ev.on("chats.update", (updates) => {
      for (const c of updates) {
        const jid = c.id;
        if (!jid) continue;
        const existing = store.listChatsRaw().find((ch) => ch.jid === jid);
        store.saveChat({
          jid,
          name: pickBetterName(existing?.name, c.name || c.subject || existing?.name),
          type: chatType(jid),
          unread_count: c.unreadCount ?? existing?.unread_count ?? 0,
          last_message: existing?.last_message || null,
          last_timestamp: c.conversationTimestamp
            ? Number(c.conversationTimestamp)
            : existing?.last_timestamp || null,
          updated_at: Date.now(),
        });
      }
    });

    sock.ev.on("groups.upsert", (groups) => {
      for (const g of groups) {
        const jid = g.id;
        if (!jid) continue;
        const existing = store.listChatsRaw().find((ch) => ch.jid === jid);
        store.saveChat({
          jid,
          name: pickBetterName(existing?.name, g.subject || g.name || existing?.name),
          type: "group",
          unread_count: existing?.unread_count || 0,
          last_message: existing?.last_message || null,
          last_timestamp: existing?.last_timestamp || null,
          updated_at: Date.now(),
        });
      }
    });

    sock.ev.on("chats.upsert", (chats) => {
      for (const c of chats) {
        const jid = c.id;
        if (!jid) continue;
        const existing = store.listChatsRaw().find((ch) => ch.jid === jid);
        store.saveChat({
          jid,
          name: pickBetterName(existing?.name, c.name || c.subject || jid.split("@")[0]),
          type: chatType(jid),
          unread_count: c.unreadCount || 0,
          last_message: existing?.last_message || null,
          last_timestamp: c.conversationTimestamp ? Number(c.conversationTimestamp) : existing?.last_timestamp || null,
          updated_at: Date.now(),
        });
      }
    });
  } catch (err) {
    logger.error(err);
    account.connectionStatus = "disconnected";
    account.starting = false;
  }
}

function mapChats(store) {
  return store.listChats().map((c) => ({
    id: c.jid,
    name: store.resolveDisplayName(c.jid, c.name || c.jid.split("@")[0]),
    type: c.type,
    last_message: c.last_message,
    last_timestamp: c.last_timestamp,
    unread_count: c.unread_count,
  }));
}

function mapMessages(store, jid, limit) {
  return store.listMessages(jid, limit).map((m) => ({
    id: m.id,
    from_me: Boolean(m.from_me),
    text: m.text,
    timestamp: m.timestamp,
    push_name: m.push_name,
  }));
}

function accountStats(account) {
  const chats = account.store.listChats();
  const msgCount = account.store.countMessages();
  return {
    id: account.id,
    connected: account.connectionStatus === "connected",
    chats: chats.length,
    messages: msgCount,
    status: account.connectionStatus,
  };
}

async function handleSend(accountId, jid, message, res) {
  const account = getAccount(accountId);
  if (!OUTBOUND_ALLOWED) {
    return res.status(403).json({
      error: "error.outbound.testMode",
      dry_run: true,
    });
  }
  if (!account.sock || account.connectionStatus !== "connected") {
    return res.status(400).json({ error: "error.whatsapp.notConnected" });
  }
  if (!jid || !message) {
    return res.status(400).json({ error: "error.whatsapp.missingFields" });
  }
  try {
    const result = await account.sock.sendMessage(jid, { text: message });
    const ts = Math.floor(Date.now() / 1000);
    account.store.saveMessage({
      id: result.key.id,
      jid,
      from_me: 1,
      text: message,
      timestamp: ts,
      push_name: account.userInfo?.name || "",
    });
    account.store.saveChat({
      jid,
      name: account.store.listChats().find((c) => c.jid === jid)?.name || jid.split("@")[0],
      type: chatType(jid),
      unread_count: 0,
      last_message: message,
      last_timestamp: ts,
      updated_at: Date.now(),
    });
    notifyPanel({
      type: "message",
      account_id: accountId,
      data: {
        chat_id: jid,
        message_id: result.key.id,
        text: message,
        from_me: true,
        timestamp: ts,
        chat_name: account.store.listChats().find((c) => c.jid === jid)?.name || jid.split("@")[0],
        chat_type: chatType(jid),
      },
    });
    res.json({ ok: true, message_id: result.key.id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
}

async function handleSendMedia(accountId, jid, mediaPath, caption, mime, res) {
  const account = getAccount(accountId);
  if (!OUTBOUND_ALLOWED) {
    return res.status(403).json({
      error: "error.outbound.testMode",
      dry_run: true,
    });
  }
  if (!account.sock || account.connectionStatus !== "connected") {
    return res.status(400).json({ error: "error.whatsapp.notConnected" });
  }
  if (!jid || !mediaPath) {
    return res.status(400).json({ error: "error.whatsapp.missingMediaFields" });
  }
  const fullPath = path.join(DATA_ROOT, "media", mediaPath);
  if (!fs.existsSync(fullPath)) {
    return res.status(404).json({ error: "error.media.notFound" });
  }
  try {
    const buffer = fs.readFileSync(fullPath);
    const contentType = (mime || "").toLowerCase();
    const fileName = path.basename(fullPath);
    let payload;
    if (contentType.startsWith("image/")) {
      payload = { image: buffer, caption: caption || undefined };
    } else if (contentType.startsWith("video/")) {
      payload = { video: buffer, caption: caption || undefined };
    } else if (contentType.startsWith("audio/")) {
      const isVoice = contentType.includes("ogg") || mediaPath.includes("voice");
      payload = isVoice
        ? { audio: buffer, mimetype: contentType, ptt: true }
        : { audio: buffer, mimetype: contentType };
    } else {
      payload = { document: buffer, mimetype: contentType || "application/octet-stream", fileName };
    }
    const result = await account.sock.sendMessage(jid, payload);
    const ts = Math.floor(Date.now() / 1000);
    const preview = caption || fileName || "[Medya]";
    account.store.saveMessage({
      id: result.key.id,
      jid,
      from_me: 1,
      text: preview,
      timestamp: ts,
      push_name: account.userInfo?.name || "",
    });
    account.store.saveChat({
      jid,
      name: account.store.listChats().find((c) => c.jid === jid)?.name || jid.split("@")[0],
      type: chatType(jid),
      unread_count: 0,
      last_message: preview,
      last_timestamp: ts,
      updated_at: Date.now(),
    });
    notifyPanel({
      type: "message",
      account_id: accountId,
      data: {
        chat_id: jid,
        message_id: result.key.id,
        text: preview,
        from_me: true,
        timestamp: ts,
        chat_name: account.store.listChats().find((c) => c.jid === jid)?.name || jid.split("@")[0],
        chat_type: chatType(jid),
      },
    });
    res.json({ ok: true, message_id: result.key.id });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
}

async function handleLogout(accountId, res) {
  const account = getAccount(accountId);
  try {
    if (account.sock) await account.sock.logout();
  } catch (_) {}
  if (account.syncTimer) {
    clearTimeout(account.syncTimer);
    account.syncTimer = null;
  }
  account.sock = null;
  account.connectionStatus = "disconnected";
  account.userInfo = null;
  account.qrData = null;
  account.starting = false;
  account.store.clearAll();
  fs.rmSync(account.authDir, { recursive: true, force: true });
  fs.mkdirSync(account.authDir, { recursive: true });
  res.json({ ok: true });
}

const app = express();
app.use(express.json({ limit: "55mb" }));

const PUBLIC_BRIDGE_PATHS = new Set(["/health"]);
app.use((req, res, next) => {
  if (PUBLIC_BRIDGE_PATHS.has(req.path)) return next();
  const token = req.get("x-bridge-token") || req.get("X-Bridge-Token");
  if (!bridgeTokenValid(token)) {
    return res.status(403).json({ error: "Unauthorized" });
  }
  next();
});

app.get("/health", (_, res) => {
  const anyConnected = [...accounts.values()].some((a) => a.connectionStatus === "connected");
  res.json({ ok: true, connected: anyConnected, accounts: accounts.size });
});

app.get("/api/accounts", (_, res) => {
  res.json([...accounts.values()].map(accountStatus));
});

app.get("/api/accounts/:id/status", (req, res) => {
  res.json(accountStatus(getAccount(req.params.id)));
});

app.get("/api/accounts/:id/qr", (req, res) => {
  const account = getAccount(req.params.id);
  if (account.connectionStatus === "connected") {
    return res.json({ status: "connected", qr: null });
  }
  if (!account.qrData) {
    return res.json({ status: account.connectionStatus, qr: null, message: "QR henüz hazır değil, bekleyin..." });
  }
  res.json({ status: "qr", qr: account.qrData });
});

app.post("/api/accounts/:id/start", async (req, res) => {
  const account = getAccount(req.params.id);
  if (!account.sock && !account.starting) await startSocket(req.params.id);
  res.json({ ok: true, status: account.connectionStatus });
});

app.post("/api/accounts/:id/logout", async (req, res) => {
  await handleLogout(req.params.id, res);
});

app.get("/api/accounts/:id/chats", (req, res) => {
  res.json(mapChats(getAccount(req.params.id).store));
});

app.get("/api/accounts/:id/chats/:jid/messages", (req, res) => {
  const limit = parseInt(req.query.limit || "50", 10);
  const jid = decodeURIComponent(req.params.jid);
  res.json(mapMessages(getAccount(req.params.id).store, jid, limit));
});

app.get("/api/accounts/:id/stats", (req, res) => {
  res.json(accountStats(getAccount(req.params.id)));
});

app.get("/api/accounts/:id/export", (req, res) => {
  const account = getAccount(req.params.id);
  const offset = parseInt(req.query.offset || "0", 10);
  const limitParam = req.query.limit;
  const limit = limitParam != null && limitParam !== "" ? parseInt(limitParam, 10) : null;
  const total = account.store.countAllMessages();
  const messages = limit != null
    ? account.store.listAllMessagesPaginated(offset, limit)
    : account.store.listAllMessages();
  res.json({
    chats: offset === 0 ? account.store.listChats() : [],
    messages,
    total_messages: total,
    offset,
    count: messages.length,
    has_more: limit != null ? offset + messages.length < total : false,
  });
});

app.post("/api/accounts/:id/chats/:jid/read", (req, res) => {
  const jid = decodeURIComponent(req.params.jid);
  getAccount(req.params.id).store.markRead(jid);
  res.json({ ok: true });
});

app.post("/api/accounts/:id/sync-panel", async (req, res) => {
  await syncHistoryToPanel(req.params.id);
  res.json({ ok: true });
});

app.post("/api/accounts/:id/send", async (req, res) => {
  const { jid, message } = req.body;
  await handleSend(req.params.id, jid, message, res);
});

app.post("/api/accounts/:id/send/media", async (req, res) => {
  const { jid, media_path, caption, mime } = req.body;
  await handleSendMedia(req.params.id, jid, media_path, caption, mime, res);
});

// Legacy routes (account "1")
app.get("/api/status", (_, res) => {
  res.json(accountStatus(getAccount("1")));
});

app.get("/api/qr", (_, res) => {
  const account = getAccount("1");
  if (account.connectionStatus === "connected") {
    return res.json({ status: "connected", qr: null });
  }
  if (!account.qrData) {
    return res.json({ status: account.connectionStatus, qr: null, message: "QR henüz hazır değil, bekleyin..." });
  }
  res.json({ status: "qr", qr: account.qrData });
});

app.post("/api/start", async (_, res) => {
  const account = getAccount("1");
  if (!account.sock && !account.starting) await startSocket("1");
  res.json({ ok: true, status: account.connectionStatus });
});

app.post("/api/logout", async (req, res) => {
  await handleLogout("1", res);
});

app.get("/api/chats", (_, res) => {
  res.json(mapChats(getAccount("1").store));
});

app.get("/api/chats/:jid/messages", (req, res) => {
  const limit = parseInt(req.query.limit || "50", 10);
  const jid = decodeURIComponent(req.params.jid);
  res.json(mapMessages(getAccount("1").store, jid, limit));
});

app.get("/api/export", (_, res) => {
  const account = getAccount("1");
  res.json({
    chats: account.store.listChats(),
    messages: account.store.listAllMessages(),
  });
});

app.get("/api/stats", (_, res) => {
  res.json(accountStats(getAccount("1")));
});

app.post("/api/chats/:jid/read", (req, res) => {
  const jid = decodeURIComponent(req.params.jid);
  getAccount("1").store.markRead(jid);
  res.json({ ok: true });
});

app.post("/api/sync-panel", async (_, res) => {
  await syncHistoryToPanel("1");
  res.json({ ok: true });
});

app.post("/api/send", async (req, res) => {
  const { jid, message } = req.body;
  await handleSend("1", jid, message, res);
});

fs.mkdirSync(DATA_ROOT, { recursive: true });
migrateLegacyWhatsAppData();
assertProductionBridgeSecret();

app.listen(PORT, HOST, () => {
  console.log(`WhatsApp bridge http://${HOST}:${PORT}`);
  startSocket("1");
});
