#!/usr/bin/env bash
# Squash all history into one clean commit before FIRST public push.
# Use when preflight reports leaked data in git history.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Not a git repository"
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: remote 'origin' already exists — only run before first push"
  echo "If already pushed, use git filter-repo instead"
  exit 1
fi

echo "→ Creating single clean commit (orphan branch)..."
CURRENT_BRANCH=$(git branch --show-current)
git checkout --orphan _publish_clean
git add -A
git commit -m "$(cat <<'EOF'
Initial public release: Message Panel

Self-hosted Telegram & WhatsApp unified inbox with scheduling,
media, REST API, webhooks, and 15-language UI.
EOF
)"
git branch -D "$CURRENT_BRANCH" 2>/dev/null || true
git branch -m "$CURRENT_BRANCH"
echo "✓ History squashed to 1 commit on branch: $CURRENT_BRANCH"
echo "  Run: ./scripts/preflight_public.sh"
