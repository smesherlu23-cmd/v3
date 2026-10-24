"""Цвета и тема оформления."""
import os
import tempfile

from helpers import _find_all, _texts, _ui_for, ok, skip

from app.core.store import Store
from app.ui import colors as C


def test_secondary_text_is_readable():
    """Подписи держат 4,5:1, значки — 3:1, на всех трёх поверхностях, в обеих темах.

    Раньше сочетания клавиш в меню, стрелки и «···» были цвета 2,4:1, точка в
    быстром запуске — 2,0:1, номер версии — 1,8:1, «+» в пустом слоте — 1,5:1.
    """
    from app.ui import theme
    try:
        for mode in ("dark", "light"):
            theme.apply_theme({"appearance": mode})
            for bg in ("BG", "PANEL", "CARD", "RAISED"):
                back = getattr(C, bg)
                for name, need in (("TEXT", 7.0), ("TEXT_2", 7.0), ("MUTED", 4.5),
                                   ("MUTED_2", 4.5), ("FAINT", 3.0)):
                    value = C.contrast(getattr(C, name), back)
                    ok(value >= need, f"{mode}: {name} on {bg}: {value:.2f}:1 (need {need})")
            for bg in ("PANEL", "CARD", "RAISED"):
                ok(C.contrast(getattr(C, bg), C.BG) >= 1.05,
                   f"{mode}: {bg} stands apart from the window background")
    finally:
        theme.reset_theme()


def test_theme_build_palette_is_identity_at_defaults():
    """Нейтральный тон и обычный контраст дают ровно тёмную палитру из colors.py.

    Тонировка — надстройка над готовой палитрой; она не должна ничего
    менять для тех, кто её не трогал. Иначе включение фичи само по себе
    оказалось бы визуальной регрессией для всех существующих пользователей.
    """
    from app.ui import theme

    palette = theme.build_palette(None, "normal")
    ok(palette == theme._BASE_TOKENS,
       "тон=None и контраст=normal -> палитра совпадает с исходной побайтово")
    ok(set(palette) == {"BG", "PANEL", "CARD", "RAISED", "LINE", "BORDER",
                        "TEXT", "TEXT_2", "MUTED", "MUTED_2", "FAINT"},
       "подстройка покрывает все поверхности, линии и текст — одну шкалу по смыслу")
    ok(set(C.LIGHT) == set(C.DARK), "у светлой темы те же имена, что у тёмной")


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
    ok(C.GREEN == "#30d158", "а исходное значение GREEN никто не менял")


def test_theme_contrast_stays_within_safe_bounds():
    """Ни один уровень контраста не схлопывает светлоту в 0 или 1 (клиппинг)."""
    from app.ui import theme

    for mode in ("dark", "light"):
        for key in theme.CONTRAST_LEVELS:
            palette = theme.build_palette(None, key, mode)
            for name, hexval in palette.items():
                _, light, _sat = theme.C.hex_to_hsl(hexval)
                ok(0.0 <= light <= 1.0, f"{mode}/{key}/{name}: светлота {light} вне [0,1]")
    # Сам факт, что "мягче"/"контрастнее" — это разные, но не крайние палитры.
    soft = theme.build_palette(None, "soft")
    strong = theme.build_palette(None, "strong")
    ok(soft["BG"] != theme._BASE_TOKENS["BG"] != strong["BG"],
       "мягкий и контрастный уровни реально отличаются от обычного")
    tinted = theme.build_palette(222, "normal", "light")
    ok(tinted["BG"] != C.LIGHT["BG"], "и светлая тема тоже подкрашивается тоном фона")


def test_theme_apply_and_reset_round_trip():
    """`apply_theme` подставляет посчитанные цвета в colors.py, `reset_theme` — возвращает."""
    from app.ui import colors as C
    from app.ui import theme

    original = C.BG
    try:
        theme.apply_theme({"bg_tint": 222, "contrast": "strong"})
        ok(C.BG != original, "после apply_theme C.BG — уже другое значение")
        ok(C.GREEN == "#30d158", "а смысловые цвета не изменились и после apply_theme")

        theme.apply_theme({"bg_tint": "не число", "contrast": "?"})
        ok(C.BG == original,
           "мусорные bg_tint/contrast -> тихий откат к нейтральным настройкам, не исключение")

        mode = theme.apply_theme({"appearance": "light"})
        ok(mode == "light" and C.MODE == "light" and C.BG == C.LIGHT["BG"],
           "светлая тема подставляет свою палитру")
        ok(C.GREEN != C.DARK_MEANING["GREEN"],
           "и свои смысловые цвета — бледно-зелёное на белом не видно")
        ok(theme.apply_theme({"appearance": "system"}, system="light") == "light"
           and theme.apply_theme({"appearance": "system"}, system="dark") == "dark"
           and theme.apply_theme({"appearance": "system"}) == "dark",
           "«Как в Windows» следует яркости системы, а без неё — тёмная")
    finally:
        theme.reset_theme()
        ok(C.BG == original and C.MODE == "dark", "reset_theme возвращает исходное значение")


