"""Поиск установленного: меню «Пуск», реестр, Store, Steam, Epic, значки, сайты и папки."""
import os
import sys
import tempfile
import time

from helpers import _FakeScanUI, _sources, _texts, _ui_for, ft, ok, skip, types_ns

from app.core.store import Store
from app.ui import iconify


def test_native_registry_and_localapps_discovery():
    """Реестр и папку Programs Centurio обходит сам, без PowerShell.

    Перебор Uninstall/App Paths и подбор exe в каталоге установки перенесены
    из скрытого PowerShell-скрипта в Python (winreg + файловая система):
    перечисление установленного — recon-признак, по которому эвристики
    антивирусов придираются к процессу powershell.exe. Логика — чистая, так
    что проверяется на любой платформе, без реального реестра Windows.
    """
    from app.platform.discovery import windows as win

    with tempfile.TemporaryDirectory() as d:
        app_dir = os.path.join(d, "Cool Editor")
        os.makedirs(app_dir)
        # Крупнейший .exe — деинсталлятор; выбрать надо совпадающий по имени.
        with open(os.path.join(app_dir, "editor.exe"), "wb") as fh:
            fh.write(b"x" * 4000)
        with open(os.path.join(app_dir, "unins000.exe"), "wb") as fh:
            fh.write(b"x" * 9000)
        picked = win._best_exe(app_dir, "Cool Editor")
        ok(picked and os.path.basename(picked) == "editor.exe",
           "the exe whose name echoes the program wins over a larger unrelated one")
        ok(win._best_exe(app_dir, "Nothing Matches").endswith("unins000.exe"),
           "with no name match, the largest exe is the fallback")
        ok(win._best_exe("C:\\Program Files", "Anything") is None,
           "a root-ish directory is refused — no scanning all of Program Files")
        ok(win._best_exe(os.path.join(d, "missing"), "x") is None,
           "a directory that isn't there yields nothing, not an error")

        prev = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            # _localapps_entries смотрит в подпапку Programs.
            ok(win._localapps_entries() == [], "no Programs subfolder means nothing found")
            programs = os.path.join(d, "Programs", "My App")
            os.makedirs(programs)
            with open(os.path.join(programs, "myapp.exe"), "wb") as fh:
                fh.write(b"x" * 100)
            found = win._localapps_entries()
            ok(len(found) == 1 and found[0]["name"] == "My App"
               and found[0]["source" if "source" in found[0] else "src"] == "localapps",
               "an app under %LocalAppData%\\Programs is found and tagged localapps")
        finally:
            if prev is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = prev

    # Форма записи реестра решается без обращения к системе.
    ok(win._registry_app("", None, None) is None, "an entry without a name is dropped")
    ok(win._registry_app("Thing", "notepad", None) is None,
       "a DisplayIcon that isn't an existing .exe doesn't invent a path")
    ok(win._under_windows("C:/Windows/System32/x.exe") is True
       and win._under_windows("D:/Games/x.exe") is False,
       "system-directory exes are recognised so they can be filtered out")


def test_store_apps_are_tracked():
    """Приложение из Store видно открытым, и на его окно можно переключиться.

    Запись `shell:AppsFolder\\…` не несёт exe, а окна UWP принадлежат
    ApplicationFrameHost.exe — Centurio не знал, что такие приложения
    запущены, и не мог ни переключиться на них, ни расставить в наборе.
    """
    from app.platform import windows as W
    from app.platform.discovery import windows as win
    from app.platform.launcher import Launcher

    ok(win.store_exe("app\\Spotify.exe") == "Spotify.exe",
       "the manifest's Executable names the process, folder dropped")
    ok(win.store_exe("$targetnametoken$.exe") is None and win.store_exe("") is None
       and win.store_exe("Calc") is None, "placeholders and junk are ignored")

    saved = win.raw_windows_entries
    try:
        win.raw_windows_entries = lambda cache: ([
            {"name": "Spotify", "path": "shell:AppsFolder\\Spotify.Spotify_x!Spotify",
             "src": "store", "exe": "Spotify.exe"},
            {"name": "Calculator", "path": "shell:AppsFolder\\Microsoft.Calc_y!App",
             "src": "store", "exe": None}], "", 0)
        found = {a["name"]: a for a in win._discover_windows(None)}
    finally:
        win.raw_windows_entries = saved
    ok(found["Spotify"]["track_exe"] == "Spotify.exe", "discovery records the Store app's process")
    ok(found["Calculator"]["track_exe"] is None, "and leaves it empty when the manifest is silent")

    launcher = Launcher()
    launcher.set_apps([dict(found["Spotify"], id="s")])
    ok(launcher._exe_index.get("spotify.exe") == {"s"},
       "the process monitor now watches for it")

    classes = {1: "ApplicationFrameWindow", 2: "Windows.UI.Core.CoreWindow", 3: "Chrome_Widget"}
    pids = {1: 100, 2: 200, 3: 300}
    ok(W.hosted_pid(1, 100, classes.get, lambda h: [3, 2], pids.get) == 200,
       "a UWP frame window is credited to the app inside it, not to ApplicationFrameHost")
    ok(W.hosted_pid(1, 100, classes.get, lambda h: [], pids.get) == 100,
       "a frame with no app inside (suspended) keeps its own process")
    ok(W.hosted_pid(3, 300, classes.get, lambda h: [2], pids.get) == 300,
       "ordinary windows are left alone")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        old = store.add_app({"name": "Spotify",
                             "path": "shell:AppsFolder\\Spotify.Spotify_x!Spotify"})
        from unittest.mock import MagicMock

        from app.controllers.scan import ScanController
        host = MagicMock()
        host.store = store
        ScanController(host)._remember_discovery(list(found.values()))
        ok(store.get_app(old["id"])["track_exe"] == "Spotify.exe",
           "a Store app added earlier learns its process on the next scan")


def test_windows_discovery_script_runs():
    """Сценарий PowerShell, который ищет программы, работает на настоящем Windows.

    Ошибка в нём не роняет Centurio — поиск просто молча возвращает пустой
    список. Поэтому на Windows-машине CI сценарий запускается по-настоящему.
    """
    if os.name != "nt":
        return
    from app.platform.discovery import windows as win

    with tempfile.TemporaryDirectory() as d:
        data, stderr, code = win.raw_windows_entries(d)
    ok(code == 0 and "ParserError" not in stderr and "Exception" not in stderr,
       f"the discovery script runs cleanly (code {code}): {stderr[:500]}")
    ok(data, "and finds something in the Start menu")
    store = [x for x in data if x.get("src") == "store"]
    ok(all("exe" in x for x in store), "Store entries carry their process name field")


def test_shortcut_arguments_survive_discovery():
    """Ярлык меню «Пуск» приносит аргументы и рабочую папку, а не только exe.

    У Discord ярлык ведёт на `Update.exe --processStart Discord.exe`: без
    аргументов Update.exe ничего не запускает. Ярлыки приложений Chrome
    ведут на один chrome_proxy.exe с разными `--app-id` и по одному пути
    склеивались в одну запись.
    """
    from app.platform import discovery
    from app.platform.discovery import windows as win

    ok(win.shortcut_args('--processStart "Discord.exe"') == ["--processStart", "Discord.exe"],
       "shortcut arguments are split with quotes removed")
    ok(win.shortcut_args('--a "unclosed') == ["--a", '"unclosed'],
       "an unbalanced quote falls back to a plain split instead of failing")
    ok(win.squirrel_target(["--processStart", "Discord.exe"]) == "Discord.exe",
       "the real program behind Squirrel's Update.exe is recognised")
    ok(win.squirrel_target(["--app-id=x"]) is None, "other arguments name no program")

    with tempfile.TemporaryDirectory() as d:
        update = os.path.join(d, "Update.exe")
        proxy = os.path.join(d, "chrome_proxy.exe")
        for path in (update, proxy):
            with open(path, "wb") as fh:
                fh.write(b"x")
        menu = [
            {"name": "Discord", "path": update, "src": "startmenu",
             "args": "--processStart Discord.exe", "wd": d},
            {"name": "YouTube", "path": proxy, "src": "startmenu", "args": "--app-id=yt"},
            {"name": "Gmail", "path": proxy, "src": "startmenu", "args": "--app-id=gm"},
        ]
        class _WindowsOs:
            name = "nt"

            def __getattr__(self, attr):
                return getattr(os, attr)

        saved = (win.raw_windows_entries, win._registry_entries, win._localapps_entries,
                 win.os)
        try:
            win.raw_windows_entries = lambda cache: (menu, "", 0)
            win._registry_entries = lambda: [{"name": "Discord Inc", "path": update,
                                              "icon": None, "src": "registry"}]
            win._localapps_entries = lambda: []
            win.os = _WindowsOs()
            found = discovery._dedupe(win._discover_windows(None))
        finally:
            (win.raw_windows_entries, win._registry_entries, win._localapps_entries,
             win.os) = saved

    by_name = {a["name"]: a for a in found}
    ok(set(by_name) == {"Discord", "YouTube", "Gmail"},
       f"both web apps survive and the bare registry copy is dropped ({sorted(by_name)})")
    ok(by_name["Discord"]["args"] == ["--processStart", "Discord.exe"]
       and by_name["Discord"]["working_dir"] == d,
       "the shortcut's arguments and working folder are kept")
    ok(by_name["Discord"]["track_exe"] == "Discord.exe",
       "and the running program is tracked by its real exe")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ok(store.queue_inbox(found) == 3, "each shortcut becomes its own queue entry")
        item = next(i for i in store.state()["inbox"] if i["name"] == "Discord")
        ok(item["args"] == ["--processStart", "Discord.exe"], "and keeps its arguments there")

    # Библиотека, собранная до этого исправления: Discord без аргументов.
    from unittest.mock import MagicMock

    from app.controllers.scan import ScanController
    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        old = store.add_app({"name": "Discord", "path": by_name["Discord"]["path"]})
        ui = MagicMock()
        ui.store = store
        ScanController(ui)._remember_discovery(found)
        fixed = store.get_app(old["id"])
        ok(fixed["args"] == ["--processStart", "Discord.exe"]
           and fixed["track_exe"] == "Discord.exe",
           "the next scan gives an old bare entry its shortcut arguments back")


