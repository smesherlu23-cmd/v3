"""Разбор интерфейса: то, что окно больше не делает под рукой, и новая шкала."""
import os
import tempfile

from helpers import (
    _key,
    _menu_labels,
    _tap,
    _texts,
    _tips,
    _ui_for,
    _walk,
    ok,
    skip,
    types_ns,
)

from app.core import queries
from app.core.store import Store
from app.ui import colors as C


def _ui_ready():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        return exc
    return None


def _library(d):
    store = Store(os.path.join(d, "data.json"))
    chat = store.add_category("Общение")["id"]
    ids = {
        "Notion": store.add_app({"name": "Notion", "path": "/x/notion.exe",
                                 "category_id": "work", "quick": True})["id"],
        "Excel": store.add_app({"name": "Excel", "path": "/x/excel.exe",
                                "category_id": "work"})["id"],
        "Telegram": store.add_app({"name": "Telegram", "path": "/x/tg.exe",
                                   "category_id": chat})["id"],
    }
    return store, chat, ids


def test_select_mode_keeps_the_quick_row_in_place():
    """«Выбрать» не убирает ряд «Быстрый запуск»: он приглушается, а плитки стоят.

    Раньше ряд исчезал, все плитки поднимались на 146 px, и следующий щелчок
    попадал в пустое место.
    """
    problem = _ui_ready()
    if problem:
        skip("select mode layout test", problem)
        return
    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store, _chat, ids = _library(d)
        ui, _ = _ui_for(store)
        before = _texts(ft.Column(ui.content_col.controls))
        ok("Быстрый запуск" in before, "the quick row is there to begin with")
        heads_before = [t for t in before if t in ("Новая", "Общение")]

        ui.toggle_select_mode()
        holder = ui.grid._section_holders[("qrow",)]
        after = _texts(ft.Column(ui.content_col.controls))
        ok("Быстрый запуск" in after, "select mode keeps the quick row")
        ok(holder.opacity < 1 and holder.disabled, "only dimmed and inert")
        ok([t for t in after if t in ("Новая", "Общение")] == heads_before,
           "and the sections below come in the same order, at the same place")

        launched = []
        ui._launch = lambda app_id, **kw: launched.append(app_id)
        card = next(c for c in _walk(holder) if isinstance(c, ft.Container)
                    and c.on_click is not None and c.width == C.DOCK_CELL)
        card.on_click(types_ns(control=card))
        ok(not launched, "a click on the dimmed row launches nothing")
        ui.toggle_select_mode()
        card.on_click(types_ns(control=card))
        ok(launched == [ids["Notion"]], "and it launches again once the mode is left")


def test_sections_fold_by_their_title():
    """Раздел сворачивается щелчком по названию, стрелка — слева от него.

    Одного раздела не свернуть, а в категории его заголовок не повторяет
    заголовок панели слева.
    """
    problem = _ui_ready()
    if problem:
        skip("section head test", problem)
        return
    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store, chat, _ids = _library(d)
        ui, _ = _ui_for(store)
        heads = [c for c in _walk(ft.Column(ui.content_col.controls))
                 if isinstance(c, ft.Container) and c.tooltip in ("Свернуть", "Развернуть")]
        ok(len(heads) == 2, "each of the two sections can be folded")
        label = heads[1]
        row = label.content.controls
        ok(isinstance(row[0], ft.Icon) and row[0].icon == ft.Icons.EXPAND_MORE_ROUNDED,
           "the arrow sits left of the name, not 1000 px away at the edge")
        ok("Общение" in _texts(label), "and the whole title is what is clicked")
        label.on_click(types_ns(control=label))
        ok(chat in ui.view.collapsed, "a click on the title folds the section")
        shown = _texts(ft.Column(ui.content_col.controls))
        ok("Telegram" not in shown and "1" in _texts(label),
           "its tiles go, and the title says how many are inside")

        ui._set_filter(f"category:{chat}")
        shown = _texts(ft.Column(ui.content_col.controls))
        ok(shown.count("Общение") == 0,
           "a category's only section has no title — the sidebar already says it")
        ok("Telegram" in shown, "and it can't be folded away: there is nothing else to see")
        ok("Общение" in _texts(ui.sidebar_container), "the sidebar title carries the name")


