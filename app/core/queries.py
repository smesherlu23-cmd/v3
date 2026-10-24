from __future__ import annotations

import time

from .text import launch_key, match_rank, plu_programs, plu_windows, short_ago

SORT_KEYS = ("alpha", "recent", "added", "manual")

SORT_LABELS = {"alpha": "По алфавиту", "recent": "Недавние",
               "added": "Недавно добавленные", "manual": "Вручную"}

SOURCES = {
    "steam": {"label": "Steam", "icon": "sports_esports", "cat": "games"},
    "epic": {"label": "Epic Games", "icon": "casino", "cat": "games"},
    "startmenu": {"label": "Меню «Пуск»", "icon": "apps", "cat": None},
    "store": {"label": "Microsoft Store", "icon": "shopping_cart", "cat": None},
    "registry": {"label": "Реестр", "icon": "data_object", "cat": None},
    "localapps": {"label": "Папка программ", "icon": "folder", "cat": None},
    "manual": {"label": "Вручную", "icon": "folder_open", "cat": None},
    "": {"label": "Другое", "icon": "folder", "cat": None},
}

# Словарь известных программ: по имени и пути программа получает несколько
# «видов» по порядку, а категорией становится первая подходящая из тех, что
# есть у человека. Мессенджеры раньше падали в «Работу» даже при наличии
# «Общения»: Zoom и WhatsApp числились только там или нигде.
_CATEGORY_HINTS = (
    ("games", ("steam", "epic games", "gog galaxy", "battle.net", "ubisoft connect",
               "origin", "ea app", "riot client", "roblox", "minecraft", "playnite",
               "amazon games", "xbox", "lutris", "heroic games")),
    ("dev", ("jetbrains", "pycharm", "intellij", "webstorm", "rider", "clion", "goland",
             "phpstorm", "datagrip", "android studio", "visual studio", "vscode",
             "vs code", "sublime text", "notepad++", "git bash", "git gui", "git-cmd",
             "\\git\\", "github", "gitlab", "docker",
             "postman", "insomnia", "dbeaver", "putty", "windows terminal", "cmder",
             "sourcetree", "unity hub", "unity editor", "\\unity\\", "godot",
             "unreal editor", "node.js", "python",
             "arduino", "xcode", "eclipse", "netbeans", "wireshark", "fiddler",
             "kubernetes", "vmware", "virtualbox", "wsl", "powershell", "mysql workbench",
             "sql server management", "azure data studio", "figma dev mode", "cursor")),
    ("create", ("photoshop", "illustrator", "premiere", "after effects", "lightroom",
                "indesign", "figma", "blender", "krita", "gimp", "inkscape", "affinity",
                "davinci", "obs studio", "obs64", "audacity", "reaper", "ableton",
                "fl studio",
                "cubase", "capture one", "clip studio", "paint.net", "sketch",
                "substance", "cinema 4d", "maya", "3ds max", "canva", "procreate",
                "vegas pro", "camtasia", "streamlabs", "vmix", "nuke", "houdini",
                "toon boom", "shotcut", "kdenlive", "corel painter", "coreldraw",
                "adobe xd", "webflow")),
    ("chat", ("telegram", "whatsapp", "discord", "viber", "signal", "skype", "zoom",
              "microsoft teams", "slack", "wechat", "icq", "mattermost",
              "rocket.chat", "messenger", "мессенджер", "vk messenger", "teamspeak",
              "mumble", "thunderbird", "outlook", "почта", "mail")),
    ("browser", ("chrome", "firefox", "microsoft edge", "msedge", "opera", "brave",
                 "vivaldi", "yandex browser", "яндекс браузер", "browser", "tor browser",
                 "chromium", "waterfox", "librewolf")),
    ("media", ("spotify", "vlc", "yandex music", "яндекс музыка", "itunes", "foobar",
               "aimp", "media player", "winamp", "mpc-hc", "potplayer", "kodi", "plex",
               "netflix", "youtube music", "audible", "deezer", "tidal", "kinopoisk",
               "кинопоиск")),
    ("utils", ("7-zip", "winrar", "everything", "powertoys", "ccleaner",
               "process explorer", "total commander", "far manager", "sharex",
               "greenshot", "lightshot", "keepass", "bitwarden", "1password", "qbittorrent",
               "utorrent", "revo uninstaller", "cpu-z", "hwinfo", "afterburner", "rufus",
               "autoruns", "rainmeter", "f.lux", "autohotkey", "translator", "переводчик")),
    ("work", ("outlook", "microsoft word", "winword", "excel", "powerpoint", "onenote",
              "microsoft teams", "slack", "zoom", "skype", "notion", "trello", "asana",
              "jira", "confluence", "miro", "todoist", "1c", "1с", "sap", "sharepoint",
              "adobe acrobat", "acrobat reader", "google docs", "google sheets",
              "yandex.disk", "mail.ru", "citrix workspace", "anydesk", "teamviewer",
              "obsidian", "evernote", "libreoffice", "wps office", "onlyoffice")),
)

