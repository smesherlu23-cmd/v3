from __future__ import annotations

import flet as ft

from . import colors as C
from . import widgets as Wg
from .format import T, as_icon, cat_icon

ROW_H = 36
HEADER_H = 48
SEPARATOR_H = 11
SUBMENU_W = 240


def item(icon, label, on_click, *, hint: str = "", danger: bool = False,
         submenu: bool = False, disabled: bool = False):
    return {"kind": "item", "icon": icon, "label": label, "on_click": on_click,
            "hint": hint, "danger": danger, "submenu": submenu, "disabled": disabled}


def separator():
    return {"kind": "sep"}


def height_of(rows) -> int:
    return sum(SEPARATOR_H if r["kind"] == "sep" else ROW_H for r in rows)


class MenuHost:
    def __init__(self, page: ft.Page, on_dismiss=None):
        self.page = page
        self.on_dismiss = on_dismiss
        self.open = False
        self._rows: list[dict] = []
        self._header = None
        self._x = 0.0
        self._y = 0.0
        self._submenu: dict | None = None
        self.shade = ft.Container(left=0, top=0, right=0, bottom=0, bgcolor=C.TRANSPARENT,
                                  on_click=lambda e: self.close())
        self.card = ft.Container(visible=False)
        self.sub_card = ft.Container(visible=False)
        self.control = ft.Stack([self.shade, self.card, self.sub_card],
                                left=0, top=0, right=0, bottom=0, visible=False)

    def show(self, x: float, y: float, rows, header=None):
        self._rows = [r for r in rows if r]
        self._header = header
        self._x, self._y = x, y
        self._submenu = None
        self.open = True
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
            self._submenu = {"key": key, "rows": rows, "y": anchor_y}
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
        height = height_of(self._rows) + (HEADER_H if self._header else 0) + 16
        height = min(height, self._window()[1] - 16)
        left, top = self._place(self._x, self._y, width, height)

        self.card.content = self._card(self._rows, self._header, width, height)
        self.card.left, self.card.top = left, top
        self.card.width = width
        self.card.visible = True

        if self._submenu:
            rows = self._submenu["rows"]
            sub_h = min(height_of(rows) + 16, self._window()[1] - 16)
            sub_left, sub_top = self._place(left + width + 6, self._submenu["y"],
                                            SUBMENU_W, sub_h)
            self.sub_card.content = self._card(rows, None, SUBMENU_W, sub_h)
            self.sub_card.left, self.sub_card.top = sub_left, sub_top
            self.sub_card.width = SUBMENU_W
            self.sub_card.visible = True
        else:
            self.sub_card.visible = False

        self.control.visible = True
        self._safe_update()

    def _card(self, rows, header, width, height=None):
        children = []
        if header is not None:
            children += [header, ft.Container(height=1, bgcolor=C.LINE,
                                              margin=ft.Margin.only(left=4, right=4, bottom=6))]
        indent = any_icons(rows)
        for row in rows:
            children.append(self._row(row, indent) if row["kind"] == "item" else
                            ft.Container(height=1, bgcolor=C.LINE,
                                         margin=ft.Margin.symmetric(vertical=5, horizontal=4)))
        full = height_of(rows) + (HEADER_H if header is not None else 0) + 16
        # Длинный список (много программ или категорий) не уходит за край окна,
        # а прокручивается внутри меню.
        scroll = height is not None and full > height
        return ft.Container(
            ft.Column(children, spacing=1, tight=not scroll,
                      scroll=ft.ScrollMode.AUTO if scroll else None),
            height=height if scroll else None,
            width=width, bgcolor=C.PANEL, border=ft.Border.all(1, C.LINE),
            border_radius=C.R_LARGE, padding=ft.Padding.all(8),
            shadow=ft.BoxShadow(blur_radius=48, offset=ft.Offset(0, 16),
                                color=C.SHADOW))

    def _row(self, row, indent: bool = False):
        color = C.ERR_TEXT if row["danger"] else C.TEXT
        icon_color = C.ERR_TEXT if row["danger"] else C.MUTED
        if row["disabled"]:
            color = icon_color = C.FAINT
        controls = []
        if row["icon"]:
            controls.append(ft.Icon(as_icon(row["icon"]), size=16, color=icon_color))
        elif indent:
            controls.append(ft.Container(width=16))
        controls.append(T(row["label"], size=C.FS_BODY, color=color, expand=True,
                          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
        if row["hint"]:
            controls.append(T(row["hint"], size=C.FS_CAPTION, color=C.MUTED_2,
                              font_family="monospace" if len(row["hint"]) <= 5 else None))
        if row["submenu"]:
            controls.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=C.FAINT))

        container = ft.Container(
            ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=8, horizontal=12), border_radius=C.R,
            height=ROW_H,
            on_click=None if row["disabled"] else (lambda e, r=row: self._fire(r)))
        if not row["disabled"]:
            def on_hover(e, c=container):
                c.bgcolor = C.RAISED if Wg.entered(e) else None
                Wg.safe_update(c)
            container.on_hover = on_hover
        return container

    def _fire(self, row):
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
    return ft.Container(ft.Row([ui.icon_slot(app, 32, 8, glyph=16),
                                ft.Column(lines, spacing=2, tight=True, expand=True)],
                               spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.Padding.only(left=12, top=8, right=12, bottom=8),
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