def test_discovery_sources():
    """Найденное помечается источником и умеет докладывать об ошибках."""
    from app.platform import discovery

    source = "\n".join(text for _label, text in _sources("platform/discovery"))
    ok("'startmenu'" in source, "the Start Menu pass tags what it finds")
    ok('"registry"' in source or "'registry'" in source,
       "and so do the uninstall and App Paths passes")
    ok('"localapps"' in source or "'localapps'" in source,
       "and a %LocalAppData%\\Programs fallback catches apps neither of those sees")
    # Реестр и папку Programs теперь обходит Python (winreg + os), а не
    # скрытый PowerShell: перебор Uninstall/App Paths — recon-признак для AV.
    ok("LOCALAPPDATA" in source, "the Programs-folder fallback scans the real folder")
    ok("HKLM:" not in discovery._WIN_PS and "HKCU:" not in discovery._WIN_PS
       and "Get-ItemProperty" not in discovery._WIN_PS,
       "the registry recon no longer runs inside PowerShell")
    ok(".EndsWith('.lnk')" in discovery._WIN_PS and ".EndsWith('.exe')" in discovery._WIN_PS,
       "Get-StartApps entries without a Store-style '!' id are resolved too, not dropped")

    from app.platform.discovery import windows as _dw
    real_run = _dw._run_powershell
    try:
        _dw._run_powershell = lambda script, timeout=60: types_ns(
            stdout='[{"name":"Visual Studio Code",'
                   '"path":"C:/Users/u/AppData/Local/Programs/Microsoft VS Code/Code.exe",'
                   '"src":"localapps"}]',
            stderr="", returncode=0)
        found = discovery._discover_windows(None)
        ok(found and found[0]["source"] == "localapps",
           "an app found only via the Programs-folder fallback keeps that source")

        _dw._run_powershell = lambda script, timeout=60: types_ns(
            stdout='[{"name":"Game Bar","path":"shell:AppsFolder\\\\X!App","src":"store",'
                   '"icon_err":"Get-AppxPackage вернул пусто"}]',
            stderr="", returncode=0)
        raw, _stderr, _code = discovery.raw_windows_entries(None)
        ok(raw[0]["icon_err"] == "Get-AppxPackage вернул пусто",
           "a Store app's icon failure reason travels through raw_windows_entries "
           "untouched, for app.diagnose to print")
    finally:
        _dw._run_powershell = real_run

    merged = discovery._dedupe([
        {"name": "A", "path": "C:/a.exe", "source": "startmenu"},
        {"name": "A", "path": "C:/a.exe", "source": "registry", "icon": "/i.png"},
    ])
    ok(len(merged) == 1, "the same program from two sources is one entry")
    ok(merged[0]["source"] == "startmenu", "the first source it was seen in wins")
    ok(merged[0]["icon"] == "/i.png", "and an icon from the second is still adopted")

    ok(not discovery._dedupe([{"name": "Centurio", "path": "C:/P/Centurio/Centurio.exe"}]),
       "Centurio does not offer its own shortcut as a program to add")

    report = {}
    discovery.discover_apps(None, report=report)
    ok("errors" in report, "a scan reports which sources failed")

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "Desktop"))
        with open(os.path.join(d, "Desktop", "Visual Studio Code.lnk"), "w") as fh:
            fh.write("x")
        pins = os.path.join(d, "Microsoft", "Internet Explorer", "Quick Launch",
                            "User Pinned", "TaskBar")
        os.makedirs(pins)
        with open(os.path.join(pins, "Telegram.lnk"), "w") as fh:
            fh.write("x")
        saved = {k: os.environ.get(k) for k in ("USERPROFILE", "APPDATA")}
        os.environ["USERPROFILE"] = d
        os.environ["APPDATA"] = d
        try:
            ok("visualstudiocode" in discovery.desktop_names(),
               "a desktop shortcut is recognised by name")
            ok("telegram" in discovery.taskbar_names(), "and so is a taskbar pin")
            picked = discovery.suggest_first_run([
                {"name": "Visual Studio Code", "path": "C:/x.exe", "source": "registry"},
                {"name": "Visual Studio Code", "path": "C:/x2.exe", "source": "startmenu"},
                {"name": "Nothing", "path": "C:/y.exe", "source": "startmenu"},
                {"name": "Steam", "path": "C:/Steam/steam.exe", "source": "startmenu"},
                {"name": "Telegram", "path": "C:/t/Telegram.exe", "source": "startmenu"},
                {"name": "Some Game", "path": "steam://rungameid/1", "source": "steam",
                 "track_exe": "Game.exe"},
            ], running={"steam.exe", "game.exe"})
            ok([(p["app"]["name"], p["hint"]) for p in picked] == [
                ("Telegram", "на панели задач"), ("Steam", "сейчас запущена"),
                ("Some Game", "сейчас запущена"), ("Visual Studio Code", "на рабочем столе")],
               f"suggestions come with evidence, strongest first ({picked})")
            ok(all(p["app"]["name"] != "Nothing" for p in picked),
               "a mere Start menu entry is no sign the program is used")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_store_icon_trim():
    """Store-иконки часто «unplated»: значок — маленький остров прозрачности
    посреди холста. Обрезка должна вернуть его к почти полному кадру."""
    from app.platform import discovery

    Image = __import__("PIL.Image", fromlist=["Image"])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "icon.png")
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        for x in range(70, 130):
            for y in range(70, 130):
                im.putpixel((x, y), (10, 200, 10, 255))
        im.save(path)

        discovery.trim_transparent_padding(path)

        with Image.open(path) as trimmed:
            tw, th = trimmed.size
            bbox = trimmed.split()[-1].getbbox()
        ok(tw < 150 and th < 150, "the padded canvas shrinks a lot")
        ok(bbox[2] - bbox[0] >= tw * 0.8 and bbox[3] - bbox[1] >= th * 0.8,
           "and the glyph now fills most of the new, tighter canvas")

        already_tight = os.path.join(d, "tight.png")
        tight = Image.new("RGBA", (64, 64), (10, 200, 10, 255))
        tight.save(already_tight)
        before = os.path.getmtime(already_tight)
        discovery.trim_transparent_padding(already_tight)
        ok(os.path.getmtime(already_tight) == before,
           "an icon that already fills its canvas is left untouched")

        blank = os.path.join(d, "blank.png")
        Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(blank)
        discovery.trim_transparent_padding(blank)  # must not raise on a fully transparent image
        ok(os.path.exists(blank), "a fully transparent icon doesn't crash the trim")


