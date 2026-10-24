"""Главное окно: плитки, меню, панель справа, клавиши, уведомления."""
import os
import tempfile
from pathlib import Path

from helpers import (
    _FakePage,
    _find_control,
    _key,
    _menu_labels,
    _sized,
    _sources,
    _tap,
    _tap_mods,
    _texts,
    _ui_for,
    _walk,
    ok,
    skip,
    types_ns,
)

from app.core.store import Store
from app.ui import colors as C
from app.ui import iconify


def test_background_redraw_waits_for_the_field_being_edited():
    """Фоновая перерисовка не стирает то, что человек сейчас печатает.

    Монитор процессов перерисовывает окно, когда что-то запустилось или
    закрылось. Поле «Аргументы» или имя в панели справа собирается при этом
    заново — с фокусом и набранным текстом пропадало и то, и другое.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("deferred redraw test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        app_id = store.add_app({"name": "A", "path": "/x/a", "category_id": "work"})["id"]
        ui, _ = _ui_for(store)
        ui.view.select_one(app_id)
        ui.refresh()
        calls = []
        real = ui.refresh
        ui.refresh = lambda content_only=False: calls.append(content_only)

        ui.view.start_typing("app_args")
        ui.set_running([app_id])
        ui.safe_refresh()
        ok(calls == [], "while a rebuilt field has the cursor, background redraws wait")
        ui.view.stop_typing("app_args")
        ok(calls == [False], "and run once, in full, when the cursor leaves it")

        calls.clear()
        ui.view.start_typing("search")
        ui.set_running([])
        ok(calls == [True], "the search row survives redraws, so typing there doesn't block them")
        ui.refresh = real


def test_drag_reorder_reaches_the_end():
    """Перетаскиванием можно поставить категорию или программу набора последней.

    Перетащенное всегда вставало перед целью, так что вниз оно не доходило
    до последнего места никогда.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("drag reorder test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)
        for name in ("B", "C"):
            store.add_category(name)
        ids = [c["id"] for c in ui.categories()]
        ui._reorder_category(ids[0], ids[-1])
        ok([c["id"] for c in ui.categories()] == ids[1:] + ids[:1],
           "a category dragged onto the last one lands after it")
        ui._reorder_category(ids[0], ids[1])
        ok([c["id"] for c in ui.categories()] == [ids[0], ids[1], ids[2]],
           "and dragged back up it lands before its target")

        apps = [store.add_app({"name": n, "path": f"/x/{n}"})["id"] for n in "abc"]
        rec = store.add_set("S", apps)
        ui.chrome.drop_set_item(rec["id"], apps[2], types_ns(src=types_ns(data=apps[0])),
                                types_ns(update=lambda: None))
        ok(store.get_set(rec["id"])["apps"] == [apps[1], apps[2], apps[0]],
           "a set member dragged onto the last one starts last")


def test_long_menus_scroll_instead_of_cutting_off():
    """«Добавить программу» в набор предлагает всю библиотеку, а не первые 14.

    Список молча обрезался до четырнадцати по алфавиту: «Zoom» в набор с
    его экрана добавить было нельзя. Длинное меню теперь прокручивается и не
    уходит за край окна.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("long menu test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": f"App {i:02d}", "path": f"/x/{i}"})["id"] for i in range(40)]
        rec = store.add_set("S", ids[:2])
        ui, _ = _ui_for(store)
        ui.context_menus.add_to_set_picker(rec["id"])
        labels = _menu_labels(ui)
        ok(len(labels) == 38 and "App 39" in labels, "every program not yet in the set is offered")
        card = ui.menu.card.content
        ok(card.height is not None and card.height <= ui._window_height(),
           "and the menu stays inside the window, scrolling instead")


def test_ui_single_screen_layout():
    """Одно окно: шапка с поиском, рельса, панель, контент, инспектор."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI layout test", exc)
        return

    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_app({"name": "Notion", "path": "/x/notion.exe", "category_id": "work",
                       "quick": True, "favorite": True})
        chrome = store.add_app({"name": "Chrome", "path": "/x/chrome.exe",
                                "category_id": "work"})
        store.mark_launched(chrome["id"])
        ui, page = _ui_for(store)

        ok(page.controls, "mount puts a control tree on the page")
        ok(ui.rail_container.width == 72, "the rail is 72 wide")
        ok(ui.sidebar_container.width == 232, "the sidebar is 232 wide")
        ok(ui.sidebar_container.visible, "and it is shown")
        ok(ui.toolbar_holder.visible, "the content toolbar is there")
        ok(not hasattr(ui, "status_container"),
           "the status bar is gone — the sidebar footer and the rail badge carry it")

        head = _texts(ui.header_holder)
        ok("Centurio" in head, "the header carries the logo")
        ok("Ctrl+Пробел" not in head,
           "the search hotkey chip is a pure hint — it stays gone from the idle header")
        ok(not any("Запуск" == t for t in head),
           "the mode switch is gone with the second window")
        ok(ui.search_field.hint_text == "Найти или запустить",
           "one field both searches and launches")

        rail = _texts(ui.rail_container)
        ok(not rail, "the rail is icons only, as it always was")

        side = _texts(ui.sidebar_container)
        for label in ("Все программы", "Избранное", "Недавние", "Запущено", "НАБОРЫ"):
            ok(label in side, f"the sidebar has «{label}»")
        ok(not any("приложени" in t for t in side),
           "the two-part «128 приложений · 4 категории» line was shortened away")
        ok("НЕДАВНИЕ" not in side, "the recent list that duplicated the grid is gone")

        bar = _texts(ui.toolbar_holder)
        ok("Выбрать" in bar, "the toolbar starts the bulk-select mode")
        ok("По алфавиту" in bar, "keeps the sort selector")
        ok("Добавить" in bar, "and carries one primary action")
        ok(not any("Обновить" in t or "сканировать" in t.lower() for t in bar),
           "rescanning still lives in the right-click menu, not here")

        content = _texts(ft.Column(ui.content_col.controls))
        ok("Быстрый запуск" in content, "the quick-launch strip is still drawn")
        ok("Ctrl+1…9" not in content, "but the pure key-hint legend stays gone")
        ok("Новая" in content, "and the category sections below it")

        ui.set_running([chrome["id"]])
        ok(not any("запущено" in t for t in _texts(ui.sidebar_container)),
           "the sidebar footer's running count is a pure hint — stays gone too")

        width_before = ui._content_width()
        ui.view.select_one(chrome["id"])
        ui.refresh()
        ok(ui.inspector_overlay.visible, "selecting a tile opens the inspector")
        ok(ui.inspector_overlay.width == 320, "which is 320 wide")
        insp = _texts(ui.inspector_overlay)
        ok("Категория" in insp and "Быстрый запуск" in insp,
           "and carries the properties the panel is for")
        # Панель лежит поверх сетки: сбоку она отнимала две колонки, и плитка,
        # по которой щёлкнули, уезжала в другой ряд.
        ok(ui._content_width() == width_before,
           "the grid keeps its width — no column is taken away from under the tile")
        ok(ui.inspector_overlay.right == 0 and ui.inspector_overlay.top == 52,
           "the panel floats on the right, under the header")

        # Ещё более узкое окно убирает боковую панель.
        page.window.width = 960
        ui.refresh()
        ok(not ui.sidebar_container.visible, "below 1000 the sidebar goes away")
        page.window.width = 1400
        ui.refresh()
        ok(ui.sidebar_container.visible, "and comes back when there is room")


