"""Экраны: наборы, добавление, разбор, настройки, первый запуск, категории."""
import os
import tempfile
import time
from pathlib import Path

from helpers import (
    _find_all,
    _find_control,
    _key,
    _menu_labels,
    _settle_threads,
    _texts,
    _ui_for,
    ft,
    ok,
    skip,
    types_ns,
)

from app.core.store import Store
from app.ui import colors as C
from app.ui import iconify


def test_ui_reports_a_write_error_that_predates_it():
    """Ошибка первой записи не теряется из-за того, что интерфейса ещё нет.

    `Store.__init__` может сохранить файл сам (миграция `ui_defaults`), а
    `on_error` назначается только в `CenturioUI.mount`. Раньше такая ошибка
    не доходила до пользователя вообще.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI early write-error test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.write_error = "No space left on device"
        ui, _ = _ui_for(store)

        ok(ui.toast.icon.color == C.DANGER, "ошибка записи до старта интерфейса показывается")
        ok("No space left on device" in ui.toast.text.value,
           f"с текстом ошибки ОС ({ui.toast.text.value})")


def test_ui_inbox_badge_and_triage():
    """Разбор: значок со счётчиком, очередь по одной, четыре клавиши."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI triage test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        # A fresh library starts with one catch-all category — anything more
        # specific ("Творчество" for OBS below) is the user's own doing, so
        # add it here to exercise the suggestion actually picking it by name.
        creative_id = store.add_category("Творчество")["id"]
        ui, _ = _ui_for(store)

        ok(not any("12" in t for t in _texts(ui.rail_container)),
           "an empty queue shows no badge at all")

        store.queue_inbox([
            {"name": "OBS Studio", "path": "C:/obs.exe", "source": "startmenu"},
            {"name": "Krita", "path": "C:/krita.exe", "source": "startmenu"},
        ])
        ui.refresh()
        ok("2" in _texts(ui.rail_container), "the badge counts what is waiting")

        ui.open_triage()
        shown = _texts(ft.Column(ui.content_col.controls)) if False else _texts(
            ui.content_col.controls[0])
        ok("Новые программы" in shown,
           "the queue is a screen inside the window, named for what is on it")
        ok("OBS Studio" in shown, "showing one program at a time")
        ok("Творчество" in shown, "with the category it looks like")
        ok("похоже" not in shown, "the pure «suggested» label is a hint — stays hidden")

        ui.keymap.handle_key(_key("1"))
        names = [a["name"] for a in store.state()["apps"]]
        ok(names == ["OBS Studio"], "1 puts it in the first offered category")
        ok(store.get_app(store.state()["apps"][0]["id"])["category_id"] == creative_id,
           "the one that was suggested")
        ok(len(store.state()["inbox"]) == 1, "and the queue moves on")

        ui.toast.fire_action()
        ok(len(store.state()["inbox"]) == 2, "«Вернуть» puts it back in the queue")
        ok(not store.state()["apps"], "and takes it out of the library")

        first = ui.inbox()[0]["name"]
        ui.keymap.handle_key(_key("Arrow Right"))
        ok(ui.inbox()[0]["name"] != first, "→ skips to the next one")

        ui.keymap.handle_key(_key("Delete"))
        ok(len(store.state()["inbox"]) == 1, "Del drops it from the queue")
        ui.toast.fire_action()
        ok(len(store.state()["inbox"]) == 2, "and that is undoable as well")

        ui.keymap.handle_key(_key("Enter"))
        ok(len(store.state()["apps"]) == 1, "Enter takes the suggestion")

        ui.triage.triage_defer_all()
        ok(not store.state()["inbox"], "«Отложить всё» empties the queue")
        ok(ui.view.screen == "grid", "and goes back to the library")
        ui.toast.fire_action()
        ok(len(store.state()["inbox"]) == 1, "undo brings the queue back")

        store.clear_inbox()
        ui.open_triage()
        ok("Всё разложено" in _texts(ui.content_col.controls[0]),
           "an empty queue has its own finished screen")

        # Все категории на выбор, цифрами 1–9 первые девять, остальные — «Ещё…».
        for n in range(11):
            store.add_category(f"Кат {n}")
        store.queue_inbox([{"name": "Blender", "path": "C:/blender.exe",
                            "source": "startmenu"}])
        ui.open_triage()
        shown = _texts(ui.content_col.controls[0])
        cats = len(store.state()["categories"])
        ok(cats > 9 and "Ещё…" in shown, "categories past the ninth sit behind «Ещё…»")
        ok("9" in shown and "10" not in shown, "and the digits stop at nine")
        ui.keymap.handle_key(_key("9"))
        ok(len(ui.inbox()) == 0, "the ninth one is a key away")

        # Уведомление «Посмотреть» не висит на самом экране новых программ.
        store.queue_inbox([{"name": "Krita", "path": "C:/krita2.exe"}])
        ui.back_to_grid()
        ui.notify.show("Нашлись новые программы: 1", icon="inbox",
                       action=ui.open_triage, action_label="Посмотреть")
        ok(ui.toast.control.visible, "the news shows on the library")
        ui.open_triage()
        ok("Нашлись новые программы: 1" not in _texts(ui.toast.control),
           "and goes away once the person is on the screen it pointed to")