def test_running_and_missing_marks_sit_on_the_icon():
    """«Открыто» — точка под значком, как в Dock; пропавший файл — знак и надпись.

    «Файл не найден» жил только 8 секунд в уведомлении — теперь он держится
    на самой плитке.
    """
    problem = _ui_ready()
    if problem:
        skip("tile marks test", problem)
        return
    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store, _chat, ids = _library(d)
        ui, _ = _ui_for(store)
        ui.set_running([ids["Excel"]])
        content = ft.Column(ui.content_col.controls)
        dots = [c for c in _walk(content) if isinstance(c, ft.Container)
                and c.width == 5 and c.bgcolor == C.TEXT_2]
        ok(len(dots) == 1, "a running program gets the Dock's dot under its name")
        ok("Excel · открыто" in _tips(content), "and its tooltip says so in words")

        ui.launcher.launch.return_value = {"ok": False,
                                           "error": "Файл не найден: /x/notion.exe"}
        ui._launch(ids["Notion"])
        ok(ids["Notion"] in ui.missing, "a launch that finds no file remembers it")
        content = ft.Column(ui.content_col.controls)
        ok("файл не найден" in _texts(content), "and the tile keeps saying so")
        ok(any(isinstance(c, ft.Container) and c.bgcolor == C.WARN for c in _walk(content)),
           "with a warning mark on its icon")
        ui.view.select_one(ids["Notion"])
        ui.refresh()
        ok("Найти файл…" in _texts(ui.inspector_overlay),
           "the panel's main button becomes «Найти файл…»")

        ui.launcher.launch.return_value = {"ok": True, "running": True}
        ui.launcher.running_ids.return_value = [ids["Notion"]]
        ui._launch(ids["Notion"])
        ok(ids["Notion"] not in ui.missing, "and the mark goes once it launches again")

        ui.set_missing(ids["Excel"], True)
        found = os.path.join(d, "excel.exe")
        with open(found, "w") as fh:
            fh.write("x")
        ui.scan.backfill_icons_async = lambda: None
        ui.relocating = ids["Excel"]
        ui.scan.file_picked(found)
        ok(ids["Excel"] not in ui.missing and store.get_app(ids["Excel"])["path"] == found,
           "«Найти файл…» takes the mark off as soon as the new path is picked")

        from app.platform.launcher import file_missing
        ok(file_missing({"path": os.path.join(d, "nope.exe")}), "a missing file is noticed")
        ok(not file_missing({"path": d}), "an existing one is not")
        ok(not file_missing({"path": "steam://rungameid/1"})
           and not file_missing({"path": "shell:AppsFolder\\X"})
           and not file_missing({"path": "\\\\server\\share\\a.exe"})
           and not file_missing({"path": "https://x.com", "kind": "web"}),
           "addresses, shell: and network paths are never checked")


def test_sidebar_has_one_selection_mark_and_keeps_colours():
    """В боковой панели «выбрано» одно, и категория своего цвета не теряет."""
    problem = _ui_ready()
    if problem:
        skip("sidebar test", problem)
        return
    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store, chat, _ids = _library(d)
        store.update_category(chat, {"color": "#4f7dff", "icon": "chat"})
        ui, _ = _ui_for(store)

        def marks():
            return [c for c in _walk(ui.sidebar_container) if isinstance(c, ft.Container)
                    and c.bgcolor == C.RAISED and c.height in (C.SIDEBAR_ROW_H, 36)]

        ok(ui.view.sidebar_open and len(marks()) == 1,
           "one row is marked — «Все программы»")
        ui._set_filter(f"category:{chat}")
        ok(len(marks()) == 1, "picking a category moves the mark there")
        icons = [c for c in _walk(ui.sidebar_container) if isinstance(c, ft.Icon)
                 and c.icon == ft.Icons.CHAT_ROUNDED]
        ok(icons and icons[0].color == "#4f7dff",
           "and the picked category keeps its own colour instead of turning grey")

        ok(not any(t.startswith("v") and t[1:2].isdigit() for t in _texts(ui.sidebar_container)),
           "the 1.8:1 version number left the sidebar — it lives in the settings")

        ui.set_sidebar_open(False)
        ok(len(marks()) == 1, "folded to icons, the panel still marks one row")
        ok(not _texts(ui.sidebar_container), "and shows no labels")
        ok("Общение" in _tips(ui.sidebar_container),
           "the names move into tooltips")


