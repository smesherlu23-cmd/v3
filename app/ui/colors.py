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

# Поверхности и текст — графит в духе macOS, а не чёрный: фон окна, панель
# (боковая и всплывающие — они светлее фона), поле и наведение. Шаг между
# уровнями виден глазом, поэтому рамки вокруг карточек не нужны. Текст:
# MUTED_2 держит 4,5:1 даже на RAISED, FAINT — 3:1 (только значки: стрелки,
# ручки перетаскивания, «···»).
DARK = {
    "BG": "#1e1e20",        # фон окна
    "PANEL": "#28282b",     # боковая панель, меню, палитра, панель свойств
    "CARD": "#2f2f33",      # поля ввода, кнопки, строки
    "RAISED": "#3a3a3f",    # наведение и выбранное
    "LINE": "#38383c",      # разделители
    "BORDER": "#4c4c52",    # рамки полей
    "TEXT": "#f5f5f7",      # основной текст
    "TEXT_2": "#d6d6db",    # текст второго плана
    "MUTED": "#b0b0b6",     # подписи
    "MUTED_2": "#a4a4aa",   # подсказки, пояснения
    "FAINT": "#8c8c93",     # значки, не текст
}

LIGHT = {
    # Не чисто белый: тон фона из настроек должен его подкрашивать.
    "BG": "#fbfbfd",
    "PANEL": "#f3f3f6",
    "CARD": "#f2f2f5",
    "RAISED": "#e5e5ea",
    "LINE": "#e2e2e7",
    "BORDER": "#c6c6cc",
    "TEXT": "#1d1d1f",
    "TEXT_2": "#3a3a3f",
    "MUTED": "#5a5a60",
    "MUTED_2": "#606066",
    "FAINT": "#7c7c83",
}

# Смысловые цвета тоном фона не подкрашиваются: зелёное «открыто» должно
# оставаться зелёным при любом оформлении. Но в светлой теме им нужна другая
# яркость, иначе жёлтая звезда и зелёная точка тонут в белом.
DARK_MEANING = {
    "GREEN": "#30d158",       # успех, «открыто»
    "DANGER": "#ff453a",      # ошибка, удаление
    "WARN": "#ff9f0a",        # предупреждение: файл не найден
    "STAR": "#ffd60a",        # избранное
    "GREEN_TEXT": "#6ee08f",  # текст тех же цветов — светлее, чтобы читался
    "ERR_TEXT": "#ff8a80",
    "WARN_TEXT": "#ffb84d",
    "ERR_BG": "#3a2224",
    "ERR_BORDER": "#5c2e2e",
    "OK_BG": "#1f3326",
    "OK_BORDER": "#2f5c3c",
    "SCRIM": "#33000000",     # лёгкое затемнение под палитрой
    "SHADOW": "#80000000",    # тень всплывающих панелей
    "EDGE": "#1affffff",      # светлая кромка стекла — как у панелей macOS
}

