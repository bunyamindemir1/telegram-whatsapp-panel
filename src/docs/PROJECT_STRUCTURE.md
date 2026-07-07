# Project structure

```
telegram-whatsapp-panel/
├── README.md                 # project overview (EN + TR summary)
├── Makefile                  # thin wrapper → src/Makefile
├── CONTRIBUTING.md           # points to src/docs/CONTRIBUTING.md
├── SECURITY.md               # vulnerability reporting
├── .github/                  # CI, issue templates, CodeQL
└── src/
    ├── app/                  # FastAPI application
    │   ├── main.py           # panel HTTP routes, WebSocket, lifespan
    │   ├── api_v1.py         # external REST API (/api/v1)
    │   ├── schemas/          # Pydantic request models
    │   ├── models.py         # SQLAlchemy ORM
    │   ├── *_service.py      # domain logic (scheduler, messaging, …)
    │   └── error_codes.py    # stable API error i18n keys
    ├── config/               # requirements.txt, pytest.ini
    ├── docker/               # Dockerfile, compose.yml
    ├── docs/                 # guides (see ARCHITECTURE.md)
    ├── locales/              # UI translations (en.json master)
    ├── scripts/              # setup, locale tools
    ├── static/               # CSS, JS, icons
    ├── templates/            # Jinja2 (index.html SPA shell)
    ├── tests/                # pytest + Playwright e2e/
    └── whatsapp-bridge/      # Node.js Baileys service
```

## Why a thin GitHub root?

GitHub requires `.github/` and `.gitignore` at the repository root. Application code lives under `src/` so the landing page shows README + Makefile only.

## Runtime data (gitignored)

| Path | Purpose |
|------|---------|
| `.env` | Secrets and feature flags |
| `data/` | SQLite database |
| `sessions/` | Telethon session files |
| `.venv/` | Local Python environment |

## Commands (from repo root)

```bash
make setup    # Docker install + start
make quick    # local install + start
make test     # unit tests
make e2e      # browser tests
make locales  # validate translation key parity
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for auth boundaries, message lifecycle, bridge contract, and design decisions.
