"""Цвет, шрифт, скругления и размеры — одна шкала на весь интерфейс.

Цвета названы по смыслу, а не по месту: фон, три уровня поверхностей, две
линии, четыре цвета текста и один для значков, акцент, успех, ошибка,
предупреждение, звезда. Каждое место окна берёт цвет отсюда — так окно не
расползается на десятки серых, отличающихся на процент яркости
(это сторожит test_colours_come_from_one_file).

Значения ниже — тёмная тема. `theme.apply_theme` подставляет вместо них
светлую (`LIGHT`) или подкрашенную тоном фона; поэтому читать цвет нужно в
момент сборки контрола (`C.TEXT`), а не запоминать в значении по умолчанию
аргумента функции.
"""
from __future__ import annotations

import colorsys
import re

# Поверхности и текст. Контраст с фоном: панель 1,07, карточка 1,15, наведение
# 1,28 — шаг, который видно глазом, поэтому рамки вокруг каждой карточки не
# нужны. Текст: MUTED_2 держит 4,5:1 даже на RAISED, FAINT — 3:1 (только
# значки: стрелки, ручки перетаскивания, «···»).
DARK = {
    "BG": "#0b0b0d",        # фон окна
    "PANEL": "#141418",     # то, что лежит поверх фона: меню, палитра, панель свойств
    "CARD": "#1b1b21",      # плитки, строки, поля ввода
    "RAISED": "#24242b",    # наведение и выбранное
    "LINE": "#26262d",      # разделители
    "BORDER": "#383840",    # рамки полей и второстепенных кнопок
    "TEXT": "#e6e6e8",      # основной текст
    "TEXT_2": "#c8ccd0",    # текст второго плана
    "MUTED": "#9aa0a6",     # подписи
    "MUTED_2": "#8a8a93",   # подсказки, пояснения
    "FAINT": "#727782",     # значки, не текст
}

LIGHT = {
    "BG": "#f1f1f4",
    "PANEL": "#f8f8fa",
    "CARD": "#ffffff",
    "RAISED": "#e6e6ec",
    "LINE": "#dedee4",
    "BORDER": "#c4c4cc",
    "TEXT": "#17171c",
    "TEXT_2": "#3a3a42",
    "MUTED": "#565b64",
    "MUTED_2": "#5d626b",
    "FAINT": "#7a7f89",
}

# Смысловые цвета тоном фона не подкрашиваются: зелёное «открыто» должно
# оставаться зелёным при любом оформлении. Но в светлой теме им нужна другая
# яркость, иначе жёлтая звезда и зелёная точка тонут в белом.
DARK_MEANING = {
    "GREEN": "#4ade80",       # успех, «открыто»
    "DANGER": "#e34f4f",      # ошибка, удаление
    "WARN": "#f0a020",        # предупреждение: файл не найден
    "STAR": "#f5c518",        # избранное
    "GREEN_TEXT": "#7ee2a8",  # текст тех же цветов — светлее, чтобы читался
    "ERR_TEXT": "#ee8888",
    "WARN_TEXT": "#f3b45a",
    "ERR_BG": "#1d1214",
    "ERR_BORDER": "#4a2626",
    "OK_BG": "#0f1912",
    "OK_BORDER": "#245233",
    "SCRIM": "#99050507",     # затемнение под палитрой
    "SHADOW": "#a6000000",    # тень всплывающих панелей
}

LIGHT_MEANING = {
    "GREEN": "#16a34a",
    "DANGER": "#dc2626",
    "WARN": "#d97706",
    "STAR": "#c99a00",
    "GREEN_TEXT": "#1e7a43",
    "ERR_TEXT": "#b42323",
    "WARN_TEXT": "#9a5700",
    "ERR_BG": "#fdecec",
    "ERR_BORDER": "#f2c4c4",
    "OK_BG": "#e8f6ec",
    "OK_BORDER": "#b9e2c6",
    "SCRIM": "#40101014",
    "SHADOW": "#30000000",
}

MODE = "dark"

