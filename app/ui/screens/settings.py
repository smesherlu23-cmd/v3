from __future__ import annotations

import flet as ft

from ... import __version__
from .. import colors as C
from .. import theme
from .. import widgets as Wg
from ..format import T, as_icon
from .common import _caps, _field

# Порядок ровно как в C.ACCENT_CHOICES — имена без хекс-литералов, иначе
# цвет утёк бы из colors.py (это сторожит test_colours_come_from_one_file).
ACCENT_NAMES = dict(zip(C.ACCENT_CHOICES, (
    "Синий", "Фиолетовый", "Розовый", "Красный", "Оранжевый",
    "Жёлтый", "Зелёный", "Графит", "Нейтральный"), strict=True))

# Тон фона — только градусы, без «нейтрального» серого как отдельного цвета:
# им управляет `None` (см. theme.py). Порядок — под ряд свотчей в интерфейсе.
BG_TINT_CHOICES = (None, 222, 268, 165, 340, 28)
BG_TINT_NAMES = {None: "Нейтральный", 222: "Синий", 268: "Фиолетовый",
                 165: "Зелёный", 340: "Розовый", 28: "Тёплый"}


SETTINGS_TABS = (
    ("view", "Вид", ft.Icons.PALETTE_ROUNDED),
    ("keys", "Клавиши", ft.Icons.KEYBOARD_ROUNDED),
    ("startup", "Запуск и трей", ft.Icons.POWER_SETTINGS_NEW_ROUNDED),
    ("library", "Библиотека", ft.Icons.INVENTORY_2_ROUNDED),
)
TAB_TITLES = {key: label for key, label, _icon in SETTINGS_TABS}


