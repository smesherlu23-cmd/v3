"""Хранилище библиотеки: запись на диск, проверка файла, копии, разбор."""
import os
import tempfile
import time

from helpers import _ui_for, ok, skip

from app.core.store import Store, hue_from_string
from app.ui import colors as C
from app.ui import iconify


def test_store():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)
        ok(len(s.state()["categories"]) == 1, "seeds a single «Новая» category")
        ok(s.state()["apps"] == [], "starts with no apps")

        a = s.add_app({"name": "VS Code", "path": "/usr/bin/code", "category_id": "dev"})
        ok(bool(a["id"]), "add_app returns id")
        ok(0 <= a["hue"] < 360, "hue in range")

        s.update_app(a["id"], {"favorite": True, "sub": "Редактор"})
        ok(s.get_app(a["id"])["favorite"] is True, "favorite toggled")
        ok(s.get_app(a["id"])["sub"] == "Редактор", "sub updated")

        ok(a.get("track_exe") is None, "track_exe defaults to None")
        s.update_app(a["id"], {"track_exe": "code.exe"})
        ok(s.get_app(a["id"])["track_exe"] == "code.exe", "track_exe updated")

        ok(a.get("poster") is None, "poster defaults to None")
        s.update_app(a["id"], {"poster": "/x/poster.jpg"})
        ok(s.get_app(a["id"])["poster"] == "/x/poster.jpg", "poster updated")

        ok(a.get("working_dir") == "" and a.get("run_as_admin") is False,
           "launch options default empty/false")
        s.update_app(a["id"], {"args": ["--x"], "working_dir": "/tmp", "run_as_admin": True})
        got = s.get_app(a["id"])
        ok(got["args"] == ["--x"] and got["working_dir"] == "/tmp" and got["run_as_admin"] is True,
           "launch options updated")

        b = s.add_app({"name": "Zed", "path": "/z", "category_id": "dev"})
        s.reorder_apps([b["id"], a["id"]])
        ok(s.get_app(b["id"])["order"] == 0 and s.get_app(a["id"])["order"] == 1,
           "reorder_apps assigns order")
        s.remove_app(b["id"])

        s.set_setting("view_mode", "list")
        s.set_setting("view_filter", "favorites")
        ok(Store(path).state()["settings"]["view_mode"] == "list", "view_mode persisted")
        ok(Store(path).state()["settings"]["view_filter"] == "favorites", "view_filter persisted")

        s.mark_launched(a["id"])
        ok(s.get_app(a["id"])["launch_count"] == 1, "launch_count incremented")
        ok(s.get_app(a["id"])["last_launched"] > 0, "last_launched set")

        cat = s.add_category("Тест")
        ok(cat["color"] == "#ffffff", "a new category starts with the neutral colour")
        ok(C.category_color(cat) == "#ffffff",
           "which is the theme's own colour, not a placeholder to swap out")
        s.update_category(cat["id"], {"color": "#ff8800", "icon": "sports_esports"})
        got_cat = next(c for c in s.state()["categories"] if c["id"] == cat["id"])
        ok(got_cat["color"] == "#ff8800" and got_cat["icon"] == "sports_esports",
           "category colour + icon updated")

        s.move_category(cat["id"], -1)
        order_ids = [c["id"] for c in sorted(s.state()["categories"], key=lambda c: c["order"])]
        ok(order_ids.index(cat["id"]) == len(order_ids) - 2, "move_category shifts order")

        s.update_app(a["id"], {"category_id": cat["id"]})
        undo = s.remove_category(cat["id"])
        ok(undo is not None, "remove_category reports what it removed")
        ok(s.get_app(a["id"])["category_id"] == s.state()["categories"][0]["id"],
           "orphaned app reassigned")

        s.set_setting("bogus", 1)
        ok("bogus" not in s.state()["settings"], "unknown setting rejected")
        s.set_setting("accent", "#4f7dff")

        # set_setting used to hand back the live settings dict, so a caller
        # could edit the store's state behind the lock and without a write.
        returned = s.set_setting("tile_size", "compact")
        returned["tile_size"] = "mutated-from-outside"
        ok(s.state()["settings"]["tile_size"] == "compact",
           "mutating set_setting's return value doesn't reach the store")

        s2 = Store(path)
        ok(s2.state()["settings"]["accent"] == "#4f7dff", "reload keeps setting")
        ok(len(s2.state()["apps"]) == 1, "reload keeps app")
        s2.remove_app(a["id"])
        ok(len(s2.state()["apps"]) == 0, "app removed")

        ok(hue_from_string("Notion") == hue_from_string("Notion"), "hue deterministic")
        ok(0 <= hue_from_string("X") < 360, "hue bounded")