BG = DARK["BG"]
PANEL = DARK["PANEL"]
CARD = DARK["CARD"]
RAISED = DARK["RAISED"]
LINE = DARK["LINE"]
BORDER = DARK["BORDER"]
TEXT = DARK["TEXT"]
TEXT_2 = DARK["TEXT_2"]
MUTED = DARK["MUTED"]
MUTED_2 = DARK["MUTED_2"]
FAINT = DARK["FAINT"]

GREEN = DARK_MEANING["GREEN"]
DANGER = DARK_MEANING["DANGER"]
WARN = DARK_MEANING["WARN"]
STAR = DARK_MEANING["STAR"]
GREEN_TEXT = DARK_MEANING["GREEN_TEXT"]
ERR_TEXT = DARK_MEANING["ERR_TEXT"]
WARN_TEXT = DARK_MEANING["WARN_TEXT"]
ERR_BG = DARK_MEANING["ERR_BG"]
ERR_BORDER = DARK_MEANING["ERR_BORDER"]
OK_BG = DARK_MEANING["OK_BG"]
OK_BORDER = DARK_MEANING["OK_BORDER"]
SCRIM = DARK_MEANING["SCRIM"]
SHADOW = DARK_MEANING["SHADOW"]

# Акцент по умолчанию — почти белый. В светлой теме белое на белом не видно,
# и его место занимает почти чёрный (см. `effective_accent`).
ACCENT = "#f5f5f7"
INK = "#16161a"
WHITE = "#ffffff"
TRANSPARENT = "#00000000"

CAT_PALETTE = ("#e6e6e8", "#f5c518", "#f0a020", "#e34f4f",
               "#b06cf0", "#4f7dff", "#3ecfaf", "#7a8290",
               "#b98cff", "#ff9f6e")
# Готовые акценты — восемь удобных значений; произвольный цвет задаётся
# в «Свои цвета» ползунками тона и яркости или полем HEX.
ACCENT_CHOICES = ("#f5f5f7", "#4f7dff", "#3ecfaf", "#4ade80",
                  "#f0a020", "#ff9f6e", "#e34f4f", "#b06cf0")

POSTER_SCRIM = ("#00000000", "#e8000000")
HUE_STRIP = ("#e34f4f", "#f0a020", "#f5c518", "#4ade80",
             "#3ecfaf", "#4f7dff", "#b06cf0", "#e34f4f")

# Шрифт: шесть размеров. Всё, что нужно прочесть, — от 12; 11 — только
# подписи капителью и метки на клавишах.
FS_CAPTION = 11
FS_SMALL = 12
FS_BODY = 13
FS_TITLE = 15
FS_HEADING = 18
FS_DISPLAY = 24

# Скругления: мелкие детали, кнопки и поля, карточки и панели. Круг — size / 2.
R_SMALL = 6
R = 10
R_LARGE = 14

HEADER_H = 52
RAIL_W = 72
RAIL_BTN = 42
SIDEBAR_W = 232

RAIL_SIZES = {
    "normal": {"rail": 72, "btn": 42, "glyph": 19, "gap": 8},
    "large": {"rail": 84, "btn": 52, "glyph": 23, "gap": 8},
    "huge": {"rail": 100, "btn": 64, "glyph": 28, "gap": 12},
}
# С подписями под значками полоса шире: имя категории в одну строку.
RAIL_LABELS_W = {"normal": 88, "large": 100, "huge": 112}
DEFAULT_RAIL_SIZE = "normal"


def rail_metrics(size, labels: bool = False) -> dict:
    metrics = dict(RAIL_SIZES.get(size) or RAIL_SIZES[DEFAULT_RAIL_SIZE])
    if labels:
        key = size if size in RAIL_LABELS_W else DEFAULT_RAIL_SIZE
        metrics["rail"] = RAIL_LABELS_W[key]
    metrics["labels"] = labels
    return metrics


