# Project Structure

Professional layout for open-source / portfolio use.

```
telegram-whatsapp-panel/
├── app/                    # FastAPI backend
│   ├── main.py             # Routes, WebSocket, internal bridge API
│   ├── i18n.py             # 15-language locale loader
│   ├── api_v1.py           # Public REST API
│   ├── telegram_service.py
│   ├── whatsapp_service.py
│   └── ...
├── locales/                # UI translations (15 JSON files)
│   ├── en.json             # Master keys (219 strings)
│   ├── tr.json
│   ├── ar.json             # RTL
│   └── ...
├── static/
│   ├── js/
│   │   ├── i18n.js         # Client i18n engine
│   │   ├── app.js          # Panel SPA logic
│   │   └── icons.js
│   └── css/style.css
├── templates/
│   └── index.html          # Single-page shell (data-i18n)
├── whatsapp-bridge/        # Node.js Baileys service
├── docs/
│   ├── en/                 # English docs index
│   ├── tr/                 # Turkish docs index
│   ├── QUICKSTART.md
│   ├── API.md
│   └── assets/
├── tests/
│   ├── test_*.py           # Unit & integration (pytest + httpx)
│   ├── test_i18n.py        # Locale integrity
│   └── e2e/                # Playwright browser tests
├── scripts/
│   ├── validate_locales.py
│   └── setup.sh            # (root) one-command Docker install
├── .github/
│   ├── workflows/ci.yml
│   ├── ISSUE_TEMPLATE/
│   └── FUNDING.yml
├── setup.sh
├── Makefile
├── docker-compose.yml
└── README.md
```

## Testing

```bash
pytest -q          # unit + API (e2e excluded by default)
make e2e           # Playwright browser tests
make locales       # validate 15 locale files
make publish-check # pre-GitHub checklist
```

## Internationalization

- **Server:** `app/i18n.py` resolves locale from `?lang=`, cookie, or `Accept-Language`
- **Client:** `static/js/i18n.js` — `t('key')`, RTL for Arabic, localStorage persistence
- **Add a string:** edit `locales/en.json`, run `python scripts/validate_locales.py`, translate other files