def test_backfill_icons_refresh_replaces_a_stale_icon():
    """A normal backfill only fills a gap — an app that already has *some*
    icon is left alone (see «backfill_icons fixes sub even when icon already
    present»). A forced refresh (bumped ICON_SCHEMA, after a change to how
    icons are resolved) has to be able to override that recorded icon too —
    including clearing it to nothing when re-resolving now comes up empty —
    or apps that picked up the wrong picture under old logic keep it forever."""
    from app.platform import discovery

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        stale = store.add_app({"name": "Old Cover", "path": "/x/old.exe",
                               "icon": "/fake/stale.jpg", "icon_fit": "cover"})
        real_resolve = discovery.icons.resolve_icon_for
        try:
            discovery.icons.resolve_icon_for = lambda path, cache=None: (None, "contain")
            ok(discovery.backfill_icons(store, None) is False,
               "a plain backfill still leaves an already-icon'd app untouched")
            ok(store.get_app(stale["id"])["icon"] == "/fake/stale.jpg",
               "so the stale icon survives it")

            changed = discovery.backfill_icons(store, None, refresh=True)
            ok(changed, "a forced refresh that resolves to nothing still counts as a change")
            ok(store.get_app(stale["id"])["icon"] is None,
               "and it clears the stale icon rather than leaving it in place")

            discovery.icons.resolve_icon_for = lambda path, cache=None: ("/fake/fresh.png", "contain")
            discovery.backfill_icons(store, None, refresh=True)
            ok(store.get_app(stale["id"])["icon"] == "/fake/fresh.png",
               "and a forced refresh can likewise replace one icon with a better one")
        finally:
            discovery.icons.resolve_icon_for = real_resolve


def test_cdn_circuit_breaker():
    from app.platform import discovery

    discovery.reset_cdn_state()
    ok(discovery._cdn_available() is True, "downloads start out enabled")

    calls = {"n": 0}
    original = discovery.steam_art._http_get

    def offline(url, timeout=None):
        calls["n"] += 1
        discovery._cdn_record(False)
        return None

    discovery.steam_art._http_get = offline
    try:
        with tempfile.TemporaryDirectory() as cache:
            ok(discovery._steam_cdn_art("730", cache) is None, "art lookup fails while offline")
            tripped_after = calls["n"]
            ok(tripped_after <= discovery._CDN_MAX_FAILURES,
               "the breaker trips without exhausting every host/name combination")
            ok(discovery._cdn_available() is False, "repeated network errors disable downloads")

            ok(discovery._steam_cdn_art("999", cache) is None, "further lookups still fail")
            ok(calls["n"] == tripped_after, "a tripped breaker issues no further requests")

            discovery.reset_cdn_state()
            ok(discovery._cdn_available() is True, "an explicit rescan re-enables downloads")

            # A miss (server reachable, art absent) must not be retried either.
            def not_found(url, timeout=None):
                calls["n"] += 1
                discovery._cdn_record(True)
                return None

            discovery.steam_art._http_get = not_found
            discovery._steam_cdn_art("555", cache)
            after_first = calls["n"]
            discovery._steam_cdn_art("555", cache)
            ok(calls["n"] == after_first, "a known miss is cached for the session")
    finally:
        discovery.steam_art._http_get = original
        discovery.reset_cdn_state()


def test_icons_are_extracted_without_powershell():
    """Иконка достаётся через `ctypes`, а не скрытым процессом PowerShell.

    Раньше на каждый файл поднимался PowerShell, внутри которого
    `Add-Type -TypeDefinition` компилировал C# с `DllImport("user32")`. Цена —
    0.3–1.5 с холодного старта на файл: библиотека из 50 игр без кэша значков
    давала минуту фоновой работы и 50 порождённых процессов. Репутация —
    скрытый PowerShell с P/Invoke из скомпилированного в рантайме кода это
    два самых тяжёлых признака, по которым Centurio принимают за infostealer.

    Настоящее извлечение проверяется только на Windows-раннере: там берётся
    системный exe, и результат обязан быть читаемым PNG.
    """
    from app.platform import win_icons
    from app.platform.discovery import windows as win

    with tempfile.TemporaryDirectory() as cache:
        first = win_icons.cache_path(r"C:\Apps\Thing.exe", cache)
        ok(first.endswith("_256.png"), f"имя в кэше как у прежнего PowerShell ({first})")
        ok(first == win_icons.cache_path(r"c:\apps\THING.exe", cache),
           "регистр пути не плодит второй файл — иначе накопленный кэш пропал бы")

        if not win_icons.available():
            ok(win_icons.extract_png(r"C:\Windows\System32\notepad.exe", first) is False,
               "вне Windows извлечение просто отвечает отказом")
            return

        exe = os.path.join(os.environ.get("windir", r"C:\Windows"), "explorer.exe")
        out = win_icons.cache_path(exe, cache)
        ok(win_icons.extract_png(exe, out) is True, f"иконка достаётся из {exe}")
        ok(os.path.exists(out) and os.path.getsize(out) > 0, "и сохраняется файлом")

        from PIL import Image
        with Image.open(out) as im:
            ok(im.format == "PNG" and im.size == (256, 256), f"это PNG 256×256 ({im.size})")
            ok(im.convert("RGBA").getchannel("A").getbbox() is not None,
               "и картинка не пустая — альфа-канал не весь нулевой")

        calls = []
        real_run = win._run_powershell
        win._run_powershell = lambda *a, **kw: calls.append(1)
        try:
            got = win._win_extract_one(exe, cache)
            ok(got == out, "одиночное извлечение отдаёт тот же файл")
            ok(calls == [], "и не поднимает PowerShell вовсе")
        finally:
            win._run_powershell = real_run

        ok(win_icons.extract_png(os.path.join(cache, "no-such.exe"),
                                 os.path.join(cache, "x.png")) is False,
           "несуществующий файл — отказ, а не исключение")


def test_posters_off_means_no_network():
    """Выключенные «Постеры для игр» действительно выключают походы в CDN.

    Флаг использовался ровно в двух местах, и оба — про отрисовку. Загрузка
    же шла безусловно: пользователь, выключивший постеры, продолжал ходить в
    CDN Valve, передавать туда список своих appid и занимать диск.
    """
    from app.platform import discovery

    urls = []
    original = discovery.steam_art._http_get

    def spy(url, timeout=None):
        urls.append(url)
        return None

    discovery.steam_art._http_get = spy
    discovery.reset_cdn_state()
    try:
        with tempfile.TemporaryDirectory() as cache:
            discovery.poster_for("steam://rungameid/730", cache, posters=False)
            ok(urls == [], "poster_for с выключенными постерами не ходит в сеть")

            discovery.reset_cdn_state()
            discovery.poster_for("steam://rungameid/730", cache, posters=True)
            ok(urls, "а с включёнными — ходит, то есть проверка не пустая")

            # backfill_icons читает настройку сам: его зовут из четырёх мест,
            # и забытый аргумент в любом из них вернул бы загрузку молча.
            with tempfile.TemporaryDirectory() as d:
                store = Store(os.path.join(d, "data.json"))
                store.set_setting("game_posters", False)
                store.add_app({"name": "CS2", "path": "steam://rungameid/730",
                               "category_id": "work"})
                urls.clear()
                discovery.reset_cdn_state()
                discovery.backfill_icons(store, cache)
                ok(urls == [], "и дозаполнение значков тоже молчит")

                store.set_setting("game_posters", True)
                discovery.reset_cdn_state()
                discovery.backfill_icons(store, cache, refresh=True)
                ok(urls, "включённая настройка возвращает загрузку")
    finally:
        discovery.steam_art._http_get = original
        discovery.reset_cdn_state()


def test_epic_poster_prefers_portrait_key_image():
    """Из `keyImages` каталога Epic берётся вертикальная обложка, если она есть.

    У Steam портретная обложка — отдельный, всегда вертикальный файл. У Epic
    это один из вариантов в списке `keyImages` вперемешку с горизонтальными
    баннерами витрины; неверный порядок перебора даёт растянутый постер.
    """
    from app.platform.discovery import epic_art

    wide_only = {"keyImages": [{"type": "OfferImageWide", "url": "https://x/wide.jpg"},
                               {"type": "Thumbnail", "url": "https://x/thumb.jpg"}]}
    ok(epic_art._best_key_image(wide_only) == "https://x/thumb.jpg",
       "без портретных вариантов берётся Thumbnail, а не первый попавшийся")

    with_tall = {"keyImages": [{"type": "DieselStoreFrontWide", "url": "https://x/wide.jpg"},
                               {"type": "OfferImageTall", "url": "https://x/tall.jpg"}]}
    ok(epic_art._best_key_image(with_tall) == "https://x/tall.jpg",
       "портретная OfferImageTall предпочитается широкой обложке")

    ok(epic_art._best_key_image({"keyImages": []}) is None,
       "пустой список keyImages -> нет обложки, а не исключение")
    ok(epic_art._best_key_image({}) is None, "запись без keyImages тоже не падает")