def test_toolbar_add_is_calm_and_buttons_are_three_kinds():
    """«Добавить» на непустой библиотеке — второстепенная кнопка.

    Самое яркое пятно в окне уводило взгляд от плиток к действию, которым после
    первой настройки почти не пользуются. Залитая остаётся в пустом состоянии.
    """
    problem = _ui_ready()
    if problem:
        skip("toolbar test", problem)
        return
    import flet as ft

    with tempfile.TemporaryDirectory() as d:
        store, _chat, _ids = _library(d)
        ui, _ = _ui_for(store)
        filled = [c for c in _walk(ui.toolbar_holder) if isinstance(c, ft.Container)
                  and c.bgcolor == ui._accent()]
        ok(not filled, "nothing in the toolbar is filled with the accent")
        ok("Найти и добавить программы" in _tips(ui.toolbar_holder),
           "«Добавить» is still there, a calm «+» in the title bar")

        empty = Store(os.path.join(d, "empty.json"))
        empty_ui, _ = _ui_for(empty)
        ui.scan.wants_suggestions = lambda: False
        empty_ui.scan.suggestions = lambda: []
        empty_ui.refresh()
        filled = [c for c in _walk(ft.Column(empty_ui.content_col.controls))
                  if isinstance(c, ft.Container) and c.bgcolor == empty_ui._accent()]
        ok(filled, "an empty library still gets the filled button — it is the only way on")

    from helpers import _sources
    links = [label for label, src in _sources("ui") if "link_btn(" in src
             and not label.endswith("widgets.py")]
    ok(not links, f"underlined links are gone from inside the window ({links})")


def test_shift_f10_opens_the_selected_tile_menu():
    problem = _ui_ready()
    if problem:
        skip("context key test", problem)
        return
    with tempfile.TemporaryDirectory() as d:
        store, _chat, _ids = _library(d)
        ui, _ = _ui_for(store)
        ui.keymap.handle_key(_key("F10", shift=True))
        ok(not ui.menu.open, "with nothing picked Shift+F10 does nothing")
        ui.keymap.handle_key(_key("Arrow Right"))
        ui.keymap.handle_key(_key("F10", shift=True))
        ok(ui.menu.open and "Свойства…" in _menu_labels(ui),
           "after the arrows it opens the menu of the picked tile")
        ui.menu.close()
        ui.keymap.handle_key(_key("Context Menu"))
        ok(ui.menu.open, "and so does the keyboard's menu key")


def test_rename_from_the_menu_focuses_the_name():
    problem = _ui_ready()
    if problem:
        skip("rename test", problem)
        return
    with tempfile.TemporaryDirectory() as d:
        store, _chat, ids = _library(d)
        ui, _ = _ui_for(store)
        focused = []
        ui._focus = focused.append
        ui.context_menus.app_menu(store.get_app(ids["Excel"]), _tap())
        rename = next(r for r in ui.menu._rows if r.get("label") == "Переименовать")
        ui.menu._fire(rename)
        ok(ui.view.inspector == ids["Excel"], "«Переименовать» opens the panel")
        ok(focused and focused[-1] is ui.inspector_panel.name_field
           and focused[-1].value == "Excel", "with the cursor in the name field")


def test_toasts_stack_in_the_corner_and_keep_their_undo():
    try:
        from app.ui.toast import ToastHost
    except Exception as exc:
        skip("toast stack test", exc)
        return
    from helpers import _FakePage

    host = ToastHost(_FakePage())
    undone = []
    host.show("Notion убран", action=lambda: undone.append(1))
    host.show("Закреплено · Ctrl+2")
    ok(host.text.value == "Закреплено · Ctrl+2", "the newest toast is the live one")
    ok(len(host.stack.controls) == 2 and host.stack.controls[-1] is host.card,
       "the earlier one stays above it while its countdown runs")
    older = host._older[0]
    ok("Notion убран" in _texts(older.card) and "Вернуть" in _texts(older.card),
       "still offering «Вернуть»")
    host._fire_older(older)
    ok(undone == [1], "which still works — a new toast doesn't take the undo away")
    ok(len(host.stack.controls) == 1, "and the stack shrinks back")
    for n in range(4):
        host.show(f"Новость {n}")
    ok(len(host.stack.controls) <= 3, "at most three toasts are on screen at once")
    host.lift(True)
    ok(host.control.bottom > 56, "they step above the select-mode bar")
    host.stop()


