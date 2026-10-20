"""Раздел версии из CHANGELOG.md — описание релиза на GitHub.

    python scripts/release_notes.py 1.2.0 notes.md [--unsigned]

К разделу дописывается памятка по установке: на странице релиза человек
видит три файла и, пока сборка не подписана, синее окно SmartScreen —
`--unsigned` добавляет, что с ним делать.

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


INSTALL = """\
**Установка.** Скачайте `CenturioSetup.exe` и запустите. Нужны Windows 10 \
или 11 (64-bit); права администратора не нужны — Centurio ставится для \
текущего пользователя. Если на компьютере нет компонентов Microsoft Visual \
C++, установщик поставит их сам, и Windows один раз спросит разрешения.

Новая версия ставится тем же установщиком поверх старой; библиотека и \
настройки сохраняются. Перед этим закройте Centurio: значок в трее → «Выход»."""

UNSIGNED = """\
Сборка пока не подписана, поэтому Windows может показать «Система Windows \
защитила ваш компьютер»: нажмите «Подробнее» → «Выполнить в любом случае». \
Совпадение файла с опубликованным проверяется по `SHA256SUMS.txt`."""


def release_body(notes: str, unsigned: bool) -> str:
    parts = [notes, "---", INSTALL] + ([UNSIGNED] if unsigned else [])
    return "\n\n".join(parts) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    unsigned = "--unsigned" in argv
    argv = [a for a in argv if a != "--unsigned"]
    if len(argv) != 2:
        print("использование: release_notes.py <версия> <файл> [--unsigned]", file=sys.stderr)
        return 2
    version = argv[0].lstrip("v")
    notes = notes_for(version)
    if notes is None:
        print(f"в CHANGELOG.md нет раздела «## {version}»", file=sys.stderr)
        return 1
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(release_body(notes, unsigned), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