def test_epic_poster_downloads_via_catalog_api():
    """`poster_for_ids` идёт в каталог Epic за метаданными, потом — за картинкой.

    До этого коммита Epic-игры вообще не получали `poster`: `poster_for` из
    `steam_art` матчит только `steam://rungameid/...` и на URI Epic молча
    отвечает `None`. Обложки грузились только через Steam CDN.
    """
    from app.platform.discovery import epic_art

    calls = []
    catalog_json = ('{"item123": {"keyImages": ['
                    '{"type": "OfferImageWide", "url": "https://cdn.example/wide.jpg"},'
                    '{"type": "OfferImageTall", "url": "https://cdn.example/tall.jpg"}]}}')

    def fake_get(url, timeout=None, max_bytes=None):
        calls.append(url)
        if "catalog-public-service" in url:
            ok("namespace123" in url and "item123" in url,
               f"запрос каталога содержит namespace и id ({url})")
            return catalog_json.encode("utf-8")
        if url == "https://cdn.example/tall.jpg":
            return b"\xff\xd8" + b"0" * 2000  # достаточно байт, чтобы не счесть заглушкой
        raise AssertionError(f"неожиданный URL: {url}")

    original = epic_art._http_get
    epic_art._http_get = fake_get
    epic_art.reset_epic_cdn_state()
    try:
        with tempfile.TemporaryDirectory() as cache:
            out = epic_art.poster_for_ids("namespace123", "item123", cache, posters=True)
            ok(out is not None and os.path.exists(out), "обложка сохранена на диск")
            ok(out.endswith("epic_item123_portrait.jpg"), f"имя файла узнаваемо ({out})")
            with open(out, "rb") as fh:
                ok(fh.read().startswith(b"\xff\xd8"), "на диске оказались именно скачанные байты")
            ok(any("catalog-public-service" in u for u in calls), "каталог был опрошен")
            ok("https://cdn.example/tall.jpg" in calls, "скачан именно портретный вариант")

            calls.clear()
            out2 = epic_art.poster_for_ids("namespace123", "item123", cache, posters=True)
            ok(out2 == out, "повторный вызов отдаёт тот же путь")
            ok(calls == [], "а в сеть уже не ходит — обложка на диске")
    finally:
        epic_art._http_get = original
        epic_art.reset_epic_cdn_state()


def test_epic_cdn_circuit_breaker():
    """Каталог Epic и CDN Steam переключаются независимо друг от друга."""
    from app.platform import discovery
    from app.platform.discovery import epic_art

    discovery.reset_cdn_state()
    ok(epic_art._cdn_available() is True, "загрузки Epic начинаются включёнными")

    calls = {"n": 0}
    original = epic_art._http_get

    def offline(url, timeout=None, max_bytes=None):
        calls["n"] += 1
        epic_art._cdn_record(False)
        return None

    epic_art._http_get = offline
    try:
        with tempfile.TemporaryDirectory() as cache:
            # Один вызов poster_for_ids делает один запрос к каталогу (в отличие
            # от Steam, где на один appid перебираются несколько CDN-хостов) —
            # автомат срабатывает после нескольких разных игр подряд.
            for i in range(epic_art._CDN_MAX_FAILURES):
                ok(epic_art.poster_for_ids("ns", f"id-{i}", cache) is None,
                   "поиск обложки не удаётся, пока каталог недоступен")
            ok(epic_art._cdn_available() is False, "повторные ошибки сети выключают загрузки")
            ok(discovery.steam_art._cdn_available() is True,
               "а выключатель Steam при этом не тронут")

            tripped_after = calls["n"]
            epic_art.poster_for_ids("ns", "id-next", cache)
            ok(calls["n"] == tripped_after, "выключенный автомат не шлёт новых запросов")

            discovery.reset_cdn_state()
            ok(epic_art._cdn_available() is True,
               "общий сброс (`discovery.reset_cdn_state`) включает и Epic")
    finally:
        epic_art._http_get = original
        discovery.reset_cdn_state()


def test_epic_posters_off_means_no_network():
    """Выключенные «Постеры для игр» действительно не трогают сеть и для Epic."""
    from app.platform import discovery
    from app.platform.discovery import epic_art

    urls = []
    original = epic_art._http_get

    def spy(url, timeout=None, max_bytes=None):
        urls.append(url)
        return None

    epic_art._http_get = spy
    discovery.reset_cdn_state()
    try:
        with tempfile.TemporaryDirectory() as cache:
            epic_art.poster_for_ids("ns", "id", cache, posters=False)
            ok(urls == [], "выключенные постеры не ходят в сеть даже за метаданными")

            epic_art.poster_for_ids("ns", "id", cache, posters=True)
            ok(urls, "а включённые — ходят, то есть проверка не пустая")
    finally:
        epic_art._http_get = original
        discovery.reset_cdn_state()


def test_epic_poster_resolves_ids_from_manifest():
    """`poster_for(path)` находит `CatalogNamespace`/`CatalogItemId` по манифесту.

    В launch-URI Epic (`com.epicgames.launcher://apps/{AppName}...`) этих
    полей нет — в отличие от Steam, где appid прямо в `steam://rungameid/...`.
    Без этого шага `backfill_icons` не мог бы дозаполнить постер для игры,
    уже добавленной в библиотеку.
    """
    from app.platform.discovery import epic_art

    with tempfile.TemporaryDirectory() as root:
        mani = os.path.join(root, "Epic", "EpicGamesLauncher", "Data", "Manifests")
        os.makedirs(mani)
        import json as _json
        with open(os.path.join(mani, "Game.item"), "w", encoding="utf-8") as fh:
            _json.dump({"DisplayName": "Some Game", "AppName": "abc123",
                       "CatalogNamespace": "ns-xyz", "CatalogItemId": "item-xyz"}, fh)

        old_pd = os.environ.get("ProgramData")
        os.environ["ProgramData"] = root
        try:
            ns, item = epic_art._catalog_ids_for_app("abc123")
            ok(ns == "ns-xyz" and item == "item-xyz",
               f"ids найдены по совпадению AppName ({ns}, {item})")
            ok(epic_art._catalog_ids_for_app("no-such-app") == (None, None),
               "несуществующий AppName -> пусто, а не исключение")

            calls = []
            original = epic_art._http_get
            epic_art._http_get = lambda *a, **kw: (calls.append(a[0]) or None)
            epic_art.reset_epic_cdn_state()
            try:
                path = "com.epicgames.launcher://apps/abc123?action=launch&silent=true"
                with tempfile.TemporaryDirectory() as cache:
                    epic_art.poster_for(path, cache, posters=True)
                    ok(any("ns-xyz" in u and "item-xyz" in u for u in calls),
                       "poster_for(path) дошёл до каталога с правильными ids")
                    ok(epic_art.poster_for("C:/x/app.exe", cache) is None,
                       "не-Epic путь -> None, без похода в манифесты")
            finally:
                epic_art._http_get = original
                epic_art.reset_epic_cdn_state()
        finally:
            if old_pd is None:
                os.environ.pop("ProgramData", None)
            else:
                os.environ["ProgramData"] = old_pd


def test_epic_backfill_fills_missing_poster():
    """`backfill_icons` дозаполняет постер уже добавленной Epic-игре."""
    from app.platform import discovery
    from app.platform.discovery import epic_art

    with tempfile.TemporaryDirectory() as root:
        mani = os.path.join(root, "Epic", "EpicGamesLauncher", "Data", "Manifests")
        os.makedirs(mani)
        import json as _json
        with open(os.path.join(mani, "Game.item"), "w", encoding="utf-8") as fh:
            _json.dump({"DisplayName": "Some Game", "AppName": "abc123",
                       "CatalogNamespace": "ns-xyz", "CatalogItemId": "item-xyz"}, fh)

        old_pd = os.environ.get("ProgramData")
        os.environ["ProgramData"] = root
        original = epic_art._http_get

        def fake_get(url, timeout=None, max_bytes=None):
            if "catalog-public-service" in url:
                return (b'{"item-xyz": {"keyImages": '
                        b'[{"type": "OfferImageTall", "url": "https://cdn.example/tall.jpg"}]}}')
            return b"\xff\xd8" + b"0" * 2000

        epic_art._http_get = fake_get
        epic_art.reset_epic_cdn_state()
        try:
            with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cache:
                store = Store(os.path.join(d, "data.json"))
                path = "com.epicgames.launcher://apps/abc123?action=launch&silent=true"
                store.add_app({"name": "Some Game", "path": path, "category_id": "work"})
                ok(store.state()["apps"][0].get("poster") is None,
                   "изначально постера нет — ровно то, из-за чего эта правка нужна")

                changed = discovery.backfill_icons(store, cache)
                ok(changed is True, "backfill_icons сообщает об изменении")
                poster = store.state()["apps"][0].get("poster")
                ok(poster is not None and os.path.exists(poster),
                   f"после дозаполнения обложка появилась и лежит на диске ({poster})")
        finally:
            epic_art._http_get = original
            epic_art.reset_epic_cdn_state()
            if old_pd is None:
                os.environ.pop("ProgramData", None)
            else:
                os.environ["ProgramData"] = old_pd


