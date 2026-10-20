"""Запуск программы: второй экземпляр, журнал падений, лог, автозапуск, трей, обновления."""
import os
import tempfile
import time
from pathlib import Path

from helpers import (
    _completes,
    _drop_log_handlers,
    _FakePage,
    _read,
    _reset_centurio_log,
    _run_bounded,
    _texts,
    _ui_for,
    ft,
    ok,
    skip,
    types_ns,
)

from app.core.store import Store
from app.ui import colors as C


def test_single_instance_mutex_is_per_session():
    """Мьютекс живёт в `Local\\`, а не в `Global\\`.

    Глобальное пространство имён общее на всю машину: на терминальном сервере
    второй пользователь не смог бы запустить программу. Вдобавок создание
    объекта в `Global\\` требует SeCreateGlobalPrivilege, которой у обычного
    пользователя может не быть, — `CreateMutexW` возвращает 0, `acquire`
    отвечает True, и защита от второго экземпляра просто отключается.
    """
    from app.platform import single_instance

    ok(single_instance.MUTEX_NAME.startswith("Local\\"),
       f"имя мьютекса ограничено сеансом ({single_instance.MUTEX_NAME})")

    ok(single_instance.SHOW_EVENT_NAME.startswith("Local\\"),
       "событие «покажи окно» тоже живёт в сеансе")
    if os.name != "nt":
        ok(single_instance.signal_existing() is False,
           "вне Windows будить некого — второй запуск скажет об этом сам")
        return
    import threading

    woke = threading.Event()
    try:
        ok(single_instance.acquire() is True, "первый экземпляр захватывает мьютекс")
        ok(single_instance.acquire() is True, "повторный вызов в том же процессе — не отказ")
        ok(single_instance.listen(woke.set), "первый экземпляр слушает просьбы показать окно")
        ok(single_instance.signal_existing() is True, "второй запуск достучался до первого")
        ok(woke.wait(5), "и первый показал окно")
    finally:
        single_instance.release()


def test_geometry_debounce():
    """Debounce.schedule(immediate=True) must not deadlock.

    The window-close handler takes this path: the previous inline version ran
    the callback while holding its own non-reentrant lock, so closing the
    window hung the app instead of saving the geometry and exiting.
    """

    from app.infra.debounce import Debounce

    # Every immediate flush goes through _completes(), and each assertion gets
    # its own instance: a deadlocked flush keeps that instance's lock forever.
    calls = []
    d = Debounce(0.05, lambda: calls.append(1))
    ok(_completes(lambda: d.schedule(immediate=True)),
       "immediate flush returns instead of deadlocking")
    ok(len(calls) == 1, "immediate flush runs the callback once")

    burst = []
    d2 = Debounce(0.05, lambda: burst.append(1))
    for _ in range(5):
        d2.schedule()
    ok(not burst, "debounced calls don't fire immediately")
    time.sleep(0.25)
    ok(len(burst) == 1, "a burst of calls collapses into one")

    mixed = []
    d3 = Debounce(0.05, lambda: mixed.append(1))
    d3.schedule()
    ok(_completes(lambda: d3.schedule(immediate=True)),
       "immediate flush after a pending one returns")
    time.sleep(0.2)
    ok(len(mixed) == 1, "an immediate flush cancels the pending one")

    dropped = []
    d4 = Debounce(0.05, lambda: dropped.append(1))
    d4.schedule()
    d4.cancel()
    time.sleep(0.2)
    ok(not dropped, "cancel drops the pending call")


