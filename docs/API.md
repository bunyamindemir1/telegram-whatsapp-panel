# API v1

Tam OpenAPI şeması: panel çalışırken **http://localhost:8000/docs**

## Kimlik doğrulama

Tüm `/api/v1/*` uçları Bearer token gerektirir:

```http
Authorization: Bearer mp_xxxxxxxx
```

Anahtar oluşturma (panel oturumu veya mevcut anahtar ile):

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer mp_..." \
  -H "Content-Type: application/json" \
  -d '{"name":"otomasyon"}'
```

## Mesaj gönderme

```bash
curl -X POST http://localhost:8000/api/v1/messages/send \
  -H "Authorization: Bearer mp_..." \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "whatsapp",
    "account_id": 1,
    "chat_id": "905551234567@s.whatsapp.net",
    "message": "Merhaba"
  }'
```

## Medya gönderme

```bash
curl -X POST "http://localhost:8000/api/v1/messages/send-media?platform=telegram&account_id=1&chat_id=123&caption=Not" \
  -H "Authorization: Bearer mp_..." \
  -F "file=@photo.jpg"
```

## Webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Authorization: Bearer mp_..." \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/hook",
    "events": ["message.received"],
    "secret": "opsiyonel-imza-anahtari"
  }'
```

Olaylar HTTP POST ile gönderilir. Gövde örneği:

```json
{
  "event": "message.received",
  "platform": "telegram",
  "account_id": 1,
  "message": { "..." }
}
```

## Uç noktalar özeti

| Metot | Yol | Açıklama |
|-------|-----|----------|
| GET | `/api/v1/accounts` | Bağlı hesaplar |
| GET | `/api/v1/conversations` | Sohbet listesi |
| GET | `/api/v1/messages` | Mesaj geçmişi |
| POST | `/api/v1/messages/send` | Metin gönder |
| POST | `/api/v1/messages/send-media` | Medya gönder |
| GET | `/api/v1/media/{path}` | Medya dosyası |
| GET/POST | `/api/v1/scheduled` | Zamanlanmış mesajlar |
| GET/POST/DELETE | `/api/v1/webhooks` | Webhook yönetimi |
| POST | `/api/v1/keys` | API anahtarı oluştur |

## Hata kodları

| Kod | Anlam |
|-----|-------|
| 401 | Geçersiz veya eksik API anahtarı |
| 403 | Test modu — giden mesaj engelli |
| 404 | Hesap veya sohbet bulunamadı |
| 429 | Rate limit |

Güvenlik: [SECURITY.md](../SECURITY.md)