def test_store_sets_inbox_undo():
    """Наборы, очередь разбора и обратимость — то, что добавил редизайн."""
    with tempfile.TemporaryDirectory() as d:
        s = Store(os.path.join(d, "data.json"))
        create_cat = s.add_category("Творчество")
        one = s.add_app({"name": "Notion", "path": "/x/n", "category_id": "work"})
        two = s.add_app({"name": "Figma", "path": "/x/f", "category_id": create_cat["id"]})

        rec = s.add_set("Рабочее утро", [one["id"], two["id"], "no-such-app"])
        ok(rec is not None and rec["apps"] == [one["id"], two["id"]],
           "a set keeps only ids the library actually has")
        ok(rec["quick"] is True, "and lands in the quick-launch strip by default")
        ok(s.add_set("Пустой", ["ghost"]) is None, "a set with nothing real in it isn't stored")

        gone = s.remove_apps([one["id"]])
        ok([g["id"] for g in gone] == [one["id"]], "remove_apps hands back what it removed")
        ok(s.state()["sets"][0]["apps"] == [two["id"]],
           "a removed app leaves the sets it was in")
        ok(s.restore_apps(gone) == 1, "the record goes back in")
        ok(s.restore_apps(gone) == 0, "restoring twice doesn't duplicate it")

        ok(s.update_apps([one["id"], two["id"]], {"favorite": True}) == 2,
           "update_apps patches every id it was given in one write")

        undo = s.remove_category(create_cat["id"])
        ok(undo and two["id"] in undo["apps"], "remove_category reports the apps it moved")
        ok(s.restore_category(undo) is True, "and the category can be put back")
        ok(s.get_app(two["id"])["category_id"] == create_cat["id"], "with its apps in it")

        # ---- очередь разбора ----
        added = s.queue_inbox([
            {"name": "OBS", "path": "C:/obs.exe", "source": "startmenu"},
            {"name": "Notion", "path": "/x/n"},          # уже в библиотеке
            {"name": "OBS again", "path": "C:/obs.exe"},  # уже в очереди
        ])
        ok(added == 1, "queueing skips what the library and the queue already know")
        item = s.state()["inbox"][0]
        taken = s.take_inbox(item["id"])
        ok(taken and taken["name"] == "OBS", "an entry can be taken out of the queue")
        ok(not s.state()["inbox"], "and it is gone from it")
        ok(s.restore_inbox(taken) is True, "putting it back works")
        ok(s.restore_inbox(taken) is False, "but only once")

        s.queue_inbox([{"name": "Krita", "path": "C:/krita.exe"}])
        cleared = s.clear_inbox()
        ok(len(cleared) == 2 and not s.state()["inbox"], "«Отложить всё» empties the queue")
        for entry in cleared:
            s.restore_inbox(entry)
        ok(len(s.state()["inbox"]) == 2, "and every entry can be restored")

        # Программа, добавленная в библиотеку, не должна остаться в очереди.
        s.add_app({"name": "Krita", "path": "C:/krita.exe", "category_id": "work"})
        s.flush()
        ok(len(Store(s.path).state()["inbox"]) == 1,
           "on load the queue drops what has since been added")

        s.data["sets"] = [{"id": "dead", "name": "Dead", "apps": ["ghost"]}]
        s.flush()
        ok(Store(s.path).state()["sets"] == [],
           "a set that lost every member is dropped on load")