def test_ui_sets():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI sets test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("VS Code", "Notion")]
        ui, page = _ui_for(store)

        ui.set_ops.make_set(ids)
        rec = store.state()["sets"][0]
        ok(rec["name"] == "VS Code и Notion", "a set is named after what is in it")
        ok(rec["quick"] is True, "and lands in the quick-launch strip")
        ok(ui.view.active_set == rec["id"], "and opens its own screen straight away")

        screen = _texts(ft.Column(ui.content_col.controls))
        for label in ("РАСКЛАДКА", "ПОРЯДОК ЗАПУСКА", "Запустить набор",
                      "Запомнить, как стоят окна", "60 / 40", "Пауза между запусками"):
            ok(label in screen, f"the set screen carries «{label}»")
        ok("слева · 60%" in screen, "and says where each program's window goes")
        ok("Снять с текущих окон" not in screen,
           "«снять» read as «remove» — the button says what it does now")

        ui.view.close_set()
        ui.refresh()
        side = _texts(ui.sidebar_container)
        ok("VS Code и Notion" in side, "the sidebar lists the set")
        ok("2 программы · раскладка" not in side,
           "the pure item-count/layout subtitle is a hint — stays hidden")

        # Набор запускается в своём потоке — пауза между программами не должна
        # морозить окно. Здесь она обнулена, чтобы тест не ждал её вживую,
        # как и ожидание окон для раскладки: на windows-раннере их не будет.
        from app.controllers import sets as sets_mod
        saved_wait, sets_mod.ARRANGE_WAIT = sets_mod.ARRANGE_WAIT, 0.0
        store.update_set(rec["id"], {"delay_seconds": 0})
        ui.launcher.launch.return_value = {"ok": True, "running": True}
        ui.launcher.running_ids.return_value = ids
        ui.launcher.is_running.return_value = False
        before = set(__import__("threading").enumerate())
        ui.set_ops.launch_set(rec["id"])
        ok(_settle_threads(before), "running a set finishes off the UI thread")
        ok(ui.launcher.launch.call_count == 2, "having started everything in it")

        # Уже открытая программа второй раз не запускается — набор только
        # добавляет недостающее.
        ui.launcher.launch.reset_mock()
        ui.launcher.is_running.side_effect = lambda app_id: app_id == ids[0]
        before = set(__import__("threading").enumerate())
        ui.set_ops.launch_set(rec["id"])
        ok(_settle_threads(before), "the second run finishes too")
        ok([c.args[0]["id"] for c in ui.launcher.launch.call_args_list] == [ids[1]],
           "a program that is already open is not started a second time")
        ok("уже были открыты" in ui.toast.text.value, "and the toast says which were open")
        ui.launcher.is_running.side_effect = None

        store.update_set(rec["id"], {"delay_seconds": 0.2})
        ui.launcher.launch.reset_mock()
        before = set(__import__("threading").enumerate())
        started_at = time.time()
        ui.set_ops.launch_set(rec["id"])
        ok(time.time() - started_at < 0.2, "the call itself returns at once")
        ok(_settle_threads(before, timeout=6), "and the run finishes on its own")
        ok(time.time() - started_at >= 0.2,
           "having actually waited the pause between the two programs")
        sets_mod.ARRANGE_WAIT = saved_wait

        third = store.add_app({"name": "Figma", "path": "/x/f", "category_id": "work"})["id"]
        ui.set_ops.add_to_set(rec["id"], [third])
        ok(len(store.get_set(rec["id"])["apps"]) == 3, "a program can be added to a set")
        ok(store.get_set(rec["id"])["items"][2]["slot"] == 2,
           "and takes the first free place in the layout")
        ui.toast.fire_action()
        ok(len(store.get_set(rec["id"])["apps"]) == 2, "and that is undoable")

        ui.set_ops.set_item_minimized(rec["id"], ids[1], True)
        entry = store.get_set(rec["id"])["items"][1]
        ok(entry["minimized"] is True and entry["slot"] is None,
           "a member can start minimised, and then it has no place")
        ui._open_set(rec["id"])
        board = _texts(ft.Column(ui.content_col.controls))
        ok("БЕЗ МЕСТА" in board and "свёрнутым" in board,
           "which the screen says out loud, under the layout — not only in the list")

        # Из строки «без места» программу тащат на пустое место схемы.
        from app.ui.screens import sets as set_screen
        set_screen._drop_on_slot(ui, store.get_set(rec["id"]), 1,
                                 types_ns(src=types_ns(data=ids[1])))
        entry = store.get_set(rec["id"])["items"][1]
        ok(entry["slot"] == 1 and not entry["minimized"],
           "dropping it on a free place of the layout gives the window that place")

        ui.set_ops.move_set_item(rec["id"], ids[1], -1)
        ok(store.get_set(rec["id"])["apps"][0] == ids[1],
           "the launch order can be rearranged")

        # Ручка drag_indicator на строке — настоящая: строку тащат на другую.
        dragged = types_ns(data=ids[0])
        ui.chrome.drop_set_item(rec["id"], ids[1], types_ns(src=dragged), ft.Container())
        ok(store.get_set(rec["id"])["apps"] == [ids[0], ids[1]],
           "dropping one row on another moves it in front of it")

        ui.set_ops.remove_from_set(rec["id"], ids[1])
        ok(store.get_set(rec["id"])["apps"] == [ids[0]], "a member can be removed")
        ui.toast.fire_action()
        ok(len(store.get_set(rec["id"])["apps"]) == 2, "and put back")

        ui.set_ops.remove_set(rec["id"])
        ok(not store.state()["sets"], "a set can be removed")
        ui.toast.fire_action()
        ok(len(store.state()["sets"]) == 1, "and restored")