def test_appid_for_exe_matches_installdir_boundaries():
    """`appid_for_exe` не путает `Game` с `GameExtra` по случайному префиксу.

    Наивная проверка `path.startswith(game_root)` без разделителя в конце
    считает вложенным всё, что начинается с той же строки символов — папка
    `GameExtra` тоже «начинается» с `Game`. Тест ловит именно эту ошибку
    границы, а не просто «нашёл/не нашёл».
    """
    from app.platform.discovery import steam_paths

    real_steam_roots = steam_paths._steam_roots
    try:
        with tempfile.TemporaryDirectory() as root:
            common = os.path.join(root, "steamapps", "common")
            game_exe = os.path.join(common, "Game", "game.exe")
            extra_exe = os.path.join(common, "GameExtra", "extra.exe")
            os.makedirs(os.path.dirname(game_exe))
            os.makedirs(os.path.dirname(extra_exe))
            open(game_exe, "wb").close()
            open(extra_exe, "wb").close()

            lib = os.path.join(root, "steamapps")
            with open(os.path.join(lib, "appmanifest_100.acf"), "w") as fh:
                fh.write('"AppState"{ "appid" "100" "installdir" "Game" "name" "Game" }')
            with open(os.path.join(lib, "appmanifest_200.acf"), "w") as fh:
                fh.write('"AppState"{ "appid" "200" "installdir" "GameExtra" "name" "Extra" }')
            steam_paths._steam_roots = lambda: [root]

            ok(steam_paths.appid_for_exe(game_exe) == "100", "exe в Game -> appid 100")
            ok(steam_paths.appid_for_exe(extra_exe) == "200",
               "exe в GameExtra -> appid 200, а не 100 по совпадению префикса")
            ok(steam_paths.appid_for_exe(os.path.join(common, "Unrelated", "x.exe")) is None,
               "exe вне библиотеки -> None")
            ok(steam_paths.appid_for_exe("") is None, "пустой путь -> None, без исключений")
    finally:
        steam_paths._steam_roots = real_steam_roots


def test_manual_add_redirects_steam_exe_to_launch_via_steam():
    """Ручное добавление exe из библиотеки Steam запускается потом через Steam.

    До этой правки поле «Или вставьте путь…» и кнопка «Обзор» сохраняли
    такой exe как есть, и он запускался в обход клиента Steam. Само окно
    игры открывается, но у VAC-защищённых игр (CS2 и подобных) сервер не
    видит сессии, которую Steam выдаёт только при запуске через себя, —
    матчмейкинг отвечает «не удаётся подключиться к серверу».
    """
    from app.controllers.scan import ScanController
    from app.platform.discovery import steam_paths

    real_steam_roots = steam_paths._steam_roots
    try:
        with tempfile.TemporaryDirectory() as steam_root:
            installdir = "Counter-Strike Global Offensive"
            game_dir = os.path.join(steam_root, "steamapps", "common", installdir,
                                    "game", "bin", "win64")
            os.makedirs(game_dir)
            exe = os.path.join(game_dir, "cs2.exe")
            with open(exe, "wb") as fh:
                fh.write(b"MZ")
            lib = os.path.join(steam_root, "steamapps")
            with open(os.path.join(lib, "appmanifest_730.acf"), "w") as fh:
                fh.write(f'"AppState"{{ "appid" "730" "installdir" "{installdir}" '
                        '"name" "Counter-Strike 2" }')
            steam_paths._steam_roots = lambda: [steam_root]

            with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cache:
                store = Store(os.path.join(d, "data.json"))
                ui = _FakeScanUI(store, cache)
                scan = ScanController(ui)
                scan.set_manual_path(exe)
                scan.add_manual_path()

                ok(len(scan._manual_found) == 1, "запись попала в список найденного")
                item = scan._manual_found[0]
                ok(item["path"] == "steam://rungameid/730",
                   f"путь подменён на launch-URI Steam ({item['path']})")
                ok(item["source"] == "steam", "источник помечен как steam")
                ok(item["track_exe"] == "cs2.exe",
                   "исходный exe остаётся в track_exe для отслеживания процесса")
                ok(any("Steam" in m for m in ui.notify.messages),
                   f"пользователю сказали, что это игра Steam ({ui.notify.messages})")

            # exe вне какой-либо библиотеки Steam — путь остаётся как есть.
            with tempfile.TemporaryDirectory() as other, \
                 tempfile.TemporaryDirectory() as d2, tempfile.TemporaryDirectory() as cache2:
                plain = os.path.join(other, "notepad.exe")
                with open(plain, "wb") as fh:
                    fh.write(b"MZ")
                store2 = Store(os.path.join(d2, "data.json"))
                ui2 = _FakeScanUI(store2, cache2)
                scan2 = ScanController(ui2)
                scan2.set_manual_path(plain)
                scan2.add_manual_path()
                ok(scan2._manual_found[0]["path"] == plain,
                   "обычная программа не переписывается в steam://")
                ok(scan2._manual_found[0]["source"] == "manual", "и остаётся source=manual")
    finally:
        steam_paths._steam_roots = real_steam_roots


def test_icon():
    with tempfile.TemporaryDirectory() as d:
        p = iconify.generate_icon(os.path.join(d, "icon.png"), 64)
        ok(os.path.getsize(p) > 100, "icon PNG generated")
        with open(p, "rb") as fh:
            ok(fh.read(8) == b"\x89PNG\r\n\x1a\n", "valid PNG signature")