def test_store_set_layout():
    """Набор версии 3: порядок запуска, места окон, пауза, монитор."""
    import json

    from app.core import layout as L

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)
        one = s.add_app({"name": "One", "path": "/x/1", "category_id": "work"})["id"]
        two = s.add_app({"name": "Two", "path": "/x/2", "category_id": "work"})["id"]
        three = s.add_app({"name": "Three", "path": "/x/3", "category_id": "work"})["id"]

        rec = s.add_set("Утро", [one, two])
        ok([i["app_id"] for i in rec["items"]] == [one, two],
           "a set stores its members as items")
        ok(rec["apps"] == [one, two],
           "and keeps the plain id list as a mirror everything else can read")
        ok([i["slot"] for i in rec["items"]] == [0, 1],
           "new members take the places of the default preset in order")
        ok(rec["layout"]["preset"] == L.DEFAULT_PRESET, "which is the default one")
        ok(rec["delay_seconds"] == 2.0 and rec["monitor"] == 0
           and rec["close_together"] is False, "with the launch defaults")

        s.update_set(rec["id"], {"apps": [one, two, three]})
        ok(s.get_set(rec["id"])["items"][2]["slot"] == 2,
           "adding a member gives it the first free place")

        s.update_set_item(rec["id"], three, {"slot": 0})
        items = {i["app_id"]: i for i in s.get_set(rec["id"])["items"]}
        ok(items[three]["slot"] == 0 and items[one]["slot"] is None,
           "one place holds one program: taking it frees the previous owner")

        s.update_set_item(rec["id"], two, {"minimized": True})
        items = {i["app_id"]: i for i in s.get_set(rec["id"])["items"]}
        ok(items[two]["minimized"] and items[two]["slot"] is None,
           "a minimised member gives up its place")

        s.update_set(rec["id"], {"layout": {"preset": "full"}})
        places = [i["slot"] for i in s.get_set(rec["id"])["items"]]
        ok(places.count(None) == 2 and 0 in places,
           "switching to a one-window preset drops the places that no longer exist")

        # Выбор пресета — жест «разложи заново», поэтому места, которых не было
        # в прежнем пресете, достаются тем, кто остался без места.
        s.update_set_item(rec["id"], two, {"minimized": False})
        s.update_set(rec["id"], {"layout": {"preset": "grid4"}})
        places = [i["slot"] for i in s.get_set(rec["id"])["items"]]
        ok(None not in places and sorted(places) == [0, 1, 2],
           "a roomier preset hands its new places out")
        s.update_set_item(rec["id"], two, {"minimized": True})
        s.update_set(rec["id"], {"layout": {"preset": "half"}})
        s.update_set(rec["id"], {"layout": {"preset": "grid4"}})
        kept = {i["app_id"]: i for i in s.get_set(rec["id"])["items"]}
        ok(kept[two]["minimized"] and kept[two]["slot"] is None,
           "but a member that starts minimised is left out of it")

        s.update_set(rec["id"], {"layout": {"split": 9.0}, "delay_seconds": 99,
                                 "monitor": -3})
        fresh = s.get_set(rec["id"])
        ok(fresh["layout"]["split"] == L.MAX_SPLIT, "an impossible share is clamped")
        ok(fresh["delay_seconds"] == 30.0, "so is an absurd pause")
        ok(fresh["monitor"] == 0, "and a negative monitor becomes the default")

        s.move_set_item(rec["id"], three, -2)
        ok(s.get_set(rec["id"])["apps"][0] == three,
           "the launch order can be moved, clamped at the ends")

        s.update_set_item(rec["id"], one, {"slot": None})
        s.flush()
        ok(Store(path).get_set(rec["id"])["items"][1]["slot"] is None,
           "«без места» survives a reload instead of being handed a place again")

        # Файл версии 2 знал только список id — он должен получить раскладку.
        old = os.path.join(d, "v2.json")
        with open(old, "w", encoding="utf-8") as fh:
            json.dump({"version": 2,
                       "apps": [{"id": "a", "name": "A", "path": "/a"},
                                {"id": "b", "name": "B", "path": "/b"}],
                       "sets": [{"id": "s", "name": "Старый", "apps": ["a", "b", "gone"]}],
                       "categories": [], "settings": {}}, fh)
        migrated = Store(old).state()["sets"][0]
        ok([i["app_id"] for i in migrated["items"]] == ["a", "b"],
           "a version-2 set keeps its members and drops the dead one")
        ok([i["slot"] for i in migrated["items"]] == [0, 1],
           "and comes back with a layout instead of nothing")


