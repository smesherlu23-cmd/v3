from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

import flet as ft

from app.core.store import Store
from app.infra import log, paths
from app.infra.debounce import Debounce
from app.platform import autostart, single_instance
from app.platform import windows as W
from app.platform.launcher import Launcher
from app.platform.tray import TrayController
from app.ui import colors as C
from app.ui import images
from app.ui.app import CenturioUI
from app.ui.iconify import ensure_icons, tray_icon_path

_DEV_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ASSETS_DIR = Path(os.environ.get("FLET_ASSETS_DIR") or _DEV_ASSETS_DIR).resolve()
GEOMETRY_FLUSH_DELAY = 0.5
AUTO_RESCAN_INTERVAL = 900


def shutdown(store=None, tray=None, launcher=None, geometry_flush=None,
             toast=None, stop_event=None):
    for label, step in (("flushing the store", getattr(store, "flush", None)),
                        ("stopping background jobs", getattr(stop_event, "set", None)),
                        ("cancelling the geometry flush",
                         getattr(geometry_flush, "cancel", None)),
                        ("stopping the toast timer", getattr(toast, "stop", None)),
                        ("stopping the process monitor",
                         getattr(launcher, "stop_monitor", None)),
                        ("stopping the tray icon", getattr(tray, "stop", None)),
                        ("releasing the single-instance lock", single_instance.release)):
        if step is None:
            continue
        try:
            step()
        except Exception:
            log.exception("%s on quit failed", label)


def _report_startup_failure() -> None:
    """Показать, почему программа не запустилась.

    Собранный `Centurio.exe` — оконный, консоли у него нет, и трассировка из
    Flet уходит в никуда. Без этого окна сбой старта выглядит снаружи как
    «exe вылетает сразу», без единой зацепки.
    """
    detail = traceback.format_exc(limit=8).strip()
    text = ("Centurio не смог запуститься.\n\n"
            f"{detail}\n\n"
            f"Подробности: {paths.data_dir() / 'centurio.log'}")
    # Модальное окно ждёт «ОК». Там, где нажимать некому (тесты, CI), оно
    # вешает процесс — см. тот же переключатель в корневом main.py.
    if os.environ.get("CENTURIO_NO_DIALOG") == "1":
        print(text, file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text[:1800], "Centurio", 0x10)
    except Exception:
        print(text, file=sys.stderr)


def _optional(label: str, step) -> bool:
    """Необязательный шаг запуска: сбой записываем, но окно всё равно открываем.

    Centurio — панель запуска. Ни трей, ни монитор процессов, ни автокопия
    не стоят того, чтобы из-за них программа не открылась вовсе:
    окно без трея нужнее, чем «exe вылетает сразу». Обязательные шаги (Store,
    сборка интерфейса, mount) намеренно не заворачиваются — без них показывать
    нечего, и о таком сбое сообщает `main()`.
    """
    try:
        step()
        return True
    except Exception:
        log.exception("шаг запуска «%s» не удался — продолжаю без него", label)
        return False


def main(page: ft.Page):
    """Точка входа Flet: собрать окно, а при сбое — не умереть молча.

    Исключение отсюда раньше уходило в Flet, процесс закрывался, и в логе не
    оставалось ничего: уровень по умолчанию — WARNING, а до `log.setup()`
    сообщений нет вовсе.
    """
    try:
        _start(page)
    except Exception:
        try:
            # Идемпотентно: если лог уже поднят, вернёт тот же логгер, а если
            # упали до его настройки — настроит сейчас, чтобы запись дошла.
            log.setup(log_dir=paths.data_dir())
        except Exception:
            pass
        log.exception("не удалось запустить Centurio")
        _report_startup_failure()
        raise


