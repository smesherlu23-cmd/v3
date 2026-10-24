from __future__ import annotations

import threading

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


def anim(ms: int = C.ANIM_FAST, spring: bool = False) -> ft.Animation:
    """Анимация на всё окно: замедление к концу, у появления — лёгкая пружина."""
    return ft.Animation(ms, ft.AnimationCurve(C.SPRING if spring else C.EASE))


def later(delay: float, fn) -> None:
    """Сделать что-то через `delay` секунд — в фоне, не держа цикл событий."""
    def run():
        try:
            fn()
        except Exception:
            from ..infra import log
            log.exception("сбой отложенного действия интерфейса")
    timer = threading.Timer(delay, run)
    timer.daemon = True
    timer.start()


def enter(control, start: dict, end: dict, delay: float = 0.04) -> None:
    """Появление с анимацией: сначала начальное состояние, кадр спустя — конечное.

    Flutter анимирует свойство, только если видел прежнее значение: контрол,
    который показали и сразу поставили в конечное состояние, появляется без
    движения. Поэтому начальное ставится сейчас (уйдёт с ближайшей
    перерисовкой), а конечное — чуть позже, отдельным обновлением.
    """
    for key, value in start.items():
        setattr(control, key, value)

    def finish():
        for key, value in end.items():
            setattr(control, key, value)
        safe_update(control)
    later(delay, finish)


def hop(control, height: float = 0.22) -> None:
    """Подскок, как у значка в Dock, когда программа запускается."""
    if not attached(control):
        return
    control.animate_offset = ft.Animation(C.ANIM_HOP_UP, ft.AnimationCurve(C.EASE))
    control.offset = ft.Offset(0, -height)
    safe_update(control)

    def land():
        control.animate_offset = ft.Animation(C.ANIM_HOP_DOWN, ft.AnimationCurve(C.BOUNCE))
        control.offset = ft.Offset(0, 0)
        safe_update(control)
    later(C.ANIM_HOP_UP / 1000, land)


def lift(target: ft.Container, rest: float = 1.0, hover: float = C.HOVER_SCALE):
    """Значок под курсором приподнимается, под нажатием — утапливается.

    Возвращает обработчики для GestureDetector и on_hover: нажатие только
    рисуется, запускает по-прежнему отпускание (нажатие может оказаться
    началом перетаскивания).
    """
    target.animate_scale = anim(C.ANIM_HOVER, spring=True)
    state = {"hot": False}

    def settle():
        target.scale = hover if state["hot"] else rest
        safe_update(target)

    def on_hover(hot: bool):
        state["hot"] = hot
        settle()

    def on_down(e=None):
        target.scale = C.PRESS_SCALE
        safe_update(target)

    def on_up(e=None):
        settle()
    return on_hover, on_down, on_up


def hoverable(container: ft.Container, normal, hover) -> ft.Container:
    def on_hover(e):
        container.bgcolor = hover if entered(e) else normal
        safe_update(container)
    container.bgcolor = normal
    container.on_hover = on_hover
    if container.animate is None:
        container.animate = anim(C.ANIM_FAST)
    return container


def hover_scale(container: ft.Container, scale: float = C.HOVER_SCALE_SUBTLE,
                ms: int = C.ANIM_HOVER) -> ft.Container:
    container.animate_scale = anim(ms, spring=True)
    prior = container.on_hover

    def on_hover(e):
        container.scale = scale if entered(e) else 1.0
        safe_update(container)
        if prior:
            prior(e)

    container.on_hover = on_hover
    return container


def caps(text):
    """Подпись раздела — как в боковой панели macOS: мелко, полужирно, без капса."""
    return T(text, size=C.FS_CAPTION, weight=ft.FontWeight.W_600, color=C.MUTED_2,
             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)


def divider(vertical: int = 0):
    return ft.Container(height=1, bgcolor=C.LINE,
                        margin=ft.Margin.symmetric(vertical=vertical, horizontal=0))