def test_dismissed_programs_stay_dismissed():
    """«Не нужно» в разборе и удаление из библиотеки запоминаются.

    Раньше следующее сканирование (а с автопроверкой — каждые 15 минут)
    клало ту же программу обратно в очередь.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("dismiss test", exc)
        return

    found = [{"name": "Junk", "path": "C:/junk.exe"}, {"name": "Keep", "path": "C:/keep.exe"}]
    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)
        store.queue_inbox(found)
        junk = next(i for i in store.state()["inbox"] if i["name"] == "Junk")
        ui.triage.triage_drop(junk["id"])
        ok(store.is_ignored(junk), "«не нужно» puts the program on the ignore list")
        ok(store.queue_inbox(found) == 0, "and the next scan does not bring it back")

        ui.toast.fire_action()
        ok(not store.is_ignored(junk) and len(store.state()["inbox"]) == 2,
           "undo takes it off the list and back into the queue")

        keep = next(i for i in store.state()["inbox"] if i["name"] == "Keep")
        ui.triage.triage_place(keep["id"], "work")
        app = next(a for a in store.state()["apps"] if a["name"] == "Keep")
        ui._remove_apps([app["id"]])
        ok(store.queue_inbox(found) == 0, "a program removed from the library is not re-offered")
        ui.toast.fire_action()
        ok(not store.is_ignored(app), "until the removal is undone")

        store.ignore([{"path": "C:/later.exe"}])
        store.add_app({"name": "Later", "path": "C:/later.exe"})
        ok(not store.is_ignored({"path": "C:/later.exe"}),
           "adding a program by hand forgets that it was dismissed")

        reread = Store(os.path.join(d, "data.json"))
        ok(reread.state()["ignored"] == store.state()["ignored"], "the list survives a restart")

        # Отмена «положить в категорию» и отмена добавления — это «не сейчас»,
        # а не «никогда»: программа не должна попасть в список молча.
        store.queue_inbox([{"name": "Maybe", "path": "C:/maybe.exe"}])
        maybe = next(i for i in store.state()["inbox"] if i["name"] == "Maybe")
        ui.triage.triage_place(maybe["id"], "work")
        ui.toast.fire_action()
        ok(not store.is_ignored(maybe), "undoing a triage placement does not dismiss it")


def test_store_concurrency():
    import threading
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)
        errors = []

        def writer(i):
            try:
                for j in range(40):
                    s.add_app({"name": f"A{i}-{j}", "path": f"/x/{i}/{j}"})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ok(not errors, "concurrent writers raise nothing")
        ok(len(s.state()["apps"]) == 240, "every concurrent add is kept in memory")
        ok(len(Store(path).state()["apps"]) == 240, "the file on disk survives concurrent writes")
        leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
        ok(not leftovers, "no temp files are left behind")


def test_store_load_validation():
    """JSON that parses but carries junk must not blank the window.

    Corrupt files are quarantined by _load; this is the other half — records
    the UI indexes without a guard (id, name) or sorts on (order, added_at).
    """
    import json

    from app.core.store import DEFAULT_SETTINGS

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "version": "one",
                "categories": [{"id": "work", "name": "Работа", "order": 0},
                               {"name": "no id at all"},
                               "not even a dict",
                               {"id": "dup", "name": "First"},
                               {"id": "dup", "name": "Second"}],
                "apps": [
                    {"id": "good", "name": "Notion", "path": "/n", "order": 1},
                    {"name": "no id"},
                    {"id": "", "name": "empty id"},
                    None,
                    {"id": "nameless", "path": "/x"},
                    {"id": "junk-numbers", "name": "Junk", "order": "first",
                     "added_at": None, "last_launched": "yesterday", "hue": "blue"},
                    {"id": "good", "name": "Duplicate id"},
                ],
                "settings": ["not", "an", "object"],
            }, fh)

        state = Store(path).state()
        apps = [a for a in state["apps"] if isinstance(a, dict)]
        ok([a.get("id") for a in apps] == ["good", "nameless", "junk-numbers"],
           "unusable app records are dropped")
        ok(all(isinstance(a.get("name"), str) and a.get("name") for a in apps),
           "every surviving app has a usable name")
        by_id = {a.get("id"): a for a in apps}
        ok(by_id.get("nameless", {}).get("name") == "Без названия",
           "a nameless record gets the same placeholder as a new app")
        junk = by_id.get("junk-numbers", {})
        ok(all(isinstance(junk.get(k), int) for k in ("order", "added_at", "last_launched")),
           "non-numeric sort keys are coerced")
        ok(isinstance(junk.get("hue"), int) and 0 <= junk.get("hue", -1) < 360,
           "a bad hue is re-derived")
        cats = [c for c in state["categories"] if isinstance(c, dict)]
        ok([c.get("id") for c in cats] == ["work", "dup"],
           "unusable categories are dropped and ids deduped")
        from app.core.store.sanitize import UI_DEFAULTS_VERSION
        expected = {**DEFAULT_SETTINGS, "ui_defaults_version": UI_DEFAULTS_VERSION}
        ok(state["settings"] == expected,
           "settings that aren't an object fall back to the defaults "
           "(migrated to the current ui_defaults_version, same as a fresh install)")
        ok(state["version"] == 3, "the loaded file reports the current schema version")
        ok(state["sets"] == [] and state["inbox"] == [],
           "a file written before sets and triage existed loads with both empty")

        # set_setting() has always refused an unknown key (see "unknown setting
        # rejected" in test_store above); loading used to let one straight
        # through instead of filtering it the same way.
        path2 = os.path.join(d, "data2.json")
        with open(path2, "w", encoding="utf-8") as fh:
            json.dump({"apps": [], "settings": {"accent": "#123456", "legacy_flag_removed": True}},
                      fh)
        settings2 = Store(path2).state()["settings"]
        ok(settings2["accent"] == "#123456", "a known setting from disk is kept")
        ok("legacy_flag_removed" not in settings2,
           "an unknown key from disk is dropped, matching what set_setting() would do")
        ok(set(settings2) == set(DEFAULT_SETTINGS), "the settings schema is exactly the known keys")

        # The sanitised library must survive the operations the UI performs.
        from app.core import queries
        sections = queries.build_sections(state["apps"], state["categories"], "all", "alpha", set())
        ok(queries.flatten_sections(sections), "sanitised records render into sections")
        for sort in queries.SORT_KEYS:
            queries.sort_apps(state["apps"], sort)
        ok(True, "every sort order works on the sanitised records")


def test_store_get_app_returns_a_copy():
    """get_app hands out a snapshot, like get_set and state() already do."""
    with tempfile.TemporaryDirectory() as d:
        s = Store(os.path.join(d, "data.json"))
        app_id = s.add_app({"name": "Original", "path": "/a"})["id"]

        snapshot = s.get_app(app_id)
        snapshot["name"] = "Mutated from outside"
        snapshot["args"].append("--should-not-appear")
        ok(s.get_app(app_id)["name"] == "Original",
           "mutating the returned dict does not reach the store")
        ok(s.get_app(app_id)["args"] == [],
           "nor does mutating a nested list inside it")

        s.mark_launched(app_id)
        ok(s.get_app(app_id)["launch_count"] == 1,
           "the store's own internal update still lands (mark_launched)")

        updated = s.update_app(app_id, {"favorite": True})
        updated["favorite"] = False
        ok(s.get_app(app_id)["favorite"] is True,
           "and update_app's return value is a copy too, not the live record")

        ok(s.get_app("no-such-id") is None, "a missing id still returns None")

        # `state()` зовётся на каждый refresh, в том числе из фоновых потоков,
        # поэтому копия делается своим обходом вместо `copy.deepcopy` — втрое
        # дешевле. Изоляция от этого меняться не должна ни на одном уровне
        # вложенности.
        s.add_set("Утро", [app_id])
        snapshot = s.state()
        snapshot["apps"][0]["name"] = "Mutated"
        snapshot["apps"][0]["args"].append("--nope")
        snapshot["categories"][0]["name"] = "Mutated"
        snapshot["sets"][0]["items"][0]["slot"] = 99
        snapshot["settings"]["collapsed"].append("nope")

        fresh = s.state()
        ok(fresh["apps"][0]["name"] == "Original", "state() отдаёт копию верхнего уровня")
        ok(fresh["apps"][0]["args"] == [], "и вложенных списков")
        ok(fresh["categories"][0]["name"] != "Mutated", "и соседних разделов")
        ok(fresh["sets"][0]["items"][0]["slot"] != 99, "и записей на третьем уровне")
        ok(fresh["settings"]["collapsed"] == [], "и списков внутри настроек")


def test_store_refuses_to_downgrade_a_newer_file():
    """A file saved by a schema this build doesn't know gets backed up untouched."""
    import json

    from app.core.store import SCHEMA_VERSION

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        future = {"version": SCHEMA_VERSION + 1, "apps": [{"id": "a", "name": "Future App",
                  "path": "/f", "some_field_this_build_does_not_know": "keep me"}],
                  "categories": [], "settings": {}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(future, fh)

        s = Store(path)
        ok(s.newer_version == SCHEMA_VERSION + 1,
           "the store notices the file is from a newer schema")
        ok(s.state()["apps"][0]["name"] == "Future App",
           "it still loads what it can, best-effort, rather than going empty")

        backup = os.path.join(d, f"centurio-data.v{SCHEMA_VERSION + 1}.json")
        ok(os.path.exists(backup), "the untouched original is preserved alongside it")
        with open(backup, encoding="utf-8") as fh:
            saved = json.load(fh)
        ok(saved == future, "byte-for-byte, including the field this build can't parse")

        # Библиотека открывается на чтение. `_sanitize` оставляет только
        # понятные этой сборке ключи, поэтому любая запись стёрла бы всё
        # остальное — а копия оригинала создаётся один раз и вторую попытку
        # уже не подстрахует.
        ok(s.read_only is True, "файл более новой схемы открыт только на чтение")
        s.add_app({"name": "Added while read-only", "path": "/x", "category_id": "work"})
        ok(s.flush() is False, "сохранение отвечает отказом, а не молчаливым успехом")
        with open(path, encoding="utf-8") as fh:
            on_disk = json.load(fh)
        ok(on_disk == future, "и сам файл остаётся ровно таким, каким был")
        ok(len(s.state()["apps"]) == 2,
           "в памяти правка видна — интерфейс не притворяется, что ничего не произошло")

        ok(not os.path.exists(os.path.join(d, f"centurio-data.v{SCHEMA_VERSION + 2}.json")),
           "saving the now-sanitised state doesn't touch the backup again")
        with open(backup, encoding="utf-8") as fh:
            still_original = json.load(fh)
        ok(still_original == future, "копия оригинала тоже цела")

        ok(Store(os.path.join(d, "plain.json")).newer_version is None,
           "a fresh store with no file at all reports no version conflict")

        same_version = os.path.join(d, "same.json")
        with open(same_version, "w", encoding="utf-8") as fh:
            json.dump({"version": SCHEMA_VERSION, "apps": [], "categories": [], "settings": {}}, fh)
        ok(Store(same_version).newer_version is None,
           "a file at the current schema version is not flagged")


def test_store_load_rejects_non_object_json():
    """Valid JSON that isn't an object (e.g. a bare list) is quarantined, not crashed on."""
    import json

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([1, 2, 3], fh)

        raised = None
        try:
            state = Store(path).state()
        except Exception as exc:
            raised = exc
        ok(raised is None, "a non-object top level does not crash the store")
        ok(state["apps"] == [], "and the store falls back to an empty library")
        ok(any(n.startswith("centurio-corrupt-") for n in os.listdir(d)),
           "with the original quarantined for inspection, same as invalid JSON")


def test_store_write_failure():
    """A failing save must not take down the action that triggered it."""
    import builtins
    import contextlib

    real_open = builtins.open

    @contextlib.contextmanager
    def disk_full(store):
        def failing_open(file, *a, **kw):
            if str(file).startswith(str(store.path)):
                raise OSError(28, "No space left on device")
            return real_open(file, *a, **kw)

        builtins.open = failing_open
        try:
            yield
        finally:
            builtins.open = real_open

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)
        s.add_app({"name": "Before", "path": "/b"})

        reported = []
        s.on_error = reported.append
        with disk_full(s):
            try:
                app, raised = s.add_app({"name": "During outage", "path": "/x"}), None
            except Exception as exc:
                app, raised = None, exc
            ok(raised is None, "a failing save doesn't propagate out of add_app")
            ok(app and app["name"] == "During outage",
               "add_app still returns its record when the save fails")
            ok(s.flush() is False, "flush reports the failure")
            ok(len(reported) == 1, "only the first failure of a streak is reported")
            ok("No space left" in reported[0], "the reported message carries the OS error")
            ok(s.write_error is not None, "the failure is remembered")
            ok(len(s.state()["apps"]) == 2, "the in-memory library keeps the change")
            ok(not any(n.endswith(".tmp") for n in os.listdir(d)), "no temp file is left behind")

        ok(s.flush() is True, "a later save succeeds again")
        ok(s.write_error is None, "the remembered failure is cleared")
        ok(len(Store(path).state()["apps"]) == 2, "the recovered save reaches disk")

        broken = Store(os.path.join(d, "other.json"))
        broken.on_error = lambda msg: 1 / 0
        with disk_full(broken):
            ok(broken.flush() is False, "a throwing error callback doesn't break the save path")


