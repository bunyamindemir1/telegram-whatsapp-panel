#!/usr/bin/env bash
# Shared helpers for setup.sh / start.sh

rand_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr -d '/+=' | head -c 32
  else
    python3 -c "import secrets; print(secrets.token_urlsafe(24))"
  fi
}

rand_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 18 | tr -d '/+=' | head -c 16
  else
    python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(16)))"
  fi
}

write_env_file() {
  local port="${1:-8000}"
  local mode="${2:-docker}"  # docker | local
  local admin_pass session_secret bridge_secret
  admin_pass="$(rand_password)"
  session_secret="$(rand_secret)"
  bridge_secret="$(rand_secret)"

  if [[ "$mode" == "local" ]]; then
    cat > .env <<EOF
# Auto-generated $(date -u +"%Y-%m-%d %H:%M UTC") — local dev
ENV=development
HOST=127.0.0.1
PORT=${port}

SESSION_SECRET=${session_secret}
BRIDGE_SECRET=${bridge_secret}
PANEL_ADMIN_USER=admin
PANEL_ADMIN_PASSWORD=${admin_pass}
REQUIRE_PANEL_AUTH=true

ALLOW_OUTBOUND_MESSAGES=false

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

MANAGE_WHATSAPP_BRIDGE=true
WHATSAPP_BRIDGE_URL=http://127.0.0.1:3001
WHATSAPP_BRIDGE_PORT=3001
PANEL_URL=http://127.0.0.1:${port}
TIMEZONE=Europe/Istanbul
EOF
  else
    cat > .env <<EOF
# Auto-generated $(date -u +"%Y-%m-%d %H:%M UTC") — docker
ENV=production
HOST=0.0.0.0
PORT=${port}

SESSION_SECRET=${session_secret}
BRIDGE_SECRET=${bridge_secret}
PANEL_ADMIN_USER=admin
PANEL_ADMIN_PASSWORD=${admin_pass}
REQUIRE_PANEL_AUTH=true

ALLOW_OUTBOUND_MESSAGES=false

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

MANAGE_WHATSAPP_BRIDGE=false
WHATSAPP_BRIDGE_URL=http://whatsapp-bridge:3001
WHATSAPP_BRIDGE_PORT=3001
PANEL_URL=http://panel:8000
TIMEZONE=Europe/Istanbul
EOF
  fi

  mkdir -p data sessions .run
  chmod 600 .env 2>/dev/null || true

  cat > .setup-credentials.txt <<EOF
Message Panel — credentials
Created: $(date)

URL      : http://127.0.0.1:${port}
User     : admin
Password : ${admin_pass}

Delete after saving: rm .setup-credentials.txt
EOF
  chmod 600 .setup-credentials.txt 2>/dev/null || true
  export ADMIN_PASS="$admin_pass"
}

wait_health_url() {
  local url="$1"
  local max="${2:-60}"
  local i=0
  while [[ $i -lt $max ]]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.4
    i=$((i + 1))
  done
  return 1
}

docker_images_built() {
  docker compose images -q panel 2>/dev/null | grep -q .
}
