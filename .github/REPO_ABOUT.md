# GitHub repository About & SEO

## Important: GitHub cannot geo-target README

GitHub shows **the same README to every visitor**, regardless of country or browser language. There is no setting to show English in the US and Turkish in Turkey.

**What works instead:**

| Layer | Strategy |
|-------|----------|
| **GitHub README** | English-first at the top; Turkish section at `#turkce` |
| **GitHub About** | English description (global search) |
| **Panel app** | 15-language UI — user picks language in sidebar or `?lang=xx` |

---

## Apply settings (CLI)

```bash
gh auth login
./.github/apply-repo-seo.sh
```

---

## Manual About box

Repo home → **About** → gear icon:

| Field | Value |
|-------|-------|
| **Description** | `Self-hosted Telegram & WhatsApp message scheduler — unified inbox, REST API, webhooks, 15-language UI. FastAPI, Telethon, Baileys, Docker.` |
| **Website** | `https://github.com/bunyamindemir1/telegram-whatsapp-panel` |

### Topics

```
telegram whatsapp message-scheduler self-hosted fastapi telethon baileys
rest-api webhooks docker messaging automation open-source i18n
```

---

## Optional extras

- **Social preview:** Settings → General → upload `src/docs/assets/screenshot-dashboard.png` (1280×640)
- **Pinned README section:** Keep English content above the fold; link `🇹🇷 Türkçe` near the top
- **Releases:** Tag stable versions with English release notes

---

## Panel i18n (the real multilingual experience)

Users get localized UI inside the app:

- **Complete:** English, Turkish
- **Community:** ar, de, es, fr, it, ja, ko, nl, pl, pt, ru, uk, zh
- **How:** sidebar dropdown · `?lang=tr` · `Accept-Language` cookie

See [src/docs/I18N.md](../src/docs/I18N.md).