def test_ui_add_screen():
    """Найденное — группами по категории, новое отмечено, путь вставляется в то же поле."""
    try:
        from app.platform import discovery
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI add-screen test", exc)
        return

    import threading as _threading

    from app.core.text import launch_key

    found = [
        {"name": "Elden Ring", "path": "steam://rungameid/1", "source": "steam"},
        {"name": "OBS Studio", "path": "C:/pf/obs64.exe", "source": "startmenu"},
        {"name": "Notion", "path": "/x/notion.exe", "source": "registry"},
    ]
    real_discover = discovery.discover_apps
    real_backfill = discovery.backfill_icons
    before = set(_threading.enumerate())
    try:
        discovery.discover_apps = (
            lambda icon_cache=None, on_progress=None, report=None, posters=True: list(found))
        discovery.backfill_icons = lambda *a, **kw: False
        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "data.json"))
            games_id = store.add_category("Игры")["id"]
            store.add_app({"name": "Notion", "path": "/x/notion.exe", "category_id": "work"})
            ui, _ = _ui_for(store)

            ui.open_add()
            ok(_settle_threads(before), "the scan thread finishes")
            ui.refresh()
            ok(ui.view.screen == "add", "«Найти и добавить» is a screen, not a dialog")
            ok(not ui.toolbar_holder.visible, "which takes over the toolbar's space")

            # Группы — по категории, куда программа ляжет, а не по источнику:
            # человеку всё равно, Steam это или реестр.
            groups = ui.scan.found_groups()
            ok([g["label"] for g in groups] == ["Новая", "Игры"],
               "results are grouped by the category they will land in")
            rows = {r["name"]: r for g in groups for r in g["rows"]}
            ok(rows["Elden Ring"]["source_label"] == "Steam",
               "the source is still there, as a small caption on the row")
            ok(all(r["is_new"] for g in groups for r in g["rows"]),
               "«Только новые» is on by default")
            ok(ui.view.add_sel == {rows["Elden Ring"]["key"], rows["OBS Studio"]["key"]},
               "everything new is ticked from the start — unticking one beats ticking seven")
            ok("Отмечено 2" in _texts(ft.Column(ui.content_col.controls)),
               "and the footer counts it")

            ui.scan.toggle_add_row(rows["OBS Studio"])
            ok(rows["OBS Studio"]["key"] not in ui.view.add_sel,
               "a tick taken off stays off after the screen is redrawn")

            # Пересборка экрана не должна пересоздавать поле поиска и
            # список найденного — иначе фокус слетает на каждую букву,
            # а прокрутка — на каждый клик по чекбоксу.
            field = ui._add_ui["input_field"]
            rows_col = ui._add_ui["rows_col"]
            ui.scan.set_add_input("o")
            ok(ui.view.add_query == "o" and not ui.view.manual_path,
               "a name typed in the one field filters what was found")
            ok(ui._add_ui["input_field"] is field,
               "typing keeps the very same TextField — it never loses focus")
            ok(ui._add_ui["rows_col"] is rows_col,
               "the scrollable results column is the same object too — scroll position holds")
            ui.scan.set_add_input(r"C:\Tools\thing.exe")
            ok(ui.view.manual_path and not ui.view.add_query,
               "a path in the same field is not used as a filter")
            ok("Добавить в список" in _texts(ui._add_ui["input_box"]),
               "but offered for adding with a button right in the field")
            ui.scan.set_add_input("")

            ui.scan.toggle_only_new()
            ok(ui._add_ui["input_field"] is field and ui._add_ui["rows_col"] is rows_col,
               "toggling «Только новые» reuses them as well")
            names = [r["name"] for g in ui.scan.found_groups() for r in g["rows"]]
            ok("Notion" in names, "turning it off shows what is already there")

            rows = {r["name"]: r for g in ui.scan.found_groups() for r in g["rows"]}
            ok(ui.scan.add_category_for(rows["Elden Ring"]) == games_id,
               "a Steam game is proposed for «Игры»")
            ui.scan.cycle_add_category(rows["Elden Ring"])
            ok(ui.scan.add_category_for(rows["Elden Ring"]) != games_id,
               "and the proposal can be overridden in the row")

            ticked = set(ui.view.add_sel)
            ui.scan.toggle_add_row(rows["Notion"])
            ok(ui.view.add_sel == ticked, "an app already in the library can't be ticked")

            # Путь — вторая дорога в тот же список.
            fake_exe = os.path.join(d, "MyApp.exe")
            with open(fake_exe, "w") as fh:
                fh.write("x")
            ui.scan.submit_add_input(fake_exe)
            manual = ui.scan.found_groups()[0]
            ok(manual["source"] == "manual" and manual["label"] == "Добавлено вами"
               and manual["rows"][0]["name"] == "MyApp",
               "a pasted path shows up first, in its own group")
            ok(fake_exe.lower() in ui.view.add_sel, "already ticked, since it was asked for")

            ui.scan.add_manual_path("/no/such/file.exe")
            ok(ui.toast.icon.color == C.DANGER, "a path that isn't there is refused")

            ui.view.add_sel = {launch_key(found[0])}
            ui.scan.defer_add()
            ok(len(store.state()["inbox"]) == 1, "«Решу позже» queues instead of adding")
            ok(len(store.state()["apps"]) == 1, "and nothing new landed in the library")
            store.clear_inbox()

            ui.open_add()
            ui.view.add_sel = {launch_key(found[0])}
            ui.scan.commit_add()
            ok(_settle_threads(before), "the post-add icon pass finishes")
            ok("Elden Ring" in [a["name"] for a in store.state()["apps"]],
               "committing adds the ticked programs")
            ok(ui.view.screen == "grid", "and goes back to the library")
            ui.toast.fire_action()
            ok("Elden Ring" not in [a["name"] for a in store.state()["apps"]],
               "«Вернуть» takes them out again")
    finally:
        discovery.discover_apps = real_discover
        discovery.backfill_icons = real_backfill
        _settle_threads(before)