def glass(content=None, radius: int = C.R_LARGE, **kw) -> ft.Container:
    """Матовое стекло: полупрозрачная панель, под которой размыто окно.

    Как у меню и всплывающих панелей macOS: светлая кромка, мягкая тень.
    """
    kw.setdefault("bgcolor", C.GLASS)
    kw.setdefault("border", ft.Border.all(1, C.EDGE))
    kw.setdefault("shadow", ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16),
                                         color=C.SHADOW))
    return ft.Container(content, border_radius=radius, blur=ft.Blur(30, 30),
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS, **kw)


def key_chip(label, accent=None, bright=False):
    return ft.Container(
        T(label, size=C.FS_CAPTION, weight=ft.FontWeight.W_600 if bright else None,
          color=C.on_color(accent) if bright and accent else C.MUTED,
          font_family="monospace"),
        bgcolor=accent if bright and accent else C.CARD,
        border_radius=C.R_SMALL, padding=ft.Padding.symmetric(vertical=2, horizontal=8))


def toggle(value: bool, on_toggle, accent):
    """Переключатель как в macOS: ручка скользит, включённый — цвета акцента."""
    knob = ft.Container(width=18, height=18, border_radius=9, bgcolor=C.WHITE,
                        shadow=ft.BoxShadow(blur_radius=3, offset=ft.Offset(0, 1),
                                            color=C.with_alpha(C.INK, 0.35)))
    return ft.Container(
        knob, width=38, height=22, border_radius=11, padding=ft.Padding.all(2),
        bgcolor=accent if value else C.BORDER,
        alignment=ft.Alignment.CENTER_RIGHT if value else ft.Alignment.CENTER_LEFT,
        on_click=lambda e: on_toggle(not value), animate=anim(C.ANIM_BAR, spring=True))


def segmented(options, current, on_select, height: int = 28):
    """Сегменты как в macOS: серая плашка, выбранный — светлее, с тенью."""
    def segment(label, value, icon=None, tooltip=None):
        active = current == value
        body = (ft.Icon(as_icon(icon), size=16, color=C.TEXT if active else C.MUTED)
                if icon else
                T(label, size=C.FS_BODY, color=C.TEXT if active else C.MUTED,
                  weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400))
        return ft.Container(
            body, height=height - 4, padding=ft.Padding.symmetric(horizontal=12),
            border_radius=C.R_SMALL, alignment=ft.Alignment.CENTER, tooltip=tooltip,
            bgcolor=(C.RAISED if C.MODE == "dark" else C.WHITE) if active else None,
            shadow=ft.BoxShadow(blur_radius=4, offset=ft.Offset(0, 1),
                                color=C.with_alpha(C.INK, 0.25)) if active else None,
            animate=anim(C.ANIM_FAST),
            on_click=lambda e, v=value: on_select(v))
    items = [segment(*opt) for opt in options]
    return ft.Container(ft.Row(items, spacing=2, tight=True), bgcolor=C.CARD,
                        border_radius=C.R, padding=ft.Padding.all(2), height=height)


# Три вида кнопок на всё окно: главная (залитая акцентом — одна на экран),
# второстепенная (серая, как кнопки macOS) и тихая (только текст, подложка
# под курсором). Подчёркнутая ссылка — только для того, что открывается в
# браузере.

def _btn_row(label, icon, color, size, weight):
    row = [T(label, size=size, weight=weight, color=color)]
    if icon:
        row.insert(0, ft.Icon(as_icon(icon), size=16, color=color))
    return ft.Row(row, spacing=6, tight=True, alignment=ft.MainAxisAlignment.CENTER,
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _pressable(btn: ft.Container) -> ft.Container:
    """Нажатие слегка утапливает кнопку — отклик ещё до отпускания."""
    btn.animate_scale = anim(C.ANIM_FAST, spring=True)
    return btn


def primary_btn(label, on_click, accent, icon=None, height=32, expand=False):
    ink = C.on_color(accent)
    btn = ft.Container(
        _btn_row(label, icon, ink, C.FS_BODY, ft.FontWeight.W_600),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=16),
        bgcolor=accent, border_radius=C.R, alignment=ft.Alignment.CENTER, expand=expand,
        shadow=ft.BoxShadow(blur_radius=6, offset=ft.Offset(0, 2),
                            color=C.with_alpha(accent, 0.35)),
        on_click=lambda e: on_click())
    return _pressable(hoverable(btn, accent, C.mix(accent, C.WHITE, 0.12)))


