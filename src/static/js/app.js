let currentPlatform = "telegram";
let platformSwitching = false;
let accountSwitching = false;
let currentAccountId = { telegram: 1, whatsapp: 1 };
let accountsCache = { telegram: [], whatsapp: [] };
let panelAccountId = null;
let qrAccountId = null;

function defaultAccountState() {
  return { activeThreadChat: null, chatListCache: [], selectedChat: null, threadMessages: [], threadHasMore: false };
}

const platformState = {
  telegram: { 1: defaultAccountState() },
  whatsapp: { 1: defaultAccountState() },
};

function tt(key, vars) {
  return typeof t === "function" ? t(key, vars) : key;
}

function translateError(detail, extraVars) {
  if (!detail) return tt("error.generic");
  if (typeof detail === "object" && detail !== null) {
    const code = detail.code || detail.error;
    if (code) {
      const vars = { ...detail, ...extraVars };
      delete vars.code;
      delete vars.error;
      return tt(code, vars);
    }
  }
  const msg = String(detail);
  const translated = tt(msg, extraVars);
  return translated !== msg ? translated : msg;
}

function userLocale() {
  return (typeof getLocale === "function" ? getLocale() : null) || window.__LOCALE__ || "en";
}

function buildPlatformMeta() {
  return {
    telegram: {
      label: tt("platform.telegram"),
      icon: "brand-telegram",
      color: "#2aabee",
      chatsTitle: tt("platform.telegram.chatsTitle"),
      chatsSubtitle: tt("platform.telegram.chatsSubtitle"),
      composeSubtitle: tt("platform.telegram.composeSubtitle"),
      accountHint: tt("platform.telegram.accountHint"),
    },
    whatsapp: {
      label: tt("platform.whatsapp"),
      icon: "brand-whatsapp",
      color: "#25d366",
      chatsTitle: tt("platform.whatsapp.chatsTitle"),
      chatsSubtitle: tt("platform.whatsapp.chatsSubtitle"),
      composeSubtitle: tt("platform.whatsapp.composeSubtitle"),
      accountHint: tt("platform.whatsapp.accountHint"),
    },
  };
}

let PLATFORM_META = buildPlatformMeta();

function buildRepeatLabels() {
  return {
    none: tt("enum.repeat.none"), hourly: tt("enum.repeat.hourly"), daily: tt("enum.repeat.daily"),
    weekly: tt("enum.repeat.weekly"), custom: tt("enum.repeat.custom"), random_daily: tt("enum.repeat.random_daily"),
  };
}

function buildTypeLabels() {
  return {
    user: tt("enum.type.user"), group: tt("enum.type.group"), supergroup: tt("enum.type.supergroup"),
    channel: tt("enum.type.channel"), private: tt("enum.type.private"), unknown: tt("enum.type.unknown"),
  };
}

function buildStatusLabels() {
  return {
    pending: tt("enum.status.pending"), sent: tt("enum.status.sent"), failed: tt("enum.status.failed"),
    cancelled: tt("enum.status.cancelled"), running: tt("enum.status.running"),
  };
}

function buildTabTitles() {
  return {
    dashboard: tt("nav.dashboardShort"),
    chats: tt("nav.chats"),
    compose: tt("nav.compose"),
    scheduled: tt("nav.scheduled"),
    templates: tt("nav.templates"),
    account: tt("nav.account"),
  };
}

let REPEAT_LABELS = buildRepeatLabels();
let TYPE_LABELS = buildTypeLabels();
let STATUS_LABELS = buildStatusLabels();
let TAB_TITLES = buildTabTitles();

function refreshI18nLabels() {
  PLATFORM_META = buildPlatformMeta();
  REPEAT_LABELS = buildRepeatLabels();
  TYPE_LABELS = buildTypeLabels();
  STATUS_LABELS = buildStatusLabels();
  TAB_TITLES = buildTabTitles();
  PLATFORM_LABELS.telegram = tt("platform.telegram");
  PLATFORM_LABELS.whatsapp = tt("platform.whatsapp");
  if (typeof applyI18n === "function") applyI18n();
  updateThemeUI();
  updatePlatformChrome();
  const activeTab = document.querySelector(".nav-btn.active")?.dataset?.tab;
  if (activeTab) updateMobileChrome(activeTab);
  refreshAuthStatusLabels();
}

function refreshAuthStatusLabels() {
  const ctx = document.getElementById("platform-context-status");
  if (ctx && ctx.hasAttribute("data-i18n")) ctx.textContent = tt("status.checking");
}

window.addEventListener("localechange", refreshI18nLabels);
let selectedChat = null;
let activeThreadChat = null;
let allChats = [];
let chatFilter = "all";
let refreshTimer = null;
let countdownTimer = null;
let qrPollTimer = null;
let ws = null;
let wsReconnectTimer = null;
let appInitialized = false;
let connectionStates = { telegram: { 1: "disconnected" }, whatsapp: { 1: "disconnected" } };
const tabLoadTimes = {};

function stopBackgroundTimers() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
  if (wsReconnectTimer) { clearInterval(wsReconnectTimer); wsReconnectTimer = null; }
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
}

function getUserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch (_) {
    return "UTC";
  }
}

function localeNumber(n) {
  const loc = window.__LOCALE__ || "en";
  try { return Number(n).toLocaleString(loc); } catch (_) { return String(n); }
}

function formatCountdownRemaining(diff) {
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const sec = Math.floor((diff % 60000) / 1000);
  const parts = [];
  if (h) parts.push(tt("countdown.hours", { n: h }));
  parts.push(tt("countdown.minutes", { n: m }));
  parts.push(tt("countdown.seconds", { n: sec }));
  return tt("countdown.remaining", { time: parts.join("") });
}

const TZ = getUserTimezone();

function getAccountId(platform = currentPlatform) {
  return currentAccountId[platform] || 1;
}

function ensureAccountState(platform, accountId) {
  if (!platformState[platform]) platformState[platform] = {};
  if (!platformState[platform][accountId]) {
    platformState[platform][accountId] = defaultAccountState();
  }
  return platformState[platform][accountId];
}

function withAccountId(url, platform = currentPlatform) {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}account_id=${getAccountId(platform)}`;
}

function withAccountIdFor(url, accountId, platform = currentPlatform) {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}account_id=${accountId ?? getAccountId(platform)}`;
}

function getConnectionState(platform = currentPlatform, accountId) {
  const aid = accountId ?? getAccountId(platform);
  return connectionStates[platform]?.[aid] || "disconnected";
}

function setConnectionState(platform, accountId, status) {
  if (!connectionStates[platform]) connectionStates[platform] = {};
  connectionStates[platform][accountId] = status;
}

function accountInitials(acc) {
  const name = acc.display_name || acc.label || "?";
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return String(name).slice(0, 2).toUpperCase();
}

function connectionStatusLabel(st) {
  return connectionStatusText(st);
}

function connectionBadgeHtml(st) {
  const labels = {
    connected: tt("status.live"),
    connecting: tt("status.connecting"),
    reconnecting: tt("status.reconnecting"),
    qr: tt("status.qr"),
    disconnected: tt("status.disconnected"),
    offline: tt("status.offline"),
  };
  return statusDotHtml(st, labels[st] || connectionStatusText(st));
}


let PLATFORM_LABELS = { telegram: tt("platform.telegram"), whatsapp: tt("platform.whatsapp") };

function platformIconHtml(platform, size = 20) {
  const meta = PLATFORM_META[platform];
  return meta ? platformIcon(platform, size) : icon("messages-square", { size });
}

function getCurrentAccount() {
  const list = accountsCache[currentPlatform] || [];
  return list.find((a) => a.id === getAccountId()) || null;
}

function isMobileView() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function updateMobileChrome(tab) {
  const title = TAB_TITLES[tab] || tt("common.panel");
  const titleEl = document.getElementById("mobile-page-title");
  if (titleEl) titleEl.textContent = title;
  document.querySelectorAll(".mob-nav-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
  });
  updatePlatformChrome();
}

function savePlatformState() {
  const aid = getAccountId(currentPlatform);
  ensureAccountState(currentPlatform, aid);
  platformState[currentPlatform][aid] = {
    activeThreadChat,
    chatListCache: [...chatListCache],
    selectedChat,
    threadMessages: [...threadMessages],
    threadHasMore,
  };
}

function restorePlatformState(platform) {
  const aid = getAccountId(platform);
  ensureAccountState(platform, aid);
  const s = platformState[platform][aid];
  activeThreadChat = s.activeThreadChat;
  chatListCache = s.chatListCache || [];
  selectedChat = s.selectedChat;
  threadMessages = s.threadMessages || [];
  threadHasMore = s.threadHasMore || false;
  allChats = chatListCache.length ? chatListCache : allChats;
}

function invalidatePlatformCache(platform, accountId) {
  const aid = accountId ?? getAccountId(platform);
  ensureAccountState(platform, aid);
  platformState[platform][aid].chatListCache = [];
  if (currentPlatform === platform && getAccountId(platform) === aid) chatListCache = [];
}

function updatePlatformSwitchUI(platform) {
  document.querySelectorAll(".platform-btn").forEach((b) => {
    const on = b.dataset.platform === platform;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  document.querySelectorAll(".mob-plat-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.platform === platform);
  });
  document.querySelectorAll("#platform-tabs-account .filter-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.platform === platform);
  });
  const track = document.getElementById("platform-switch-track");
  if (track) track.dataset.active = platform;
}

function updatePlatformDots() {
  const dotTg = document.getElementById("dot-telegram");
  const dotWa = document.getElementById("dot-whatsapp");
  const tgStates = Object.values(connectionStates.telegram || {});
  const waStates = Object.values(connectionStates.whatsapp || {});
  const tgOnline = tgStates.some((s) => s === "connected");
  const waOnline = waStates.some((s) => s === "connected");
  if (dotTg) dotTg.className = `platform-dot ${tgOnline ? "online tg" : "offline"}`;
  if (dotWa) dotWa.className = `platform-dot ${waOnline ? "online wa" : "offline"}`;
}

function updatePlatformChrome() {
  const meta = PLATFORM_META[currentPlatform];
  document.body.dataset.platform = currentPlatform;
  const miniPlatform = document.getElementById("mini-platform");
  if (miniPlatform) miniPlatform.textContent = meta.label;
  const ctxIcon = document.getElementById("platform-context-icon");
  if (ctxIcon) setIcon(ctxIcon, meta.icon, { size: 20 });
  const ctxName = document.getElementById("platform-context-name");
  if (ctxName) ctxName.textContent = meta.label;
  const composePill = document.getElementById("compose-platform-pill");
  const schedPill = document.getElementById("scheduled-platform-pill");
  if (composePill) composePill.innerHTML = `${platformIconHtml(currentPlatform, 16)} <span>${meta.label}</span>`;
  if (schedPill) schedPill.innerHTML = `${platformIconHtml(currentPlatform, 16)} <span>${meta.label}</span>`;
  const composeSub = document.getElementById("compose-subtitle");
  if (composeSub) composeSub.textContent = meta.composeSubtitle;
  const chatsTitle = document.getElementById("chats-title");
  if (chatsTitle) chatsTitle.textContent = meta.chatsTitle;
  const chatsSub = document.getElementById("chats-subtitle");
  if (chatsSub) chatsSub.textContent = meta.chatsSubtitle;
  document.querySelectorAll(".wa-only").forEach((el) => {
    el.classList.toggle("hidden", currentPlatform !== "whatsapp");
  });
  const ctxSync = document.getElementById("ctx-sync-wa");
  if (ctxSync) ctxSync.classList.toggle("hidden", currentPlatform !== "whatsapp");
  const ring = document.getElementById("platform-status-ring");
  if (ring) ring.dataset.platform = currentPlatform;
  const activeTab = document.querySelector(".tab.active")?.id?.replace("tab-", "") || "dashboard";
  const ctxBar = document.getElementById("platform-context-bar");
  if (ctxBar) ctxBar.classList.toggle("context-dashboard", activeTab === "dashboard");
  updatePlatformSwitchUI(currentPlatform);
  updatePlatformDots();
  updatePlatformContextStatus();
  renderAccountSwitcher();
  const acc = getCurrentAccount();
  const miniVal = document.getElementById("mini-status");
  if (miniVal && acc) {
    miniVal.textContent = acc.display_name || acc.label || connectionStatusLabel(getConnectionState());
  }
}

function updatePlatformContextStatus() {
  const el = document.getElementById("platform-context-status");
  if (!el) return;
  const st = getConnectionState(currentPlatform);
  el.innerHTML = connectionStatusHtml(st);
  el.className = `platform-context-status status-${st}`;
}

async function setPlatform(platform, opts = {}) {
  if (platform === currentPlatform && !opts.force) return;
  if (!PLATFORM_META[platform]) return;
  if (platformSwitching) return;

  platformSwitching = true;
  savePlatformState();

  const panels = document.getElementById("content-panels");
  if (panels && !opts.skipAnimation) panels.classList.add("platform-switching");

  currentPlatform = platform;
  restorePlatformState(platform);

  await loadAccounts(platform);
  updatePlatformChrome();
  updateSelectedChatUI();
  renderRecentChats();
  updateMiniStatus();
  updateConnectionBadge();
  updateWaConnectBanner(currentPlatform === "whatsapp" && getConnectionState("whatsapp") !== "connected");

  const activeTab = document.querySelector(".tab.active")?.id?.replace("tab-", "") || "dashboard";

  if (activeTab === "chats") {
    refreshWaConnectionState();
    if (activeThreadChat) {
      await openThread(activeThreadChat.id, true);
    } else {
      closeThreadUI(false);
      await loadChatThread(false);
    }
  } else if (activeTab === "compose") {
    await loadChats(false);
  } else if (activeTab === "scheduled") {
    await loadScheduled();
  } else if (activeTab === "account") {
    showAccountPanel(platform);
    checkAuthStatus(panelAccountId || getAccountId(platform));
  }

  if (panels && !opts.skipAnimation) {
    requestAnimationFrame(() => {
      panels.classList.remove("platform-switching");
      panels.classList.add("platform-switched");
      setTimeout(() => panels.classList.remove("platform-switched"), 320);
    });
  }

  if (!opts.silent) {
    toast(`${PLATFORM_META[platform].label}`, "info");
  }

  platformSwitching = false;
}