def test_ui_scanning_is_just_a_spinner():
    """05: кружок и слово, без процентов и имён источников."""
    try:
        from app.platform import discovery
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI scanning test", exc)
        return

    import threading as _threading

    real_discover = discovery.discover_apps
    before = set(_threading.enumerate())
    gate = _threading.Event()
    try:
        def slow(icon_cache=None, on_progress=None, report=None, posters=True):
            gate.wait(3)
            return []
        discovery.discover_apps = slow
        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "data.json"))
            ui, _ = _ui_for(store)
            ui.open_add()

            deadline = time.time() + 3
            while not ui.scan.scanning() and time.time() < deadline:
                time.sleep(0.01)
            ui.refresh()
            shown = _texts(ui.content_col.controls[0])
            ok("Смотрю, что установлено" in shown, "the scan says only that it is scanning")
            ok(not any("%" in t for t in shown), "no percentage")
            ok(not any(t.isdigit() for t in shown), "no counter of what was found")
            ok(not any("Steam" in t for t in shown), "and no source name")

            gate.set()
            ok(_settle_threads(before), "the scan finishes")
    finally:
        gate.set()
        discovery.discover_apps = real_discover
        _settle_threads(before)


def test_ui_category_popover():
    """08: палитра, HEX, два ползунка и своя картинка вместо RGB-ползунков."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI category popover test", exc)
        return

    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, page = _ui_for(store)
        cat_id = store.state()["categories"][0]["id"]

        ui._open_popover(cat_id)
        ok(ui.popover_layer.visible, "the popover opens next to the rail")
        ok(not page.opened, "and it is not a dialog")
        shown = _texts(ui.popover_layer.content)
        ok("ЦВЕТ" in shown and "ИКОНКА" in shown, "it has the colour and icon groups")
        ok("Своя картинка" in shown, "and the custom-image row")
        ok("Удалить категорию" in shown, "and deletion, without a second dialog")

        sliders = _find_all(ui.popover_layer.content, lambda c: isinstance(c, ft.Slider))
        ok(len(sliders) == 2, f"two sliders, not three RGB ones ({len(sliders)})")
        ok(any(s.max == 359 for s in sliders), "one of them is the hue")

        ui.set_category_color(cat_id, "#3ecfaf")
        ok(store.state()["categories"][0]["color"] == "#3ecfaf", "a swatch writes through")
        ui.set_category_icon(cat_id, "brush")
        ok(store.state()["categories"][0]["icon"] == "brush", "so does an icon")

        # HEX-поле и ползунки дают тот же результат, что палитра.
        hue, light, _sat = C.hex_to_hsl("#3ecfaf")
        ok(C.hsl_to_hex(hue, light) != "", "hue/lightness round-trip to a colour")
        ui.set_category_color(cat_id, C.parse_hex("#B06CF0"))
        ok(store.state()["categories"][0]["color"] == "#b06cf0", "and so does typed HEX")

        png = iconify.generate_icon(os.path.join(d, "mark.png"), 32)
        stored = ui._store_category_image(cat_id, str(png))
        ok(stored and os.path.exists(stored), "a custom image is copied next to the library")
        store.update_category(cat_id, {"image": stored})
        ui.refresh()
        from app.ui import widgets
        glyph = widgets.cat_glyph(store.state()["categories"][0])
        art = _find_control(glyph, lambda c: isinstance(c, ft.Image))
        ok(art is not None, "and it is what the rail draws")
        ok(art.fit == ft.BoxFit.COVER,
           "cropped to fill like a Discord icon, not letterboxed inside the badge")
        ok(getattr(glyph, "border_radius", None), "inside a circular clip")

        # A category holds one picture: swapping formats must not leave the
        # previous file orphaned in the cache with nothing pointing at it.
        jpg = os.path.join(d, "mark.jpg")
        __import__("PIL.Image", fromlist=["Image"]).new("RGB", (40, 24)).save(jpg)
        swapped = ui._store_category_image(cat_id, jpg)
        ok(swapped and swapped.endswith(".jpg"), "a JPG is accepted, not just PNG/SVG")
        ok(not os.path.exists(stored), "and the previous file is cleaned up")
        again = ui._store_category_image(cat_id, jpg)
        ok(again != swapped and not os.path.exists(swapped),
           "a new picture of the same format gets a new name, so no stale cached image shows")

        ok(ui._store_category_image(cat_id, os.path.join(d, "notes.txt")) is None,
           "something that isn't an image is still refused")

        ui.clear_category_image(cat_id)
        ok(store.state()["categories"][0]["image"] is None, "it can be taken off again")

        ui.close_popover()
        ok(not ui.popover_layer.visible, "Esc closes the popover")


def test_ui_calm_mode():
    """Спокойный вид — теперь основной режим. Он всё ещё прячет чистые
    подсказки клавиш и часть счётчиков, но больше не трогает пути, хоткеи,
    источники находок и то, сколько программ найдено/ждёт в разборе."""
    try:
        from app.platform import discovery
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI calm-mode test", exc)
        return

    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ok("calm" not in store.settings(),
           "calm mode is the only mode now — there is no setting left to toggle it")

        app_id = store.add_app({"name": "Notion", "path": r"C:\Program Files\Notion\N.exe",
                                "category_id": "work", "quick": True})["id"]
        other_id = store.add_app({"name": "Figma", "path": r"C:\pf\Figma.exe",
                                  "category_id": "work"})["id"]
        store.mark_launched(app_id)
        ui, _ = _ui_for(store)
        ui.view.select_one(app_id)
        ui.refresh()

        def everything():
            return (_texts(ui.header_holder) + _texts(ui.sidebar_container)
                    + _texts(ui.toolbar_holder)
                    + _texts(ft.Column(ui.content_col.controls))
                    + _texts(ui.inspector_overlay))

        quiet = everything()
        ok("Ctrl+1" in quiet, "item 1: the tile's own hotkey still shows")
        ok(any(t.startswith("C:\\") for t in quiet),
           "item 2: the inspector's technical block (path) is untouched")
        ok(any(t.startswith("Место 1") for t in quiet),
           "item 3: and its quick-launch slot note")
        ok("Ctrl+1…9" not in quiet, "but the quick-row key-hint legend stays gone (group 1)")
        ok("Notion" in quiet, "the name was of course never hidden either way")

        ui._open_palette()
        palette = _texts(ui.palette_layer)
        ok(any("Новая" in t or "назад" in t for t in palette),
           "item 4: a palette row still carries its category/last-launched subtitle")
        ok(not any("выбрать" in t for t in palette),
           "but the palette's own key-hint footer is a pure hint — still gone")
        ui._close_palette()

        ui.set_ops.make_set([app_id, other_id])
        rec = store.state()["sets"][0]
        set_accel = ui._set_accels.get(rec["id"])
        ok(set_accel and set_accel in _texts(ft.Column(ui.content_col.controls)),
           "item 5: a set's own hotkey shows on its screen")
        ui.view.close_set()
        ui.refresh()

        found = [{"name": "OBS Studio", "path": "C:/pf/obs64.exe", "source": "startmenu"}]
        real_discover, real_backfill = discovery.discover_apps, discovery.backfill_icons
        try:
            discovery.discover_apps = (
                lambda icon_cache=None, on_progress=None, report=None, posters=True: list(found))
            discovery.backfill_icons = lambda *a, **kw: False
            import threading as _threading
            before = set(_threading.enumerate())
            ui.open_add()
            ok(_settle_threads(before), "the scan thread finishes")
            ui.refresh()
            add_screen = _texts(ft.Column(ui.content_col.controls))
            ok(any("компьютере" in t for t in add_screen),
               "group 2: «сколько найдено» stays on the Add screen's header")
            ok("C:/pf/obs64.exe" not in add_screen,
               "item 6: a found row no longer prints its path/status line at all")
            ok("OBS Studio" in add_screen, "just the name and its category")
        finally:
            discovery.discover_apps, discovery.backfill_icons = real_discover, real_backfill

        store.queue_inbox([{"name": "Krita", "path": "C:/krita.exe", "source": "startmenu"}])
        ui.refresh()
        ok(any("1" in t for t in _texts(ui.rail_container)),
           "group 2: «сколько в разборе» — the rail badge — stays visible")
        ui.open_triage()
        triage_screen = _texts(ui.content_col.controls[0])
        ok(any("Осталось" in t for t in triage_screen),
           "group 2: and the in-screen «Осталось N · разложено M» count")
        ok(any("Меню «Пуск»" in t for t in triage_screen), "item 7: as does the item's source")
        footer = _find_control(ui.content_col.controls[0],
                               lambda c: isinstance(c, ft.Container) and c.height == 52)
        ok(footer is not None and footer.visible is not False,
           "item 7: and the triage key-legend footer is not force-hidden")


def test_ui_defaults_legacy_calm_ignored():
    """Old data files may still carry the retired calm:false setting on disk —
    it is quietly dropped rather than resurrected, since calm mode is now the
    only mode and there is nothing left to toggle."""
    import json

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": 3, "apps": [], "categories": [],
                      "settings": {"calm": False}}, fh)
        s = Store(path)
        ok("calm" not in s.settings(), "the stale calm setting is not carried forward")


def test_ui_restore_from_auto_backup():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI auto-backup restore test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_app({"name": "Editor", "path": "C:/e.exe"})
        ui, _ = _ui_for(store)
        asked = []
        ui.ask_for_file = lambda *a, **kw: asked.append(a)
        ui.restore_menu()
        ok(asked and not ui.menu.open, "without auto copies, «Восстановить…» asks for a file")

        copy = store.auto_backup()
        store.add_app({"name": "Later", "path": "C:/l.exe"})
        ui.restore_menu()
        labels = _menu_labels(ui)
        ok(ui.menu.open and labels[0].startswith("сегодня, ") and labels[-1] == "Из файла…",
           f"with them, it lists the copies and still offers a file ({labels})")
        row = next(r for r in ui.menu._rows if r["kind"] == "item")
        ok(row["hint"] == "1 программа", "each copy says how much is in it")
        row["on_click"]()
        ok([a["name"] for a in store.state()["apps"]] == ["Editor"],
           "picking a copy restores the library from it")
        ok(copy.exists(), "and the copy itself stays")


def test_rename_icon_and_restore_from_backup():
    """Программу можно переименовать и дать ей свою картинку; копию — восстановить.

    Имена из реестра («7-Zip 23.01 (x64)», «WINWORD») раньше оставались как
    есть, а у «Сохранить копию» не было обратной кнопки.
    """
    try:
        from PIL import Image

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("rename/icon/restore test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        app_id = store.add_app({"name": "WINWORD", "path": "C:/w.exe",
                                "category_id": "work"})["id"]
        ui, _ = _ui_for(store)

        ui.rename_app(app_id, "  Word ")
        ok(store.get_app(app_id)["name"] == "Word", "the name is trimmed and saved")
        ui.rename_app(app_id, "   ")
        ok(store.get_app(app_id)["name"] == "Word", "a blank name is ignored")

        src = os.path.join(d, "logo.bmp")
        Image.new("RGB", (512, 300), "red").save(src)
        ui.ask_for_file = lambda title, on_path, extensions=None: on_path(src)
        ui.pick_app_icon(app_id)
        app = store.get_app(app_id)
        ok(app["custom_icon"] and app["icon"].endswith(".png"), "a picked image becomes the icon")
        with Image.open(app["icon"]) as im:
            ok(max(im.size) <= 256, "scaled down to icon size")
        first = app["icon"]
        ui.pick_app_icon(app_id)
        ok(store.get_app(app_id)["icon"] != first and not os.path.exists(first),
           "a new pick gets a new file and the old one is removed")

        from app.platform import discovery
        discovery.backfill_icons(store, ui.icon_cache_dir(), refresh=True)
        ok(store.get_app(app_id)["custom_icon"], "refreshing icons keeps the user's picture")
        ui.clear_icon_cache()
        ok(os.path.exists(store.get_app(app_id)["icon"]), "and so does clearing the icon cache")

        ui.scan.backfill_icons_async = lambda: None
        ui.reset_app_icon(app_id)
        ok(not store.get_app(app_id)["custom_icon"], "the program's own icon can come back")

        backup = store.backup()
        store.add_app({"name": "Extra", "path": "C:/e.exe", "category_id": "work"})
        ui.restore_backup(str(backup))
        ok([a["name"] for a in store.state()["apps"]] == ["Word"],
           "restoring a backup puts the library back as it was")
        ui.toast.fire_action()
        ok(sorted(a["name"] for a in store.state()["apps"]) == ["Extra", "Word"],
           "and the restore itself can be undone")

        junk = os.path.join(d, "junk.json")
        with open(junk, "w", encoding="utf-8") as fh:
            fh.write('{"version": 99, "apps": []}')
        ui.restore_backup(junk)
        ok(len(store.state()["apps"]) == 2, "a backup from a newer version is refused")
        ok("более новой" in ui.toast.text.value, "with a reason")


def test_ui_settings_screen():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI settings test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, page = _ui_for(store)
        ui._open_settings()
        ok(not page.opened, "the settings are a screen, not a dialog")

        # Разделы слева, содержимое справа. «Категории» среди разделов нет
        # намеренно: ими управляют в рельсе и в поповере «Цвет и иконка».
        shown = _texts(ui.content_col.controls[0])
        for tab in ("Вид", "Клавиши", "Запуск и трей", "Библиотека"):
            ok(tab in shown, f"the section «{tab}» is in the left column")
        ok("Категории" not in shown, "and «Категории» is not a settings section")
        ok(ui.view.settings_tab == "view", "«Вид» is the one open to begin with")
        for row in ("ОФОРМЛЕНИЕ", "АКЦЕНТ", "ПЛИТКИ", "Постеры для игр"):
            ok(row in shown, f"«{row}» is on it")
        ok("Огромная" not in shown and "Очень крупная" in shown,
           "the biggest rail size is «Очень крупная», not a joke")
        # Настройки — на всю ширину: полоса категорий и панель библиотеки не
        # стоят рядом с их собственной навигацией.
        ok(not ui.rail_container.visible and not ui.sidebar_container.visible,
           "the settings take the whole window, without the library's rail and sidebar")
        ok("Спокойный вид" not in shown,
           "calm mode is the only mode now — there is no switch left for it")

        # Каждая настройка живёт ровно в одном разделе.
        expected = {
            "keys": ("Поиск по библиотеке", "Программы из «Быстрого запуска»", "Наборы",
                     "Меню выбранной плитки"),
            "startup": ("Запускать вместе с Windows",
                        "Закрытие окна оставляет Centurio в трее",
                        "Свёрнутое окно уходит в трей, а не на панель задач",
                        "Прятать окно после запуска программы"),
            "library": ("Новое сначала в «Новые программы»", "Проверять новое раз в 15 минут",
                        "Кэш значков", "Копия библиотеки", "Файл библиотеки",
                        "Подробный журнал"),
        }
        for tab, rows in expected.items():
            ui.set_settings_tab(tab)
            here = _texts(ui.content_col.controls[0])
            for row in rows:
                ok(row in here, f"«{row}» is on the «{tab}» section")
            ok("АКЦЕНТ" not in here, f"and «{tab}» does not carry «Вид»'s controls")
            if tab == "keys":
                ok("Подсказки клавиш" not in here,
                   "its own switch went with it — the footer it controlled is gone too")
        ui.set_settings_tab("view")

        for key in ("hide_after", "autostart", "close_to_tray", "triage"):
            before = bool(store.state()["settings"].get(key))
            ui.set_setting(key, not before)
            ok(store.state()["settings"][key] is (not before), f"«{key}» writes through")

        ui.set_settings_tab("keys")
        here = " ".join(_texts(ui.content_col.controls[0]))
        ok("только когда открыто окно Centurio" in here,
           "the keys tab says the shortcuts are window-only")

        ui.set_settings_tab("startup")
        here = _texts(ui.content_col.controls[0])
        ok(any("Крестик прячет окно" in t for t in here),
           "the two tray switches that read alike now explain what each does")
        ok("Проверить сейчас" in here, "and checking for updates is a button, not a link")

        ui.set_settings_tab("library")
        ui.backup()
        ok(any(p.name.startswith("centurio-backup-") for p in Path(d).glob("*.json")),
           "«Сохранить» writes a backup next to the library")


def test_ui_first_run():
    """A first run drops straight into the empty-library grid, with no modal.

    Suggestions, once a scan finds any, live inline in that empty state
    (test_ui_first_run_suggestions) and reuse the Add screen's scan.
    There used to be a "чем пользуетесь каждый день" picker modal on top
    of it (auto-shown once, replayable from settings) — removed because it
    duplicated the Add screen's own checklist for no real benefit while
    adding a whole extra screen, an "onboarded" flag, and a second
    scan-and-suggest code path to keep in sync with the first one.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI first-run test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)

        ok("Библиотека пуста" in _texts(ui.body),
           "an empty library shows the ordinary empty state, not a modal")
        ok(not ui.popover_layer.visible and not ui.bulk_layer.visible
           and not ui.palette_layer.visible,
           "nothing is popped open over it uninvited")

        for gone in ("maybe_onboard", "show_onboarding", "close_onboarding",
                    "onboarding_items", "toggle_onboarding", "commit_onboarding"):
            ok(not hasattr(ui, gone), f"the onboarding picker ({gone}) is gone for good")
        ok(not hasattr(ui, "onboarding_layer"), "and so is its overlay")
        ok("onboarded" not in store.state()["settings"],
           "along with the flag that used to gate it")