def secondary_btn(label, on_click, icon=None, danger=False, height=32,
                  active=False, icon_color=None, expand=False):
    color = C.ERR_TEXT if danger else C.TEXT
    btn = ft.Container(
        _btn_row(label, icon, color, C.FS_BODY, ft.FontWeight.W_500),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=12),
        bgcolor=C.RAISED if active else C.CARD,
        border_radius=C.R, alignment=ft.Alignment.CENTER, expand=expand,
        on_click=lambda e: on_click())
    if icon and icon_color and not danger:
        btn.content.controls[0].color = icon_color
    if active:
        btn.animate = anim(C.ANIM_FAST)
        return btn
    return _pressable(hoverable(btn, C.CARD, C.RAISED))


def quiet_btn(label, on_click, icon=None, danger=False, height=30, color=None):
    tone = C.ERR_TEXT if danger else (color or C.TEXT_2)
    btn = ft.Container(
        _btn_row(label, icon, tone, C.FS_BODY, ft.FontWeight.W_500),
        height=height, padding=ft.Padding.symmetric(vertical=0, horizontal=10),
        border_radius=C.R, alignment=ft.Alignment.CENTER,
        on_click=lambda e: on_click())
    return hoverable(btn, None, C.CARD)


def icon_btn(icon, tooltip, on_click, size=30, color=None, glyph=18, active=False):
    btn = ft.Container(
        ft.Icon(as_icon(icon), size=glyph, color=color or (C.TEXT if active else C.MUTED)),
        width=size, height=size, border_radius=C.R, alignment=ft.Alignment.CENTER,
        bgcolor=C.RAISED if active else None, tooltip=tooltip,
        on_click=lambda e: on_click())
    if active:
        return btn
    return _pressable(hoverable(btn, None, C.CARD))


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
        inner = ft.Icon(ft.Icons.LAYERS_ROUNDED, size=round(size * 0.5), color=C.MUTED)
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


def dock_dot(on: bool, size: int = 5):
    """Точка «открыто» под значком — как у программ в Dock."""
    return ft.Container(width=size, height=size, border_radius=size / 2,
                        bgcolor=C.TEXT_2 if on else C.TRANSPARENT,
                        animate=anim(C.ANIM_FAST))


def with_badge(control, size: int, badge, badge_size: int):
    """Метка в правом нижнем углу значка: «открыто», «не найден»."""
    return ft.Stack([control, ft.Container(badge, right=-3, bottom=-3)],
                    width=size, height=size, clip_behavior=ft.ClipBehavior.NONE)


def missing_badge(size: int, ring):
    return ft.Container(ft.Icon(ft.Icons.PRIORITY_HIGH_ROUNDED, size=size - 6, color=C.INK),
                        width=size, height=size, border_radius=size / 2, bgcolor=C.WARN,
                        border=ft.Border.all(2, ring), alignment=ft.Alignment.CENTER)


def win_btn(icon_name, tooltip, handler, danger=False):
    c = ft.Container(
        ft.Icon(as_icon(icon_name), size=14, color=C.MUTED),
        width=40, height=30, border_radius=C.R, alignment=ft.Alignment.CENTER,
        animate=anim(C.ANIM_FAST), on_click=lambda e: handler(),
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


def squircle(size: int) -> int:
    """Скругление значка как у иконок macOS — около 22% стороны."""
    return max(4, round(size * 0.22))