_CATEGORY_NAME_HINTS = {
    "games": ("игр", "game", "гейм", "gaming", "gamer", "плей"),
    "dev": ("разработ", "программир", "код", "development", "coding", "programming",
            "software", "engineer", "инженер"),
    "create": ("творч", "дизайн", "creat", "design", "монтаж", "рисован", "иллюстрац"),
    "chat": ("общен", "мессендж", "связь", "чат", "chat", "messag", "social", "соц",
             "почт", "mail"),
    "browser": ("браузер", "browser", "интернет", "internet", "сеть", "web"),
    "media": ("музык", "видео", "медиа", "кино", "media", "music", "video", "плеер",
              "развлеч", "entertain"),
    "utils": ("утилит", "систем", "инструмент", "tool", "util", "system", "сервис"),
    "work": ("работ", "офис", "work", "office", "продуктивн", "productiv",
             "бизнес", "business", "документ", "document"),
}


def _category_for_kind(categories: list[dict], kind: str) -> str | None:
    for c in categories:
        if c["id"] == kind:
            return c["id"]
    needles = _CATEGORY_NAME_HINTS.get(kind, ())
    for c in categories:
        name = (c.get("name") or "").lower()
        if any(n in name for n in needles):
            return c["id"]
    return None


def valid_filter(f: str, categories: list[dict]) -> str:
    if f and f.startswith("category:"):
        cid = f.split(":", 1)[1]
        if not any(c["id"] == cid for c in categories):
            return "all"
    return f or "all"


def visible(apps: list[dict]) -> list[dict]:
    return [a for a in apps if not a.get("hidden")]


def sort_apps(apps: list[dict], sort: str) -> list[dict]:
    if sort == "alpha":
        return sorted(apps, key=lambda a: a["name"].lower())
    if sort == "recent":
        return sorted(apps, key=lambda a: a.get("last_launched", 0), reverse=True)
    if sort == "added":
        return sorted(apps, key=lambda a: a.get("added_at", 0), reverse=True)
    if sort == "manual":
        return sorted(apps, key=lambda a: (a.get("order", 0), a.get("added_at", 0)))
    return apps


def recent_apps(apps: list[dict], limit: int | None = None) -> list[dict]:
    lst = sorted([a for a in apps if a.get("last_launched")],
                 key=lambda a: a["last_launched"], reverse=True)
    return lst[:limit] if limit else lst


def quick_apps(apps: list[dict]) -> list[dict]:
    return [a for a in apps if a.get("quick")]


def hotkey_apps(apps: list[dict], accels: dict) -> list[dict]:
    return [a for a in apps if a["id"] in accels]


