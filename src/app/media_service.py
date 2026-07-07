from __future__ import annotations

import mimetypes
import secrets
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app import error_codes as E
from app.config import MEDIA_DIR

MAX_MEDIA_BYTES = 50 * 1024 * 1024
ALLOWED_MIME_PREFIXES = ("image/", "video/", "audio/", "application/")


def _account_media_dir(platform: str, account_id: int) -> Path:
    path = MEDIA_DIR / platform / str(account_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_message_type(mime: str, filename: str = "") -> str:
    mime = (mime or "").lower()
    name = (filename or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        if "ogg" in mime or name.endswith(".ogg") or "opus" in mime:
            return "voice"
        return "audio"
    if mime.startswith("application/") or name.endswith((".pdf", ".doc", ".docx", ".zip")):
        return "document"
    return "document"


async def save_upload(
    upload: UploadFile,
    platform: str,
    account_id: int,
) -> dict:
    content = await upload.read()
    if len(content) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail=E.MEDIA_TOO_LARGE)
    mime = upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or "application/octet-stream"
    if not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail={"code": E.MEDIA_UNSUPPORTED, "mime": mime})

    ext = Path(upload.filename or "").suffix
    if not ext:
        ext = mimetypes.guess_extension(mime) or ""
    token = secrets.token_hex(8)
    rel_name = f"{uuid.uuid4().hex}_{token}{ext}"
    dest_dir = _account_media_dir(platform, account_id)
    dest = dest_dir / rel_name
    dest.write_bytes(content)

    rel_path = str(dest.relative_to(MEDIA_DIR))
    msg_type = detect_message_type(mime, upload.filename or "")
    return {
        "media_path": rel_path,
        "media_mime": mime,
        "media_filename": upload.filename or rel_name,
        "media_size": len(content),
        "message_type": msg_type,
        "absolute_path": str(dest),
    }


def resolve_media_path(media_path: str) -> Path:
    candidate = (MEDIA_DIR / media_path).resolve()
    if not str(candidate).startswith(str(MEDIA_DIR.resolve())):
        raise HTTPException(status_code=400, detail=E.MEDIA_INVALID_PATH)
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=E.MEDIA_NOT_FOUND)
    return candidate


def save_bytes(
    data: bytes,
    platform: str,
    account_id: int,
    mime: str,
    filename_hint: str = "",
) -> dict:
    ext = Path(filename_hint).suffix if filename_hint else ""
    if not ext:
        ext = mimetypes.guess_extension(mime) or ""
    token = secrets.token_hex(6)
    rel_name = f"{uuid.uuid4().hex}_{token}{ext}"
    dest_dir = MEDIA_DIR / platform / str(account_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / rel_name
    dest.write_bytes(data)
    rel_path = str(dest.relative_to(MEDIA_DIR))
    msg_type = detect_message_type(mime, filename_hint or rel_name)
    return {
        "media_path": rel_path,
        "media_mime": mime,
        "media_filename": filename_hint or rel_name,
        "media_size": len(data),
        "message_type": msg_type,
        "absolute_path": str(dest),
    }


def telegram_message_type(msg) -> str:
    if getattr(msg, "photo", None):
        return "image"
    if getattr(msg, "video", None):
        return "video"
    if getattr(msg, "voice", None):
        return "voice"
    if getattr(msg, "audio", None):
        return "audio"
    if getattr(msg, "sticker", None):
        return "sticker"
    if getattr(msg, "document", None):
        return "document"
    return "text"
