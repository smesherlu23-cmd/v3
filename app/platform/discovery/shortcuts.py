from __future__ import annotations

import ntpath
import os
import re

from ...infra import log, procs

_SHORTCUT_EXT = (".lnk", ".url")

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", (name or "").lower())

def _shortcut_names(directory: str) -> set[str]:
    out: set[str] = set()
    try:
        entries = os.listdir(directory)
    except OSError:
        return out
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        if ext.lower() in _SHORTCUT_EXT:
            norm = _norm(stem)
            if norm:
                out.add(norm)
    return out

def desktop_names() -> set[str]:
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    names: set[str] = set()
    for folder in ("Desktop", "Рабочий стол"):
        names |= _shortcut_names(os.path.join(home, folder))
    public = os.environ.get("PUBLIC")
    if public:
        names |= _shortcut_names(os.path.join(public, "Desktop"))
    return names

def autostart_names() -> set[str]:
    names: set[str] = set()
    appdata = os.environ.get("APPDATA")
    if appdata:
        names |= _shortcut_names(os.path.join(
            appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"))
    if os.name != "nt":
        return names
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                value_name = winreg.EnumValue(key, i)[0]
                norm = _norm(value_name)
                if norm:
                    names.add(norm)
    except OSError:
        pass
    except Exception:
        log.exception("не удалось прочитать ключ запуска для получения предложений по первому запуску")
    return names

def taskbar_names() -> set[str]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return set()
    return _shortcut_names(os.path.join(appdata, "Microsoft", "Internet Explorer",
                                        "Quick Launch", "User Pinned", "TaskBar"))

def _exe_name(item: dict) -> str:
    exe = item.get("track_exe") or ntpath.basename(item.get("path") or "")
    exe = exe.lower()
    return exe if exe.endswith(".exe") else ""

def suggest_first_run(found: list[dict], limit: int = 12,
                      running: set[str] | None = None) -> list[dict]:
    """Что из найденного человек, судя по всему, уже использует.

    Только с уликами: значок на панели задач, работающий процесс, автозагрузка,
    ярлык на рабочем столе. Пункт меню «Пуск» уликой не считается — он есть
    почти у всего установленного.
    """
    try:
        pinned, startup, desktop = taskbar_names(), autostart_names(), desktop_names()
    except Exception:
        log.exception("не удалось собрать подсказки при первом запуске")
        pinned, startup, desktop = set(), set(), set()
    if running is None:
        running = set(procs.snapshot().values())

    tiers: list[list[dict]] = [[], [], [], []]
    seen: set[str] = set()
    for item in found:
        norm = _norm(item.get("name"))
        if not norm or norm in seen:
            continue
        if norm in pinned:
            tier, hint = 0, "на панели задач"
        elif _exe_name(item) in running:
            tier, hint = 1, "сейчас запущена"
        elif norm in startup:
            tier, hint = 2, "в автозагрузке"
        elif norm in desktop:
            tier, hint = 3, "на рабочем столе"
        else:
            continue
        seen.add(norm)
        tiers[tier].append({"app": item, "hint": hint})
    return [s for tier in tiers for s in tier][:limit]
