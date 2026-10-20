"""Раздел версии из CHANGELOG.md — описание релиза на GitHub.

    python scripts/release_notes.py 1.2.0 notes.md

Файл пишется самим скриптом: через конвейер PowerShell на раннере кириллица
перекодировалась бы по кодовой странице консоли. Если раздела нет, скрипт
выходит с ошибкой — релиз без описания не публикуется.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def notes_for(version: str, text: str | None = None) -> str | None:
    text = CHANGELOG.read_text(encoding="utf-8") if text is None else text
    m = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    body = m.group(1).strip()
    return body or None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("использование: release_notes.py <версия> <файл>", file=sys.stderr)
        return 2
    version = argv[0].lstrip("v")
    notes = notes_for(version)
    if notes is None:
        print(f"в CHANGELOG.md нет раздела «## {version}»", file=sys.stderr)
        return 1
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(notes + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
