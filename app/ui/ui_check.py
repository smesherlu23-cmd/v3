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
        "add_query": view.add_query,
        "add_path": view.manual_path,
        "typing": view.typing,
        "inspector": view.inspector,
        "menu": ui.menu.open,
        "launched": list(launched),
        "toast": toast.text.value if toast.control.visible else "",
        "apps": [a["name"] for a in ui.apps()],
    }


def _trace(ui) -> None:
    """Что поле поиска получает из окна и что в нём после запуска — в лог.

    Набранное приходит из Flutter, очистка — из Python; если на раннере
    они расходятся, порядок событий в логе показывает, кто кого перебил.
    """
    field, page = ui.search_field, ui.page

    def wrap(name, describe):
        inner = getattr(field, name)

        def traced(e):
            log.info("ui-check: поле %s %s", name, describe(e))
            if inner:
                return inner(e)
        setattr(field, name, traced)
    wrap("on_change", lambda e: repr(e.control.value))
    wrap("on_focus", lambda e: "")
    wrap("on_blur", lambda e: "")

    keys = page.on_keyboard_event

    def traced_key(e):
        log.info("ui-check: клавиша %s%s", "Ctrl+" if e.ctrl else "", e.key)
        if keys:
            return keys(e)
    page.on_keyboard_event = traced_key

    after = ui.after_launch

    def traced_after(from_palette=False):
        after(from_palette)
        log.info("ui-check: после запуска поле = %r", field.value)
    ui.after_launch = traced_after


def start(ui, launcher, path: str, stop: threading.Event) -> None:
    launched: list[str] = []
    _trace(ui)

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
