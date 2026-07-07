# Project Structure

Professional layout for open-source / portfolio use.

```
telegram-whatsapp-panel/
├── README.md
├── LICENSE
├── Makefile
├── docker-compose.yml
├── app/                    # FastAPI backend
│   ├── main.py
│   ├── i18n.py
│   └── ...
├── config/
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── pytest.ini
├── docker/
│   ├── Dockerfile
│   └── entrypoint.sh
├── docs/
│   ├── CONTRIBUTING.md
│   ├── SECURITY.md
│   ├── QUICKSTART.md
│   └── assets/
├── locales/                # 15 JSON translation files
├── scripts/
│   ├── setup.sh
│   ├── run.py
│   └── ...
├── static/ templates/
├── tests/
└── whatsapp-bridge/
```

## Testing

```bash
make test           # pytest via config/pytest.ini
make e2e            # Playwright browser tests
make locales        # validate 15 locale files
make preflight      # pre-publish checks
```

## Internationalization

- **Server:** `app/i18n.py` resolves locale from `?lang=`, cookie, or `Accept-Language`
- **Client:** `static/js/i18n.js` — `t('key')`, RTL for Arabic
- **Add a string:** edit `locales/en.json`, run `python scripts/validate_locales.py`