def test_store_validates_settings_on_write_not_only_on_read():
    """Мусорное значение не должно доезжать до диска.

    Проверка стояла только на чтении, поэтому между записью и следующим
    запуском приложение работало с испорченными настройками: `apply_window`
    считала `max(LIBRARY_MIN_W, "not-an-int")` и падала в `TypeError`, тот
    проглатывался общим `except Exception` — окно просто не восстанавливалось.
    """
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        s = Store(path)

        bad = [("win_w", "not-an-int", None), ("minimize_to_tray", "yes", True),
               ("collapsed", "oops", []), ("accent", 42, "#0a84ff"),
               ("icon_schema", True, 0)]
        for key, junk, expected in bad:
            s.set_setting(key, junk)
            ok(s.settings()[key] == expected,
               f"{key}={junk!r} отвергнут в памяти (стало {s.settings()[key]!r})")
            ok(Store(path).settings()[key] == expected, f"{key} не уехал на диск испорченным")

        good = [("win_w", 1280), ("minimize_to_tray", False), ("collapsed", ["work"]),
                ("accent", "#ff8800"), ("icon_schema", 3), ("win_x", None)]
        for key, value in good:
            s.set_setting(key, value)
            ok(s.settings()[key] == value, f"{key}={value!r} сохраняется как есть")
        ok(Store(path).settings()["collapsed"] == ["work"], "и переживает перезапуск")


