"""Запуск программ, слежение за процессами, окна и раскладки наборов."""
import os
import sys
import tempfile
import time

from helpers import ok, skip, types_ns

from app.core.store import Store


def test_layout_presets():
    """Раскладка окон — доли экрана, а не пиксели: переживает смену монитора."""
    from app.core import layout as L

    ok(L.slot_count("full") == 1, "«На весь экран» — одно место")
    ok(L.slot_count("half") == 2 and L.slot_count("6040") == 3, "half is two, 60/40 is three")
    ok(L.slot_count("grid4") == 4, "and the grid is four")
    ok(L.valid_preset("nonsense") == L.DEFAULT_PRESET, "an unknown preset falls back")

    left, top_right, bottom_right = L.slots("6040", 0.6, 0.5)
    ok(left == (0.0, 0.0, 0.6, 1.0), "60/40 gives the left window six tenths")
    ok(top_right == (0.6, 0.0, 0.4, 0.5) and bottom_right == (0.6, 0.5, 0.4, 0.5),
       "and stacks the other two in the remaining column")
    for name in L.PRESETS:
        covered = sum(w * h for _x, _y, w, h in L.slots(name))
        ok(abs(covered - 1.0) < 1e-9, f"«{name}» covers the screen exactly, no gaps")

    dragged = L.slots("half", 0.95)[0]
    ok(dragged[2] == L.MAX_SPLIT, "dragging an edge past the limit stops at it")

    ok("слева" in L.slot_label("6040", 0), "each place has a name")
    ok("60%" in L.slot_label("6040", 0, 0.6), "carrying the share it takes")
    ok(L.slot_label("6040", 9) == "", "an index the preset doesn't have has none")
    ok(L.slot_label("grid4", 3) == "справа снизу", "the grid names its corners")

    ok(L.rect_for({"slot": 0}, "half") == (0.0, 0.0, L.DEFAULT_SPLIT, 1.0),
       "a member's rect comes from its place in the preset")
    ok(L.rect_for({"slot": 0, "minimized": True}, "half") is None,
       "a minimised member has no rect at all")
    ok(L.rect_for({"slot": None}, "half") is None, "and neither has one without a place")
    explicit = L.rect_for({"slot": 1, "rect": [0.1, 0.2, 0.3, 0.4]}, "half")
    ok(explicit == (0.1, 0.2, 0.3, 0.4),
       "a captured rect wins over the preset — that is what «Снять с окон» stores")

    ok(L.normal_rect([0, 0, 0, 1]) is None, "a zero-width rect is not a rect")
    ok(L.normal_rect("nope") is None and L.normal_rect([1, 2]) is None,
       "and neither is junk")

    area = (100, 50, 1000, 800)
    ok(L.to_pixels((0.0, 0.0, 0.6, 1.0), area) == (100, 50, 600, 800),
       "fractions become pixels against the monitor's work area")
    back = L.to_fractions((100, 50, 600, 800), area)
    ok(abs(back[2] - 0.6) < 1e-9, "and pixels become fractions again")
    ok(L.nearest_preset([(0, 0, .5, 1), (.5, 0, .5, 1)])[0] == "half",
       "two captured windows read as «Пополам»")


def test_window_helpers():
    """Окна других программ: на не-Windows всё честно ничего не делает."""
    from app.platform import windows as W

    if not W.available():
        ok(W.list_windows() == [], "list_windows is empty where there is no user32")
        ok(W.monitors() == [] and W.work_area(0) is None, "so is the monitor list")
        ok(W.activate(1) is False and W.place(1, (0, 0, 10, 10)) is False,
           "and moving a window is a quiet no-op instead of a crash")
        ok(W.close_window(1) is False and W.minimize(1) is False,
           "the same for closing and minimising")
        ok(W.count_for({"x.exe"}) == 0, "counting windows answers zero, not None")

    ok(W.exe_names_for({"path": r"C:\Office\EXCEL.EXE"}) == {"excel.exe"},
       "a program is matched by the file name of its path")
    ok(W.exe_names_for({"path": "steam://rungameid/570",
                        "track_exe": "dota2.exe"}) == {"dota2.exe"},
       "a game started through a launcher is matched by its tracked process")
    ok(W.exe_names_for({"path": "steam://rungameid/570"}) == set(),
       "and a URL alone matches nothing")
    ok(W.windows_for(set(), snapshot=[{"exe": "a.exe"}]) == [],
       "asking about no names returns nothing")
    ok(W.windows_for({"a.exe"}, snapshot=[{"exe": "a.exe"}, {"exe": "b.exe"}])
       == [{"exe": "a.exe"}], "and a snapshot can be filtered without touching the OS")


