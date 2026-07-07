# Feature comparison — native apps vs Message Panel

Reference for what this project adds on top of the official Telegram and WhatsApp clients. Personal accounts only; not Business API / bot-only setups.

## Summary

| Capability | WhatsApp | Telegram | Message Panel |
|------------|:--------:|:--------:|:-------------:|
| Send later (one-shot) | No | Limited | Yes |
| Recurring sends | No | No | Yes |
| Random daily window | No | No | Yes |
| Scheduled queue (pending/sent/failed) | No | No | Yes |
| Templates with variables | No | No | Yes |
| Unified Telegram + WhatsApp inbox | No | No | Yes |
| Multiple accounts per platform | Limited | Limited | Yes |
| REST API on personal account | No | No | Yes |
| Webhooks | Business API | Bot API | Yes |
| Auto-reply rules | No | No | Yes |
| Follow-up if no reply | No | No | Yes |
| Chat notes, tags, pin, mute, snooze | No | No | Yes |
| Broadcast + CSV import | No | No | Yes |
| Backup / restore panel data | No | No | Yes |
| Export chat history (JSON/CSV) | No | No | Yes |
| Test mode (dry-run outbound) | No | No | Yes |

## Scheduling

**WhatsApp** has no native “send at 09:00 tomorrow” for personal accounts.

**Telegram** allows one-time schedule in some clients; there is no recurrence, random window, or central queue with retry.

**Message Panel** supports once, hourly, daily, weekly, custom interval, random daily window, edit/duplicate jobs, calendar view, and JSON export of the queue.

## Automation

Consumer apps do not expose personal-account webhooks. Message Panel provides:

- REST API v1 with API keys
- Webhooks: `message.received`, `message.sent`, `scheduled.sent`, `scheduled.failed`, `follow_up.triggered`
- Auto-reply with contains / exact / regex match modes

## Operations

Self-hosted: SQLite, encrypted credential storage, bcrypt panel login, optional outbound guard, backup/restore of templates and schedules, activity log for audit.