def test_light_theme_builds_every_screen():
    """Светлое оформление собирает все экраны без белого на белом."""
    problem = _ui_ready()
    if problem:
        skip("light theme test", problem)
        return
    import flet as ft

    from app.ui import theme

    with tempfile.TemporaryDirectory() as d:
        store, _chat, ids = _library(d)
        rec = store.add_set("Утро", [ids["Notion"], ids["Telegram"]])
        store.queue_inbox([{"name": "Krita", "path": "C:/krita.exe"}])
        ui, page = _ui_for(store)
        try:
            ui.set_setting("appearance", "light")
            ok(C.MODE == "light" and page.theme_mode == ft.ThemeMode.LIGHT,
               "the whole window switches")
            ok(ui._accent() == C.ACCENT and C.contrast(ui._accent(), C.BG) >= 3,
               "the default blue accent reads on the light window as it is")
            ok(C.on_color(ui._accent()) == C.WHITE, "with white text on it")
            ui.set_setting("accent", "#f5f5f7")
            ok(ui._accent() == C.TEXT, "a white accent turns dark instead of white-on-white")
            ui.set_setting("accent", C.ACCENT)
            for open_screen in (ui.back_to_grid, ui.open_triage, ui._open_settings,
                                lambda: ui._open_set(rec["id"]),
                                lambda: ui._select_tile(ids["Excel"])):
                open_screen()
                ok(ui.content_col.controls, "every screen builds in the light theme")
            accent = ui._accent()

            def white_text(node, on_accent=False, depth=0):
                if node is None or isinstance(node, str) or depth > 40:
                    return []
                on_accent = on_accent or getattr(node, "bgcolor", None) == accent
                found = []
                if isinstance(node, ft.Text) and node.color in (C.WHITE, "#ffffff") \
                        and not on_accent:
                    found.append(node.value)
                for child in (getattr(node, "controls", None) or []):
                    found += white_text(child, on_accent, depth + 1)
                return found + white_text(getattr(node, "content", None), on_accent,
                                          depth + 1)

            for open_screen in (ui.back_to_grid, ui._open_settings,
                                lambda: ui._open_set(rec["id"])):
                open_screen()
                ok(not white_text(ui.body),
                   "no text is painted white on the light window, except on the accent")

            ui.set_setting("appearance", "system")
            ok(C.MODE == "dark", "«Как в Windows» without a brightness from Flutter is dark")
            page.platform_brightness = ft.Brightness.LIGHT
            ui.refresh()
            ok(C.MODE == "light", "and follows Windows once it says it is light")
        finally:
            theme.reset_theme()


def test_messengers_go_to_the_chat_category():
    """WhatsApp и Zoom — в «Общение», если оно есть; «Работа» — только запасная."""
    cats = [{"id": "work", "name": "Работа"}, {"id": "c", "name": "Общение"},
            {"id": "b", "name": "Браузеры"}, {"id": "m", "name": "Музыка и видео"}]

    def where(name):
        cid = queries.suggest_category({"name": name, "path": f"C:/x/{name}.exe"}, cats)
        return next(c["name"] for c in cats if c["id"] == cid)

    for name in ("WhatsApp", "Zoom", "Telegram", "Discord", "Microsoft Teams"):
        ok(where(name) == "Общение", f"{name} goes to «Общение»")
    ok(where("Google Chrome") == "Браузеры" and where("Firefox") == "Браузеры",
       "browsers find «Браузеры»")
    ok(where("Spotify") == "Музыка и видео", "a player finds the media category by its name")
    ok(where("Something Unknown") == "Работа", "and the unknown falls back to «Работа»")
    no_chat = [c for c in cats if c["id"] != "c"]
    cid = queries.suggest_category({"name": "Zoom", "path": "C:/x/zoom.exe"}, no_chat)
    ok(cid == "work", "without «Общение» Zoom still finds a sensible home")
    ok(queries.suggest_category({"name": "Digital Paint", "path": "C:/x/dp.exe"},
                                [{"id": "d", "name": "Разработка"}] + cats) != "d",
       "«digital» is not mistaken for git and sent to development")


def test_one_add_field_tells_a_name_from_a_path():
    from app.core.text import looks_like_target

    for text in (r"C:\Program Files\x.exe", "C:/x", r"\\server\share", "%APPDATA%\\x",
                 "youtube.com", "https://ya.ru"):
        ok(looks_like_target(text), f"«{text}» is a path or an address")
    for text in ("telegram", "vs code", "obs.exe", ""):
        ok(not looks_like_target(text), f"«{text}» is a name to look for")