def test_ui_matches_the_design_sizes():
    """Макет: размеры воспроизводятся попиксельно.

    Ловит ровно то, что глазами в тестах не видно и что легко разъезжается при
    следующей правке: плитка не 120×128, палитра не 640, полотно монитора не 280.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI size test", exc)
        return

    import flet as ft

    from app.ui import colors as C

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        poster = os.path.join(d, "poster.png")
        iconify.generate_icon(poster, 64)
        store.add_app({"name": "CS2", "path": "steam://rungameid/730",
                       "category_id": "games", "poster": poster})
        app_id = store.add_app({"name": "Excel", "path": "C:/x.exe",
                                "category_id": "work", "quick": True})["id"]
        second = store.add_app({"name": "Teams", "path": "C:/t.exe",
                                "category_id": "work"})["id"]
        ui, _ = _ui_for(store)

        ok(ui.header_holder.content.height == C.HEADER_H == 52, "the header is 52 tall")
        ok(ui.search_box.width == C.SEARCH_W == 560, "the search field is 560 wide")
        ok(ui.rail_container.width == 72 and ui.sidebar_container.width == 232,
           "the rail is 72 and the sidebar 232")
        ok(_sized(ui.rail_container, 42, 42), "the rail buttons are 42x42")
        ok(_sized(ui.rail_container, 3, 26), "with a 3x26 indicator on the active one")

        content = ft.Column(ui.content_col.controls)
        ok(_sized(content, C.QUICK_W, 88) and C.QUICK_W == 132,
           "a quick-launch card is 132 wide")
        # Плитка почти квадратная, значок крупно: у прежней 164×146 значок 50 px
        # занимал десятую часть площади, остальное было тёмной пустотой.
        ok(_sized(content, C.TILE_W, C.TILE_H) and (C.TILE_W, C.TILE_H) == (120, 128),
           "a tile is 120x128")
        ok(_sized(content, C.TILE_ICON, C.TILE_ICON) and C.TILE_ICON == 56,
           "with a 56 px icon — almost half the tile")
        ok(_sized(content, C.POSTER_W, C.POSTER_H) and (C.POSTER_W, C.POSTER_H) == (120, 180),
           "a game poster is 120x180, as wide as a tile")
        per_row = (ui._content_width() - 48 + C.TILE_GAP) // (C.TILE_W + C.TILE_GAP)
        ok(per_row == 8, f"eight programs fit a row of the 1400 px window ({per_row})")

        ui._select_tile(app_id)
        ok(ui.inspector_overlay.width == 320, "the inspector is 320 wide")
        ok(_sized(ui.inspector_overlay, 48, 48), "its icon is 48x48")
        ok(_sized(ui.inspector_overlay, 168, 34), "the category control is 168x34")

        ui._open_palette()
        ok(_sized(ui.palette_layer, C.PALETTE_W, None) and C.PALETTE_W == 640,
           "the palette is 640 wide")
        ok(_sized(ui.palette_layer, None, 48), "its result rows are 48 tall")
        ok(ui.palette_layer.top == 52 and ui.palette_scrim.top == 0,
           "and the whole layer starts under the header, which stays above it — "
           "covering the search row it stole the click that should focus the field")
        ui._close_palette()

        ui.toggle_select_mode()
        ui._tile_tap(second, [second])
        ok(_sized(ui.bulk_layer, None, 56), "the floating action bar is 56 tall")
        ok(ui.bulk_layer.bottom == 26, "sitting 26 off the bottom")
        ok(_sized(ft.Column(ui.content_col.controls), 20, 20),
           "and the tiles carry a 20x20 checkbox in this mode")
        ok(ui.bulk_layer.bottom == 26 and ui.toast.control.bottom > 56 + 26,
           "the toasts step above the bar")
        ui.toggle_select_mode()

        rec = store.add_set("Набор", [app_id, second])
        ui.refresh()
        ui._open_set(rec["id"])
        board = ft.Column(ui.content_col.controls)
        ok(_sized(board, None, C.CANVAS_H) and C.CANVAS_H == 280,
           "the monitor board is 280 tall")
        ok(_sized(board, C.SET_SIDE_W, None) and C.SET_SIDE_W == 300,
           "«Порядок запуска» is 300 wide")
        ok(_sized(board, None, 52), "its rows are 52 tall")
        ok(_sized(board, None, 44), "and «Добавить программу» is 44")


def test_ui_tile_cache():
    """Плитки переиспользуются, пока их вид не изменился."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI tile cache test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        cats = [c["id"] for c in store.state()["categories"]]
        for i in range(8):
            store.add_app({"name": f"App {i}", "path": f"/bin/app{i}",
                           "category_id": cats[i % len(cats)]})
        ui, _ = _ui_for(store)
        target = store.state()["apps"][0]
        tid = target["id"]

        def tile():
            return ui._tile_cache[tid][1]

        before = tile()
        ui.refresh()
        ok(tile() is before, "an unchanged tile is reused, not rebuilt")

        cached = len(ui._tile_cache)
        ok(cached == 8, "every visible app lands in the cache")

        def rebuilds(label, change):
            was = tile()
            change()
            ui.refresh()
            ok(tile() is not was, label)

        rebuilds("renaming rebuilds the tile",
                 lambda: store.update_app(tid, {"name": "Renamed"}))
        rebuilds("favouriting rebuilds the tile",
                 lambda: store.update_app(tid, {"favorite": True}))
        rebuilds("a new icon rebuilds the tile",
                 lambda: store.update_app(tid, {"icon": "/tmp/whatever.png"}))
        rebuilds("launching rebuilds the tile",
                 lambda: setattr(ui, "running", {tid}))
        rebuilds("selecting rebuilds the tile",
                 lambda: ui.view.select_one(tid))
        rebuilds("select mode rebuilds the tile",
                 lambda: ui.view.enter_select_mode())
        rebuilds("the tile size setting rebuilds every tile",
                 lambda: store.set_setting("tile_size", "compact"))
        rebuilds("switching to list mode rebuilds the row",
                 lambda: ui.view.set_mode("list"))
        rebuilds("renaming its category rebuilds the tile",
                 lambda: store.update_category(store.get_app(tid)["category_id"],
                                               {"name": "Другое имя"}))

        gone = [a["id"] for a in store.state()["apps"] if a["id"] != tid]
        store.remove_apps(gone)
        ui.refresh()
        ok(set(ui._tile_cache) == {tid},
           "tiles of removed apps are dropped from the cache")


