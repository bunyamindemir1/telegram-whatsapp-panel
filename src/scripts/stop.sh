#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="$(cd "$SRC_DIR/.." && pwd)"
cd "$ROOT"

stop_pid() {
  local f="$1"
  if [[ -f "$f" ]]; then
    local pid
    pid=$(cat "$f")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
  fi
}

stop_pid .run/panel.pid
# Bridge managed by panel subprocess — kill stray bridge on 3001
if lsof -ti:3001 >/dev/null 2>&1; then
  lsof -ti:3001 | xargs kill 2>/dev/null || true
fi
echo "Stopped."
