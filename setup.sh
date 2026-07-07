#!/usr/bin/env bash
# Mesaj Paneli — one-command setup (Docker, <1 min after images are cached)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/common.sh"

MODE="docker"
FORCE=0
FAST=0
PORT=8000

usage() {
  cat <<'EOF'
Mesaj Paneli — Kurulum

Kullanım:
  ./setup.sh              Docker ile kur (önerilen)
  ./setup.sh --fast       Docker — imaj varsa build atla (~10 sn)
  ./setup.sh --local      Yerel geliştirme (install.sh + start.sh)
  ./setup.sh --force      Mevcut .env dosyasının üzerine yaz
  ./setup.sh --port 8080  Panel portu (varsayılan: 8000)

Hızlı yerel geliştirme (Docker yok):
  ./install.sh && ./start.sh    # ~30 sn (önbellekli)

Gereksinimler (Docker):
  - Docker 24+ ve Docker Compose v2

Gereksinimler (yerel):
  - Python 3.9+, Node.js 18+
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) MODE="local"; shift ;;
    --fast) FAST=1; shift ;;
    --force) FORCE=1; shift ;;
    --port) PORT="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Bilinmeyen seçenek: $1"; usage; exit 1 ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }

ensure_env() {
  if [[ -f .env && "$FORCE" -eq 0 ]]; then
    yellow "⚠️  .env zaten var — mevcut ayarlar korunuyor."
    yellow "    Yeniden oluşturmak için: ./setup.sh --force"
    # shellcheck disable=SC1091
    set +u; source .env 2>/dev/null || true; set -u
    ADMIN_PASS="${PANEL_ADMIN_PASSWORD:-}"
    return
  fi
  bold "→ Güvenli .env oluşturuluyor..."
  write_env_file "$PORT" docker
}

wait_health() {
  local url="http://127.0.0.1:${PORT}/api/health"
  printf "→ Panel hazırlanıyor"
  if wait_health_url "$url" 90; then
    echo " ✓"
    return 0
  fi
  echo ""
  red "Panel zaman aşımına uğradı. Loglar: docker compose logs -f panel"
  return 1
}

setup_docker() {
  command -v docker >/dev/null || { red "Docker bulunamadı. https://docs.docker.com/get-docker/"; exit 1; }
  docker compose version >/dev/null 2>&1 || { red "Docker Compose v2 gerekli."; exit 1; }

  ensure_env
  export PORT

  if [[ "$FAST" -eq 1 ]] && docker_images_built; then
    bold "→ Docker konteynerleri başlatılıyor (hızlı mod, build yok)..."
    docker compose up -d
  else
    bold "→ Docker konteynerleri başlatılıyor (ilk seferde 2-3 dk sürebilir)..."
    docker compose up -d --build
  fi

  wait_health

  echo ""
  green "╔══════════════════════════════════════════════════╗"
  green "║           Mesaj Paneli hazır!                    ║"
  green "╚══════════════════════════════════════════════════╝"
  echo ""
  echo "  Panel    : http://127.0.0.1:${PORT}"
  echo "  API Docs : http://127.0.0.1:${PORT}/docs"
  if [[ -n "${ADMIN_PASS:-}" ]]; then
    echo "  Kullanıcı: admin"
    echo "  Şifre    : ${ADMIN_PASS}"
    yellow "  (Şifre .setup-credentials.txt dosyasına da kaydedildi)"
  else
    echo "  Giriş    : .env içindeki PANEL_ADMIN_USER / PANEL_ADMIN_PASSWORD"
  fi
  echo ""
  yellow "  Test modu aktif — mesaj gönderilmez (ALLOW_OUTBOUND_MESSAGES=false)"
  echo "  Canlıya geçiş: .env içinde ALLOW_OUTBOUND_MESSAGES=true"
  echo ""
  echo "  Sonraki adımlar:"
  echo "    1. Panele giriş yapın"
  echo "    2. Hesap → Telegram API veya WhatsApp QR bağlayın"
  echo "    3. docs/QUICKSTART.md rehberine bakın"
  echo ""
  echo "  Tekrar başlatma: ./setup.sh --fast"
  echo ""
}

setup_local() {
  chmod +x install.sh start.sh stop.sh 2>/dev/null || true
  ./install.sh
  if [[ ! -f .env || "$FORCE" -eq 1 ]]; then
    write_env_file "$PORT" local
  fi
  echo ""
  green "Yerel kurulum tamam. Başlatmak için:"
  echo "  ./start.sh"
  echo ""
  yellow "Tek komut (kur + başlat): make quick"
}

bold "Mesaj Paneli — Kurulum"
echo ""

if [[ "$MODE" == "local" ]]; then
  setup_local
else
  setup_docker
fi