def build_settings_screen(ui):
    """Настройки в духе macOS: разделы слева с цветными значками, справа —
    группы-карточки со строками.

    На всю ширину окна: внутри библиотеки рядом оставались полоса категорий и
    боковая панель — три колонки и полтысячи пикселей до первого переключателя.
    """
    tab = ui.view.settings_tab
    nav_rows = [_settings_nav_row(ui, key, label, icon, key == tab)
                for key, label, icon in SETTINGS_TABS]
    nav = ft.Container(
        ft.Column([ft.Container(T("Настройки", size=C.FS_HEADING, weight=ft.FontWeight.BOLD,
                                  color=C.TEXT), padding=ft.Padding.only(left=8, bottom=12))]
                  + nav_rows + [ft.Container(expand=True),
                                ft.Container(T(f"Centurio {__version__}", size=C.FS_SMALL,
                                               color=C.MUTED_2),
                                             padding=ft.Padding.only(left=8))],
                  spacing=2, expand=True),
        width=C.SETTINGS_NAV_W, bgcolor=C.PANEL,
        padding=ft.Padding.only(left=12, top=20, right=12, bottom=16),
        border=ft.Border.only(right=ft.BorderSide(1, C.LINE)))

    title = ft.Row([T(TAB_TITLES.get(tab, "Вид"), size=C.FS_HEADING, weight=ft.FontWeight.BOLD,
                      color=C.TEXT, expand=True),
                    T("Всё сохраняется само", size=C.FS_SMALL, color=C.MUTED_2),
                    Wg.icon_btn(ft.Icons.CLOSE_ROUNDED, "Закрыть", ui.back_to_grid, size=30)],
                   spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    body = ft.Container(
        ft.Column([title] + _settings_pane(ui, tab), spacing=24, scroll=ft.ScrollMode.AUTO,
                  expand=True),
        expand=True, padding=ft.Padding.only(left=32, top=20, right=32, bottom=24))

    return ft.Row([nav, ft.Container(body, width=720)], spacing=0, expand=True,
                  vertical_alignment=ft.CrossAxisAlignment.STRETCH)


def _settings_nav_row(ui, key, label, icon, active):
    tile = ft.Container(ft.Icon(as_icon(icon), size=14, color=C.WHITE), width=22, height=22,
                        border_radius=C.R_SMALL, bgcolor=C.SETTINGS_TINTS.get(key, C.ACCENT),
                        alignment=ft.Alignment.CENTER)
    row = ft.Container(
        ft.Row([tile, T(label, size=C.FS_BODY, color=C.TEXT,
                        weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400)],
               spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=32, border_radius=C.R_SMALL, padding=ft.Padding.symmetric(horizontal=8),
        animate=Wg.anim(C.ANIM_FAST),
        on_click=lambda e: ui.set_settings_tab(key))
    if active:
        row.bgcolor = C.RAISED
        return row
    return Wg.hoverable(row, None, C.CARD)


def _card(rows):
    """Группа строк на одной карточке, с тонкими разделителями — как в macOS."""
    items = []
    for index, row in enumerate(r for r in rows if r is not None):
        if index:
            items.append(ft.Container(height=1, bgcolor=C.LINE, margin=ft.Margin.only(left=16)))
        items.append(row)
    return ft.Container(ft.Column(items, spacing=0, tight=True), bgcolor=C.CARD,
                        border_radius=C.R_LARGE, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def _group(label, rows, note=None):
    items = []
    if label:
        items.append(ft.Container(_caps(label), padding=ft.Padding.only(left=12)))
    items.append(_card(rows))
    if note:
        items.append(ft.Container(T(note, size=C.FS_SMALL, color=C.MUTED_2),
                                  padding=ft.Padding.only(left=12, right=12)))
    return ft.Column(items, spacing=8, tight=True)


def _block(control):
    """Строка без подписи слева — для рядов образцов и раскрытых панелей."""
    return ft.Container(control, padding=ft.Padding.symmetric(vertical=14, horizontal=16))


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
    shown = C.readable(col)
    swatch = ft.Container(
        ft.Icon(ft.Icons.CHECK_ROUNDED, size=16, color=C.on_color(shown)) if selected else None,
        width=32, height=32, border_radius=16, bgcolor=shown,
        border=ft.Border.all(2, C.TEXT) if selected else ft.Border.all(1, C.LINE),
        alignment=ft.Alignment.CENTER, tooltip=ACCENT_NAMES.get(col),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e, c=col: ui.set_setting("accent", c))
    return Wg.hover_scale(swatch)


def _accent_swatches(ui):
    current = C.parse_hex(ui.setting("accent")) or C.ACCENT
    return ft.Row([_accent_swatch(ui, col, current) for col in C.ACCENT_CHOICES],
                  spacing=8, wrap=True, run_spacing=8, tight=True)


def _slider_row(label, value, maximum, gradient, thumb, on_change):
    return ft.Row([
        T(label, size=C.FS_SMALL, color=C.MUTED, width=64),
        ft.Container(
            ft.Slider(min=0, max=maximum, value=value, on_change_end=on_change,
                      active_color=C.TRANSPARENT, inactive_color=C.TRANSPARENT,
                      thumb_color=thumb, height=20, expand=True),
            gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT,
                                       end=ft.Alignment.CENTER_RIGHT,
                                       colors=list(gradient)),
            border_radius=C.R_SMALL, height=20, expand=True),
    ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _custom_accent(ui):
    """Свой цвет акцента: HEX и ползунки тона и яркости."""
    current = C.parse_hex(ui.setting("accent")) or C.ACCENT
    hue, light, _sat = C.hex_to_hsl(current)
    hex_box = ft.Container(
        ft.Row([ft.Container(width=16, height=16, border_radius=4, bgcolor=current),
                _field(ui.view, "accent_color", current.upper(), "#RRGGBB",
                       mono=True, size=C.FS_SMALL,
                       on_submit=lambda e: ui.set_setting(
                           "accent", C.parse_hex(e.control.value) or current))],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=128, height=34, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE),
        border_radius=C.R, padding=ft.Padding.symmetric(horizontal=12))
    sliders = ft.Column([
        _slider_row("Тон", hue, 359, C.HUE_STRIP, current,
                    lambda e: ui.set_setting("accent",
                                             C.hsl_to_hex(float(e.control.value), light))),
        _slider_row("Яркость", light * 100, 100, (C.INK, current, C.WHITE), current,
                    lambda e: ui.set_setting("accent",
                                             C.hsl_to_hex(hue, float(e.control.value) / 100))),
    ], spacing=8, tight=True, width=420)
    return ft.Column([T("Акцент", size=C.FS_BODY, color=C.TEXT_2), hex_box, sliders],
                     spacing=12, tight=True)


def _window_preview(palette: dict, accent: str, width=88, height=56):
    """Мини-окно темы: фон, боковая панель, плитки и пятно акцента.

    Карточка «Угля» раньше показывала белый квадрат — цвет акцента, а не
    темы, и по образцу нельзя было понять, как будет выглядеть окно.
    """
    tile = width * 0.18
    return ft.Container(
        ft.Stack([
            ft.Container(left=0, top=0, bottom=0, width=width * 0.24,
                         bgcolor=palette["PANEL"],
                         border=ft.Border.only(right=ft.BorderSide(1, palette["LINE"]))),
            ft.Container(left=width * 0.32, top=height * 0.16, width=tile, height=tile,
                         border_radius=3, bgcolor=palette["CARD"]),
            ft.Container(left=width * 0.32 + tile + 4, top=height * 0.16, width=tile,
                         height=tile, border_radius=3, bgcolor=palette["CARD"]),
            ft.Container(left=width * 0.32 + 2 * (tile + 4), top=height * 0.16, width=tile,
                         height=tile, border_radius=3, bgcolor=palette["RAISED"]),
            ft.Container(left=width * 0.32, top=height * 0.62, width=width * 0.3, height=5,
                         border_radius=3, bgcolor=palette["MUTED_2"]),
            ft.Container(right=8, bottom=8, width=14, height=14, border_radius=7,
                         bgcolor=accent),
        ]),
        width=width, height=height, bgcolor=palette["BG"], border_radius=C.R_SMALL,
        border=ft.Border.all(1, palette["BORDER"]), clip_behavior=ft.ClipBehavior.HARD_EDGE)


def _theme_card(ui, preset):
    accent_hex = C.ACCENT_CHOICES[preset["accent"]]
    active = (ui.setting("bg_tint") == preset["bg_tint"]
              and ui.setting("contrast", theme.DEFAULT_CONTRAST) == preset["contrast"]
              and (C.parse_hex(ui.setting("accent")) or C.ACCENT).lower() == accent_hex.lower())
    palette = theme.build_palette(preset["bg_tint"], preset["contrast"], C.MODE)
    shown_accent = accent_hex if C.contrast(accent_hex, palette["BG"]) >= 1.6 \
        else palette["TEXT"]

    def apply(e):
        ui.set_settings({"accent": accent_hex, "bg_tint": preset["bg_tint"],
                         "contrast": preset["contrast"]})

    card = ft.Container(
        ft.Column([_window_preview(palette, shown_accent),
                   T(preset["label"], size=C.FS_SMALL,
                     weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                     color=C.TEXT if active else C.MUTED)],
                  spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
        padding=ft.Padding.all(8), border_radius=C.R_LARGE,
        border=ft.Border.all(2, ui._accent() if active else C.TRANSPARENT),
        bgcolor=C.CARD if active else None,
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=apply, tooltip=preset["label"])
    return Wg.hover_scale(card)


def _theme_cards(ui):
    """Готовое сочетание акцента, тона фона и контраста — одним щелчком.

    Дальше его можно подстроить в «Свои цвета» — пресет лишь задаёт стартовую
    точку, а не отдельно хранимый режим.
    """
    return ft.Row([_theme_card(ui, p) for p in theme.THEME_PRESETS],
                  spacing=8, wrap=True, run_spacing=8, tight=True)


def _bg_tint_swatch(ui, hue, current):
    selected = hue == current
    if hue is None:
        content = ft.Icon(ft.Icons.CLOSE_ROUNDED, size=14, color=C.MUTED)
        color = C.CARD
    else:
        content = None
        color = C.hsl_to_hex(hue, 0.5, 0.55)
    swatch = ft.Container(
        width=32, height=32, border_radius=16, bgcolor=color, content=content,
        alignment=ft.Alignment.CENTER,
        border=ft.Border.all(2, C.TEXT) if selected else ft.Border.all(1, C.LINE),
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
                      spacing=8, wrap=True, run_spacing=8, tight=True)
    thumb = C.hsl_to_hex(hue, 0.5, 0.55) if current is not None else C.MUTED
    slider = ft.Container(
        _slider_row("Тон фона", hue, 359, C.HUE_STRIP, thumb,
                    lambda e: ui.set_setting("bg_tint", int(float(e.control.value)))),
        width=420)
    return ft.Column([T("Тон фона", size=C.FS_BODY, color=C.TEXT_2), swatches, slider],
                     spacing=12, tight=True)


def _custom_colors(ui):
    """«Свои цвета» — свёрнуты: темы и готовые акценты закрывают почти всё.

    Четыре пересекающихся способа задать цвет сразу на виду только путали.
    """
    open_now = ui.view.custom_colors

    def toggle(e):
        ui.view.custom_colors = not open_now
        ui.refresh()

    head = ft.Container(
        ft.Row([T("Свои цвета", size=C.FS_BODY, color=C.TEXT, expand=True),
                T("HEX, тон и яркость акцента, тон фона, контраст", size=C.FS_SMALL,
                  color=C.MUTED_2),
                ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED if open_now
                        else ft.Icons.CHEVRON_RIGHT_ROUNDED, size=18, color=C.FAINT)],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=12, horizontal=16), on_click=toggle)
    Wg.hoverable(head, None, C.RAISED)
    if not open_now:
        return [head]
    return [head,
            _block(_custom_accent(ui)),
            _block(_bg_tint_picker(ui)),
            _row("Контраст", _contrast_segments(ui))]


def _contrast_segments(ui):
    return _segments(ui, "contrast", theme.DEFAULT_CONTRAST,
                     (("Мягче", "soft"), ("Обычный", "normal"), ("Контрастнее", "strong")))


def _appearance_segments(ui):
    return _segments(ui, "appearance", theme.DEFAULT_APPEARANCE,
                     (("Тёмное", "dark"), ("Светлое", "light"), ("Как в Windows", "system")))


def _sidebar_segments(ui):
    return Wg.segmented((("С подписями", True), ("Только значки", False)),
                        ui.view.sidebar_open, ui.set_sidebar_open)


def _settings_view(ui):
    return [
        _group("Внешний вид", [
            _row("Оформление", _appearance_segments(ui)),
            _block(_theme_cards(ui)),
            _row("Акцент", _accent_swatches(ui)),
        ] + _custom_colors(ui),
            note="«Как в Windows» следует настройке «Цвет приложений» в Параметрах."),
        _group("Окно", [
            _row("Значки программ", _tile_segments(ui)),
            _row("Боковая панель", _sidebar_segments(ui),
                 sub="В узком окне она сама сворачивается до значков"),
            _switch(ui, "Показывать «Быстрый запуск»", "show_quick_row",
                    "Полка закреплённых программ над сеткой, Ctrl+1…9"),
            _switch(ui, "Постеры для игр", "game_posters",
                    "Обложки Steam и Epic Games вместо значков"),
        ]),
    ]


KEY_HINTS = (
    ("Ctrl+K", "Поиск по библиотеке"),
    ("Ctrl+1…9", "Программы из «Быстрого запуска»"),
    ("Ctrl+Alt+1…9", "Наборы"),
    ("Стрелки, Enter", "Выбрать плитку и запустить"),
    ("Shift+F10", "Меню выбранной плитки"),
    ("Ctrl+A", "Выбрать все плитки на экране"),
    ("Del", "Убрать выбранное (можно вернуть)"),
    ("Ctrl+,", "Настройки"),
    ("Esc", "Закрыть панель, а на главном экране — спрятать окно"),
)


def _key_hint(keys, text):
    return _row(text, ft.Container(T(keys, size=C.FS_SMALL, color=C.TEXT, font_family="monospace"),
                                   height=26, padding=ft.Padding.symmetric(horizontal=10),
                                   bgcolor=C.RAISED, border_radius=C.R_SMALL,
                                   alignment=ft.Alignment.CENTER))


def _settings_keys(ui):
    return [_group("Сочетания клавиш", [_key_hint(keys, text) for keys, text in KEY_HINTS],
                   note="Клавиши работают, только когда открыто окно Centurio: в других "
                        "программах те же сочетания делают то, что делали."),
            _group("Как позвать окно", [_block(T(
                "Щелчком по значку в трее или повторным запуском Centurio. Чтобы звать "
                "окно с клавиатуры, закрепите Centurio на панели задач (правый щелчок по "
                "значку → «Закрепить на панели задач»): тогда Win+цифра — номер значка "
                "слева — откроет уже запущенный Centurio.", size=C.FS_BODY, color=C.TEXT_2))])]


def _settings_startup(ui):
    return [
        _group("Запуск и окно", [
            _switch(ui, "Запускать вместе с Windows", "autostart",
                    "Centurio стартует свёрнутым в трей и ждёт, пока вы его позовёте"),
            _switch(ui, "Закрытие окна оставляет Centurio в трее", "close_to_tray",
                    "Крестик прячет окно, а не выходит. Выйти — «Выход» в меню значка в трее"),
            _switch(ui, "Свёрнутое окно уходит в трей, а не на панель задач",
                    "minimize_to_tray", "Кнопка «Свернуть» прячет окно туда же, куда крестик"),
            _switch(ui, "Прятать окно после запуска программы", "hide_after",
                    "Запустили из поиска — окно Centurio уходит, не мешая"),
        ]),
        _group("Обновления", [
            _switch(ui, "Проверять обновления", "check_updates",
                    "Раз в день Centurio спрашивает GitHub, вышла ли новая версия. "
                    "Ничего о компьютере и библиотеке не отправляется."),
            _row(_update_status(ui), _update_action(ui)),
        ]),
    ]


def _update_status(ui):
    newer = ui.updates.available()
    return f"Вышла версия {newer}" if newer else f"Установлена версия {__version__}"


def _update_action(ui):
    if ui.updates.available():
        return Wg.primary_btn("Скачать", lambda: ui.open_url(ui.updates.url()), ui._accent(),
                              ft.Icons.DOWNLOAD_ROUNDED, height=32)
    return Wg.secondary_btn("Проверить сейчас", ui.updates.check_now, ft.Icons.REFRESH_ROUNDED,
                            height=32)


def _settings_library(ui):
    size = ui.icon_cache_size()
    cache_label = (f"{size / (1024 * 1024):.0f} МБ" if size >= 1024 * 1024
                   else f"{max(1, size // 1024)} КБ" if size else "пусто")
    return [
        _group("Новые программы", [
            _switch(ui, "Новое сначала в «Новые программы»", "triage",
                    "Найденные программы ждут там, пока вы решите, куда их положить"),
            _switch(ui, "Проверять новое раз в 15 минут", "auto_rescan",
                    "Установили программу — она сама появится в «Новых программах»"),
        ]),
        _group("Данные", [
            _row("Кэш значков",
                 ft.Row([T(cache_label, size=C.FS_SMALL, color=C.MUTED_2,
                           font_family="monospace"),
                         Wg.secondary_btn("Очистить", ui.clear_icon_cache, height=28)],
                        spacing=12, tight=True)),
            _row("Копия библиотеки",
                 ft.Row([Wg.secondary_btn("Восстановить…", ui.restore_menu,
                                          ft.Icons.RESTORE_ROUNDED, height=28),
                         Wg.secondary_btn("Сохранить", ui.backup, ft.Icons.BACKUP_ROUNDED,
                                          height=28)],
                        spacing=8, tight=True),
                 sub=_auto_backup_note(ui)),
            _row("Файл библиотеки", Wg.secondary_btn("Показать в папке", ui.show_data_folder,
                                                      ft.Icons.FOLDER_OPEN_ROUNDED,
                                                      height=28)),
            _switch(ui, "Подробный журнал", "debug_log",
                    "Пишет больше подробностей в centurio.log — для разбора ошибок"),
        ]),
    ]


def _auto_backup_note(ui):
    last = ui.last_auto_backup()
    note = "Раз в день Centurio сам сохраняет копию и хранит 7 последних."
    return f"{note} Последняя — {last}." if last else note


def _row(title, control, on_click=None, sub=None):
    left = [T(title, size=C.FS_BODY, color=C.TEXT)]
    if sub:
        left.append(T(sub, size=C.FS_SMALL, color=C.MUTED_2))
    return ft.Container(
        ft.Row([ft.Column(left, spacing=2, tight=True, expand=True), control],
               spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=10, horizontal=16),
        on_click=(lambda e: on_click()) if on_click else None)


def _switch(ui, title, key, sub=None):
    value = bool(ui.setting(key))
    return _row(title,
                Wg.toggle(value, lambda v, k=key: ui.set_setting(k, v), ui._accent()),
                on_click=lambda k=key, v=value: ui.set_setting(k, not v), sub=sub)


def _segments(ui, key, default, options):
    return Wg.segmented(options, ui.setting(key, default),
                        lambda v, k=key: ui.set_setting(k, v))


def _tile_segments(ui):
    return _segments(ui, "tile_size", "large",
                     (("Крупные", "large"), ("Плотные", "compact")))
