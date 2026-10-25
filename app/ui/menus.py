from __future__ import annotations

import flet as ft

from . import colors as C
from . import widgets as Wg
from .format import T, as_icon, cat_icon

ROW_H = 30
HEADER_H = 48
SEPARATOR_H = 11
SUBMENU_W = 240
PAD = 6
# Заголовок меню с линией под ним.
HEADER_BLOCK = HEADER_H + 6
# Меню вырастает из точки щелчка: с левого верхнего угла.
_POP_FROM = ft.Scale(0.94, alignment=ft.Alignment.TOP_LEFT)
_POP_TO = ft.Scale(1.0, alignment=ft.Alignment.TOP_LEFT)


def item(icon, label, on_click, *, hint: str = "", danger: bool = False,
         submenu: bool = False, disabled: bool = False):
    return {"kind": "item", "icon": icon, "label": label, "on_click": on_click,
            "hint": hint, "danger": danger, "submenu": submenu, "disabled": disabled}


def separator():
    return {"kind": "sep"}


def height_of(rows) -> int:
    return sum(SEPARATOR_H if r["kind"] == "sep" else ROW_H for r in rows)


class MenuHost:
    def __init__(self, page: ft.Page, on_dismiss=None, accent=None):
        self.page = page
        self.on_dismiss = on_dismiss
        # Строка под курсором залита акцентом, как в меню macOS.
        self.accent = accent or (lambda: C.ACCENT)
        self.open = False
        self._rows: list[dict] = []
        self._header = None
        self._x = 0.0
        self._y = 0.0
        self._submenu: dict | None = None
        # Где на экране строка, открывшая подменю: оно встаёт рядом с ней.
        self._row_y: float | None = None
        self.shade = ft.Container(left=0, top=0, right=0, bottom=0, bgcolor=C.TRANSPARENT,
                                  on_click=lambda e: self.close())
        self.card = ft.Container(visible=False, animate_opacity=Wg.anim(C.ANIM_POP),
                                 animate_scale=Wg.anim(C.ANIM_POP, spring=True))
        self.sub_card = ft.Container(visible=False)
        self.control = ft.Stack([self.shade, self.card, self.sub_card],
                                left=0, top=0, right=0, bottom=0, visible=False)

    def show(self, x: float, y: float, rows, header=None):
        self._rows = [r for r in rows if r]
        self._header = header
        self._x, self._y = x, y
        self._submenu = None
        self._row_y = None
        appearing = not self.open
        self.open = True
        if appearing:
            Wg.enter(self.card, {"opacity": 0, "scale": _POP_FROM},
                     {"opacity": 1, "scale": _POP_TO})
        self._render()

    def close(self):
        if not self.open:
            return
        self.open = False
        self._submenu = None
        self.control.visible = False
        self.card.visible = False
        self.sub_card.visible = False
        self._safe_update()
        if self.on_dismiss:
            self.on_dismiss()

    def toggle_submenu(self, key: str, rows, anchor_y: float):
        if self._submenu and self._submenu["key"] == key:
            self._submenu = None
        else:
            # Первая строка подменю — вровень со строкой, которая его открыла,
            # как в macOS; раньше оно вставало у верхнего края меню.
            y = anchor_y if self._row_y is None else self._row_y - PAD - 1
            self._submenu = {"key": key, "rows": rows, "y": y}
        self._render()

    def _window(self) -> tuple[float, float]:
        win = getattr(self.page, "window", None)
        return (getattr(win, "width", None) or C.LIBRARY_W,
                getattr(win, "height", None) or C.LIBRARY_H)

    def _place(self, x, y, width, height):
        win_w, win_h = self._window()
        left = x if x + width + 8 <= win_w else max(8.0, x - width)
        top = y if y + height + 8 <= win_h else max(8.0, win_h - height - 8)
        return left, top

    def _render(self):
        width = C.MENU_W if self._header else SUBMENU_W + 22
        height = height_of(self._rows) + (HEADER_BLOCK if self._header else 0) + 2 * PAD + 2
        height = min(height, self._window()[1] - 16)
        left, top = self._place(self._x, self._y, width, height)

        self.card.content = self._card(self._rows, self._header, width, height)
        self.card.left, self.card.top = left, top
        self.card.width = width
        self.card.visible = True

        if self._submenu:
            rows = self._submenu["rows"]
            sub_h = min(height_of(rows) + 2 * PAD + 2, self._window()[1] - 16)
            sub_left, sub_top = self._place(left + width + 6, self._submenu["y"],
                                            SUBMENU_W, sub_h)
            self.sub_card.content = self._card(rows, None, SUBMENU_W, sub_h, main=False)
            self.sub_card.left, self.sub_card.top = sub_left, sub_top
            self.sub_card.width = SUBMENU_W
            self.sub_card.visible = True
        else:
            self.sub_card.visible = False

        self.control.visible = True
        self._safe_update()

    def _card(self, rows, header, width, height=None, main=True):
        children = []
        top = 1 + PAD
        if header is not None:
            children += [header, ft.Container(height=1, bgcolor=C.LINE,
                                              margin=ft.Margin.only(left=8, right=8, bottom=5))]
            top += HEADER_BLOCK
        indent = any_icons(rows)
        for row in rows:
            if row["kind"] == "item":
                children.append(self._row(row, indent, top if main else None))
                top += ROW_H
            else:
                children.append(ft.Container(height=1, bgcolor=C.LINE,
                                             margin=ft.Margin.symmetric(vertical=5,
                                                                        horizontal=8)))
                top += SEPARATOR_H
        full = height_of(rows) + (HEADER_BLOCK if header is not None else 0) + 2 * PAD + 2
        # Длинный список (много программ или категорий) не уходит за край окна,
        # а прокручивается внутри меню.
        scroll = height is not None and full > height
        # Матовое стекло, как у меню macOS: под ним размыто окно.
        return Wg.glass(
            ft.Column(children, spacing=0, tight=not scroll,
                      scroll=ft.ScrollMode.AUTO if scroll else None),
            radius=C.R_LARGE, height=height if scroll else None,
            width=width, padding=ft.Padding.all(PAD))

    def _row(self, row, indent: bool = False, top: float | None = None):
        color = C.ERR_TEXT if row["danger"] else C.TEXT
        icon_color = C.ERR_TEXT if row["danger"] else C.MUTED
        if row["disabled"]:
            color = icon_color = C.FAINT
        controls = []
        tinted = []
        if row["icon"]:
            glyph = ft.Icon(as_icon(row["icon"]), size=16, color=icon_color)
            controls.append(glyph)
            tinted.append((glyph, icon_color))
        elif indent:
            controls.append(ft.Container(width=16))
        label = T(row["label"], size=C.FS_BODY, color=color, expand=True,
                  max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        controls.append(label)
        tinted.append((label, color))
        if row["hint"]:
            # Клавиши — обычным шрифтом, как в меню macOS.
            hint = T(row["hint"], size=C.FS_SMALL, color=C.MUTED_2)
            controls.append(hint)
            tinted.append((hint, C.MUTED_2))
        if row["submenu"]:
            chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=16, color=C.FAINT)
            controls.append(chevron)
            tinted.append((chevron, C.FAINT))

        container = ft.Container(
            ft.Row(controls, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=0, horizontal=10), border_radius=C.R_SMALL,
            height=ROW_H,
            on_click=None if row["disabled"] else (lambda e, r=row: self._fire(r, top)))
        if not row["disabled"]:
            def on_hover(e, c=container, danger=row["danger"]):
                hot = Wg.entered(e)
                fill = (C.DANGER if danger else self.accent()) if hot else None
                ink = C.on_color(fill) if fill else None
                c.bgcolor = fill
                for ctl, rest in tinted:
                    ctl.color = ink or rest
                Wg.safe_update(c)
            container.on_hover = on_hover
        return container

    def _fire(self, row, top: float | None = None):
        self._row_y = None if top is None else (self.card.top or 0) + top
        if not row["submenu"]:
            self.close()
        handler = row["on_click"]
        if handler:
            handler()

    def _safe_update(self):
        try:
            if Wg.attached(self.control):
                self.control.update()
        except Exception:
            from ..infra import log
            log.exception("не удалось обновить контекстное меню")


