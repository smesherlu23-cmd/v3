from __future__ import annotations

import flet as ft

from ...core import queries
from ...core.text import match_spans
from .. import colors as C
from .. import widgets as Wg
from ..format import T, as_icon
from .common import _caps


def build_palette(ui, rows):
    children = []
    app_rows = [r for r in rows if r["kind"] == "app"]
    set_rows = [r for r in rows if r["kind"] == "set"]

    if app_rows:
        children.append(_group_head("ПРОГРАММЫ", first=True))
        children.append(_palette_list([_palette_app_row(ui, r) for r in app_rows]))
    if set_rows:
        children.append(_group_head("НАБОРЫ", first=not app_rows))
        children.append(_palette_list([_palette_set_row(ui, r) for r in set_rows]))
    if not rows:
        children.append(_palette_empty(ui))

    app = ui._palette_app(rows)
    actions = queries.palette_actions(app)
    if actions:
        # Подписано, к какой программе относятся действия: после Tab
        # подсветка уходит на них, и строка программы иначе ничем не выделена.
        children.append(_group_head(f"ДЕЙСТВИЯ · {app['name'].upper()}"))
        children.append(ft.Container(
            ft.Column([_palette_action_row(ui, a, i) for i, a in enumerate(actions)],
                      spacing=2, tight=True),
            padding=ft.Padding.only(left=8, right=8, bottom=8)))
    return ft.Container(
        ft.Column(children, spacing=0, tight=True),
        width=C.PALETTE_W, bgcolor=C.PANEL,
        border=ft.Border.all(1, C.BORDER), border_radius=C.R_LARGE,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        shadow=ft.BoxShadow(blur_radius=64, offset=ft.Offset(0, 24), color=C.SHADOW))


def _group_head(label, first: bool = False):
    return ft.Container(_caps(label),
                        padding=ft.Padding.only(left=16, top=12 if first else 16, right=16,
                                                bottom=8))


def _palette_list(rows):
    return ft.Container(ft.Column(rows, spacing=2, tight=True),
                        padding=ft.Padding.symmetric(horizontal=8))


def _row_state(ui, index: int) -> tuple[bool, bool]:
    """(активна, держит действия): вторая — строка, к которой относятся «Действия»."""
    on_results = ui.view.palette_focus == "results"
    active = on_results and ui.view.palette_index == index
    anchored = not on_results and ui.view.palette_result == index
    return active, anchored


def _palette_row(ui, index: int, plate, lines, right, on_click, height=48):
    active, anchored = _row_state(ui, index)
    controls = [plate, ft.Column(lines, spacing=2, expand=True, tight=True)]
    if right is not None:
        controls.append(right)
    row = ft.Container(
        ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=height, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        bgcolor=C.RAISED if active else None,
        border=ft.Border.all(1, C.BORDER if anchored else C.TRANSPARENT),
        on_click=lambda e: on_click())
    row.on_hover = lambda e, i=index: ui.palette_hover(i, e)
    return row


def _name_spans(ui, name: str):
    """Совпавшие буквы — полужирным цветом акцента. Серая подложка на тёмном
    фоне была едва видна."""
    accent = ui._accent()
    hit = ft.TextStyle(weight=ft.FontWeight.BOLD, font_family="Inter Bold", color=accent)
    return [ft.TextSpan(text, hit if matched else None)
            for text, matched in match_spans(name, ui.view.query)]


def _palette_app_row(ui, row):
    app = row["app"]
    active, anchored = _row_state(ui, row["index"])
    right = Wg.key_chip("Enter", ui._accent(), bright=True) if active else None
    sub = queries.app_palette_sub(row, ui.window_count(app))
    if app["id"] in ui.missing:
        sub = " · ".join(p for p in ("файл не найден", sub) if p)
    lines = [T(spans=_name_spans(ui, app["name"]), size=C.FS_BODY, weight=ft.FontWeight.W_500,
               color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    if sub:
        lines.append(T(sub, size=C.FS_SMALL, color=C.MUTED if active or anchored
                       else C.MUTED_2, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
    plate = ui.icon_slot(app, 32, 8, glyph=17)
    return _palette_row(ui, row["index"], plate, lines, right,
                        lambda r=row: ui.palette_click(r))


def _palette_set_row(ui, row):
    rec = row["set"]
    active, _anchored = _row_state(ui, row["index"])
    right = Wg.key_chip("Enter", ui._accent(), bright=True) if active else None
    lines = [T(spans=_name_spans(ui, rec["name"]), size=C.FS_BODY, weight=ft.FontWeight.W_500,
               color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
             T(queries.set_palette_sub(rec, row["members"]), size=C.FS_SMALL,
               color=C.MUTED if active else C.MUTED_2, max_lines=1,
               overflow=ft.TextOverflow.ELLIPSIS)]
    return _palette_row(ui, row["index"], ui.set_mosaic(rec, 32, 8), lines, right,
                        lambda r=row: ui.palette_click(r))


def _palette_action_row(ui, action, index):
    active = ui.view.palette_focus == "actions" and ui.view.palette_index == index
    controls = [ft.Container(ft.Icon(as_icon(action["icon"]), size=16,
                                     color=C.TEXT if active else C.MUTED),
                             width=32, alignment=ft.Alignment.CENTER),
                T(action["label"], size=C.FS_BODY, color=C.TEXT if active else C.TEXT_2,
                  expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    if active:
        controls.append(Wg.key_chip("Enter", ui._accent(), bright=True))
    row = ft.Container(
        ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=40, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        bgcolor=C.RAISED if active else None,
        on_click=lambda e, k=action["key"]: ui.run_palette_action(k))
    if not active:
        Wg.hoverable(row, None, C.RAISED)
    return row


def _palette_empty(ui):
    return ft.Container(
        ft.Row([T("Ничего не найдено", size=C.FS_BODY, color=C.MUTED, expand=True),
                Wg.secondary_btn("Найти на диске", ui.open_add, ft.Icons.SEARCH, height=32)],
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=16, top=12, right=12, bottom=12))
