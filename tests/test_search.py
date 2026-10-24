"""Поиск: ранжирование, раскладка и кириллица, другие имена, палитра."""
import os
import tempfile
import time

from helpers import _find_control, _key, _texts, _ui_for, ft, ok, skip, types_ns

from app.core.store import Store


def test_search_ranks_without_noise():
    """Короткий запрос не тащит пол-библиотеки, чужая раскладка не обгоняет прямое.

    Первая версия «умного» поиска сверяла каждый запрос и в другой
    раскладке, и с транслитом имени: «t» → «е» находило «е» почти в любом
    имени по-русски (469 из 500 программ), а «v» → «м» ставило первым
    Manager («менеджер»).
    """
    from app.core import queries
    from app.core.text import match_rank, match_spans

    ok(match_rank("Steam", "t") is None, "one letter inside a word is not a match")
    ok(match_rank("Telegram", "t") == 0, "one letter at the start is")
    ok(match_rank("Manager", "v") is None, "a Latin letter is not read as Cyrillic")
    ok(match_rank("Telegram", "еуд") == match_rank("Telegram", "tel") + 5,
       "the other keyboard layout still finds it, but ranks below a direct match")
    ok(match_rank("Google Chrome", "хром") == 1, "Cyrillic spelling of a Latin name is direct")

    apps = [{"id": str(i), "name": f"Tool {i}", "category_id": "work"} for i in range(30)]
    cats = [{"id": "work", "name": "Работа"}]
    ok(len(queries.search_rows(apps, "tool", set(), cats)) == queries.PALETTE_LIMIT,
       "the palette shows a screenful of the best matches, not all thirty")
    ok(queries.search_rows(apps, "р", set(), cats) == [],
       "one letter of a category name does not list the whole category")
    ok(len(queries.search_rows(apps, "раб", set(), cats)) == queries.PALETTE_LIMIT,
       "three letters of it do")

    def lit(name, q):
        return "".join(t for t, hit in match_spans(name, q) if hit)
    ok(lit("VS Code", "code") == "Code", "a plain hit is highlighted")
    ok(lit("Telegram", "еуд") == "Tel", "so is a hit typed in the other layout")
    ok(lit("Visual Studio Code", "vsc") == "VSC", "and the first letters of an acronym hit")


def test_search_aliases_and_frecency():
    """«пс» находит Photoshop, а из равных совпадений первым идёт то, чем пользуются."""
    from app.core import queries
    from app.core.store import sanitize

    ok(sanitize.clean_aliases("пс, фотошоп, ПС, ,  ") == ["пс", "фотошоп"],
       "other names are split on commas, trimmed and deduplicated")
    ok(sanitize.clean_aliases(None) == [] and sanitize.clean_aliases([1, "a"]) == ["a"],
       "and junk in the file is dropped")

    cats = [{"id": "work", "name": "Работа"}]
    day = 86_400_000
    now = int(time.time() * 1000)
    apps = [
        {"id": "ps", "name": "Adobe Photoshop 2025", "aliases": ["пс", "фотошоп"],
         "category_id": "work"},
        {"id": "remote", "name": "PS Remote Play", "category_id": "work"},
        {"id": "tg", "name": "Telegram", "category_id": "work"},
        {"id": "teams", "name": "Microsoft Teams", "category_id": "work",
         "launch_count": 9, "launches": [now - day] * 9, "last_launched": now - day},
        {"id": "old", "name": "Old Editor", "category_id": "work", "launch_count": 50,
         "launches": [now - 200 * day] * 10, "last_launched": now - 200 * day},
        {"id": "new", "name": "Oxygen Editor", "category_id": "work", "launch_count": 6,
         "launches": [now - day] * 6, "last_launched": now - day},
    ]

    def ids(q):
        return [r["app"]["id"] for r in queries.search_rows(apps, q, set(), cats)]

    rows = queries.search_rows(apps, "пс", set(), cats)
    ok(rows and rows[0]["app"]["id"] == "ps",
       f"an other name typed in full beats a name that merely starts so ({ids('пс')})")
    ok(rows[0]["via"] == "пс" and queries.app_palette_sub(rows[0]).startswith("«пс»"),
       "and the palette says which other name matched")
    ok(ids("фото")[:1] == ["ps"], "an other name matches by its start, too")
    ok(ids("te")[:2] == ["teams", "tg"],
       "between a name start and a word start, the program in use wins")
    ok(ids("editor")[:2] == ["new", "old"],
       "six launches this week outweigh fifty half a year ago")
    ok(ids("tel")[:1] == ["tg"], "frecency never drags in what the query does not match")

    fresh = [{"id": "a", "name": "Microsoft Teams", "category_id": "work"},
             {"id": "b", "name": "Telegram", "category_id": "work"}]
    ok([r["app"]["id"] for r in queries.search_rows(fresh, "te", set(), cats)] == ["b", "a"],
       "with nothing launched yet, a name start still comes before a word start")

    ok([a["key"] for a in queries.palette_actions({"kind": "web"})] == ["set"],
       "a site has no folder and no admin mode in the palette")
    ok([a["label"] for a in queries.palette_actions({"kind": "folder"})][0] == "Показать в папке",
       "a folder is shown in its parent, not «the program's folder»")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        rec = store.add_app({"name": "Photoshop", "path": "C:/ps.exe", "aliases": "пс"})
        ok(store.get_app(rec["id"])["aliases"] == ["пс"], "a new record keeps its other names")
        store.update_app(rec["id"], {"aliases": "пс, фш"})
        ok(store.get_app(rec["id"])["aliases"] == ["пс", "фш"], "and they can be edited")
        for _ in range(sanitize.MAX_LAUNCHES + 3):
            store.mark_launched(rec["id"])
        app = store.get_app(rec["id"])
        ok(len(app["launches"]) == sanitize.MAX_LAUNCHES and app["launch_count"] == 13,
           "only the latest launches are remembered, the count keeps growing")