def test_autostart():
    from app.platform import autostart

    with tempfile.TemporaryDirectory() as d:
        prev = os.environ.get("APPDATA")
        os.environ["APPDATA"] = d
        try:
            link = autostart.startup_shortcut()
            ok(link is not None and link.name == "Centurio.lnk",
               "startup shortcut path derived from APPDATA")
            ok(autostart.remove_startup_shortcut() is False,
               "removing a missing shortcut is a quiet no-op")
            link.parent.mkdir(parents=True, exist_ok=True)
            link.write_text("shortcut")
            ok(autostart.remove_startup_shortcut() is True and not link.exists(),
               "the installer's startup shortcut is removed")

            if os.name == "nt":
                # На настоящей Windows проверяем именно COM-путь (IShellLink),
                # а не откат на реестр: APPDATA изолирован во временную папку,
                # так что реальную «Автозагрузку» тест не трогает. Если бы
                # индексы vtable или Save были неверны, ярлык не появился бы —
                # и это упало бы на windows-раннере, а не пряталось за
                # молчаливым откатом на HKCU\Run.
                ok(autostart.create_startup_shortcut() is True,
                   "create_startup_shortcut writes a .lnk via IShellLink")
                ok(link.exists() and link.stat().st_size > 0,
                   "the shortcut file is really on disk and non-empty")
                autostart.remove_startup_shortcut()
        finally:
            if prev is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = prev

    if os.name != "nt":
        ok(autostart.is_enabled() is False, "autostart reports off outside Windows")
        ok(autostart.sync(True) is True, "sync keeps the stored preference outside Windows")
        ok(autostart.sync(False) is False, "sync keeps 'off' outside Windows")


def test_built_exe_autostart_passes_no_arguments():
    """Собранному exe нельзя передавать `--hidden` — он не запустит Python.

    Оболочка `flet build` (main.dart шаблона) принимает любой аргумент
    командной строки, кроме `--debug`, за адрес сервера «режима разработчика»
    и встроенный Python не запускает вовсе. Ярлык «Автозагрузки» с `--hidden`
    — и от инсталлятора, и от самого Centurio — поднимал окно, которое
    вечно ждало подключения к «--hidden». «Запуск в трей» теперь передаётся
    полем «Окно: свёрнутое» у ярлыка, а старые ярлыки переписываются.
    """
    import struct

    from app.platform import autostart

    prev = {k: os.environ.get(k) for k in ("FLET_PLATFORM", "APPDATA")}

    def restore():
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    with tempfile.TemporaryDirectory() as d:
        try:
            os.environ["APPDATA"] = d
            os.environ.pop("FLET_PLATFORM", None)
            ok("--hidden" in autostart._launch_parts()[1],
               "из исходников трей по-прежнему просит --hidden")
            os.environ["FLET_PLATFORM"] = "windows"
            ok(autostart._launch_parts()[1] == "",
               "собранному exe ярлык не передаёт ни одного аргумента")

            link = autostart.startup_shortcut()
            link.parent.mkdir(parents=True, exist_ok=True)
            link.write_bytes(b"L\0\0\0" + '"C:\\x\\Centurio.exe" --hidden'.encode("utf-16-le"))
            ok(autostart.has_stale_arguments() is True,
               "ярлык прошлой версии с --hidden распознаётся как устаревший")
            link.write_bytes(b"L\0\0\0" + "C:\\x\\Centurio.exe".encode("utf-16-le"))
            if os.name != "nt":
                ok(autostart.has_stale_arguments() is False,
                   "ярлык без аргументов переписывать незачем")
            os.environ.pop("FLET_PLATFORM", None)
            link.write_bytes(b"L\0\0\0" + '"main.py" --hidden'.encode("utf-16-le"))
            ok(autostart.has_stale_arguments() is False,
               "при запуске из исходников --hidden в ярлыке — норма, а не устаревание")
            link.unlink()

            ok(isinstance(autostart.started_minimized(), bool),
               "STARTUPINFO читается без исключений на любой платформе")

            if os.name == "nt":
                os.environ["FLET_PLATFORM"] = "windows"
                ok(autostart.create_startup_shortcut() is True,
                   "ярлык собранного exe создаётся")
                data = link.read_bytes()
                ok("--hidden".encode("utf-16-le") not in data,
                   "и не несёт --hidden")
                # ShellLinkHeader: ShowCommand — 4 байта по смещению 0x3C.
                ok(struct.unpack_from("<I", data, 0x3C)[0] == autostart.SW_SHOWMINNOACTIVE,
                   "зато запускает окно свёрнутым — это и есть «в трей»")
                ok(autostart.has_stale_arguments() is False,
                   "свежий ярлык не считается устаревшим")
                autostart.remove_startup_shortcut()
        finally:
            restore()


