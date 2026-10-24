from __future__ import annotations

import flet as ft

from .. import colors as C
from .. import widgets as Wg
from ..format import T, as_icon


def build_bulk_bar(ui):
    ids = list(ui.view.sel)

    def action(label, icon, on_click, icon_color=None, arrow=False, danger=False):
        tone = C.ERR_TEXT if danger else C.TEXT
        row = [ft.Icon(as_icon(icon), size=16, color=icon_color or (C.ERR_TEXT if danger
                                                                      else C.MUTED)),
               T(label, size=C.FS_BODY, weight=ft.FontWeight.W_500, color=tone)]
        if arrow:
            row.append(ft.Icon(ft.Icons.KEYBOARD_ARROW_UP, size=14, color=C.FAINT))
        btn = ft.Container(
            ft.Row(row, spacing=8, tight=True), height=36,
            padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
            alignment=ft.Alignment.CENTER, on_click=lambda e: on_click())
        return Wg.hoverable(btn, None, C.RAISED)

    def divider():
        return ft.Container(width=1, height=20, bgcolor=C.LINE,
                            margin=ft.Margin.symmetric(horizontal=4))

    in_hidden = ui.view.filter == "hidden"
    return ft.Container(
        ft.Row([
            T(f"Выбрано {len(ids)}", size=C.FS_BODY, weight=ft.FontWeight.W_600, color=C.TEXT),
            divider(),
            action("Категория", ft.Icons.FOLDER, lambda: ui.context_menus.bulk_menu("cat"),
                   arrow=True),
            action("В набор", ft.Icons.LAYERS, lambda: ui.context_menus.bulk_menu("set"),
                   arrow=True),
            action("В избранное", ft.Icons.STAR, lambda: ui._bulk_favorite(ids),
                   icon_color=C.STAR),
            action("Показать" if in_hidden else "Скрыть",
                   ft.Icons.VISIBILITY if in_hidden else ft.Icons.VISIBILITY_OFF,
                   lambda: ui._hide_apps(ids, not in_hidden)),
            action("Убрать", ft.Icons.DELETE_OUTLINE, lambda: ui._remove_apps(ids),
                   danger=True),
            divider(),
            Wg.quiet_btn("Отмена", ui.toggle_select_mode, height=36, color=C.MUTED),
        ], spacing=4, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=56, bgcolor=C.PANEL, border=ft.Border.all(1, C.BORDER),
        border_radius=C.R_LARGE, padding=ft.Padding.only(left=16, right=8),
        shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16), color=C.SHADOW))
