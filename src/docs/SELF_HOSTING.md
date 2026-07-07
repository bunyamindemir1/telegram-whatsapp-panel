# Kendi Sunucunuzda Çalıştırma

## Docker Compose (önerilen)

```bash
make setup
```

Üretim ortamı için `.env` değerlerini gözden geçirin:

| Değişken | Açıklama |
|----------|----------|
| `SESSION_SECRET` | Oturum çerezi imzası (32+ karakter) |
| `BRIDGE_SECRET` | Panel ↔ WhatsApp köprü token |
| `PANEL_ADMIN_PASSWORD` | Panel giriş şifresi |
| `ALLOW_OUTBOUND_MESSAGES` | `true` = canlı gönderim |
| `TIMEZONE` | Zamanlama gösterimi (varsayılan: Europe/Istanbul) |

## HTTPS ile yayınlama

Panel doğrudan internete açmayın. Örnek Caddy:

```caddy
panel.example.com {
    reverse_proxy localhost:8000
}
```

`SESSION_SECRET` ve şifreleri mutlaka değiştirin.

## Veri kalıcılığı

Docker volume'ları:

| Volume | İçerik |
|--------|--------|
| `panel_data` | SQLite DB, medya, şifreli kimlik bilgileri |
| `panel_sessions` | Telegram oturum dosyaları |
| `wa_data` | WhatsApp oturum verisi |

Yedekleme:

```bash
docker compose down
docker run --rm -v telegram-whatsapp-panel_panel_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/panel-data-backup.tar.gz -C /data .
```

## Güncelleme

```bash
git pull
docker compose up -d --build
```

## Kaynak tüketimi

Tipik kullanım: ~200–400 MB RAM (panel + köprü). Medya birikimi `data/media/` altında büyüyebilir.

## Sorun giderme

```bash
docker compose ps
docker compose logs panel --tail 100
docker compose logs whatsapp-bridge --tail 100
curl -s http://127.0.0.1:8000/api/health
```

Daha fazla: [FAQ.md](FAQ.md)
