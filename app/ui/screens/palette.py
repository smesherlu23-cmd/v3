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
        children.append(_group_head("Программы", first=True))
        children.append(_palette_list([_palette_app_row(ui, r) for r in app_rows]))
    if set_rows:
        children.append(_group_head("Наборы", first=not app_rows))
        children.append(_palette_list([_palette_set_row(ui, r) for r in set_rows]))
    if not rows:
        children.append(_palette_empty(ui))

    app = ui._palette_app(rows)
    actions = queries.palette_actions(app)
    if actions:
        # Подписано, к какой программе относятся действия: после Tab
        # подсветка уходит на них, и строка программы иначе ничем не выделена.
        children.append(_group_head(f"Действия · {app['name']}"))
        children.append(ft.Container(
            ft.Column([_palette_action_row(ui, a, i) for i, a in enumerate(actions)],
                      spacing=2, tight=True),
            padding=ft.Padding.only(left=8, right=8, bottom=8)))
    # Стекло, как у Spotlight: под палитрой размыта сетка.
    return Wg.glass(ft.Column(children, spacing=0, tight=True), radius=C.R_XL,
                    width=C.PALETTE_W, padding=ft.Padding.only(bottom=6),
                    shadow=ft.BoxShadow(blur_radius=60, offset=ft.Offset(0, 24),
                                        color=C.SHADOW))


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
    # Выбранная строка залита акцентом, как в Spotlight; строка, к которой
    # относятся «Действия», — серой подложкой.
    row = ft.Container(
        ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=height, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        bgcolor=ui._accent() if active else (C.RAISED if anchored else None),
        border=ft.Border.all(1, C.TRANSPARENT),
        animate=Wg.anim(C.ANIM_FAST),
        on_click=lambda e: on_click())
    row.on_hover = lambda e, i=index: ui.palette_hover(i, e)
    return row


def _name_spans(ui, name: str, on_accent: bool = False):
    """Совпавшие буквы — полужирным, на обычной строке ещё и цветом акцента.

    Серая подложка совпадения на тёмном фоне была едва видна.
    """
    color = C.on_color(ui._accent()) if on_accent else ui._accent()
    hit = ft.TextStyle(weight=ft.FontWeight.BOLD, font_family="Inter Bold", color=color)
    return [ft.TextSpan(text, hit if matched else None)
            for text, matched in match_spans(name, ui.view.query)]


def _enter_chip(ui):
    ink = C.on_color(ui._accent())
    return ft.Container(T("Enter", size=C.FS_CAPTION, weight=ft.FontWeight.W_600,
                          color=ink, font_family="monospace"),
                        bgcolor=C.with_alpha(ink, 0.18), border_radius=C.R_SMALL,
                        padding=ft.Padding.symmetric(vertical=2, horizontal=8))


def _palette_app_row(ui, row):
    app = row["app"]
    active, anchored = _row_state(ui, row["index"])
    ink = C.on_color(ui._accent())
    right = _enter_chip(ui) if active else None
    sub = queries.app_palette_sub(row, ui.window_count(app))
    if app["id"] in ui.missing:
        sub = " · ".join(p for p in ("файл не найден", sub) if p)
    lines = [T(spans=_name_spans(ui, app["name"], active), size=C.FS_BODY,
               weight=ft.FontWeight.W_500, color=ink if active else C.TEXT, max_lines=1,
               overflow=ft.TextOverflow.ELLIPSIS)]
    if sub:
        lines.append(T(sub, size=C.FS_SMALL,
                       color=C.with_alpha(ink, 0.8) if active else C.MUTED_2,
                       max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
    plate = ui.icon_slot(app, 32, 8, glyph=17)
    return _palette_row(ui, row["index"], plate, lines, right,
                        lambda r=row: ui.palette_click(r))


def _palette_set_row(ui, row):
    rec = row["set"]
    active, _anchored = _row_state(ui, row["index"])
    ink = C.on_color(ui._accent())
    right = _enter_chip(ui) if active else None
    lines = [T(spans=_name_spans(ui, rec["name"], active), size=C.FS_BODY,
               weight=ft.FontWeight.W_500, color=ink if active else C.TEXT, max_lines=1,
               overflow=ft.TextOverflow.ELLIPSIS),
             T(queries.set_palette_sub(rec, row["members"]), size=C.FS_SMALL,
               color=C.with_alpha(ink, 0.8) if active else C.MUTED_2, max_lines=1,
               overflow=ft.TextOverflow.ELLIPSIS)]
    return _palette_row(ui, row["index"], ui.set_mosaic(rec, 32, 7), lines, right,
                        lambda r=row: ui.palette_click(r))


def _palette_action_row(ui, action, index):
    active = ui.view.palette_focus == "actions" and ui.view.palette_index == index
    ink = C.on_color(ui._accent())
    controls = [ft.Container(ft.Icon(as_icon(action["icon"]), size=16,
                                     color=ink if active else C.MUTED),
                             width=32, alignment=ft.Alignment.CENTER),
                T(action["label"], size=C.FS_BODY, color=ink if active else C.TEXT_2,
                  expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    if active:
        controls.append(_enter_chip(ui))
    row = ft.Container(
        ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=36, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        bgcolor=ui._accent() if active else None,
        on_click=lambda e, k=action["key"]: ui.run_palette_action(k))
    if not active:
        Wg.hoverable(row, None, C.RAISED)
    return row


def _palette_empty(ui):
    return ft.Container(
        ft.Row([T("Ничего не найдено", size=C.FS_BODY, color=C.MUTED, expand=True),
                Wg.secondary_btn("Найти на диске", ui.open_add, ft.Icons.SEARCH_ROUNDED,
                                 height=30)],
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=16, top=12, right=12, bottom=12))
