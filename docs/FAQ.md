# Sık Sorulan Sorular

## Kurulum

### Kurulum ne kadar sürer?

- **İlk Docker build:** 2–3 dakika (bağımlılık indirme)
- **Sonraki başlatmalar:** ~10–30 saniye
- `make setup` komutu `.env` oluşturma + konteyner başlatma dahil **1 dakikanın altında** biter (image cache varsa)

### Docker olmadan kurabilir miyim?

Evet:

```bash
make setup -- --local
source .venv/bin/activate && python scripts/run.py
# ayrı terminal: cd whatsapp-bridge && node server.js
```

### Port 8000 meşgul

```bash
make setup -- --port 8080
```

veya `.env` içinde `PORT=8080` değiştirin.

## Güvenlik

### Varsayılan şifre güvenli mi?

`make setup` rastgele 16 karakterlik şifre üretir. `.setup-credentials.txt` dosyasını kaydettikten sonra silin.

### İnternete açmak güvenli mi?

Önce [SECURITY.md](SECURITY.md) okuyun. Öneriler:

- Güçlü `PANEL_ADMIN_PASSWORD`
- `BRIDGE_SECRET` ve `SESSION_SECRET` değiştirin
- Reverse proxy + HTTPS (Caddy, Nginx)
- Mümkünse VPN veya IP kısıtlaması

### Test modu nedir?

`ALLOW_OUTBOUND_MESSAGES=false` iken panel arayüzü çalışır ama **hiçbir mesaj gönderilmez**. Kurulumu ve arayüzü güvenle denemenizi sağlar.

## Telegram

### Bot API mi, kullanıcı hesabı mı?

**Kullanıcı hesabı** (Telethon). Kendi Telegram hesabınızla giriş yaparsınız — Bot API değil.

### API ID nereden alınır?

[my.telegram.org](https://my.telegram.org) → API development tools

## WhatsApp

### Resmi WhatsApp Business API mi?

Hayır. Baileys köprüsü ile **kendi WhatsApp hesabınızı** QR ile bağlarsınız (WhatsApp Web benzeri).

### Köprü neden ayrı servis?

WhatsApp Node.js (Baileys) kullanır; panel Python (FastAPI). Köprü iki dünyayı birleştirir.

## API

### API anahtarı nasıl oluşturulur?

Panel → Hesap → Geliştirici → API Anahtarı Oluştur  
veya `POST /api/v1/keys` (oturum gerekli)

### Webhook destekleniyor mu?

Evet. `message.received` ve `message.sent` olayları. Bkz. [API.md](API.md)

## Katkı & destek

### Bağış / sponsor

Yakında — `.github/FUNDING.yml` dosyasına sponsor linkinizi ekleyebilirsiniz.

### Nasıl katkıda bulunurum?

[CONTRIBUTING.md](CONTRIBUTING.md)
