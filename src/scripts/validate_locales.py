#!/usr/bin/env python3
"""Validate all locale files have identical keys to en.json."""

import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent
LOCALES = SRC_ROOT / "locales"


def main() -> int:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = set(en.keys())
    errors = 0
    for path in sorted(LOCALES.glob("*.json")):
        if path.name == "en.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = keys - set(data.keys())
        extra = set(data.keys()) - keys
        if missing:
            print(f"FAIL {path.name}: missing {len(missing)} keys")
            errors += 1
        if extra:
            print(f"WARN {path.name}: {len(extra)} extra keys")
        else:
            print(f"OK   {path.name} ({len(data)} keys)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
