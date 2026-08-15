from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

_LOGGER = logging.getLogger("centurio")
_LOGGER.addHandler(logging.NullHandler())
_configured = False
_FORMAT = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")


def is_debug() -> bool:
    return "--debug" in sys.argv or os.environ.get("CENTURIO_DEBUG") == "1"


def _default_dir() -> Path:
    return paths.data_dir()


def _add_console() -> None:
    # RotatingFileHandler — тоже StreamHandler, поэтому сравнение точное.
    if any(type(h) is logging.StreamHandler for h in _LOGGER.handlers):
        return
    sh = logging.StreamHandler()
    sh.setFormatter(_FORMAT)
    _LOGGER.addHandler(sh)


def setup(debug: bool | None = None, log_dir: str | Path | None = None) -> logging.Logger:
    global _configured
    if _configured:
        return _LOGGER
    if debug is None:
        debug = is_debug()

    _LOGGER.setLevel(logging.DEBUG if debug else logging.WARNING)

    try:
        d = Path(log_dir) if log_dir else _default_dir()
        d.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(d / "centurio.log", maxBytes=512 * 1024,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(_FORMAT)
        _LOGGER.addHandler(fh)
    except Exception:
        pass

    if debug:
        _add_console()

    _LOGGER.debug("logging started (log dir: %s)", log_dir or "<default>")

    _configured = True
    return _LOGGER


def set_debug(enabled: bool) -> None:
    """Поднять подробность лога после того, как прочитаны настройки.

    `setup()` вызывается до создания `Store`, иначе сообщения о карантине
    битого файла данных и о несовместимой версии схемы уходят в `NullHandler`.
    Но флаг `debug_log` лежит внутри этого же файла, поэтому уровень
    приходится повышать вторым шагом. Понижать нечего: `--debug` и
    `CENTURIO_DEBUG` уже учтены в `setup()`.
    """
    if not enabled or _LOGGER.level == logging.DEBUG:
        return
    _LOGGER.setLevel(logging.DEBUG)
    _add_console()

def debug(msg, *args, **kw):
    _LOGGER.debug(msg, *args, **kw)


def info(msg, *args, **kw):
    _LOGGER.info(msg, *args, **kw)


def warning(msg, *args, **kw):
    _LOGGER.warning(msg, *args, **kw)


def error(msg, *args, **kw):
    _LOGGER.error(msg, *args, **kw)


def exception(msg, *args, **kw):
    _LOGGER.exception(msg, *args, **kw)
