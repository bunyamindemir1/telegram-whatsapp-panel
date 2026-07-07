#!/usr/bin/env python3
"""Write manually curated locale files (no translation API)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "locales"


def load_en() -> dict[str, str]:
    return json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))


def write_locale(code: str, data: dict[str, str], en: dict[str, str]) -> None:
    missing = set(en) - set(data)
    extra = set(data) - set(en)
    if missing:
        raise SystemExit(f"{code}: missing keys {sorted(missing)[:5]}... ({len(missing)} total)")
    if extra:
        raise SystemExit(f"{code}: extra keys {sorted(extra)[:5]}...")
    path = LOCALES / f"{code}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    same = sum(1 for k, v in en.items() if data[k] == v)
    print(f"✓ {code}.json — {len(en) - same}/{len(en)} translated ({100 * (len(en) - same) / len(en):.0f}%)")


def main() -> None:
    en = load_en()
    from scripts.locale_data import pt, it, nl, pl, ru, uk, ar, zh, ja, ko

    for code, data in [
        ("pt", pt.DATA),
        ("it", it.DATA),
        ("nl", nl.DATA),
        ("pl", pl.DATA),
        ("ru", ru.DATA),
        ("uk", uk.DATA),
        ("ar", ar.DATA),
        ("zh", zh.DATA),
        ("ja", ja.DATA),
        ("ko", ko.DATA),
    ]:
        write_locale(code, data, en)


if __name__ == "__main__":
    main()
