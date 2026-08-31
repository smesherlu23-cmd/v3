from __future__ import annotations

import re

from . import colors as C

_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")

_EXCLUDE = frozenset({
    "ACCENT", "ON_ACCENT", "WHITE",
    "GREEN", "GREEN_TEXT", "DANGER", "STAR",
    "ERR_TEXT", "ERR_BG", "ERR_BORDER", "ERR_BTN_BORDER",
    "BADGE_BG", "BADGE_BORDER", "BADGE_TEXT",
    "DONE_BG", "DONE_BORDER",
})

MAX_TINT_SATURATION = 0.2

CONTRAST_LEVELS = {"soft": 0.85, "normal": 1.0, "strong": 1.16}
DEFAULT_CONTRAST = "normal"

THEME_PRESETS = (
    {"id": "coal", "label": "Уголь", "bg_tint": None, "contrast": "normal", "accent": 0},
    {"id": "midnight", "label": "Полночь", "bg_tint": 222, "contrast": "normal", "accent": 1},
    {"id": "emerald", "label": "Изумруд", "bg_tint": 165, "contrast": "normal", "accent": 2},
    {"id": "amethyst", "label": "Аметист", "bg_tint": 268, "contrast": "normal", "accent": 7},
    {"id": "crisp", "label": "Контраст", "bg_tint": None, "contrast": "strong", "accent": 0},
)


def _themeable_tokens() -> dict[str, str]:
    out = {}
    for name in dir(C):
        if not name.isupper() or name in _EXCLUDE:
            continue
        value = getattr(C, name)
        if isinstance(value, str) and _HEX6.match(value):
            out[name] = value
    return out

_BASE_TOKENS = _themeable_tokens()


def _tint_hex(hexval: str, tint_hue: int | None, contrast: float) -> str:
    hue, light, sat = C.hex_to_hsl(hexval)
    light = max(0.0, min(1.0, 0.5 + (light - 0.5) * contrast))
    if tint_hue is not None:
        headroom = 1.0 if light <= 0.5 else max(0.0, 1 - (light - 0.5) * 2)
        sat = max(sat, headroom * MAX_TINT_SATURATION)
        hue = tint_hue % 360
    return C.hsl_to_hex(hue, light, sat)


def build_palette(bg_tint: int | None, contrast_key: str) -> dict[str, str]:
    contrast = CONTRAST_LEVELS.get(contrast_key, CONTRAST_LEVELS[DEFAULT_CONTRAST])
    return {name: _tint_hex(value, bg_tint, contrast) for name, value in _BASE_TOKENS.items()}


def apply_theme(settings: dict) -> None:
    bg_tint = settings.get("bg_tint")
    if not isinstance(bg_tint, int) or isinstance(bg_tint, bool):
        bg_tint = None
    contrast_key = settings.get("contrast")
    if contrast_key not in CONTRAST_LEVELS:
        contrast_key = DEFAULT_CONTRAST
    for name, value in build_palette(bg_tint, contrast_key).items():
        setattr(C, name, value)


def reset_theme() -> None:
    for name, value in _BASE_TOKENS.items():
        setattr(C, name, value)
