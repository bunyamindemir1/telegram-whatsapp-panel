#!/usr/bin/env bash
# Fast local dependency install (~15–45s, cached)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3.9}"
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

command -v "$PYTHON" >/dev/null || { echo "Need Python 3.9+"; exit 1; }
command -v node >/dev/null || { echo "Need Node.js 18+"; exit 1; }

bold "→ Installing dependencies (parallel)..."

if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

(
  pip install -q -r requirements.txt
  echo "  ✓ Python"
) &
PID_PY=$!

(
  cd whatsapp-bridge
  if [[ -f package-lock.json ]]; then npm ci --silent 2>/dev/null || npm install --silent
  else npm install --silent
  fi
  echo "  ✓ Node bridge"
) &
PID_NP=$!

wait "$PID_PY" "$PID_NP"
mkdir -p data sessions .run locales
green "✓ Install complete — run: make start"
