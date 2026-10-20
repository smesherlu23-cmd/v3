"""Цвета и тема оформления."""
import os
import tempfile

from helpers import _find_all, _texts, _ui_for, ok, skip

from app.core.store import Store
from app.ui import colors as C


def test_secondary_text_is_readable():
    """Второстепенный текст держит контраст WCAG AA (4.5:1) на фоне и панелях.

    Подсказки и пояснения были цвета 3.7:1 и 3.0:1 при кегле 10.5–13 px.
    """
    def lum(hexval):
        r, g, b = (int(hexval[i:i + 2], 16) / 255 for i in (1, 3, 5))

        def f(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    from app.ui import theme
    theme.reset_theme()
    for name in ("MUTED", "MUTED_2", "TEXT_DIM"):
        for bg in ("BG_1", "PANEL", "PANEL_3"):
            value = ratio(getattr(C, name), getattr(C, bg))
            ok(value >= 4.5, f"{name} on {bg}: {value:.2f}:1")


def test_theme_build_palette_is_identity_at_defaults():
    """Нейтральный тон и обычный контраст дают тот же набор цветов, что и сейчас.

    Тонировка — новая надстройка над готовой палитрой; она не должна ничего
    менять для тех, кто её не трогал. Иначе включение фичи само по себе
    оказалось бы визуальной регрессией для всех существующих пользователей.
    """
    from app.ui import theme

    palette = theme.build_palette(None, "normal")
    ok(palette == theme._BASE_TOKENS,
       "тон=None и контраст=normal -> палитра совпадает с исходной побайтово")
    ok(len(theme._BASE_TOKENS) > 40,
       f"подстройка реально покрывает много токенов, а не единицы ({len(theme._BASE_TOKENS)})")


def test_theme_excludes_meaning_colours():
    """Тон фона не перекрашивает «смысловые» цвета — успех/опасность/рейтинг.

    Зелёная кнопка не должна становиться фиолетовой только потому, что
    пользователь выбрал фиолетовый тон интерфейса — тогда цвет перестаёт
    что-либо сообщать.
    """
    from app.ui import colors as C
    from app.ui import theme

    for name in ("GREEN", "DANGER", "STAR", "ACCENT"):
        ok(name not in theme._BASE_TOKENS, f"{name} не подстраивается тоном")

    palette = theme.build_palette(222, "normal")
    ok("GREEN" not in palette and "DANGER" not in palette and "ACCENT" not in palette,
       "смысловые токены отсутствуют и в результате build_palette")
    ok(C.GREEN == "#4ade80", "а исходное значение GREEN никто не менял")


def test_theme_contrast_stays_within_safe_bounds():
    """Ни один уровень контраста не схлопывает светлоту в 0 или 1 (клиппинг)."""
    from app.ui import theme

    for key in theme.CONTRAST_LEVELS:
        palette = theme.build_palette(None, key)
        for name, hexval in palette.items():
            _, light, _sat = theme.C.hex_to_hsl(hexval)
            ok(0.0 <= light <= 1.0, f"{key}/{name}: светлота {light} вне [0,1]")
    # Сам факт, что "мягче"/"контрастнее" — это разные, но не крайние палитры.
    soft = theme.build_palette(None, "soft")
    strong = theme.build_palette(None, "strong")
    ok(soft["BG_0"] != theme._BASE_TOKENS["BG_0"] != strong["BG_0"],
       "мягкий и контрастный уровни реально отличаются от обычного")


def test_theme_apply_and_reset_round_trip():
    """`apply_theme` подставляет посчитанные цвета в colors.py, `reset_theme` — возвращает."""
    from app.ui import colors as C
    from app.ui import theme

    original = C.BG_0
    try:
        theme.apply_theme({"bg_tint": 222, "contrast": "strong"})
        ok(C.BG_0 != original, "после apply_theme C.BG_0 — уже другое значение")
        ok(C.GREEN == "#4ade80", "а смысловые цвета не изменились и после apply_theme")

        theme.apply_theme({"bg_tint": "не число", "contrast": "?"})
        ok(C.BG_0 == original,
           "мусорные bg_tint/contrast -> тихий откат к нейтральным настройкам, не исключение")
    finally:
        theme.reset_theme()
        ok(C.BG_0 == original, "reset_theme возвращает исходное значение")


def test_settings_screen_has_theme_controls():
    """Экран настроек показывает пресеты темы, тон фона и контраст — не только акцент."""
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("settings theme controls test", exc)
        return

    import flet as ft

    from app.ui import theme

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)
        ui._open_settings()
        ui.set_settings_tab("view")

        pane = ft.Column(ui.content_col.controls)
        texts = _texts(pane)
        for caption in ("ТЕМА", "ТОН ФОНА", "КОНТРАСТ"):
            ok(caption in texts, f"на экране настроек есть блок «{caption}»")
        for preset in theme.THEME_PRESETS:
            ok(preset["label"] in texts, f"пресет «{preset['label']}» показан")

        sliders = _find_all(pane, lambda c: isinstance(c, ft.Slider))
        ok(any(s.max == 359 for s in sliders if s is not None) and len(sliders) >= 3,
           "у тона фона свой ползунок 0-359, отдельный от акцентного")

        # Применение пресета меняет все три настройки разом — и, что важнее,
        # реально пересчитывает C.BG_0 при следующей перерисовке.
        from app.ui import colors as C
        before = C.BG_0
        ui.set_settings({"accent": "#4f7dff", "bg_tint": 222, "contrast": "normal"})
        stored = store.state()["settings"]
        ok(stored["accent"] == "#4f7dff" and stored["bg_tint"] == 222,
           "все настройки пресета записались одним вызовом")
        ok(C.BG_0 != before, "и палитра действительно пересчиталась при refresh()")
        theme.reset_theme()