def test_ui_section_holders_dont_flicker():
    """Обёртка секции (её Row/Container) переживает refresh как есть —
    иначе Flet видит новый объект на месте старого и перевыкладывает всю
    секцию целиком, из-за чего мерцали даже плитки, которых изменение не
    касалось."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI section holder test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        cat_id = store.state()["categories"][0]["id"]
        ids = [store.add_app({"name": f"App {i}", "path": f"/bin/app{i}",
                              "category_id": cat_id})["id"] for i in range(3)]
        ui, _ = _ui_for(store)

        key = ("grid", cat_id)
        holder = ui.grid._section_holders[key]
        row_before = holder.content
        tiles_before = list(row_before.controls)

        store.update_app(ids[0], {"favorite": True})
        ui.refresh()

        ok(ui.grid._section_holders[key] is holder,
           "the section's own wrapper container is reused, not rebuilt")
        ok(ui.grid._section_holders[key].content is row_before,
           "so is its Row — Flet only has to diff its list of children")
        ok(row_before.controls[0] is not tiles_before[0], "the changed tile is rebuilt")
        ok(row_before.controls[1] is tiles_before[1] and row_before.controls[2] is tiles_before[2],
           "but its untouched neighbours are the very same objects — nothing to redraw there")

        gone_key = ("grid", "no-such-category")
        ok(gone_key not in ui.grid._section_holders, "sanity: unrelated keys are never created")


def test_ui_skips_work_while_hidden():
    """Спрятанное окно не перерисовывается — работа копится до возврата."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI visibility test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        for i in range(5):
            store.add_app({"name": f"App {i}", "path": f"/bin/app{i}"})
        ui, _ = _ui_for(store)

        ui.set_visible(False)
        ui._tile_cache.clear()
        ui.refresh()
        ok(not ui._tile_cache, "a hidden refresh builds no tiles at all")
        ok(ui._dirty, "it records that a repaint is owed")

        store.add_app({"name": "Added while hidden", "path": "/bin/late"})
        ui.refresh()
        ok(not ui._tile_cache, "further hidden refreshes stay free")

        ui.set_visible(True)
        ok(not ui._dirty, "coming back clears the debt")
        ok(len(ui._tile_cache) == 6, "and repaints everything once, including the new app")

        before = dict(ui._tile_cache)
        ui.set_visible(True)
        ok(dict(ui._tile_cache) == before, "a repeated show does not repaint again")

        ui.set_visible(False)
        settings = ui.store.settings()
        ok(isinstance(settings, dict) and "hide_after" in settings,
           "settings stay readable while hidden, without a full state copy")


