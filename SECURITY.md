# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest `main` | yes |

## Reporting a Vulnerability

Please **do not** open public GitHub issues for security vulnerabilities.

Use a **[private security advisory](https://github.com/bunyamindemir1/telegram-whatsapp-panel/security/advisories/new)** on GitHub (preferred) or contact the maintainer privately with:

- Description of the issue
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

We aim to respond within 7 days.

## Threat Model

Mesaj Paneli is a **self-hosted** tool that connects to **your own** Telegram and WhatsApp accounts. You are responsible for:

- Securing the server and network access
- Complying with [Telegram](https://telegram.org/tos) and [WhatsApp](https://www.whatsapp.com/legal) Terms of Service
- Not using the tool for spam or unsolicited messaging

### Critical surfaces

| Surface | Risk | Mitigation |
|---------|------|------------|
| Panel (`:8000`) | Unauthorized access | Session auth, bcrypt passwords, rate limiting |
| WhatsApp bridge (`:3001`) | Message send without auth | `X-Bridge-Token` required; bind to `127.0.0.1` by default |
| API keys (`/api/v1`) | Programmatic abuse | Bearer tokens (hashed), HTTPS in production |
| Session files | Account takeover | Keep `sessions/` and `data/` private; encrypt backups |
| `ALLOW_OUTBOUND_MESSAGES` | Accidental sends | Defaults to `false` (dry-run) |

### Production checklist

- Run `make setup` (generates strong secrets) — never use placeholder values
- Set `ENV=production` and `REQUIRE_PANEL_AUTH=true`
- `SESSION_SECRET`, `BRIDGE_SECRET`, `PANEL_ADMIN_PASSWORD` must be unique (app refuses weak defaults)
- Use HTTPS via reverse proxy (nginx, Caddy, Traefik)
- Do not expose port `3001` publicly (Docker: bridge is internal only)
- OpenAPI `/docs` is **disabled** in production by default (`ENABLE_OPENAPI=true` to enable)
- Rotate API keys periodically
- Back up `data/.encryption_key` (or `CREDENTIALS_ENCRYPTION_KEY`) with your data volume
- Never commit: `.env`, `.setup-credentials.txt`, `data/`, `sessions/`, `.run/`
- Before push: `make publish-check` scans for leaked secrets