LIGHT_MEANING = {
    "GREEN": "#248a3d",
    "DANGER": "#d70015",
    "WARN": "#c93400",
    "STAR": "#b8860b",
    "GREEN_TEXT": "#1e7a35",
    "ERR_TEXT": "#b4000f",
    "WARN_TEXT": "#9a3a00",
    "ERR_BG": "#fdecec",
    "ERR_BORDER": "#f2c4c4",
    "OK_BG": "#e8f6ec",
    "OK_BORDER": "#b9e2c6",
    "SCRIM": "#14000000",
    "SHADOW": "#2e000000",
    "EDGE": "#14000000",
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
EDGE = DARK_MEANING["EDGE"]
# Стекло — панель на 82% непрозрачности: под ней размыто то, что за ней.
# Считается от PANEL в `theme.apply_theme`, вместе с тоном фона.
GLASS = "#d128282b"

# Акцент по умолчанию — синий, как в macOS. Белый «нейтральный» остался
# среди готовых: в светлой теме его место занимает почти чёрный
# (см. `readable`).
ACCENT = "#0a84ff"
NEUTRAL_ACCENT = "#f5f5f7"
INK = "#16161a"
WHITE = "#ffffff"
TRANSPARENT = "#00000000"

CAT_PALETTE = ("#0a84ff", "#bf5af2", "#ff375f", "#ff453a",
               "#ff9f0a", "#ffd60a", "#30d158", "#64d2ff",
               "#8e8e93", "#e6e6e8")
# Готовые акценты; произвольный цвет задаётся в «Свои цвета» ползунками тона
# и яркости или полем HEX.
ACCENT_CHOICES = ("#0a84ff", "#bf5af2", "#ff375f", "#ff453a",
                  "#ff9f0a", "#ffd60a", "#30d158", "#8e8e93", "#f5f5f7")

# Значки разделов настроек — цветные квадраты, как в настройках macOS.
SETTINGS_TINTS = {"view": "#0a84ff", "keys": "#8e8e93", "startup": "#30d158",
                  "library": "#ff9f0a"}

POSTER_SCRIM = ("#00000000", "#e8000000")
HUE_STRIP = ("#e34f4f", "#f0a020", "#f5c518", "#4ade80",
             "#3ecfaf", "#4f7dff", "#b06cf0", "#e34f4f")

# Шрифт: шесть размеров. Всё, что нужно прочесть, — от 12; 11 — только
# подписи разделов и метки на клавишах. Крупное набирается плотнее (см.
# format.T): так держится текст в macOS.
FS_CAPTION = 11
FS_SMALL = 12
FS_BODY = 13
FS_TITLE = 15
FS_HEADING = 20
FS_DISPLAY = 26

# Скругления: мелкие детали, кнопки и поля, карточки, большие всплывающие
# панели. Круг — size / 2.
R_SMALL = 6
R = 8
R_LARGE = 12
R_XL = 16

HEADER_H = 52
# Боковая панель — одна, как в Finder: развёрнутая с подписями или узкая
# полоса значков (сама сворачивается в узком окне).
SIDEBAR_W = 240
SIDEBAR_RAIL_W = 64
SIDEBAR_ROW_H = 30

INSPECTOR_W = 320
SEARCH_W = 480
SEARCH_MIN_W = 200
PALETTE_W = 640
# Сетка как в Finder и Launchpad: значок без карточки, имя под ним. В ряд
# на окне 1400 px входит девять программ.
TILE_W = 104
TILE_H = 116
TILE_ICON = 60
TILE_W_COMPACT = 88
TILE_H_COMPACT = 100
TILE_ICON_COMPACT = 48
TILE_GAP = 12
# Ряд быстрого запуска — полка в духе Dock: значки и подписи под ними.
DOCK_ICON = 48
DOCK_CELL = 84
DOCK_SCALE = 1.14
POSTER_W = 104
POSTER_H = 148
POSTER_W_COMPACT = 88
POSTER_H_COMPACT = 124
LIBRARY_W = 1400
LIBRARY_H = 880
LIBRARY_MIN_W = 940
LIBRARY_MIN_H = 620
MENU_W = 280
POPOVER_W = 330
POPOVER_H = 520
TOAST_W = 380
SET_SIDE_W = 300
SETTINGS_NAV_W = 216
CANVAS_H = 280

NARROW_SIDEBAR = 1100

# Движение: короткое и мягкое. Кривые — с замедлением к концу, а у того,
# что появляется (палитра, меню), — с лёгким пружинным перелётом.
ANIM_FAST = 140
ANIM_HOVER = 160
ANIM_BAR = 220
ANIM_TILE = 180
ANIM_POP = 200
# Подскок значка при запуске, как в Dock: вверх быстро, вниз — с отскоком.
ANIM_HOP_UP = 160
ANIM_HOP_DOWN = 520
BOUNCE = "bounceOut"
EASE = "easeOutCubic"
SPRING = "easeOutBack"
HOVER_SCALE = 1.06
HOVER_SCALE_SUBTLE = 1.02
PRESS_SCALE = 0.94


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
    """Белый текст на акценте, а на светлом (жёлтом, зелёном) — тёмный.

    Как в macOS: белое на синем, хотя тёмное там формально контрастнее;
    белый берётся, пока его контраст не ниже 3:1 (полужирная подпись кнопки).
    """
    return WHITE if contrast(WHITE, background) >= 3.0 else INK


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