def test_ui_context_menus():
    """Правая кнопка на плитке — меню, как везде в Windows; панель свойств —
    его последний пункт «Свойства…». По пустому месту сетки правая кнопка
    ничего не открывает."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI context-menu test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B", "C")]
        ui, page = _ui_for(store)

        ui.context_menus.app_menu(store.get_app(ids[0]), _tap())
        ok(ui.menu.open and not ui.view.inspector,
           "right-clicking a plain tile opens a menu, not the properties panel")
        labels = _menu_labels(ui)
        for entry in ("Запустить", "От имени администратора", "Показать в папке",
                      "В избранное", "В быстрый запуск", "Переложить в…", "В набор…",
                      "Переименовать", "Свойства…", "Убрать из библиотеки"):
            ok(entry in labels, f"the tile menu offers «{entry}»")
        ok(labels[-2:] == ["Свойства…", "Убрать из библиотеки"],
           "with «Свойства…» at the end, next to removing")
        ok(not page.opened, "and nothing modal was opened to do it")
        props = next(r for r in ui.menu._rows if r.get("label") == "Свойства…")
        ui.menu._fire(props)
        ok(not ui.menu.open and ui.view.inspector == ids[0] and ui.inspector_overlay.visible,
           "«Свойства…» opens the panel for that program")
        ui._close_inspector()

        ui.missing = {ids[2]}
        ui.context_menus.app_menu(store.get_app(ids[2]), _tap())
        labels = _menu_labels(ui)
        ok(labels[0] == "Найти файл…" and "Запустить" not in labels,
           "a program whose file is gone offers to find it instead of launching")
        ok("файл не найден" in _texts(ui.menu.card), "and the menu header says why")
        ui.menu.close()
        ui.missing = set()

        ui.view.select_one(ids[0])
        ui.view.toggle_selection(ids[1])
        ui.context_menus.app_menu(store.get_app(ids[0]), _tap())
        labels = _menu_labels(ui)
        ok("В набор…" in labels,
           "right-clicking inside a selection offers the selection's menu")
        ok("Скрыть из сетки" in labels, "with the bulk actions on it")
        ok(any("Убрать" in x for x in labels), "including removing all of it")

        submenu = [r for r in ui.menu._rows if r["kind"] == "item" and r["submenu"]]
        ok(len(submenu) == 2, "two of its entries open submenus")
        ui.menu.toggle_submenu("cat", ui.context_menus._category_submenu(ids[:2]), 250)
        ok(ui.menu.sub_card.visible, "and the submenu opens next to the menu")
        ok("Новая" in _texts(ui.menu.sub_card), "listing the categories to move into")

        ui.menu.close()
        ok(not ui.menu.open, "clicking away closes it")

        ui.context_menus.category_menu(store.state()["categories"][0], _tap())
        labels = _menu_labels(ui)
        for entry in ("Изменить", "Удалить категорию"):
            ok(entry in labels, f"the category menu offers «{entry}»")
        ok("Переименовать" not in labels and "Цвет и иконка" not in labels,
           "rename and colour/icon used to be two entries opening the same popover")
        ok("Переместить выше" in labels, "and reordering")
        first_row = next(r for r in ui.menu._rows
                         if r["kind"] == "item" and r["label"] == "Переместить выше")
        ok(first_row["disabled"], "which is disabled for the first category")
        ui.menu.close()

        ok(not hasattr(ui, "_empty_menu"),
           "the empty-grid-space context menu is gone, not just unreachable")

        # Меню не должно вылезать за край окна.
        ui.menu.close()
        ui.context_menus.category_menu(store.state()["categories"][0], _tap(1390, 870))
        ok(ui.menu.card.left < 1390 and ui.menu.card.top < 870,
           "a menu opened near the corner is flipped back inside the window")


def test_ui_inspector_replaces_the_modal_form():
    """Инспектор вместо окна на тринадцать полей."""
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI inspector test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        app_id = store.add_app({"name": "Excel", "path": r"C:\Office16\EXCEL.EXE",
                                "category_id": "work", "track_exe": "EXCEL.EXE"})["id"]
        ui, page = _ui_for(store)

        ui._select_tile(app_id)
        ok(ui.inspector_overlay.visible, "clicking a tile opens the panel")
        ok(not page.opened, "and blocks nothing")
        shown = _texts(ui.inspector_overlay)
        name_field = _find_control(ui.inspector_overlay,
                                   lambda n: isinstance(n, ft.TextField) and n.value == "Excel")
        ok(name_field is not None, "the panel names the app in a field you can rename it in")
        ok(any("EXCEL.EXE" in t for t in shown), "and shows where it lives")
        ok("Запустить" in shown, "with the action that runs it")
        ok("Показать в папке" in [c.tooltip for c in _walk(ui.inspector_overlay)
                                  if getattr(c, "tooltip", None)],
           "opening the containing folder is a button here now, not a menu item")
        ok("Категория" in shown and "Быстрый запуск" in shown and "В наборах" in shown,
           "the properties are there")
        ok("Своя горячая клавиша" not in shown, "and no system-wide hotkey field any more")
        ok("В набор" in shown,
           "«В наборах» stays even for an app in none — that's how it joins the first one")
        ok("ПАРАМЕТРЫ ЗАПУСКА" in shown, "and the collapsed launch options")
        ok(not any("Скрыть" in t for t in shown),
           "«Скрыть» didn't come along when the popup's items moved in here")

        # Каждое изменение применяется сразу, кнопки «Сохранить» нет.
        ok("Сохранить" not in shown, "there is no save button")
        ui._toggle_quick(app_id, True)
        ok(store.get_app(app_id)["quick"] is True, "the pin toggle writes through")
        ui.refresh()
        ok("Место 1 · Ctrl+1 в окне" in _texts(ui.inspector_overlay),
           "and its slot shows up under «Быстрый запуск» right away")
        ui._set_args(app_id, "--profile work")
        ok(store.get_app(app_id)["args"] == ["--profile", "work"], "so do the arguments")
        ui._set_admin(app_id, True)
        ok(store.get_app(app_id)["run_as_admin"] is True, "and the admin switch")

        ui.context_menus.launch_more_menu(store.get_app(app_id), _tap())
        for entry in ("Открыть ещё окно", "От имени администратора"):
            ok(entry in _menu_labels(ui), f"«Ещё способы запуска» offers «{entry}»")
        ui.menu.close()

        ui.context_menus.add_to_set_menu(store.get_app(app_id), _tap())
        ok("Новый набор…" in _menu_labels(ui),
           "the «+» chip in «В наборах» opens the same add-to-set menu")
        ui.menu.close()

        ui.view.adv = True
        ui.refresh()
        ok("EXCEL.EXE" in _texts(ui.inspector_overlay), "the process is shown when known")

        second = store.add_app({"name": "Zoom", "path": "/x/z", "category_id": "work"})["id"]
        ui._select_tile(second)
        ok(_find_control(ui.inspector_overlay,
                         lambda n: isinstance(n, ft.TextField) and n.value == "Zoom"),
           "selecting another tile switches the panel instead of stacking a window")

        ui._close_inspector()
        ok(not ui.inspector_overlay.visible, "the cross closes it")


def test_ui_delete_is_undone_not_confirmed():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI delete test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_category("Творчество")  # a second category to move apps into below
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("Notion", "Figma")]
        ui, page = _ui_for(store)

        ui._remove_apps([ids[0]])
        ok(not page.opened, "nothing was opened to ask first")
        ok(store.get_app(ids[0]) is None, "the app is gone straight away")
        ok(ui.toast.action_btn.visible and ui.toast.action_label.value == "Вернуть",
           "a toast offers to put it back")
        ok(ui.toast.countdown.value == "8", "counting down from eight seconds")
        # Слой тоста шириной ровно с карточку. Растянутый на всё окно (left=0 и
        # right=0 сразу) он съедал каждый клик на своей высоте: полоса боковой
        # панели и сетки не отзывалась, пока не истечёт отсчёт.
        ok(ui.toast.control.left is None and ui.toast.control.width is None,
           "the toast layer is not pinned to both window edges")
        # В правом нижнем углу, как уведомления Windows: посередине окна они
        # закрывали плитки.
        ok(ui.toast.control.right == 16 and ui.toast.control.bottom == 16,
           "it sits in the bottom-right corner")
        ui.toast.fire_action()
        ok(store.get_app(ids[0]) is not None, "«Вернуть» restores it")

        cat = store.state()["categories"][1]
        ui._move_apps_to_category(ids, cat["id"])
        ok(all(store.get_app(i)["category_id"] == cat["id"] for i in ids), "moving works")
        ui.toast.fire_action()
        ok(all(store.get_app(i)["category_id"] == "work" for i in ids),
           "and is undoable too")

        ui._reorder_apps(ids, [ids[1]], ids[0])
        ok(store.get_app(ids[1])["order"] < store.get_app(ids[0])["order"],
           "dragging one tile onto another moves it in front")
        ok(ui.view.sort == "manual",
           "and switches sorting to manual so the new order is actually visible")

        # Та же ручка, что и настоящая плитка использует: DragTarget вокруг
        # неё принимает {"ids": [...]} из перетаскиваемой плитки.
        ui.view.set_sort("alpha")
        dragged = types_ns(data={"ids": [ids[0]]})
        ui.grid._accept_reorder(types_ns(src=dragged), ids[1], [ids[1], ids[0]], {})
        ok(store.get_app(ids[0])["order"] < store.get_app(ids[1])["order"],
           "the grid's own drop handler reorders tiles the same way")
        ok(ui.view.sort == "manual", "and flips sorting to manual too")

        ui._remove_category(cat["id"])
        ok(not any(c["id"] == cat["id"] for c in store.state()["categories"]),
           "a category goes without a confirmation")
        ui.toast.fire_action()
        ok(any(c["id"] == cat["id"] for c in store.state()["categories"]),
           "and comes back with its apps")

        while len(store.state()["categories"]) > 1:
            store.remove_category(store.state()["categories"][-1]["id"])
        ui.refresh()
        ui._remove_category(store.state()["categories"][0]["id"])
        ok(len(store.state()["categories"]) == 1,
           "the last category can't be deleted — the apps would have nowhere to go")


def test_ui_reorder_apps_direction():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI reorder direction test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        cat_id = store.state()["categories"][0]["id"]
        a, b, c = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": cat_id})["id"]
                   for n in ("A", "B", "C")]
        ui, _ = _ui_for(store)

        ui._reorder_apps([a, b, c], [a], b)
        ok([r["id"] for r in sorted(store.state()["apps"], key=lambda r: r["order"])] == [b, a, c],
           "dropping a tile on its very next neighbour moves it past that neighbour")

        ui._reorder_apps([b, a, c], [c], a)
        ok([r["id"] for r in sorted(store.state()["apps"], key=lambda r: r["order"])] == [b, c, a],
           "and dropping on the previous neighbour moves it back, in one step either way")


def test_ui_click_launches_right_click_opens_the_menu():
    """ЛКМ по плитке запускает программу, ПКМ открывает меню, «···» — то же меню."""
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI click-behaviour test", exc)
        return

    def tile_taps():
        return [g for g in _walk(ft.Column(ui.content_col.controls))
                if isinstance(g, ft.GestureDetector) and g.on_secondary_tap_down
                and (g.on_tap or g.on_tap_down)]

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B")]
        ui, _ = _ui_for(store)
        ui.launcher.launch.return_value = {"ok": True, "running": True}
        ui.launcher.running_ids.return_value = []

        taps = tile_taps()
        ok(len(taps) == 2 and all(g.on_tap and not g.on_tap_down for g in taps),
           "tiles launch when the button is released, not pressed: a press may "
           "start a drag, and dragging a tile must not launch the app")
        taps[0].on_tap(types_ns(control=taps[0]))
        ok(ui.launcher.launch.called, "a plain click launches the app directly")
        ok(ui.view.inspector is None, "without opening the inspector")

        ui.context_menus.app_menu(store.get_app(ids[1]), _tap())
        ok(ui.launcher.launch.call_count == 1,
           "right-clicking a plain tile does not launch it")
        ok(ui.menu.open and ui.view.inspector is None,
           "right-clicking opens the tile's menu, as everywhere in Windows")
        ui.menu.close()

        more = [c for c in _walk(ft.Column(ui.content_col.controls))
                if isinstance(c, ft.GestureDetector) and c.on_tap_down
                and not c.on_tap and getattr(c.content, "tooltip", None) == "Меню"]
        ok(len(more) == 2 and not any(c.visible for c in more),
           "every tile carries «···», hidden until the pointer is over it")
        more[0].on_tap_down(_tap(700, 320))
        ok(ui.menu.open and ui.launcher.launch.call_count == 1,
           "and «···» opens the same menu, launching nothing")
        ok(ui.menu.card.left == 700, "right where it was pressed")
        ui.menu.close()

        # В списке — то же самое.
        ui._set_mode("list")
        ui.launcher.launch.reset_mock()
        taps = tile_taps()
        ok(len(taps) == 2 and all(g.on_tap and not g.on_tap_down for g in taps),
           "list rows also wait for the release")
        taps[0].on_tap(types_ns(control=taps[0]))
        ok(ui.launcher.launch.called, "list rows launch on a plain click too")
        ui.context_menus.app_menu(store.get_app(ids[1]), _tap())
        ok(ui.menu.open, "and open the menu on the right click")


def test_ui_bulk_operations():
    """Массовые операции: режим выбора, плавающая панель, отмена вместо вопроса."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI bulk-select test", exc)
        return

    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B", "C", "D")]
        ui, page = _ui_for(store)

        ok(not ui.bulk_layer.visible, "the floating bar is not there to begin with")
        ui.toggle_select_mode()
        ok(ui.view.select_mode, "«Выбрать» turns the mode on")
        ok(not ui.inspector_overlay.visible, "the inspector steps aside for it")
        ok(not ui.bulk_layer.visible, "and the bar waits until something is picked")
        bar = _texts(ui.toolbar_holder)
        ok("Выбрать всё" in bar, "the toolbar offers to take the whole view")
        ok("Добавить" in bar, "the primary add button stays put, even in select mode")

        ui._tile_tap(ids[0], ids)
        ok(ui.view.sel == [ids[0]], "a click picks one")
        ok(ui.bulk_layer.visible, "and the bar appears")
        ok("Выбрано 1" in _texts(ui.bulk_layer), "counting what is picked")
        ok(ui.toast.control.bottom > 82,
           "and the toast steps above it, so «Вернуть» never lands on the bar")
        for label in ("Категория", "В набор", "В избранное", "Скрыть", "Убрать", "Отмена"):
            ok(label in _texts(ui.bulk_layer), f"the bar offers «{label}»")

        ui._tile_tap(ids[2], ids, _tap_mods(shift=True))
        ok(ui.view.sel == ids[:3], "Shift+click takes the range from the last one")
        ok("Выбрано 3" in _texts(ui.bulk_layer), "and the counter follows")
        ui._tile_tap(ids[1], ids)
        ok(ui.view.sel == [ids[0], ids[2]], "clicking a picked tile drops it")

        head = _texts(ft.Column(ui.content_col.controls))
        ok(not any("выбрано" in t for t in head),
           "the section header's own pure selection count is a hint — stays gone")

        ui._select_all_visible()
        ok(len(ui.view.sel) == 4, "«Выбрать всё» takes everything in the view")

        ui._hide_apps(list(ui.view.sel), True)
        ok(all(store.get_app(i)["hidden"] for i in ids), "«Скрыть» applies at once")
        ok(not page.opened, "without asking anything")
        ok(ui.toast.action_label.value == "Отменить", "and offers to undo it")
        ui.refresh()
        ok("Скрытые" in _texts(ui.sidebar_container),
           "hidden programs get a sidebar row so they can be found again")
        ui.toast.fire_action()
        ok(not any(store.get_app(i)["hidden"] for i in ids), "undo brings them back")
        ui.refresh()
        ok("Скрытые" not in _texts(ui.sidebar_container),
           "and the row goes away once nothing is hidden")

        ok(ui.view.select_mode and not ui.view.sel,
           "an applied action clears the selection but stays in the mode")
        ui._tile_tap(ids[0], ids)
        ui._bulk_favorite([ids[0]])
        ok(store.get_app(ids[0])["favorite"] is True, "«В избранное» applies at once too")
        ui.toast.fire_action()
        ok(store.get_app(ids[0])["favorite"] is False, "and is undoable")

        ui.toggle_select_mode()
        ok(not ui.view.select_mode and not ui.view.sel,
           "«Отмена» leaves the mode and drops the selection")
        ok(not ui.bulk_layer.visible, "taking the bar with it")

        # Ctrl+клик по плитке включает режим, не открывая инспектор.
        ui._tile_tap(ids[1], ids, _tap_mods(ctrl=True))
        ok(ui.view.select_mode and ui.view.sel == [ids[1]],
           "Ctrl+click turns the mode on and picks that one")
        ok(ui.view.inspector is None, "and the inspector stays out of the way")

        # У Flet в событии клика модификаторов нет, поэтому тот же путь есть в
        # меню по правой кнопке — иначе мышью диапазон было бы не взять.
        ui.context_menus.app_menu(store.get_app(ids[3]), _tap())
        labels = _menu_labels(ui)
        for entry in ("Отметить", "Выбрать до этой", "Выбрать всё", "Выйти из режима"):
            ok(entry in labels, f"the select-mode menu offers «{entry}»")
        ui.menu.close()
        ui._range_to(ids[3])
        ok(ui.view.sel == ids[1:], "«Выбрать до этой» takes the range with the mouse")

        ui.toggle_select_mode()
        ok(not ui.view.select_mode, "leaving select mode")
        ui.context_menus.app_menu(store.get_app(ids[0]), _tap())
        ok(ui.menu.open and "Отметить" not in _menu_labels(ui),
           "outside select mode, right-clicking an ordinary tile opens its own "
           "menu — «Выбрать» in the toolbar is how the mode is entered with the mouse")
        ui.menu.close()


