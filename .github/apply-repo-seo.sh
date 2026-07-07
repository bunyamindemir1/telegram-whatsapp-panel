#!/usr/bin/env bash
# Apply GitHub About description, homepage, and topics (requires: gh auth login)
set -euo pipefail

REPO="${GITHUB_REPO:-bunyamindemir1/telegram-whatsapp-panel}"

# English-first for global GitHub search; mentions i18n for panel UI
DESC='Self-hosted Telegram & WhatsApp message scheduler — unified inbox, REST API, webhooks, 15-language UI. FastAPI, Telethon, Baileys, Docker.'

TOPICS=(
  telegram whatsapp message-scheduler self-hosted fastapi telethon baileys
  rest-api webhooks docker messaging automation open-source i18n
)

if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI: https://cli.github.com/" >&2
  exit 1
fi

gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login" >&2; exit 1; }

echo "Updating $REPO (English About + topics) …"
gh repo edit "$REPO" \
  --description "$DESC" \
  --homepage "https://github.com/$REPO"

for t in "${TOPICS[@]}"; do
  gh repo edit "$REPO" --add-topic "$t" 2>/dev/null || true
done

echo "Done. Verify: https://github.com/$REPO"
echo "Turkish README section: https://github.com/$REPO#turkce"
