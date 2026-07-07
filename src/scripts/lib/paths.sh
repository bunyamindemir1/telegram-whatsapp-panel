#!/usr/bin/env bash
# Shared path helpers — source from src/scripts/*.sh
mesaj_paths() {
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  ROOT="$(cd "$SRC_DIR/.." && pwd)"
}