def test_ui_aliases_field():
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI aliases test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        rec = store.add_app({"name": "Adobe Photoshop", "path": "C:/ps.exe",
                             "category_id": "work"})
        ui, _ = _ui_for(store)
        ui.view.inspector = rec["id"]
        panel = ui.inspector_panel.build_inspector()
        ok("Другие имена" in _texts(panel), "the inspector offers other names for search")
        field = _find_control(panel, lambda c: isinstance(c, ft.TextField)
                              and "фотошоп" in (c.tooltip or ""))
        ok(field is not None, "as a plain text field")
        ui.set_aliases(rec["id"], "пс, фш")
        ok(store.get_app(rec["id"])["aliases"] == ["пс", "фш"], "typing there saves them")
        ui.view.query = "фш"
        ok([r["app"]["id"] for r in ui._palette_rows() if r.get("kind") != "set"][:1]
           == [rec["id"]], "and the palette finds the program by them")


def test_search_field_keeps_focus_and_order():
    """Строка поиска не теряет фокус, выделение не уезжает за мышью.

    Щелчок по строке открывал палитру полной перерисовкой: шапка собиралась
    заново, строка поиска на стороне Flutter создавалась новой — без фокуса,
    и набранное шло в никуда. Палитра лежала поверх шапки и забирала
    повторный щелчок по строке. А строки палитры, перестроенные под
    неподвижным курсором, «наводились» и уводили выделение с лучшего
    совпадения — Enter запускал не то.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("search focus test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        for name in ("Telegram", "Teams", "Notion"):
            store.add_app({"name": name, "path": f"/x/{name}", "category_id": "work"})
        ui, _ = _ui_for(store)
        header = ui.header_holder.content
        ui._open_palette()
        ui.refresh()
        ok(ui.header_holder.content is header,
           "opening the palette and redrawing keep the very same header and search row")
        ui.set_setting("accent", "#5ea2ff")
        ok(ui.header_holder.content is not header, "only a theme change rebuilds it")

        ui._on_search(types_ns(control=types_ns(value="te")))
        ok(ui.view.palette_index == 0, "typing puts the best match first")
        ui.palette_hover(1, types_ns(data=True))
        ok(ui.view.palette_index == 0,
           "a row that appeared under a resting pointer does not steal the selection")
        ui._palette_keyed_at = 0.0
        ui.palette_hover(1, types_ns(data=True))
        ok(ui.view.palette_index == 1, "a real move of the mouse still does")

        launched = []
        ui._launch = lambda app_id, **kw: launched.append(store.get_app(app_id)["name"])
        ui.search_field.value = "not"
        ui.keymap.handle_key(_key("Enter"))
        ok(launched == ["Notion"],
           "Enter goes by what is in the field even if its on_change is still queued")


def test_arrow_keys_skip_collapsed_sections():
    """Стрелки не уходят в свёрнутую категорию, Enter не запускает невидимое."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("collapsed navigation test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        hidden_cat = store.add_category("Свёрнутая")
        shown = store.add_app({"name": "A", "path": "/x/a", "category_id": "work"})["id"]
        store.add_app({"name": "B", "path": "/x/b", "category_id": hidden_cat["id"]})
        ui, _ = _ui_for(store)
        ui._toggle_section(hidden_cat["id"])
        ok([a["id"] for a in ui._flat_apps()] == [shown], "a collapsed section's tiles are out")
        ui.move_selection(1)
        ui.move_selection(1)
        ok(ui._flat_apps()[ui.view.selected]["id"] == shown,
           "so the selection stays on what is actually shown")
        ui.toggle_select_mode()
        ok(len(ui._flat_apps()) == 2, "select mode opens collapsed sections, and counts them")


