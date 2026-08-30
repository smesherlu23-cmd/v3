from __future__ import annotations

import re

from . import colors as C

_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")

# Токены, которые подстройка темы не трогает. Акцент — отдельная, более
# старая настройка (см. `CenturioUI._accent`); подмешивать её ещё и сюда
# означало бы менять одно и то же двумя механизмами разом. Белый —
# примитив, а не поверхность. Остальные — цвета со смыслом (успех,
# опасность, рейтинг и их фоны/рамки): зелёная кнопка не должна становиться
# фиолетовой только потому, что пользователь выбрал фиолетовый тон
# интерфейса, иначе цвет перестаёт что-либо сообщать.
_EXCLUDE = frozenset({
    "ACCENT", "ON_ACCENT", "WHITE",
    "GREEN", "GREEN_TEXT", "DANGER", "STAR",
    "ERR_TEXT", "ERR_BG", "ERR_BORDER", "ERR_BTN_BORDER",
    "BADGE_BG", "BADGE_BORDER", "BADGE_TEXT",
    "DONE_BG", "DONE_BORDER",
})

# Насыщенность, которую можно подмешать тону, не делая цвет грязным —
# держим её невысокой, чтобы фон оставался приглушённым, а не ярким.
MAX_TINT_SATURATION = 0.2

CONTRAST_LEVELS = {"soft": 0.85, "normal": 1.0, "strong": 1.16}
DEFAULT_CONTRAST = "normal"

# Пресеты — только числа: тон (градусы или None), ключ контраста и индекс в
# C.ACCENT_CHOICES. Ни одного hex-литерала — их бы поймал
# test_colours_come_from_one_file, а тут они и не нужны: оттенок фона
# считается через HSL, а акцент пресета — это просто ссылка на готовый цвет.
THEME_PRESETS = (
    {"id": "coal", "label": "Уголь", "bg_tint": None, "contrast": "normal", "accent": 0},
    {"id": "midnight", "label": "Полночь", "bg_tint": 222, "contrast": "normal", "accent": 1},
    {"id": "emerald", "label": "Изумруд", "bg_tint": 165, "contrast": "normal", "accent": 2},
    {"id": "amethyst", "label": "Аметист", "bg_tint": 268, "contrast": "normal", "accent": 7},
    {"id": "crisp", "label": "Контраст", "bg_tint": None, "contrast": "strong", "accent": 0},
)


def _themeable_tokens() -> dict[str, str]:
    """Имя токена → его значение в colors.py, отобранное для подстройки темы.

    Отбор идёт по форме значения (ровно `#rrggbb`, без альфы), а не по
    заранее выписанному списку имён — так список остаётся верным сам
    собой, если в colors.py добавится новый токен фона/линии/текста.
    Тени и скримы (8-значный hex с альфой) и составные значения (кортежи
    вроде TILE_GRADIENT) в него не попадают уже просто по типу.
    """
    out = {}
    for name in dir(C):
        if not name.isupper() or name in _EXCLUDE:
            continue
        value = getattr(C, name)
        if isinstance(value, str) and _HEX6.match(value):
            out[name] = value
    return out


# Снимок исходных значений colors.py — один раз, до первой подмены. Если бы
# `build_palette` отталкивался от уже подкрашенных значений, повторная
# смена тона каждый раз уводила бы палитру всё дальше от исходного дизайна
# вместо того, чтобы каждый раз пересчитываться заново от одной базы.
_BASE_TOKENS = _themeable_tokens()


def _tint_hex(hexval: str, tint_hue: int | None, contrast: float) -> str:
    hue, light, sat = C.hex_to_hsl(hexval)
    light = max(0.0, min(1.0, 0.5 + (light - 0.5) * contrast))
    if tint_hue is not None:
        # Тёмные и средние тона берут тон в полную силу — там и виден тот
        # самый «прохладный/тёплый фон», ради которого это всё делается.
        # А вот у самых светлых токенов (почти-белый текст) запас насыщен-
        # ности спадает к нулю: подмешать в них тот же тон получится, но
        # едва заметно, иначе текст выглядел бы пастельным, а не белым.
        headroom = 1.0 if light <= 0.5 else max(0.0, 1 - (light - 0.5) * 2)
        sat = max(sat, headroom * MAX_TINT_SATURATION)
        hue = tint_hue % 360
    return C.hsl_to_hex(hue, light, sat)


def build_palette(bg_tint: int | None, contrast_key: str) -> dict[str, str]:
    """Токен → новый hex для выбранного тона фона и уровня контраста."""
    contrast = CONTRAST_LEVELS.get(contrast_key, CONTRAST_LEVELS[DEFAULT_CONTRAST])
    return {name: _tint_hex(value, bg_tint, contrast) for name, value in _BASE_TOKENS.items()}


def apply_theme(settings: dict) -> None:
    """Пересчитать палитру из настроек и подставить её в colors.py.

    `C.BG_0` и подобные — обращение к атрибуту модуля заново при каждом
    использовании, а не значение, замороженное в момент `import colors as
    C`, поэтому подмена видна везде, где экран строится заново. Вызывается
    из `CenturioUI.refresh()` перед перестройкой содержимого.
    """
    bg_tint = settings.get("bg_tint")
    if not isinstance(bg_tint, int) or isinstance(bg_tint, bool):
        bg_tint = None
    contrast_key = settings.get("contrast")
    if contrast_key not in CONTRAST_LEVELS:
        contrast_key = DEFAULT_CONTRAST
    for name, value in build_palette(bg_tint, contrast_key).items():
        setattr(C, name, value)


def reset_theme() -> None:
    """Вернуть исходные значения colors.py — для тестов и предпросмотра."""
    for name, value in _BASE_TOKENS.items():
        setattr(C, name, value)
