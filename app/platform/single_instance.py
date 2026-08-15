from __future__ import annotations

import sys
import threading

from ..infra import log

_ERROR_ALREADY_EXISTS = 183
# `Local\`, а не `Global\`. Глобальное пространство имён общее на всю машину:
# на терминальном сервере или при быстром переключении пользователей второй
# пользователь не смог бы запустить программу. Вдобавок создание объекта в
# `Global\` требует SeCreateGlobalPrivilege, которой у обычного пользователя
# может не быть, — тогда CreateMutexW возвращает 0, `acquire` отвечает True и
# защита от второго экземпляра просто отключается. `Local\` — это сеанс входа,
# ровно та область, в которой «второй экземпляр» и имеет смысл.
MUTEX_NAME = "Local\\CenturioSingleInstanceMutex"

_handle = None
_lock = threading.Lock()


def acquire() -> bool:
    global _handle
    if not sys.platform.startswith("win"):
        return True
    with _lock:
        if _handle is not None:
            return True
        try:
            import ctypes
            handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
            if not handle:
                return True
            already = ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
            if already:
                ctypes.windll.kernel32.CloseHandle(handle)
                return False
            _handle = handle
            return True
        except Exception:
            log.exception("не удалось проверить единственный экземпляр")
            return True


def release() -> None:
    global _handle
    with _lock:
        if _handle is None:
            return
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_handle)
        except Exception:
            log.exception("не удалось освободить мьютекс единственного экземпляра")
        _handle = None
