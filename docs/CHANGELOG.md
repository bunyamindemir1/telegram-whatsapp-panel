# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- **Cleaner repo root** — shell scripts moved to `scripts/`, governance docs to `docs/` and `.github/`
- `pyproject.toml` replaces `pytest.ini`; primary install via `make setup`

### Added
- **First account wizard** — after login, guided Telegram/WhatsApp connect flow
- Dashboard **Connect now** banner when no account is linked
- `account_setup_snapshot` API fields on `/api/panel/status`
- **Fast local dev path**: `install.sh`, `start.sh`, `stop.sh`, `make quick` (~30s, no Docker)
- `setup.sh --fast` — skip Docker rebuild when images exist (~10s restart)
- `scripts/smoke_local.sh`, `scripts/preflight_public.sh`, `scripts/squash_for_publish.sh`
- `scripts/lib/common.sh` — shared env/health helpers
- `.github/CODEOWNERS`, `dependabot.yml`, `SUPPORT.md`, CodeQL workflow
- README comparison table + extra badges for GitHub visibility
- One-command setup script (`setup.sh`) with auto-generated secrets
- Premium README, docs site (`docs/`), GitHub issue/PR templates
- Project banner, favicon, improved login branding
- Makefile (`make setup`, `make test`, `make dev`)
- Sponsor placeholder (`.github/FUNDING.yml`)
- **15-language UI** (EN, TR, AR RTL, RU, DE, FR, ES, PT, IT, NL, PL, UK, ZH, JA, KO) — 377 keys
- Playwright E2E tests (`tests/e2e/`)
- Locale validation script (`scripts/validate_locales.py`)
- Inbound media download (WhatsApp Baileys + Telegram Telethon)
- Panel `/api/media` and `/api/messages/send-media` for UI
- Media bubbles in chat (image, video, audio, document)
- Chat compose attachment button (paperclip)
- Webhook system (`/api/v1/webhooks`)
- Developer panel (API keys + webhooks UI)
- Light/dark theme toggle
- First-run onboarding wizard
- Premium branding (Pro badge)

### Fixed
- Docker image now includes `locales/` (i18n works in containers)
- `start.sh` disables uvicorn reload in background (`NO_RELOAD`) for stable local runs

### Security
- Production rejects weak/placeholder `SESSION_SECRET`, `BRIDGE_SECRET`, `PANEL_ADMIN_PASSWORD`
- Bridge token check uses timing-safe comparison (Python + Node)
- OpenAPI `/docs` disabled in production by default (`ENABLE_OPENAPI=true` to enable)
- Health endpoint hides `env` in production
- Extra security headers (HSTS on HTTPS, DNS prefetch off)
- `docker-compose` requires secrets from `.env` (no weak defaults)
- `prepare_github.sh` scans staged files for leaked secrets
- Test fixtures use fake API credentials (no real hashes in repo)
- `.gitignore` covers `.run/` logs
- Production startup rejects default `BRIDGE_SECRET`
- Test endpoint disabled in production
- Bridge binds to `127.0.0.1` by default
- Removed hardcoded phone number defaults from config

## [0.9.0] - 2026-07-07

### Added
- Multi-account Telegram and WhatsApp support
- Lucide-style icon set
- Bulk message import with progress UI
- Conversation custom labels
- Panel authentication with bcrypt
