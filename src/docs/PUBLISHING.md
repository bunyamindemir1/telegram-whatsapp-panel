# Publishing to GitHub

Checklist before making the repository public (portfolio / open source).

## 1. Pre-flight

```bash
# Secrets not in repo
git status
git check-ignore -v data/ sessions/ .env .setup-credentials.txt .run/

# Full gate (tests + secret scan + governance)
make publish-check
./scripts/preflight_public.sh

If preflight reports **git history leaks** (first commit had old test credentials):

```bash
chmod +x scripts/squash_for_publish.sh
./scripts/squash_for_publish.sh   # only before first push / no remote yet
./scripts/preflight_public.sh
```
```

## 2. Remote (already configured)

Repository: **https://github.com/bunyamindemir1/telegram-whatsapp-panel**

```bash
git remote add origin git@github.com:bunyamindemir1/telegram-whatsapp-panel.git
# or HTTPS:
# git remote add origin https://github.com/bunyamindemir1/telegram-whatsapp-panel.git
```

## 3. Push

## 4. Repository settings (GitHub UI — after first push)

**Repository name:** `telegram-whatsapp-panel`

**About (description):**
```
Schedule WhatsApp & Telegram messages from one self-hosted panel — recurring sends, random daily windows, templates, unified inbox, REST API & webhooks on personal accounts. FastAPI + Telethon + Baileys. Docker.
```

**Topics:** `telegram`, `whatsapp`, `message-scheduler`, `scheduled-messages`, `self-hosted`, `unified-inbox`, `telegram-panel`, `whatsapp-automation`, `fastapi`, `telethon`, `baileys`, `rest-api`, `webhooks`, `docker`, `messaging`, `automation`, `open-source`, `i18n`, `message-panel`, `inbox`

Apply in one command: `./.github/apply-repo-seo.sh` (see [.github/REPO_ABOUT.md](../.github/REPO_ABOUT.md))

| Setting | Where | Recommended |
|---------|-------|-------------|
| Description + topics | Settings → General | See REPO_ABOUT.md or run apply script |
| Secret scanning | Settings → Code security | **On** |
| Push protection | Settings → Code security | **On** |
| Dependabot alerts | Settings → Code security | **On** |
| Private vulnerability reporting | Settings → Code security | **On** |
| Branch protection | Settings → Branches | Require CI, block force push |
| Default branch | Settings → General | `main` |

## 5. What must NEVER be committed

- `.env`, `.setup-credentials.txt`, `.run/`
- `data/` (DB, media, WhatsApp session)
- `sessions/` (Telegram `.session` files)
- Real API keys / phone numbers in commits

## 6. After publish

- Verify CI badge turns green on `main`
- Add screenshot to README if not already: `docs/assets/screenshot.png`
- Star History (optional): [star-history.com](https://star-history.com)

## 7. Donations (later)

Edit `.github/FUNDING.yml`:

```yaml
github: your-username
ko_fi: yourname
```