def test_set_layout_waits_for_late_windows():
    """Раскладка набора ждёт окна, которые открываются не сразу.

    Раньше окна расставлялись один раз через пару секунд после запуска:
    тяжёлая программа к этому моменту окна ещё не показала и молча
    оставалась на месте.
    """
    try:
        from app.controllers import sets as sets_mod
    except Exception as exc:
        skip("set layout wait test", exc)
        return
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"C:/{n}.exe"})["id"] for n in ("a", "b")]
        rec = store.add_set("S", ids)
        store.update_set(rec["id"], {"layout": {"preset": "half"}})

        calls = {"n": 0}
        placed = []

        def list_windows():
            calls["n"] += 1
            wins = [{"hwnd": 1, "exe": "a.exe", "minimized": False}]
            if calls["n"] >= 3:
                wins.append({"hwnd": 2, "exe": "b.exe", "minimized": False})
            return wins

        fake = types_ns(
            available=lambda: True, work_area=lambda i=0: (0, 0, 1000, 800),
            list_windows=list_windows,
            windows_for=lambda names, snap: [w for w in snap if w["exe"] in names],
            exe_names_for=lambda app: {os.path.basename(app["path"]).lower()},
            place=lambda hwnd, rect: placed.append(hwnd) or True,
            minimize=lambda hwnd: True)
        ui = MagicMock()
        ui.store = store
        saved = (sets_mod.W, sets_mod.ARRANGE_POLL, sets_mod.ARRANGE_SETTLE)
        sets_mod.W, sets_mod.ARRANGE_POLL, sets_mod.ARRANGE_SETTLE = fake, 0.01, 0.01
        try:
            sets_mod.SetsController(ui).arrange_set(rec["id"], quiet=True, wait=2.0)
        finally:
            sets_mod.W, sets_mod.ARRANGE_POLL, sets_mod.ARRANGE_SETTLE = saved
        ok(2 in placed, "a window that appears late is still put in its place")
        ok(placed.count(1) >= 2, "and the early one is placed again once things settle")
        ok(not ui.notify.show.called, "nothing to complain about when every window showed up")


def test_console_programs_get_a_console():
    """Консольная программа запускается со своим окном консоли.

    С DETACHED_PROCESS у PowerShell, Python или .bat консоли не было вовсе:
    они работали невидимо или сразу завершались.
    """
    from app.platform import launcher as la_mod

    seen = {}

    class FakeProc:
        def wait(self):
            return 0

    def fake_popen(argv, **kw):
        seen.update(kw)
        return FakeProc()

    with tempfile.TemporaryDirectory() as d:
        exe = os.path.join(d, "pwsh.exe")
        with open(exe, "wb") as fh:
            fh.write(b"x")
        saved = la_mod.subprocess.Popen
        la_mod.subprocess.Popen = fake_popen
        try:
            res = la_mod.Launcher().launch({"id": "p", "path": exe})
        finally:
            la_mod.subprocess.Popen = saved
    ok(res.get("ok"), "the program starts")
    ok(seen.get("creationflags") == 0x10, "with CREATE_NEW_CONSOLE, not DETACHED_PROCESS")


