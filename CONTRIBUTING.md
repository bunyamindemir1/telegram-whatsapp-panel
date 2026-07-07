# Contributing to Mesaj Paneli

Thank you for helping make this project better!

## Quick dev setup

```bash
git clone https://github.com/bunyamindemir1/telegram-whatsapp-panel.git
cd telegram-whatsapp-panel
make quick                    # or: make setup for Docker
```

Panel: http://127.0.0.1:8000 · After login, the **first account wizard** guides Telegram/WhatsApp setup.

## Before you PR

```bash
pytest -q
make e2e
make locales
make preflight
```

Update `docs/CHANGELOG.md` under `[Unreleased]` for user-facing changes.

## Code guidelines

- **Python:** follow patterns in `app/`; focused functions, type hints where existing
- **JavaScript:** ES modules in `whatsapp-bridge/`; vanilla JS in `static/js/`
- **Icons:** Lucide paths via `static/js/icons.js` — no emojis in UI
- **Commits:** imperative mood (`Add webhook retry`, `Fix media bulk insert`)
- **UI changes:** include screenshots in PR

## Areas we welcome

- i18n (English UI strings)
- Webhook delivery logs & retry
- PostgreSQL support
- Bridge integration tests
- Documentation & deployment guides
- Scheduled media messages

## Security

Report vulnerabilities per [SECURITY.md](SECURITY.md) — do not open public issues.
