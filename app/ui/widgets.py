from __future__ import annotations

import flet as ft

from ..core.view_state import SEARCH_FIELD
from . import colors as C
from .format import T, as_icon, cat_icon
from .images import icon_image


def attached(control) -> bool:
    """Стоит ли контрол на странице. У отцепленного Flet 1.0 бросает из `.page`."""
    try:
        return control.page is not None
    except RuntimeError:
        return False


def entered(e) -> bool:
    """Курсор вошёл, а не вышел: `e.data` у on_hover — True или False."""
    return e.data is True


def dragged_data(e):
    """`data` перетаскиваемого контрола в событиях DragTarget."""
    return getattr(getattr(e, "src", None), "data", None)


def safe_update(control) -> None:
    try:
        if attached(control):
            control.update()
    except Exception:
        from ..infra import log
        log.exception("сбой при обновлении контрола после устаревшего события")


def track_typing(field: ft.TextField, view, key: str) -> ft.TextField:
    prior_focus, prior_blur, prior_submit = field.on_focus, field.on_blur, field.on_submit
    # Поле, в которое фокус попал при открытой палитре: туда его увёл Tab —
    # Flutter передаёт фокус следующему полю окна. Набранное там (а это
    # продолжение запроса) переименовывало программу из панели справа.
    stray = {"on": False}

    def on_focus(e):
        if view.palette_open and key != SEARCH_FIELD:
            stray["on"] = True
            if view.on_stray_focus:
                view.on_stray_focus()
            return
        stray["on"] = False
        view.start_typing(key)
        if prior_focus:
            prior_focus(e)

    def on_blur(e):
        if stray["on"]:
            stray["on"] = False
            return
        view.stop_typing(key)
        if prior_blur:
            prior_blur(e)

    def on_submit(e):
        if stray["on"]:
            return
        if prior_submit:
            prior_submit(e)

    field.on_focus, field.on_blur = on_focus, on_blur
    if prior_submit:
        field.on_submit = on_submit
    return field


def hoverable(container: ft.Container, normal, hover) -> ft.Container:
    def on_hover(e):
        container.bgcolor = hover if entered(e) else normal
        safe_update(container)
    container.bgcolor = normal
    container.on_hover = on_hover
    return container


def hover_scale(container: ft.Container, scale: float = C.HOVER_SCALE,
                anim: int = C.ANIM_HOVER) -> ft.Container:
    container.animate_scale = ft.Animation(anim, ft.AnimationCurve.EASE_OUT)
    prior = container.on_hover

    def on_hover(e):
        container.scale = scale if entered(e) else 1.0
        safe_update(container)
        if prior:
            prior(e)

    container.on_hover = on_hover
    return container


def caps(text):
    return T(text, size=C.FS_CAPTION, weight=ft.FontWeight.W_600, color=C.MUTED_2,
             style=ft.TextStyle(letter_spacing=0.8))


def divider(vertical: int = 0):
    return ft.Container(height=1, bgcolor=C.LINE,
                        margin=ft.Margin.symmetric(vertical=vertical, horizontal=0))


def key_chip(label, accent=None, bright=False):
    return ft.Container(
        T(label, size=C.FS_CAPTION, weight=ft.FontWeight.W_600 if bright else None,
          color=C.on_color(accent) if bright and accent else C.MUTED,
          font_family="monospace"),
        bgcolor=accent if bright and accent else C.RAISED,
        border=None if bright else ft.Border.all(1, C.LINE),
        border_radius=C.R_SMALL, padding=ft.Padding.symmetric(vertical=2, horizontal=8))


def toggle(value: bool, on_toggle, accent):
    knob = ft.Container(width=14, height=14, border_radius=7,
                        bgcolor=C.on_color(accent) if value else C.MUTED)
    return ft.Container(
        ft.Row([knob], alignment=ft.MainAxisAlignment.END if value
               else ft.MainAxisAlignment.START),
        width=36, height=20, border_radius=10, padding=ft.Padding.all(3),
        bgcolor=accent if value else C.BORDER,
        on_click=lambda e: on_toggle(not value),
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT))