def build_sections(apps: list[dict], categories: list[dict], view: str,
                   sort: str, running: set) -> list[dict]:
    if view == "hidden":
        return [{"name": "Скрытые",
                 "apps": sort_apps([a for a in apps if a.get("hidden")], sort),
                 "editable": False, "cid": None}]
    shown = visible(apps)
    if view == "favorites":
        return [{"name": "Избранное",
                 "apps": sort_apps([a for a in shown if a.get("favorite")], sort),
                 "editable": False, "cid": None}]
    if view == "recent":
        return [{"name": "Недавние", "apps": recent_apps(shown),
                 "editable": False, "cid": None}]
    if view == "running":
        return [{"name": "Запущено",
                 "apps": sort_apps([a for a in shown if a["id"] in running], sort),
                 "editable": False, "cid": None}]
    if view.startswith("category:"):
        cid = view.split(":", 1)[1]
        cat = next((c for c in categories if c["id"] == cid), None)
        return [{"name": cat["name"] if cat else "Категория",
                 "apps": sort_apps([a for a in shown if a.get("category_id") == cid], sort),
                 "editable": bool(cat), "cid": cid}]
    sections = []
    known = set()
    for cat in categories:
        known.add(cat["id"])
        sections.append({"name": cat["name"], "cid": cat["id"], "editable": True,
                         "apps": sort_apps([a for a in shown if a.get("category_id") == cat["id"]], sort)})
    orphan = sort_apps([a for a in shown if a.get("category_id") not in known], sort)
    if orphan:
        sections.append({"name": "Без категории", "apps": orphan, "editable": False, "cid": None})
    return [s for s in sections if s["apps"]]


def flatten_sections(sections: list[dict]) -> list[dict]:
    return [a for sec in sections for a in sec["apps"]]


def current_title(view: str, categories: list[dict]) -> str:
    return {"all": "Все программы", "favorites": "Избранное", "recent": "Недавние",
            "running": "Запущено", "hidden": "Скрытые"}.get(view) or (
        next((c["name"] for c in categories if view == f"category:{c['id']}"), "Все программы"))

PALETTE_LIMIT = 8
SET_LIMIT = 3
# Категория и подпись («Steam», «Работа») — подсказка слабее имени и только
# от трёх букв: иначе одна «р» выводила бы всю категорию «Работа».
CATEGORY_RANK = 9


# Вес запуска по давности, как у «частоты» в Firefox: вчерашний запуск
# весит больше десятка прошлогодних.
_RECENCY_WEIGHTS = ((4, 100), (14, 70), (31, 50), (90, 30))
_DAY_MS = 86_400_000


def frecency(app: dict, now_ms: int | None = None) -> float:
    """Насколько часто и недавно запускали: число запусков × средний вес давности."""
    count = int(app.get("launch_count") or 0)
    if not count:
        return 0.0
    stamps = [t for t in app.get("launches") or [] if isinstance(t, int)] \
        or [int(app.get("last_launched") or 0)]
    now = now_ms if now_ms is not None else int(time.time() * 1000)

    def weight(ts):
        days = (now - ts) / _DAY_MS
        return next((w for limit, w in _RECENCY_WEIGHTS if days < limit), 10)
    return count * sum(weight(t) for t in stamps) / len(stamps)


def name_match(app: dict, query: str) -> tuple[int | None, str]:
    """Лучшее совпадение запроса с именем или с одним из «других имён».

    Возвращает ранг и другое имя, если сработало оно. Другое имя, набранное
    целиком («пс» у Photoshop), — самое сильное совпадение: его человек
    завёл ровно для этого.
    """
    best, via = match_rank(app.get("name") or "", query), ""
    flat = " ".join(query.lower().split())
    for alias in app.get("aliases") or []:
        if " ".join(alias.lower().split()) == flat:
            return -1, alias
        rank = match_rank(alias, query)
        if rank is not None and (best is None or rank < best):
            best, via = rank, alias
    return best, via


