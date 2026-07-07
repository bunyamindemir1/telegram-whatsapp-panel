/**
 * Mesaj Paneli — client-side i18n (15 languages)
 */
(function () {
  const STORAGE_KEY = "mesaj_locale";
  let messages = window.__I18N__ || {};
  let locale = window.__LOCALE__ || "en";

  function interpolate(text, vars) {
    if (!vars) return text;
    return String(text).replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? String(vars[k]) : `{${k}}`));
  }

  function t(key, vars) {
    const raw = messages[key] ?? window.__I18N_FALLBACK__?.[key] ?? key;
    return interpolate(raw, vars);
  }

  function isRtl(code) {
    return (window.__LOCALES__ || []).find((l) => l.code === code)?.rtl === true;
  }

  function applyDom() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      if (el.childElementCount && !el.hasAttribute("data-i18n-force")) return;
      el.textContent = t(key);
    });
    document.querySelectorAll("[data-i18n-html]").forEach((el) => {
      const key = el.getAttribute("data-i18n-html");
      if (key) el.innerHTML = t(key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (key) el.placeholder = t(key);
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (key) el.title = t(key);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      const key = el.getAttribute("data-i18n-aria");
      if (key) el.setAttribute("aria-label", t(key));
    });
    document.title = t("meta.title");
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute("content", t("meta.description"));
  }

  function applyRtl(code) {
    const rtl = isRtl(code);
    document.documentElement.dir = rtl ? "rtl" : "ltr";
    document.documentElement.lang = code;
    document.body.classList.toggle("rtl", rtl);
  }

  async function loadLocale(code) {
    if (code === locale && Object.keys(messages).length) return;
    const res = await fetch(`/api/i18n/${code}`);
    if (!res.ok) throw new Error("Locale load failed");
    const data = await res.json();
    messages = data.messages || {};
    locale = data.locale || code;
    window.__I18N__ = messages;
    window.__LOCALE__ = locale;
    applyRtl(locale);
    applyDom();
    localStorage.setItem(STORAGE_KEY, locale);
    document.cookie = `mesaj_locale=${locale};path=/;max-age=31536000;SameSite=Lax`;
    window.dispatchEvent(new CustomEvent("localechange", { detail: { locale } }));
  }

  async function setLocale(code) {
    if (!code || code === locale) return;
    await loadLocale(code);
    const sel = document.getElementById("lang-select");
    if (sel) sel.value = locale;
  }

  function initLangSelect() {
    const sel = document.getElementById("lang-select");
    if (!sel || sel.dataset.ready) return;
    const list = window.__LOCALES__ || [];
    sel.innerHTML = list
      .map((l) => `<option value="${l.code}">${l.native}</option>`)
      .join("");
    sel.value = locale;
    sel.dataset.ready = "1";
    sel.addEventListener("change", () => setLocale(sel.value));
  }

  async function initI18n() {
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial = stored && (window.__LOCALES__ || []).some((l) => l.code === stored) ? stored : locale;
    if (initial !== locale) {
      try {
        await loadLocale(initial);
      } catch {
        applyRtl(locale);
        applyDom();
      }
    } else {
      applyRtl(locale);
      applyDom();
    }
    initLangSelect();
  }

  window.t = t;
  window.applyI18n = applyDom;
  window.setLocale = setLocale;
  window.getLocale = () => locale;
  window.initI18n = initI18n;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initI18n);
  } else {
    initI18n();
  }
})();