def test_search_forgives_layout_and_cyrillic():
    """Поиск понимает не ту раскладку, русское написание и первые буквы.

    Раньше искалась только подстрока: «еуд» (набрано вместо «tel»), «хром»,
    «ворд» и «vsc» не находили ничего.
    """
    from app.core import queries

    apps = [{"id": n, "name": n, "category_id": "work", "launch_count": c}
            for n, c in (("Telegram", 0), ("Google Chrome", 0), ("Microsoft Word", 0),
                         ("Visual Studio Code", 0), ("Notepad", 3), ("Notion", 9))]

    def first(q):
        rows = queries.search_rows(apps, q, set(), [{"id": "work", "name": "Работа"}])
        return [r["app"]["name"] for r in rows]

    ok(first("еуд")[:1] == ["Telegram"], "a query typed in the Russian layout still finds it")
    ok(first("телег")[:1] == ["Telegram"], "so does the name spelled in Cyrillic")
    ok(first("хром")[:1] == ["Google Chrome"], "«хром» finds Chrome")
    ok(first("ворд")[:1] == ["Microsoft Word"], "«ворд» finds Word")
    ok(first("vsc")[:1] == ["Visual Studio Code"], "first letters of the words find it too")
    ok(first("not") == ["Notion", "Notepad"],
       "equally good matches go by how often they were launched")
    ok(first("zzz") == [], "and nonsense finds nothing")


