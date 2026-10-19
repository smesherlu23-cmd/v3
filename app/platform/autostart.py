from __future__ import annotations

import os
import sys
from pathlib import Path

from ..infra import log

APP_NAME = "Centurio"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_HIDDEN_ARG = "--hidden"

# «Окно: свёрнутое» у ярлыка. Им, а не аргументом, собранный exe узнаёт, что
# его запустила «Автозагрузка» и показываться не нужно (см. _embedded).
SW_SHOWMINNOACTIVE = 7
_STARTF_USESHOWWINDOW = 0x1
# SW_HIDE, SW_SHOWMINIMIZED, SW_MINIMIZE, SW_SHOWMINNOACTIVE
_MINIMIZED_SHOW = frozenset((0, 2, 6, 7))


def _embedded() -> bool:
    """Запущены ли мы внутри собранного `flet build` exe.

    Там Python встроен во Flutter-оболочку, и любой аргумент командной строки
    она принимает за адрес сервера «режима разработчика»: Python не
    запускается вовсе, а окно ждёт подключения к «--hidden» (шаблон сборки
    Flet, main.dart: `isDesktopPlatform() && _args.isNotEmpty`). Поэтому
    собранному exe аргументы передавать нельзя. Признак — FLET_PLATFORM:
    его выставляет эта же оболочка.
    """
    return bool(os.environ.get("FLET_PLATFORM"))


def _launch_parts() -> tuple[str, str]:
    exe = sys.executable
    if _embedded():
        return exe, ""
    if getattr(sys, "frozen", False):
        return exe, _HIDDEN_ARG
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script:
        return exe, f'"{script}" {_HIDDEN_ARG}'
    return exe, _HIDDEN_ARG


def started_minimized() -> bool:
    """Попросил ли запустивший нас ярлык свёрнутое окно.

    Так «Автозагрузка» передаёт собранному exe «запуск в трей» вместо
    `--hidden`: у ярлыка стоит «Окно: свёрнутое», и Windows кладёт это в
    STARTUPINFO процесса. Обычный запуск из меню «Пуск» или двойным щелчком
    приходит с SW_SHOWNORMAL и сюда не попадает.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                        ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

        # Свой экземпляр kernel32: argtypes, выставленные на общем
        # ctypes.windll, поменяли бы их всем остальным модулям.
        get_startup_info = ctypes.WinDLL("kernel32").GetStartupInfoW
        get_startup_info.argtypes = [ctypes.POINTER(STARTUPINFOW)]
        get_startup_info.restype = None
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        get_startup_info(ctypes.byref(si))
        return bool(si.dwFlags & _STARTF_USESHOWWINDOW) and si.wShowWindow in _MINIMIZED_SHOW
    except Exception:
        log.exception("не удалось прочитать STARTUPINFO")
        return False


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
                    description: str, show_cmd: int = 0) -> bool:
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
        vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)
        return proto(vtable[index])(ptr, *args)

    initialized = False
    try:
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        initialized = hr in (0, 1)
    except OSError:
        pass
    try:
        link = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_ShellLink), None, CLSCTX_INPROC_SERVER,
                               byref(IID_IShellLinkW), byref(link))
        try:
            call(link, 20, target, argtypes=(c_wchar_p,))
            if arguments:
                call(link, 11, arguments, argtypes=(c_wchar_p,))
            if workdir:
                call(link, 9, workdir, argtypes=(c_wchar_p,))
            if description:
                call(link, 7, description, argtypes=(c_wchar_p,))
            if show_cmd:
                call(link, 15, show_cmd, argtypes=(ctypes.c_int,))
            persist = c_void_p()
            call(link, 0, byref(IID_IPersistFile), byref(persist),
                 argtypes=(POINTER(GUID), POINTER(c_void_p)))
            try:
                call(persist, 6, str(path), True,
                     argtypes=(c_wchar_p, wintypes.BOOL))
            finally:
                call(persist, 2)
        finally:
            call(link, 2)
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
                           "Запуск Centurio при входе в Windows",
                           show_cmd=SW_SHOWMINNOACTIVE)


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


def _run_key_value() -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _kind = winreg.QueryValueEx(key, APP_NAME)
        return str(value)
    except FileNotFoundError:
        return None
    except Exception:
        log.exception("не удалось прочитать значение реестра автозапуска")
        return None


def _run_key_set() -> bool:
    return _run_key_value() is not None


def has_stale_arguments() -> bool:
    """Автозапуск от прошлой версии передаёт собранному exe `--hidden`.

    Такой ярлык (его ставил и инсталлятор) запускает Flutter-оболочку без
    Python — см. `_embedded`. Аргументы ярлык хранит строкой UTF-16LE, так что
    для проверки его не нужно разбирать целиком.
    """
    if not _embedded():
        return False
    path = startup_shortcut()
    try:
        if path and path.exists() and _HIDDEN_ARG.encode("utf-16-le") in path.read_bytes():
            return True
    except OSError:
        pass
    value = _run_key_value() if os.name == "nt" else None
    return bool(value and _HIDDEN_ARG in value)


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
        pass
    except Exception:
        log.exception("не удалось удалить ключ автозапуска из реестра")


def set_autostart(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    if not enabled:
        remove_startup_shortcut()
        _delete_run_key()
        return True

    if create_startup_shortcut():
        _delete_run_key()
        return True
    log.warning("ярлык автозапуска создать не удалось — откатываюсь на HKCU\\Run")
    remove_startup_shortcut()
    return _set_run_key()


def adopt_installer_choice() -> bool:
    return is_enabled()


def needs_write(preference: bool, enabled: bool) -> bool:
    return bool(preference) != bool(enabled)


def sync(preference: bool) -> bool:
    if os.name != "nt":
        return bool(preference)
    preference = bool(preference)
    if needs_write(preference, is_enabled()) or (preference and has_stale_arguments()):
        set_autostart(preference)
    return preference