def test_ui_quick_numbers_match_the_hotkeys():
    """Ctrl+N launches whichever quick card holds that slot — the card stays
    quiet about it, but a program's own tooltip still spells it out."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("quick-slot numbering test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "quick": True})["id"]
               for n in ("Notion", "Figma")]
        ui, _ = _ui_for(store)
        ui.set_ops.make_set(ids)          # goes into the strip, ahead of both cards
        ui.refresh()

        from app.core.hotkeys import free_quick_slot, quick_accels

        accels = quick_accels(store.state()["apps"])
        ok(sorted(a.split("+")[-1] for a in accels.values()) == ["1", "2"],
           "the two pinned programs own Ctrl+1 and Ctrl+2")

        ui.view.close_set()
        ui.refresh()
        # Только сама лента, без заголовков секций под ней.
        strip = ui.content_col.controls[1]
        numbers = [t for t in _texts(strip) if t.isdigit()]
        ok(not numbers, "the pure slot-number badge is a hint — it never prints on the card")
        tips = [c.tooltip for c in _walk(strip) if getattr(c, "tooltip", None)]
        ok(any("Ctrl+1" in t for t in tips) and any("Ctrl+2" in t for t in tips),
           "but a program's own tooltip still spells out its combination")
        ok(not any("Ctrl+Alt+1" in t for t in tips),
           "the set's tooltip, on the other hand, drops the combination entirely")

        for n in range(3, 10):
            store.add_app({"name": f"App {n}", "path": f"/x/{n}", "quick": True})
        ok(free_quick_slot(store.state()["apps"]) == 0, "nine pinned programs fill the strip")


def test_ui_launch_failure_offers_a_way_out():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI launch-failure test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        app_id = store.add_app({"name": "Zoom", "path": "/gone/zoom.exe",
                                "category_id": "work"})["id"]
        ui, _ = _ui_for(store)
        ui.launcher.launch.return_value = {"ok": False, "error": "Файл не найден: zoom.exe"}

        ui._launch(app_id)
        ok(ui.toast.icon.color == C.DANGER, "a failed launch is reported as an error")
        ok("не нашёлся" in ui.toast.text.value, f"in words ({ui.toast.text.value})")
        ok(ui.toast.detail.visible, "with a second line explaining why")
        ok(ui.toast.action_label.value == "Найти", "and the action that fixes it")


def test_ui_keyboard():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI keyboard test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B", "C")]
        ui, _ = _ui_for(store)

        ui.keymap.handle_key(_key(",", ctrl=True))
        ok(ui.view.screen == "settings", "Ctrl+, opens the settings screen")
        ui.keymap.handle_key(_key("Escape"))
        ok(ui.view.screen == "grid", "Esc leaves it")

        ui.keymap.handle_key(_key("a", ctrl=True))
        ok(len(ui.view.sel) == 3, "Ctrl+A selects every visible tile")
        ok(ui.view.select_mode, "and turns the bulk-select mode on with them")
        ui.keymap.handle_key(_key("Delete"))
        ok(not store.state()["apps"], "Delete removes the selection")
        ui.toast.fire_action()
        ok(len(store.state()["apps"]) == 3, "and it is undoable")
        ui.keymap.handle_key(_key("Escape"))
        ok(not ui.view.select_mode and not ui.view.sel,
           "Esc leaves the mode and drops the selection")

        # Ctrl+1…9 и Ctrl+Alt+1…9 — только в окне, системных сочетаний нет.
        launched, sets_run = [], []
        ui._launch = lambda app_id, **kw: launched.append(app_id)
        ui.set_ops.launch_set = lambda set_id, **kw: sets_run.append(set_id)
        store.update_app(ids[1], {"quick": True})
        rec = store.add_set("S", ids[:2])
        ui.refresh()
        ui.keymap.handle_key(_key("1", ctrl=True))
        ok(launched == [ids[1]], "Ctrl+1 runs the first pinned program")
        ui.keymap.handle_key(_key("2", ctrl=True))
        ok(launched == [ids[1]], "an empty slot does nothing")
        ui.keymap.handle_key(_key("1", ctrl=True, alt=True))
        ok(sets_run == [rec["id"]], "Ctrl+Alt+1 runs the first set")

        ui.view.typing = "search"
        ui.keymap.handle_key(_key("1", ctrl=True, alt=True))
        ok(sets_run == [rec["id"]],
           "inside a text field Ctrl+Alt+digit is AltGr typing, not a set")
        ui.view.typing = None

        hidden = []
        ui.controllers["hide_to_tray"] = lambda: hidden.append(1)
        ui.view.close_inspector()
        ui.keymap.handle_key(_key("Escape"))
        ok(hidden == [1], "Esc with nothing left to close hides the window")


def test_tab_from_the_palette_does_not_type_into_the_inspector():
    """Tab в палитре: Flutter уводит фокус в следующее поле окна.

    Им оказывалось имя программы в панели справа, и продолжение запроса
    («tel» + «zz») переименовывало программу в «zz».
    """
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI stray focus test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        app_id = store.add_app({"name": "Figma", "path": "/x/figma.exe",
                                "category_id": "work"})["id"]
        store.add_app({"name": "Telegram", "path": "/x/tg.exe", "category_id": "work"})
        ui, _ = _ui_for(store)
        focused = []
        ui.refocus_search = lambda: focused.append(ui.search_field)
        ui.view.select_one(app_id)
        ui.refresh()
        name = _find_control(ui.inspector_overlay,
                             lambda n: isinstance(n, ft.TextField) and n.value == "Figma")
        ok(name is not None, "the inspector shows the name field")

        ui.toggle_search()
        ui._on_search(types_ns(control=types_ns(value="tel")))
        focused.clear()
        ui.keymap.handle_key(_key("Tab"))
        ok(focused[-1:] == [ui.search_field], "after Tab the cursor is put back into the search")

        focused.clear()
        name.on_focus(types_ns(control=name))
        ok(focused[-1:] == [ui.search_field] and ui.view.typing != "app_name",
           "a field that grabbed focus from the open palette hands it straight back")
        name.value = "zz"
        name.on_submit(types_ns(control=name))
        name.on_blur(types_ns(control=name))
        ok(store.get_app(app_id)["name"] == "Figma",
           "and what landed in it by mistake does not rename the program")

        ui._close_palette()
        ui.refresh()
        name = _find_control(ui.inspector_overlay,
                             lambda n: isinstance(n, ft.TextField) and n.value == "Figma")
        name.on_focus(types_ns(control=name))
        ok(ui.view.typing == "app_name", "with the palette closed the field works as before")
        name.value = "Figma Desktop"
        name.on_blur(types_ns(control=name))
        ok(store.get_app(app_id)["name"] == "Figma Desktop", "and renaming still works")


def test_ui_keys_belong_to_the_focused_field():
    """Пока курсор в поле ввода, клавиши библиотеки молчат.

    `page.on_keyboard_event` в Flet — глобальный обработчик и не знает, где
    фокус. Из-за этого `Delete`, нажатый внутри поля «Аргументы», удалял
    программу из библиотеки, стрелки в поиске двигали выделение в сетке,
    а `Escape` в поле прятал окно в трей.
    """
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI typing-guard test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}", "category_id": "work"})["id"]
               for n in ("A", "B", "C")]
        ui, _ = _ui_for(store)

        ui.view.select_one(ids[0])
        ui._toggle_adv()
        args = _find_control(ui.inspector_overlay,
                             lambda n: isinstance(n, ft.TextField) and n.hint_text == "не заданы")
        ok(args is not None, "инспектор показывает поле «Аргументы»")

        args.on_focus(types_ns(control=args))
        ok(ui.view.typing == "app_args", "фокус в поле отмечается в состоянии")
        ui.keymap.handle_key(_key("Delete"))
        ok(len(store.state()["apps"]) == 3, "Delete внутри поля не удаляет программу")
        ui.keymap.handle_key(_key("a", ctrl=True))
        ok(len(ui.view.sel) == 1 and not ui.view.select_mode,
           "Ctrl+A внутри поля выделяет текст, а не все плитки")

        args.on_blur(types_ns(control=args))
        ok(ui.view.typing is None, "уход фокуса снимает признак")
        ui.keymap.handle_key(_key("Delete"))
        ok(len(store.state()["apps"]) == 2, "и Delete снова работает по библиотеке")
        ui.toast.fire_action()

        search = ui.search_field
        search.on_focus(types_ns(control=search))
        hidden = []
        ui.controllers["hide_to_tray"] = lambda: hidden.append(1)
        ui.keymap.handle_key(_key("Arrow Down"))
        ok(ui.view.selected == -1, "стрелки в поиске не двигают выделение в сетке")
        search.value = "tel"
        ui.keymap.handle_key(_key("Escape"))
        ok(hidden == [], "Escape в поле с текстом не прячет окно в трей")
        search.value = ""
        ui.keymap.handle_key(_key("Escape"))
        ok(hidden == [1], "а в пустом поиске прячет — как на главном экране, "
                          "иначе окно из трея (курсор сразу в поиске) не убрать клавишей")
        search.on_focus(types_ns(control=search))

        ui.refresh()
        ok(ui.view.typing == "search",
           "поисковое поле переживает перестроение — признак остаётся")

        # Инспектор собирается заново на каждом refresh, в том числе на фоновом
        # от монитора процессов. Признак обязан уйти вместе со старым контролом,
        # иначе он залипнет и клавиши библиотеки замолчат насовсем.
        ui.view.typing = "app_args"
        ui.refresh()
        ok(ui.view.typing is None, "у пересобранного поля признак снимается")

        ui.view.set_screen("add")
        ok(ui.view.typing is None, "смена экрана тоже снимает признак")
        committed = []
        ui.scan.commit_add = lambda: committed.append(1)
        ui.view.typing = "add_search"
        ui.keymap.handle_key(_key("Enter", ctrl=True))
        ok(committed == [1], "Ctrl+Enter подтверждает добавление прямо из поля")


def _all_controls(root):
    """Каждый контрол поддерева — по всем полям, а не только controls/content."""
    import dataclasses

    seen, stack, out = set(), [root], []
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, (list, tuple)):
            stack.extend(node)
            continue
        if not dataclasses.is_dataclass(node) or isinstance(node, type):
            continue
        out.append(node)
        for f in dataclasses.fields(node):
            if f.name.startswith("_") or f.name in ("parent", "page"):
                continue
            value = getattr(node, f.name, None)
            if isinstance(value, (list, tuple)) or dataclasses.is_dataclass(value):
                stack.append(value)
    return out


def test_ui_icons_are_objects_not_names():
    """Во Flet 1.0 значок — `ft.Icons.X`, а не строка «folder».

    Строку клиент не рисует: на месте всего контрола появлялся серый
    прямоугольник ошибки (так выглядело меню «Переложить в…»).
    """
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI icon objects test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ids = [store.add_app({"name": n, "path": f"/x/{n}.exe", "category_id": "work"})["id"]
               for n in ("Alpha", "Beta")]
        rec = store.add_set("Утро", ids)
        ui, page = _ui_for(store)
        bad = []

        def check(where):
            for ctl in _all_controls(page.controls):
                if isinstance(ctl, ft.Icon) and isinstance(ctl.icon, str):
                    bad.append(f"{where}: {ctl.icon!r}")

        check("grid")
        app = store.get_app(ids[0])
        for name, show in (("category picker", lambda: ui.context_menus.category_picker(app, None)),
                           ("set menu", lambda: ui.context_menus.add_to_set_menu(app, None)),
                           ("sort menu", lambda: ui.context_menus.sort_menu(None)),
                           ("set item menu", lambda: ui.context_menus.set_item_menu(
                               store.get_set(rec["id"]), store.get_set(rec["id"])["items"][0],
                               None))):
            show()
            check(name)
            ui.menu.close()
        ui.view.select_one(ids[0])
        ui.refresh()
        check("inspector")
        ui.toggle_search()
        ui._on_search(types_ns(control=types_ns(value="al")))
        ui.keymap.handle_key(_key("Tab"))
        check("palette actions")
        ui._close_palette()
        for tab in ("view", "keys", "startup", "library"):
            ui._open_settings()
            ui.set_settings_tab(tab)
            check(f"settings/{tab}")
        ui.open_add()
        check("add screen")
        ui._open_set(rec["id"])
        check("set screen")
        ok(not bad, "string icon names reach ft.Icon: " + "; ".join(bad))


def test_ui_icons_are_never_letters():
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI icon test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_app({"name": "Notion", "path": "/x/notion.exe", "category_id": "work"})
        ui, _ = _ui_for(store)
        app = store.state()["apps"][0]

        slot = ui.icon_slot(app, 60, 16)
        ok(slot.bgcolor == C.RAISED, "an icon-less app gets the neutral pad")
        ok(isinstance(slot.content, ft.Icon), "with a glyph, not a letter")
        ok(slot.content.color == C.MUTED, "in the muted placeholder colour")
        ok(slot.content.icon == ft.Icons.FOLDER, "and the glyph is its category's")

        icon_png = iconify.generate_icon(os.path.join(d, "real.png"), 32)
        store.update_app(app["id"], {"icon": str(icon_png)})
        ui.refresh()
        slot = ui.icon_slot(store.get_app(app["id"]), 60, 16)
        ok(isinstance(slot.content, ft.Image), "once extracted, the real icon is what shows")

        ok(not any("initials" in src for _label, src in _sources("ui")),
           "nothing in the window draws a letter placeholder any more")


def test_images_are_handed_over_as_paths_not_base64():
    """Растр уходит клиенту путём — кодирование осталось только браузеру.

    base64 занимал ×1.33 от файла строкой в памяти Python и ещё столько же в
    протоколе Flet; постер 600×900 превращался в ~200 КБ строки. Хуже того,
    при библиотеке больше 192 картинок кэш начинал пробуксовывать: каждый
    `refresh` заново читал с диска и кодировал вытесненные картинки —
    синхронно, в потоке отрисовки.
    """
    try:
        import flet as ft  # noqa: F401

        from app.ui import images
    except Exception as exc:
        skip("UI image-source test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        png = str(iconify.generate_icon(os.path.join(d, "icon.png"), 32))
        missing = os.path.join(d, "gone.png")

        try:
            images.embed_images(False)
            img = images.icon_image(png, width=32, height=32)
            ok(img is not None and img.src == png, f"путь уходит как есть ({img and img.src})")

            ok(images.raster_path(png) == png, "существующий растр опознаётся")
            ok(images.raster_path(missing) is None, "отсутствующий файл — нет")
            ok(images.raster_path(os.path.join(d, "icon.txt")) is None, "как и не картинка")
            ok(images.icon_image(missing) is None,
               "для отсутствующего файла картинки нет — рисуется значок-заглушка")

            images.embed_images(True)
            web = images.icon_image(png, width=32, height=32)
            ok(web is not None and isinstance(web.src, bytes),
               "в режиме CENTURIO_WEB картинка уходит байтами, а не путём: страница в "
               "браузере не читает файлы с диска")
        finally:
            images.embed_images(False)


def test_ui_icon_slot_respects_stored_fit():
    """A Steam app's «icon» field is sometimes a wide capsule/header image and
    sometimes a genuinely square one — which one it got is recorded in
    icon_fit. The slot must go by that, not just by «came from Steam», or a
    square icon gets cover-cropped for no reason."""
    try:
        import flet as ft

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI icon-fit test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        icon_png = iconify.generate_icon(os.path.join(d, "square.png"), 32)
        square = store.add_app({"name": "Square Game", "path": "steam://rungameid/1",
                                "icon": str(icon_png), "icon_fit": "contain"})
        wide = store.add_app({"name": "Capsule Game", "path": "steam://rungameid/2",
                              "icon": str(icon_png), "icon_fit": "cover"})
        ui, _ = _ui_for(store)

        square_slot = ui.icon_slot(store.get_app(square["id"]), 60, 16)
        ok(square_slot.content.fit == ft.BoxFit.CONTAIN,
           "a Steam app whose icon is a real square one is not cover-cropped")

        wide_slot = ui.icon_slot(store.get_app(wide["id"]), 60, 16)
        ok(wide_slot.content.fit == ft.BoxFit.COVER,
           "one whose icon is capsule/header art still fills the slot as before")


def test_toast_lifecycle():
    try:
        from app.ui.toast import ToastHost
    except Exception as exc:
        skip("toast test", exc)
        return

    host = ToastHost(_FakePage())
    host.show("Готово")
    ok(host.control.visible and host.text.value == "Готово", "a plain toast shows its text")
    ok(not host.action_btn.visible, "with no action")

    host.error("Реестр не отдал список программ",
               detail="Остальные источники прочитались", action_label="Повторить",
               action=lambda: None)
    ok(host.icon.color == C.DANGER, "an error toast is red")
    ok(host.card.bgcolor == C.ERR_BG, "and looks different, not just differently worded")
    ok(host.detail.visible, "a second line explains what happened")
    ok(host.action_label.value == "Повторить", "and the action closes it")

    fired = []
    host.show("Убрано", action=lambda: fired.append(1))
    ok(host.countdown.value == "8", "an undoable toast counts down from eight")
    host._tick(host._token)
    ok(host.countdown.value == "7", "each tick takes a second off")
    host.fire_action()
    ok(fired == [1], "clicking it runs the action once")
    host.fire_action()
    ok(fired == [1], "a second click can't run it again")

    host.show("Первый", action=lambda: None)
    stale = host._token
    host.show("Второй", action=lambda: None)
    host._tick(stale)
    ok(host.text.value == "Второй" and host.control.visible,
       "a stale timer doesn't clear the toast that replaced it")

    # Обычная новость не затирает «Вернуть» — иначе фоновое «Нашлось нового»
    # молча отнимало отмену удаления.
    undone = []
    host.show("Убрано 3", action=lambda: undone.append(1))
    host.show("Нашлось нового: 2", wait_for_undo=True)
    ok(host.text.value == "Убрано 3" and host.action_btn.visible,
       "background news waits while an undo is still on offer")
    for _ in range(8):
        host._tick(host._token)
    ok(host.text.value == "Нашлось нового: 2" and not host.action_btn.visible,
       "and shows once the undo has run out")
    host.show("Убрано 2", action=lambda: undone.append(3))
    host.show("Telegram открыт")
    ok(host.text.value == "Telegram открыт",
       "the answer to the user's own action is shown at once")
    host.show("Убрано 1", action=lambda: undone.append(2))
    host.error("Не удалось сохранить данные")
    ok(host.text.value == "Не удалось сохранить данные",
       "an error does not wait — it replaces the undo")
    host.stop()


def test_icon_cache_size_is_not_recounted_on_every_draw():
    """Обход каталога кэша не повторяется на каждое нажатие переключателя.

    `icon_cache_size` вызывается из отрисовки вкладки «Библиотека», а это
    `rglob` со `stat` на каждый файл. При нескольких тысячах файлов кэша
    получалась заметная задержка на каждый чих, притом что цифра справочная.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI icon-cache-size test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)

        cache = Path(ui.icon_cache_dir())
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "a.png").write_bytes(b"x" * 1000)

        first = ui.icon_cache_size()
        ok(first == 1000, f"размер считается ({first})")

        (cache / "b.png").write_bytes(b"x" * 500)
        ok(ui.icon_cache_size() == 1000, "повторный вызов берёт запомненное, а не обходит диск")

        ui.forget_icon_cache_size()
        ok(ui.icon_cache_size() == 1500, "после явного сброса цифра пересчитывается")


