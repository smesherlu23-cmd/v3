from __future__ import annotations

import sys
import threading

from ..infra import log

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_ASFW_ANY = -1
# `Local\`, а не `Global\`. Глобальное пространство имён общее на всю машину:
# на терминальном сервере или при быстром переключении пользователей второй
# пользователь не смог бы запустить программу. Вдобавок создание объекта в
# `Global\` требует SeCreateGlobalPrivilege, которой у обычного пользователя
# может не быть, — тогда CreateMutexW возвращает 0, `acquire` отвечает True и
# защита от второго экземпляра просто отключается. `Local\` — это сеанс входа,
# ровно та область, в которой «второй экземпляр» и имеет смысл.
MUTEX_NAME = "Local\\CenturioSingleInstanceMutex"
# Второй запуск будит первый этим событием, и тот показывает своё окно.
SHOW_EVENT_NAME = "Local\\CenturioShowWindowEvent"

_handle = None
_show_event = None
_listening = threading.Event()
_lock = threading.Lock()


_k32 = None


def _kernel32():
    """Свой экземпляр kernel32 с объявленными типами.

    Типы, выставленные на общем `ctypes.windll.kernel32`, поменялись бы для
    всех остальных модулей.
    """
    global _k32
    if _k32 is not None:
        return _k32
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32")
    k.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
    k.CreateEventW.restype = wintypes.HANDLE
    k.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    k.OpenEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = (wintypes.HANDLE,)
    k.SetEvent.restype = wintypes.BOOL
    k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    k.CloseHandle.restype = wintypes.BOOL
    k.GetLastError.restype = wintypes.DWORD
    _k32 = k
    return k


def acquire() -> bool:
    global _handle
    if not sys.platform.startswith("win"):
        return True
    with _lock:
        if _handle is not None:
            return True
        try:
            kernel32 = _kernel32()
            handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            if not handle:
                return True
            already = kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
            if already:
                kernel32.CloseHandle(handle)
                return False
            _handle = handle
            return True
        except Exception:
            log.exception("не удалось проверить единственный экземпляр")
            return True


def signal_existing() -> bool:
    """Попросить уже запущенный Centurio показать окно. True — просьба доставлена."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        kernel32 = _kernel32()
        event = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if not event:
            return False
        try:
            # Окно на передний план выводит первый экземпляр, а право на это
            # сейчас есть только у нас — нас запустил пользователь.
            ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)
            return bool(kernel32.SetEvent(event))
        finally:
            kernel32.CloseHandle(event)
    except Exception:
        log.exception("не удалось разбудить запущенный экземпляр")
        return False


def listen(on_show) -> bool:
    """Показывать окно, когда пользователь запускает Centurio второй раз."""
    global _show_event
    if not sys.platform.startswith("win"):
        return False
    with _lock:
        if _listening.is_set():
            return True
        kernel32 = _kernel32()
        if _show_event is None:
            _show_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)
        if not _show_event:
            _show_event = None
            return False
        event = _show_event
        _listening.set()

    def loop():
        while _listening.is_set():
            if kernel32.WaitForSingleObject(event, 500) != _WAIT_OBJECT_0:
                continue
            if not _listening.is_set():
                break
            try:
                on_show()
            except Exception:
                log.exception("не удалось показать окно по просьбе второго экземпляра")

    threading.Thread(target=loop, daemon=True).start()
    return True


def release() -> None:
    global _handle
    # Событие не закрываем: слушающий поток может ждать на нём, а закрыть
    # дескриптор посреди ожидания нельзя. Процесс всё равно завершается.
    _listening.clear()
    with _lock:
        handle, _handle = _handle, None
    if handle is None:
        return
    try:
        _kernel32().CloseHandle(handle)
    except Exception:
        log.exception("не удалось освободить мьютекс единственного экземпляра")
