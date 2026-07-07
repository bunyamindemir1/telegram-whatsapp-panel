"""Stable i18n keys returned as API error details (client translates via locales)."""

# Auth & panel
AUTH_INVALID = "error.auth.invalidCredentials"
AUTH_USERNAME_REQUIRED = "error.auth.usernameRequired"
AUTH_ACCOUNT_DISABLED = "error.auth.accountDisabled"
AUTH_SETUP_REQUIRED = "error.auth.setupRequired"
AUTH_LOGIN_REQUIRED = "error.auth.loginRequired"
AUTH_RATE_LIMIT = "error.auth.rateLimit"

# Accounts & platform
INVALID_PLATFORM = "error.invalidPlatform"
UNSUPPORTED_PLATFORM = "error.unsupportedPlatform"
ACCOUNT_NOT_FOUND = "error.account.notFound"
SETUP_ALREADY_DONE = "error.setup.alreadyDone"
PANEL_SETUP_REQUIRED = "error.panel.setupRequired"

# Bridge & sync
BRIDGE_INVALID_SECRET = "error.bridge.invalidSecret"
SYNC_WHATSAPP_ONLY = "error.sync.whatsappOnly"

# Outbound / test mode
OUTBOUND_TEST_MODE = "error.outbound.testMode"
OUTBOUND_BLOCKED = "error.outbound.blocked"
OUTBOUND_DRY_RUN = "error.outbound.dryRun"
TEST_PHONE_NOT_SET = "error.test.phoneNotSet"

# Scheduling & messages
SCHEDULE_TIME_REQUIRED = "error.schedule.timeRequired"
SCHEDULE_FUTURE_REQUIRED = "error.schedule.futureRequired"
SCHEDULE_RANDOM_WINDOW = "error.schedule.randomWindowRequired"
SCHEDULE_CUSTOM_INTERVAL = "error.schedule.customIntervalRequired"
MESSAGE_NOT_FOUND = "error.message.notFound"
MESSAGE_NOT_EDITABLE = "error.message.notEditable"
AUTO_REPLY_NOT_FOUND = "error.autoReply.notFound"
FOLLOW_UP_NOT_FOUND = "error.followUp.notFound"
LABEL_REQUIRED = "error.conversation.labelRequired"

# Media & API v1
MEDIA_TOO_LARGE = "error.media.tooLarge"
MEDIA_UNSUPPORTED = "error.media.unsupportedType"
MEDIA_INVALID_PATH = "error.media.invalidPath"
MEDIA_NOT_FOUND = "error.media.notFound"
API_KEY_NOT_FOUND = "error.apiKey.notFound"
WEBHOOK_NOT_FOUND = "error.webhook.notFound"
API_KEY_INVALID = "error.apiKey.invalid"
LOCALE_NOT_SUPPORTED = "error.locale.notSupported"
CSV_HEADER_REQUIRED = "error.csv.headerRequired"
BRIDGE_EVENT_DATA_REQUIRED = "error.bridge.eventDataRequired"
NOT_FOUND = "error.notFound"