def _tier(rank: int) -> int:
    # Начало имени и начало любого слова — одинаково хорошие попадания:
    # между ними решает то, чем человек пользуется чаще.
    return 0 if rank in (0, 1) else rank


def search_rows(apps: list[dict], query: str, running: set,
                categories: list[dict], recent_limit: int = PALETTE_LIMIT) -> list[dict]:
    names = {c["id"]: c["name"] for c in categories}
    pool = visible(apps)
    out: list[dict] = []

    def add(app, note, via=""):
        out.append({"app": app, "index": len(out), "note": note, "via": via,
                    "cat": names.get(app.get("category_id"), "")})

    q = (query or "").strip().lower()
    if q:
        scored = []
        now = int(time.time() * 1000)
        for a in pool:
            rank, via = name_match(a, q)
            if rank is None and len(q) >= 3 and match_rank(
                    f"{a.get('sub') or ''} {names.get(a.get('category_id'), '')}", q) is not None:
                rank = CATEGORY_RANK
            if rank is not None:
                scored.append(((_tier(rank), -frecency(a, now), rank, a["name"].lower()),
                               a, via))
        scored.sort(key=lambda row: row[0])
        for _key, app, via in scored[:recent_limit]:
            add(app, "открыто" if app["id"] in running else "", via)
        return out

    for app in sorted([a for a in pool if a["id"] in running], key=lambda a: a["name"].lower()):
        add(app, "открыто")
    for app in [a for a in recent_apps(pool) if a["id"] not in running][:recent_limit]:
        add(app, "")
    if not out:
        pinned = quick_apps(pool)
        rest = sorted((a for a in pool if not a.get("quick")),
                      key=lambda a: a["name"].lower())
        for app in (pinned + rest)[:recent_limit]:
            add(app, "")
    return out


def set_rows(sets: list[dict], apps: list[dict], query: str) -> list[dict]:
    q = (query or "").strip().lower()
    names = {a["id"]: a["name"] for a in apps}
    out = []
    for rec in sets:
        members = [names[i] for i in rec.get("apps", []) if i in names]
        if q and match_rank(rec["name"], q) is None \
                and not any(match_rank(m, q) is not None for m in members):
            continue
        out.append({"set": rec, "members": members})
    return out[:SET_LIMIT] if q else out


def has_layout(rec: dict) -> bool:
    return any(i.get("slot") is not None or i.get("rect") for i in rec.get("items", []))


def set_palette_sub(rec: dict, members: list[str]) -> str:
    count = len(members)
    text = f"{count} {plu_programs(count)}"
    if members:
        text += f", включая {members[0]}"
    return f"{text} · с раскладкой" if has_layout(rec) else text


def app_palette_sub(row: dict, windows: int = 0) -> str:
    parts = [f"«{row['via']}»"] if row.get("via") else []
    parts += [row["cat"]] if row["cat"] else []
    if row["note"] == "открыто":
        parts.append(f"открыто, {windows} {plu_windows(windows)}" if windows > 1 else "открыто")
    else:
        ago = short_ago(row["app"].get("last_launched"))
        if ago:
            parts.append(ago)
    return " · ".join(parts)

PALETTE_ACTIONS = (
    {"key": "folder", "icon": "folder_open", "label": "Открыть папку программы"},
    {"key": "admin", "icon": "shield", "label": "Запустить от имени администратора"},
    {"key": "set", "icon": "playlist_add", "label": "Добавить в набор…"},
)


def palette_actions(app: dict | None) -> list[dict]:
    if app is None:
        return []
    kind = app.get("kind")
    if not kind:
        return [dict(a) for a in PALETTE_ACTIONS]
    # У сайта нет папки, а «от администратора» к документу и папке неприменимо.
    out = [dict(a) for a in PALETTE_ACTIONS
           if a["key"] == "set" or (a["key"] == "folder" and kind != "web")]
    for action in out:
        if action["key"] == "folder":
            action["label"] = "Показать в папке"
    return out