def test_ui_first_run_suggestions():
    """Пустая библиотека сама смотрит, что установлено, и предлагает то, чем
    человек, судя по уликам, уже пользуется."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI first-run suggestions test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "Desktop"))
        for name in ("Zeta Notes", "Qwerty Paint"):
            with open(os.path.join(d, "Desktop", f"{name}.lnk"), "w") as fh:
                fh.write("x")
        saved = {k: os.environ.get(k) for k in ("USERPROFILE", "APPDATA")}
        os.environ["USERPROFILE"] = d
        os.environ["APPDATA"] = d
        try:
            store = Store(os.path.join(d, "data.json"))
            ui, _ = _ui_for(store)
            ui.scan.start_scan = lambda force=False: None
            found = [{"name": "Zeta Notes", "path": "C:/z/zeta.exe", "source": "startmenu"},
                     {"name": "Qwerty Paint", "path": "C:/q/qpaint.exe", "source": "startmenu"},
                     {"name": "Unused Tool", "path": "C:/u/unused.exe", "source": "startmenu"}]
            ui.scan._remember_discovery(found)
            ui.refresh()
            shown = _texts(ui.body)
            ok("Похоже, вы этим пользуетесь" in shown, "suggestions replace the bare empty state")
            ok("Zeta Notes" in shown and "Qwerty Paint" in shown and "Unused Tool" not in shown,
               "only programs with evidence of use are offered")
            ok("Добавить 2" in shown, "all of them start ticked")

            from app.core.text import launch_key

            ui.scan.toggle_suggestion(launch_key(found[1]))
            ok("Добавить 1" in _texts(ui.body), "a card can be unticked")

            ui.scan.review_suggestions()
            ok(ui.view.screen == "add" and ui.view.add_sel == {launch_key(found[0])},
               "«Всё найденное» opens the full list with the same picks")
            ui.back_to_grid()

            ui.scan.add_suggestions()
            names = [a["name"] for a in store.state()["apps"]]
            ok(names == ["Zeta Notes"], f"«Добавить» adds the ticked ones ({names})")
            ok(store.state()["settings"]["first_run_done"], "and the offer is not repeated")

            ui.toast.fire_action()
            ok(not store.state()["apps"] and "Похоже, вы этим пользуетесь" in _texts(ui.body),
               "«Вернуть» brings back the offer along with the empty library")
            ui.scan.add_suggestions()
            store.remove_apps([a["id"] for a in store.state()["apps"]])
            ui.refresh()
            ok("Библиотека пуста" in _texts(ui.body),
               "an emptied library later shows the plain empty state")

            store2 = Store(os.path.join(d, "data2.json"))
            ui2, _ = _ui_for(store2)
            ui2.scan.start_scan = lambda force=False: None
            ui2.scan._remember_discovery(found)
            ui2.scan.dismiss_suggestions()
            ok("Библиотека пуста" in _texts(ui2.body) and store2.state()["settings"]["first_run_done"],
               "«Не сейчас» puts the offer away for good")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_ui_settings_cache():
    """refresh() reads the store once, no matter how many tiles it draws."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI settings-cache test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        for i in range(5):
            store.add_app({"name": f"App{i}", "path": f"/x/{i}", "category_id": "work"})
        ui, _ = _ui_for(store)

        calls = {"n": 0}
        real_state = store.state

        def counting_state():
            calls["n"] += 1
            return real_state()
        store.state = counting_state

        ui.refresh()
        few = calls["n"]
        ok(few > 0, "refresh() reads the store at least once")

        for i in range(5, 80):
            store.add_app({"name": f"App{i}", "path": f"/x/{i}", "category_id": "work"})
        calls["n"] = 0
        ui.refresh()
        ok(calls["n"] == few, "the read count doesn't grow with the number of apps")
        ok(calls["n"] == 1, "refresh() takes exactly one snapshot")
        ok(ui._snapshot is None, "and drops it when the pass ends")

        calls["n"] = 0
        ui.view.set_query("app1")
        ui.refresh(content_only=True)
        ok(calls["n"] == 1, "a keystroke in the search box costs one store read")

        ui.view.set_query("")
        calls["n"] = 0
        before = len(ui.apps())
        store.add_app({"name": "Fresh", "path": "/x/fresh", "category_id": "work"})
        ok(len(ui.apps()) == before + 1, "reads outside a refresh go to the store")
        ok(calls["n"] >= 2, "those reads aren't served from a stale snapshot")