function closeThreadUI(clearState = true) {
  if (clearState) {
    activeThreadChat = null;
    threadMessages = [];
  }
  setChatThreadOpen(false);
  document.getElementById("chat-header")?.classList.add("hidden");
  document.getElementById("chat-compose")?.classList.add("hidden");
  document.getElementById("load-more-msgs")?.classList.add("hidden");
  const thread = document.getElementById("message-thread");
  if (thread && !activeThreadChat) {
    thread.innerHTML = emptyState("message-square-text", tt("empty.selectChat"));
    thread.classList.remove("wa-thread");
  }
}

function toggleMobileSidebar() {
  const sidebar = document.getElementById("sidebar");
  const open = sidebar?.classList.toggle("open");
  document.getElementById("sidebar-backdrop")?.classList.toggle("hidden", !open);
  document.body.classList.toggle("sidebar-open", !!open);
}

function closeMobileSidebar() {
  document.getElementById("sidebar")?.classList.remove("open");
  document.getElementById("sidebar-backdrop")?.classList.add("hidden");
  document.body.classList.remove("sidebar-open");
}

function shouldRefreshTab(tab, ttlMs = 15000) {
  const now = Date.now();
  if (!tabLoadTimes[tab] || now - tabLoadTimes[tab] > ttlMs) {
    tabLoadTimes[tab] = now;
    return true;
  }
  return false;
}

function mobileNav(tab) {
  switchTab(tab);
  closeMobileSidebar();
}

function refreshCurrentTab() {
  const active = document.querySelector(".tab.active");
  if (!active) return;
  const tab = active.id.replace("tab-", "");
  delete tabLoadTimes[tab];
  if (tab === "dashboard") loadStats();
  if (tab === "chats") loadChatThread(true);
  if (tab === "compose") loadChats(true);
  if (tab === "scheduled") loadScheduled();
  if (tab === "templates") loadTemplates();
  if (tab === "account") checkAuthStatus(panelAccountId || getAccountId());
  toast(tt("toast.refreshed"), "info");
}

function setChatThreadOpen(open) {
  const layout = document.getElementById("chat-layout");
  const backBtn = document.getElementById("chat-back-btn");
  if (layout) layout.classList.toggle("thread-open", open && isMobileView());
  if (backBtn) backBtn.classList.toggle("hidden", !open || !isMobileView());
}

function closeThreadMobile() {
  activeThreadChat = null;
  threadMessages = [];
  threadHasMore = false;
  savePlatformState();
  setChatThreadOpen(false);
  document.getElementById("chat-header")?.classList.add("hidden");
  document.getElementById("chat-compose")?.classList.add("hidden");
  document.getElementById("message-thread").innerHTML = emptyState("message-square-text", tt("empty.selectChat"));
  loadChatThread();
}

// ─── API ───────────────────────────────────────────────
function toastT(key, type = "info", vars) {
  toast(tt(key, vars), type);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(translateError(data.detail || data.error));
  return data;
}

