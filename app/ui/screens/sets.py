from __future__ import annotations

import flet as ft

from ...core import layout as L
from ...core.text import KINDS, plu_programs
from .. import colors as C
from .. import widgets as Wg
from ..format import T
from .common import _caps, _field

PANEL_PAD = 16


def build_set_screen(ui, rec):
    return ft.Column([ft.Container(
        ft.Column([_set_header(ui, rec),
                   ft.Row([_layout_column(ui, rec), _order_column(ui, rec)],
                          spacing=24, vertical_alignment=ft.CrossAxisAlignment.START)],
                  spacing=24, tight=True),
        padding=ft.Padding.symmetric(vertical=24, horizontal=24))],
        spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)


def _set_header(ui, rec):
    accel = ui._set_accels.get(rec["id"])
    name = Wg.track_typing(ft.TextField(
        value=rec["name"], border=ft.NoInputBorder(), filled=False, dense=True,
        text_size=C.FS_HEADING, color=C.TEXT, cursor_color=C.TEXT,
        content_padding=ft.Padding.symmetric(vertical=0, horizontal=0),
        text_style=ft.TextStyle(weight=ft.FontWeight.BOLD, font_family="Inter Bold"),
        on_blur=lambda e: ui.set_ops.rename_set(rec["id"], e.control.value),
        on_submit=lambda e: ui.set_ops.rename_set(rec["id"], e.control.value)),
        ui.view, "set_name")
    count = len(rec["items"])
    meta = [T(f"{count} {plu_programs(count)}", size=C.FS_SMALL, color=C.MUTED_2)]
    if accel:
        meta += [_meta_divider(),
                 ft.Container(T(accel, size=C.FS_SMALL, color=C.MUTED, font_family="monospace"),
                              tooltip="Запускает набор, пока открыто окно Centurio")]
    monitor = ft.Container(
        ft.Row([ft.Icon(ft.Icons.DESKTOP_WINDOWS, size=14, color=C.FAINT),
                T(f"Монитор {rec['monitor'] + 1}", size=C.FS_SMALL, color=C.MUTED),
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=C.FAINT)],
               spacing=4, tight=True),
        tooltip="Куда расставлять окна", border_radius=C.R_SMALL,
        padding=ft.Padding.symmetric(vertical=2, horizontal=4),
        on_click=lambda e: ui.context_menus.monitor_menu(rec, e))
    meta += [_meta_divider(), Wg.hoverable(monitor, None, C.CARD)]
    right = [Wg.secondary_btn("Запомнить, как стоят окна",
                              lambda: ui.set_ops.capture_set_layout(rec["id"]),
                              ft.Icons.CENTER_FOCUS_STRONG),
             Wg.primary_btn("Запустить набор", lambda: ui.set_ops.launch_set(rec["id"]),
                            ui._accent(), ft.Icons.PLAY_ARROW)]
    return ft.Row([
        ui.set_mosaic(rec, 48, 12),
        ft.Column([ft.Container(name, height=28),
                   ft.Row(meta, spacing=8, tight=True,
                          vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                  spacing=4, expand=True, tight=True),
    ] + right, spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _meta_divider():
    return ft.Container(width=1, height=12, bgcolor=C.LINE)


def _layout_column(ui, rec):
    head = ft.Row([_caps("РАСКЛАДКА"), ft.Container(height=1, bgcolor=C.LINE, expand=True)],
                  spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    panel = ft.Container(
        ft.Column([_canvas(ui, rec), _no_place(ui, rec)], spacing=12, tight=True),
        bgcolor=C.PANEL, border_radius=C.R_LARGE, padding=ft.Padding.all(PANEL_PAD))
    presets = ft.Row([_preset_thumb(ui, rec, key) for key in L.PRESETS],
                     spacing=8, wrap=True, run_spacing=8)
    return ft.Column([head, panel, presets], spacing=12, tight=True, expand=True)


def _canvas_width(ui) -> float:
    inner = ui._content_width() - 24 * 2 - 24 - C.SET_SIDE_W
    return max(240.0, inner - 2 * PANEL_PAD - 2 * 8)


def _app(ui, app_id):
    return next((a for a in ui.apps() if a["id"] == app_id), None)


def _window_tint(app) -> str:
    """Подложка окна на схеме — с лёгким оттенком цвета программы."""
    return C.mix(C.CARD, C.hsl_to_hex(app.get("hue") or 0, 0.55, 0.55), 0.1)


def _canvas(ui, rec):
    conf = rec["layout"]
    cw, ch = _canvas_width(ui), C.CANVAS_H - 2 - 16
    group = f"slot:{rec['id']}"
    taken = set()
    windows = []
    for entry in rec["items"]:
        rect = L.rect_for(entry, conf["preset"], conf["split"], conf["vsplit"])
        if rect is None:
            continue
        app = _app(ui, entry["app_id"])
        if app is None:
            continue
        if entry.get("slot") is not None:
            taken.add(entry["slot"])
        windows.append(_window(ui, rec, entry, app, rect, cw, ch, group))

    # Пустые места раскладки — цели для перетаскивания из строки «без места».
    targets = []
    for index, (x, y, w, h) in enumerate(L.slots(conf["preset"], conf["split"],
                                                 conf["vsplit"])):
        if index in taken:
            continue
        box = ft.Container(
            T("перетащите сюда программу", size=C.FS_SMALL, color=C.MUTED_2,
              text_align=ft.TextAlign.CENTER),
            border=ft.Border.all(1, C.BORDER), border_radius=C.R_SMALL,
            alignment=ft.Alignment.CENTER, padding=ft.Padding.all(8))
        box.width, box.height = max(40.0, w * cw - 8), max(34.0, h * ch - 8)
        targets.append(ft.Container(ft.DragTarget(
            group=group, content=box,
            on_accept=lambda e, i=index: _drop_on_slot(ui, rec, i, e),
            on_will_accept=lambda e, b=box: _mark(ui, b, True),
            on_leave=lambda e, b=box: _mark(ui, b, False)),
            left=x * cw + 4, top=y * ch + 4))

    children = targets + windows + _split_handles(ui, rec, cw, ch)
    return ft.Container(ft.Stack(children, width=cw, height=ch),
                        height=C.CANVAS_H, bgcolor=C.BG,
                        border=ft.Border.all(1, C.LINE), border_radius=C.R,
                        padding=ft.Padding.all(8))


def _mark(ui, box, on: bool):
    box.border = ft.Border.all(2 if on else 1, ui._accent() if on else C.BORDER)
    Wg.safe_update(box)


def _drop_on_slot(ui, rec, index, e):
    app_id = Wg.dragged_data(e)
    if isinstance(app_id, str):
        ui.set_ops.set_item_slot(rec["id"], app_id, index)


def _window(ui, rec, entry, app, rect, cw, ch, group):
    conf = rec["layout"]
    x, y, w, h = rect
    width, height = max(40.0, w * cw - 8), max(34.0, h * ch - 8)
    icon_size = 40 if min(width, height) >= 110 else 28
    place = (L.slot_label(conf["preset"], entry.get("slot"), conf["split"])
             if entry.get("slot") is not None else "своё место")
    body = ft.Column([
        ui.icon_slot(app, icon_size, 10, glyph=round(icon_size * 0.5)),
        T(app["name"], size=C.FS_SMALL, weight=ft.FontWeight.W_600, color=C.TEXT,
          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER),
        T(place, size=C.FS_CAPTION, color=C.MUTED_2, max_lines=1,
          overflow=ft.TextOverflow.ELLIPSIS),
    ], spacing=4, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER)
    card = ft.Container(
        body, width=width, height=height, bgcolor=_window_tint(app),
        border=ft.Border.all(1, C.BORDER), border_radius=C.R_SMALL,
        padding=ft.Padding.all(8), alignment=ft.Alignment.CENTER,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        tooltip="Перетащите в другое место раскладки")
    slot = entry.get("slot")
    content = ft.Draggable(group=group, content=card, data=entry["app_id"])
    if slot is not None:
        # Окно — тоже цель: брошенная на него программа занимает его место,
        # а прежняя уходит в «без места».
        content = ft.DragTarget(
            group=group, content=content,
            on_accept=lambda e, i=slot: _drop_on_slot(ui, rec, i, e),
            on_will_accept=lambda e, b=card: _mark(ui, b, True),
            on_leave=lambda e, b=card: _mark(ui, b, False))
    return ft.Container(
        ft.GestureDetector(content, on_secondary_tap_down=lambda e, en=entry:
                           ui.context_menus.set_item_menu(rec, en, e)),
        left=x * cw + 4, top=y * ch + 4)


def _split_handles(ui, rec, cw, ch):
    conf = rec["layout"]
    if conf["preset"] not in L.SPLIT_PRESETS:
        return []
    handles = [_handle(ui, rec, "split", conf["split"] * cw - 4, 0, 8, ch, cw,
                       ft.MouseCursor.RESIZE_LEFT_RIGHT)]
    if conf["preset"] in ("6040", "grid4"):
        left = conf["split"] * cw if conf["preset"] == "6040" else 0
        width = cw - left
        handles.append(_handle(ui, rec, "vsplit", left, conf["vsplit"] * ch - 4,
                               width, 8, ch, ft.MouseCursor.RESIZE_UP_DOWN))
    return handles


def _handle(ui, rec, key, left, top, width, height, span, cursor):
    moved = {"by": 0.0}

    def on_update(e):
        moved["by"] += (e.delta_x if key == "split" else e.delta_y) or 0

    def on_end(e):
        if not moved["by"]:
            return
        current = rec["layout"][key]
        ui.set_ops.set_layout_split(rec["id"], key,
                                    L.clamp(current + moved["by"] / max(1.0, span),
                                            L.MIN_SPLIT, L.MAX_SPLIT))
        moved["by"] = 0.0

    return ft.GestureDetector(
        ft.Container(width=width, height=height, border_radius=4),
        left=left, top=top, mouse_cursor=cursor,
        on_pan_update=on_update, on_pan_end=on_end)


def _no_place(ui, rec):
    """Строка под схемой: кто откроется без места и как.

    Notion с пометкой «без места» на схеме не появлялся вовсе, и было неясно,
    что с ним будет при запуске.
    """
    conf = rec["layout"]
    group = f"slot:{rec['id']}"
    chips = []
    for entry in rec["items"]:
        app = _app(ui, entry["app_id"])
        if app is None:
            continue
        kind = KINDS.get(app.get("kind") or "")
        if L.rect_for(entry, conf["preset"], conf["split"], conf["vsplit"]) is not None:
            continue
        note = (f"{kind}, откроется как обычно" if kind
                else "свёрнутым" if entry.get("minimized") else "откроется как обычно")
        chip = ft.Container(
            ft.Row([ui.icon_slot(app, 20, 5, glyph=12),
                    T(app["name"], size=C.FS_SMALL, weight=ft.FontWeight.W_500, color=C.TEXT,
                      max_lines=1),
                    T(note, size=C.FS_SMALL, color=C.MUTED_2, max_lines=1)],
                   spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=32, padding=ft.Padding.only(left=6, right=12), border_radius=16,
            bgcolor=C.CARD,
            tooltip=None if kind else "Перетащите на схему, чтобы дать окну место")
        if kind:
            chips.append(chip)
        else:
            chips.append(ft.GestureDetector(
                ft.Draggable(group=group, content=chip, data=entry["app_id"]),
                mouse_cursor=ft.MouseCursor.GRAB,
                on_secondary_tap_down=lambda e, en=entry: ui.context_menus.set_item_menu(
                    rec, en, e)))
    if not chips:
        return ft.Container(height=0)
    return ft.Row([ft.Container(_caps("БЕЗ МЕСТА"), padding=ft.Padding.only(top=8)),
                   ft.Row(chips, spacing=8, wrap=True, run_spacing=8, expand=True)],
                  spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)


def _preset_thumb(ui, rec, key):
    """Раскладка — миниатюрной схемой: различаются они формой, а не словами."""
    conf = rec["layout"]
    active = conf["preset"] == key
    accent = ui._accent()
    tw, th = 56, 34
    split = conf["split"] if key == conf["preset"] else L.DEFAULT_SPLIT
    vsplit = conf["vsplit"] if key == conf["preset"] else L.DEFAULT_VSPLIT
    cells = [ft.Container(left=x * tw + 1, top=y * th + 1,
                          width=max(4.0, w * tw - 2), height=max(4.0, h * th - 2),
                          border_radius=3, bgcolor=accent if active else C.BORDER)
             for x, y, w, h in L.slots(key, split, vsplit)]
    thumb = ft.Container(ft.Stack(cells, width=tw, height=th), width=tw, height=th)
    btn = ft.Container(
        ft.Column([thumb, T(L.PRESET_LABELS[key], size=C.FS_SMALL,
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                            color=C.TEXT if active else C.MUTED)],
                  spacing=8, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        width=112, padding=ft.Padding.symmetric(vertical=12, horizontal=8), border_radius=C.R,
        bgcolor=C.RAISED if active else C.CARD,
        border=ft.Border.all(1, C.BORDER if active else C.TRANSPARENT),
        tooltip=L.PRESET_LABELS[key],
        on_click=lambda e: ui.set_ops.set_layout_preset(rec["id"], key))
    return btn if active else Wg.hoverable(btn, C.CARD, C.RAISED)


def _order_column(ui, rec):
    head = ft.Row([_caps("ПОРЯДОК ЗАПУСКА"), ft.Container(height=1, bgcolor=C.LINE, expand=True)],
                  spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    rows = [_order_row(ui, rec, entry) for entry in rec["items"]]
    add = ft.Container(
        ft.Row([ft.Icon(ft.Icons.ADD, size=16, color=C.MUTED),
                T("Добавить программу", size=C.FS_BODY, color=C.TEXT_2)],
               spacing=8, tight=True, alignment=ft.MainAxisAlignment.CENTER),
        height=44, border_radius=C.R, border=ft.Border.all(1, C.BORDER),
        alignment=ft.Alignment.CENTER,
        on_click=lambda e: ui.context_menus.add_to_set_picker(rec["id"], e))
    rows.append(Wg.hoverable(add, None, C.RAISED))
    rows.append(_target_row(ui, rec))

    delay = ft.Container(
        ft.Row([T("без паузы" if not rec["delay_seconds"] else f"{rec['delay_seconds']:g} с",
                  size=C.FS_SMALL, color=C.TEXT, font_family="monospace"),
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=C.FAINT)],
               spacing=4, tight=True),
        height=30, padding=ft.Padding.symmetric(horizontal=12),
        bgcolor=C.CARD, border_radius=C.R, alignment=ft.Alignment.CENTER,
        tooltip="Другая пауза",
        on_click=lambda e: ui.context_menus.delay_menu(rec, e))
    settings = [Wg.divider(4),
                _set_option("Пауза между запусками", Wg.hoverable(delay, C.CARD, C.RAISED))]
    return ft.Container(
        ft.Column([head, ft.Column(rows, spacing=8, tight=True)] + settings,
                  spacing=12, tight=True),
        width=C.SET_SIDE_W)


def _target_row(ui, rec):
    field = _field(ui.view, "set_target", "", "Сайт, папка или файл",
                   on_submit=lambda e: ui.in_background(ui.set_ops.add_target, rec["id"],
                                                        e.control.value),
                   size=C.FS_BODY)

    def pick(icon, tip, folder):
        return Wg.icon_btn(icon, tip, lambda: ui.set_ops.pick_target(rec["id"], folder),
                           size=28)

    return ft.Container(
        ft.Row([ft.Icon(ft.Icons.LINK, size=16, color=C.FAINT), field,
                pick(ft.Icons.FOLDER_OPEN, "Выбрать папку", True),
                pick(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, "Выбрать файл", False)],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=44, padding=ft.Padding.only(left=12, right=8), border_radius=C.R,
        bgcolor=C.CARD, tooltip="Вставьте адрес сайта или путь и нажмите Enter")


def _set_option(title, control):
    return ft.Row([T(title, size=C.FS_BODY, color=C.TEXT_2, expand=True), control],
                  spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _order_row(ui, rec, entry):
    app = _app(ui, entry["app_id"])
    if app is None:
        return ft.Container(height=0)
    conf = rec["layout"]
    kind = KINDS.get(app.get("kind") or "")
    placed = L.rect_for(entry, conf["preset"], conf["split"], conf["vsplit"]) is not None
    muted = not placed
    place = (f"{kind} · окно не расставляется" if kind
             else "свёрнутым" if entry.get("minimized")
             else L.slot_label(conf["preset"], entry.get("slot"), conf["split"])
             or ("своё место" if placed else "без места"))
    rest_bg = C.PANEL if muted else C.CARD
    row = ft.Container(
        ft.Row([
            ft.Icon(ft.Icons.DRAG_INDICATOR, size=16, color=C.FAINT),
            ui.icon_slot(app, 32, 8, glyph=16),
            ft.Column([T(app["name"], size=C.FS_BODY, weight=ft.FontWeight.W_500,
                         color=C.TEXT_2 if muted else C.TEXT, max_lines=1,
                         overflow=ft.TextOverflow.ELLIPSIS),
                       T(place, size=C.FS_SMALL, color=C.MUTED_2, max_lines=1,
                         overflow=ft.TextOverflow.ELLIPSIS)],
                      spacing=2, expand=True, tight=True),
            Wg.icon_btn(ft.Icons.MORE_HORIZ, "Меню",
                        lambda en=entry: ui.context_menus.set_item_menu(rec, en, None),
                        size=28, color=C.FAINT),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=52, padding=ft.Padding.only(left=8, right=8), border_radius=C.R,
        bgcolor=rest_bg, border=ft.Border.all(1, C.TRANSPARENT))
    Wg.hoverable(row, rest_bg, C.RAISED)
    tapper = ft.GestureDetector(
        row, on_secondary_tap_down=lambda e, en=entry: ui.context_menus.set_item_menu(rec, en, e))
    group = f"setitem:{rec['id']}"
    rest = C.TRANSPARENT
    return ft.DragTarget(
        group=group,
        content=ft.Draggable(group=group, content=tapper, data=entry["app_id"]),
        on_accept=lambda e, r=row: ui.chrome.drop_set_item(rec["id"], entry["app_id"], e, r, rest),
        on_will_accept=lambda e, r=row: ui.chrome.highlight_drop(r, True, rest),
        on_leave=lambda e, r=row: ui.chrome.highlight_drop(r, False, rest))

