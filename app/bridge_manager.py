import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.config import (
    BRIDGE_SECRET,
    MANAGE_WHATSAPP_BRIDGE,
    PANEL_URL,
    WHATSAPP_BRIDGE_DIR,
    WHATSAPP_BRIDGE_PORT,
)

_bridge_process: Optional[subprocess.Popen] = None


def _node_modules_ready() -> bool:
    return (WHATSAPP_BRIDGE_DIR / "node_modules").exists()


async def start_whatsapp_bridge() -> bool:
    global _bridge_process

    if not MANAGE_WHATSAPP_BRIDGE:
        from app.whatsapp_service import whatsapp_service
        return await whatsapp_service.health()

    if not shutil.which("node"):
        return False

    if not _node_modules_ready():
        npm = shutil.which("npm")
        if not npm:
            return False
        proc = await asyncio.create_subprocess_exec(
            npm, "install",
            cwd=str(WHATSAPP_BRIDGE_DIR),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    if _bridge_process and _bridge_process.poll() is None:
        return True

    env = {
        **os.environ,
        "WHATSAPP_BRIDGE_PORT": str(WHATSAPP_BRIDGE_PORT),
        "PANEL_URL": PANEL_URL,
        "BRIDGE_SECRET": BRIDGE_SECRET,
        "ALLOW_OUTBOUND_MESSAGES": os.getenv("ALLOW_OUTBOUND_MESSAGES", "false"),
    }
    _bridge_process = subprocess.Popen(
        ["node", "server.js"],
        cwd=str(WHATSAPP_BRIDGE_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(20):
        await asyncio.sleep(0.5)
        if _bridge_process.poll() is not None:
            return False
        from app.whatsapp_service import whatsapp_service
        if await whatsapp_service.health():
            return True

    return False


def stop_whatsapp_bridge() -> None:
    global _bridge_process
    if _bridge_process and _bridge_process.poll() is None:
        _bridge_process.terminate()
        try:
            _bridge_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bridge_process.kill()
    _bridge_process = None