def test_discovery():
    from app.platform import discovery
    apps = discovery.discover_apps()
    ok(isinstance(apps, list), "discover_apps returns a list")
    ok(all(("name" in a and "path" in a) for a in apps), "discovered apps have name+path")
    ok(all(a == b for a, b in zip(apps, sorted(apps, key=lambda x: x["name"].lower()), strict=True)),
       "discovered apps are sorted")
    ok(discovery._looks_like_junk("Uninstall Foo") is True, "junk filter flags uninstallers")
    ok(discovery._looks_like_junk("Google Chrome") is False, "junk filter keeps real apps")
    ok(discovery._is_windows_system("Character Map", r"C:\WINDOWS\system32\charmap.exe") is True,
       "system filter drops Windows-dir tools")
    ok(discovery._is_windows_system("Node.js", r"C:\Program Files\nodejs\node.exe") is True,
       "system filter drops runtimes like Node.js")
    ok(discovery._is_windows_system("Google Chrome", r"C:\Program Files\Google\Chrome\chrome.exe") is False,
       "system filter keeps real apps")

    # Каждая строка ниже — то, что «Найти и добавить» реально предлагал.
    # Все они проходили фильтр по названию: у записи в реестре имя честное
    # («Steam»), а мусорный на самом деле путь, так что решает именно он.
    for name, path in (
        ("Steam", r"C:\Program Files (x86)\Steam\uninstall.exe"),
        ("Rockstar Games SDK",
         r"C:\Program Files\Rockstar Games\Social Club\uninstallRGSCRedistributable.exe"),
        ("Paradox Launcher v2",
         r"C:\Users\A\AppData\Local\Package Cache\{f0c}\LauncherInstallerBundle.exe"),
        ("Python 3.14.4 (64-bit)",
         r"C:\Users\A\AppData\Local\Package Cache\{21b}\python-3.14.4-amd64.exe"),
        ("TabTip", r"C:\Program Files\Common Files\microsoft shared\ink\TabTip.exe"),
        ("wab", r"C:\Program Files\Windows Mail\wab.exe"),
        ("wabmig", r"C:\Program Files\Windows Mail\wabmig.exe"),
        ("SKYPESERVER",
         r"C:\Program Files\Microsoft Office\Root\Office16\SkypeSrv\SKYPESERVER.EXE"),
        ("MSOXMLED", r"C:\Program Files\Microsoft Office\Root\Office16\MSOXMLED.EXE"),
    ):
        ok(discovery._is_windows_system(name, path) is True,
           f"«{name}» is installer/component plumbing, not a program to offer")

    # …и ровно та же чистка не должна съесть настоящие программы, включая
    # те, что лежат в одной папке с офисным мусором.
    for name, path in (
        ("Word", r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE"),
        ("Excel", r"C:\Program Files\Microsoft Office\Root\Office16\EXCEL.EXE"),
        ("Steam", r"C:\Program Files (x86)\Steam\steam.exe"),
        ("Rockstar Games Launcher", r"C:\Program Files\Rockstar Games\Launcher\Launcher.exe"),
        ("NVIDIA App", r"C:\Program Files\NVIDIA Corporation\NVIDIA App\NVIDIA App.exe"),
        ("Telegram Desktop", r"C:\Users\A\AppData\Roaming\Telegram Desktop\Telegram.exe"),
        ("7-Zip File Manager", r"C:\Program Files\7-Zip\7zFM.exe"),
        ("Terminal", r"shell:AppsFolder\Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"),
    ):
        ok(discovery._is_windows_system(name, path) is False,
           f"«{name}» is a real program and survives the cleanup")

    ok(discovery._vdf_val('"appid" "570" "name" "Dota 2"', "appid") == "570", "vdf value parsed")
    ok(discovery._vdf_val("nothing", "name") is None, "vdf missing key -> None")
    ok("228980" in discovery._STEAM_SKIP_ID, "steam redistributables skipped")
    ic, fit = discovery.resolve_icon_for("steam://rungameid/99999999")
    ok(ic is None and fit == "contain", "resolve_icon_for: missing steam art -> None/contain")
    ok(discovery.resolve_icon_for("")[0] is None, "resolve_icon_for: empty path -> None")

    # _steam_roots is module-level state. Every stub below is restored: these
    # tests share one process with everything after them in __main__, and an
    # unrestored patch quietly makes the order of the test list significant.
    real_steam_roots = discovery.steam_paths._steam_roots
    try:
        with tempfile.TemporaryDirectory() as d:
            lib = os.path.join(d, "steamapps")
            os.makedirs(lib)
            with open(os.path.join(lib, "appmanifest_730.acf"), "w") as fh:
                fh.write('"AppState"{ "appid" "730" "name" "Counter-Strike 2" }')
            discovery.steam_paths._steam_roots = lambda: [d]
            games = discovery._steam_games(None)
            ok(games and games[0]["sub"] == "Steam", "steam games carry sub='Steam'")
            ok(games and "track_exe" in games[0], "steam games carry a track_exe field")
            ok(games and "poster" in games[0], "steam games carry a poster field")
    finally:
        discovery.steam_paths._steam_roots = real_steam_roots


    with tempfile.TemporaryDirectory() as d:
        lc = os.path.join(d, "appcache", "librarycache")
        os.makedirs(lc)
        with open(os.path.join(lc, "730_library_600x900.jpg"), "wb") as fh:
            fh.write(b"\0" * 2048)
        ok(discovery._steam_portrait(d, "730") == os.path.join(lc, "730_library_600x900.jpg"),
           "steam portrait: local library_600x900 found")
        ok(discovery._steam_portrait(d, "999") is None, "steam portrait: missing -> None")
    ok(discovery.poster_for("C:/x/app.exe") is None, "poster_for: non-steam path -> None")

    # icon vs poster: a wide capsule/header sitting in the library cache must
    # never come back as the *icon* — it belongs to poster_for() alone, and
    # icon_slot() would cover-crop it into an unrecognisable sliver.
    with tempfile.TemporaryDirectory() as d:
        lc = os.path.join(d, "appcache", "librarycache")
        os.makedirs(lc)
        with open(os.path.join(lc, "730_header.jpg"), "wb") as fh:
            fh.write(b"\0" * 2048)
        icon, fit = discovery.steam_art._steam_icon(d, "730")
        ok(icon is None and fit == "contain",
           "steam icon: capsule/header art alone does not count as an icon")

        with open(os.path.join(lc, "730_icon.jpg"), "wb") as fh:
            fh.write(b"\0" * 512)
        icon, fit = discovery.steam_art._steam_icon(d, "730")
        ok(icon == os.path.join(lc, "730_icon.jpg") and fit == "contain",
           "steam icon: the real small square icon is what's used once it exists")

    with tempfile.TemporaryDirectory() as d:
        # logo.png looked tempting (it's small and per-app) but it's the
        # wordmark meant to overlay the hero background — wide, mostly
        # transparent, illegible once shrunk to icon size. Not an icon.
        lc = os.path.join(d, "appcache", "librarycache")
        sub = os.path.join(lc, "730")
        os.makedirs(sub)
        with open(os.path.join(sub, "logo.png"), "wb") as fh:
            fh.write(b"\0" * 2048)
        icon, fit = discovery.steam_art._steam_icon(d, "730")
        ok(icon is None and fit == "contain",
           "steam icon: the hero wordmark doesn't count as an icon either")


    deduped = discovery._dedupe([{"name": "CS2", "path": "steam://rungameid/730",
                                  "sub": "Steam", "source": "steam", "track_exe": "cs2.exe",
                                  "poster": "/x/p.jpg"}])
    ok(deduped[0]["sub"] == "Steam", "_dedupe preserves sub field")
    ok(deduped[0]["track_exe"] == "cs2.exe", "_dedupe preserves track_exe field")
    ok(deduped[0]["poster"] == "/x/p.jpg", "_dedupe preserves poster field")

    with tempfile.TemporaryDirectory() as d:
        gdir = os.path.join(d, "steamapps", "common", "Portal")
        os.makedirs(gdir)
        for fn, size in [("portal.exe", 500), ("bigtool.exe", 9000),
                         ("vcredist_x64.exe", 8000), ("crashhandler.exe", 100)]:
            with open(os.path.join(gdir, fn), "wb") as fh:
                fh.write(b"\0" * size)
        ok(discovery._steam_game_exe(d, "Portal", "Portal") == "portal.exe",
           "steam exe: name-matching exe chosen over bigger unrelated exe")
    with tempfile.TemporaryDirectory() as d:
        gdir = os.path.join(d, "steamapps", "common", "Mystery")
        os.makedirs(gdir)
        for fn, size in [("game.exe", 7000), ("unins000.exe", 9000), ("tiny.exe", 10)]:
            with open(os.path.join(gdir, fn), "wb") as fh:
                fh.write(b"\0" * size)
        ok(discovery._steam_game_exe(d, "Mystery", "Mystery") == "game.exe",
           "steam exe: largest non-junk exe is the fallback")
    ok(discovery._steam_game_exe("/x", None, "n") is None, "steam exe: no installdir -> None")

    # track_exe (a bare filename, matched against running processes) and the
    # icon-extraction fallback (which needs an openable file) read the same
    # lookup — one is just the other's basename.
    with tempfile.TemporaryDirectory() as d:
        gdir = os.path.join(d, "steamapps", "common", "Portal")
        os.makedirs(gdir)
        exe_path = os.path.join(gdir, "portal.exe")
        with open(exe_path, "wb") as fh:
            fh.write(b"\0" * 500)
        full = discovery.steam_paths._steam_game_exe_full(d, "Portal", "Portal")
        ok(full == exe_path, "steam exe (full path): points at the real file, not just a name")
        ok(os.path.basename(full) == discovery._steam_game_exe(d, "Portal", "Portal"),
           "and its basename is exactly what _steam_game_exe already returned")

    # track_exe and the icon fallback deliberately want opposite exes: the
    # first wants whatever process is actually running (the big engine
    # binary, wherever it's buried); the second wants whatever is most
    # likely to carry the branded icon (a small stub right at the root).
    with tempfile.TemporaryDirectory() as d:
        gdir = os.path.join(d, "steamapps", "common", "Game")
        os.makedirs(os.path.join(gdir, "bin", "win64"))
        with open(os.path.join(gdir, "GameLauncher.exe"), "wb") as fh:
            fh.write(b"\0" * 300)
        with open(os.path.join(gdir, "bin", "win64", "Game-Win64-Shipping.exe"), "wb") as fh:
            fh.write(b"\0" * 90000)

        ok(discovery._steam_game_exe(d, "Game", "Game") == "Game-Win64-Shipping.exe",
           "steam exe (track_exe): the big engine binary wins, launcher names ruled out")

        icon_exe = discovery.steam_paths._steam_game_icon_exe(d, "Game", "Game")
        ok(icon_exe == os.path.join(gdir, "GameLauncher.exe"),
           "steam icon exe: the shallow launcher stub wins instead, and isn't excluded")

    for name, tmpl, subs in [
        ("_WIN_PS", discovery._WIN_PS, {"__DIRS__": "'C:\\x'", "__CACHE__": "'C:\\c'"}),
        ("_WIN_ICON_ONE_PS", discovery._WIN_ICON_ONE_PS, {"__CACHE__": "'C:\\c'", "__EXE__": "'C:\\a.exe'"}),
        ("_WIN_STORE_ICON_ONE_PS", discovery._WIN_STORE_ICON_ONE_PS,
         {"__CACHE__": "'C:\\c'", "__FAMILY__": "'Fam_8wek'", "__APPID__": "'App'"}),
    ]:
        s = tmpl
        for k, v in subs.items():
            s = s.replace(k, v)
        ok(s.count("{") == s.count("}"), f"{name}: braces balanced")
        ok(s.count('@"') == s.count('"@'), f"{name}: here-strings balanced")
        ok(s.count("'") % 2 == 0, f"{name}: single quotes balanced")
        remaining = [k for k in ("__DIRS__", "__CACHE__", "__EXE__", "__FAMILY__", "__APPID__")
                    if k in s]
        ok(not remaining, f"{name}: all placeholders substituted")

    for fn in ("Get-StartApps", "Save-StoreIcon", "Resolve-StoreAsset", "Add-Store",
              "Get-LogoAttr", "Get-Pkg"):
        ok(fn in discovery._WIN_PS, f"_WIN_PS defines/calls {fn}")
    # Реестр и localapps ушли из PowerShell в Python — скрипт больше не
    # перебирает Uninstall/App Paths и не подбирает exe в каталоге установки.
    ok("Best-Exe" not in discovery._WIN_PS, "_WIN_PS no longer guesses exes in install dirs")
    for fn in ("_registry_entries", "_localapps_entries", "_best_exe"):
        ok(hasattr(discovery.windows, fn), f"discovery.windows exposes native {fn}")

    # Скрытый PowerShell, внутри которого `Add-Type -TypeDefinition` компилирует
    # C# с `DllImport`, — классика offensive tooling, попадающая под AMSI, и
    # один из самых тяжёлых признаков, по которым Centurio принимают за
    # infostealer. Значки теперь достаёт `win_icons` через ctypes, и вернуться
    # к компиляции в рантайме молча уже не выйдет.
    for name, script in (("_WIN_PS", discovery._WIN_PS),
                         ("_WIN_ICON_ONE_PS", discovery._WIN_ICON_ONE_PS),
                         ("_WIN_STORE_ICON_ONE_PS", discovery._WIN_STORE_ICON_ONE_PS)):
        ok("-TypeDefinition" not in script, f"{name}: не компилирует C# в рантайме")
        ok("DllImport" not in script, f"{name}: не объявляет P/Invoke")
    ok("Save-Icon" not in discovery._WIN_PS,
       "пакетный поиск вообще не трогает значки — их достаёт Python после отсева мусора")
    ok("-AllUsers" in discovery._WIN_PS,
       "a per-user Get-AppxPackage miss gets a second, -AllUsers try")
    ok("Import-Module Appx" in discovery._WIN_PS,
       "the Appx module is loaded explicitly, in case autoloading is off")
    ok("icon_err" in discovery._WIN_PS,
       "Save-StoreIcon's failure reason travels back in the JSON itself, not stderr")

    ok(discovery.store_parts("shell:AppsFolder\\Contoso.App_8wekyb3d8bbwe!App")
       == ("Contoso.App_8wekyb3d8bbwe", "App"), "store_parts splits family and appId on '!'")
    ok(discovery.store_parts("shell:AppsFolder\\NoBang_8wekyb3d8bbwe")
       == ("NoBang_8wekyb3d8bbwe", "App"), "and defaults the appId when there's no '!' at all")
    ok(discovery.store_parts(r"C:\ordinary\path.exe") is None,
       "an ordinary file path is not a Store path")

    # raw_windows_entries is what app.diagnose uses to tell "PowerShell
    # never found this program" apart from "we found it and our own filter
    # dropped it" — discover_apps()'s filtered count alone can't say which.
    from app.platform.discovery import windows as _win_mod
    real_run = _win_mod._run_powershell
    try:
        _win_mod._run_powershell = lambda script, timeout=60: types_ns(
            stdout='[{"name":"A","path":"C:/a.exe","src":"registry"}]',
            stderr="", returncode=0)
        data, stderr, code = discovery.raw_windows_entries(None)
        ok(data == [{"name": "A", "path": "C:/a.exe", "src": "registry"}] and code == 0,
           "raw_windows_entries hands back the parsed JSON untouched by any filter")

        _win_mod._run_powershell = lambda script, timeout=60: types_ns(
            stdout="", stderr="ParserError: unexpected token", returncode=1)
        data, stderr, code = discovery.raw_windows_entries(None)
        ok(data == [] and code == 1 and "ParserError" in stderr,
           "a script-level failure comes back as an empty list plus the reason, not silence")
    finally:
        _win_mod._run_powershell = real_run

    # A Store app's icon isn't just tried once at discovery time — a later
    # rescan/backfill has to be able to retry it too, the same way an .exe's
    # icon can be. resolve_icon_for used to fall straight through to the
    # .exe branch (endswith('.exe') is False for a shell: path) and give up.
    # icons.py calls windows._win_extract_store_one directly (not through
    # this package's re-export), so that's what has to be patched.
    from app.platform.discovery import windows as _win_mod
    real_extract, real_os_name = _win_mod._win_extract_store_one, os.name
    calls = []
    try:
        os.name = "nt"
        _win_mod._win_extract_store_one = (
            lambda path, cache: calls.append((path, cache)) or "/cache/store.png")
        icon, fit = discovery.resolve_icon_for(
            "shell:AppsFolder\\Contoso.App_8wekyb3d8bbwe!App", "/cache")
        ok(icon == "/cache/store.png" and fit == "contain",
           "resolve_icon_for routes a Store path to the Store retry")
        ok(calls == [("shell:AppsFolder\\Contoso.App_8wekyb3d8bbwe!App", "/cache")],
           "with the path and cache dir passed through untouched")
    finally:
        _win_mod._win_extract_store_one, os.name = real_extract, real_os_name

    # A Steam game whose library cache has no small icon.jpg (and no logo)
    # falls back to pulling one straight out of the game's own exe, the same
    # way a plain .exe gets its icon — rather than staying empty forever.
    real_icon_exe_for, real_extract_one, real_os_name = (
        discovery.steam_paths.steam_icon_exe_for, _win_mod._win_extract_one, os.name)
    calls = []
    with tempfile.TemporaryDirectory() as d:
        fake_exe = os.path.join(d, "game.exe")
        with open(fake_exe, "wb") as fh:
            fh.write(b"\0" * 10)
        try:
            os.name = "nt"
            discovery.steam_paths.steam_icon_exe_for = lambda path: fake_exe
            _win_mod._win_extract_one = (
                lambda path, cache: calls.append((path, cache)) or "/cache/game.png")
            icon, fit = discovery.resolve_icon_for("steam://rungameid/1604270", "/cache")
            ok(icon == "/cache/game.png" and fit == "contain",
               "resolve_icon_for falls back to the game's own exe icon")
            ok(calls == [(fake_exe, "/cache")],
               "extracting from the exe that steam_icon_exe_for resolved")
        finally:
            (discovery.steam_paths.steam_icon_exe_for, _win_mod._win_extract_one,
             os.name) = real_icon_exe_for, real_extract_one, real_os_name

    # 32-bit builds get silently handed the 32-bit PowerShell, whose HKLM
    # queries are then themselves registry-redirected — a native 64-bit-only
    # install (a machine-wide VS Code, say) never shows up even though every
    # path in the script looks like it should be the 64-bit view.
    real_maxsize, real_name, real_isfile = sys.maxsize, os.name, os.path.isfile
    try:
        os.name = "nt"
        sys.maxsize = 2**31 - 1
        os.path.isfile = lambda p: False
        ok(discovery._powershell_exe() == "powershell",
           "32-bit process, no Sysnative escape hatch -> falls back rather than failing")
        os.path.isfile = lambda p: "sysnative" in p.lower()
        ok("sysnative" in discovery._powershell_exe().lower(),
           "32-bit process with Sysnative available -> reaches the real 64-bit PowerShell")
        sys.maxsize = 2**63 - 1
        ok(discovery._powershell_exe() == "powershell",
           "a 64-bit process already sees the real registry, no Sysnative detour needed")
    finally:
        sys.maxsize, os.name, os.path.isfile = real_maxsize, real_name, real_isfile

    store2 = Store(os.path.join(tempfile.mkdtemp(), "d.json"))
    a = store2.add_app({"name": "CS2", "path": "steam://rungameid/730", "icon": "/fake/cover.jpg"})
    ok(not a.get("sub"), "precondition: no sub yet")
    try:
        discovery.steam_paths._steam_roots = lambda: []
        changed = discovery.backfill_icons(store2, None)
        ok(changed and store2.get_app(a["id"])["sub"] == "Steam",
           "backfill_icons fixes sub even when icon already present")
    finally:
        discovery.steam_paths._steam_roots = real_steam_roots
    ok(discovery.steam_paths._steam_roots is real_steam_roots,
       "the module-level Steam-root lookup is left as this test found it")


def test_steam_exe_lookup_is_cached():
    """Папка игры обходится один раз, дальше берётся из кэша."""
    from app.platform import discovery

    with tempfile.TemporaryDirectory() as d:
        lib = os.path.join(d, "lib")
        root = os.path.join(lib, "steamapps", "common", "MyGame")
        os.makedirs(root)
        with open(os.path.join(root, "MyGame.exe"), "wb") as fh:
            fh.write(b"x" * 5000)
        cache = os.path.join(d, "icons")
        os.makedirs(cache)

        walks = []
        real_walk = discovery.os.walk

        def counting_walk(*a, **kw):
            walks.append(1)
            return real_walk(*a, **kw)

        discovery.os.walk = counting_walk
        try:
            first = discovery._steam_game_exe(lib, "MyGame", "My Game", cache, "12345")
            walked = len(walks)
            second = discovery._steam_game_exe(lib, "MyGame", "My Game", cache, "12345")
            ok(first == "MyGame.exe", "the game executable is found by walking once")
            ok(second == first, "the cached answer matches")
            ok(len(walks) == walked, "and the second lookup does not walk the folder")

            discovery.reset_steam_exe_cache(cache)
            discovery._steam_game_exe(lib, "MyGame", "My Game", cache, "12345")
            ok(len(walks) > walked, "a forced rescan walks again")
        finally:
            discovery.os.walk = real_walk


def test_icon_cache_pruning():
    """Осиротевшие файлы кэша удаляются, нужные и свежие — нет."""
    from app.platform import discovery

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        cache = os.path.join(d, "icons")
        os.makedirs(cache)
        used = os.path.join(cache, "used.png")
        orphan = os.path.join(cache, "orphan.png")
        fresh = os.path.join(cache, "fresh.png")
        for path in (used, orphan, fresh):
            with open(path, "wb") as fh:
                fh.write(b"x")
        old = time.time() - 30 * 86400
        os.utime(used, (old, old))
        os.utime(orphan, (old, old))
        store.add_app({"name": "A", "path": "/bin/a", "icon": used})

        removed = discovery.prune_icon_cache(store, cache)
        ok(os.path.exists(used), "a file an app still points at survives")
        ok(not os.path.exists(orphan), "an old unreferenced file is removed")
        ok(os.path.exists(fresh), "a recent file is kept — it may belong to a pending add")
        ok(removed == 1, "the removal count is reported")


def test_web_address_parsing():
    from app.core.text import web_address, web_name

    ok(web_address("youtube.com") == "https://youtube.com", "a bare domain becomes https")
    ok(web_address("https://github.com/x") == "https://github.com/x", "a full URL stays as is")
    ok(web_address("www.google.ru/search?q=1") == "https://www.google.ru/search?q=1",
       "with a path and a query too")
    ok(web_address("кц.рф") == "https://кц.рф", "and a Cyrillic domain")
    for junk in ("notes.txt", "app.exe", "C:\\x\\y", "hello", "", ".git", "localhost:3000"):
        ok(web_address(junk) is None, f"{junk!r} is not taken for a website")
    ok(web_name("https://www.YouTube.com/watch?v=1") == "youtube.com",
       "a site is named after its host, without www")
    ok(web_name("http://localhost:8080/a") == "localhost", "and without the port")


def test_sites_folders_documents():
    """В библиотеке и в наборах живут не только программы."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("sites, folders and documents test", exc)
        return
    from app.controllers import sets as sets_mod
    from app.controllers import targets
    from app.platform import windows as W

    with tempfile.TemporaryDirectory() as d:
        folder = os.path.join(d, "Проекты")
        os.makedirs(folder)
        doc = os.path.join(d, "Отчёт.docx")
        exe = os.path.join(d, "tool.exe")
        for path in (doc, exe):
            with open(path, "w") as fh:
                fh.write("x")

        item, _ = targets.describe(folder, None)
        ok(item["kind"] == "folder" and item["name"] == "Проекты", "a folder is a folder")
        item, _ = targets.describe(f'"{doc}"', None)
        ok(item["kind"] == "file" and item["name"] == "Отчёт", "a document is a document")
        item, _ = targets.describe(exe, None)
        ok(not item.get("kind") and item["name"] == "Tool", "a program stays a program")
        item, _ = targets.describe("youtube.com", None)
        ok(item["kind"] == "web" and item["path"] == "https://youtube.com", "a site is a site")
        item, error = targets.describe(os.path.join(d, "missing.exe"), None)
        ok(item is None and error, "a path that isn't there is refused, with a reason")

        store = Store(os.path.join(d, "data.json"))
        prog = store.add_app({"name": "Editor", "path": exe, "category_id": "work"})
        ui, _ = _ui_for(store)

        ui.open_add()
        for raw in (folder, doc, "github.com"):
            ui.scan.add_manual_path(raw)
        manual = [r for g in ui.scan.found_groups() if g["source"] == "manual" for r in g["rows"]]
        ok(sorted(r["item"]["kind"] for r in manual) == ["file", "folder", "web"],
           "the Add screen takes a folder, a document and a site")
        ui.scan.commit_add()
        kinds = {a["name"]: a["kind"] for a in store.state()["apps"]}
        ok(kinds == {"Editor": "", "Проекты": "folder", "Отчёт": "file", "github.com": "web"},
           f"and they land in the library knowing what they are ({kinds})")

        site = next(a for a in store.state()["apps"] if a["kind"] == "web")
        ui.view.inspector = site["id"]
        shown = _texts(ui.inspector_panel.build_inspector())
        ok("Открыть" in shown and "Параметры запуска" not in shown,
           "a site is opened, and has no launch parameters to tune")

        report = next(a for a in store.state()["apps"] if a["kind"] == "file")
        ui.set_ops.make_set([prog["id"], report["id"]])
        set_id = store.state()["sets"][0]["id"]
        ok(store.get_set(set_id)["items"][1]["slot"] is None,
           "a document in a new set gets no window place either")
        before = len(store.state()["apps"])
        ui.set_ops.add_target(set_id, "https://mail.example.com/inbox")
        rec = store.get_set(set_id)
        mail = next(a for a in store.state()["apps"] if a["path"].startswith("https://mail"))
        ok(len(store.state()["apps"]) == before + 1 and mail["id"] in rec["apps"],
           "a site typed into a set joins the set and the library")
        entry = next(i for i in rec["items"] if i["app_id"] == mail["id"])
        ok(entry["slot"] is None, "and takes no place in the window layout")
        ok("сайт · окно не расставляется" in _texts(ft.Column(ui.content_col.controls)),
           "which the set screen says plainly")
        ui.set_ops.add_target(set_id, folder)
        ok(len(store.state()["apps"]) == before + 1,
           "a folder already in the library is reused, not duplicated")
        ui.set_ops.add_target(set_id, "news.example.org")
        ui.toast.fire_action()
        ok(len(store.state()["apps"]) == before + 1
           and not any("news" in a["path"] for a in store.state()["apps"]),
           "«Вернуть» takes a site added through a set out of the library as well")

        only_web = store.add_set("Сайты", [mail["id"], site["id"]])
        saved = (W.available, W.work_area, W.list_windows)
        W.available = lambda: True
        W.work_area = lambda index=0: (0, 0, 1000, 800)
        W.list_windows = lambda: []
        old_wait = sets_mod.ARRANGE_WAIT
        try:
            started = time.monotonic()
            ui.set_ops.arrange_set(only_web["id"], quiet=True, wait=5)
            ok(time.monotonic() - started < 2,
               "arranging does not wait for windows a site or folder will never have")
            ok("Не дождался" not in (ui.toast.text.value or ""), "nor complains about them")
        finally:
            W.available, W.work_area, W.list_windows = saved
            sets_mod.ARRANGE_WAIT = old_wait
