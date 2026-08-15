from __future__ import annotations

import os
import sys
from pathlib import Path

from ..infra import log

APP_NAME = "Centurio"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}" --hidden'
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script:
        return f'"{exe}" "{script}" --hidden'
    return f'"{exe}" --hidden'


def startup_shortcut() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            / "Startup" / f"{APP_NAME}.lnk")


def remove_startup_shortcut() -> bool:
    path = startup_shortcut()
    if path is None:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("ярлык не удалён %s", path)
        return False


def _run_key_set() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        log.exception("не удалось прочитать значение реестра автозапуска")
        return False


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    if _run_key_set():
        return True
    path = startup_shortcut()
    return bool(path and path.exists())


def set_autostart(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    remove_startup_shortcut()
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        log.exception("не удалось установить автозапуск")
        return False


def adopt_installer_choice() -> bool:
    """Разовый подхват галочки инсталлятора — что стоит в системе сейчас.

    `installer/centurio.iss` создаёт `{userstartup}\\Centurio.lnk`, если при
    установке отмечена галочка «Запускать при входе в Windows». Другого
    способа узнать её нет, поэтому первый запуск читает состояние системы и
    записывает его в настройки. Вызывать это можно ровно один раз — за
    однократностью следит `autostart_adopted` (см. `app/main.py`).
    """
    return is_enabled()


def needs_write(preference: bool, enabled: bool) -> bool:
    """Трогать систему нужно только там, где она расходится с настройкой.

    | настройка | автозапуск стоит | пишем |
    |-----------|------------------|-------|
    | True      | True             | нет   |
    | True      | False            | True  |
    | False     | True             | False |
    | False     | False            | нет   |

    Третья строка и есть починенный дефект: раньше вместо неё писалось `True`.
    Первая и четвёртая важны отдельно — `set_autostart` попутно удаляет ярлык
    из «Автозагрузки», и вызов на каждом запуске стирал бы ярлык, который
    пользователь мог положить туда сам.
    """
    return bool(preference) != bool(enabled)


def sync(preference: bool) -> bool:
    """Привести систему в соответствие с настройкой — и только с ней.

    Раньше здесь стояло `preference or is_enabled()`, то есть любой ключ
    `Centurio` в `HKCU\\Run` — оставшийся от прежней установки, от другой
    сборки, от чего угодно — молча включал автозапуск обратно, а `app/main.py`
    следом переписывал этим настройку пользователя. Выключить автозапуск было
    нельзя в принципе.
    """
    if os.name != "nt":
        return bool(preference)
    preference = bool(preference)
    if needs_write(preference, is_enabled()):
        set_autostart(preference)
    return preference
