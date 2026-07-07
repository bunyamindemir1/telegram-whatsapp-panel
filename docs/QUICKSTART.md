# Hızlı Başlangıç — 60 saniye

Bu rehber, Mesaj Paneli'ni **Docker** ile en hızlı şekilde ayağa kaldırmanız içindir.

## Gereksinimler

| Gereksinim | Minimum |
|------------|---------|
| Docker | 24+ |
| Docker Compose | v2 |
| RAM | 1 GB |
| Disk | 500 MB |

## Tek komut kurulum

```bash
git clone https://github.com/bunyamindemir1/telegram-whatsapp-panel.git
cd telegram-whatsapp-panel
chmod +x setup.sh && ./setup.sh
```

`setup.sh` otomatik olarak:

1. Güvenli `.env` oluşturur (rastgele şifreler)
2. Panel + WhatsApp köprüsünü Docker'da başlatır
3. Sağlık kontrolünü bekler
4. Giriş bilgilerini ekrana yazar

> **İlk build** 2–3 dakika sürebilir. Sonraki başlatmalar: `./setup.sh --fast` (~10 sn).

## Yerel geliştirme (Docker yok, ~30 sn)

Python 3.9+ ve Node.js 18+ yeterli:

```bash
./install.sh && ./start.sh    # veya: make quick
./scripts/smoke_local.sh      # sağlık + i18n + test doğrulaması
./stop.sh                     # durdur
```

Panel WhatsApp köprüsünü otomatik başlatır — ikinci terminal gerekmez.

## Panele giriş

1. Tarayıcıda açın: **http://127.0.0.1:8000**
2. Kullanıcı: `admin`
3. Şifre: kurulum çıktısındaki veya `.setup-credentials.txt` dosyasındaki değer

## Hesap bağlama

### Telegram

1. [my.telegram.org](https://my.telegram.org) → API ID ve Hash alın
2. Panel → **Hesap** sekmesi → Telegram API bilgilerini girin
3. Telefon doğrulama kodunu girin

### WhatsApp

1. Panel → **Hesap** → **WhatsApp Bağla**
2. Telefonda WhatsApp → Ayarlar → Bağlı Cihazlar → QR okutun

## Test modu

Varsayılan olarak **giden mesajlar kapalıdır** (`ALLOW_OUTBOUND_MESSAGES=false`).

Canlı gönderim için `.env` dosyasında:

```env
ALLOW_OUTBOUND_MESSAGES=true
```

Sonra: `docker compose restart`

## Yararlı komutlar

```bash
docker compose logs -f panel      # Panel logları
docker compose ps                 # Durum
docker compose down               # Durdur
docker compose up -d              # Tekrar başlat
make test                         # Testleri çalıştır
```

## Sonraki adımlar

- [API kullanımı](API.md)
- [Docker / sunucu](SELF_HOSTING.md)
- [SSS](FAQ.md)
