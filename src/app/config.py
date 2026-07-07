import os
import secrets
from pathlib import Path
from typing import Optional

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

# Documented weak default — listed in secret_policy only; never used at runtime.
DEFAULT_BRIDGE_SECRET = "mesaj-bridge-local-secret"


def load_persistent_secret(env_name: str, filename: str, *, data_dir: Optional[Path] = None) -> str:
    """Load secret from env, persisted file, or generate a strong random value."""
    data_dir = data_dir or DATA_DIR
    env_val = os.getenv(env_name, "").strip()
    if env_val:
        return env_val
    secret_file = data_dir / filename
    if secret_file.exists():
        return secret_file.read_text().strip()
    generated = secrets.token_urlsafe(32)
    secret_file.write_text(generated)
    secret_file.chmod(0o600)
    return generated


PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
PANEL_ADMIN_USER = os.getenv("PANEL_ADMIN_USER", "admin")
PANEL_ADMIN_PASSWORD = os.getenv("PANEL_ADMIN_PASSWORD", "")
REQUIRE_PANEL_AUTH = os.getenv("REQUIRE_PANEL_AUTH", "true" if ENV == "production" else "false").lower() in (
    "1",
    "true",
    "yes",
)

SESSION_SECRET = load_persistent_secret("SESSION_SECRET", ".session_secret")
BRIDGE_SECRET = load_persistent_secret("BRIDGE_SECRET", ".bridge_secret")
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