def test_store_flushes_to_disk_before_swapping_the_file():
    """Атомарной замены мало: без fsync содержимое остаётся в кэше ОС.

    `os.replace` меняет запись каталога одним действием, но записанные байты
    до сброса живут только в памяти. Отключение питания между записью и
    сбросом — и вместо библиотеки на диске обрезанный файл, который уедет
    в карантин, а пользователь получит пустой список программ.
    """
    calls = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    def spy_replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    with tempfile.TemporaryDirectory() as d:
        s = Store(os.path.join(d, "data.json"))
        os.fsync, os.replace = spy_fsync, spy_replace
        try:
            s.add_app({"name": "Durable", "path": "/d"})
        finally:
            os.fsync, os.replace = real_fsync, real_replace

        ok(calls == ["fsync", "replace"],
           f"каждая запись сбрасывается на диск, потом заменяет файл (было {calls})")
        ok(len(Store(os.path.join(d, "data.json")).state()["apps"]) == 1,
           "и запись доезжает до диска")


def test_store_batched_writes():
    """Bulk paths write the file once, not once per record."""
    from app.core.view_state import ViewState
    from app.platform import discovery

    with tempfile.TemporaryDirectory() as d:
        s = Store(os.path.join(d, "data.json"))
        for i in range(20):
            s.add_app({"name": f"Game{i}", "path": f"steam://rungameid/{i}"})

        writes = {"n": 0}
        real_persist = s._persist

        def counting_persist():
            writes["n"] += 1
            return real_persist()
        s._persist = counting_persist

        changed = discovery.backfill_icons(s, None)
        ok(changed is True, "backfill patches the steam apps")
        ok(writes["n"] == 1, "backfilling 20 apps writes the file once, not 20 times")
        ok(all(a.get("sub") == "Steam" for a in Store(os.path.join(d, "data.json")).state()["apps"]),
           "the batched changes reach disk")

        writes["n"] = 0
        ok(discovery.backfill_icons(s, None) is False, "a second backfill has nothing to do")
        ok(writes["n"] == 0, "an unchanged backfill doesn't write at all")

        writes["n"] = 0
        ViewState(s).persist()
        ok(writes["n"] == 0,
           "the three view settings don't block the caller with a synchronous write")
        ok(s.flush() is True and writes["n"] == 1,
           "but they were queued and land in exactly one write once flushed")

        # Каждое сохранение переписывает файл целиком — на библиотеке в 500
        # программ это ~8.5 мс синхронно в потоке интерфейса. Одиночные
        # переключатели («избранное», «от администратора», горячая клавиша)
        # били по диску на каждый щелчок, хотя массовые пути давно батчатся.
        writes["n"] = 0
        app_id = s.state()["apps"][0]["id"]
        s.update_app(app_id, {"favorite": True})
        ok(writes["n"] == 0, "одиночное изменение не блокирует щелчок записью на диск")
        ok(s.get_app(app_id)["favorite"] is True, "в памяти оно видно сразу")
        ok(s.flush() is True and writes["n"] == 1, "и досохраняется одной записью")
        ok(Store(os.path.join(d, "data.json")).get_app(app_id)["favorite"] is True,
           "то есть доезжает до диска")

        writes["n"] = 0
        s.update_app(app_id, {"favorite": False}, persist=True)
        ok(writes["n"] == 1, "явный persist=True по-прежнему пишет сразу")

        writes["n"] = 0
        before = len(s.state()["apps"])
        added = s.add_apps([{"name": f"Bulk{i}", "path": f"/bulk/{i}"} for i in range(15)])
        ok(writes["n"] == 1, "adding 15 apps at once writes the file once, not 15 times")
        ok(len(added) == 15 and len({a["id"] for a in added}) == 15,
           "each gets its own id")
        ok([a["order"] for a in added] == list(range(before, before + 15)),
           "orders are sequential, same as adding them one at a time would give")
        ok(len(s.state()["apps"]) == before + 15, "all of them land in the library")
        added[0]["name"] = "mutated after the fact"
        ok(s.get_app(added[0]["id"])["name"] == "Bulk0",
           "add_apps hands back copies too, not the live records")

        writes["n"] = 0
        ok(s.add_apps([]) == [], "an empty batch is a no-op")
        ok(writes["n"] == 0, "and doesn't write at all")