def test_second_instance_stops_even_when_flet_disarms_sys_exit():
    """Второй экземпляр обязан остановиться и в собранном exe.

    Загрузчик `flet build` подменяет `sys.exit` функцией, которая только
    сообщает код оболочке и возвращает управление. `sys.exit(0)` после
    «Centurio уже запущен» поэтому ничего не останавливал: следом шёл
    `ft.app()`, и второй экземпляр поднимал второе окно. Проверяется в
    отдельном процессе ровно в таких условиях.
    """
    import subprocess
    import sys as _sys

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as d:
        fake = os.path.join(d, "fake")
        os.makedirs(os.path.join(fake, "app", "platform"))
        with open(os.path.join(fake, "flet.py"), "w", encoding="utf-8") as fh:
            fh.write("print('FLET_IMPORTED')\n"
                     "def run(*a, **kw):\n    print('FT_APP_STARTED')\n")
        # Подменяется весь пакет app: проверяется только логика точки входа.
        for rel, body in ((("app", "__init__.py"), ""),
                          (("app", "main.py"), "ASSETS_DIR = '.'\ndef main(page):\n    pass\n"),
                          (("app", "platform", "__init__.py"), ""),
                          (("app", "platform", "single_instance.py"),
                           "def acquire():\n    return False\n"
                           "def signal_existing():\n    return False\n")):
            with open(os.path.join(fake, *rel), "w", encoding="utf-8") as fh:
                fh.write(body)
        runner = os.path.join(d, "run.py")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write("import runpy, sys\n"
                     "sys.exit = lambda code=0: print('EXIT', code)\n"
                     f"runpy.run_path({str(root / 'main.py')!r}, run_name='__main__')\n")

        env = dict(os.environ)
        env["APPDATA"] = d
        env["PYTHONPATH"] = fake
        env["CENTURIO_NO_DIALOG"] = "1"
        # Кириллица в stderr на windows-раннере (cp1252) иначе не печатается.
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("CENTURIO_WEB", None)
        proc = subprocess.run([_sys.executable, runner], cwd=d, env=env,
                              capture_output=True, encoding="utf-8", timeout=120)
        ok("уже запущен" in proc.stderr, "второму экземпляру говорят, что Centurio уже запущен")
        ok("FT_APP_STARTED" not in proc.stdout,
           f"и окно он не поднимает, даже когда sys.exit обезврежен ({proc.stdout!r})")
        ok("FLET_IMPORTED" not in proc.stdout,
           "второй экземпляр выходит, не загружая Flet: окно по Win+N появляется сразу")


def test_autostart_cannot_switch_itself_back_on():
    """Выключенный пользователем автозапуск остаётся выключенным.

    `sync` раньше применяла `preference or is_enabled()`: посторонний ключ
    `Centurio` в `HKCU\\Run` — от прежней установки, от другой сборки —
    включал автозапуск обратно, а `app/main.py` этим же переписывал настройку
    в файле данных. Таблица истинности проверяется на любой платформе,
    настоящий реестр — только на Windows-раннере.
    """
    from app.platform import autostart

    table = [(True, True, False), (True, False, True),
             (False, True, True), (False, False, False)]
    for preference, enabled, expected in table:
        ok(autostart.needs_write(preference, enabled) is expected,
           f"настройка={preference}, в системе={enabled} → пишем {expected}")

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)
        ok(s.settings()["autostart_adopted"] is False,
           "у нового файла данных галочка инсталлятора ещё не перенесена")
        s.set_setting("autostart_adopted", True)
        ok(Store(path).settings()["autostart_adopted"] is True,
           "отметка о переносе переживает перезапуск, поэтому он разовый")

    if os.name != "nt":
        return

    was = autostart.is_enabled()
    try:
        autostart.set_autostart(True)
        ok(autostart.is_enabled() is True, "автозапуск включается")
        # Предпочтение — ярлыку в «Автозагрузке», а не записи в HKCU\Run:
        # она формально подпадает под MITRE T1547.001, и антивирусы к ней
        # придирчивее. Ключ остаётся только запасным путём, если COM не смог
        # создать ярлык, — иначе его быть не должно.
        link = autostart.startup_shortcut()
        if link is not None and link.exists():
            ok(autostart._run_key_set() is False,
               "при живом ярлыке ключ реестра не создаётся")
        ok(autostart.sync(False) is False and autostart.is_enabled() is False,
           "чужой ключ в HKCU\\Run не переигрывает выключенную настройку")
        ok(autostart.sync(True) is True and autostart.is_enabled() is True,
           "включённая настройка доводится до системы")
    finally:
        autostart.set_autostart(was)