# Три вида кнопок на всё окно: главная (залитая акцентом — одна на экран),
# второстепенная (с рамкой) и тихая (только текст, подложка под курсором).
# Подчёркнутая ссылка — только для того, что открывается в браузере.

def _btn_row(label, icon, color, size, weight):
    row = [T(label, size=size, weight=weight, color=color)]
    if icon:
        row.insert(0, ft.Icon(as_icon(icon), size=16, color=color))
    return ft.Row(row, spacing=8, tight=True, alignment=ft.MainAxisAlignment.CENTER,
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def primary_btn(label, on_click, accent, icon=None, height=36, expand=False):
    ink = C.on_color(accent)
    btn = ft.Container(
        _btn_row(label, icon, ink, C.FS_BODY, ft.FontWeight.W_600),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=16),
        bgcolor=accent, border_radius=C.R, alignment=ft.Alignment.CENTER, expand=expand,
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e: on_click())
    return hover_scale(hoverable(btn, accent, C.mix(accent, ink, 0.12)))


def secondary_btn(label, on_click, icon=None, danger=False, height=36,
                  active=False, icon_color=None, expand=False):
    color = C.ERR_TEXT if danger else C.TEXT
    btn = ft.Container(
        _btn_row(label, icon, color, C.FS_BODY, ft.FontWeight.W_500),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=12),
        bgcolor=C.RAISED if active else None,
        border=ft.Border.all(1, C.ERR_BORDER if danger else C.BORDER),
        border_radius=C.R, alignment=ft.Alignment.CENTER, expand=expand,
        animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
        on_click=lambda e: on_click())
    if icon and icon_color and not danger:
        btn.content.controls[0].color = icon_color
    return btn if active else hoverable(btn, None, C.RAISED)


def quiet_btn(label, on_click, icon=None, danger=False, height=32, color=None):
    tone = C.ERR_TEXT if danger else (color or C.TEXT_2)
    btn = ft.Container(
        _btn_row(label, icon, tone, C.FS_BODY, ft.FontWeight.W_500),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=12),
        border_radius=C.R, alignment=ft.Alignment.CENTER,
        on_click=lambda e: on_click())
    return hoverable(btn, None, C.RAISED)


def icon_btn(icon, tooltip, on_click, size=32, color=None, glyph=16, active=False):
    btn = ft.Container(
        ft.Icon(as_icon(icon), size=glyph, color=color or (C.TEXT if active else C.MUTED)),
        width=size, height=size, border_radius=C.R, alignment=ft.Alignment.CENTER,
        bgcolor=C.RAISED if active else None, tooltip=tooltip,
        on_click=lambda e: on_click())
    return btn if active else hoverable(btn, None, C.RAISED)


def link_btn(label, on_click):
    """Подчёркнутая ссылка — только наружу: сайт, страница загрузки."""
    return ft.Container(
        T(label, size=C.FS_BODY, weight=ft.FontWeight.W_500, color=C.TEXT),
        border=ft.Border.only(bottom=ft.BorderSide(1, C.FAINT)),
        padding=ft.Padding.only(bottom=2), on_click=lambda e: on_click())


def spinner(size=38):
    return ft.ProgressRing(width=size, height=size, stroke_width=2.5,
                           color=C.TEXT, bgcolor=C.LINE)