def category_kinds(item: dict) -> list[str]:
    """Виды программы по словарю — от самого точного к запасному."""
    kinds = []
    source_kind = SOURCES.get((item.get("source") or "").lower(), {}).get("cat")
    if source_kind:
        kinds.append(source_kind)
    haystack = f"{item.get('name', '')} {item.get('path', '')}".lower()
    for cid, needles in _CATEGORY_HINTS:
        if cid not in kinds and any(n in haystack for n in needles):
            kinds.append(cid)
    return kinds


def suggest_category(item: dict, categories: list[dict]) -> str | None:
    if not categories:
        return None
    for kind in category_kinds(item):
        match = _category_for_kind(categories, kind)
        if match:
            return match
    # Ничего не подошло — «Работа», если она есть, иначе первая категория.
    return _category_for_kind(categories, "work") or categories[0]["id"]


# На экране новых программ цифрами 1–9 выбираются первые девять категорий,
# остальные — через «Ещё…». Раньше их было четыре, и пятая категория
# («Игры») просто не предлагалась.
TRIAGE_KEYS = 9


def suggest_categories(item: dict, categories: list[dict],
                       limit: int | None = None) -> list[dict]:
    """Все категории, первой — та, что подходит программе лучше всего."""
    if not categories:
        return []
    best = suggest_category(item, categories)
    ordered = [c for c in categories if c["id"] == best]
    ordered += [c for c in categories if c["id"] != best]
    return ordered[:limit] if limit else ordered


MANUAL_GROUP = "manual"


def group_found(found: list[dict], existing_keys: set, categories: list[dict],
                only_new: bool = False, query: str = "") -> list[dict]:
    """Найденное — группами по категории, куда программа ляжет.

    Раньше группы шли по источнику (Steam, меню «Пуск», реестр): человеку
    всё равно, откуда программа, ему важно, где она окажется. Источник
    остаётся мелкой подписью у строки. Добавленное вручную — первой группой.
    """
    q = (query or "").strip().lower()
    by_id = {c["id"]: c for c in categories}
    buckets: dict[str, list[dict]] = {}
    for item in found:
        path = (item.get("path") or "").strip()
        name = item.get("name") or ""
        if not path:
            continue
        if q and match_rank(name, q) is None and q not in path.lower():
            continue
        source = item.get("source") or ""
        if source not in SOURCES:
            source = ""
        key = launch_key(item)
        cat = suggest_category(item, categories)
        group = MANUAL_GROUP if source == "manual" else (cat or "")
        buckets.setdefault(group, []).append({
            "key": key,
            "item": item,
            "name": name,
            "path": path,
            "source": source,
            "source_label": SOURCES[source]["label"],
            "is_new": key not in existing_keys,
            "cat": cat,
        })

    order = [MANUAL_GROUP] + [c["id"] for c in categories] + [""]
    order += [k for k in buckets if k not in order]
    groups = []
    for key in order:
        rows = buckets.get(key)
        if not rows:
            continue
        rows.sort(key=lambda r: r["name"].lower())
        shown = [r for r in rows if r["is_new"]] if only_new else rows
        if not shown:
            continue
        cat = by_id.get(key)
        if key == MANUAL_GROUP:
            label, icon = "Добавлено вами", SOURCES["manual"]["icon"]
        elif cat:
            label, icon = cat["name"], cat.get("icon") or "folder"
        else:
            label, icon = "Без категории", "folder"
        groups.append({"group": key, "source": key if key == MANUAL_GROUP else "",
                       "label": label, "icon": icon, "cat": cat,
                       "rows": shown, "total": len(rows),
                       "new": sum(1 for r in rows if r["is_new"])})
    return groups


def set_name_for(apps: list[dict]) -> str:
    names = [a["name"] for a in apps][:2]
    if not names:
        return "Набор"
    joined = " и ".join(names)
    return joined if len(joined) <= 32 else names[0]