def test_ui_background_rescan():
    """Тихая проверка складывает новое в разбор и не переиконивает всё."""
    try:
        from app.platform import discovery
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI background-rescan test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_app({"name": "App", "path": "/x/app.exe", "category_id": "work"})
        ui, _ = _ui_for(store)

        refreshes = []
        real_backfill = discovery.backfill_icons
        real_discover = discovery.discover_apps
        before = set(__import__("threading").enumerate())

        def fake_backfill(store_, icon_cache=None, refresh=False):
            refreshes.append(refresh)
            return False

        discovery.backfill_icons = fake_backfill
        discovery.discover_apps = (lambda icon_cache=None, on_progress=None, report=None, posters=True:
                                   [{"name": "Fresh", "path": "C:/fresh.exe",
                                     "source": "startmenu"}])
        try:
            ui.scan.rescan(silent=True)
            ok(_settle_threads(before), "the silent rescan finishes")
            ok(refreshes == [False],
               "a silent rescan only fills gaps, it doesn't re-resolve every icon")
            ok(len(store.state()["inbox"]) == 1,
               "what it found waits in the triage queue instead of appearing by itself")
            ok(not any(a["name"] == "Fresh" for a in store.state()["apps"]),
               "nothing was added to the library behind the user's back")

            store.clear_inbox()
            store.set_setting("triage", False)
            ui.scan.rescan()
            ok(_settle_threads(before), "the explicit rescan finishes")
            ok(refreshes == [False, True],
               "an explicit rescan still forces the full icon refresh")
            ok(not store.state()["inbox"],
               "with «Складывать новое в разбор» off, nothing is queued")
        finally:
            discovery.backfill_icons = real_backfill
            discovery.discover_apps = real_discover
            _settle_threads(before)