def test_window_placement_covers_the_invisible_frame():
    """Окна набора встают вплотную: поправка на невидимую рамку Windows."""
    from app.platform import windows as W

    ok(W.frame_adjusted((0, 0, 960, 1040), (7, 0, 7, 7)) == (-7, 0, 974, 1047),
       "the window rect grows by the invisible frame so the visible part fits the slot")
    ok(W.frame_adjusted((10, 20, 30, 40), (0, 0, 0, 0)) == (10, 20, 30, 40),
       "no frame, no change")


def test_system_programs_are_launched_by_full_path():
    """`powershell` и `explorer` по имени резолвятся через PATH.

    Если раньше системного каталога в PATH стоит директория, куда пишет
    непривилегированный процесс — типовая ошибка установки инструментов
    разработчика, — подменяется исполняемый файл.
    """
    from app.platform.discovery import windows as win
    from app.platform.launcher import explorer_exe

    ps, explorer = win._powershell_exe(), explorer_exe()
    if os.name != "nt":
        ok(ps == "powershell" and explorer == "explorer",
           "вне Windows остаются имена — там этих программ всё равно нет")
        return

    ok(os.path.isabs(ps) and os.path.isfile(ps), f"powershell берётся по полному пути ({ps})")
    ok(os.path.isabs(explorer) and os.path.isfile(explorer),
       f"проводник тоже ({explorer})")
    windir = (os.environ.get("windir") or r"C:\Windows").lower()
    ok(ps.lower().startswith(windir) and explorer.lower().startswith(windir),
       "и оба лежат внутри каталога Windows, а не там, куда указал PATH")


def test_admin_argument_quoting():
    """The elevated command line is built with Windows' own quoting rules."""
    import subprocess

    from app.platform.launcher import Launcher

    built = []

    class FakeShell:
        @staticmethod
        def ShellExecuteW(_h, _verb, _path, params, _cwd, _show):
            built.append(params)
            return 42

    lch = Launcher()
    real_ctypes = sys.modules.get("ctypes")
    fake = types_ns(windll=types_ns(shell32=FakeShell()))
    sys.modules["ctypes"] = fake
    try:
        args = ["--profile", "hello world", 'we"ird', r"C:\p ath" + "\\"]
        res = lch._run_as_admin(r"C:\x\app.exe", args, r"C:\x")
        ok(res.get("ok") is True, "a successful ShellExecuteW is reported as ok")
        ok(built and built[0] == subprocess.list2cmdline(args),
           f"arguments are quoted the way subprocess quotes them ({built})")
        ok(built and '\\"' in built[0],
           "an embedded quote is escaped instead of breaking the command line")
    finally:
        if real_ctypes is None:
            sys.modules.pop("ctypes", None)
        else:
            sys.modules["ctypes"] = real_ctypes


def test_hotkeys():
    from app.core.hotkeys import (
        free_quick_slot,
        quick_accels,
        resolve_accels,
        set_accels,
        slot_target,
    )
    apps = [{"id": "a", "quick": True}, {"id": "b", "quick": False},
            {"id": "c", "quick": True}]
    accels = quick_accels(apps)
    ok(accels == {"a": "Ctrl+1", "c": "Ctrl+2"}, "pinned programs are numbered in order")
    ok(slot_target(accels, "1") == "a" and slot_target(accels, "2") == "c",
       "Ctrl+N resolves to the program its badge shows")
    ok(slot_target(accels, "9") is None, "an unassigned slot resolves to nothing")
    ok(free_quick_slot(apps) == 3, "the next free number follows the pinned ones")

    many = [{"id": str(i), "quick": True} for i in range(12)]
    ok(len(quick_accels(many)) == 9, "only nine quick slots are handed out")
    ok(free_quick_slot(many) == 0, "and none is left over")
    ok(quick_accels([{"id": "n", "quick": False}]) == {}, "unpinned programs get no number")

    # Наборы — своя строка клавиатуры, чтобы цифра на плитке всегда значила
    # ровно Ctrl+N и запускала программу, а не набор.
    sets = [{"id": "s1"}, {"id": "s2"}]
    ok(set_accels(sets) == {"s1": "Ctrl+Alt+1", "s2": "Ctrl+Alt+2"}, "sets take Ctrl+Alt+1…9")
    ok(resolve_accels(apps, sets) == (accels, set_accels(sets)),
       "one call gives both maps the window and the badges share")