def test_ui_refresh_thread_safety():
    """refresh() runs from five threads and rebuilds one shared control tree."""
    try:
        import threading

        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI refresh thread-safety test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        for i in range(8):
            store.add_app({"name": f"App{i}", "path": f"/x/{i}", "category_id": "work"})
        ui, _ = _ui_for(store)

        seen_elsewhere = []
        real_build = ui.grid.build_content

        def probing_build():
            box = []
            t = threading.Thread(target=lambda: box.append(ui._snapshot))
            t.start()
            t.join()
            seen_elsewhere.append(box[0])
            return real_build()

        ui.grid.build_content = probing_build
        try:
            ui.refresh()
        finally:
            ui.grid.build_content = real_build
        ok(seen_elsewhere == [None],
           "a refresh's snapshot is invisible to every other thread")
        ok(ui._snapshot is None, "the snapshot is dropped when the pass ends")

        overlaps = []
        depth = {"n": 0}
        real_build2 = ui.grid.build_content

        def counting_build():
            depth["n"] += 1
            if depth["n"] > 1:
                overlaps.append(depth["n"])
            try:
                return real_build2()
            finally:
                depth["n"] -= 1

        ui.grid.build_content = counting_build
        errors = []

        def hammer():
            try:
                for _ in range(25):
                    ui.refresh()
                    ui.set_running(["nope"])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            ui.grid.build_content = real_build2
        ok(not errors, f"concurrent refreshes raise nothing ({errors[:1]})")
        ok(not overlaps, "two refresh passes never build the control tree at once")
        ok(ui._snapshot is None, "no snapshot is left behind after the storm")
