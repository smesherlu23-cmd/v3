from __future__ import annotations

import flet as ft

from ... import __version__
from ...core.hotkeys import format_accel
from .. import colors as C
from .. import theme
from .. import widgets as Wg
from ..format import T
from .common import _caps, _field, _screen_header

# Порядок ровно как в C.ACCENT_CHOICES — имена без хекс-литералов, иначе
# цвет утёк бы из colors.py (это сторожит test_colours_come_from_one_file).
ACCENT_NAMES = dict(zip(C.ACCENT_CHOICES, (
    "Белый", "Синий", "Бирюзовый", "Зелёный",
    "Оранжевый", "Коралловый", "Красный", "Фиолетовый")))

# Тон фона — только градусы, без «нейтрального» серого как отдельного цвета:
# им управляет `None` (см. theme.py). Порядок — под ряд свотчей в интерфейсе.
BG_TINT_CHOICES = (None, 222, 268, 165, 340, 28)
BG_TINT_NAMES = {None: "Нейтральный", 222: "Синий", 268: "Фиолетовый",
                 165: "Зелёный", 340: "Розовый", 28: "Тёплый"}


SETTINGS_TABS = (
    ("view", "Вид", ft.Icons.PALETTE),
    ("keys", "Клавиши", ft.Icons.KEYBOARD),
    ("startup", "Запуск и трей", ft.Icons.POWER_SETTINGS_NEW),
    ("library", "Библиотека", ft.Icons.STORAGE),
)


def build_settings_screen(ui):
    tab = ui.view.settings_tab
    nav_rows = [_settings_nav_row(ui, key, label, icon, key == tab)
                for key, label, icon in SETTINGS_TABS]
    nav = ft.Container(
        ft.Column(nav_rows + [ft.Container(expand=True),
                              T(f"Centurio v{__version__}", size=11, color=C.MUTED_3,
                                font_family="monospace")],
                  spacing=3, expand=True),
        width=C.SETTINGS_NAV_W, padding=ft.padding.only(14, 18, 14, 20),
        border=ft.border.only(right=ft.BorderSide(1, C.LINE_2)))

    body = ft.Container(
        ft.Column(_settings_pane(ui, tab), spacing=17, scroll=ft.ScrollMode.AUTO,
                  expand=True),
        expand=True, padding=ft.padding.only(28, 20, 28, 24))

    return ft.Column([
        _screen_header("Настройки", "Всё сохраняется само", ui.back_to_grid),
        ft.Row([nav, body], spacing=0, expand=True,
               vertical_alignment=ft.CrossAxisAlignment.START),
    ], spacing=0, expand=True)


