from __future__ import annotations

import flet as ft

from .. import colors as C
from .. import widgets as Wg
from ..format import ICON_PACK, T, cat_icon
from .common import _caps, _field

AVATAR = 52


def _image_row(ui, cat):
    has_image = bool(cat.get("image"))
    art = Wg.cat_image(cat, AVATAR, fill=AVATAR) if has_image else None
    if art is None:
        art = ft.Container(
            ft.Icon(ft.Icons.ADD_A_PHOTO, size=20, color=C.MUTED),
            width=AVATAR, height=AVATAR, border_radius=AVATAR / 2, bgcolor=C.CARD,
            border=ft.Border.all(1, C.BORDER), alignment=ft.Alignment.CENTER)

    avatar = ft.Container(
        art, width=AVATAR, height=AVATAR, border_radius=AVATAR / 2,
        tooltip="Заменить картинку" if has_image else "Выбрать картинку",
        on_click=lambda e: ui.pick_category_image(cat["id"]))

    buttons = [Wg.secondary_btn("Заменить" if has_image else "Выбрать",
                                lambda: ui.pick_category_image(cat["id"]), height=28)]
    if has_image:
        buttons.append(Wg.quiet_btn("Убрать", lambda: ui.clear_category_image(cat["id"]),
                                    height=28, color=C.MUTED))

    return ft.Container(
        ft.Row([avatar,
                ft.Column([T("Своя картинка", size=C.FS_BODY, color=C.TEXT_2),
                           T("PNG, JPG, WEBP, GIF или SVG", size=C.FS_SMALL, color=C.MUTED_2),
                           ft.Row(buttons, spacing=8, tight=True)],
                          spacing=4, expand=True, tight=True)],
               spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=C.CARD, border_radius=C.R,
        padding=ft.Padding.all(12), margin=ft.Margin.only(top=8))


def build_category_popover(ui, cat):
    color = C.category_color(cat)
    hue, lightness, _sat = C.hex_to_hsl(color)

    name_field = Wg.track_typing(ft.TextField(
        value=cat["name"], border=ft.NoInputBorder(), filled=False, dense=True,
        text_size=C.FS_BODY, color=C.TEXT, cursor_color=C.TEXT, expand=True,
        content_padding=ft.Padding.symmetric(vertical=0, horizontal=0),
        text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
        on_blur=lambda e: ui.rename_category(cat["id"], e.control.value),
        on_submit=lambda e: ui.rename_category(cat["id"], e.control.value)),
        ui.view, "category_name")

    header = ft.Row([
        ft.Container(Wg.cat_glyph(cat, size=18, fill=34 if cat.get("image") else None),
                     width=36, height=36,
                     border_radius=18 if cat.get("image") else C.R,
                     bgcolor=C.RAISED,
                     alignment=ft.Alignment.CENTER,
                     clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
        ft.Container(name_field, height=34, bgcolor=C.CARD,
                     border=ft.Border.all(1, C.LINE), border_radius=C.R,
                     padding=ft.Padding.symmetric(horizontal=12), expand=True),
        Wg.icon_btn(ft.Icons.CLOSE, "Закрыть", ui.close_popover),
    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    swatches = [ft.Container(
        width=24, height=24, border_radius=12, bgcolor=hexval,
        border=ft.Border.all(2, C.TEXT) if hexval.lower() == color.lower()
        else ft.Border.all(1, C.LINE),
        tooltip=hexval.upper(),
        on_click=lambda e, h=hexval: ui.set_category_color(cat["id"], h))
        for hexval in C.CAT_PALETTE]

    hex_box = ft.Container(
        ft.Row([ft.Container(width=14, height=14, border_radius=4, bgcolor=color),
                _field(ui.view, "category_color", color.upper(), "#RRGGBB",
                       mono=True, size=C.FS_SMALL,
                       on_submit=lambda e: ui.set_category_color(
                           cat["id"], C.parse_hex(e.control.value) or color))],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=112, height=34, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE),
        border_radius=C.R, padding=ft.Padding.symmetric(horizontal=12))

    def slider_row(label, value, maximum, gradient, on_change):
        return ft.Row([
            T(label, size=C.FS_SMALL, color=C.MUTED, width=56),
            ft.Container(
                ft.Slider(min=0, max=maximum, value=value, on_change_end=on_change,
                          active_color=C.TRANSPARENT, inactive_color=C.TRANSPARENT,
                          thumb_color=color, height=18, expand=True),
                gradient=ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT,
                                           end=ft.Alignment.CENTER_RIGHT,
                                           colors=list(gradient)),
                border_radius=C.R_SMALL, height=18, expand=True,
                padding=ft.Padding.symmetric(vertical=0, horizontal=0)),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    sliders = ft.Column([
        slider_row("Тон", hue, 359, C.HUE_STRIP,
                   lambda e: ui.set_category_color(
                       cat["id"], C.hsl_to_hex(float(e.control.value), lightness))),
        slider_row("Яркость", lightness * 100, 100, (C.INK, color, C.WHITE),
                   lambda e: ui.set_category_color(
                       cat["id"], C.hsl_to_hex(hue, float(e.control.value) / 100))),
    ], spacing=8, tight=True, expand=True)

    cells = [ft.Container(
        ft.Icon(cat_icon(name), size=18,
                color=color if name == cat.get("icon") and not cat.get("image") else C.TEXT_2),
        width=36, height=36, border_radius=C.R,
        bgcolor=C.RAISED if name == cat.get("icon") else C.CARD,
        border=ft.Border.all(2, C.TEXT) if name == cat.get("icon") and not cat.get("image")
        else ft.Border.all(1, C.TRANSPARENT),
        alignment=ft.Alignment.CENTER, tooltip=name,
        on_click=lambda e, n=name: ui.set_category_icon(cat["id"], n)) for name in ICON_PACK]

    image_row = _image_row(ui, cat)

    footer = ft.Container(
        ft.Row([ft.Container(
            Wg.quiet_btn("Удалить категорию", lambda: ui._remove_category(cat["id"]),
                         ft.Icons.DELETE_OUTLINE, danger=True))],
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(top=12), margin=ft.Margin.only(top=8),
        border=ft.Border.only(top=ft.BorderSide(1, C.LINE)))

    return ft.Container(
        ft.Column([
            header,
            _caps("ЦВЕТ"),
            ft.Row(swatches, spacing=8, wrap=True, run_spacing=8),
            ft.Row([hex_box, sliders], spacing=12,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            Wg.divider(8),
            _caps("ИКОНКА"),
            ft.Container(ft.Column([ft.Row(cells, spacing=4, wrap=True, run_spacing=4)],
                                   scroll=ft.ScrollMode.AUTO), height=120),
            image_row,
            footer,
        ], spacing=12, tight=True),
        width=C.POPOVER_W, bgcolor=C.PANEL, border=ft.Border.all(1, C.LINE),
        border_radius=C.R_LARGE, padding=ft.Padding.all(16),
        shadow=ft.BoxShadow(blur_radius=48, offset=ft.Offset(0, 16), color=C.SHADOW))