def test_launcher_monitor_lifecycle():
    """stop_monitor() used to crash the monitor thread with AttributeError."""
    import threading
    import time
    import types

    from app.platform.launcher import Launcher

    fake = types.ModuleType("psutil")
    fake.process_iter = lambda attrs=None: []
    prev_mod = sys.modules.get("psutil")
    sys.modules["psutil"] = fake
    crashes = []
    prev_hook = threading.excepthook
    threading.excepthook = lambda args: crashes.append(args)
    try:
        lch = Launcher()
        ok(lch.start_monitor(interval=0.01) is True, "monitor starts when psutil is importable")
        ok(lch.start_monitor(interval=0.01) is True, "start_monitor is idempotent")
        time.sleep(0.05)
        lch.stop_monitor()
        time.sleep(0.15)
        ok(not crashes, "stopping the monitor doesn't crash its thread")
        ok(lch.start_monitor(interval=0.01) is True, "the monitor can be restarted after a stop")
        lch.stop_monitor()
        time.sleep(0.1)
        ok(not crashes, "restart + stop stays clean")
    finally:
        threading.excepthook = prev_hook
        if prev_mod is None:
            sys.modules.pop("psutil", None)
        else:
            sys.modules["psutil"] = prev_mod


def test_running_badge_clears_when_nothing_is_tracked():
    """Метка «запущено» не остаётся на программах, которых больше нет.

    Пересчёт `_name_ids` жил внутри `if tracked`, поэтому опустевший индекс —
    все программы удалены или все они URL-схемы без `track_exe` — оставлял
    прошлый результат навсегда. Заодно проверяется, что смена состава
    индекса будит монитор, а не ждёт очередного тика.
    """
    import threading
    import time
    import types

    from app.infra import procs
    from app.platform.launcher import Launcher

    running = ["chrome.exe"]
    fake = types.ModuleType("psutil")
    fake.process_iter = lambda attrs=None: [
        types.SimpleNamespace(info={"pid": i, "name": name})
        for i, name in enumerate(running, start=1)]
    prev_mod = sys.modules.get("psutil")
    sys.modules["psutil"] = fake
    prev_hook = threading.excepthook
    crashes = []
    threading.excepthook = lambda args: crashes.append(args)

    def wait_for(predicate, limit=2.0):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    lch = Launcher()
    try:
        procs._at = 0.0          # снимок процессов кэшируется на 2 секунды
        lch.set_apps([{"id": "chrome", "path": r"C:\x\chrome.exe"}])
        lch.start_monitor(interval=0.05)
        ok(wait_for(lambda: lch.running_ids() == ["chrome"]),
           f"запущенная программа отмечается ({lch.running_ids()})")

        procs._at = 0.0
        lch.set_apps([])
        ok(wait_for(lambda: lch.running_ids() == []),
           f"после опустевшей библиотеки метка снимается ({lch.running_ids()})")

        ok(not crashes, "монитор при этом не падает")
    finally:
        lch.stop_monitor()
        threading.excepthook = prev_hook
        procs._at = 0.0
        if prev_mod is None:
            sys.modules.pop("psutil", None)
        else:
            sys.modules["psutil"] = prev_mod


def test_launcher_emit():
    """Running-state changes are emitted once, and only when they change."""
    from app.platform.launcher import Launcher

    seen = []
    lch = Launcher(on_change=lambda ids: seen.append(sorted(ids)))
    with lch._lock:
        lch._name_ids = {"a"}
    lch._emit()
    lch._emit()
    ok(seen == [["a"]], "an unchanged running set doesn't re-emit")
    with lch._lock:
        lch._name_ids = {"a", "b"}
    lch._emit()
    ok(seen == [["a"], ["a", "b"]], "a changed running set emits once")