def _settings_nav_row(ui, key, label, icon, active):
    row = ft.Container(
        ft.Row([ft.Icon(icon, size=16, color=C.TEXT if active else C.MUTED_2),
                T(label, size=13, color=C.TEXT if active else C.MUTED,
                  weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400)],
               spacing=11, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=38, border_radius=9, padding=ft.padding.symmetric(0, 11),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e: ui.set_settings_tab(key))
    if active:
        row.bgcolor = C.PANEL_ACTIVE
        return row
    return Wg.hoverable(row, None, C.SELECTED_BG)


def _group(label, control):
    return ft.Column([_caps(label), ft.Row([control], tight=True)],
                     spacing=9, tight=True)


def _settings_pane(ui, tab):
    if tab == "keys":
        return _settings_keys(ui)
    if tab == "startup":
        return _settings_startup(ui)
    if tab == "library":
        return _settings_library(ui)
    return _settings_view(ui)


def _accent_swatch(ui, col, current):
    selected = col.lower() == current.lower()
    swatch = ft.Container(
        width=30, height=30, border_radius=9, bgcolor=col,
        border=ft.border.all(2, C.ACCENT) if selected else ft.border.all(1, C.LINE_4),
        tooltip=ACCENT_NAMES.get(col),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e, c=col: ui.set_setting("accent", c))
    return Wg.hover_scale(swatch)


def _accent_picker(ui):
    """Готовые акценты плюс произвольный цвет — ползунки тона/яркости и HEX.

    Тот же способ выбора цвета, что и у категорий, только пишет в настройку
    `accent`. Значение всегда прогоняется через parse_hex/hsl_to_hex, так что
    на диск и в bgcolor уходит корректный `#rrggbb`.
    """
    current = ui._accent()
    hue, light, _sat = C.hex_to_hsl(current)

    swatches = ft.Row([_accent_swatch(ui, col, current) for col in C.ACCENT_CHOICES],
                      spacing=9, wrap=True, run_spacing=9, tight=True)

    hex_box = ft.Container(
        ft.Row([ft.Container(width=14, height=14, border_radius=4, bgcolor=current),
                _field(ui.view, "accent_color", current.upper(), "#RRGGBB",
                       mono=True, size=12,
                       on_submit=lambda e: ui.set_setting(
                           "accent", C.parse_hex(e.control.value) or current))],
               spacing=7, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=116, height=32, bgcolor=C.BG_1, border=ft.border.all(1, C.SLOT_BORDER),
        border_radius=8, padding=ft.padding.symmetric(0, 9))

    def slider_row(label, value, maximum, gradient, on_change):
        return ft.Row([
            T(label, size=10.5, color=C.TEXT_DIM, width=26),
            ft.Container(
                ft.Slider(min=0, max=maximum, value=value, on_change_end=on_change,
                          active_color=C.ACCENT, inactive_color=C.TRANSPARENT,
                          thumb_color=current, height=18, expand=True),
                gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                                           end=ft.alignment.center_right,
                                           colors=list(gradient)),
                border_radius=3, height=18, expand=True),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    sliders = ft.Column([
        slider_row("тон", hue, 359, C.HUE_STRIP,
                   lambda e: ui.set_setting("accent",
                                            C.hsl_to_hex(float(e.control.value), light))),
        slider_row("ярк.", light * 100, 100, (C.BG_1, current, C.WHITE),
                   lambda e: ui.set_setting("accent",
                                            C.hsl_to_hex(hue, float(e.control.value) / 100))),
    ], spacing=5, tight=True, expand=True)

    return ft.Column([
        swatches,
        ft.Container(ft.Row([hex_box, sliders], spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER),
                     width=380),
    ], spacing=12, tight=True)


def _theme_preset_chip(ui, preset):
    accent_hex = C.ACCENT_CHOICES[preset["accent"]]
    active = (ui.setting("bg_tint") == preset["bg_tint"]
             and ui.setting("contrast", theme.DEFAULT_CONTRAST) == preset["contrast"]
             and ui._accent().lower() == accent_hex.lower())
    swatch_color = (accent_hex if preset["bg_tint"] is None
                    else C.hsl_to_hex(preset["bg_tint"], 0.5, 0.55))

    def apply(e):
        ui.set_settings({"accent": accent_hex, "bg_tint": preset["bg_tint"],
                         "contrast": preset["contrast"]})

    chip = ft.Container(
        ft.Column([
            ft.Container(width=46, height=30, border_radius=8, bgcolor=swatch_color,
                        border=ft.border.all(1.5, accent_hex)),
            T(preset["label"], size=10.5, color=C.TEXT if active else C.MUTED),
        ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
        padding=ft.padding.all(7), border_radius=11,
        border=ft.border.all(2, ui._accent()) if active else ft.border.all(1, C.TRANSPARENT),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=apply, tooltip=preset["label"])
    return Wg.hover_scale(chip)


def _theme_presets(ui):
    """Быстрый набор акцент + тон фона + контраст одним кликом.

    Дальше это можно тонко подстроить свотчами и ползунками ниже — пресет
    лишь задаёт стартовую точку, а не отдельно хранимый режим.
    """
    return ft.Row([_theme_preset_chip(ui, p) for p in theme.THEME_PRESETS],
                 spacing=10, wrap=True, run_spacing=10, tight=True)


def _bg_tint_swatch(ui, hue, current):
    selected = hue == current
    if hue is None:
        content = ft.Icon(ft.Icons.CLOSE_ROUNDED, size=14, color=C.MUTED_2)
        color = C.BG_1
    else:
        content = None
        color = C.hsl_to_hex(hue, 0.5, 0.55)
    swatch = ft.Container(
        width=30, height=30, border_radius=9, bgcolor=color, content=content,
        alignment=ft.alignment.center,
        border=ft.border.all(2, ui._accent()) if selected else ft.border.all(1, C.LINE_4),
        tooltip=BG_TINT_NAMES.get(hue),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e, h=hue: ui.set_setting("bg_tint", h))
    return Wg.hover_scale(swatch)


def _bg_tint_picker(ui):
    """Едва заметная подкраска фона, панелей и линий под один оттенок.

    В отличие от акцента (кнопки, выделение) это про сам корпус интерфейса —
    та же идея, что подсветка рабочего стола под цвет обоев. `None` —
    нейтральный серый, как было раньше и остаётся по умолчанию.
    """
    current = ui.setting("bg_tint")
    hue = current if isinstance(current, int) else 0

    swatches = ft.Row([_bg_tint_swatch(ui, h, current) for h in BG_TINT_CHOICES],
                      spacing=9, wrap=True, run_spacing=9, tight=True)

    thumb = C.hsl_to_hex(hue, 0.5, 0.55) if current is not None else C.MUTED_2
    slider = ft.Container(
        ft.Row([
            T("тон", size=10.5, color=C.TEXT_DIM, width=26),
            ft.Container(
                ft.Slider(min=0, max=359, value=hue,
                          on_change_end=lambda e: ui.set_setting(
                              "bg_tint", int(float(e.control.value))),
                          active_color=C.ACCENT, inactive_color=C.TRANSPARENT,
                          thumb_color=thumb, height=18, expand=True),
                gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                                           end=ft.alignment.center_right,
                                           colors=list(C.HUE_STRIP)),
                border_radius=3, height=18, expand=True),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=260)

    return ft.Column([swatches, slider], spacing=12, tight=True)


def _contrast_segments(ui):
    return _segments(ui, "contrast", theme.DEFAULT_CONTRAST,
                     (("Мягче", "soft"), ("Обычная", "normal"), ("Контрастнее", "strong")))


def _settings_view(ui):
    return [
        _group("ТЕМА", _theme_presets(ui)),
        ft.Column([_caps("АКЦЕНТ"), _accent_picker(ui)], spacing=10, tight=True),
        ft.Column([_caps("ТОН ФОНА"), _bg_tint_picker(ui)], spacing=10, tight=True),
        _group("КОНТРАСТ", _contrast_segments(ui)),
        _group("ПЛОТНОСТЬ", _tile_segments(ui)),
        _group("ПОЛОСА КАТЕГОРИЙ", _rail_segments(ui)),
        ft.Container(height=1, bgcolor=C.LINE_2),
        _switch(ui, "Показывать «Быстрый запуск»", "show_quick_row"),
        _switch(ui, "Постеры для игр", "game_posters"),
    ]


def _launch_hotkey_field(ui):
    capturing = ui.view.capture and ui.view.capture_target == "launch"
    explicit = ui.setting("launch_hotkey")
    label = "нажмите…" if capturing else format_accel(explicit)
    return ft.Container(
        ft.Row([T(label, size=11.5, color=C.TEXT, font_family="monospace"),
                ft.Icon(ft.Icons.EDIT, size=14, color=C.MUTED_2)],
               spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=32, padding=ft.padding.symmetric(0, 12), bgcolor=C.PANEL,
        border=ft.border.all(1, ui._accent() if capturing else C.TOAST_BORDER),
        border_radius=8, alignment=ft.alignment.center,
        tooltip="Нажмите комбинацию" if capturing else "Другая комбинация",
        on_click=lambda e: ui._begin_capture("launch"))


def _settings_keys(ui):
    return [
        _row("Вызов Centurio", _launch_hotkey_field(ui)),
        ft.Container(height=1, bgcolor=C.LINE_2),
        _settings_note("Своя комбинация для отдельной программы задаётся в панели "
                       "справа от неё, а Ctrl+1…9 раздаются закреплённым в "
                       "«Быстром запуске» сами. Комбинации, которые уже что-то "
                       "делают в Windows — Alt+F4, Win+L и подобные — назначить нельзя."),
    ]


def _settings_startup(ui):
    return [
        _switch(ui, "Запускать с Windows", "autostart"),
        _switch(ui, "Крестик сворачивает в трей", "close_to_tray"),
        _switch(ui, "Прятать окно после запуска", "hide_after"),
    ]


def _settings_library(ui):
    size = ui.icon_cache_size()
    cache_label = f"{size / (1024 * 1024):.0f} МБ" if size else "пусто"
    return [
        _switch(ui, "Складывать новое в разбор", "triage"),
        _switch(ui, "Проверять новое раз в 15 минут", "auto_rescan"),
        ft.Container(height=1, bgcolor=C.LINE_2),
        _row("Кэш иконок",
             ft.Row([T(cache_label, size=11, color=C.MUTED_2, font_family="monospace"),
                     Wg.link_btn("Очистить", ui.clear_icon_cache)], spacing=10, tight=True)),
        _row("Копия библиотеки",
             Wg.outline_btn("Сохранить", ui.backup, ft.Icons.BACKUP, height=32)),
        _row("Файл библиотеки", Wg.link_btn("Показать в папке", ui.show_data_folder)),
        ft.Container(height=1, bgcolor=C.LINE_2),
        _switch(ui, "Подробный лог", "debug_log"),
    ]


def _settings_note(text):
    return ft.Container(
        T(text, size=11.5, color=C.TEXT_DIM),
        padding=ft.padding.all(12), border_radius=10, bgcolor=C.PANEL,
        border=ft.border.all(1, C.LINE_2))


def _row(title, control, on_click=None):
    return ft.Container(
        ft.Row([T(title, size=13, color=C.TEXT_2, expand=True), control],
               spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        on_click=(lambda e: on_click()) if on_click else None)


def _switch(ui, title, key):
    value = bool(ui.setting(key))
    return _row(title,
                Wg.toggle(value, lambda v, k=key: ui.set_setting(k, v), ui._accent()),
                on_click=lambda k=key, v=value: ui.set_setting(k, not v))


def _segments(ui, key, default, options):
    def segment(label, value):
        active = ui.setting(key, default) == value
        return ft.Container(
            T(label, size=12, weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
              color=C.TEXT if active else C.MUTED),
            height=26, padding=ft.padding.symmetric(0, 12), border_radius=6,
            bgcolor=C.PANEL_ACTIVE if active else None, alignment=ft.alignment.center,
            animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
            on_click=lambda e, v=value: ui.set_setting(key, v))
    return ft.Container(ft.Row([segment(label, value) for label, value in options], spacing=0),
                        bgcolor=C.PANEL, border=ft.border.all(1, C.SEGMENT_BORDER),
                        border_radius=8, padding=ft.padding.all(2))


def _tile_segments(ui):
    return _segments(ui, "tile_size", "large",
                     (("Крупные", "large"), ("Плотные", "compact")))


def _rail_segments(ui):
    return _segments(ui, "rail_size", C.DEFAULT_RAIL_SIZE,
                     (("Обычная", "normal"), ("Крупная", "large"), ("Огромная", "huge")))
