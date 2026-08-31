from __future__ import annotations

from ...core import queries
from ...core.text import plu_apps


def tray_items(store) -> list[dict]:
    from ...core.hotkeys import resolve_accels
    from ...core.store import DEFAULT_LAUNCH_HOTKEY
    state = store.state()
    apps = state["apps"]
    launch = state["settings"].get("launch_hotkey") or DEFAULT_LAUNCH_HOTKEY
    accels, _sets = resolve_accels(apps, state["sets"], launch)
    out = []
    for app in queries.quick_apps(apps)[:6]:
        accel = accels.get(app["id"])
        out.append({"id": app["id"], "name": app["name"],
                    "label": f"{app['name']}   {accel}" if accel else app["name"]})
    return out


def library_summary(store) -> str:
    apps = store.state()["apps"]
    waiting = len(store.state()["inbox"])
    if not apps:
        return "библиотека пуста"
    text = f"{len(apps)} {plu_apps(len(apps))}"
    return f"{text} · {waiting} в разборе" if waiting else text
