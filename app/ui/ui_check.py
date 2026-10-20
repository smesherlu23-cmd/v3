"""Снимок состояния окна для проверки интерфейса под виртуальным экраном.

Включается переменной `CENTURIO_UI_CHECK=<файл>`; её ставит только
`scripts/ui_check.py`. Сценарий нажимает настоящие клавиши в настоящем окне
Flet, а сюда смотрит, дошло ли нажатое до программы: так ловятся ошибки,
которых не видно в тестах без окна, — например, поле поиска, которое после
щелчка теряло фокус. Запуск программ при этом только записывается.
"""
from __future__ import annotations

import json
import os
import threading

from ..infra import log

INTERVAL = 0.1


def snapshot(ui, launched: list[str]) -> dict:
    view = ui.view
    rows = ui._palette_rows() if view.palette_open else []
    toast = ui.toast
    return {
        "screen": view.screen,
        # Пока окно считается скрытым, перерисовки копятся и в окно не уходят.
        "visible": ui._visible,
        "query": ui.search_field.value or "",
        "palette_open": view.palette_open,
        "palette": [r["app"]["name"] if r["kind"] == "app" else r["set"]["name"]
                    for r in rows],
        # По этому запросу посчитан список: значение поля Flet обновляет
        # раньше, чем обработчик успевает пересчитать выдачу.
        "palette_query": view.query,
        "palette_index": view.palette_index,
        "palette_focus": view.palette_focus,
        "accent": ui.setting("accent"),
        "typing": view.typing,
        "inspector": view.inspector,
        "launched": list(launched),
        "toast": toast.text.value if toast.control.visible else "",
        "apps": [a["name"] for a in ui.apps()],
    }


def start(ui, launcher, path: str, stop: threading.Event) -> None:
    launched: list[str] = []

    def record_launch(app):
        launched.append(app["name"])
        return {"ok": True, "running": False}
    launcher.launch = record_launch

    def loop():
        tmp = f"{path}.tmp"
        while not stop.wait(INTERVAL):
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(snapshot(ui, launched), fh, ensure_ascii=False)
                os.replace(tmp, path)
            except Exception:
                log.exception("не удалось записать снимок для проверки интерфейса")
    threading.Thread(target=loop, daemon=True).start()
