from __future__ import annotations

import os
import sys
from pathlib import Path

from ..infra import log

APP_NAME = "Centurio"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_parts() -> tuple[str, str]:
    """(что запускать, аргументы) — для ярлыка и для ключа реестра.

    Из исходников это интерпретатор + путь к `main.py`; у собранного
    `Centurio.exe` (`sys.frozen`) — сам exe. Флаг `--hidden` уводит запуск
    сразу в трей, чтобы автозапуск не выкидывал окно при каждом входе.
    """
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return exe, "--hidden"
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script:
        return exe, f'"{script}" --hidden'
    return exe, "--hidden"


def _launch_command() -> str:
    target, args = _launch_parts()
    return f'"{target}" {args}'.strip()


def startup_shortcut() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            / "Startup" / f"{APP_NAME}.lnk")


def _write_shortcut(path: Path, target: str, arguments: str, workdir: str,
                    description: str) -> bool:
    """Создать .lnk через оболочку Windows (IShellLink), без сторонних процессов.

    Ярлык в «Автозагрузке» — тот же путь автозапуска, что использует
    инсталлятор, и эвристики антивирусов относятся к нему заметно спокойнее,
    чем к записи в `HKCU\\Run` (та формально подпадает под MITRE T1547.001 —
    признак персистентности). Создаём его документированным COM-вызовом
    `CoCreateInstance(CLSID_ShellLink)` — так же, как это делает проводник, —
    а не запуском PowerShell с `WScript.Shell`, чтобы не плодить ещё один
    подозрительный для AV скрытый процесс.

    Возвращает True, только если файл действительно появился. Любой сбой COM
    гасится в False — вызывающий откатывается на ключ реестра, чтобы
    автозапуск не сломался молча.
    """
    import ctypes
    import uuid
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, spec: str):
            super().__init__()
            u = uuid.UUID(spec)
            self.Data1, self.Data2, self.Data3 = u.time_low, u.time_mid, u.time_hi_version
            for i, b in enumerate(u.bytes[8:16]):
                self.Data4[i] = b

    CLSID_ShellLink = GUID("00021401-0000-0000-C000-000000000046")
    IID_IShellLinkW = GUID("000214F9-0000-0000-C000-000000000046")
    IID_IPersistFile = GUID("0000010B-0000-0000-C000-000000000046")
    CLSCTX_INPROC_SERVER = 1
    COINIT_APARTMENTTHREADED = 0x2

    ole32 = ctypes.oledll.ole32

    def call(ptr, index, *args, argtypes=()):
        # COM-указатель — это указатель на таблицу указателей на функции;
        # первый аргумент каждого метода — сам интерфейс (this).
        vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)
        return proto(vtable[index])(ptr, *args)

    initialized = False
    try:
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        initialized = hr in (0, 1)  # S_OK или S_FALSE — оба надо уравновесить
    except OSError:
        # RPC_E_CHANGED_MODE — COM уже поднят с другой моделью; работаем как есть.
        pass
    try:
        link = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_ShellLink), None, CLSCTX_INPROC_SERVER,
                               byref(IID_IShellLinkW), byref(link))
        try:
            call(link, 20, target, argtypes=(c_wchar_p,))               # SetPath
            if arguments:
                call(link, 11, arguments, argtypes=(c_wchar_p,))        # SetArguments
            if workdir:
                call(link, 9, workdir, argtypes=(c_wchar_p,))           # SetWorkingDirectory
            if description:
                call(link, 7, description, argtypes=(c_wchar_p,))       # SetDescription
            persist = c_void_p()
            call(link, 0, byref(IID_IPersistFile), byref(persist),      # QueryInterface
                 argtypes=(POINTER(GUID), POINTER(c_void_p)))
            try:
                call(persist, 6, str(path), True,                       # IPersistFile::Save
                     argtypes=(c_wchar_p, wintypes.BOOL))
            finally:
                call(persist, 2)                                        # Release
        finally:
            call(link, 2)                                              # Release
        return path.exists()
    except Exception:
        log.exception("не удалось создать ярлык автозапуска %s", path)
        return False
    finally:
        if initialized:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass


def create_startup_shortcut() -> bool:
    path = startup_shortcut()
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.exception("нет папки «Автозагрузка» %s", path.parent)
        return False
    target, arguments = _launch_parts()
    workdir = os.path.dirname(target) or ""
    return _write_shortcut(path, target, arguments, workdir,
                           "Запуск Centurio при входе в Windows")


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


def _set_run_key() -> bool:
    try:
        import winreg

        # CreateKeyEx, а не OpenKey: на свежем профиле Windows ветки
        # `...\CurrentVersion\Run` может не быть вовсе, и OpenKey падает
        # с FileNotFoundError — переключатель «Запускать с Windows» тихо
        # не срабатывал. Существующую ветку CreateKeyEx просто открывает.
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        return True
    except Exception:
        log.exception("не удалось записать ключ автозапуска в реестр")
        return False


def _delete_run_key() -> None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass          # нет ветки или нет значения — удалять уже нечего
    except Exception:
        log.exception("не удалось удалить ключ автозапуска из реестра")


def set_autostart(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    if not enabled:
        # Гасим оба возможных источника: и ярлык, и ключ реестра, оставшийся
        # от прежних версий, — иначе выключить автозапуск не получится.
        remove_startup_shortcut()
        _delete_run_key()
        return True

    # Предпочитаем ярлык в «Автозагрузке»: тот же путь, что у инсталлятора, и
    # он не выглядит для антивирусов персистентностью, как запись в HKCU\Run.
    # Ключ реестра — запасной путь на случай, если COM почему-то не отработал:
    # автозапуск важнее его AV-профиля, ломаться молча он не должен.
    if create_startup_shortcut():
        _delete_run_key()
        return True
    log.warning("ярлык автозапуска создать не удалось — откатываюсь на HKCU\\Run")
    remove_startup_shortcut()
    return _set_run_key()


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
    Первая и четвёртая важны отдельно — `set_autostart` при включении
    пересоздаёт ярлык, а при выключении сносит и ярлык, и ключ реестра;
    лишний вызов на каждом запуске трогал бы «Автозагрузку» впустую.
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
