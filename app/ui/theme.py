from __future__ import annotations

from . import colors as C

MAX_TINT_SATURATION = 0.2

CONTRAST_LEVELS = {"soft": 0.85, "normal": 1.0, "strong": 1.16}
DEFAULT_CONTRAST = "normal"

# Оформление: тёмное, светлое или как в Windows (светлая или тёмная тема
# приложений в «Параметрах» — Flutter сообщает её как яркость платформы).
APPEARANCES = ("dark", "light", "system")
DEFAULT_APPEARANCE = "dark"

THEME_PRESETS = (
    {"id": "coal", "label": "Уголь", "bg_tint": None, "contrast": "normal", "accent": 0},
    {"id": "midnight", "label": "Полночь", "bg_tint": 222, "contrast": "normal", "accent": 1},
    {"id": "emerald", "label": "Изумруд", "bg_tint": 165, "contrast": "normal", "accent": 2},
    {"id": "amethyst", "label": "Аметист", "bg_tint": 268, "contrast": "normal", "accent": 7},
    {"id": "crisp", "label": "Контраст", "bg_tint": None, "contrast": "strong", "accent": 0},
)

# Подстраиваются тоном и контрастом только поверхности, линии и текст.
# Смысловые цвета (успех, ошибка, звезда) и акцент — нет: иначе зелёное
# «открыто» становилось бы фиолетовым вместе с фоном.
_BASE_TOKENS = dict(C.DARK)
_BASES = {"dark": C.DARK, "light": C.LIGHT}
_MEANINGS = {"dark": C.DARK_MEANING, "light": C.LIGHT_MEANING}


def resolve_mode(settings: dict, system: str | None = None) -> str:
    """«dark» или «light» — что показывать при этих настройках."""
    choice = settings.get("appearance")
    if choice not in APPEARANCES:
        choice = DEFAULT_APPEARANCE
    if choice == "system":
        return "light" if system == "light" else "dark"
    return choice


def _tint_hex(hexval: str, tint_hue: int | None, contrast: float, mode: str) -> str:
    hue, light, sat = C.hex_to_hsl(hexval)
    light = max(0.0, min(1.0, 0.5 + (light - 0.5) * contrast))
    if tint_hue is not None:
        # В тёмной теме светлые цвета (текст) почти не подкрашиваются — иначе
        # белый текст становился цветным. В светлой теме подкраска нужна и
        # светлому фону, иначе её не видно вовсе.
        if mode == "light":
            headroom = 1.0
        else:
            headroom = 1.0 if light <= 0.5 else max(0.0, 1 - (light - 0.5) * 2)
        sat = max(sat, headroom * MAX_TINT_SATURATION)
        hue = tint_hue % 360
    return C.hsl_to_hex(hue, light, sat)


def build_palette(bg_tint: int | None, contrast_key: str,
                  mode: str = "dark") -> dict[str, str]:
    contrast = CONTRAST_LEVELS.get(contrast_key, CONTRAST_LEVELS[DEFAULT_CONTRAST])
    base = _BASES.get(mode, C.DARK)
    if bg_tint is None and contrast == 1.0:
        return dict(base)
    return {name: _tint_hex(value, bg_tint, contrast, mode) for name, value in base.items()}


def _settings_tint(settings: dict) -> int | None:
    bg_tint = settings.get("bg_tint")
    if not isinstance(bg_tint, int) or isinstance(bg_tint, bool):
        return None
    return bg_tint


def apply_theme(settings: dict, system: str | None = None) -> str:
    """Подставить в colors.py цвета для этих настроек. Возвращает «dark»/«light»."""
    contrast_key = settings.get("contrast")
    if contrast_key not in CONTRAST_LEVELS:
        contrast_key = DEFAULT_CONTRAST
    mode = resolve_mode(settings, system)
    for name, value in build_palette(_settings_tint(settings), contrast_key, mode).items():
        setattr(C, name, value)
    for name, value in _MEANINGS[mode].items():
        setattr(C, name, value)
    C.MODE = mode
    return mode


def reset_theme() -> None:
    apply_theme({})


def effective_accent(stored: str | None) -> str:
    """Акцент, который видно на текущем фоне.

    Белый акцент «Угля» в светлой теме превратился бы в белые кнопки на белом;
    вместо него — почти чёрный. Свой цвет человека не трогаем, если он виден.
    """
    return C.readable(C.parse_hex(stored) or C.ACCENT)
