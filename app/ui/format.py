from __future__ import annotations

import flet as ft

ICON_PACK = [
    "work", "business", "apartment", "store", "home", "folder", "folder_special",
    "code", "terminal", "data_object", "bug_report", "build", "engineering", "memory",
    "brush", "palette", "draw", "design_services", "architecture", "photo_camera",
    "image", "movie", "movie_creation", "music_note", "headphones", "mic", "podcasts",
    "sports_esports", "videogame_asset", "casino", "extension", "sports_soccer",
    "sports_basketball", "fitness_center", "directions_run", "chat", "mail", "forum",
    "language", "translate", "public", "map", "place", "flight", "directions_car",
    "school", "menu_book", "book", "science", "calculate", "functions",
    "cloud", "download", "storage", "dns", "wifi", "security", "lock", "vpn_key",
    "settings", "dashboard", "widgets", "apps", "star", "favorite", "bolt",
    "local_cafe", "restaurant", "shopping_cart", "attach_money", "credit_card",
    "calendar_month", "schedule", "alarm", "computer", "desktop_windows", "tv",
    "phone_android", "keyboard", "print", "rocket_launch", "pets", "spa",
]

_BOLD = {ft.FontWeight.BOLD, ft.FontWeight.W_700, ft.FontWeight.W_800, ft.FontWeight.W_900}


def _family_for(weight):
    if weight in _BOLD:
        return "Inter Bold"
    if weight == ft.FontWeight.W_600:
        return "Inter SemiBold"
    return "Inter"


def _tracking(size) -> float:
    """Межбуквенный интервал по кеглю: крупное — плотнее, как у шрифтов macOS.

    Inter, как и San Francisco, рассчитан на это: заголовки без поджатия
    выглядят разреженными.
    """
    if not size:
        return 0.0
    if size >= 24:
        return -0.6
    if size >= 18:
        return -0.4
    if size >= 15:
        return -0.2
    return 0.0


def T(value="", **kw):
    fam = kw.get("font_family")
    if fam == "monospace":
        kw["font_family"] = "mono"
    elif fam is None:
        kw["font_family"] = _family_for(kw.get("weight"))
    tracking = _tracking(kw.get("size"))
    if tracking and "style" not in kw and fam != "monospace":
        kw["style"] = ft.TextStyle(letter_spacing=tracking)
    return ft.Text(value, **kw)


def cat_icon(name: str):
    """Значок категории — скруглённый вариант Material: мягче, ближе к SF Symbols."""
    key = (name or "folder").upper()
    return (getattr(ft.Icons, f"{key}_ROUNDED", None) or getattr(ft.Icons, key, None)
            or ft.Icons.FOLDER_ROUNDED)


def as_icon(value):
    """Значок по имени («folder») или уже готовый `ft.Icons.X`.

    Во Flet 1.0 значок — объект, а не строка: строку клиент не рисует, и на
    месте всего контрола появлялся серый прямоугольник ошибки.
    """
    return cat_icon(value) if isinstance(value, str) else value