def test_image_cache_bounded():
    """The image caches used to keep every image the session ever touched."""
    try:
        from app.ui import images
    except Exception as exc:  # flet only — a missing ceiling must not skip
        skip("image cache test", exc)
        return
    _IMG_BYTES_CACHE, _LruCache, img_bytes = (images._IMG_BYTES_CACHE, images._LruCache,
                                              images.img_bytes)

    cache = _LruCache(max_entries=3)
    for i in range(10):
        cache.put(f"k{i}", 1.0, f"v{i}", 1)
    ok(len(cache) == 3, "the entry ceiling is enforced")
    ok(cache.get("k9", 1.0) == "v9" and cache.get("k0", 1.0) is None,
       "the least recently used entries are the ones evicted")
    ok(cache.get("k9", 2.0) is None, "a changed mtime invalidates the entry")

    byte_capped = _LruCache(max_entries=100, max_bytes=10)
    for i in range(5):
        byte_capped.put(f"k{i}", 1.0, "x" * 4, 4)
    ok(len(byte_capped) <= 3, "the byte ceiling is enforced independently of the count")

    ok(_IMG_BYTES_CACHE.max_entries <= 1024 and bool(_IMG_BYTES_CACHE.max_bytes),
       "the shared image cache declares a finite ceiling")
    _IMG_BYTES_CACHE.clear()
    with tempfile.TemporaryDirectory() as d:
        encoded = []
        for i in range(min(_IMG_BYTES_CACHE.max_entries, 200) + 20):
            p = os.path.join(d, f"i{i}.png")
            iconify.generate_icon(p, 8)
            encoded.append(img_bytes(p))
        ok(all(encoded), "every image encodes")
        ok(len(_IMG_BYTES_CACHE) <= _IMG_BYTES_CACHE.max_entries,
           "img_bytes never grows past its ceiling")
        ok(img_bytes(p) == encoded[-1], "an evicting cache still returns correct data")
    _IMG_BYTES_CACHE.clear()