def test_tray_lists_pinned_programs_without_keys():
    """Меню трея — закреплённые программы по именам, без Ctrl+N.

    Ctrl+N работают только в окне Centurio, а меню трея открыто, когда окна
    нет: подпись с клавишей обещала бы то, чего нажатие не сделает.
    """
    from app.ui import screens

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B", "C")]
        for app_id in ids[:2]:
            store.update_app(app_id, {"quick": True})
        items = screens.tray_items(store)
        ok([i["id"] for i in items] == ids[:2], "only pinned programs are listed")
        ok([i["label"] for i in items] == ["A", "B"], "labelled by name alone")


def test_log():
    import importlib

    from app.infra import log as _log
    importlib.reload(_log)
    import logging
    with tempfile.TemporaryDirectory() as d:
        try:
            _log.setup(debug=True, log_dir=d)
            _log._LOGGER.handlers = [h for h in _log._LOGGER.handlers
                                     if isinstance(h, logging.FileHandler)]
            try:
                raise ValueError("boom")
            except ValueError:
                _log.exception("handled test error")
            _log.debug("a debug line")
            ok(os.path.exists(os.path.join(d, "centurio.log")), "debug log file created")
            with open(os.path.join(d, "centurio.log"), encoding="utf-8") as fh:
                body = fh.read()
            ok("handled test error" in body and "boom" in body,
               "exception logged with traceback")
        finally:
            # RotatingFileHandler keeps centurio.log open until closed — POSIX
            # lets you unlink an open file, but the TemporaryDirectory cleanup
            # below runs on Windows too, where an open handle blocks deletion.
            for h in list(_log._LOGGER.handlers):
                h.close()
                _log._LOGGER.removeHandler(h)


def test_entry_point_records_a_crash_before_any_project_import():
    """«Вылетает, логов нет» — самый бесполезный отчёт; журнал должен быть всегда.

    Обычный лог поднимается внутри `main(page)`, то есть уже после `import
    flet` и разбора всего пакета `app`. Если процесс умирает раньше — а
    отсутствующая нативная DLL убивает именно там, — наружу не попадало ни
    строчки: у собранного exe нет консоли. Корневой `main.py` теперь пишет
    `centurio-crash.log` только стандартной библиотекой и до импортов проекта.

    Проверяется по-настоящему: запускаем настоящую точку входа отдельным
    процессом, подсунув падающий `flet` — так же ведёт себя ненайденная DLL.
    """
    import subprocess
    import sys as _sys

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as d:
        fake = os.path.join(d, "fake")
        os.makedirs(fake)
        with open(os.path.join(fake, "flet.py"), "w", encoding="utf-8") as fh:
            fh.write('raise ImportError("DLL load failed while importing flet")\n')

        env = dict(os.environ)
        env["APPDATA"] = d
        env["PYTHONPATH"] = fake
        # Иначе модальное окно ждало бы «ОК» и повесило бы прогон.
        env["CENTURIO_NO_DIALOG"] = "1"
        env.pop("CENTURIO_WEB", None)
        proc = subprocess.run([_sys.executable, str(root / "main.py")],
                              env=env, capture_output=True, text=True, timeout=120)

        ok(proc.returncode != 0, "a broken import really does kill the process")

        crash = os.path.join(d, "Centurio", "centurio-crash.log")
        ok(os.path.exists(crash), "and it leaves a crash log behind anyway")
        body = ""
        if os.path.exists(crash):
            with open(crash, encoding="utf-8") as fh:
                body = fh.read()
        ok("Centurio boot" in body,
           "the log says how far startup got before dying")
        ok("DLL load failed" in body,
           f"and names the actual failure, not just 'it crashed' ({body[-200:]!r})")


