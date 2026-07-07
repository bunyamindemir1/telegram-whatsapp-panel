/**
 * Lucide-style inline SVG icons (stroke, 24×24).
 * https://lucide.dev — MIT
 */
const ICON_PATHS = {
  send: [
    "M22 2 11 13",
    "M22 2 15 22 11 13 2 9 22 2z",
  ],
  "message-circle": ["M7.9 20A9 9 0 1 0 4 16.1L2 22Z"],
  "messages-square": ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
  "layout-dashboard": [
    "M3 3h7v9H3z",
    "M14 3h7v5h-7z",
    "M14 12h7v9h-7z",
    "M3 16h7v5H3z",
  ],
  mail: [
    "M22 7 13.5 15.5a2 2 0 0 1-3 0L2 7",
    "M22 7v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7",
  ],
  clock: ["M12 6v6l4 2", "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z"],
  user: [
    "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2",
    "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  ],
  "file-text": [
    "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",
    "M14 2v4a2 2 0 0 0 2 2h4",
    "M10 9H8",
    "M16 13H8",
    "M16 17H8",
  ],
  "refresh-cw": [
    "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",
    "M21 3v5h-5",
    "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",
    "M8 16H3v5",
  ],
  download: [
    "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",
    "M7 10l5 5 5-5",
    "M12 15V3",
  ],
  pencil: [
    "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z",
    "M15 5l4 4",
  ],
  x: ["M18 6 6 18", "M6 6l12 12"],
  menu: ["M4 12h16", "M4 6h16", "M4 18h16"],
  "arrow-left": ["M19 12H5", "M12 19l-7-7 7-7"],
  "chevron-right": ["M9 18l6-6-6-6"],
  shield: ["M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"],
  lock: [
    "M12 17v-2",
    "M7 11V7a5 5 0 0 1 10 0v4",
    "M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z",
  ],
  "alert-triangle": [
    "M21.73 18 12 2 2.27 18",
    "M12 9v4",
    "M12 17h.01",
  ],
  calendar: [
    "M8 2v4",
    "M16 2v4",
    "M3 10h18",
    "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
  ],
  shuffle: [
    "M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22",
    "M2 6h1.9c1.5 0 2.9.9 3.6 2.2",
    "M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8",
    "M18 2l4 4-4 4",
    "M2 6l4 4-4 4",
  ],
  users: [
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
    "M16 3.128a4 4 0 0 1 0 7.744",
    "M22 21v-2a4 4 0 0 0-3-3.87",
    "M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  ],
  rocket: [
    "M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z",
    "M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z",
    "M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0",
    "M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5",
  ],
  settings: [
    "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z",
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  ],
  "qr-code": [
    "M5 7V5a2 2 0 0 1 2-2h2",
    "M19 7V5a2 2 0 0 0-2-2h-2",
    "M5 17v2a2 2 0 0 0 2 2h2",
    "M19 17v2a2 2 0 0 1-2 2h-2",
    "M7 12h10",
    "M12 7v10",
  ],
  plus: ["M5 12h14", "M12 5v14"],
  search: ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.3-4.3"],
  timer: ["M10 2h4", "M12 14v-4", "M4.93 4.93l1.41 1.41", "M19.07 4.93l-1.41 1.41", "M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z"],
  repeat: ["M17 2l4 4-4 4", "M3 11v-1a4 4 0 0 1 4-4h14", "M7 22l-4-4 4-4", "M21 13v1a4 4 0 0 1-4 4H3"],
  dices: [
    "M16 8h.01",
    "M12 12h.01",
    "M8 16h.01",
    "M8 8h.01",
    "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z",
  ],
  image: [
    "M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z",
    "M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
    "M21 15l-5-5L5 21",
  ],
  video: [
    "M15 10l4.553-2.276A1 1 0 0 1 21 8.618v6.764a1 1 0 0 1-1.447.894L15 14",
    "M3 6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  ],
  mic: [
    "M12 19v3",
    "M19 10v2a7 7 0 0 1-14 0v-2",
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M12 2v7",
  ],
  paperclip: ["M13.234 20.252 21 12.3", "M8 16.5l7.586-7.586a2 2 0 1 0-2.828-2.828L5.172 13.672a4 4 0 1 0 5.656 5.656l8.586-8.586a6 6 0 0 0-8.485-8.485L2.5 9.5"],
  "map-pin": ["M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z", "M12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  smartphone: [
    "M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z",
    "M12 18h.01",
  ],
  "message-square-text": [
    "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    "M13 8H7",
    "M17 12H7",
  ],
  "circle-check": ["M22 11.08V12a10 10 0 1 1-5.93-9.14", "M22 4 12 14.01l-3-3"],
  "circle-x": ["M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z", "M15 9l-6 6", "M9 9l6 6"],
  "circle-alert": ["M12 12h.01", "M12 8v4", "M12 16h.01", "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z"],
  eye: [
    "M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0",
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  ],
  "eye-off": [
    "M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575",
    "M14.084 14.158a3 3 0 0 1-4.242-4.242",
    "M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143",
    "M2 2l20 20",
  ],
  "brand-telegram": [
    "M22 2 11 13",
    "M22 2 15 22 11 13 2 9 22 2z",
  ],
  "brand-whatsapp": ["M7.9 20A9 9 0 1 0 4 16.1L2 22Z"],
  moon: [
    "M12 3a6 6 0 0 0 0 12 6 6 0 0 0 0-12z",
    "M12 1v2",
    "M12 21v2",
    "M4.22 4.22l1.42 1.42",
    "M18.36 18.36l1.42 1.42",
    "M1 12h2",
    "M21 12h2",
    "M4.22 19.78l1.42-1.42",
    "M18.36 5.64l1.42-1.42",
  ],
};

function icon(name, opts = {}) {
  const paths = ICON_PATHS[name];
  if (!paths) return "";
  const size = opts.size ?? 20;
  const cls = opts.class ? `icon ${opts.class}` : "icon";
  const stroke = opts.stroke ?? "currentColor";
  const sw = opts.strokeWidth ?? 2;
  const body = paths.map((d) => `<path d="${d}"/>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" class="${cls}" aria-hidden="true">${body}</svg>`;
}

function setIcon(el, name, opts = {}) {
  if (!el || !name) return;
  el.innerHTML = icon(name, opts);
}

function initIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    const size = parseInt(el.dataset.iconSize || "20", 10);
    const extra = el.className ? ` ${el.className}` : "";
    setIcon(el, el.dataset.icon, { size, class: `icon${extra}`.trim() });
  });
}

function emptyIcon(name, size = 36) {
  return `<span class="empty-icon">${icon(name, { size })}</span>`;
}

function emptyState(name, message, extra = "") {
  return `<div class="empty-state">${emptyIcon(name)}<p>${message}</p>${extra}</div>`;
}

function platformIcon(platform, size = 20) {
  const key = platform === "whatsapp" ? "brand-whatsapp" : "brand-telegram";
  const brand = platform === "whatsapp" ? "icon-brand-wa" : "icon-brand-tg";
  return icon(key, { size, class: `icon ${brand}` });
}

function statusDotHtml(status, label) {
  return `<span class="status-inline"><span class="status-dot dot-${status}"></span><span>${label}</span></span>`;
}

function connectionStatusText(st) {
  if (typeof t === "function") {
    const map = {
      connected: t("status.connected"),
      connecting: t("status.connecting"),
      reconnecting: t("status.reconnecting"),
      qr: t("status.qr"),
      disconnected: t("status.disconnected"),
      offline: t("status.offline"),
    };
    return map[st] || st;
  }
  const fallback = {
    connected: "Connected", connecting: "Connecting", reconnecting: "Reconnecting",
    qr: "QR pending", disconnected: "Disconnected", offline: "Bridge offline",
  };
  return fallback[st] || st;
}

function connectionStatusHtml(st) {
  return statusDotHtml(st, connectionStatusText(st));
}

function btnWithIcon(iconName, text, iconSize = 16) {
  return `<span class="btn-with-icon">${icon(iconName, { size: iconSize, class: "icon btn-leading-icon" })}<span>${text}</span></span>`;
}
