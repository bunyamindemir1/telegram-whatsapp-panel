"""Playwright fixtures for E2E tests against the FastAPI app."""

import threading
import time

import pytest
import uvicorn

from app.main import app


@pytest.fixture(scope="session")
def live_server():
    host, port = "127.0.0.1", 8765
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://{host}:{port}"
    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.skip("Could not start test server")

    yield url
    server.should_exit = True