def test_launcher_index():
    from app.platform.launcher import Launcher
    lch = Launcher()
    lch.set_apps([{"id": "1", "path": r"C:\x\chrome.exe"},
                  {"id": "2", "path": "steam://rungameid/730"},
                  {"id": "3", "path": r"C:\tools\vim.bat"},
                  {"id": "4", "path": r"C:\tools\build.cmd"},
                  {"id": "5", "path": r"C:\old\legacy.com"},
                  {"id": "6", "path": r"C:\docs\notes.txt"}])
    keys = set(lch._exe_index)
    ok("chrome.exe" in keys and "vim.bat" in keys, "exe index built (Windows exe/bat)")
    ok("build.cmd" in keys and "legacy.com" in keys,
       "every extension in _EXE_EXTS is indexed, not a copy of the list")
    ok("notes.txt" not in keys, "non-executables stay out of the index")
    ok(all("steam" not in k for k in keys), "URL launchers excluded from index")

    # set_apps used to carry its own copy of the extension list.
    from app.platform import launcher as launcher_module
    launcher_module._EXE_EXTS.add(".ps1")
    try:
        lch.set_apps([{"id": "7", "path": r"C:\s\script.ps1"}])
        ok("script.ps1" in lch._exe_index, "the index follows _EXE_EXTS, not a private copy")
    finally:
        launcher_module._EXE_EXTS.discard(".ps1")

    lch.set_apps([{"id": "g", "path": "steam://rungameid/730", "track_exe": "cs2.exe"},
                  {"id": "h", "path": "C:/x/Chrome.exe", "track_exe": None}])
    idx = lch._exe_index
    ok(idx.get("cs2.exe") == {"g"}, "URL game indexed by track_exe")
    ok(idx.get("chrome.exe") == {"h"}, "file app still indexed by path basename")


def test_launch_arguments_keep_quoted_paths_intact():
    r"""Кавычки снимаются, обратная косая черта — нет.

    `shlex.split(posix=False)` кавычки не снимал: программа получала
    `"C:\Program Files\a.txt"` вместе с ними, а перед запуском от
    администратора `list2cmdline` экранировал уже закавыченный токен ещё раз.
    Простой `posix=True` не годится с другой стороны — он считает обратную
    косую черту экранированием и съедает разделители пути Windows.
    """
    import subprocess

    from app.core.text import split_args
    from app.platform.launcher import Launcher

    quoted = r'--file "C:\Program Files\a.txt"'
    ok(split_args(quoted) == ["--file", r"C:\Program Files\a.txt"],
       f"кавычки сняты, путь целый ({split_args(quoted)})")
    ok(subprocess.list2cmdline(split_args(quoted)) == r'--file "C:\Program Files\a.txt"',
       "и обратно в командную строку он собирается без второго экранирования")

    ok(split_args(r"C:\Users\me\app.exe --flag") == [r"C:\Users\me\app.exe", "--flag"],
       "незакавыченный путь Windows не теряет разделители")
    ok(split_args("--tag 'a b' --n 5") == ["--tag", "a b", "--n", "5"],
       "одинарные кавычки работают так же")
    ok(split_args("--url http://x/y#frag") == ["--url", "http://x/y#frag"],
       "решётка в середине аргумента не обрубает строку")

    lch = Launcher()
    ok(lch._as_args(quoted) == ["--file", r"C:\Program Files\a.txt"],
       "запуск разбирает строку тем же правилом")
    ok(lch._as_args('незакрытая "кавычка') == ["незакрытая", '"кавычка'],
       "явно неправильный ввод не роняет запуск")