function toast(msg, type = "info") {
  const c = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = translateError(msg);
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showStatus(id, msg, type = "") {
  const el = document.getElementById(id);
  if (el) { el.textContent = translateError(msg); el.className = `status-msg ${type}`; }
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function formatDate(iso) {
  if (!iso) return "-";
  const loc = typeof getLocale === "function" ? getLocale() : "en";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(loc, { timeZone: TZ, dateStyle: "short", timeStyle: "short" });
}

function formatTs(ts) {
  if (!ts) return "";
  const loc = typeof getLocale === "function" ? getLocale() : "en";
  return new Date(ts * 1000).toLocaleString(loc, { timeZone: TZ, hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

// Türkiye saati datetime-local → ISO with +03:00 offset
function localDateTimeToISO(localStr) {
  if (!localStr) return null;
  return localStr + ":00+03:00";
}

// ─── Platform ────────────────────────────────────────
// setPlatform defined above with full UX

function switchTab(tab) {
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${tab}`));
  updateMobileChrome(tab);
  if (tab === "scheduled" && shouldRefreshTab("scheduled")) loadScheduled();
  if (tab === "dashboard" && shouldRefreshTab("dashboard")) loadStats();
  if (tab === "templates" && shouldRefreshTab("templates")) loadTemplates();
  if (tab === "chats") {
    if (activeThreadChat) {
      setChatThreadOpen(true);
      openThread(activeThreadChat.id, true);
    } else {
      setChatThreadOpen(false);
      refreshWaConnectionState();
      loadChatThread(false);
    }
  }
  if (tab === "compose") {
    loadChats(false);
    renderRecentChats();
  }
  if (tab === "account") {
    showAccountPanel(currentPlatform);
    checkAuthStatus(panelAccountId || getAccountId());
    if (!document.getElementById("developer-card")?.classList.contains("collapsed")) {
      loadDeveloperTools();
    }
  }
  updatePlatformChrome();
  closeMobileSidebar();
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function showAccountPanel(platform) {
  if (platform !== currentPlatform) {
    setPlatform(platform, { silent: true, skipAnimation: true });
    return;
  }
  updatePlatformSwitchUI(platform);
  loadAccounts(platform).then(() => renderAccountsList(platform));
}

async function loadAccounts(platform = currentPlatform) {
  try {
    const list = await api(`/api/accounts?platform=${platform}`);
    accountsCache[platform] = list;
    if (list.length) {
      const cur = list.find((a) => a.id === currentAccountId[platform]);
      if (!cur) {
        const def = list.find((a) => a.is_default) || list[0];
        currentAccountId[platform] = def.id;
      }
      for (const acc of list) {
        ensureAccountState(platform, acc.id);
        setConnectionState(platform, acc.id, acc.status || "disconnected");
      }
    }
    if (platform === currentPlatform) renderAccountSwitcher();
    return list;
  } catch (e) {
    console.error(e);
    return accountsCache[platform] || [];
  }
}

function renderAccountSwitcher() {
  const track = document.getElementById("account-switcher-track");
  const bar = document.getElementById("account-switcher");
  if (!track || !bar) return;
  const accounts = accountsCache[currentPlatform] || [];
  bar.classList.toggle("hidden", !accounts.length && false);
  if (!accounts.length) {
    track.innerHTML = `<span class="account-switcher-empty muted small">${tt("account.noAccountsHint")}</span>`;
    return;
  }
  track.innerHTML = accounts.map((acc) => {
    const active = acc.id === getAccountId();
    const st = getConnectionState(currentPlatform, acc.id);
    return `<button type="button" class="account-pill${active ? " active" : ""}" data-account-id="${acc.id}" onclick="setAccount(${acc.id})" title="${escapeHtml(acc.label)}">
      <span class="account-pill-avatar">${escapeHtml(accountInitials(acc))}</span>
      <span class="account-pill-dot status-${st}"></span>
      <span class="account-pill-label">${escapeHtml(acc.label)}</span>
    </button>`;
  }).join("");
}

async function setAccount(accountId, opts = {}) {
  if (accountId === getAccountId() && !opts.force) return;
  if (accountSwitching || platformSwitching) return;

  accountSwitching = true;
  savePlatformState();

  const panels = document.getElementById("content-panels");
  if (panels && !opts.skipAnimation) panels.classList.add("platform-switching");

  currentAccountId[currentPlatform] = accountId;
  restorePlatformState(currentPlatform);

  renderAccountSwitcher();
  updatePlatformChrome();
  updateSelectedChatUI();
  renderRecentChats();
  updateMiniStatus();
  updateConnectionBadge();
  updateWaConnectBanner(currentPlatform === "whatsapp" && getConnectionState("whatsapp", accountId) !== "connected");

  const activeTab = document.querySelector(".tab.active")?.id?.replace("tab-", "") || "dashboard";

  if (activeTab === "chats") {
    refreshWaConnectionState();
    if (activeThreadChat) {
      await openThread(activeThreadChat.id, true);
    } else {
      closeThreadUI(false);
      await loadChatThread(false);
    }
  } else if (activeTab === "compose") {
    await loadChats(false);
  } else if (activeTab === "scheduled") {
    await loadScheduled();
  } else if (activeTab === "account") {
    showAccountPanel(currentPlatform);
    await checkAuthStatus(accountId);
  }

  if (panels && !opts.skipAnimation) {
    requestAnimationFrame(() => {
      panels.classList.remove("platform-switching");
      panels.classList.add("platform-switched");
      setTimeout(() => panels.classList.remove("platform-switched"), 320);
    });
  }

  if (!opts.silent) {
    const acc = (accountsCache[currentPlatform] || []).find((a) => a.id === accountId);
    toast(acc ? acc.label : tt("toast.accountSwitched"), "info");
  }

  accountSwitching = false;
}

function promptAddAccount() {
  const overlay = document.getElementById("add-account-overlay");
  const title = document.getElementById("add-account-title");
  const subtitle = document.getElementById("add-account-subtitle");
  const input = document.getElementById("add-account-label");
  const meta = PLATFORM_META[currentPlatform];
  if (title) title.innerHTML = `${icon(meta.icon, { size: 20 })} ${tt("account.add")}`;
  if (subtitle) subtitle.textContent = tt("account.createFor", { platform: meta.label });
  if (input) {
    input.value = "";
    const n = (accountsCache[currentPlatform] || []).length + 1;
    input.placeholder = `${meta.label} ${n}`;
  }
  overlay?.classList.remove("hidden");
  input?.focus();
}

function closeAddAccountModal() {
  document.getElementById("add-account-overlay")?.classList.add("hidden");
}

async function confirmAddAccount() {
  const input = document.getElementById("add-account-label");
  const label = (input?.value || "").trim() || input?.placeholder || tt("account.defaultNewName");
  const btn = document.getElementById("btn-confirm-add-account");
  if (btn) btn.disabled = true;
  try {
    const acc = await api("/api/accounts", {
      method: "POST",
      body: JSON.stringify({ platform: currentPlatform, label }),
    });
    closeAddAccountModal();
    ensureAccountState(currentPlatform, acc.id);
    await loadAccounts(currentPlatform);
    renderAccountsList(currentPlatform);
    await setAccount(acc.id, { silent: true });
    toastT("toast.accountAdded", "success", { name: acc.label });
    switchTab("account");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderAccountsList(platform) {
  const container = document.getElementById("accounts-list");
  if (!container) return;
  const accounts = accountsCache[platform] || [];
  if (!accounts.length) {
    container.innerHTML = emptyState("user", `${tt("account.noAccountsHtml")} <button class="btn ghost small" onclick="promptAddAccount()">+ ${tt("common.add")}</button>`);
    document.getElementById("account-detail-panel")?.classList.add("hidden");
    return;
  }
  container.innerHTML = accounts.map((acc) => {
    const st = getConnectionState(platform, acc.id);
    const isActive = acc.id === getAccountId() && platform === currentPlatform;
    const stText = st === "connected" ? tt("status.connected") : (st === "qr" ? tt("status.qr") : tt("status.disconnected"));
    return `<div class="account-card${isActive ? " active-account" : ""}${acc.is_default ? " is-default" : ""}">
      <div class="account-card-avatar">
        ${escapeHtml(accountInitials(acc))}
        <span class="account-card-status-dot status-${st}"></span>
      </div>
      <div class="account-card-body">
        <strong>${escapeHtml(acc.label)}</strong>
        <div class="account-card-meta">${escapeHtml(acc.display_name || acc.phone_masked || stText)}</div>
        <div class="account-card-badges">
          ${acc.is_default ? `<span class="account-badge default">${tt("account.defaultBadge")}</span>` : ""}
          <span class="account-badge ${st === "connected" ? "connected" : "disconnected"}">${stText}</span>
        </div>
      </div>
      <div class="account-card-actions">
        ${!isActive ? `<button class="btn ghost small" onclick="setAccount(${acc.id})">${tt("account.switch")}</button>` : ""}
        ${!acc.is_default ? `<button class="btn ghost small" onclick="setDefaultAccount(${acc.id})">${tt("account.defaultBadge")}</button>` : ""}
        <button class="btn secondary small" onclick="openAccountConnect(${acc.id})">${st === "connected" ? tt("account.manage") : tt("account.connectShort")}</button>
        ${accounts.length > 1 ? `<button class="btn small danger" onclick="removeAccount(${acc.id})">${tt("account.removeShort")}</button>` : ""}
      </div>
    </div>`;
  }).join("");
}

async function setDefaultAccount(accountId) {
  try {
    await api(`/api/accounts/${accountId}/default`, { method: "POST" });
    await loadAccounts(currentPlatform);
    renderAccountsList(currentPlatform);
    renderAccountSwitcher();
    toastT("toast.defaultUpdated", "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function removeAccount(accountId) {
  const acc = (accountsCache[currentPlatform] || []).find((a) => a.id === accountId);
  if (!acc) return;
  if (!confirm(tt("confirm.removeAccount", { name: acc.label }))) return;
  try {
    await api(`/api/accounts/${accountId}`, { method: "DELETE" });
    delete platformState[currentPlatform]?.[accountId];
    delete connectionStates[currentPlatform]?.[accountId];
    if (getAccountId() === accountId) {
      const remaining = (accountsCache[currentPlatform] || []).filter((a) => a.id !== accountId);
      if (remaining.length) currentAccountId[currentPlatform] = remaining[0].id;
    }
    await loadAccounts(currentPlatform);
    if (getAccountId() === accountId) {
      const list = accountsCache[currentPlatform] || [];
      if (list.length) currentAccountId[currentPlatform] = list[0].id;
    }
    renderAccountsList(currentPlatform);
    renderAccountSwitcher();
    if (panelAccountId === accountId) {
      panelAccountId = null;
      document.getElementById("account-detail-panel")?.classList.add("hidden");
    }
    toastT("toast.accountRemoved", "info");
  } catch (e) {
    toast(e.message, "error");
  }
}

function openAccountConnect(accountId) {
  panelAccountId = accountId;
  if (accountId !== getAccountId()) {
    setAccount(accountId, { silent: true, skipAnimation: true }).then(() => {
      showAccountConnectPanel(accountId);
    });
    return;
  }
  showAccountConnectPanel(accountId);
}

function setAccountFromPanel() {
  if (panelAccountId) setAccount(panelAccountId);
}

async function showAccountConnectPanel(accountId) {
  const panel = document.getElementById("account-detail-panel");
  panel?.classList.remove("hidden");
  const acc = (accountsCache[currentPlatform] || []).find((a) => a.id === accountId);
  const label = acc?.label || `Hesap ${accountId}`;
  document.getElementById("auth-connected-label").textContent = `— ${label}`;
  document.getElementById("auth-form-label").textContent = `— ${label}`;
  document.querySelectorAll(".tg-auth-field").forEach((el) => {
    el.classList.toggle("hidden", currentPlatform !== "telegram");
  });
  document.querySelectorAll(".wa-auth-field").forEach((el) => {
    el.classList.toggle("hidden", currentPlatform !== "whatsapp");
  });
  document.getElementById("auth-status")?.classList.toggle("hidden", currentPlatform === "whatsapp");
  document.getElementById("wa-auth-status")?.classList.toggle("hidden", currentPlatform !== "whatsapp");
  const logoutBtn = document.querySelector("#auth-connected .btn.danger");
  if (logoutBtn) {
    logoutBtn.textContent = currentPlatform === "whatsapp" ? tt("account.disconnect") : tt("account.logout");
    logoutBtn.onclick = currentPlatform === "whatsapp" ? waLogout : logout;
  }
  await checkAuthStatus(accountId);
  if (currentPlatform === "telegram") await loadTelegramCredentials(accountId);
}

// ─── Auth ────────────────────────────────────────────
let panelSetupMode = false;

function updateSafeModeBanner(dryRun) {
  const el = document.getElementById("safe-mode-banner");
  if (el) el.classList.toggle("hidden", !dryRun);
}

function maskPhoneDisplay(phone) {
  if (!phone) return "";
  const digits = String(phone).replace(/\D/g, "");
  if (digits.length < 4) return "***";
  const prefix = String(phone).startsWith("+") ? String(phone).slice(0, 4) : digits.slice(0, 3);
  return `${prefix}***${digits.slice(-2)}`;
}

function togglePasswordVisibility() {
  const input = document.getElementById("panel-password");
  const btn = document.getElementById("panel-password-toggle");
  if (!input || !btn) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  setIcon(btn, show ? "eye-off" : "eye", { size: 18 });
  btn.setAttribute("aria-label", show ? tt("login.passwordHide") : tt("login.passwordShow"));
}

function scorePassword(pw) {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Za-z]/.test(pw) && /\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score;
}

function updatePasswordStrength() {
  const pw = document.getElementById("panel-password")?.value || "";
  const bar = document.querySelector(".password-strength-bar");
  const text = document.getElementById("password-strength-text");
  if (!bar || !text) return;
  const score = scorePassword(pw);
  bar.classList.remove("weak", "fair", "strong");
  if (!pw) {
    text.textContent = tt("login.passwordHint");
    return;
  }
  if (score <= 1) { bar.classList.add("weak"); text.textContent = tt("login.passwordWeak"); }
  else if (score <= 2) { bar.classList.add("fair"); text.textContent = tt("login.passwordFair"); }
  else { bar.classList.add("strong"); text.textContent = tt("login.passwordStrong"); }
}

function showLoginOverlay(setupRequired) {
  panelSetupMode = setupRequired;
  const overlay = document.getElementById("login-overlay");
  const title = document.getElementById("login-title");
  const subtitle = document.getElementById("login-subtitle");
  const setupFields = document.getElementById("setup-fields");
  const loginFields = document.getElementById("login-fields");
  const usernameField = document.getElementById("username-field");
  const setupExtra = document.getElementById("setup-password-extra");
  const passwordLabel = document.getElementById("password-label");
  const btn = document.getElementById("panel-login-btn");

  overlay.classList.remove("hidden");
  initIcons(overlay);
  if (setupRequired) {
    title.textContent = tt("login.setupTitle");
    subtitle.textContent = tt("login.setupSubtitle");
    setupFields.classList.remove("hidden");
    loginFields.classList.remove("hidden");
    usernameField.classList.add("hidden");
    setupExtra?.classList.remove("hidden");
    if (passwordLabel) passwordLabel.textContent = tt("login.passwordCreate");
    btn.textContent = tt("login.setupSubmit");
    document.getElementById("panel-password")?.setAttribute("autocomplete", "new-password");
  } else {
    title.textContent = tt("login.title");
    subtitle.textContent = tt("login.subtitle");
    setupFields.classList.add("hidden");
    loginFields.classList.remove("hidden");
    usernameField.classList.toggle("hidden", false);
    setupExtra?.classList.add("hidden");
    if (passwordLabel) passwordLabel.textContent = tt("login.password");
    btn.textContent = tt("login.submit");
    document.getElementById("panel-password")?.setAttribute("autocomplete", "current-password");
  }
  updatePasswordStrength();
}

async function checkPanelAuth() {
  const s = await api("/api/panel/status");
  updateSafeModeBanner(s.dry_run);
  updatePanelUserLine(s);
  if (s.setup_required) {
    showLoginOverlay(true);
    return false;
  }
  if (s.protected && !s.authenticated) {
    showLoginOverlay(false);
    return false;
  }
  return true;
}

function updatePanelUserLine(status) {
  const line = document.getElementById("panel-user-line");
  const label = document.getElementById("panel-user-label");
  const logoutBtn = document.getElementById("panel-logout-btn");
  if (!line || !label) return;
  const show = status?.authenticated && status?.username;
  line.classList.toggle("hidden", !show);
  if (logoutBtn) logoutBtn.classList.toggle("hidden", !status?.protected);
  if (show) label.textContent = status.username;
}

async function panelLogin() {
  const err = document.getElementById("login-error");
  const btn = document.getElementById("panel-login-btn");
  err.classList.add("hidden");
  try {
    if (panelSetupMode) {
      const username = document.getElementById("panel-username").value.trim();
      const password = document.getElementById("panel-password").value;
      const confirm = document.getElementById("panel-password-confirm")?.value || "";
      if (password !== confirm) throw new Error(tt("login.passwordMismatch"));
      if (scorePassword(password) < 2) throw new Error(tt("login.passwordTooWeak"));
      btn.disabled = true;
      await api("/api/panel/setup", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
    } else {
      const username = document.getElementById("panel-username-login")?.value.trim() || undefined;
      const password = document.getElementById("panel-password").value;
      btn.disabled = true;
      await api("/api/panel/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
    }
    document.getElementById("login-overlay").classList.add("hidden");
    await init();
    try {
      const s = await api("/api/panel/status");
      if (s.dry_run) toastT("toast.testModeWelcome", "info");
    } catch (_) {}
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove("hidden");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function panelLogout() {
  try {
    await api("/api/panel/logout", { method: "POST" });
    if (ws) { ws.close(); ws = null; }
    stopBackgroundTimers();
    appInitialized = false;
    showLoginOverlay(false);
    await checkPanelAuth();
    toast(tt("toast.logout"), "info");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function updateMiniStatus() {
  try {
    const aid = getAccountId();
    if (currentPlatform === "telegram") {
      const s = await api(withAccountId("/api/auth/status"));
      setConnectionState("telegram", aid, s.connection_state || (s.connected ? "connected" : "disconnected"));
      const dot = document.getElementById("status-dot");
      const val = document.getElementById("mini-status");
      if (s.connected) {
        dot.className = "dot online";
        val.textContent = s.user?.username ? `@${s.user.username}` : s.user?.first_name || tt("status.connectedShort");
      } else {
        dot.className = "dot offline";
        val.textContent = tt("status.disconnected");
      }
    } else {
      const s = await api(withAccountId("/api/whatsapp/auth/status"));
      const st = s.connected ? "connected" : (s.status || "disconnected");
      setConnectionState("whatsapp", aid, st);
      const dot = document.getElementById("status-dot");
      const val = document.getElementById("mini-status");
      if (s.connected) {
        dot.className = "dot whatsapp-online";
        val.textContent = s.user?.name || tt("status.connectedShort");
      } else if (!s.bridge_running) {
        dot.className = "dot offline";
        val.textContent = tt("status.offline");
      } else {
        dot.className = "dot offline";
        val.textContent = s.status === "qr" ? tt("status.qr") : tt("status.disconnected");
      }
    }
    updateConnectionBadge();
    renderAccountSwitcher();
  } catch (_) {}
}

async function checkAuthStatus(accountId) {
  const aid = accountId ?? panelAccountId ?? getAccountId();
  try {
    if (currentPlatform === "telegram") {
      const s = await api(withAccountIdFor("/api/auth/status", aid, "telegram"));
      setConnectionState("telegram", aid, s.connection_state || (s.connected ? "connected" : "disconnected"));
      document.getElementById("auth-connected").style.display = s.connected ? "block" : "none";
      document.getElementById("auth-form").style.display = s.connected ? "none" : "block";
      if (s.connected && s.user) {
        const phone = s.user.phone ? maskPhoneDisplay(s.user.phone) : "";
        document.getElementById("user-info").innerHTML = `<strong>${escapeHtml(s.user.first_name)}</strong><br>@${escapeHtml(s.user.username || "-")}${phone ? `<br>${escapeHtml(phone)}` : ""}`;
      }
    } else {
      const ws = await api(withAccountIdFor("/api/whatsapp/auth/status", aid, "whatsapp"));
      const st = ws.connected ? "connected" : (ws.status || "disconnected");
      setConnectionState("whatsapp", aid, st);
      document.getElementById("auth-connected").style.display = ws.connected ? "block" : "none";
      document.getElementById("auth-form").style.display = ws.connected ? "none" : "block";
      if (ws.connected && ws.user) {
        const phone = ws.user.phone ? maskPhoneDisplay(ws.user.phone) : (ws.user.id || "");
        document.getElementById("user-info").innerHTML = `<strong>${escapeHtml(ws.user.name || "")}</strong><br>${escapeHtml(phone)}`;
      }
      loadWaStats(aid);
      updateWaConnectBanner(!ws.connected);
    }
    if (aid === getAccountId()) updateMiniStatus();
    renderAccountsList(currentPlatform);
    renderAccountSwitcher();
  } catch (e) { console.error(e); }
}

// Telegram auth
async function loadTelegramCredentials(accountId) {
  const aid = accountId ?? panelAccountId ?? getAccountId();
  try {
    const creds = await api(withAccountIdFor("/api/credentials/telegram", aid, "telegram"));
    const statusEl = document.getElementById("credentials-status");
    const apiIdEl = document.getElementById("auth-api-id");
    const apiHashEl = document.getElementById("auth-api-hash");
    const phoneEl = document.getElementById("auth-phone");
    if (phoneEl && creds.phone_masked) {
      phoneEl.placeholder = `${creds.phone_masked} (${tt("auth.phonePlaceholder")})`;
      phoneEl.value = "";
    }
    if (creds.configured) {
      if (apiIdEl) apiIdEl.value = creds.api_id;
      if (apiHashEl) {
        apiHashEl.placeholder = creds.api_hash_masked || tt("auth.hashPlaceholder");
        apiHashEl.value = "";
      }
      if (statusEl) {
        statusEl.style.display = "block";
        statusEl.innerHTML = `${icon("lock", { size: 14 })} ${tt("auth.savedLine", { app: escapeHtml(creds.app_name || "mesaj"), id: creds.api_id, hash: escapeHtml(creds.api_hash_masked) })}`;
      }
    }
  } catch (_) {}
}

async function saveTelegramCredentials() {
  const aid = panelAccountId ?? getAccountId();
  try {
    const apiId = parseInt(document.getElementById("auth-api-id").value, 10);
    const apiHash = document.getElementById("auth-api-hash").value.trim();
    const phone = document.getElementById("auth-phone").value.trim();
    if (!apiId) { showStatus("auth-status", tt("auth.apiIdRequired"), "error"); return; }
    if (!apiHash) { showStatus("auth-status", tt("auth.enterHash"), "error"); return; }
    await api(withAccountIdFor("/api/credentials/telegram", aid, "telegram"), {
      method: "PUT",
      body: JSON.stringify({ api_id: apiId, api_hash: apiHash, app_name: "mesaj", short_name: "mesaj", phone, account_id: aid }),
    });
    toastT("toast.credentialsSaved", "success");
    await loadTelegramCredentials(aid);
  } catch (e) { showStatus("auth-status", e.message, "error"); }
}

async function startAuth() {
  const aid = panelAccountId ?? getAccountId();
  try {
    const body = { phone: document.getElementById("auth-phone").value.trim() };
    const apiId = document.getElementById("auth-api-id").value;
    const apiHash = document.getElementById("auth-api-hash").value.trim();
    if (apiId) body.api_id = parseInt(apiId);
    if (apiHash) body.api_hash = apiHash;
    const r = await api(withAccountIdFor("/api/auth/start", aid, "telegram"), { method: "POST", body: JSON.stringify(body) });
    if (r.status === "already_authorized") { toastT("toast.alreadyConnected", "success"); return checkAuthStatus(aid); }
    document.getElementById("code-step").classList.remove("hidden");
    showStatus("auth-status", tt("auth.enterCode"), "success");
  } catch (e) { showStatus("auth-status", e.message, "error"); }
}

async function verifyCode() {
  const aid = panelAccountId ?? getAccountId();
  try {
    const r = await api(withAccountIdFor("/api/auth/verify-code", aid, "telegram"), { method: "POST", body: JSON.stringify({ code: document.getElementById("auth-code").value.trim() }) });
    if (r.status === "password_required") { document.getElementById("password-step").classList.remove("hidden"); return; }
    toastT("toast.telegramConnected", "success");
    await finishAccountSetupIfConnected();
    checkAuthStatus(aid);
  } catch (e) { showStatus("auth-status", e.message, "error"); }
}

async function verifyPassword() {
  const aid = panelAccountId ?? getAccountId();
  try {
    await api(withAccountIdFor("/api/auth/verify-password", aid, "telegram"), { method: "POST", body: JSON.stringify({ password: document.getElementById("auth-password").value }) });
    toastT("toast.telegramConnected", "success");
    await finishAccountSetupIfConnected();
    checkAuthStatus(aid);
  } catch (e) { showStatus("auth-status", e.message, "error"); }
}

async function logout() {
  const aid = panelAccountId ?? getAccountId();
  if (!confirm(tt("confirm.telegramLogout"))) return;
  await api(withAccountIdFor("/api/auth/logout", aid, "telegram"), { method: "POST" });
  toastT("toast.telegramLogout", "info");
  checkAuthStatus(aid);
}

// WhatsApp QR
function openQrModal(accountId) {
  qrAccountId = accountId ?? panelAccountId ?? getAccountId();
  document.getElementById("qr-overlay").classList.remove("hidden");
  const frame = document.getElementById("qr-frame");
  const status = document.getElementById("qr-status");
  frame.innerHTML = `<div class="qr-placeholder"><span class="loading"></span><p>${tt("qr.preparing")}</p></div>`;
  api(withAccountIdFor("/api/whatsapp/auth/start", qrAccountId, "whatsapp"), { method: "POST" }).catch(() => {});

  async function tick() {
    try {
      const s = await api(withAccountIdFor("/api/whatsapp/auth/status", qrAccountId, "whatsapp"));
      setConnectionState("whatsapp", qrAccountId, s.connected ? "connected" : (s.status || "disconnected"));
      if (s.connected) {
        closeQrModal();
        toastT("toast.whatsappConnected", "success");
        await finishAccountSetupIfConnected();
        invalidatePlatformCache("whatsapp", qrAccountId);
        checkAuthStatus(qrAccountId);
        if (qrAccountId === getAccountId()) updateWaConnectBanner(false);
        if (currentPlatform === "whatsapp" && qrAccountId === getAccountId()) {
          loadChatThread(true);
          syncAllMessages(true);
        }
        return;
      }
      const qr = await api(withAccountIdFor("/api/whatsapp/auth/qr", qrAccountId, "whatsapp"));
      if (qr.qr) {
        frame.innerHTML = `<img src="${qr.qr}" alt="WhatsApp QR" class="wa-qr-img" />`;
        status.textContent = tt("qr.scan");
      } else {
        status.textContent = qr.message || tt("qr.preparing");
      }
    } catch (e) { status.textContent = e.message; }
  }
  tick();
  if (qrPollTimer) clearInterval(qrPollTimer);
  qrPollTimer = setInterval(tick, 2000);
}

function closeQrModal() {
  document.getElementById("qr-overlay").classList.add("hidden");
  if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
  qrAccountId = null;
}

async function waLogout() {
  const aid = panelAccountId ?? getAccountId();
  if (!confirm(tt("confirm.waDisconnect"))) return;
  await api(withAccountIdFor("/api/whatsapp/auth/logout", aid, "whatsapp"), { method: "POST" });
  invalidatePlatformCache("whatsapp", aid);
  if (aid === getAccountId()) {
    activeThreadChat = null;
    threadMessages = [];
    threadHasMore = false;
    ensureAccountState("whatsapp", aid);
    platformState.whatsapp[aid].activeThreadChat = null;
    platformState.whatsapp[aid].threadMessages = [];
    savePlatformState();
  }
  toastT("toast.waDisconnected", "info");
  checkAuthStatus(aid);
  if (aid === getAccountId()) updateWaConnectBanner(true);
  if (document.getElementById("tab-chats")?.classList.contains("active") && aid === getAccountId()) loadChatThread(true);
}

async function loadWaStats(accountId) {
  const aid = accountId ?? panelAccountId ?? getAccountId();
  try {
    const s = await api(withAccountIdFor("/api/whatsapp/stats", aid, "whatsapp"));
    const box = document.getElementById("wa-stats-box");
    if (!box) return;
    if (s.connected) {
      box.classList.remove("hidden");
      document.getElementById("wa-stat-chats").textContent = tt("account.waStatChats", { count: s.bridge_chats || s.panel_conversations || 0 });
      document.getElementById("wa-stat-msgs").textContent = tt("account.waStatMsgs", { count: s.bridge_messages || 0 });
    } else {
      box.classList.add("hidden");
    }
  } catch (_) {}
}

function updateWaConnectBanner(show) {
  const el = document.getElementById("wa-connect-banner");
  if (!el) return;
  el.classList.toggle("hidden", !show || currentPlatform !== "whatsapp");
}

async function refreshWaConnectionState() {
  if (currentPlatform !== "whatsapp") {
    updateWaConnectBanner(false);
    return;
  }
  try {
    const aid = getAccountId();
    const s = await api(withAccountId("/api/whatsapp/auth/status", "whatsapp"));
    updateWaConnectBanner(!s.connected);
    setConnectionState("whatsapp", aid, s.connected ? "connected" : (s.status || "disconnected"));
    updateConnectionBadge();
    renderAccountSwitcher();
  } catch (_) {
    updateWaConnectBanner(true);
  }
}

// ─── Stats ───────────────────────────────────────────
async function loadStats() {
  try {
    const s = await api("/api/stats");
    document.getElementById("stat-pending").textContent = s.pending;
    document.getElementById("stat-sent").textContent = s.sent;
    document.getElementById("stat-failed").textContent = s.failed;
    document.getElementById("stat-scheduler").textContent = s.scheduler.running ? tt("status.schedulerOn") : tt("status.schedulerOff");
    document.getElementById("stat-scheduler").classList.toggle("success", s.scheduler.running);
    document.getElementById("pending-badge").classList.toggle("hidden", !s.pending);
    if (s.pending) document.getElementById("pending-badge").textContent = s.pending;
    const mobBadge = document.getElementById("mobile-pending-badge");
    if (mobBadge) {
      mobBadge.classList.toggle("hidden", !s.pending);
      if (s.pending) mobBadge.textContent = s.pending;
    }

    const tgEl = document.getElementById("dash-tg-status");
    const waEl = document.getElementById("dash-wa-status");
    const tgCard = document.getElementById("dash-tg");
    const waCard = document.getElementById("dash-wa");
    tgEl.innerHTML = s.telegram_connected
      ? statusDotHtml("connected", tt("status.connectedShort"))
      : statusDotHtml("disconnected", tt("status.disconnected"));
    waEl.innerHTML = s.whatsapp_connected
      ? statusDotHtml("connected", tt("status.connectedShort"))
      : statusDotHtml(s.whatsapp_bridge ? "connecting" : "offline", s.whatsapp_bridge ? tt("dashboard.waitingConnect") : tt("status.offline"));
    tgCard.classList.toggle("online", s.telegram_connected);
    waCard.classList.toggle("online", s.whatsapp_connected);

    const nextBox = document.getElementById("next-run-info");
    if (s.scheduler.next_run) {
      nextBox.innerHTML = `<div class="muted small">${tt("dashboard.nextRun")}</div><div class="next-run-time">${formatDate(s.scheduler.next_run)}</div><div class="countdown" id="countdown"></div>`;
      startCountdown(new Date(s.scheduler.next_run));
    } else {
      nextBox.innerHTML = `<p class="muted">${tt("dashboard.noScheduled")}</p>`;
    }
  } catch (e) { console.error(e); }
}

function startCountdown(target) {
  const el = document.getElementById("countdown");
  if (!el) return;
  if (countdownTimer) clearInterval(countdownTimer);
  function tick() {
    const diff = target - Date.now();
    if (diff <= 0) { el.textContent = tt("countdown.now"); return; }
    el.textContent = formatCountdownRemaining(diff);
  }
  tick();
  countdownTimer = setInterval(tick, 1000);
}

// ─── Chats (compose) ─────────────────────────────────
async function loadChats(refresh = false) {
  const list = document.getElementById("chat-list");
  list.innerHTML = `<div class="empty-state"><span class="loading"></span><p>${tt("common.loading")}</p></div>`;
  try {
    const url = withAccountId(`/api/conversations?platform=${currentPlatform}${refresh ? "&refresh=true" : ""}`);
    allChats = await api(url);
    if (!allChats.length) {
      allChats = await api(withAccountId(`/api/chats?platform=${currentPlatform}${refresh ? "&refresh=true" : ""}`));
    }
    renderChats();
  } catch (e) {
    list.innerHTML = emptyState("alert-triangle", escapeHtml(e.message));
  }
}

function renderChats() {
  const list = document.getElementById("chat-list");
  const search = document.getElementById("chat-search")?.value || "";
  let filtered = allChats;
  if (chatFilter !== "all") filtered = filtered.filter((c) => c.type === chatFilter);
  filtered = filterChats(filtered, search.toLowerCase());
  if (!filtered.length) { list.innerHTML = emptyState("search", tt("chats.noChats")); return; }
  list.innerHTML = filtered.map((c) => `
    <div class="chat-item ${selectedChat?.id === c.id ? "selected" : ""}" data-chat-id="${encodeURIComponent(c.id)}" onclick="selectChatFromEl(this)">
      <div class="chat-item-name">${escapeHtml(c.name)}</div>
      <span class="chat-type">${TYPE_LABELS[c.type] || c.type}</span>
    </div>`).join("");
}

function selectChatFromEl(el) {
  selectChat(decodeURIComponent(el.dataset.chatId));
}

function selectChat(id) {
  selectedChat = allChats.find((c) => c.id === id);
  updateSelectedChatUI();
  saveRecentChat(selectedChat);
  renderChats();
}

function updateSelectedChatUI() {
  const box = document.getElementById("selected-chat-box");
  const searchWrap = document.getElementById("compose-recipient-search");
  const list = document.getElementById("chat-list");
  if (!box) return;
  if (selectedChat) {
    box.classList.remove("hidden");
    if (searchWrap) searchWrap.classList.add("hidden");
    if (list) list.classList.add("collapsed");
    document.getElementById("selected-chat-name").textContent = selectedChat.name;
    document.getElementById("selected-chat-type").textContent = TYPE_LABELS[selectedChat.type] || selectedChat.type;
    const av = document.getElementById("selected-chat-avatar");
    if (av) setIcon(av, PLATFORM_META[currentPlatform]?.icon || "messages-square", { size: 18 });
  } else {
    box.classList.add("hidden");
    if (searchWrap) searchWrap.classList.remove("hidden");
    if (list) list.classList.remove("collapsed");
  }
}

function clearSelectedChat() {
  selectedChat = null;
  updateSelectedChatUI();
  renderChats();
}

const RECENT_CHATS_KEY = "mesaj_recent_chats";

function saveRecentChat(chat) {
  if (!chat) return;
  let recent = [];
  try { recent = JSON.parse(localStorage.getItem(RECENT_CHATS_KEY) || "[]"); } catch (_) {}
  recent = recent.filter((c) => c.id !== chat.id);
  recent.unshift({ id: chat.id, name: chat.name, type: chat.type, platform: currentPlatform, account_id: getAccountId() });
  recent = recent.slice(0, 5);
  localStorage.setItem(RECENT_CHATS_KEY, JSON.stringify(recent));
  renderRecentChats();
}

function renderRecentChats() {
  const row = document.getElementById("recent-chats-row");
  const container = document.getElementById("recent-chats-chips");
  if (!row || !container) return;
  let recent = [];
  try { recent = JSON.parse(localStorage.getItem(RECENT_CHATS_KEY) || "[]"); } catch (_) {}
  recent = recent.filter((c) => c.platform === currentPlatform && (c.account_id === getAccountId() || !c.account_id));
  if (!recent.length) { row.classList.add("hidden"); return; }
  row.classList.remove("hidden");
  container.innerHTML = recent.map((c) =>
    `<button type="button" class="recent-chip" onclick="pickRecentChat('${encodeURIComponent(c.id)}')">${escapeHtml(c.name)}</button>`
  ).join("");
}

function pickRecentChat(encodedId) {
  const id = decodeURIComponent(encodedId);
  const fromList = allChats.find((c) => c.id === id);
  if (fromList) { selectChat(id); return; }
  let recent = [];
  try { recent = JSON.parse(localStorage.getItem(RECENT_CHATS_KEY) || "[]"); } catch (_) {}
  const r = recent.find((c) => c.id === id);
  if (r) {
    selectedChat = { id: r.id, name: r.name, type: r.type };
    updateSelectedChatUI();
  }
}

document.getElementById("chat-search")?.addEventListener("input", renderChats);
document.querySelectorAll("#chat-filters .filter-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#chat-filters .filter-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    chatFilter = btn.dataset.filter;
    renderChats();
  });
});

// ─── WebSocket (anlık mesajlar) ──────────────────────
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    updateConnectionBadge();
    if (wsReconnectTimer) { clearInterval(wsReconnectTimer); wsReconnectTimer = null; }
  };

  ws.onmessage = (ev) => {
    try {
      const event = JSON.parse(ev.data);
      handleRealtimeEvent(event);
    } catch (_) {}
  };

  ws.onclose = () => {
    updateConnectionBadge();
    if (!wsReconnectTimer) {
      wsReconnectTimer = setInterval(() => connectWebSocket(), 3000);
    }
  };
}

function handleRealtimeEvent(event) {
  if (event.type === "connection") {
    const aid = event.account_id ?? getAccountId(event.platform);
    if (event.platform) setConnectionState(event.platform, aid, event.status);
    updateConnectionBadge();
    if (event.platform === currentPlatform && aid === getAccountId()) updateMiniStatus();
    if (event.platform === "whatsapp") {
      if (event.status === "connected") {
        invalidatePlatformCache("whatsapp", aid);
        if (aid === getAccountId()) updateWaConnectBanner(false);
        if (currentPlatform === "whatsapp" && aid === getAccountId()) {
          loadChatThread(true);
          syncAllMessages(true);
        }
      } else if (aid === getAccountId()) {
        updateWaConnectBanner(currentPlatform === "whatsapp" && event.status !== "connected");
      }
    }
    renderAccountSwitcher();
    if (document.getElementById("tab-account")?.classList.contains("active")) renderAccountsList(currentPlatform);
    return;
  }
  if (event.type === "message" && event.data) {
    const m = event.data;
    const msgAccountId = m.account_id ?? event.account_id ?? getAccountId(m.platform);
    if (activeThreadChat && m.chat_id === activeThreadChat.id && m.platform === currentPlatform && msgAccountId === getAccountId()) {
      appendMessageBubble(m);
    }
    if (document.getElementById("tab-chats")?.classList.contains("active")) {
      loadChatThread();
    }
    return;
  }
  if (event.type === "conversation_update") {
    const updAccountId = event.account_id ?? getAccountId(event.platform);
    if (updAccountId === getAccountId(event.platform || currentPlatform) && document.getElementById("tab-chats")?.classList.contains("active")) {
      loadChatThread();
    }
  }
}

function updateConnectionBadge() {
  const el = document.getElementById("conn-badge");
  if (!el) return;
  const st = getConnectionState(currentPlatform);
  el.innerHTML = connectionBadgeHtml(st);
  el.className = `conn-badge ${st}`;
  updatePlatformDots();
  updatePlatformContextStatus();
}

let chatListCache = [];
let chatSearchTimer = null;
let chatListFilter = "all";
let threadMessages = [];
let threadHasMore = false;

function chatInitials(name) {
  if (!name) return "?";
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function chatPhoneFromId(id) {
  if (!id) return "";
  return String(id).split("@")[0].replace(/\D/g, "");
}

function formatPhoneTr(digitsOrId) {
  const digits = String(digitsOrId || "").replace(/\D/g, "");
  if (digits.length < 10) return digits;
  const local = digits.slice(-10);
  if (local.startsWith("5")) {
    return `+90 ${local.slice(0, 3)} ${local.slice(3, 6)} ${local.slice(6, 8)} ${local.slice(8)}`;
  }
  return `+${digits}`;
}

function isPhoneLikeName(name) {
  if (!name) return true;
  const s = String(name).trim();
  if (s.includes("@")) return true;
  const digits = s.replace(/\D/g, "");
  return digits.length >= 10 && digits.length >= s.replace(/\s/g, "").length * 0.85;
}

function getChatDisplay(chat) {
  const rawName = (chat?.name || "").trim();
  const phone = chatPhoneFromId(chat?.id);
  const formattedPhone = phone ? formatPhoneTr(phone) : "";
  if (rawName && !isPhoneLikeName(rawName)) {
    return { title: rawName, subtitle: formattedPhone || null };
  }
  if (chat?.display_phone) {
    return { title: chat.display_phone, subtitle: rawName && rawName !== chat.display_phone ? rawName : null };
  }
  if (formattedPhone) {
    return { title: formattedPhone, subtitle: null };
  }
  return { title: rawName || phone || tt("chats.unnamedChat"), subtitle: null };
}

function formatMessageTime(ts) {
  if (!ts) return "";
  if (typeof ts === "string") return formatDate(ts);
  return formatTs(ts);
}

function formatShortTime(ts) {
  if (!ts) return "";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString(userLocale(), { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(userLocale(), { timeZone: TZ, day: "2-digit", month: "2-digit" });
}

function setChatListFilter(filter) {
  chatListFilter = filter;
  document.querySelectorAll(".chat-filter").forEach((b) => {
    b.classList.toggle("active", b.dataset.filter === filter);
  });
  loadChatThread(false);
}

function applyChatListFilter(chats) {
  if (chatListFilter === "unread") return chats.filter((c) => (c.unread_count || 0) > 0);
  if (chatListFilter === "group") return chats.filter((c) => c.type === "group" || c.type === "supergroup");
  if (chatListFilter === "private") return chats.filter((c) => c.type === "private" || c.type === "user");
  return chats;
}

function getMessageDayKey(ts) {
  if (!ts) return "";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  return d.toLocaleDateString(userLocale(), { timeZone: TZ });
}

function formatDayLabel(ts) {
  const key = getMessageDayKey(ts);
  const today = new Date().toLocaleDateString(userLocale(), { timeZone: TZ });
  const yesterday = new Date(Date.now() - 86400000).toLocaleDateString(userLocale(), { timeZone: TZ });
  if (key === today) return tt("chats.today");
  if (key === yesterday) return tt("chats.yesterday");
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  return d.toLocaleDateString(userLocale(), { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
}

function formatBubbleTime(ts) {
  if (!ts) return "";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  return d.toLocaleTimeString(userLocale(), { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}
function filterChats(chats, search) {
  if (!search) return chats;
  const q = search.toLowerCase();
  return chats.filter((c) => {
    const disp = getChatDisplay(c);
    const name = (disp.title + " " + (disp.subtitle || "")).toLowerCase();
    const phone = chatPhoneFromId(c.id);
    const last = (c.last_message || "").toLowerCase();
    return name.includes(q) || phone.includes(q.replace(/\D/g, "")) || last.includes(q) || (c.id || "").toLowerCase().includes(q);
  });
}

function renderChatListItems(chats) {
  const list = document.getElementById("wa-chat-list");
  if (!chats.length) {
    list.innerHTML = emptyState("messages-square", tt("chats.noChats"));
    return;
  }
  list.innerHTML = chats.map((c) => {
    const wa = currentPlatform === "whatsapp";
    const avatarClass = wa ? "wa-avatar" : "tg-avatar";
    const disp = getChatDisplay(c);
    const subtitle = disp.subtitle ? `<div class="chat-item-sub muted small">${escapeHtml(disp.subtitle)}</div>` : "";
    return `<div class="chat-item wa-style ${activeThreadChat?.id === c.id ? "selected" : ""}" data-chat-id="${encodeURIComponent(c.id)}" onclick="openThreadFromEl(this)">
      <div class="chat-item-avatar ${avatarClass}">${escapeHtml(chatInitials(disp.title))}</div>
      <div class="chat-item-body">
        <div class="chat-item-top">
          <div class="chat-item-name-wrap">
            <div class="chat-item-name">${escapeHtml(disp.title)}</div>
            ${subtitle}
          </div>
          <span class="chat-item-time">${formatShortTime(c.last_timestamp)}</span>
        </div>
        <div class="chat-item-bottom">
          <div class="chat-item-preview muted small">${c.type === "group" ? `${icon("users", { size: 12, class: "icon inline-group-icon" })} ` : ""}${escapeHtml((c.last_message || tt("chats.noMessagePreview")).slice(0, 60))}</div>
          ${c.unread_count > 0 ? `<span class="unread-badge">${c.unread_count > 99 ? "99+" : c.unread_count}</span>` : ""}
        </div>
      </div>
    </div>`;
  }).join("");
}

function mediaUrl(path) {
  if (!path) return "";
  return `/api/media/${encodeURIComponent(path)}`;
}

function renderMessageContent(m) {
  const type = m.message_type || "text";
  const url = m.media_path ? mediaUrl(m.media_path) : "";
  if (type === "image" && url) {
    return `<div class="msg-media"><img src="${url}" alt="" loading="lazy" onclick="openMediaLightbox('${url.replace(/'/g, "\\'")}')" /></div>`
      + (m.caption ? `<div class="msg-caption">${escapeHtml(m.caption)}</div>` : "");
  }
  if (type === "video" && url) {
    return `<div class="msg-media"><video src="${url}" controls preload="metadata"></video></div>`
      + (m.caption ? `<div class="msg-caption">${escapeHtml(m.caption)}</div>` : "");
  }
  if ((type === "audio" || type === "voice") && url) {
    return `<div class="msg-media msg-audio"><audio src="${url}" controls preload="metadata"></audio></div>`;
  }
  if (type === "document" && url) {
    const name = escapeHtml(m.media_filename || "Dosya");
    return `<a class="msg-document" href="${url}" download target="_blank" rel="noopener">${icon("paperclip", { size: 14 })} ${name}</a>`;
  }
  if (type !== "text" && !url) {
    return `<div class="msg-text msg-media-placeholder">${escapeHtml(m.text || `[${type}]`)}</div>`;
  }
  return `<div class="msg-text">${escapeHtml(m.text || "")}</div>`;
}

function openMediaLightbox(url) {
  const el = document.getElementById("media-lightbox");
  const img = document.getElementById("media-lightbox-img");
  if (!el || !img) return;
  img.src = url;
  el.classList.remove("hidden");
}

function closeMediaLightbox() {
  const el = document.getElementById("media-lightbox");
  if (el) el.classList.add("hidden");
}

function initTheme() {
  const saved = localStorage.getItem("mesaj_theme") || "dark";
  document.documentElement.dataset.theme = saved;
  updateThemeUI();
}

function updateThemeUI() {
  const isDark = document.documentElement.dataset.theme !== "light";
  const iconEl = document.getElementById("theme-icon");
  const labelEl = document.getElementById("theme-label");
  const btn = document.getElementById("theme-toggle-btn");
  const meta = document.getElementById("meta-theme-color");
  if (iconEl) setIcon(iconEl, isDark ? "moon" : "sun", { size: 14, class: "icon" });
  const targetKey = isDark ? "theme.light" : "theme.dark";
  if (labelEl) labelEl.textContent = tt(targetKey);
  if (btn) btn.title = tt(targetKey);
  if (meta) meta.setAttribute("content", isDark ? "#0b0f14" : "#f4f7fb");
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("mesaj_theme", next);
  updateThemeUI();
}

window.updateThemeUI = updateThemeUI;
window.toggleTheme = toggleTheme;

let accountSetupPlatform = null;
let accountSetupDismissed = false;

function reopenAccountSetup() {
  accountSetupDismissed = false;
  api("/api/panel/status").then((s) => showAccountSetupOverlay(s)).catch(() => {});
}

async function updateSetupBanner() {
  const el = document.getElementById("dashboard-setup-banner");
  if (!el) return;
  try {
    const s = await api("/api/panel/status");
    el.classList.toggle("hidden", !s.needs_account_setup);
  } catch (_) {
    el.classList.add("hidden");
  }
}

function showAccountSetupOverlay(status) {
  if (accountSetupDismissed || !status?.needs_account_setup) return;
  accountSetupPlatform = null;
  document.getElementById("account-setup-step-pick")?.classList.add("active");
  document.getElementById("account-setup-step-name")?.classList.remove("active");
  document.getElementById("account-setup-overlay")?.classList.remove("hidden");
  initIcons();
}

function dismissAccountSetup() {
  accountSetupDismissed = true;
  document.getElementById("account-setup-overlay")?.classList.add("hidden");
}

function accountSetupBack() {
  document.getElementById("account-setup-step-name")?.classList.remove("active");
  document.getElementById("account-setup-step-pick")?.classList.add("active");
}

function accountSetupPickPlatform(platform) {
  accountSetupPlatform = platform;
  const existing = accountsCache[platform] || [];
  if (existing.length) {
    accountSetupContinue();
    return;
  }
  const meta = PLATFORM_META[platform];
  const hint = document.getElementById("account-setup-platform-hint");
  const input = document.getElementById("setup-account-label");
  if (hint) hint.textContent = tt("account.createFor", { platform: meta.label });
  if (input) input.value = `${meta.label} 1`;
  document.getElementById("account-setup-step-pick")?.classList.remove("active");
  document.getElementById("account-setup-step-name")?.classList.add("active");
  input?.focus();
  input?.select();
}

async function accountSetupContinue() {
  const platform = accountSetupPlatform;
  if (!platform) return;
  const btn = document.getElementById("btn-account-setup-continue");
  const input = document.getElementById("setup-account-label");
  const label = (input?.value || "").trim() || input?.placeholder || "Account";
  if (btn) btn.disabled = true;
  try {
    let accountId;
    const existing = accountsCache[platform] || [];
    if (existing.length === 0) {
      const acc = await api("/api/accounts", {
        method: "POST",
        body: JSON.stringify({ platform, label }),
      });
      accountId = acc.id;
      ensureAccountState(platform, acc.id);
      await loadAccounts(platform);
    } else {
      accountId = (existing.find((a) => a.is_default) || existing[0]).id;
    }
    dismissAccountSetup();
    await setPlatform(platform, { silent: true, skipAnimation: true });
    switchTab("account");
    await openAccountConnect(accountId);
    if (platform === "whatsapp") {
      setTimeout(() => openQrModal(), 400);
    }
    toastT("setup.openingAccount", "info");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function finishAccountSetupIfConnected() {
  try {
    const s = await api("/api/panel/status");
    if (!s.needs_account_setup) {
      dismissAccountSetup();
      document.getElementById("account-setup-overlay")?.classList.add("hidden");
      if (!localStorage.getItem("mesaj_onboarded")) initOnboarding();
    }
    await updateSetupBanner();
  } catch (_) {}
}

async function initPostLoginFlow() {
  try {
    const s = await api("/api/panel/status");
    await updateSetupBanner();
    if (s.needs_account_setup) {
      accountSetupDismissed = false;
      showAccountSetupOverlay(s);
      return;
    }
    initOnboarding();
  } catch (_) {
    initOnboarding();
  }
}

function initOnboarding() {
  if (localStorage.getItem("mesaj_onboarded")) return;
  document.getElementById("onboarding-overlay")?.classList.remove("hidden");
}

function finishOnboarding(step) {
  if (step === "skip" || step === "done") {
    localStorage.setItem("mesaj_onboarded", "1");
    document.getElementById("onboarding-overlay")?.classList.add("hidden");
    return;
  }
  const steps = document.querySelectorAll(".onboarding-step");
  const cur = document.querySelector(".onboarding-step.active");
  const idx = cur ? [...steps].indexOf(cur) : 0;
  steps.forEach((s) => s.classList.remove("active"));
  if (idx + 1 < steps.length) steps[idx + 1].classList.add("active");
  else finishOnboarding("done");
}

// alias for button onclick
function finishOnboardingNext() { finishOnboarding("next"); }

async function loadDeveloperTools() {
  const keysEl = document.getElementById("api-keys-list");
  const hooksEl = document.getElementById("webhooks-list");
  if (!keysEl) return;
  try {
    const keys = await api("/api/v1/keys");
    keysEl.innerHTML = keys.length
      ? keys.map((k) => `<div class="dev-item"><strong>${escapeHtml(k.name)}</strong><span class="muted small">${escapeHtml(k.key_prefix)}…</span>
        <button class="btn ghost small" onclick="revokeApiKey(${k.id})">${tt("common.delete")}</button></div>`).join("")
      : `<p class="muted small">${tt("developer.noApiKeys")}</p>`;
    const hooks = await api("/api/v1/webhooks");
    if (hooksEl) {
      hooksEl.innerHTML = hooks.length
        ? hooks.map((h) => `<div class="dev-item"><strong>${escapeHtml(h.name)}</strong><span class="muted small">${escapeHtml(h.url)}</span>
          <button class="btn ghost small" onclick="deleteWebhook(${h.id})">${tt("common.delete")}</button></div>`).join("")
        : `<p class="muted small">${tt("developer.noWebhooks")}</p>`;
    }
  } catch (_) {}
}

function toggleDeveloperCard() {
  const card = document.getElementById("developer-card");
  const btn = document.getElementById("developer-toggle");
  if (!card || !btn) return;
  card.classList.toggle("collapsed");
  const collapsed = card.classList.contains("collapsed");
  btn.textContent = tt(collapsed ? "developer.show" : "developer.hide");
  if (!collapsed) loadDeveloperTools();
}

async function createApiKeyPrompt() {
  const name = prompt(tt("prompt.apiKeyName"), "Automation");
  if (!name) return;
  try {
    const r = await api("/api/v1/keys", { method: "POST", body: JSON.stringify({ name }) });
    prompt(tt("prompt.apiKeySave"), r.api_key);
    loadDeveloperTools();
  } catch (e) { toast(e.message, "error"); }
}

async function revokeApiKey(id) {
  if (!confirm(tt("confirm.deleteApiKey"))) return;
  await api(`/api/v1/keys/${id}`, { method: "DELETE" });
  loadDeveloperTools();
}

async function createWebhookPrompt() {
  const name = prompt(tt("prompt.webhookName"), "n8n");
  const url = prompt(tt("prompt.webhookUrl"));
  if (!name || !url) return;
  try {
    await api("/api/v1/webhooks", { method: "POST", body: JSON.stringify({ name, url, events: ["message.received"] }) });
    toastT("toast.webhookAdded", "success");
    loadDeveloperTools();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteWebhook(id) {
  if (!confirm(tt("confirm.deleteWebhook"))) return;
  await api(`/api/v1/webhooks/${id}`, { method: "DELETE" });
  loadDeveloperTools();
}

function renderThreadMessages(msgs, append = false) {
  const thread = document.getElementById("message-thread");
  thread.classList.toggle("wa-thread", currentPlatform === "whatsapp");
  if (!msgs.length && !append) {
    thread.innerHTML = emptyState("messages-square", tt("scheduled.empty"));
    return;
  }
  const wa = currentPlatform === "whatsapp";
  const isGroup = activeThreadChat?.type === "group" || activeThreadChat?.type === "supergroup";
  let html = "";
  let lastDate = append ? getMessageDayKey(threadMessages[0]?.timestamp) : "";
  for (const m of msgs) {
    const dayKey = getMessageDayKey(m.timestamp);
    if (dayKey && dayKey !== lastDate) {
      html += `<div class="msg-date-divider"><span>${formatDayLabel(m.timestamp)}</span></div>`;
      lastDate = dayKey;
    }
    const me = m.from_me ? "me" : "them";
    const extra = m.from_me && wa ? " wa-me" : "";
    const dedupId = m.message_id || m.id;
    const showSender = !m.from_me && (isGroup || wa) && m.sender_name;
    html += `<div class="msg-bubble ${me}${extra}" data-id="${dedupId}" data-msg-id="${dedupId}">
      ${showSender ? `<div class="msg-sender">${escapeHtml(m.sender_name)}</div>` : ""}
      ${renderMessageContent(m)}
      <div class="msg-time">${formatBubbleTime(m.timestamp)}</div>
    </div>`;
  }
  if (append) {
    const old = thread.innerHTML;
    thread.innerHTML = html + old;
  } else {
    thread.innerHTML = html;
    thread.scrollTop = thread.scrollHeight;
  }
}

function appendMessageBubble(m) {
  const thread = document.getElementById("message-thread");
  const dedupId = m.message_id || m.id;
  if (thread.querySelector(`[data-msg-id="${dedupId}"]`)) return;
  const empty = thread.querySelector(".empty-state");
  if (empty) empty.remove();
  const wa = currentPlatform === "whatsapp";
  const div = document.createElement("div");
  div.className = `msg-bubble ${m.from_me ? "me" : "them"}${m.from_me && wa ? " wa-me" : ""}`;
  div.dataset.id = dedupId;
  div.dataset.msgId = dedupId;
  const sender = !m.from_me && m.sender_name ? `<div class="msg-sender">${escapeHtml(m.sender_name)}</div>` : "";
  div.innerHTML = `${sender}${renderMessageContent(m)}<div class="msg-time">${formatMessageTime(m.timestamp)}</div>`;
  thread.appendChild(div);
  thread.scrollTop = thread.scrollHeight;
}

// ─── Chat thread view ────────────────────────────────
async function loadChatThread(refresh = false) {
  const list = document.getElementById("wa-chat-list");
  if (refresh || !chatListCache.length) {
    showChatListSkeleton();
    try {
      const url = withAccountId(`/api/conversations?platform=${currentPlatform}${refresh ? "&refresh=true" : ""}`);
      chatListCache = await api(url);
      if (!chatListCache.length) {
        chatListCache = await api(withAccountId(`/api/chats?platform=${currentPlatform}${refresh ? "&refresh=true" : ""}`));
      }
      allChats = chatListCache;
    } catch (e) {
      list.innerHTML = emptyState("alert-triangle", escapeHtml(e.message));
      return;
    }
  }
  const search = (document.getElementById("wa-chat-search")?.value || "").trim();
  let filtered = applyChatListFilter(filterChats(chatListCache, search.toLowerCase()));
  if (!filtered.length) {
    list.innerHTML = emptyState("messages-square", search ? tt("chats.noResults") : tt("chats.noChatsConnect"));
    return;
  }
  renderChatListItems(filtered);
  savePlatformState();
}

async function searchMessagesGlobal(query) {
  const box = document.getElementById("message-search-results");
  if (!box) return;
  if (!query || query.length < 2) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  try {
    const results = await api(withAccountId(`/api/messages/search?q=${encodeURIComponent(query)}&platform=${currentPlatform}&limit=30`));
    if (!results.length) {
      box.innerHTML = `<p class="muted small">${tt("chats.noMessagesFound")}</p>`;
      box.classList.remove("hidden");
      return;
    }
    box.innerHTML = results.map((r) =>
      `<button type="button" class="search-result-item" onclick="openThread('${encodeURIComponent(r.chat_id)}')">
        <strong>${escapeHtml(r.chat_name || r.chat_id)}</strong>
        <span class="muted small">${formatMessageTime(r.timestamp)}</span>
        <p>${escapeHtml((r.text || "").slice(0, 80))}</p>
      </button>`
    ).join("");
    box.classList.remove("hidden");
  } catch (_) {
    box.classList.add("hidden");
  }
}

function showChatListSkeleton() {
  const list = document.getElementById("wa-chat-list");
  if (!list) return;
  list.innerHTML = Array.from({ length: 8 }, () => `
    <div class="chat-item chat-skeleton" aria-hidden="true">
      <div class="skeleton-avatar"></div>
      <div class="skeleton-lines">
        <div class="skeleton-line w70"></div>
        <div class="skeleton-line w45"></div>
      </div>
    </div>`).join("");
}

function showThreadSkeleton() {
  const thread = document.getElementById("message-thread");
  if (!thread) return;
  thread.innerHTML = Array.from({ length: 6 }, (_, i) => `
    <div class="msg-skeleton ${i % 2 ? "right" : "left"}" aria-hidden="true">
      <div class="skeleton-bubble"></div>
    </div>`).join("");
}

function showImportProgress(current, total, hint) {
  const box = document.getElementById("import-progress");
  const bar = document.getElementById("import-progress-bar");
  const count = document.getElementById("import-progress-count");
  const hintEl = document.getElementById("import-progress-hint");
  if (!box) return;
  box.classList.remove("hidden");
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : (current > 0 ? 8 : 3);
  if (bar) bar.style.width = `${pct}%`;
  if (count) {
    count.textContent = total > 0
      ? `${current.toLocaleString("tr-TR")} / ${total.toLocaleString("tr-TR")}`
      : tt("import.preparing");
  }
  if (hint && hintEl) hintEl.textContent = hint;
}

function hideImportProgress() {
  document.getElementById("import-progress")?.classList.add("hidden");
  const bar = document.getElementById("import-progress-bar");
  if (bar) bar.style.width = "0%";
}

async function syncAllMessages(silent = false) {
  if (currentPlatform !== "whatsapp") {
    if (!silent) toastT("toast.importWaOnly", "info");
    return;
  }
  const btn = document.getElementById("btn-sync-all");
  if (btn) btn.disabled = true;
  if (!silent) showImportProgress(0, 0, tt("import.loadingChats"));
  try {
    await loadChatThread(true);
    let offset = 0;
    let total = 0;
    let totalSynced = 0;
    let firstChunk = true;

    while (true) {
      if (!silent) {
        showImportProgress(
          offset,
          total,
          firstChunk ? tt("import.syncing") : tt("import.savedCount", { count: localeNumber(totalSynced) })
        );
      }
      const r = await api(
        withAccountId(`/api/messages/sync-all/${currentPlatform}?offset=${offset}&chunk_size=3000`),
        { method: "POST" }
      );
      totalSynced += r.synced || 0;
      if (r.total_messages && total === 0) total = r.total_messages;
      if (!silent) {
        showImportProgress(
          r.next_offset || offset,
          total || r.stored_messages || 0,
          tt("import.savedCount", { count: localeNumber(totalSynced) })
        );
      }
      if (firstChunk || (r.synced > 0)) {
        await loadChatThread(false);
      }
      firstChunk = false;
      if (!r.has_more) break;
      offset = r.next_offset;
    }

    invalidatePlatformCache(currentPlatform, getAccountId());
    await loadChatThread(false);
    loadWaStats();
    if (!silent) toastT("import.savedCount", "success", { count: localeNumber(totalSynced) });
  } catch (e) {
    if (!silent) toast(e.message, "error");
  } finally {
    hideImportProgress();
    if (btn) btn.disabled = false;
  }
}

function openThreadFromEl(el) {
  openThread(decodeURIComponent(el.dataset.chatId));
}

function openRenameChatModal() {
  if (!activeThreadChat) return;
  const overlay = document.getElementById("rename-chat-overlay");
  const input = document.getElementById("rename-chat-input");
  const hint = document.getElementById("rename-chat-hint");
  const disp = getChatDisplay(activeThreadChat);
  if (input) input.value = isPhoneLikeName(activeThreadChat.name) ? "" : (activeThreadChat.name || disp.title);
  if (hint) {
    const phone = formatPhoneTr(chatPhoneFromId(activeThreadChat.id));
    hint.textContent = phone ? tt("rename.phoneHint", { phone }) : tt("rename.phoneHintShort");
  }
  overlay?.classList.remove("hidden");
  input?.focus();
}

function closeRenameChatModal() {
  document.getElementById("rename-chat-overlay")?.classList.add("hidden");
}

async function confirmRenameChat() {
  if (!activeThreadChat) return;
  const input = document.getElementById("rename-chat-input");
  const label = (input?.value || "").trim();
  if (!label) { toastT("toast.enterName", "error"); return; }
  try {
    const r = await api(withAccountId(`/api/conversations/${currentPlatform}/${encodeURIComponent(activeThreadChat.id)}/label`), {
      method: "PATCH",
      body: JSON.stringify({ label }),
    });
    activeThreadChat.name = r.name;
    activeThreadChat.chat_name_custom = true;
    const idx = chatListCache.findIndex((c) => c.id === activeThreadChat.id);
    if (idx >= 0) chatListCache[idx] = { ...chatListCache[idx], name: r.name, chat_name_custom: true };
    closeRenameChatModal();
    const disp = getChatDisplay(activeThreadChat);
    document.getElementById("chat-header-name").textContent = disp.title;
    document.getElementById("chat-header-type").textContent = disp.subtitle || (TYPE_LABELS[activeThreadChat.type] || "");
    document.getElementById("chat-header-avatar").textContent = chatInitials(disp.title);
    renderChatListItems(applyChatListFilter(filterChats(chatListCache, (document.getElementById("wa-chat-search")?.value || "").trim().toLowerCase())));
    toastT("toast.nameSaved", "success", { name: r.name });
    savePlatformState();
  } catch (e) { toast(e.message, "error"); }
}

document.getElementById("wa-chat-search")?.addEventListener("input", (e) => {
  const q = e.target.value.trim();
  loadChatThread(false);
  if (chatSearchTimer) clearTimeout(chatSearchTimer);
  chatSearchTimer = setTimeout(() => searchMessagesGlobal(q), 350);
});

async function openThread(id, restoreOnly = false) {
  activeThreadChat = chatListCache.find((c) => c.id === id) || allChats.find((c) => c.id === id);
  if (!activeThreadChat) {
    activeThreadChat = { id, name: id.split("@")[0], type: "private" };
  }
  document.getElementById("message-search-results")?.classList.add("hidden");
  setChatThreadOpen(true);
  const header = document.getElementById("chat-header");
  header.classList.remove("hidden");
  header.classList.toggle("wa-header", currentPlatform === "whatsapp");
  document.getElementById("chat-compose").classList.remove("hidden");
  const disp = getChatDisplay(activeThreadChat);
  document.getElementById("chat-header-name").textContent = disp.title;
  document.getElementById("chat-header-type").textContent = disp.subtitle || (TYPE_LABELS[activeThreadChat.type] || activeThreadChat.type);
  const av = document.getElementById("chat-header-avatar");
  if (av) {
    av.textContent = chatInitials(disp.title);
    av.className = `chat-header-avatar ${currentPlatform === "whatsapp" ? "wa-avatar" : "tg-avatar"}`;
  }
  updateConnectionBadge();

  if (restoreOnly && threadMessages.length) {
    renderThreadMessages(threadMessages);
    document.getElementById("load-more-msgs")?.classList.toggle("hidden", !threadHasMore);
    loadChatThread(false);
    return;
  }

  const thread = document.getElementById("message-thread");
  showThreadSkeleton();

  try {
    const msgs = await api(withAccountId(`/api/messages/${currentPlatform}/${encodeURIComponent(id)}?limit=80`));
    threadMessages = msgs;
    threadHasMore = msgs.length >= 80;
    renderThreadMessages(msgs);
    document.getElementById("load-more-msgs")?.classList.toggle("hidden", !threadHasMore);
  } catch (e) {
    thread.innerHTML = emptyState("alert-triangle", escapeHtml(e.message));
  }
  loadChatThread(false);
  savePlatformState();
}

async function loadMoreThreadMessages() {
  if (!activeThreadChat || !threadMessages.length) return;
  const oldest = threadMessages[0];
  if (!oldest?.id) return;
  try {
    const older = await api(
      withAccountId(`/api/messages/${currentPlatform}/${encodeURIComponent(activeThreadChat.id)}?limit=50&before_id=${oldest.id}`)
    );
    if (!older.length) {
      threadHasMore = false;
      document.getElementById("load-more-msgs")?.classList.add("hidden");
      return;
    }
    threadMessages = [...older, ...threadMessages];
    renderThreadMessages(older, true);
    threadHasMore = older.length >= 50;
    document.getElementById("load-more-msgs")?.classList.toggle("hidden", !threadHasMore);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function sendChatReply() {
  const text = document.getElementById("chat-reply").value.trim();
  if (!text || !activeThreadChat) return;
  try {
    await api(withAccountId("/api/messages/send"), {
      method: "POST",
      body: JSON.stringify({
        platform: currentPlatform,
        chat_id: activeThreadChat.id,
        message: text,
        chat_name: activeThreadChat.name,
        chat_type: activeThreadChat.type || "unknown",
      }),
    });
    document.getElementById("chat-reply").value = "";
    toast(tt("toast.sent"), "success");
    const msgs = await api(withAccountId(`/api/messages/${currentPlatform}/${encodeURIComponent(activeThreadChat.id)}?limit=100`));
    renderThreadMessages(msgs);
  } catch (e) { toast(e.message, "error"); }
}

async function sendChatMedia(file) {
  if (!file || !activeThreadChat) return;
  const caption = document.getElementById("chat-reply")?.value.trim() || "";
  const params = new URLSearchParams({
    platform: currentPlatform,
    account_id: String(getAccountId()),
    chat_id: activeThreadChat.id,
    caption,
    chat_name: activeThreadChat.name || "",
    chat_type: activeThreadChat.type || "unknown",
  });
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch(withAccountId(`/api/messages/send-media?${params}`), { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || tt("error.mediaSend"));
    document.getElementById("chat-reply").value = "";
    toastT("toast.mediaSent", "success");
    const msgs = await api(withAccountId(`/api/messages/${currentPlatform}/${encodeURIComponent(activeThreadChat.id)}?limit=100`));
    renderThreadMessages(msgs);
  } catch (e) { toast(e.message, "error"); }
}

function onChatFileSelected(e) {
  const f = e.target.files?.[0];
  if (f) sendChatMedia(f);
  e.target.value = "";
}

let composeSelectedFile = null;

function onComposeFileSelected(e) {
  composeSelectedFile = e.target.files?.[0] || null;
  const label = document.getElementById("compose-file-label");
  if (label) {
    if (composeSelectedFile) {
      label.textContent = composeSelectedFile.name;
      label.classList.remove("hidden");
    } else {
      label.textContent = "";
      label.classList.add("hidden");
    }
  }
}

function clearComposeFile() {
  composeSelectedFile = null;
  const input = document.getElementById("compose-file-input");
  if (input) input.value = "";
  const label = document.getElementById("compose-file-label");
  if (label) {
    label.textContent = "";
    label.classList.add("hidden");
  }
}

async function sendComposeMedia(file, sendNow = true) {
  if (!file || !selectedChat) return false;
  const caption = document.getElementById("message-text")?.value.trim() || "";
  const params = new URLSearchParams({
    platform: currentPlatform,
    account_id: String(getAccountId()),
    chat_id: selectedChat.id,
    caption,
    chat_name: selectedChat.name || "",
    chat_type: selectedChat.type || "unknown",
  });
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(withAccountId(`/api/messages/send-media?${params}`), { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || tt("error.mediaSend"));
  clearComposeFile();
  document.getElementById("message-text").value = "";
  document.getElementById("message-text")?.dispatchEvent(new Event("input"));
  toastT(sendNow ? "toast.mediaSent" : "toast.mediaScheduled", "success");
  return true;
}

async function testSendNaber() {
  try {
    const r = await api("/api/test/send-naber", { method: "POST" });
    toastT("test.naberSent", "success", { name: r.target.chat_name });
  } catch (e) {
    toast(e.message, "error");
    if (e.message.includes("error.outbound") || e.message.includes("Test modu")) {
      showStatus("auth-status", tt("test.safeMode"), "error");
    }
  }
}

function useChatForSchedule() { openScheduleFromChat(); }

function openScheduleFromChat() {
  if (!activeThreadChat) { toastT("toast.selectChatFirst", "error"); return; }
  const text = document.getElementById("chat-reply")?.value.trim();
  if (!text) { toastT("toast.writeForSchedule", "error"); return; }
  selectedChat = activeThreadChat;
  openScheduleModal({ message: text, fromChat: true });
}

// ─── Compose / Schedule (Teams tarzı) ────────────────
let scheduleRepeatType = "none";
let scheduledFilterStatus = "";

function getTrNow() {
  return new Date(new Date().toLocaleString("en-US", { timeZone: TZ }));
}

function pad2(n) { return String(n).padStart(2, "0"); }

function trToLocalParts(tr) {
  return {
    date: `${tr.getFullYear()}-${pad2(tr.getMonth() + 1)}-${pad2(tr.getDate())}`,
    time: `${pad2(tr.getHours())}:${pad2(tr.getMinutes())}`,
  };
}

function getModalDateTimeLocal() {
  const d = document.getElementById("modal-schedule-date")?.value;
  const t = document.getElementById("modal-schedule-time")?.value;
  if (!d || !t) return null;
  return `${d}T${t}`;
}

function setModalDateTime(tr) {
  tr.setSeconds(0, 0);
  const { date, time } = trToLocalParts(tr);
  const dateEl = document.getElementById("modal-schedule-date");
  const timeEl = document.getElementById("modal-schedule-time");
  if (dateEl) dateEl.value = date;
  if (timeEl) timeEl.value = time;
  updateSchedulePreview();
}

function syncModalDateTime() {
  document.querySelectorAll(".schedule-preset").forEach((b) => b.classList.remove("active"));
  updateSchedulePreview();
}

function applySchedulePreset(preset) {
  const tr = getTrNow();
  switch (preset) {
    case "15m": tr.setMinutes(tr.getMinutes() + 15); break;
    case "30m": tr.setMinutes(tr.getMinutes() + 30); break;
    case "1h": tr.setHours(tr.getHours() + 1); break;
    case "this_evening":
      tr.setHours(18, 0, 0, 0);
      if (tr <= getTrNow()) tr.setDate(tr.getDate() + 1);
      break;
    case "tomorrow_morning":
      tr.setDate(tr.getDate() + 1);
      tr.setHours(9, 0, 0, 0);
      break;
    case "next_monday": {
      const day = tr.getDay();
      const add = day === 0 ? 1 : (8 - day);
      tr.setDate(tr.getDate() + add);
      tr.setHours(9, 0, 0, 0);
      break;
    }
    default: break;
  }
  setModalDateTime(tr);
  document.querySelectorAll(".schedule-preset").forEach((b) => {
    b.classList.toggle("active", b.dataset.preset === preset);
  });
}

function setRepeatPill(repeat) {
  scheduleRepeatType = repeat;
  document.querySelectorAll(".repeat-pill").forEach((b) => {
    b.classList.toggle("active", b.dataset.repeat === repeat);
  });
  document.getElementById("modal-custom-interval-field")?.classList.toggle("hidden", repeat !== "custom");
  const randomPanel = document.getElementById("random-window-panel");
  const fixedDt = document.getElementById("schedule-fixed-datetime");
  const isRandom = repeat === "random_daily";
  randomPanel?.classList.toggle("hidden", !isRandom);
  fixedDt?.classList.toggle("hidden", isRandom);
  if (isRandom && randomPanel) randomPanel.open = true;
  updateSchedulePreview();
}

function applyWindowPreset(start, end) {
  const startEl = document.getElementById("modal-window-start");
  const endEl = document.getElementById("modal-window-end");
  if (startEl) startEl.value = start;
  if (endEl) endEl.value = end;
  updateSchedulePreview();
}

function getRandomWindowTimes() {
  const start = document.getElementById("modal-window-start")?.value;
  const end = document.getElementById("modal-window-end")?.value;
  if (!start || !end) return null;
  if (start >= end) return { error: tt("schedule.windowError") };
  return { start, end };
}

function formatRelativeFuture(isoStr) {
  if (!isoStr) return "";
  const target = new Date(isoStr.endsWith("Z") || isoStr.includes("+") ? isoStr : isoStr + "Z");
  const diffMs = target - Date.now();
  if (diffMs < 0) return tt("time.past");
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return tt("time.soon");
  if (mins < 60) return `${mins} dakika sonra`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} saat sonra`;
  const days = Math.round(hours / 24);
  if (days < 7) return tt("time.daysLater", { days });
  return formatDate(isoStr);
}

function updateSchedulePreview() {
  const summary = document.getElementById("schedule-summary-text");
  const relative = document.getElementById("schedule-summary-relative");
  if (!summary) return;

  if (scheduleRepeatType === "random_daily") {
    const win = getRandomWindowTimes();
    if (win?.error) {
      summary.textContent = win.error;
      if (relative) relative.textContent = "";
      return;
    }
    if (win) {
      summary.textContent = tt("schedule.randomDailySummary", { start: win.start, end: win.end });
      if (relative) {
        relative.textContent = tt("schedule.relativeRandom");
      }
    }
    return;
  }

  const local = getModalDateTimeLocal();
  if (!local || !summary) return;
  const iso = localDateTimeToISO(local);
  summary.textContent = formatDate(iso);
  if (relative) {
    const rep = REPEAT_LABELS[scheduleRepeatType] || "";
    relative.textContent = `${formatRelativeFuture(iso)}${rep && scheduleRepeatType !== "none" ? ` · ${rep}` : ""}`;
  }
}

function openScheduleModal(opts = {}) {
  if (!selectedChat && !opts.fromChat) { toastT("toast.pickRecipient", "error"); return; }
  const message = opts.message ?? document.getElementById("message-text")?.value.trim();
  if (!message) { toastT("toast.writeMessage", "error"); return; }

  document.getElementById("schedule-modal-message").textContent = message;
  document.getElementById("schedule-modal-recipient").textContent =
    `${PLATFORM_LABELS[currentPlatform]} · ${selectedChat?.name || "—"}`;
  setRepeatPill("none");
  applySchedulePreset("30m");
  document.getElementById("schedule-modal").classList.remove("hidden");
  document.getElementById("schedule-modal").dataset.message = message;
  document.getElementById("schedule-modal").dataset.fromChat = opts.fromChat ? "1" : "";
}

function closeScheduleModal() {
  document.getElementById("schedule-modal")?.classList.add("hidden");
}

async function submitScheduledJob(sendNow, messageOverride) {
  if (!selectedChat) { toast(tt("toast.pickRecipient"), "error"); return false; }
  const message = messageOverride ?? document.getElementById("message-text")?.value.trim();
  if (!message) { toast(tt("toast.emptyMessage"), "error"); return false; }

  let scheduledAt;
  if (sendNow) {
    scheduledAt = new Date(Date.now() + 2000).toISOString();
  } else if (scheduleRepeatType === "random_daily") {
    const win = getRandomWindowTimes();
    if (!win || win.error) {
      toast(win?.error || tt("schedule.pickWindow"), "error");
      return false;
    }
    scheduledAt = new Date(Date.now() + 60000).toISOString();
  } else {
    const local = getModalDateTimeLocal();
    if (!local) { toastT("toast.pickDateTime", "error"); return false; }
    scheduledAt = localDateTimeToISO(local);
    const target = new Date(scheduledAt);
    if (target <= new Date()) { toastT("toast.futureTime", "error"); return false; }
  }

  const repeatType = sendNow ? "none" : scheduleRepeatType;
  const win = scheduleRepeatType === "random_daily" ? getRandomWindowTimes() : null;
  const body = {
    platform: currentPlatform,
    account_id: getAccountId(),
    chat_id: selectedChat.id,
    chat_name: selectedChat.name,
    chat_type: selectedChat.type || "unknown",
    message_text: message,
    scheduled_at: repeatType === "random_daily" ? null : scheduledAt,
    repeat_type: repeatType,
    repeat_interval_minutes: repeatType === "custom"
      ? parseInt(document.getElementById("modal-repeat-interval")?.value || "60", 10) : null,
    window_start_time: win?.start || null,
    window_end_time: win?.end || null,
  };

  const r = await api("/api/scheduled", { method: "POST", body: JSON.stringify(body) });
  if (sendNow) await api(`/api/scheduled/${r.id}/send-now`, { method: "POST" });
  return { scheduledAt, sendNow, response: r };
}

async function confirmSchedule() {
  const modal = document.getElementById("schedule-modal");
  const message = modal?.dataset.message || "";
  const fromChat = modal?.dataset.fromChat === "1";
  const btn = document.getElementById("btn-confirm-schedule");
  if (btn) btn.disabled = true;
  try {
    const result = await submitScheduledJob(false, message);
    closeScheduleModal();
    if (fromChat) document.getElementById("chat-reply").value = "";
    else {
      document.getElementById("message-text").value = "";
      document.getElementById("message-text").dispatchEvent(new Event("input"));
    }
    const when = result?.response?.scheduled_at_tr;
    if (scheduleRepeatType === "random_daily" && when) {
      toastT("toast.randomScheduled", "success", { when });
    } else {
      toastT("toast.scheduledMsg", "success");
    }
    loadScheduled();
    loadStats();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function sendMessageNow() {
  const btn = document.getElementById("btn-send-now");
  if (btn) btn.disabled = true;
  try {
    if (composeSelectedFile) {
      await sendComposeMedia(composeSelectedFile, true);
    } else {
      await submitScheduledJob(true);
      document.getElementById("message-text").value = "";
      document.getElementById("message-text").dispatchEvent(new Event("input"));
      toastT("toast.platformSent", "success", { platform: PLATFORM_LABELS[currentPlatform] });
    }
    loadScheduled();
    loadStats();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setScheduledFilter(status) {
  scheduledFilterStatus = status;
  document.querySelectorAll("#scheduled-segments .segment").forEach((b) => {
    b.classList.toggle("active", b.dataset.status === status);
  });
  loadScheduled();
}

document.getElementById("message-text")?.addEventListener("input", (e) => {
  document.getElementById("char-count").textContent = e.target.value.length;
});

// ─── Scheduled list ──────────────────────────────────
async function loadScheduled() {
  const container = document.getElementById("scheduled-list");
  const url = scheduledFilterStatus
    ? `/api/scheduled?status=${scheduledFilterStatus}`
    : "/api/scheduled";
  try {
    let jobs = await api(url);
    jobs = jobs.filter((j) => (j.platform || "telegram") === currentPlatform && (j.account_id === getAccountId() || j.account_id == null));
    const label = document.getElementById("scheduled-count-label");
    if (label) label.textContent = jobs.length ? tt("scheduled.records", { count: jobs.length }) : tt("scheduled.subtitle");
    if (!jobs.length) {
      const meta = PLATFORM_META[currentPlatform];
      container.innerHTML = emptyState(meta.icon, tt("scheduled.emptyPlatform", { platform: meta.label }),
        `<button class="btn primary" onclick="switchTab('compose')">${tt("scheduled.scheduleFirst")}</button>`);
      return;
    }
    const renderJob = (j) => {
      const plat = j.platform || "telegram";
      const isActive = j.is_active && (j.status === "pending" || j.status === "failed");
      const rel = (j.status === "pending" && j.scheduled_at) ? formatRelativeFuture(j.scheduled_at) : "";
      return `<div class="scheduled-item ${j.status}">
        <div class="scheduled-item-top">
          <div class="scheduled-avatar">${platformIconHtml(plat, 20)}</div>
          <div class="scheduled-item-main">
            <header>
              <strong>${escapeHtml(j.chat_name)}</strong>
              <div class="scheduled-badges">
                <span class="platform-tag ${plat}">${PLATFORM_LABELS[plat]}</span>
                <span class="badge ${j.status}">${STATUS_LABELS[j.status] || j.status}</span>
              </div>
            </header>
            <div class="scheduled-meta">
              ${j.repeat_type === "random_daily" && j.window_start_time
                ? `<span class="scheduled-window meta-icon">${icon("dices", { size: 14 })} ${tt("scheduled.windowBetween", { start: j.window_start_time, end: j.window_end_time })}</span>` : ""}
              <span class="scheduled-time meta-icon">${icon("timer", { size: 14 })} ${j.scheduled_at_tr || formatDate(j.scheduled_at)}</span>
              ${rel ? `<span class="scheduled-relative">${rel}</span>` : ""}
              ${j.repeat_type !== "none" ? `<span class="meta-icon">${icon("repeat", { size: 14 })} ${REPEAT_LABELS[j.repeat_type] || j.repeat_type}</span>` : ""}
            </div>
            <div class="scheduled-text">${escapeHtml(j.message_text)}</div>
          </div>
        </div>
        ${j.error_message ? `<div class="error-box">${icon("alert-triangle", { size: 16 })}<span>${escapeHtml(j.error_message)}</span></div>` : ""}
        <div class="item-actions">
          ${isActive ? `<button class="btn small ghost" onclick="sendNow(${j.id})">${btnWithIcon("rocket", tt("scheduled.sendNowBtn"))}</button>` : ""}
          ${j.status === "failed" ? `<button class="btn small secondary" onclick="retryJob(${j.id})">${btnWithIcon("refresh-cw", "Tekrar dene")}</button>` : ""}
          ${isActive ? `<button class="btn small danger" onclick="cancelJob(${j.id})">${tt("common.cancel")}</button>` : ""}
        </div>
      </div>`;
    };
    if (scheduledFilterStatus) {
      container.innerHTML = jobs.map(renderJob).join("");
      return;
    }
    const pending = jobs.filter((j) => j.is_active && (j.status === "pending" || j.status === "failed"));
    const rest = jobs.filter((j) => !pending.includes(j));
    let html = "";
    if (pending.length && !scheduledFilterStatus) {
      html += `<div class="scheduled-group-label">${tt("scheduled.upcoming", { count: pending.length })}</div>`;
      html += pending.map(renderJob).join("");
    }
    const showRest = scheduledFilterStatus ? jobs : rest;
    if (showRest.length && !scheduledFilterStatus && pending.length) {
      html += `<div class="scheduled-group-label">${tt("scheduled.other")}</div>`;
    }
    html += showRest.map(renderJob).join("");
    container.innerHTML = html;
  } catch (e) { container.innerHTML = emptyState("alert-triangle", escapeHtml(e.message)); }
}

async function sendNow(id) {
  try { await api(`/api/scheduled/${id}/send-now`, { method: "POST" }); toastT("toast.sentShort", "success"); loadScheduled(); loadStats(); }
  catch (e) { toast(e.message, "error"); }
}
async function retryJob(id) {
  try { await api(`/api/scheduled/${id}/retry`, { method: "POST" }); toastT("toast.retried", "success"); loadScheduled(); }
  catch (e) { toast(e.message, "error"); }
}
async function cancelJob(id) {
  if (!confirm(tt("confirm.cancelJob"))) return;
  await api(`/api/scheduled/${id}`, { method: "DELETE" });
  toastT("toast.cancelledJob", "info"); loadScheduled(); loadStats();
}

// ─── Templates ───────────────────────────────────────
async function loadTemplates() {
  try {
    const templates = await api("/api/templates");
    const list = document.getElementById("templates-list");
    const sel = document.getElementById("template-select");
    sel.innerHTML = `<option value="">${tt("templates.select")}</option>` + templates.map((t) => `<option value="${t.id}">${escapeHtml(t.title)}</option>`).join("");
    if (!templates.length) { list.innerHTML = `<p class="muted">${tt("templates.noneShort")}</p>`; return; }
    list.innerHTML = templates.map((t) => `
      <div class="template-item">
        <header><strong>${escapeHtml(t.title)}</strong>
          <div><button class="btn small ghost" onclick="useTemplate(${t.id})">${tt("common.use")}</button>
          <button class="btn small danger" onclick="deleteTemplate(${t.id})">${tt("common.delete")}</button></div>
        </header>
        <p>${escapeHtml(t.message_text.slice(0,120))}</p>
      </div>`).join("");
  } catch (e) { console.error(e); }
}

async function saveTemplate() {
  const title = document.getElementById("template-title").value.trim();
  const message_text = document.getElementById("template-text").value.trim();
  if (!title || !message_text) { toastT("toast.titleRequired", "error"); return; }
  await api("/api/templates", { method: "POST", body: JSON.stringify({ title, message_text }) });
  document.getElementById("template-title").value = "";
  document.getElementById("template-text").value = "";
  toastT("toast.templateSaved", "success");
  loadTemplates();
}

async function useTemplate(id) {
  const templates = await api("/api/templates");
  const t = templates.find((x) => x.id === id);
  if (t) { switchTab("compose"); document.getElementById("message-text").value = t.message_text; document.getElementById("message-text").dispatchEvent(new Event("input")); }
}

async function deleteTemplate(id) {
  if (!confirm(tt("confirm.deleteGeneric"))) return;
  await api(`/api/templates/${id}`, { method: "DELETE" });
  loadTemplates();
}

document.getElementById("template-select")?.addEventListener("change", async (e) => {
  if (!e.target.value) return;
  useTemplate(parseInt(e.target.value));
});

function startRefreshTimer() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (document.hidden) return;
    loadStats();
    updateMiniStatus();
    if (document.getElementById("tab-scheduled")?.classList.contains("active")) loadScheduled();
  }, 30000);
}

// ─── Init ────────────────────────────────────────────
async function init() {
  initIcons();
  updatePlatformChrome();
  if (!appInitialized) {
    connectWebSocket();
    let resizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => setChatThreadOpen(!!activeThreadChat), 150);
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = null;
      } else {
        loadStats();
        updateMiniStatus();
        startRefreshTimer();
      }
    });
    appInitialized = true;
  } else {
    connectWebSocket();
  }
  updateMobileChrome("dashboard");
  renderRecentChats();
  try {
    await Promise.all([loadAccounts("telegram"), loadAccounts("whatsapp")]);
    const cfg = await api("/api/config");
    const phoneEl = document.getElementById("auth-phone");
    if (phoneEl && cfg.telegram_phone_masked && !phoneEl.value) {
      phoneEl.placeholder = `${cfg.telegram_phone_masked}`;
    }
    await loadTelegramCredentials(getAccountId("telegram"));
  } catch (_) {}
  await checkAuthStatus(getAccountId());
  await loadStats();
  await loadScheduled();
  await loadTemplates();
  renderAccountSwitcher();
  await initPostLoginFlow();
  startRefreshTimer();
}

function bootPanel() {
  initTheme();
  initIcons();
  checkPanelAuth().then((ok) => { if (ok) init(); });
}

bootPanel();
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeScheduleModal();
    closeAddAccountModal();
    closeRenameChatModal();
  }
  if (e.target.matches("input, textarea, select")) return;
  if (e.key === "1" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setPlatform("telegram"); }
  if (e.key === "2" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setPlatform("whatsapp"); }
});
document.getElementById("setup-account-label")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") accountSetupContinue();
});
document.getElementById("add-account-overlay")?.addEventListener("click", (e) => {
  if (e.target.id === "add-account-overlay") closeAddAccountModal();
});
document.getElementById("add-account-label")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") confirmAddAccount();
});
document.getElementById("rename-chat-overlay")?.addEventListener("click", (e) => {
  if (e.target.id === "rename-chat-overlay") closeRenameChatModal();
});
document.getElementById("rename-chat-input")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") confirmRenameChat();
});
document.getElementById("schedule-modal")?.addEventListener("click", (e) => {
  if (e.target.id === "schedule-modal") closeScheduleModal();
});
document.getElementById("chat-search")?.addEventListener("focus", () => {
  if (!allChats.length) loadChats();
});
document.getElementById("panel-password")?.addEventListener("input", updatePasswordStrength);
document.getElementById("panel-password")?.addEventListener("keydown", (e) => { if (e.key === "Enter") panelLogin(); });
document.getElementById("panel-password-confirm")?.addEventListener("keydown", (e) => { if (e.key === "Enter") panelLogin(); });
document.getElementById("auth-code")?.addEventListener("keydown", (e) => { if (e.key === "Enter") verifyCode(); });
document.getElementById("chat-reply")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatReply(); }
});
document.getElementById("auth-password")?.addEventListener("keydown", (e) => { if (e.key === "Enter") verifyPassword(); });