def test_queries():
    from app.core import queries
    from app.core.view_state import ViewState

    cats = [{"id": "work", "name": "Work", "order": 0}, {"id": "games", "name": "Games", "order": 1}]
    apps = [
        {"id": "1", "name": "Notion", "category_id": "work", "favorite": True, "last_launched": 100},
        {"id": "2", "name": "Chrome", "category_id": "work", "last_launched": 200},
        {"id": "3", "name": "CS2", "category_id": "games"},
        {"id": "4", "name": "Orphan", "category_id": "missing"},
    ]
    running = {"2"}

    ok(queries.valid_filter("category:missing", cats) == "all", "valid_filter drops a dead category")
    ok(queries.valid_filter("category:work", cats) == "category:work", "valid_filter keeps a live category")
    ok(queries.valid_filter("favorites", cats) == "favorites", "valid_filter passes non-category filters through")

    fav = queries.build_sections(apps, cats, "favorites", "alpha", running)
    ok([a["id"] for a in fav[0]["apps"]] == ["1"], "favorites section holds only favourited apps")

    run = queries.build_sections(apps, cats, "running", "alpha", running)
    ok([a["id"] for a in run[0]["apps"]] == ["2"], "running section matches the running-ids set")

    rec = queries.build_sections(apps, cats, "recent", "alpha", running)
    ok([a["id"] for a in rec[0]["apps"]] == ["2", "1"], "recent section sorts by last_launched, newest first")

    cat_sec = queries.build_sections(apps, cats, "category:games", "alpha", running)
    ok([a["id"] for a in cat_sec[0]["apps"]] == ["3"], "category section holds only that category's apps")

    all_sec = queries.build_sections(apps, cats, "all", "alpha", running)
    ok("Без категории" in [s["name"] for s in all_sec],
       "an app whose category was deleted gets its own section instead of being dropped")


    ok(queries.current_title("category:games", cats) == "Games",
       "current_title resolves a category name")
    ok(queries.current_title("all", cats) == "Все программы",
       "and names the all-apps view for the sidebar heading")
    ok(queries.current_title("hidden", cats) == "Скрытые",
       "including the view that «Скрыть» files things into")

    buried = apps + [{"id": "5", "name": "Buried", "category_id": "work", "hidden": True}]
    shown = queries.build_sections(buried, cats, "all", "alpha", running)
    ok("Buried" not in [a["name"] for s in shown for a in s["apps"]],
       "a hidden app is out of the grid")
    only = queries.build_sections(buried, cats, "hidden", "alpha", running)
    ok([a["name"] for a in only[0]["apps"]] == ["Buried"],
       "and the «Скрытые» view is where it can be found again")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        store.add_category("Work")
        wid = store.state()["categories"][0]["id"]
        store.set_setting("view_filter", f"category:{wid}")
        vs = ViewState(store)
        ok(vs.filter == f"category:{wid}", "ViewState restores a persisted, still-valid filter")

        vs.set_filter("favorites")
        ok(store.state()["settings"]["view_filter"] == "favorites", "set_filter persists immediately")

        # is_all_view drives the rail's "Главное меню" highlight, and it used
        # to light up for every non-category filter.
        vs.set_filter("all")
        ok(vs.is_all_view() is True, "the all-apps view is the all view")
        for other in ("favorites", "recent", "running", f"category:{wid}"):
            vs.set_filter(other)
            ok(vs.is_all_view() is False, f"{other} is not the all view")

        vs.move_selection(1, 3)
        ok(vs.selected == 0, "move_selection picks the first item from nothing selected")
        vs.move_selection(1, 3)
        ok(vs.selected == 1, "move_selection advances by one")
        vs.move_selection(-5, 3)
        ok(vs.selected == 0, "move_selection clamps at the start")

        vs.set_filter(f"category:{wid}")
        store.data["categories"] = []
        vs.revalidate(store.state()["categories"])
        ok(vs.filter == "all", "revalidate falls back once the active category is gone")

    # Category suggestions ("games" for a Steam app, say) name a *kind* of
    # category, not a literal id — they only match straight through while
    # the built-in "games"/"dev"/"create" category is still around.
    steam_item = {"name": "Half-Life", "path": "steam://rungameid/70", "source": "steam"}
    ok(queries.suggest_category(steam_item, [{"id": "games", "name": "Игры"},
                                             {"id": "work", "name": "Работа"}]) == "games",
       "the id match still wins when the default category is there")

    ok(queries.suggest_category(steam_item, [{"id": "aaa", "name": "Работа"},
                                             {"id": "bbb", "name": "Мои игрули"}]) == "bbb",
       "gone (renamed/replaced), it falls back to a same-ish-named category by name")

    ok(queries.suggest_category(steam_item, [{"id": "aaa", "name": "Gaming Rig"},
                                             {"id": "bbb", "name": "Work"}]) == "aaa",
       "the name match isn't tied to Russian either")

    ok(queries.suggest_category(steam_item, [{"id": "work", "name": "Работа"},
                                             {"id": "misc", "name": "Разное"}]) == "work",
       "and when nothing matches by id or name, it falls back to the first "
       "category in the list rather than staying stuck on the missing default")

    outlook_item = {"name": "Outlook", "path": "C:/Program Files/Outlook.exe"}
    ok(queries.suggest_category(outlook_item, [{"id": "aaa", "name": "Игры"},
                                               {"id": "bbb", "name": "Офис"}]) == "bbb",
       "office/productivity apps are recognised as a category kind too, not just games/dev/create")


