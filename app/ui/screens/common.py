from __future__ import annotations

import flet as ft

from .. import colors as C
from .. import widgets as Wg
from ..format import T


def _caps(text):
    """Подпись раздела: мелко и полужирно, без капса — как в macOS."""
    return Wg.caps(text)


def _screen_header(title, subtitle, on_close, extra=None):
    right = list(extra or [])
    right.append(Wg.icon_btn(ft.Icons.CLOSE_ROUNDED, "Закрыть", on_close, size=32, glyph=18))
    lines = [T(title, size=C.FS_HEADING, weight=ft.FontWeight.BOLD, color=C.TEXT)]
    if subtitle:
        lines.append(T(subtitle, size=C.FS_SMALL, color=C.MUTED_2))
    return ft.Container(
        ft.Row([ft.Column(lines, spacing=4, expand=True, tight=True)] + right,
               spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=24, top=20, right=16, bottom=16),
        border=ft.Border.only(bottom=ft.BorderSide(1, C.LINE)))


def _field(view, key, value, hint, on_change=None, on_submit=None, mono=False, size=None):
    size = size or C.FS_BODY
    return Wg.track_typing(ft.TextField(
        value=value or "", hint_text=hint, border=ft.NoInputBorder(), filled=False,
        dense=True, text_size=size, color=C.TEXT, cursor_color=C.TEXT, expand=True,
        hint_style=ft.TextStyle(color=C.MUTED_2, size=size),
        text_style=ft.TextStyle(font_family="mono") if mono else None,
        content_padding=ft.Padding.symmetric(vertical=0, horizontal=0),
        on_change=on_change, on_submit=on_submit), view, key)