def _start(page: ft.Page):
    log.setup(log_dir=paths.data_dir())
    store = Store()
    log.set_debug(bool(store.state()["settings"].get("debug_log")))
    log.debug("Centurio starting (argv=%s)", sys.argv)

    _optional("подготовка значков", lambda: ensure_icons(ASSETS_DIR))
    is_web = page.web or os.environ.get("CENTURIO_WEB") == "1"
    images.embed_images(is_web)
    # Собранный exe аргументов не получает (см. autostart._embedded), поэтому
    # «Автозагрузка» просит трей полем «Окно: свёрнутое» у ярлыка;
    # `--hidden` остаётся для запуска из исходников.
    start_hidden = "--hidden" in sys.argv or (not is_web and autostart.started_minimized())

    page.title = "Centurio"
    page.bgcolor = C.BG_1
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.fonts = {
        "Inter": "fonts/Inter-Regular.ttf",
        "Inter SemiBold": "fonts/Inter-SemiBold.ttf",
        "Inter Bold": "fonts/Inter-Bold.ttf",
        "Inter ExtraBold": "fonts/Inter-ExtraBold.ttf",
        "mono": "fonts/Mono-Regular.ttf",
    }
    page.theme = ft.Theme(color_scheme_seed=C.ACCENT, font_family="Inter")

    if not is_web:
        page.window.title_bar_hidden = True
        page.window.frameless = True
        page.window.prevent_close = True

    launcher = Launcher()
    geometry_flush = None
    ui_holder = {}
    bg_stop = threading.Event()

    def quit_app():
        ui = ui_holder.get("ui")
        shutdown(store=store, tray=tray, launcher=launcher,
                 geometry_flush=geometry_flush, toast=getattr(ui, "toast", None),
                 stop_event=bg_stop)
        _quit(page)

    def apply_window():
        if is_web:
            return
        try:
            s = store.state()["settings"]
            page.window.resizable = True
            page.window.min_width = C.LIBRARY_MIN_W
            page.window.min_height = C.LIBRARY_MIN_H
            width = max(C.LIBRARY_MIN_W, s.get("win_w") or C.LIBRARY_W)
            height = max(C.LIBRARY_MIN_H, s.get("win_h") or C.LIBRARY_H)
            page.window.width = width
            page.window.height = height
            x, y = s.get("win_x"), s.get("win_y")
            have_pos = x is not None and y is not None
            areas = W.monitors()
            fits = have_pos and (not areas or W.visible_on_monitors((x, y, width, height), areas))
            if fits:
                page.window.left = x
                page.window.top = y
            if s.get("win_max"):
                page.window.maximized = True
            page.update()
            if not fits:
                page.run_task(page.window.center)
        except Exception:
            log.exception("восстановление геометрии окна ошибка")

    def set_visible(visible: bool):
        try:
            launcher.set_background(not visible)
        except Exception:
            log.exception("не удалось переключить режим монитора процессов")
        ui = ui_holder.get("ui")
        if ui is not None:
            try:
                ui.set_visible(visible)
            except Exception:
                log.exception("не удалось переключить видимость интерфейса")

    def show_window():
        _show_window(page)
        set_visible(True)

    def hide_window():
        _hide_window(page)
        set_visible(False)

    def open_library():
        ui = ui_holder.get("ui")
        show_window()
        if ui is not None:
            ui.open_library()

    def minimize():
        if store.state()["settings"].get("minimize_to_tray") and tray.available:
            hide_to_tray()
        else:
            page.window.minimized = True
            set_visible(False)
            page.update()

    def toggle_maximize():
        page.window.maximized = not page.window.maximized
        page.update()

    def close():
        if store.state()["settings"].get("close_to_tray") and tray.available:
            hide_to_tray()
        else:
            quit_app()

    def hide_to_tray():
        if is_web:
            return
        if tray.available:
            hide_window()
            tray_hint_once()
        else:
            page.window.minimized = True
            set_visible(False)
            page.update()

    def tray_hint_once():
        # Окно исчезло, а значок в Windows 11 часто спрятан за стрелкой —
        # без подсказки кажется, что программа закрылась.
        if store.state()["settings"].get("tray_hint_shown"):
            return
        if tray.notify("Centurio работает в трее. Щёлкните значок, чтобы открыть окно, "
                       "или запустите Centurio ещё раз. Выйти — «Выход» в меню значка."):
            store.set_setting("tray_hint_shown", True)

    def on_setting(key, value):
        if key == "autostart":
            autostart.set_autostart(bool(value))

    def refresh_runtime():
        launcher.set_apps(store.state()["apps"])
        tray.refresh()

    controllers = {
        "minimize": minimize, "toggle_maximize": toggle_maximize, "close": close,
        "hide_to_tray": hide_to_tray, "on_setting": on_setting,
        "on_library_changed": refresh_runtime,
    }

    def launch_from_tray(app_id):
        ui = ui_holder.get("ui")
        if ui is not None:
            ui._launch(app_id)

    def tray_menu():
        from app.ui import screens
        items = [(item["label"], (lambda aid=item["id"]: launch_from_tray(aid)))
                 for item in screens.tray_items(store)]
        return items, screens.library_summary(store)

    tray = TrayController(tray_icon_path(ASSETS_DIR), on_show=open_library, on_quit=quit_app,
                          on_open_library=open_library, menu_provider=tray_menu)

    ui = CenturioUI(page, store, launcher, controllers)
    ui_holder["ui"] = ui
    launcher.on_change = lambda ids: ui.set_running(ids)

    def on_key(e: ft.KeyboardEvent):
        try:
            ui.keymap.handle_key(e)
        except Exception:
            log.exception("управление нажатием клавиши ошибка")
    page.on_keyboard_event = on_key

    def _flush_geometry():
        try:
            store.flush()
        except Exception:
            log.exception("сбой в геометрии окна промывки")
        try:
            ui.refresh()
        except Exception:
            log.exception("сбой при перерисовке после изменения размера")

    geometry_flush = Debounce(GEOMETRY_FLUSH_DELAY, _flush_geometry)

    def save_window(flush: bool = False):
        try:
            w, h = page.window.width, page.window.height
            maximized = page.window.maximized
            store.set_setting("win_max", maximized, persist=False)
            if not maximized:
                if w and h and w >= C.LIBRARY_MIN_W and h >= C.LIBRARY_MIN_H:
                    store.set_setting("win_w", int(w), persist=False)
                    store.set_setting("win_h", int(h), persist=False)
                if page.window.left is not None and page.window.top is not None:
                    store.set_setting("win_x", int(page.window.left), persist=False)
                    store.set_setting("win_y", int(page.window.top), persist=False)
        except Exception:
            log.exception("сбой при сохранении геометрии окна")
            return
        geometry_flush.schedule(immediate=flush)

    def on_win_event(e):
        kind = e.type.value if e.type else ""
        if kind in ("resized", "moved", "maximize", "unmaximize"):
            save_window()
        elif kind == "minimize":
            log.info("событие окна: свёрнуто")
            set_visible(False)
        elif kind in ("restore", "focus"):
            set_visible(True)
        elif kind == "close":
            save_window(flush=True)
            close()
    page.window.on_event = on_win_event if not is_web else None

    apply_window()
    if start_hidden and not is_web:
        ui.set_visible(False)
    ui.mount()

    def _backfill():
        try:
            from app.platform import discovery
            cache = str(app_paths_dir(store))
            schema = store.state()["settings"].get("icon_schema", 0)
            refresh = schema < discovery.ICON_SCHEMA
            if discovery.backfill_icons(store, cache, refresh=refresh):
                ui.refresh()
            if refresh:
                store.set_setting("icon_schema", discovery.ICON_SCHEMA)
            discovery.prune_icon_cache(store, cache)
            ui.forget_icon_cache_size()
        except Exception:
            log.exception("сбой при заполнении значков")
    threading.Thread(target=_backfill, daemon=True).start()
    _optional("меню трея", refresh_runtime)
    _optional("монитор запущенных программ", launcher.start_monitor)
    _optional("предложения на пустой библиотеке", ui.scan.offer_first_run)
    if os.environ.get("CENTURIO_UI_CHECK"):
        from app.ui import ui_check
        ui_check.start(ui, launcher, os.environ["CENTURIO_UI_CHECK"], bg_stop)

    def _background_loop():
        # Автокопия и обновления проверяются при запуске и потом каждые 15
        # минут: сами они срабатывают не чаще раза в сутки, а компьютер с
        # Centurio в трее могут не выключать неделями.
        _optional("автокопия библиотеки", store.auto_backup)
        _optional("проверка обновлений", ui.updates.check_if_due)
        while not bg_stop.wait(AUTO_RESCAN_INTERVAL):
            _optional("автокопия библиотеки", store.auto_backup)
            _optional("проверка обновлений", ui.updates.check_if_due)
            try:
                if store.state()["settings"].get("auto_rescan"):
                    ui.scan.rescan(silent=True)
            except Exception:
                log.exception("ошибка автоматической повторной проверки галочки")
    threading.Thread(target=_background_loop, daemon=True).start()

    if not is_web:
        def _adopt_autostart():
            settings = store.state()["settings"]
            if not settings.get("autostart_adopted"):
                adopted = (bool(settings.get("autostart"))
                           or autostart.adopt_installer_choice())
                store.set_setting("autostart", adopted)
                store.set_setting("autostart_adopted", True)
                ui.refresh()
            autostart.sync(bool(store.state()["settings"].get("autostart", False)))

        _optional("автозапуск", _adopt_autostart)
        _optional("значок в трее", tray.start)
        _optional("показ окна по второму запуску",
                  lambda: single_instance.listen(open_library))
        if start_hidden:
            # Прятаться в трей можно только если трей действительно поднялся:
            # иначе окно исчезнет, а вернуть его будет нечем.
            if tray.available:
                hide_window()
            else:
                log.warning("трея нет — открываю окно, несмотря на --hidden")


def app_paths_dir(store):
    return Path(store.path).parent / "icons"


def _show_window(page):
    try:
        page.window.visible = True
        page.window.minimized = False
        page.update()
    except Exception:
        log.exception("не удалось восстановить окно")
    async def to_front():
        await page.window.to_front()
        page.window.focused = True
        page.update()
    try:
        page.run_task(to_front)
    except Exception:
        log.exception("не удалось переместить окно на передний план")


def _hide_window(page):
    try:
        page.window.visible = False
        page.update()
    except Exception:
        log.exception("не удалось скрыть окно")


def _quit(page):
    async def destroy():
        page.window.prevent_close = False
        page.update()
        await page.window.destroy()
    # Закрытие окна идёт через цикл событий Flet; если он уже не отвечает,
    # процесс всё равно должен завершиться, а не висеть в трее без значка.
    threading.Timer(5.0, os._exit, args=(0,)).start()
    try:
        page.run_task(destroy)
    except Exception:
        log.exception("не удалось закрыть окно, выход вручную")
        os._exit(0)
