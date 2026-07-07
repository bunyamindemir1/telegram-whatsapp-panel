import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SRC_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SRC_DIR.parent
BASE_DIR = SRC_DIR

SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", REPO_ROOT / "sessions"))
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data"))
DB_PATH = DATA_DIR / "telegram_panel.db"
WHATSAPP_BRIDGE_DIR = SRC_DIR / "whatsapp-bridge"

SESSIONS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

ENV = os.getenv("ENV", "development").lower()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_TEST_PHONE = os.getenv("TELEGRAM_TEST_PHONE", "")

DEFAULT_BRIDGE_SECRET = "mesaj-bridge-local-secret"

PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
PANEL_ADMIN_USER = os.getenv("PANEL_ADMIN_USER", "admin")
PANEL_ADMIN_PASSWORD = os.getenv("PANEL_ADMIN_PASSWORD", "")
REQUIRE_PANEL_AUTH = os.getenv("REQUIRE_PANEL_AUTH", "true" if ENV == "production" else "false").lower() in (
    "1",
    "true",
    "yes",
)

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
if not SESSION_SECRET:
    _secret_file = DATA_DIR / ".session_secret"
    if _secret_file.exists():
        SESSION_SECRET = _secret_file.read_text().strip()
    else:
        SESSION_SECRET = secrets.token_urlsafe(32)
        _secret_file.write_text(SESSION_SECRET)
        _secret_file.chmod(0o600)

BRIDGE_SECRET = os.getenv("BRIDGE_SECRET", DEFAULT_BRIDGE_SECRET)
PANEL_URL = os.getenv("PANEL_URL", f"http://127.0.0.1:{PORT}")
WHATSAPP_BRIDGE_URL = os.getenv("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3001")
WHATSAPP_BRIDGE_PORT = int(os.getenv("WHATSAPP_BRIDGE_PORT", "3001"))
MANAGE_WHATSAPP_BRIDGE = os.getenv("MANAGE_WHATSAPP_BRIDGE", "true").lower() in ("1", "true", "yes")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Istanbul")

# Varsayılan: test modu — kimseye mesaj gitmez
ALLOW_OUTBOUND_MESSAGES = os.getenv("ALLOW_OUTBOUND_MESSAGES", "false").lower() in ("1", "true", "yes")

ENABLE_OPENAPI = os.getenv("ENABLE_OPENAPI", "false" if ENV == "production" else "true").lower() in (
    "1",
    "true",
    "yes",
)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
