#!/usr/bin/env bash
# Public GitHub release preflight — run before first public push
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3.9}"

red() { printf '\033[31m✗ %s\033[0m\n' "$*"; }
green() { printf '\033[32m✓ %s\033[0m\n' "$*"; }
yellow() { printf '\033[33m⚠ %s\033[0m\n' "$*"; }
section() { printf '\n\033[1m── %s ──\033[0m\n' "$*"; }

FAIL=0
warn() { yellow "$1"; }
fail() { red "$1"; FAIL=1; }

section "1. Governance files (OSPO baseline)"
REQUIRED=(
  LICENSE
  README.md
  src/docs/CONTRIBUTING.md
  src/docs/SECURITY.md
  .github/CODE_OF_CONDUCT.md
  src/docs/CHANGELOG.md
  src/docs/SUPPORT.md
  .github/CODEOWNERS
  .github/dependabot.yml
  .github/workflows/ci.yml
  .github/PULL_REQUEST_TEMPLATE.md
)
for f in "${REQUIRED[@]}"; do
  if [[ -f "$f" ]]; then green "$f"; else fail "Missing: $f"; fi
done

section "2. Secrets & sensitive data"
for f in .env .setup-credentials.txt; do
  if git ls-files --error-unmatch "$f" 2>/dev/null; then
    fail "$f is tracked by git"
  else
    green "$f not tracked"
  fi
done
for f in data sessions .run .venv; do
  if [[ -e "$f" ]] && ! git check-ignore -q "$f" 2>/dev/null; then
    fail "$f exists but is not gitignored"
  else
    green "$f ignored or absent"
  fi
done

section "3. Git history scan (full tree)"
if git rev-parse --git-dir >/dev/null 2>&1; then
  HISTORY_HITS=0
  check_history() {
    local label="$1"
    shift
    for needle in "$@"; do
      if git log --all -S "$needle" --oneline -- . \
          ':(exclude)src/scripts/preflight_public.sh' 2>/dev/null | grep -q .; then
        fail "Git history contains: $label"
        HISTORY_HITS=1
      fi
    done
  }
  check_history "leaked API hash" "891a8bc2d58e4c0827dd3dfac0f9ea48"
  check_history "leaked API id" "37625430"
  check_history "personal phone" "905070401109"
  if [[ "$HISTORY_HITS" -eq 0 ]]; then green "Git history clean"; fi
else
  warn "Not a git repo"
fi

section "4. License & metadata"
if [[ -f LICENSE ]] && grep -qi "MIT License" LICENSE; then
  green "MIT LICENSE present"
else
  fail "LICENSE missing or not MIT"
fi
if grep -q "bunyamindemir1/telegram-whatsapp-panel" README.md; then
  green "README repo URLs set"
else
  warn "Update README GitHub URLs before publish"
fi
if grep -rq "YOUR_USER" README.md src/docs/ .github/ 2>/dev/null; then
  warn "Replace YOUR_USER placeholders"
fi

section "5. CI workflow hygiene"
if grep -q "^permissions:" .github/workflows/ci.yml; then
  green "CI has explicit permissions"
else
  warn "Add permissions: contents: read to CI"
fi
if grep -qE 'uses: actions/checkout@v[0-9]+' .github/workflows/ci.yml; then
  yellow "CI uses action tags (@v4) — consider pinning to commit SHA for supply-chain hardening"
fi

section "6. Automated tests"
"$PYTHON" src/scripts/validate_locales.py
PYTHONPATH=src "$PYTHON" -m pytest -q -c src/config/pytest.ini -m "not e2e"
node --check src/whatsapp-bridge/server.js
green "Tests & locale validation passed"

section "7. GitHub UI settings (manual — after repo created)"
cat <<'EOF'
  □ Settings → General: description + topics (telegram, whatsapp, fastapi, self-hosted)
  □ Settings → Code security: Secret scanning + Push protection ON
  □ Settings → Code security: Dependabot alerts + security updates ON
  □ Settings → Code security: Private vulnerability reporting ON
  □ Settings → Branches: protect main (require CI, no force push)
  □ Settings → Actions: allow workflows, review third-party actions
  □ Verify CI badge green on main after first push
EOF

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  green "════════════════════════════════════════"
  green "  PREFLIGHT PASSED — safe to push public"
  green "════════════════════════════════════════"
  echo ""
  echo "Next: git add . && git commit && gh repo create telegram-whatsapp-panel --public --push"
else
  red "════════════════════════════════════════"
  red "  PREFLIGHT FAILED — fix items above first"
  red "════════════════════════════════════════"
  exit 1
fi