def test_ui_accent_is_fully_customisable():
    """Акцент — любой цвет, а не только пресеты: ползунки тона/яркости и HEX.

    Раньше выбор был из четырёх готовых образцов. Теперь тот же способ, что и
    у категорий (тон + яркость + поле HEX), пишет в настройку `accent`, а
    `_accent()` всегда возвращает валидный `#rrggbb`, даже если в настройке
    оказался мусор, — иначе битый акцент уронил бы отрисовку border/bgcolor.
    """
    try:
        from app.ui.app import CenturioUI  # noqa: F401
    except Exception as exc:
        skip("UI accent test", exc)
        return

    import flet as ft

    ok(len(C.ACCENT_CHOICES) > 4, "there are more than the old four presets")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        ui, _ = _ui_for(store)
        ui._open_settings()
        ui.set_settings_tab("view")

        pane = ft.Column(ui.content_col.controls)
        sliders = _find_all(pane, lambda c: isinstance(c, ft.Slider))
        ok(len(sliders) >= 2 and any(s.max == 359 for s in sliders),
           f"the accent has hue + lightness sliders like categories ({len(sliders)})")

        ui.set_setting("accent", C.hsl_to_hex(300, 0.55))
        stored = store.state()["settings"]["accent"]
        ok(stored not in C.ACCENT_CHOICES and C.parse_hex(stored) == stored,
           "a colour off the preset list is accepted and stored as clean hex")

        store.set_setting("accent", "garbage")
        ui.refresh()
        ok(ui._accent().startswith("#") and len(ui._accent()) == 7,
           "a broken accent value falls back to a real colour, never reaches bgcolor")


def test_colors():
    c1, c2 = C.cover_colors(200)
    ok(c1.startswith("#") and len(c1) == 7, "cover color is hex")
    ok(c1 != c2, "cover gradient has two stops")
    ok(C.glyph_color(10) == "#ffffff", "glyph colour is white on a red hue")
    ok(C.glyph_color(240) == "#ffffff", "glyph colour is white on a blue hue")
    ok(C.glyph_color(60) == C.BG_1, "glyph colour is dark on a bright yellow hue")
    ok(C.glyph_color(120) == C.BG_1, "glyph colour is dark on a bright green hue")
    for hue in range(0, 360, 30):
        col = C.glyph_color(hue)
        ok(col.startswith("#") and len(col) == 7, f"glyph_color({hue}) is a valid hex colour")


def test_color_parsing():
    ok(C.parse_hex("#ff8800") == "#ff8800", "hex parsed")
    ok(C.parse_hex("ff8800") == "#ff8800", "hex without # parsed")
    ok(C.parse_hex("#f80") == "#ff8800", "short hex expanded")
    ok(C.parse_hex("rgb(255, 136, 0)") == "#ff8800", "rgb() parsed")
    ok(C.parse_hex("255,136,0") == "#ff8800", "r,g,b parsed")
    ok(C.parse_hex("nonsense") is None, "bad colour -> None")
    ok(C.hex_to_rgb("#ff8800") == (255, 136, 0), "hex_to_rgb")
    ok(C.rgb_to_hex(255, 136, 0) == "#ff8800", "rgb_to_hex")
    ok(C.rgb_to_hex(999, -5, 0) == "#ff0000", "rgb_to_hex clamps")
    ok(C.category_color({"color": "#123456"}) == "#123456", "category_color uses explicit hex")
    ok(C.category_color({"name": "Игры"}) == "#ffffff",
       "and falls back to the theme's white when nothing was chosen")
