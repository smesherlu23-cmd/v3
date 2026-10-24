from __future__ import annotations

from ...core import queries
from ...core.text import plu_apps


def tray_items(store) -> list[dict]:
    apps = store.state()["apps"]
    return [{"id": app["id"], "name": app["name"], "label": app["name"]}
            for app in queries.quick_apps(apps)[:6]]


def library_summary(store) -> str:
    apps = store.state()["apps"]
    waiting = len(store.state()["inbox"])
    if not apps:
        return "библиотека пуста"
    text = f"{len(apps)} {plu_apps(len(apps))}"
    return f"{text} · новых: {waiting}" if waiting else text
