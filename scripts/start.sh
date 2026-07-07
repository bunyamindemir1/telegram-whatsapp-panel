#!/usr/bin/env bash
# Start panel locally in ~5s (after install.sh)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

PORT="${PORT:-8000}"
FORCE_ENV=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-env) FORCE_ENV=1; shift ;;
    --port) PORT="${2:?}"; shift 2 ;;
    -h|--help)
      echo "Usage: make start  (or ./scripts/start.sh [--port 8000] [--force-env])"
      exit 0 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

if [[ ! -d .venv ]]; then
  echo "Run make install first"
  exit 1
fi

if [[ ! -f .env || "$FORCE_ENV" -eq 1 ]]; then
  echo "→ Writing .env (local dev)..."
  write_env_file "$PORT" local
else
  # shellcheck disable=SC1091
  set +u; source .env 2>/dev/null || true; set -u
  export ADMIN_PASS="${PANEL_ADMIN_PASSWORD:-}"
fi

if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT in use — stop with make stop or use --port"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
mkdir -p .run data sessions

echo "→ Starting panel (bridge auto-managed)..."
nohup env NO_RELOAD=1 python run.py > .run/panel.log 2>&1 &
echo $! > .run/panel.pid

URL="http://127.0.0.1:${PORT}/api/health"
printf "→ Waiting for panel"
if wait_health_url "$URL" 75; then
  echo " ✓"
else
  echo ""
  echo "Failed — see .run/panel.log"
  tail -20 .run/panel.log 2>/dev/null || true
  exit 1
fi

echo ""
echo "  Panel : http://127.0.0.1:${PORT}"
echo "  Docs  : http://127.0.0.1:${PORT}/docs"
if [[ -n "${ADMIN_PASS:-}" ]]; then
  echo "  Login : admin — password in .setup-credentials.txt"
fi
echo "  Stop  : make stop"
echo "  Logs  : tail -f .run/panel.log"