def test_startup_failure_is_reported_not_silent():
    """Сбой старта обязан оставить трассировку, а не убить окно молча.

    Собранный `Centurio.exe` — оконный: консоли нет, и исключение из `main()`
    уходило в Flet бесследно. Уровень лога по умолчанию — WARNING, поэтому в
    файле тоже не оставалось ничего. Снаружи это выглядело как «exe вылетает
    сразу», без единой зацепки, и причину нельзя было даже назвать.
    """
    import importlib

    _log = _reset_centurio_log()
    try:
        from app import main as main_mod
    except Exception as exc:
        skip("startup guard test", exc)
        return
    importlib.reload(main_mod)

    with tempfile.TemporaryDirectory() as d:
        prev = os.environ.get("APPDATA")
        os.environ["APPDATA"] = d
        real_ui = main_mod.CenturioUI
        real_report = main_mod._report_startup_failure
        try:
            def boom(*a, **kw):
                raise RuntimeError("сбой сборки интерфейса")
            main_mod.CenturioUI = boom
            # `_report_startup_failure` показывает модальное окно MessageBoxW.
            # На раннере его некому закрыть, и шаг Test висел часами вместо
            # секунд. Проверяем здесь запись в лог, а не саму отрисовку окна.
            main_mod._report_startup_failure = lambda: None

            finished, raised = _run_bounded(lambda: main_mod.main(_FakePage()))
            ok(finished, "startup returns instead of hanging")
            ok(isinstance(raised, RuntimeError),
               f"the failure is re-raised, not swallowed into a dead window ({raised!r})")

            body = ""
            logfile = os.path.join(d, "Centurio", "centurio.log")
            if os.path.exists(logfile):
                with open(logfile, encoding="utf-8") as fh:
                    body = fh.read()
            ok("Traceback" in body, "the log carries a real traceback")
            ok("сбой сборки интерфейса" in body,
               "and names the actual cause, not just 'failed to start'")
        finally:
            main_mod.CenturioUI = real_ui
            main_mod._report_startup_failure = real_report
            _drop_log_handlers(_log)
            if prev is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = prev


def test_optional_startup_steps_degrade_instead_of_killing_the_app():
    """Отказ трея, клавиш или значков не должен мешать окну открыться.

    Centurio — панель запуска: окно без трея нужнее, чем «exe вылетает сразу».
    Платформенные шаги (pystray, монитор процессов, запись значков рядом
    с exe) на чужой машине могут отказать по причинам, которые
    нам не подвластны, — тогда их надо записать в лог и идти дальше.
    """
    import importlib

    _log = _reset_centurio_log()
    try:
        from app import main as main_mod
    except Exception as exc:
        skip("startup degradation test", exc)
        return
    importlib.reload(main_mod)

    from app.platform import launcher as la_mod
    from app.platform import tray as tr_mod

    def boom(*a, **kw):
        raise OSError("симулированный отказ платформы")

    saved = (main_mod.ensure_icons, tr_mod.TrayController.start,
             la_mod.Launcher.start_monitor, tr_mod.TrayController.refresh,
             main_mod._report_startup_failure)
    with tempfile.TemporaryDirectory() as d:
        prev = os.environ.get("APPDATA")
        os.environ["APPDATA"] = d
        try:
            main_mod.ensure_icons = boom
            tr_mod.TrayController.start = boom
            la_mod.Launcher.start_monitor = boom
            tr_mod.TrayController.refresh = boom
            # Страховка: если старт всё же упадёт, модальное окно не должно
            # подвесить прогон — см. _run_bounded.
            main_mod._report_startup_failure = lambda: None

            finished, raised = _run_bounded(lambda: main_mod.main(_FakePage()))
            ok(finished, "startup returns instead of hanging")
            ok(raised is None,
               f"the window still opens when every optional step fails ({raised!r})")

            body = ""
            logfile = os.path.join(d, "Centurio", "centurio.log")
            if os.path.exists(logfile):
                with open(logfile, encoding="utf-8") as fh:
                    body = fh.read()
            degraded = [line for line in body.splitlines() if "шаг запуска" in line]
            ok(len(degraded) >= 4,
               f"and each skipped step is written down, not swallowed ({len(degraded)})")
        finally:
            (main_mod.ensure_icons, tr_mod.TrayController.start,
             la_mod.Launcher.start_monitor, tr_mod.TrayController.refresh,
             main_mod._report_startup_failure) = saved
            _drop_log_handlers(_log)
            if prev is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = prev