def mosaic(cells: list, size: int, radius: int):
    """Значок набора: первые четыре программы плиткой 2×2.

    Одинаковый серый значок слоёв у всех наборов их не различал — по мозаике
    состав виден сразу.
    """
    gap = max(2, size // 16)
    pad = max(2, size // 10)
    if not cells:
        inner = ft.Icon(ft.Icons.LAYERS, size=round(size * 0.5), color=C.MUTED)
    elif len(cells) == 1:
        inner = cells[0]
    else:
        rows = [cells[:2], cells[2:4]] if len(cells) > 2 else [cells[:2]]
        inner = ft.Column([ft.Row(r, spacing=gap, tight=True,
                                  alignment=ft.MainAxisAlignment.CENTER) for r in rows],
                          spacing=gap, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          alignment=ft.MainAxisAlignment.CENTER)
    return ft.Container(inner, width=size, height=size, border_radius=radius,
                        bgcolor=C.RAISED, padding=ft.Padding.all(pad),
                        alignment=ft.Alignment.CENTER,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def mosaic_cell(size: int, count: int) -> int:
    """Размер одной клетки мозаики для значка `size` из `count` программ."""
    gap = max(2, size // 16)
    pad = max(2, size // 10)
    inner = size - 2 * pad
    if count <= 1:
        return inner
    return (inner - gap) // 2


def dot(size=6, color=None):
    return ft.Container(width=size, height=size, border_radius=size / 2,
                        bgcolor=color or C.GREEN)


def with_badge(control, size: int, badge, badge_size: int):
    """Метка в правом нижнем углу значка: «открыто», «не найден»."""
    return ft.Stack([control, ft.Container(badge, right=-3, bottom=-3)],
                    width=size, height=size, clip_behavior=ft.ClipBehavior.NONE)


def running_badge(size: int, ring):
    """Зелёный кружок «открыто» с обводкой цвета фона — виден на любом значке."""
    return ft.Container(width=size, height=size, border_radius=size / 2, bgcolor=C.GREEN,
                        border=ft.Border.all(2, ring))


def missing_badge(size: int, ring):
    return ft.Container(ft.Icon(ft.Icons.PRIORITY_HIGH, size=size - 6, color=C.INK),
                        width=size, height=size, border_radius=size / 2, bgcolor=C.WARN,
                        border=ft.Border.all(2, ring), alignment=ft.Alignment.CENTER)


def win_btn(icon_name, tooltip, handler, danger=False):
    c = ft.Container(
        ft.Icon(as_icon(icon_name), size=14, color=C.MUTED),
        width=40, height=32, border_radius=C.R_SMALL, alignment=ft.Alignment.CENTER,
        on_click=lambda e: handler(),
    )

    def on_hover(e):
        if entered(e):
            c.bgcolor = C.DANGER if danger else C.RAISED
            c.content.color = C.WHITE if danger else C.TEXT
        else:
            c.bgcolor = None
            c.content.color = C.MUTED
        safe_update(c)
    c.on_hover = on_hover
    c.tooltip = tooltip
    return c


def cat_glyph_name(cat) -> str:
    return (cat or {}).get("icon") or "folder"


def cat_image(cat, size: int, fill: int | None = None):
    path = (cat or {}).get("image")
    if not path:
        return None
    box = fill or (size + 3)
    art = icon_image(path, width=box, height=box, fit=ft.BoxFit.COVER)
    if art is None:
        return None
    return ft.Container(art, width=box, height=box, border_radius=box / 2,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS)


def cat_glyph(cat, size=19, color=None, fill: int | None = None):
    col = color or (C.category_color(cat) if cat else C.MUTED)
    if cat:
        custom = cat_image(cat, size, fill)
        if custom is not None:
            return custom
    return ft.Icon(cat_icon(cat_glyph_name(cat)), size=size, color=col)


_FIT_BY_KIND = {"cover": ft.BoxFit.COVER, "logo": ft.BoxFit.CONTAIN,
                "contain": ft.BoxFit.CONTAIN}


def icon_slot(app, size: int, radius: int, glyph: int | None = None,
              border=None, glyph_color=None, bgcolor=None, cat=None,
              source_glyph: str = "folder"):
    """Значок программы. Картинка — как есть, без подложки; без картинки — знак
    категории на мягкой подложке, чтобы пустое место не выглядело дырой."""
    fit = _FIT_BY_KIND.get(app.get("icon_fit"), ft.BoxFit.CONTAIN)
    name = cat_glyph_name(cat) if cat else source_glyph
    placeholder = ft.Icon(cat_icon(name), size=glyph or round(size * 0.46),
                          color=glyph_color or C.MUTED)
    cover = app.get("icon_fit") == "cover"
    art_size = size if cover else size - max(2, size // 12)
    inner = icon_image(app.get("icon"), width=art_size, height=art_size, fit=fit,
                       error_content=placeholder)
    plate = inner is None or bgcolor is not None
    if inner is None:
        inner = placeholder
    return ft.Container(
        inner, width=size, height=size, border_radius=radius,
        bgcolor=(bgcolor or C.RAISED) if plate else None,
        border=ft.Border.all(1, border) if border else None,
        alignment=ft.Alignment.CENTER,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