def test_store_corrupt_recovery():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"apps": [ truncated...')

        s = Store(path)
        ok(s.state()["apps"] == [], "a corrupted file falls back to defaults")
        saved = [f for f in os.listdir(d) if f.startswith("centurio-corrupt-")]
        ok(len(saved) == 1, "the unreadable file is quarantined, not discarded")
        with open(os.path.join(d, saved[0]), encoding="utf-8") as fh:
            ok("truncated" in fh.read(), "the quarantined copy keeps the original bytes")

        s.add_app({"name": "After", "path": "/x"})
        ok(len(Store(path).state()["apps"]) == 1, "the store stays usable afterwards")


def test_bg_tint_setting_is_sanitized():
    """`bg_tint` — целое число градусов или `None`, иначе тихий откат к умолчанию."""
    from app.core.store import sanitize

    ok(sanitize.clean_setting_value("bg_tint", 222, None) == 222, "целое число принимается")
    ok(sanitize.clean_setting_value("bg_tint", None, None) is None, "None принимается как есть")
    ok(sanitize.clean_setting_value("bg_tint", "222", None) is None,
       "строка -> откат к умолчанию, а не молчаливая порча типа")
    ok(sanitize.clean_setting_value("bg_tint", True, None) is None,
       "bool — не int, хоть Python и считает его подклассом")
    ok(sanitize.clean_setting_value("contrast", "strong", "normal") == "strong",
       "строковое значение контраста принимается")
    ok(sanitize.clean_setting_value("contrast", "", "normal") == "normal",
       "пустая строка -> откат к умолчанию")


def test_data_ops():
    with tempfile.TemporaryDirectory() as d:
        s = Store(os.path.join(d, "data.json"))
        s.add_app({"name": "One", "path": "/one", "category_id": "work"})
        s.add_category("Мои игры")
        exp = s.export_data(os.path.join(d, "out.json"))
        ok(os.path.exists(exp), "export writes a file")

        s2 = Store(os.path.join(d, "data2.json"))
        ok(s2.import_data(exp) is True, "import loads exported data")
        ok(len(s2.state()["apps"]) == 1, "imported apps present")
        ok(any(c["name"] == "Мои игры" for c in s2.state()["categories"]), "imported categories present")
        ok(s2.import_data(os.path.join(d, "nope.json")) is False, "import of missing file -> False")

        bak = s.backup()
        ok(os.path.exists(bak) and "backup" in bak.name, "backup file created")


def test_auto_backups():
    """Раз в сутки — автокопия, если библиотека менялась; хранятся семь последних."""
    from app.core.store import store as store_mod

    hour = 3600
    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ok(store.auto_backup() is None, "an empty library is not worth a copy")

        store.add_app({"name": "Editor", "path": "C:/e.exe"})
        first = store.auto_backup()
        ok(first is not None and first.parent.name == "backups"
           and first.name.startswith("auto-"), "the first copy lands in «backups»")
        ok(store.backup_summary(first) == {"apps": 1, "sets": 0},
           "and a copy can say what is in it")
        ok(store.auto_backup() is None, "a second one the same day is not made")

        later = time.time() + 21 * hour
        store.set_setting("win_x", 120)
        ok(store.auto_backup(now=later) is None,
           "a day later, a moved window alone does not make a new copy")

        made = [first]
        for n in range(store_mod.AUTO_BACKUP_KEEP + 2):
            store.add_app({"name": f"App {n}", "path": f"C:/a{n}.exe"})
            # Время файла — «вчера», чтобы следующая копия не считалась слишком частой.
            past = time.time() - 21 * hour
            os.utime(made[-1], (past, past))
            made.append(store.auto_backup())
        ok(all(made), "each day with changes gets its own copy")
        kept = store.auto_backups()
        ok(len(kept) == store_mod.AUTO_BACKUP_KEEP,
           f"only the latest {store_mod.AUTO_BACKUP_KEEP} are kept ({len(kept)})")
        ok(kept[0] == made[-1] and first not in kept, "newest first, oldest pruned")

        store.newer_version = store_mod.SCHEMA_VERSION + 1
        store.data["apps"].append(dict(store.data["apps"][0], id="x"))
        os.utime(kept[0], (time.time() - 21 * hour,) * 2)
        ok(store.auto_backup() is None, "a library opened read-only is never copied")


def test_old_default_accent_moves_to_the_new_one():
    """Белый акцент прежней версии по умолчанию становится синим, выбранный — остаётся."""
    from app.core.store.sanitize import UI_DEFAULTS_VERSION, clean_settings

    moved = clean_settings({"accent": "#F5F5F7", "ui_defaults_version": 1})
    ok(moved["accent"] == "#0a84ff" and moved["ui_defaults_version"] == UI_DEFAULTS_VERSION,
       "the untouched old default follows the new look")
    kept = clean_settings({"accent": "#ff375f", "ui_defaults_version": 1})
    ok(kept["accent"] == "#ff375f", "an accent the person picked stays theirs")
    chosen = clean_settings({"accent": "#f5f5f7", "ui_defaults_version": UI_DEFAULTS_VERSION})
    ok(chosen["accent"] == "#f5f5f7",
       "white picked after the change is a choice, not an old default")