def any_icons(rows) -> bool:
    """Есть ли в меню значки: тогда строки без значка получают отступ под него."""
    return any(r.get("kind") == "item" and r.get("icon") for r in rows)


def app_header(ui, app, running: bool, missing: bool = False):
    lines = [T(app["name"], size=C.FS_BODY, weight=ft.FontWeight.BOLD, color=C.TEXT,
               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    if missing:
        lines.append(T("файл не найден", size=C.FS_SMALL, color=C.WARN_TEXT))
    elif running:
        lines.append(T(ui.running_note(app), size=C.FS_SMALL, color=C.GREEN_TEXT))
    return ft.Container(ft.Row([ui.icon_slot(app, 32, Wg.squircle(32), glyph=16),
                                ft.Column(lines, spacing=2, tight=True, expand=True)],
                               spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding.only(left=10, top=8, right=10, bottom=8),
                        height=HEADER_H)


def text_header(label: str, count: str = ""):
    row = [T(label, size=C.FS_BODY, weight=ft.FontWeight.BOLD, color=C.TEXT, expand=True,
             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    if count:
        row.append(T(count, size=C.FS_SMALL, color=C.MUTED_2))
    return ft.Container(ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding.only(left=12, top=8, right=12, bottom=8),
                        height=HEADER_H)


def category_header(ui, cat, count: int):
    return ft.Container(
        ft.Row([ft.Icon(cat_icon(cat.get("icon")), size=16, color=C.category_color(cat)),
                T(cat["name"], size=C.FS_BODY, weight=ft.FontWeight.BOLD, color=C.TEXT,
                  expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                T(str(count), size=C.FS_SMALL, color=C.MUTED_2)],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=12, top=8, right=12, bottom=8), height=HEADER_H)