def test_launch_options():
    from app.platform.launcher import Launcher
    lch = Launcher()
    ok(lch._as_args("--a b") == ["--a", "b"], "string args split")
    ok(lch._as_args(["--x", "y"]) == ["--x", "y"], "list args preserved")
    ok(lch._as_args(None) == [], "no args -> empty")
    with tempfile.TemporaryDirectory() as d:
        ok(lch._work_dir({"working_dir": d}, r"C:\x\app.exe") == d, "working_dir honoured")
        bad = lch._work_dir({"working_dir": "/no/such/dir"}, os.path.join(d, "app.exe"))
        ok(bad == d, "invalid working_dir falls back to exe folder")
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tf:
        exe = tf.name
    try:
        res = lch.launch({"id": "x", "path": exe, "run_as_admin": True})
        ok(res.get("ok") is False, "run_as_admin degrades gracefully off-Windows")
    finally:
        os.unlink(exe)

    # os.startfile is Windows-only. The AttributeError it raised elsewhere
    # sailed past launch()'s `except OSError` and into the Flet event handler
    # behind the click; it has to come back as a reported failure instead.
    real_startfile = getattr(os, "startfile", None)
    if real_startfile is not None:
        del os.startfile
    try:
        raised = None
        try:
            res = lch.launch({"id": "u", "path": "steam://rungameid/730"})
        except Exception as exc:
            res, raised = None, exc
        ok(raised is None, "a URL launch without os.startfile doesn't raise")
        ok(res and res.get("ok") is False and res.get("error"),
           "it reports the failure instead, with a message for the toast")
    finally:
        if real_startfile is not None:
            os.startfile = real_startfile

    # A Store app is a package id, not a file: it has to reach the shell
    # without going through the "does this path exist" check that every
    # on-disk program takes.
    opened = []
    shell_launcher = Launcher()
    shell_launcher._open_with_os = opened.append
    store = r"shell:AppsFolder\Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"
    res = shell_launcher.launch({"id": "s", "path": store})
    ok(res.get("ok") is True and opened == [store],
       "a Store app is handed to the shell verbatim")
    ok(shell_launcher.launch({"id": "m", "path": r"C:\nope\gone.exe"}).get("ok") is False,
       "while an ordinary missing file is still reported missing")


def test_running_is_tracked_by_the_real_process():
    """Приложение с известным процессом отслеживается по нему, а не по пути.

    У Discord и Slack на Squirrel путь — их общий Update.exe: стоило одному
    обновиться, «запущенными» становились все.
    """
    from app.platform import windows as W
    from app.platform.launcher import Launcher

    apps = [{"id": "d", "path": "C:/Discord/Update.exe", "track_exe": "Discord.exe"},
            {"id": "s", "path": "C:/Slack/Update.exe", "track_exe": "slack.exe"},
            {"id": "n", "path": "C:/Notepad++/notepad++.exe"}]
    launcher = Launcher()
    launcher.set_apps(apps)
    ok("update.exe" not in launcher._exe_index, "the shared Update.exe is not a marker")
    ok(launcher._exe_index.get("discord.exe") == {"d"}, "the real process is")
    ok(launcher._exe_index.get("notepad++.exe") == {"n"}, "a plain program is still found by its exe")
    ok(W.exe_names_for(apps[0]) == {"discord.exe"}, "window matching uses the same rule")


def test_process_monitor_backs_off():
    """Монитор процессов молчит без цели и растягивает интервал в трее."""
    from app.infra import procs
    from app.platform.launcher import Launcher

    calls = []
    real = procs.snapshot
    procs.snapshot = lambda max_age=2.0: (calls.append(1), {1: "tracked.exe"})[1]
    monitor = Launcher()
    try:
        monitor.start_monitor(interval=0.05, idle_interval=5.0)
        time.sleep(0.3)
        ok(not calls, "nothing tracked means the process list is never read")

        monitor.set_apps([{"id": "a", "path": "C:/tracked.exe", "track_exe": "tracked.exe"}])
        time.sleep(0.3)
        ok(bool(calls), "adding a tracked app wakes the monitor instead of waiting it out")
        ok("a" in monitor.running_ids(), "and the running app is recognised")

        monitor.set_background(True)
        time.sleep(0.1)
        idle_mark = len(calls)
        time.sleep(0.4)
        ok(len(calls) == idle_mark, "in the tray the interval stretches out")

        monitor.set_background(False)
        time.sleep(0.15)
        ok(len(calls) > idle_mark, "showing the window polls again at once")
    finally:
        monitor.stop_monitor()
        procs.snapshot = real