def test_ui_search_palette():
    """Палитра поиска вместо окна «Запуск»: тот же лончер, одно окно."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI palette test", exc)
        return

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        code = store.add_app({"name": "VS Code", "path": "/x/code.exe",
                              "category_id": "dev", "quick": True})["id"]
        other = store.add_app({"name": "Notion", "path": "/x/n.exe",
                               "category_id": "work"})["id"]
        store.mark_launched(other)
        store.add_set("Утро", [code, other])
        ui, _ = _ui_for(store)

        ok(not ui.view.palette_open, "the library opens without the palette")
        ok(not ui.palette_layer.visible, "so nothing covers it")

        ui.toggle_search()
        ok(ui.view.palette_open and ui.palette_layer.visible,
           "the search hotkey opens the palette over the library")
        shown = _texts(ui.palette_layer)
        ok("ПРОГРАММЫ" in shown and "НАБОРЫ" in shown
           and any(t.startswith("ДЕЙСТВИЯ · ") for t in shown),
           "which comes in three groups, the actions naming whose they are")
        ok("Notion" in shown, "an empty query offers what was launched recently")
        ok("Утро" in shown, "and the sets")

        # Первое Ctrl+Пробел на чистой библиотеке не должно открывать пустоту.
        from app.core import queries
        fresh = Store(os.path.join(d, "fresh.json"))
        fresh.add_app({"name": "Пусто", "path": "/x/p.exe", "category_id": "work"})
        rows = queries.search_rows(fresh.state()["apps"], "", set(),
                                   fresh.state()["categories"])
        ok([r["app"]["name"] for r in rows] == ["Пусто"],
           "with nothing launched yet it falls back to what the library has")
        ok("Enter" in shown, "the highlighted row says what runs it")
        ok(not any("выбрать" in t for t in shown),
           "the palette's own key-hint footer is a pure hint — stays gone")

        ok(ui.content_col.controls, "the grid behind it is still built")
        ui.search_field.value = "code"
        ui._on_search(types_ns(control=types_ns(value="code")))
        shown = _texts(ui.palette_layer)
        # Совпавшая часть названия вынесена в свой span, чтобы её подсветить.
        ok("Code" in shown and "VS " in shown, "typing filters the palette")
        ok("Notion" not in shown, "to the matches only")
        grid = _texts(ft.Column(ui.content_col.controls))
        ok("Notion" in grid, "while the grid behind deliberately does not re-sort")

        ui.keymap.handle_key(_key("Tab"))
        ok(ui.view.palette_focus == "actions", "Tab moves into the actions")
        ok("ДЕЙСТВИЯ · VS CODE" in _texts(ui.palette_layer),
           "the actions say which program they are for — the row lost its highlight")
        ui.keymap.handle_key(_key("Tab"))
        ok(ui.view.palette_focus == "results", "and back out")

        hidden = []
        ui.controllers["hide_to_tray"] = lambda: hidden.append(1)
        ui.launcher.launch.return_value = {"ok": True, "running": True}
        ui.launcher.running_ids.return_value = [code]
        ui.keymap.handle_key(_key("Enter"))
        ok(ui.launcher.launch.called, "Enter launches the highlighted row")
        ok(hidden == [1], "and the window hides itself")
        ok(ui.view.query == "" and not ui.view.palette_open,
           "with the palette closed and the query cleared for next time")

        ui.set_setting("hide_after", False)
        hidden.clear()
        ui.toggle_search()
        ui._on_search(types_ns(control=types_ns(value="code")))
        ui.keymap.handle_key(_key("Enter"))
        ok(hidden == [], "unless «Прятать окно после запуска» is off")

        ui.toggle_search()
        ui.keymap.handle_key(_key("Escape"))
        ok(not ui.view.palette_open, "Esc closes the palette")
        ok(hidden == [], "and stays in the library instead of hiding the window")
        ui.keymap.handle_key(_key("Escape"))
        ok(hidden == [1], "the second Esc puts the window away")

        ui.keymap.handle_key(_key("k", ctrl=True))
        ok(ui.view.palette_open, "Ctrl+K opens it when the window is already up")
        ok(ui.toggle_search() is False, "and the hotkey again puts it away")