INSPECTOR_W = 320
SEARCH_W = 560
SEARCH_MIN_W = 220
PALETTE_W = 640
# Плитка: значок крупно, имя под ним, вторая строка — горячая клавиша или
# «открыто». В ряд на 1400 px окна входит восемь программ.
TILE_W = 120
TILE_H = 128
TILE_ICON = 56
TILE_W_COMPACT = 104
TILE_H_COMPACT = 112
TILE_ICON_COMPACT = 44
TILE_GAP = 12
QUICK_W = 132
QUICK_H = 88
POSTER_W = 120
POSTER_H = 180
POSTER_W_COMPACT = 104
POSTER_H_COMPACT = 156
LIBRARY_W = 1400
LIBRARY_H = 880
LIBRARY_MIN_W = 940
LIBRARY_MIN_H = 620
MENU_W = 300
POPOVER_W = 330
POPOVER_H = 520
TOAST_W = 380
SET_SIDE_W = 300
SETTINGS_NAV_W = 216
CANVAS_H = 280

NARROW_SIDEBAR = 1000

ANIM_FAST = 120
ANIM_HOVER = 80
ANIM_BAR = 140
ANIM_TILE = 150
# Плитки и кнопки чуть приподнимаются под курсором — тонко, чтобы читалось как
# отклик, а не как прыжок. Держим здесь, чтобы масштаб был единым по всему UI.
HOVER_SCALE = 1.03
HOVER_SCALE_SUBTLE = 1.02
PRESS_SCALE = 0.97


def _hex(rgb) -> str:
    r, g, b = rgb
    return rgb_to_hex(round(r * 255), round(g * 255), round(b * 255))


def parse_hex(text) -> str | None:
    if not text:
        return None
    s = str(text).strip().lower()
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", s)
    if not m:
        m = re.match(r"(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})$", s)
    if m:
        return rgb_to_hex(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    s = s.lstrip("#")
    if len(s) == 3 and all(c in "0123456789abcdef" for c in s):
        s = "".join(c * 2 for c in s)
    if len(s) == 6 and all(c in "0123456789abcdef" for c in s):
        return "#" + s
    return None


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (parse_hex(hex_color) or "#888888").lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _byte(value) -> int:
    return max(0, min(255, int(value)))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{_byte(r):02x}{_byte(g):02x}{_byte(b):02x}"


def with_alpha(hex_color: str, alpha: float) -> str:
    base = (parse_hex(hex_color) or "#000000").lstrip("#")
    return f"#{_byte(round(alpha * 255)):02x}{base}"


def hsl_to_hex(hue: float, lightness: float, saturation: float = 0.62) -> str:
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0,
                                  max(0.0, min(1.0, lightness)),
                                  max(0.0, min(1.0, saturation)))
    return _hex((r, g, b))


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (v / 255 for v in hex_to_rgb(hex_color))
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, lightness, s


def luminance(hex_color: str) -> float:
    """Относительная яркость по WCAG: 0 — чёрный, 1 — белый."""
    def channel(value):
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_color(background: str) -> str:
    """Тёмный или белый текст — что читается на этом фоне лучше."""
    return INK if contrast(INK, background) >= contrast(WHITE, background) else WHITE


def mix(a: str, b: str, amount: float) -> str:
    """Цвет между a и b: amount=0 — a, 1 — b."""
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    t = max(0.0, min(1.0, amount))
    return rgb_to_hex(round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                      round(ba + (bb - ba) * t))


def readable(color: str) -> str:
    """Цвет, который виден на фоне текущей темы.

    Белый акцент и белые категории в светлой теме — белое на белом: их место
    занимает основной цвет текста. Светлый цветной (салатовый, жёлтый)
    затемняется до различимого оттенка того же тона, а не становится чёрным.
    """
    parsed = parse_hex(color) or TEXT
    if contrast(parsed, BG) >= 2.0:
        return parsed
    hue, light, sat = hex_to_hsl(parsed)
    if sat < 0.2:
        return TEXT
    step = -0.03 if luminance(BG) > 0.5 else 0.03
    for _ in range(30):
        light = max(0.0, min(1.0, light + step))
        candidate = hsl_to_hex(hue, light, sat)
        if contrast(candidate, BG) >= 2.4:
            return candidate
    return TEXT


def category_color(cat: dict) -> str:
    return readable(parse_hex(cat.get("color")) or TEXT)