def test_ui_discovery_reuse():
    """Rescan, then open «Найти и добавить»: the machine is walked once."""
    try:
        from app.platform import discovery
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI discovery-reuse test", exc)
        return

    scans = {"n": 0}
    real_discover = discovery.discover_apps
    before = set(__import__("threading").enumerate())
    try:
        def counting(icon_cache=None, on_progress=None, report=None, posters=True):
            scans["n"] += 1
            return []

        discovery.discover_apps = counting
        with tempfile.TemporaryDirectory() as d:
            store = Store(os.path.join(d, "data.json"))
            ui, _ = _ui_for(store)

            ui.scan.start_scan()
            ok(_settle_threads(before), "the first scan finishes")
            ok(scans["n"] == 1, "opening the add screen with nothing cached scans once")
            ok(ui.scan.cached_discovery() is not None, "the result is cached")

            ui.scan.start_scan()
            ok(_settle_threads(before), "the second open settles")
            ok(scans["n"] == 1, "a cached result is reused instead of rescanning")

            ui.scan._discovered_at -= 200
            ok(ui.scan.cached_discovery() is None, "a stale result is not reused")
    finally:
        discovery.discover_apps = real_discover
        _settle_threads(before)


def test_slow_adding_does_not_hold_the_window():
    """Во Flet 1.0 обычный обработчик события выполняется в цикле событий.

    Добавление по пути извлекает значок (иногда через PowerShell, до 25 с) и
    качает обложку игры Steam — всё это время окно не отвечало бы. Поэтому
    Enter в поле пути и в поле набора отдают работу фоновому потоку.
    """
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI background work test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}.exe"})["id"] for n in ("A", "B")]
        rec = store.add_set("S", ids)
        ui, _ = _ui_for(store)
        handed = []
        ui.in_background = lambda fn, *args: handed.append((fn, args))
        # Настоящий поиск программ здесь ни к чему: его поток перерисовывает
        # экран и пишет в папку, пока тест ищет поле.
        ui.scan.start_scan = lambda force=False: None

        ui.open_add()
        path_field = _find_control(ui.content_col, lambda n: isinstance(n, ft.TextField)
                                   and "адрес сайта" in (n.hint_text or ""))
        path_field.on_submit(types_ns(control=types_ns(value="youtube.com")))
        ok(handed and handed[-1] == (ui.scan.submit_add_input, ("youtube.com",)),
           "Enter in the add field hands the work to a background thread")
        added = []
        real_add = ui.scan.add_manual_path
        ui.scan.add_manual_path = lambda text=None: added.append(text)
        ui.scan.submit_add_input("youtube.com")
        ui.scan.submit_add_input("telegram")
        ui.scan.add_manual_path = real_add
        ok(added == ["youtube.com"],
           "where an address is added, and a plain name only filters — nothing to add")

        ui._open_set(rec["id"])
        target = _find_control(ui.content_col, lambda n: isinstance(n, ft.TextField)
                               and n.hint_text == "Сайт, папка или файл")
        target.on_submit(types_ns(control=types_ns(value="github.com")))
        ok(handed[-1] == (ui.set_ops.add_target, (rec["id"], "github.com")),
           "and so does the set's own field")