def test_first_hide_to_tray_explains_where_the_window_went():
    """Первый уход в трей объясняет себя — и только первый.

    Крестик по умолчанию прячет окно в трей, а значок в Windows 11 часто
    скрыт за стрелкой: без подсказки выглядело так, будто программа закрылась.
    """
    import importlib

    _log = _reset_centurio_log()
    try:
        from app import main as main_mod
    except Exception as exc:
        skip("tray hint test", exc)
        return
    importlib.reload(main_mod)
    from app.platform import tray as tr_mod

    shown = []

    def fake_start(self):
        self.available = True
        self._icon = types_ns(notify=lambda message, title=None: shown.append(message),
                              update_menu=lambda: None, stop=lambda: None)
        return True

    saved = (tr_mod.TrayController.start, main_mod._report_startup_failure)
    with tempfile.TemporaryDirectory() as d:
        prev = os.environ.get("APPDATA")
        os.environ["APPDATA"] = d
        try:
            tr_mod.TrayController.start = fake_start
            main_mod._report_startup_failure = lambda: None
            page = _FakePage()
            finished, raised = _run_bounded(lambda: main_mod.main(page))
            ok(finished and raised is None, f"the window opens ({raised!r})")
            page.window.on_event(types_ns(type=ft.WindowEventType.CLOSE))
            ok(page.window.visible is False, "the close button hides the window to the tray")
            ok(len(shown) == 1 and "трее" in shown[0], "and says where it went")
            page.window.visible = True
            page.window.on_event(types_ns(type=ft.WindowEventType.CLOSE))
            ok(len(shown) == 1, "but only the first time")
        finally:
            tr_mod.TrayController.start, main_mod._report_startup_failure = saved
            from app.platform import single_instance
            single_instance.release()
            _drop_log_handlers(_log)
            if prev is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = prev


