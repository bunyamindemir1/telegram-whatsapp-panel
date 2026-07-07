# Project Structure

```
telegram-whatsapp-panel/          ← GitHub root (5 items)
├── README.md
├── LICENSE
├── Makefile
├── docker-compose.yml
└── src/
    ├── app/                      FastAPI backend
    ├── config/                   requirements.txt, pytest.ini
    ├── docker/                   Dockerfile + entrypoint
    ├── docs/                     guides, CONTRIBUTING, SECURITY
    ├── locales/                  15 JSON translation files
    ├── scripts/                  setup, install, dev tools
    ├── static/ templates/
    ├── tests/                    pytest + Playwright E2E
    └── whatsapp-bridge/          Node.js Baileys service
```

Runtime data (gitignored) stays at repo root: `.env`, `data/`, `sessions/`, `.venv/`.

## Testing

```bash
make test           # pytest via src/config/pytest.ini
make e2e            # Playwright browser tests
make locales        # validate 15 locale files
make preflight      # pre-publish checks
```

## Internationalization

- **Server:** `src/app/i18n.py`
- **Client:** `src/static/js/i18n.js`
- **Add a string:** edit `src/locales/en.json`, run `make locales`
