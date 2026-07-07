#!/usr/bin/env python3
import os

import uvicorn

from app.config import ENV, HOST, PORT

if __name__ == "__main__":
    reload = ENV != "production" and os.getenv("NO_RELOAD", "").lower() not in ("1", "true", "yes")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=reload)
