from __future__ import annotations

import flet as ft

from ..core import queries
from ..infra import log
from . import colors as C
from . import widgets as Wg
from .format import T, as_icon

SIDEBAR_PAD = 10
SECTION_H = 30
ROW_GAP = 2
# Заголовок окна — ряд из частей заданной ширины: кнопки окна (три по 40 и
# промежутки) с отступами, панель инструментов сетки, название раздела. Что
# остаётся — строке поиска. Название получает место по оценке с запасом и
# обрезается, если оценка мала, — так ничего не наезжает: раньше в узком окне
# поиск ложился на название и уходил под переключатель вида.
WINDOW_BTNS_W = 3 * 40 + 2 * 2 + 8 + 8
TOOLBAR_W = 204
TITLE_PAD = 8
TITLE_MIN_W = 96
SEARCH_GAP = 24


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Ширина строки с запасом: средняя буква Inter — около 0,6 кегля."""
    return len(text) * size * (0.66 if bold else 0.6)


class Chrome:
    """Заголовок окна и боковая панель.

    Как в macOS: панель инструментов живёт в заголовке окна, а слева одна
    боковая панель — библиотека, категории, наборы. В узком окне (или по
    кнопке) она сворачивается в полосу значков, плавно.
    """

    def __init__(self, ui):
        self.ui = ui
        # Где по вертикали стоит строка категории — к ней прикладывается
        # поповер «Изменить».
        self.row_tops: dict[str, float] = {}
        self.sidebar_scroll = 0.0
        self.sidebar_zone = ft.Container(animate=Wg.anim(C.ANIM_BAR),
                                         clip_behavior=ft.ClipBehavior.HARD_EDGE)
        self.title_holder = ft.Container(padding=ft.Padding.only(left=TITLE_PAD))
        # Сколько места в заголовке осталось строке поиска — считает sync_header.
        self.search_room = float(C.SEARCH_W + SEARCH_GAP)

    # --- заголовок окна -------------------------------------------------

    def sync_search_box(self):
        active = self.ui.view.palette_open
        box, field = self.ui.search_box, self.ui.search_field
        box.width = max(C.SEARCH_MIN_W, min(C.SEARCH_W, self.search_room - SEARCH_GAP))
        box.bgcolor = C.CARD
        # Фокус — кольцо цвета акцента, как у полей macOS.
        box.border = ft.Border.all(2 if active else 1,
                                   C.with_alpha(self.ui._accent(), 0.7) if active
                                   else C.TRANSPARENT)
        # Поле живёт всё время работы окна — цвета темы ему переставляются
        # здесь, и только когда тема сменилась: иначе каждая перерисовка
        # слала бы клиенту новый стиль подсказки.
        if field.color != C.TEXT or getattr(field.hint_style, "color", None) != C.MUTED_2:
            field.color = C.TEXT
            field.cursor_color = C.TEXT
            field.hint_style = ft.TextStyle(color=C.MUTED_2, size=C.FS_BODY)
        self.ui.search_icon.color = C.TEXT_2 if active else C.MUTED_2
        if active:
            tail = [ft.Container(ft.Icon(ft.Icons.CANCEL_ROUNDED, size=16, color=C.FAINT),
                                 tooltip="Закрыть поиск",
                                 on_click=lambda e: self.ui._close_palette())]
            self.ui.search_tail.content = ft.Row(tail, spacing=8, tight=True,
                                                 vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            self.ui.search_tail.content = None

    def build_header(self):
        centre = ft.Container(
            ft.Row([ft.WindowDragArea(ft.Container(height=36), expand=True),
                    self.ui.search_box,
                    ft.WindowDragArea(ft.Container(height=36), expand=True)],
                   spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True)
        buttons = ft.Row([Wg.win_btn(ft.Icons.REMOVE_ROUNDED, "Свернуть", self.ui._minimize),
                          Wg.win_btn(ft.Icons.CROP_SQUARE_ROUNDED, "Развернуть",
                                     self.ui._toggle_maximize),
                          Wg.win_btn(ft.Icons.CLOSE_ROUNDED, "Закрыть", self.ui._close,
                                     danger=True)],
                         spacing=2, tight=True)
        # Боковая панель тянется до верха окна, как в Finder: над ней нет
        # линии заголовка, и кнопка панели стоит на её же фоне.
        main = ft.Container(
            ft.Row([ft.WindowDragArea(self.title_holder),
                    centre, self.ui.toolbar_holder, ft.Container(width=8), buttons],
                   spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=C.HEADER_H, bgcolor=C.BG, expand=True,
            border=ft.Border.only(bottom=ft.BorderSide(1, C.LINE)),
            padding=ft.Padding.only(right=8))
        return ft.Row([self.sidebar_zone, main], spacing=0, height=C.HEADER_H,
                      vertical_alignment=ft.CrossAxisAlignment.START)

    def sync_header(self):
        """Части заголовка, которые меняются: ширина над панелью, название, кнопки."""
        width = self.ui._sidebar_width()
        expanded = self.ui._sidebar_expanded()
        # Над настройками — их собственная колонка разделов, без кнопки панели.
        settings = self.ui.view.screen == "settings"
        self.sidebar_zone.width = C.SETTINGS_NAV_W if settings else max(width,
                                                                         C.SIDEBAR_RAIL_W)
        self.sidebar_zone.bgcolor = C.PANEL
        self.sidebar_zone.border = ft.Border.only(right=ft.BorderSide(1, C.LINE))
        toggle = Wg.icon_btn(ft.Icons.VIEW_SIDEBAR_OUTLINED,
                             "Свернуть панель" if expanded else "Развернуть панель",
                             self.ui._toggle_sidebar, size=30, glyph=18)
        self.sidebar_zone.content = ft.WindowDragArea(ft.Container(
            None if settings else
            ft.Row([toggle], alignment=ft.MainAxisAlignment.START
                   if width > C.SIDEBAR_RAIL_W else ft.MainAxisAlignment.CENTER),
            padding=ft.Padding.only(left=14 if width > C.SIDEBAR_RAIL_W else 0),
            height=C.HEADER_H, alignment=ft.Alignment.CENTER_LEFT))
        on_grid = self.ui.view.screen == "grid" and not self.ui.view.active_set
        # Всё, что в заголовке не поиск: колонка над панелью, кнопки окна,
        # инструменты сетки.
        room = (self.ui._window_width() - self.sidebar_zone.width - WINDOW_BTNS_W
                - (TOOLBAR_W if on_grid else 0) - TITLE_PAD)
        if on_grid:
            title = self.ui._current_title()
            # Число — все программы раздела, и в свёрнутых группах тоже: как
            # рядом с ним в боковой панели.
            count = str(sum(len(sec["apps"]) for sec in self.ui.sections()))
            want = text_width(title, C.FS_TITLE, bold=True) + 8 + text_width(count, C.FS_BODY)
            # Длинное имя категории уступает место поиску и обрезается.
            width = max(TITLE_MIN_W, min(want + 4, room - C.SEARCH_MIN_W - SEARCH_GAP))
            self.title_holder.width = width + TITLE_PAD
            self.title_holder.content = ft.Row(
                [T(title, size=C.FS_TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT,
                   max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                   expand_loose=True),
                 T(count, size=C.FS_BODY, color=C.MUTED_2)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            room -= width
        else:
            self.title_holder.width = None
            self.title_holder.content = None
        self.search_room = room
        self.ui.toolbar_holder.width = TOOLBAR_W if on_grid else None
        self.ui.toolbar_holder.alignment = ft.Alignment.CENTER_RIGHT
        self.ui.toolbar_holder.content = self.build_toolbar() if on_grid else None
        self.ui.toolbar_holder.visible = on_grid

    def _tool(self, icon, tooltip, on_press, active=False):
        """Кнопка панели инструментов; меню у неё открывается под ней."""
        box = ft.Container(
            ft.Icon(as_icon(icon), size=18, color=C.TEXT if active else C.MUTED),
            width=32, height=30, border_radius=C.R, alignment=ft.Alignment.CENTER,
            bgcolor=C.RAISED if active else None, tooltip=tooltip,
            animate=Wg.anim(C.ANIM_FAST))
        if not active:
            Wg.hoverable(box, None, C.CARD)
        return ft.GestureDetector(box, mouse_cursor=ft.MouseCursor.CLICK,
                                  on_tap_down=lambda e: on_press(e))

    def build_toolbar(self):
        view = self.ui.view
        if view.select_mode:
            # Какой раздел — видно в названии слева; «Выбрать всё в «…»» с длинным
            # именем категории не помещалось в заголовок.
            items = [Wg.quiet_btn("Выбрать всё", self.ui._select_all_visible),
                     Wg.primary_btn("Готово", self.ui.toggle_select_mode, self.ui._accent(),
                                    height=28)]
        else:
            items = [
                Wg.segmented([(None, "grid", ft.Icons.GRID_VIEW_ROUNDED, "Значки"),
                              (None, "list", ft.Icons.VIEW_LIST_ROUNDED, "Список")],
                             view.mode, self.ui._set_mode),
                self._tool(ft.Icons.SORT_ROUNDED,
                           f"Порядок: {queries.SORT_LABELS[view.sort].lower()}",
                           self.ui.context_menus.sort_menu),
                self._tool(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, "Выбрать несколько",
                           lambda e: self.ui.toggle_select_mode()),
                self._tool(ft.Icons.ADD_ROUNDED, "Найти и добавить программы",
                           lambda e: self.ui.open_add()),
            ]
        return ft.Row(items, spacing=6, tight=True,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # --- боковая панель -------------------------------------------------

    def _on_sidebar_scroll(self, e: ft.OnScrollEvent):
        self.sidebar_scroll = e.pixels or 0.0

    def _row(self, icon_ctl, label, active, on_click, count=None, tooltip=None,
             on_context=None, badge=None):
        """Строка панели: значок, имя, справа счётчик. В узкой полосе — один значок."""
        expanded = self.ui._sidebar_expanded()
        if expanded:
            right = []
            if badge:
                right.append(self._badge(badge))
            elif count:
                right.append(T(str(count), size=C.FS_SMALL, color=C.MUTED_2))
            body = ft.Row([ft.Container(icon_ctl, width=20, alignment=ft.Alignment.CENTER),
                           T(label, size=C.FS_BODY, color=C.TEXT, max_lines=1,
                             overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                             weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400)]
                          + right, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            row = ft.Container(body, height=C.SIDEBAR_ROW_H,
                               padding=ft.Padding.symmetric(horizontal=8),
                               border_radius=C.R_SMALL, tooltip=tooltip)
        else:
            inner = icon_ctl
            if badge:
                inner = ft.Stack([ft.Container(icon_ctl, width=36, height=36,
                                               alignment=ft.Alignment.CENTER),
                                  ft.Container(self._badge(badge), right=-2, top=-2)],
                                 width=36, height=36)
            row = ft.Container(inner, width=40, height=36, border_radius=C.R,
                               alignment=ft.Alignment.CENTER, tooltip=tooltip or label)
        row.bgcolor = C.RAISED if active else None
        row.animate = Wg.anim(C.ANIM_FAST)
        if not active:
            Wg.hoverable(row, None, C.CARD)
        return ft.GestureDetector(
            row, mouse_cursor=ft.MouseCursor.CLICK, on_tap=lambda e: on_click(),
            on_secondary_tap_down=(lambda e: on_context(e)) if on_context else None)

    def _badge(self, count: int):
        accent = self.ui._accent()
        return ft.Container(
            T(str(count if count < 100 else 99), size=C.FS_CAPTION, weight=ft.FontWeight.BOLD,
              color=C.on_color(accent)),
            height=18, border_radius=9, bgcolor=accent,
            padding=ft.Padding.symmetric(horizontal=6), alignment=ft.Alignment.CENTER)

    def _section(self, label, on_add=None, add_tip=None):
        if not self.ui._sidebar_expanded():
            return ft.Container(height=1, bgcolor=C.LINE, width=28,
                                margin=ft.Margin.symmetric(vertical=8))
        row = [ft.Container(Wg.caps(label), expand=True)]
        if on_add:
            row.append(Wg.icon_btn(ft.Icons.ADD_ROUNDED, add_tip, on_add, size=22, glyph=16))
        return ft.Container(ft.Row(row, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            height=SECTION_H, padding=ft.Padding.only(left=8, right=2, top=8))

    def _icon(self, name, color=None, size=18):
        return ft.Icon(as_icon(name), size=size, color=color or self.ui._accent())

    def _filter_row(self, icon_ctl, label, key, count=None):
        view = self.ui.view
        active = view.filter == key and view.screen == "grid" and not view.active_set
        return self._row(icon_ctl, label, active, lambda: self.ui._set_filter(key),
                         count=count)

    def build_sidebar(self):
        apps = self.ui.apps()
        shown = queries.visible(apps)
        buried = sum(1 for a in apps if a.get("hidden"))
        running = sum(1 for a in shown if a["id"] in self.ui.running)
        favorites = sum(1 for a in shown if a.get("favorite"))
        expanded = self.ui._sidebar_expanded()
        self.row_tops = {}
        top = SIDEBAR_PAD

        items = [self._section("Библиотека")]
        top += SECTION_H if expanded else 17
        library = [
            self._filter_row(self._icon(ft.Icons.APPS_ROUNDED), "Все программы", "all",
                             len(shown)),
            self._filter_row(self._icon(ft.Icons.STAR_ROUNDED, C.STAR), "Избранное",
                             "favorites", favorites),
            self._filter_row(self._icon(ft.Icons.SCHEDULE_ROUNDED), "Недавние", "recent"),
            self._filter_row(Wg.dot(8), "Запущено", "running", running),
        ]
        if buried:
            library.append(self._filter_row(self._icon(ft.Icons.VISIBILITY_OFF_ROUNDED,
                                                       C.MUTED), "Скрытые", "hidden", buried))
        items += library
        row_h = (C.SIDEBAR_ROW_H if expanded else 36) + ROW_GAP
        top += len(library) * row_h

        items.append(self._section("Категории", self.ui._add_category, "Новая категория"))
        top += SECTION_H if expanded else 17
        counts: dict[str, int] = {}
        for a in shown:
            counts[a.get("category_id")] = counts.get(a.get("category_id"), 0) + 1
        for cat in self.ui.categories():
            self.row_tops[cat["id"]] = top
            items.append(self._category_row(cat, counts.get(cat["id"], 0)))
            top += row_h

        items.append(self._section("Наборы", self.ui.set_ops.new_set,
                                   "Собрать набор из выбранного"))
        if self.ui.view.select_mode:
            items.append(self._set_drop_hint())
        records = self.ui.sets()
        for rec in records:
            items.append(self._set_row(rec))
        if not records and not self.ui.view.select_mode and expanded:
            items.append(ft.Container(
                T("Выберите программы и нажмите «+»", size=C.FS_SMALL, color=C.MUTED_2),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4)))

        waiting = len(self.ui.inbox())
        view = self.ui.view
        footer = [
            self._row(self._icon(ft.Icons.INBOX_ROUNDED), "Новые программы",
                      view.screen == "triage", self.ui.open_triage, badge=waiting or None,
                      # Подсказка нужна полосе значков: в панели число и так видно.
                      tooltip=f"Новые программы · {waiting}"
                      if waiting and not self.ui._sidebar_expanded() else None),
            self._row(self._icon(ft.Icons.SETTINGS_ROUNDED, C.MUTED), "Настройки", False,
                      self.ui._open_settings),
        ]
        newer = self.ui.updates.available()
        if newer:
            footer.append(self._row(self._icon(ft.Icons.DOWNLOAD_ROUNDED, C.GREEN),
                                    f"Вышла {newer}", False,
                                    lambda: self.ui.open_url(self.ui.updates.url()),
                                    tooltip="Скачать новую версию"))
        align = (ft.CrossAxisAlignment.STRETCH if expanded
                 else ft.CrossAxisAlignment.CENTER)
        return ft.Container(
            ft.Column([
                ft.Column(items, spacing=ROW_GAP, expand=True, scroll=ft.ScrollMode.AUTO,
                          on_scroll=self._on_sidebar_scroll, horizontal_alignment=align),
                ft.Container(ft.Column(footer, spacing=ROW_GAP, horizontal_alignment=align),
                             border=ft.Border.only(top=ft.BorderSide(1, C.LINE)),
                             padding=ft.Padding.only(top=8)),
            ], spacing=8, expand=True, horizontal_alignment=align),
            padding=ft.Padding.only(left=SIDEBAR_PAD, top=SIDEBAR_PAD, right=SIDEBAR_PAD,
                                    bottom=SIDEBAR_PAD),
            bgcolor=C.PANEL, border=ft.Border.only(right=ft.BorderSide(1, C.LINE)),
            expand=True)

    def _category_row(self, cat, count):
        view = self.ui.view
        active = view.filter == f"category:{cat['id']}" and view.screen == "grid" \
            and not view.active_set
        glyph = Wg.cat_glyph(cat, size=18, fill=20)
        tapper = self._row(glyph, cat["name"], active,
                           lambda cid=cat["id"]: self.ui._set_filter(f"category:{cid}"),
                           count=count,
                           on_context=lambda e, c=cat: self.ui.context_menus.category_menu(c, e))
        row = tapper.content

        def _accept(e):
            payload = Wg.dragged_data(e)
            self.highlight_drop(row, False)
            if isinstance(payload, dict) and payload.get("category_id"):
                self.ui._reorder_category(payload["category_id"], cat["id"])
            elif isinstance(payload, dict) and payload.get("ids"):
                self.ui._move_apps_to_category(payload["ids"], cat["id"])
            elif payload:
                self.ui._move_apps_to_category([payload], cat["id"])

        target = ft.DragTarget(group="apps", content=tapper, on_accept=_accept,
                               on_will_accept=lambda e: self.highlight_drop(row, True),
                               on_leave=lambda e: self.highlight_drop(row, False))
        return ft.Draggable(group="apps", content=target, data={"category_id": cat["id"]})

    def _set_row(self, rec):
        active = self.ui.view.active_set == rec["id"]
        expanded = self.ui._sidebar_expanded()
        icon = self.ui.set_mosaic(rec, 20 if expanded else 24, 5)
        tapper = self._row(icon, rec["name"], active,
                           lambda sid=rec["id"]: self.ui._open_set(sid),
                           on_context=lambda e, r=rec: self.ui.context_menus.set_menu(r, e))
        row = tapper.content
        return ft.DragTarget(
            group="apps", content=tapper,
            on_accept=lambda e, sid=rec["id"]: self._drop_on_set(sid, e, row),
            on_will_accept=lambda e: self.highlight_drop(row, True),
            on_leave=lambda e: self.highlight_drop(row, False))

    def _set_drop_hint(self):
        expanded = self.ui._sidebar_expanded()
        content = (ft.Row([self._icon(ft.Icons.LAYERS_ROUNDED, C.MUTED),
                           T("Перетащите сюда", size=C.FS_BODY, color=C.MUTED, expand=True,
                             max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=8)
                   if expanded else self._icon(ft.Icons.LAYERS_ROUNDED, C.MUTED))
        row = ft.Container(content, height=C.SIDEBAR_ROW_H, border_radius=C.R_SMALL,
                           padding=ft.Padding.symmetric(horizontal=8),
                           border=ft.Border.all(1, C.BORDER),
                           tooltip="Перетащите выбранное — получится набор",
                           on_click=lambda e: self.ui.set_ops.new_set())
        return ft.DragTarget(
            group="apps", content=row,
            on_accept=lambda e, r=row: self._drop_new_set(e, r),
            on_will_accept=lambda e, r=row: self.highlight_drop(r, True, C.BORDER),
            on_leave=lambda e, r=row: self.highlight_drop(r, False, C.BORDER))

    def highlight_drop(self, row, on: bool, rest=None):
        row.border = (ft.Border.all(1, self.ui._accent()) if on
                      else (ft.Border.all(1, rest) if rest else None))
        try:
            row.update()
        except Exception:
            log.exception("сбой при обновлении интерфейса после перетаскивания")

    def drop_set_item(self, set_id, target_id, e, row, rest=None):
        self.highlight_drop(row, False, rest)
        moved = Wg.dragged_data(e)
        rec = self.ui.store.get_set(set_id)
        if not rec or not isinstance(moved, str) or moved == target_id:
            return
        current = [i["app_id"] for i in rec["items"]]
        if moved not in current or target_id not in current:
            return
        moving_down = current.index(target_id) > current.index(moved)
        order = [i for i in current if i != moved]
        order.insert(order.index(target_id) + (1 if moving_down else 0), moved)
        self.ui.store.reorder_set_items(set_id, order)
        self.ui.refresh()

    def _dropped_ids(self, e) -> list[str]:
        payload = Wg.dragged_data(e)
        if isinstance(payload, dict) and payload.get("ids"):
            return list(payload["ids"])
        return [payload] if payload else []

    def _drop_on_set(self, set_id, e, row, rest=None):
        self.highlight_drop(row, False, rest)
        ids = self._dropped_ids(e)
        if ids:
            self.ui.set_ops.add_to_set(set_id, ids)

    def _drop_new_set(self, e, row):
        self.highlight_drop(row, False, C.BORDER)
        ids = self._dropped_ids(e)
        if ids:
            self.ui.set_ops.make_set(ids)
