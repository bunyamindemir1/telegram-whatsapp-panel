#!/usr/bin/env bash
# Pre-publish safety check — run before first git push
set -euo pipefail
PYTHON="${PYTHON:-python3.9}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

red() { printf '\033[31m✗ %s\033[0m\n' "$*"; }
green() { printf '\033[32m✓ %s\033[0m\n' "$*"; }

echo "→ Checking for secrets in staging area..."
if git rev-parse --git-dir >/dev/null 2>&1; then
  for f in .env .setup-credentials.txt data sessions .run; do
    if git ls-files --error-unmatch "$f" 2>/dev/null; then
      red "$f is tracked by git — remove it"
      exit 1
    fi
  done

  echo "→ Scanning staged files for secret patterns..."
  STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)
  if [[ -n "$STAGED" ]]; then
    while IFS= read -r file; do
      [[ -f "$file" ]] || continue
      case "$file" in
        *.example|src/scripts/lib/common.sh|src/tests/*) continue ;;
      esac
      if grep -qE 'BEGIN (RSA |OPENSSH )?PRIVATE KEY' "$file" 2>/dev/null; then
        red "Possible private key in staged file: $file"
        exit 1
      fi
      if grep -qE 'mp_[A-Za-z0-9_-]{24,}' "$file" 2>/dev/null; then
        red "Possible API key in staged file: $file"
        exit 1
      fi
      if grep -qE 'PANEL_ADMIN_PASSWORD=[^[:space:]]+' "$file" 2>/dev/null; then
        red "Possible admin password in staged file: $file"
        exit 1
      fi
      if grep -qE 'SESSION_SECRET=[^[:space:]]+' "$file" 2>/dev/null; then
        if ! grep -qE '(CHANGE_ME|degistirin-)' "$file" 2>/dev/null; then
          red "Possible SESSION_SECRET in staged file: $file"
          exit 1
        fi
      fi
      if grep -qE 'BRIDGE_SECRET=[^[:space:]]+' "$file" 2>/dev/null; then
        if ! grep -qE '(CHANGE_ME|degistirin-)' "$file" 2>/dev/null; then
          red "Possible BRIDGE_SECRET in staged file: $file"
          exit 1
        fi
      fi
      if grep -qE 'TELEGRAM_API_HASH=[0-9a-fA-F]{32}' "$file" 2>/dev/null; then
        red "Possible Telegram API hash in staged file: $file"
        exit 1
      fi
      if grep -qE '(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})' "$file" 2>/dev/null; then
        red "Possible token/API key in staged file: $file"
        exit 1
      fi
    done <<< "$STAGED"
    green "Staged secret scan OK"
  fi

  echo "→ Scanning tracked source for embedded weak bridge default..."
  ALLOW_WEAK_LITERAL='src/app/config.py|src/app/secret_policy.py|src/tests/test_secret_policy.py|src/whatsapp-bridge/server.js'
  while IFS= read -r file; do
    [[ -f "$file" ]] || continue
    case "$file" in
      src/whatsapp-bridge/node_modules/*) continue ;;
    esac
    if echo "$file" | grep -qE "$ALLOW_WEAK_LITERAL"; then
      continue
    fi
    if grep -q 'mesaj-bridge-local-secret' "$file" 2>/dev/null; then
      red "Hardcoded weak bridge secret in tracked file: $file"
      exit 1
    fi
  done < <(git ls-files 'src/**' '.github/**' '*.md' 2>/dev/null || true)
  green "Tracked weak-secret scan OK"
else
  echo "  (not a git repo yet — skip tracked check)"
fi

for path in .env .setup-credentials.txt data sessions .run; do
  if [[ -e "$path" ]] && git rev-parse --git-dir >/dev/null 2>&1; then
    if ! git check-ignore -q "$path" 2>/dev/null; then
      red "$path is not gitignored"
      exit 1
    fi
  fi
done
green "gitignore coverage OK"

echo "→ Locales..."
"$PYTHON" src/scripts/validate_locales.py

echo "→ Unit tests..."
PYTHONPATH=src "$PYTHON" -m pytest -q -c src/config/pytest.ini

echo "→ Bridge syntax..."
node --check src/whatsapp-bridge/server.js

if grep -rq "YOUR_USER" README.md src/docs/ .github/ 2>/dev/null; then
  echo "WARN: Replace YOUR_USER in README/docs before publishing"
fi

echo ""
echo "✓ Ready — see src/docs/PUBLISHING.md for GitHub steps"
