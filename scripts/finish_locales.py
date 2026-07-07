# -*- coding: utf-8 -*-
"""Write remaining manual locale files (no translation API)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "locales"


def save(code: str, data: dict[str, str]) -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    if set(data) != set(en):
        raise SystemExit(f"{code}: key mismatch")
    (LOCALES / f"{code}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    same = sum(1 for k, v in en.items() if data[k] == v)
    print(f"{code}: {len(en) - same}/{len(en)} translated")


def load_module(name: str) -> dict[str, str]:
    import importlib.util

    path = Path(__file__).parent / "locale_data" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DATA


def main() -> None:
    for code in ("nl", "pl", "ru", "uk", "ar", "zh", "ja", "ko"):
        save(code, load_module(code))


if __name__ == "__main__":
    main()
