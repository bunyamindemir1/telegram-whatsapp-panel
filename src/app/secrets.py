from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import DATA_DIR

KEY_FILE = DATA_DIR / ".encryption_key"


@lru_cache(maxsize=1)
def _load_fernet() -> Fernet:
    env_key = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "").strip()
    if env_key:
        return Fernet(env_key.encode() if isinstance(env_key, str) else env_key)
    if KEY_FILE.exists():
        return Fernet(KEY_FILE.read_bytes())
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    return Fernet(key)


def encrypt_text(plaintext: str) -> str:
    return _load_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    try:
        return _load_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Şifreli veri çözülemedi (anahtar uyumsuz olabilir)") from exc


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * (len(value) - visible * 2)}{value[-visible:]}"
