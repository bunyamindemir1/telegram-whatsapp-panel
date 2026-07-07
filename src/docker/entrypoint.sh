#!/bin/sh
set -e
cd /app
echo "Mesaj Paneli başlatılıyor (ENV=${ENV:-development})..."
if [ "${ALLOW_OUTBOUND_MESSAGES:-false}" != "true" ]; then
  echo "⚠️  TEST MODU: Giden mesajlar KAPALI (ALLOW_OUTBOUND_MESSAGES=false)"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