def test_log_is_ready_before_the_store_is_read():
    """Порядок в `main()`: сначала лог, потом чтение файла данных.

    Про карантин битого файла и про несовместимую схему сообщает сам
    `Store.__init__`. Пока `log.setup()` шёл после него, эти сообщения — ровно
    те, ради которых лог и заводят, — уходили в `NullHandler`. Проверяется по
    исходнику: выполнить `main()` в тесте нельзя, ему нужна страница Flet.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(encoding="utf-8")

    # Ищем не по имени, а по делу: ту функцию, которая заводит Store. Тело
    # старта переехало из `main` в `_start` (сверху появилась обёртка, ловящая
    # сбой запуска), и привязка к имени сломала бы проверку, хотя само
    # правило — лог раньше чтения данных — не менялось.
    def makes_store(fn):
        return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "Store" for n in ast.walk(fn))

    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and makes_store(n))

    def first_line(match):
        lines = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and match(n.func)]
        return min(lines) if lines else None

    setup_at = first_line(lambda f: isinstance(f, ast.Attribute) and f.attr == "setup"
                          and isinstance(f.value, ast.Name) and f.value.id == "log")
    store_at = first_line(lambda f: isinstance(f, ast.Name) and f.id == "Store")

    ok(setup_at is not None, "main() настраивает лог")
    ok(store_at is not None, "main() создаёт Store")
    ok(setup_at < store_at,
       f"log.setup() раньше Store() (строки {setup_at} и {store_at})")


def test_log_level_follows_the_debug_setting():
    """`debug_log` живёт внутри файла данных, а лог поднимается до его чтения.

    Значит уровень нельзя задать одним `setup()` — его повышает вторым шагом
    `set_debug()`, уже после того, как Store прочитал настройки.
    """
    import importlib
    import logging

    from app.infra import log as _log
    importlib.reload(_log)
    with tempfile.TemporaryDirectory() as d:
        try:
            _log.setup(debug=False, log_dir=d)
            _log._LOGGER.handlers = [h for h in _log._LOGGER.handlers
                                     if isinstance(h, logging.FileHandler)]
            ok(_log._LOGGER.level == logging.WARNING, "без флага лог остаётся кратким")
            _log.debug("строка до чтения настроек")

            _log.set_debug(False)
            ok(_log._LOGGER.level == logging.WARNING, "выключенная настройка ничего не меняет")

            _log.set_debug(True)
            ok(_log._LOGGER.level == logging.DEBUG, "настройка из файла данных поднимает уровень")
            _log.debug("строка после чтения настроек")

            with open(os.path.join(d, "centurio.log"), encoding="utf-8") as fh:
                body = fh.read()
            ok("строка до чтения настроек" not in body, "до set_debug отладка не пишется")
            ok("строка после чтения настроек" in body, "после set_debug пишется")
        finally:
            for h in list(_log._LOGGER.handlers):
                h.close()
                _log._LOGGER.removeHandler(h)


def test_update_check():
    """Раз в сутки — вопрос GitHub о новой версии; о каждой версии говорится один раз."""
    import io
    import json as _json
    import urllib.error
    from unittest.mock import patch

    from app import __version__
    from app.infra import updates

    ok(updates.parse_version("v1.10.2") == (1, 10, 2) and updates.parse_version("beta") is None,
       "versions are read from tags, junk is not")
    ok(updates.is_newer("1.10.0", "1.9.9") and not updates.is_newer("1.2", "1.2.0")
       and not updates.is_newer("x", "1.0.0"), "and compared as numbers, not text")

    def reply(payload):
        return io.BytesIO(_json.dumps(payload).encode())

    with patch("urllib.request.urlopen",
               lambda req, timeout: reply({"tag_name": "v9.9.9",
                                           "html_url": "https://example/r/9"})):
        ok(updates.fetch_latest() == {"version": "9.9.9", "url": "https://example/r/9"},
           "the latest release is read from the GitHub API")
    with patch("urllib.request.urlopen",
               lambda req, timeout: reply({"tag_name": "v9.9.9", "prerelease": True})):
        ok(updates.fetch_latest() is None, "a pre-release is not offered")

    def missing(req, timeout):
        raise urllib.error.HTTPError(updates.API_URL, 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", missing):
        ok(updates.fetch_latest() is None, "no releases yet is not an error")

    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI update check test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)
        opened = []
        ui.open_url = opened.append
        ok(ui.updates.due(), "a fresh install is due for a check")

        ui.updates.fetch = lambda: {"version": "9.9.9", "url": "https://example/r/9"}
        ui.updates.check(quiet=True)
        ok(ui.toast.text.value == "Вышла Centurio 9.9.9" and ui.toast.action_btn.visible,
           "a newer release is announced with a way to get it")
        ui.toast.fire_action()
        ok(opened == ["https://example/r/9"], "«Скачать» opens the release page")
        ok(not ui.updates.due(), "and the next check waits a day")
        ui.refresh()
        ok(any("Вышла 9.9.9" in t for t in _texts(ui.sidebar_container)),
           "the sidebar keeps a quiet reminder")

        ui.toast.dismiss()
        ui.toast.text.value = ""
        ui.updates.check(quiet=True)
        ok(ui.toast.text.value == "", "the same version is not announced twice")

        ui.updates.fetch = lambda: {"version": __version__, "url": "u"}
        ui.updates.check(quiet=False)
        ok(ui.updates.available() == "" and __version__ in ui.toast.text.value,
           "«Проверить сейчас» says when this is the latest version")

        def offline():
            raise OSError("no network")
        ui.updates.fetch = offline
        ui.updates.check(quiet=False)
        ok(ui.toast.icon.color == C.DANGER, "and says so when GitHub can't be reached")

        store.set_setting("check_updates", False)
        store.set_setting("update_checked_at", 0)
        ok(not ui.updates.due(), "with the switch off, nothing is ever asked")


def test_shutdown_releases_resources():
    """Quitting used to rely entirely on daemon threads and os._exit."""
    try:
        from app import main as main_mod
    except Exception as exc:
        skip("shutdown test", exc)
        return

    ok(hasattr(main_mod, "shutdown"), "app.main exposes a shutdown routine")
    shutdown = main_mod.shutdown

    page_module = _read("app", "main.py")
    ok("ui.keymap.handle_key(e)" in page_module,
       "the page's key handler delegates to the UI's key table")

    calls = []

    class Recorder:
        def __init__(self, label, boom=False):
            self.label = label
            self.boom = boom

        def __call__(self):
            calls.append(self.label)
            if self.boom:
                raise RuntimeError(f"{self.label} is already gone")

    shutdown(store=types_ns(flush=Recorder("flush")),
             tray=types_ns(stop=Recorder("tray")),
             launcher=types_ns(stop_monitor=Recorder("monitor")),
             geometry_flush=types_ns(cancel=Recorder("geometry")),
             toast=types_ns(stop=Recorder("toast")),
             stop_event=types_ns(set=Recorder("bg")))
    ok(set(calls) == {"flush", "bg", "geometry", "monitor", "tray", "toast"},
       f"every resource is released ({calls})")
    ok(calls[0] == "flush", "the store is flushed before anything is torn down")
    ok("bg" in calls, "the background-jobs loop is signalled to stop, not left running")

    calls.clear()
    shutdown(store=types_ns(flush=Recorder("flush", boom=True)),
             tray=types_ns(stop=Recorder("tray")),
             launcher=types_ns(stop_monitor=Recorder("monitor")))
    ok("tray" in calls and "monitor" in calls,
       "a step that raises doesn't stop the rest of the teardown")

    raised = None
    try:
        shutdown()
    except Exception as exc:
        raised = exc
    ok(raised is None, "shutdown with nothing to release is a quiet no-op")


def test_tray_mini_launcher():
    try:
        from app.platform.tray import TrayController
        from app.ui import screens as dialogs
    except Exception as exc:
        skip("tray test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        for i in range(8):
            store.add_app({"name": f"App{i}", "path": f"/x/{i}", "category_id": "work",
                           "quick": i < 7})
        items = dialogs.tray_items(store)
        ok(len(items) == 6, "the menu offers at most six pinned programs")
        ok(all("Ctrl+" not in i["label"] for i in items),
           "no key in the labels: Ctrl+N only works inside the window")
        ok("8 приложений" in dialogs.library_summary(store), "and the menu sizes the library")

        store.queue_inbox([{"name": "New", "path": "C:/new.exe"}])
        ok("в разборе" in dialogs.library_summary(store),
           "and mentions the queue when something waits in it")

        opened = []
        tray = TrayController("/no/such/icon.png",
                              on_show=lambda: opened.append("launch"),
                              on_open_library=lambda: opened.append("library"),
                              menu_provider=lambda: ([("App0", lambda: opened.append("app"))],
                                                     "8 приложений"))
        ok(tray.start() is False, "a missing icon file doesn't crash the tray")
        tray._show()
        tray._open_library()
        ok(opened == ["launch", "library"], "the entries reach their callbacks")
        tray.menu_provider = lambda: 1 / 0
        ok(tray._provided() == ([], ""), "a failing menu provider degrades to an empty menu")
