#!/usr/bin/env bash
# Full local smoke test — run while panel is up (./start.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3.9}"
PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"

red() { printf '\033[31m✗ %s\033[0m\n' "$*"; }
green() { printf '\033[32m✓ %s\033[0m\n' "$*"; }

fail() { red "$1"; exit 1; }

yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

echo "=== Local smoke test ==="

curl -fsS "$BASE/api/health" >/dev/null || fail "Health endpoint down"
green "Health OK"

HEALTH=$(curl -fsS "$BASE/api/health")
echo "$HEALTH" | grep -q '"ok":true' || fail "Health payload invalid"
green "Health JSON OK"

LOCS=$(curl -fsS "$BASE/api/i18n/locales")
echo "$LOCS" | grep -q '"locales"' || fail "i18n locales API"
COUNT=$(echo "$LOCS" | "$PYTHON" -c "import sys,json; print(len(json.load(sys.stdin)['locales']))")
[[ "$COUNT" -eq 15 ]] || fail "Expected 15 locales, got $COUNT"
green "i18n API: 15 locales"

CODE=$(curl -fsS -o /dev/null -w "%{http_code}" "$BASE/?lang=en")
[[ "$CODE" == "200" ]] || fail "Homepage HTTP $CODE"
green "Homepage 200"

HTML=$(curl -fsS "$BASE/?lang=tr")
echo "$HTML" | grep -q 'lang-select' || fail "Language selector missing"
green "UI shell OK"

BRIDGE=$(curl -fsS "$BASE/api/health" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('whatsapp_bridge', False))")
green "WhatsApp bridge reachable: $BRIDGE"

echo "→ Locale files..."
"$PYTHON" src/scripts/validate_locales.py || fail "locale validation failed"
green "locales OK"

echo "→ Packaging checks..."
PYTHONPATH=src "$PYTHON" -m pytest -q src/tests/test_docker_packaging.py src/tests/test_i18n.py || fail "packaging/i18n tests failed"
green "packaging tests OK"

echo ""
green "=== All local smoke tests passed ==="