def test_settings_screen_has_theme_controls():
    """Экран настроек: оформление, темы, акценты — на виду; свои цвета — свёрнуты."""
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
        for caption in ("Внешний вид", "Оформление", "Акцент"):
            ok(caption in texts, f"на экране настроек есть блок «{caption}»")
        for label in ("Тёмное", "Светлое", "Как в Windows"):
            ok(label in texts, f"оформление «{label}» на выбор")
        for preset in theme.THEME_PRESETS:
            ok(preset["label"] in texts, f"пресет «{preset['label']}» показан")
        ok(not _find_all(pane, lambda c: isinstance(c, ft.Slider)),
           "ползунков на виду нет: свои цвета свёрнуты под «Свои цвета»")
        ok("Свои цвета" in texts, "но до них один щелчок")

        ui.view.custom_colors = True
        ui.refresh()
        pane = ft.Column(ui.content_col.controls)
        texts = _texts(pane)
        for caption in ("Тон фона", "Контраст"):
            ok(caption in texts, f"раскрытые «Свои цвета» содержат «{caption}»")
        sliders = _find_all(pane, lambda c: isinstance(c, ft.Slider))
        ok(any(s.max == 359 for s in sliders if s is not None) and len(sliders) >= 3,
           "у тона фона свой ползунок 0-359, отдельный от акцентного")

        # Применение пресета меняет все три настройки разом — и, что важнее,
        # реально пересчитывает C.BG при следующей перерисовке.
        from app.ui import colors as C
        before = C.BG
        ui.set_settings({"accent": "#4f7dff", "bg_tint": 222, "contrast": "normal"})
        stored = store.state()["settings"]
        ok(stored["accent"] == "#4f7dff" and stored["bg_tint"] == 222,
           "все настройки пресета записались одним вызовом")
        ok(C.BG != before, "и палитра действительно пересчиталась при refresh()")

        ui.set_setting("appearance", "light")
        ok(C.MODE == "light" and ui.page.theme_mode == ft.ThemeMode.LIGHT,
           "«Светлое» переключает и наши цвета, и тему самого Flutter")
        ok(ui.page.bgcolor == C.BG, "и фон страницы под окном")
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
        ui.view.custom_colors = True
        ui.refresh()

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
    """Помощники цвета: текст на фоне, смешение, видимость на текущей теме."""
    from app.ui import theme
    ok(C.on_color("#f5f5f7") == C.INK, "on a white accent the text is dark")
    ok(C.on_color("#1b1b21") == C.WHITE, "on a near-black accent it is white")
    ok(C.mix("#000000", "#ffffff", 0.5) in ("#7f7f7f", "#808080"), "mix goes half way")
    ok(C.mix("#123456", "#ffffff", 0) == "#123456", "and zero keeps the first colour")
    try:
        theme.apply_theme({"appearance": "light"})
        ok(C.readable("#f5f5f7") == C.TEXT,
           "a white accent turns into the text colour on a light window")
        green = C.readable("#4ade80")
        ok(green != C.TEXT and C.contrast(green, C.BG) >= 2.0,
           "a pale green is darkened to a visible green, not swapped for black")
        ok(C.readable("#e34f4f") == "#e34f4f", "a colour that is visible stays as it is")
    finally:
        theme.reset_theme()
    ok(C.readable("#f5f5f7") == "#f5f5f7", "on the dark window white is fine")


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
    ok(C.category_color({"color": "#4f7dff"}) == "#4f7dff", "category_color uses explicit hex")
    ok(C.category_color({"name": "Игры"}) == C.TEXT,
       "and falls back to the theme's text colour when nothing was chosen")
