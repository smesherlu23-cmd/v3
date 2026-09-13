from __future__ import annotations

import os
import sys

# Ранний журнал падений. Пишется только стандартной библиотекой и до любого
# импорта проекта — потому что падать умеет и сам импорт.
#
# Обычный лог (`app/infra/log.py`) поднимается внутри `main(page)`, то есть уже
# после `import flet`, после разбора всего пакета `app` и после старта Flet.
# Если процесс умирает раньше — а у собранного Centurio.exe нет консоли, —
# наружу не попадает ни строчки, и «вылетает, логов нет» невозможно даже
# назвать. Здесь пишется файл, который переживает такие сбои:
#
#   %APPDATA%\Centurio\centurio-crash.log
#
# Сюда же направлен `faulthandler`: он ловит жёсткие падения (нарушение
# доступа в нативной библиотеке), которые обычным `except` не перехватить.

_CRASH_NAME = "centurio-crash.log"
_MAX_CRASH_BYTES = 256 * 1024


def _crash_log_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "Centurio")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = os.path.expanduser("~")
    return os.path.join(folder, _CRASH_NAME)


def _record(text: str) -> None:
    """Дописать строку в журнал падений. Не бросает — это последний рубеж."""
    try:
        path = _crash_log_path()
        try:
            if os.path.getsize(path) > _MAX_CRASH_BYTES:
                os.replace(path, path + ".old")
        except OSError:
            pass
        import datetime

        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n=== {stamp} ===\n{text}\n")
            fh.flush()
    except Exception:
        pass


def _enable_faulthandler():
    """Направить дампы жёстких падений в тот же файл.

    Возвращает открытый файл — его нельзя закрывать, пока программа жива,
    иначе faulthandler потеряет цель записи.
    """
    try:
        import faulthandler

        fh = open(_crash_log_path(), "a", encoding="utf-8")
        faulthandler.enable(fh)
        return fh
    except Exception:
        return None


def _environment() -> str:
    """Строка о том, где именно мы запустились — первое, что нужно при разборе."""
    return (f"Centurio boot | python {sys.version.split()[0]} | "
            f"frozen={getattr(sys, 'frozen', False)} | "
            f"exe={sys.executable} | argv={sys.argv}")


def _message_box(text: str, title: str = "Centurio", flags: int = 0x10) -> None:
    """Показать окно пользователю — или напечатать, если показывать некому.

    `MessageBoxW` модальный: ждёт нажатия «ОК». Там, где нажимать некому
    (тесты, CI, автоматический прогон), он вешает процесс намертво — на этом
    уже висел windows-раннер. `CENTURIO_NO_DIALOG=1` переводит сообщение в
    поток ошибок, не трогая поведение у обычного пользователя.
    """
    if os.environ.get("CENTURIO_NO_DIALOG") == "1":
        print(text, file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text[:1800], title, flags)
    except Exception:
        print(text, file=sys.stderr)


def _notify_already_running():
    _message_box("Centurio уже запущен — смотрите в трее.", flags=0x40)


def _boot() -> None:
    """Собственно запуск. Всё, что может упасть, живёт здесь под защитой."""
    import flet as ft

    from app.main import ASSETS_DIR, main
    from app.platform import single_instance

    web = os.environ.get("CENTURIO_WEB") == "1"
    port = int(os.environ.get("CENTURIO_PORT", "0") or 0)
    if not web and not single_instance.acquire():
        _notify_already_running()
        sys.exit(0)
    if web:
        ft.app(target=main, view=None, port=port or 8550, assets_dir=str(ASSETS_DIR))
    else:
        ft.app(target=main, assets_dir=str(ASSETS_DIR))


if __name__ == "__main__":
    _fault_file = _enable_faulthandler()
    # Отметка «дошли до сюда» до всех импортов: если следующей записи в файле
    # не появится, значит упал импорт или сам Flet, а не логика запуска.
    _record(_environment())
    try:
        _boot()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        detail = traceback.format_exc()
        _record(detail)
        _message_box("Centurio не смог запуститься.\n\n"
                     + detail.strip()[-1200:]
                     + f"\n\nПодробности: {_crash_log_path()}")
        raise
