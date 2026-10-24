from __future__ import annotations

import flet as ft

from ..core import queries
from ..infra import log
from . import colors as C
from . import widgets as Wg
from .format import T, as_icon

HEADER_SIDES_W = 320


class Chrome:
    def __init__(self, ui):
        self.ui = ui

    def sync_search_box(self):
        active = self.ui.view.palette_open
        room = self.ui._window_width() - HEADER_SIDES_W
        box, field = self.ui.search_box, self.ui.search_field
        box.width = max(C.SEARCH_MIN_W, min(C.SEARCH_W, room))
        box.bgcolor = C.CARD
        box.border = ft.Border.all(1, C.BORDER if active else C.LINE)
        # Поле живёт всё время работы окна — цвета темы ему переставляются
        # здесь, и только когда тема сменилась: иначе каждая перерисовка
        # слала бы клиенту новый стиль подсказки.
        if field.color != C.TEXT or getattr(field.hint_style, "color", None) != C.MUTED_2:
            field.color = C.TEXT
            field.cursor_color = C.TEXT
            field.hint_style = ft.TextStyle(color=C.MUTED_2, size=C.FS_BODY)
        self.ui.search_icon.color = C.TEXT_2 if active else C.MUTED_2
        if active:
            tail = [ft.Container(ft.Icon(ft.Icons.CLOSE, size=16, color=C.MUTED),
                                 tooltip="Закрыть поиск",
                                 on_click=lambda e: self.ui._close_palette())]
            self.ui.search_tail.content = ft.Row(tail, spacing=8, tight=True,
                                                 vertical_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            self.ui.search_tail.content = None

    def build_header(self):
        logo = ft.WindowDragArea(
            ft.Container(T("Centurio", size=C.FS_BODY, weight=ft.FontWeight.BOLD, color=C.TEXT),
                         width=150, padding=ft.Padding.only(left=16),
                         alignment=ft.Alignment.CENTER_LEFT))
        centre = ft.Container(
            ft.Row([ft.WindowDragArea(ft.Container(height=36), expand=True),
                    self.ui.search_box,
                    ft.WindowDragArea(ft.Container(height=36), expand=True)],
                   spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True)
        buttons = ft.Container(
            ft.Row([Wg.win_btn(ft.Icons.REMOVE, "Свернуть", self.ui._minimize),
                    Wg.win_btn(ft.Icons.CROP_SQUARE, "Развернуть", self.ui._toggle_maximize),
                    Wg.win_btn(ft.Icons.CLOSE, "Закрыть", self.ui._close, danger=True)],
                   spacing=2, alignment=ft.MainAxisAlignment.END),
            width=150, alignment=ft.Alignment.CENTER_RIGHT)
        return ft.Container(
            ft.Row([logo, centre, buttons], spacing=16,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=C.HEADER_H, bgcolor=C.BG,
            border=ft.Border.only(bottom=ft.BorderSide(1, C.LINE)),
            padding=ft.Padding.only(right=8),
        )

    def _rail_item(self, glyph, active, on_click, tooltip, keep_color=False,
                   on_drop_app=None, on_drop_category=None, on_context=None,
                   badge=None, marker=True, label=None):
        """Кнопка полосы слева.

        Метка выбора (полоска акцента) — только у того, что показано справа:
        раздела или экрана. Кнопка «панель» показывает нажатое состояние без
        метки, иначе в полосе было две метки «выбрано» сразу. Категория своего
        цвета не теряет: выбранная — на подложке, а не серая.
        """
        metrics = self.ui.rail()
        btn = metrics["btn"]

        round_r, square_r = btn / 2, btn / 3
        inner = ft.Container(
            glyph, width=btn, height=btn,
            border_radius=square_r if active else round_r,
            bgcolor=C.RAISED if active else None,
            alignment=ft.Alignment.CENTER, tooltip=None if label else tooltip,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            animate=ft.Animation(C.ANIM_BAR, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(C.ANIM_HOVER, ft.AnimationCurve.EASE_OUT),
        )

        def on_hover(e):
            if active:
                return
            highlight = Wg.entered(e)
            inner.bgcolor = C.RAISED if highlight else None
            inner.border_radius = square_r if highlight else round_r
            inner.scale = C.HOVER_SCALE if highlight else 1.0
            if not keep_color and isinstance(inner.content, ft.Icon):
                inner.content.color = C.TEXT if highlight else C.MUTED
            Wg.safe_update(inner)
        inner.on_hover = on_hover

        button = inner
        if badge is not None:
            button = ft.Stack([inner, ft.Container(badge, right=-3, top=-3)],
                              width=btn + 6, height=btn + 6)
        if label:
            button = ft.Column([button,
                                T(label, size=C.FS_CAPTION, max_lines=1,
                                  overflow=ft.TextOverflow.ELLIPSIS,
                                  text_align=ft.TextAlign.CENTER,
                                  width=metrics["rail"] - 12,
                                  color=C.TEXT if active else C.MUTED_2)],
                               spacing=4, tight=True,
                               horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        tapper = ft.GestureDetector(
            button, mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=lambda e: on_click(),
            on_secondary_tap_down=(lambda e: on_context(e)) if on_context else None)

        content = tapper
        if on_drop_app is not None or on_drop_category is not None:
            def _accept(e):
                payload = Wg.dragged_data(e)
                inner.border = None
                Wg.safe_update(inner)

                if isinstance(payload, dict) and payload.get("category_id"):
                    if on_drop_category:
                        on_drop_category(payload["category_id"])
                elif on_drop_app is not None:
                    if isinstance(payload, dict) and payload.get("ids"):
                        on_drop_app(payload["ids"])
                    elif payload:
                        on_drop_app([payload])

            def _will(e):
                inner.border = ft.Border.all(2, self.ui._accent())
                Wg.safe_update(inner)

            def _leave(e):
                inner.border = None
                Wg.safe_update(inner)
            content = ft.DragTarget(group="apps", content=tapper,
                                    on_accept=_accept, on_will_accept=_will, on_leave=_leave)

        bar = ft.Container(width=3, height=round(btn * 0.62),
                           border_radius=ft.BorderRadius.only(top_right=3, bottom_right=3),
                           bgcolor=self.ui._accent()) if active and marker \
            else ft.Container(width=3)
        return ft.Row([bar, ft.Container(content, expand=True, alignment=ft.Alignment.CENTER)],
                      spacing=0)

    def _inbox_badge(self, count: int):
        accent = self.ui._accent()
        return ft.Container(
            T(str(count if count < 100 else 99), size=C.FS_CAPTION, weight=ft.FontWeight.BOLD,
              color=C.on_color(accent), font_family="monospace"),
            height=18, border_radius=9, bgcolor=accent,
            padding=ft.Padding.symmetric(horizontal=5), alignment=ft.Alignment.CENTER)

    def _on_rail_scroll(self, e: ft.OnScrollEvent):
        self.ui._rail_scroll = e.pixels or 0.0

    def build_rail(self):
        self.ui._rail_scroll = 0.0
        on_grid = self.ui.view.screen == "grid" and not self.ui.view.active_set
        all_active = self.ui.is_all_view() and on_grid
        waiting = len(self.ui.inbox())
        metrics = self.ui.rail()
        btn, glyph, gap = metrics["btn"], metrics["glyph"], metrics["gap"]
        labels = metrics["labels"]

        def icon(name, size, active):
            return ft.Icon(as_icon(name), size=size, color=C.TEXT if active else C.MUTED)

        top = [
            self._rail_item(icon(ft.Icons.GRID_VIEW, glyph, all_active), all_active,
                            lambda: self.ui._set_filter("all"), "Все программы",
                            label="Все" if labels else None),
            # Кнопка панели — переключатель, а не раздел: включённая она лишь
            # ярче, без подложки и метки, чтобы «выбрано» в полосе было одно.
            self._rail_item(icon(ft.Icons.VIEW_SIDEBAR, glyph - 1, self.ui.view.sidebar_open),
                            False, lambda: self.ui._toggle_sidebar(),
                            "Скрыть панель" if self.ui.view.sidebar_open else "Показать панель",
                            keep_color=self.ui.view.sidebar_open,
                            label="Панель" if labels else None),
            ft.Container(width=round(btn * 0.72), height=1, bgcolor=C.LINE,
                         margin=ft.Margin.symmetric(vertical=4)),
        ]

        cats = []
        for cat in self.ui.categories():
            active = self.ui.view.filter == f"category:{cat['id']}" and on_grid
            item = self._rail_item(
                Wg.cat_glyph(cat, size=glyph, fill=btn), active,
                lambda cid=cat["id"]: self.ui._set_filter(f"category:{cid}"), cat["name"],
                keep_color=True,
                on_drop_app=lambda ids, cid=cat["id"]: self.ui._move_apps_to_category(ids, cid),
                on_drop_category=lambda dragged, cid=cat["id"]: self.ui._reorder_category(
                    dragged, cid),
                on_context=lambda e, c=cat: self.ui.context_menus.category_menu(c, e),
                label=cat["name"] if labels else None)
            cats.append(ft.Draggable(group="apps", content=item,
                                     data={"category_id": cat["id"]}))
        add = ft.Container(ft.Icon(ft.Icons.ADD, size=glyph - 3, color=C.FAINT),
                           width=btn, height=btn, border_radius=btn / 2,
                           alignment=ft.Alignment.CENTER,
                           border=ft.Border.all(1, C.BORDER),
                           on_click=lambda e: self.ui._add_category(),
                           tooltip="Добавить категорию")
        Wg.hoverable(add, None, C.RAISED)
        cats.append(ft.Row([ft.Container(width=3),
                            ft.Container(add, expand=True, alignment=ft.Alignment.CENTER)],
                           spacing=0))
        middle = ft.Container(
            ft.Column(cats, spacing=gap, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                      scroll=ft.ScrollMode.AUTO, on_scroll=self._on_rail_scroll, expand=True),
            expand=True)

        triage_active = self.ui.view.screen == "triage"
        bottom = [
            self._rail_item(
                icon(ft.Icons.INBOX, glyph - 1, triage_active), triage_active,
                lambda: self.ui.open_triage(),
                f"Новые программы · {waiting}" if waiting else "Новые программы",
                badge=self._inbox_badge(waiting) if waiting else None,
                label="Новые" if labels else None),
            self._rail_item(icon(ft.Icons.SETTINGS, glyph - 1, False), False,
                            lambda: self.ui._open_settings(), "Настройки",
                            label="Настройки" if labels else None),
        ]

        return ft.Container(
            ft.Column(top + [middle] + bottom, spacing=gap,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            padding=ft.Padding.only(top=16, bottom=12), bgcolor=C.BG,
            border=ft.Border.only(right=ft.BorderSide(1, C.LINE)), expand=True,
        )

    def _sidebar_filter(self, icon_ctl, label, key):
        active = self.ui.view.filter == key and self.ui.view.screen == "grid" \
            and not self.ui.view.active_set
        row = ft.Container(
            ft.Row([
                ft.Container(icon_ctl, width=16, height=16, alignment=ft.Alignment.CENTER),
                T(label, size=C.FS_BODY, color=C.TEXT if active else C.TEXT_2,
                  weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400, expand=True),
            ], spacing=12),
            padding=ft.Padding.symmetric(vertical=8, horizontal=12), border_radius=C.R,
            bgcolor=C.RAISED if active else None,
            animate=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
            on_click=lambda e: self.ui._set_filter(key),
        )
        if not active:
            Wg.hoverable(row, None, C.CARD)
        return row

    def build_sidebar(self):
        apps = self.ui.apps()
        buried = sum(1 for a in apps if a.get("hidden"))

        # Заголовок панели — на шаг тише разделов в сетке: он подписывает
        # раздел, а не спорит с «Работой» и «Общением» за внимание.
        top = [ft.Container(T(self.ui._current_title(), size=C.FS_HEADING,
                              weight=ft.FontWeight.W_600, color=C.TEXT, max_lines=1,
                              overflow=ft.TextOverflow.ELLIPSIS),
                            padding=ft.Padding.symmetric(horizontal=12))]
        top += [
            Wg.divider(8),
            self._sidebar_filter(ft.Icon(ft.Icons.STAR, size=16, color=C.STAR),
                                 "Избранное", "favorites"),
            self._sidebar_filter(ft.Icon(ft.Icons.SCHEDULE, size=16, color=C.MUTED),
                                 "Недавние", "recent"),
            self._sidebar_filter(Wg.dot(8), "Запущено", "running"),
        ]
        if buried:
            top.append(self._sidebar_filter(
                ft.Icon(ft.Icons.VISIBILITY_OFF, size=16, color=C.MUTED),
                "Скрытые", "hidden"))

        top += [Wg.divider(8),
                ft.Container(ft.Row([Wg.caps("НАБОРЫ"), ft.Container(expand=True),
                                     Wg.icon_btn(ft.Icons.ADD, "Собрать набор из выбранного",
                                                 self.ui.set_ops.new_set, size=24, glyph=16)],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                             padding=ft.Padding.only(left=12, right=8, bottom=4))]

        sets_block = []
        if self.ui.view.select_mode:
            sets_block.append(self._set_drop_hint())
        records = self.ui.sets()
        for rec in records:
            sets_block.append(self._sidebar_set_row(rec))
        if not records and not self.ui.view.select_mode:
            sets_block.append(ft.Container(
                T("Выберите плитки и нажмите «плюс»", size=C.FS_SMALL, color=C.MUTED_2),
                padding=ft.Padding.symmetric(horizontal=12)))
        return ft.Container(
            ft.Column([ft.Column(top, spacing=4, tight=True),
                       ft.Column(sets_block, spacing=4, expand=True,
                                 scroll=ft.ScrollMode.AUTO),
                       self._sidebar_footer()],
                      spacing=4, expand=True),
            padding=ft.Padding.only(left=12, top=24, right=12, bottom=12), bgcolor=C.BG,
            border=ft.Border.only(right=ft.BorderSide(1, C.LINE)), expand=True,
        )

    def _sidebar_set_row(self, rec):
        active = self.ui.view.active_set == rec["id"]
        row = ft.Container(
            ft.Row([self.ui.set_mosaic(rec, 22, 6),
                    T(rec["name"], size=C.FS_BODY, weight=ft.FontWeight.W_500,
                      color=C.TEXT if active else C.TEXT_2, max_lines=1,
                      overflow=ft.TextOverflow.ELLIPSIS, expand=True)],
                   spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=8), border_radius=C.R,
            bgcolor=C.RAISED if active else None,
            border=ft.Border.all(1, C.TRANSPARENT),
            on_click=lambda e, sid=rec["id"]: self.ui._open_set(sid))
        if not active:
            Wg.hoverable(row, None, C.CARD)
        rest = C.TRANSPARENT
        return ft.DragTarget(
            group="apps", content=ft.GestureDetector(
                row, on_secondary_tap_down=lambda e, r=rec: self.ui.context_menus.set_menu(r, e)),
            on_accept=lambda e, sid=rec["id"]: self._drop_on_set(sid, e, row, rest),
            on_will_accept=lambda e, r=row: self.highlight_drop(r, True, rest),
            on_leave=lambda e, r=row: self.highlight_drop(r, False, rest))

    def _set_drop_hint(self):
        row = ft.Container(
            ft.Row([ft.Container(ft.Icon(ft.Icons.LAYERS, size=16, color=C.MUTED),
                                 width=22, height=22, alignment=ft.Alignment.CENTER),
                    T("Перетащите сюда", size=C.FS_BODY, color=C.MUTED, expand=True,
                      max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)],
                   spacing=10),
            padding=ft.Padding.symmetric(vertical=6, horizontal=8), border_radius=C.R,
            border=ft.Border.all(1, C.BORDER),
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

    def _sidebar_footer(self):
        # Номер версии здесь был набран цветом 1,8:1 — его не прочесть, а
        # версия и так есть в настройках. Остаётся только весть о новой.
        newer = self.ui.updates.available()
        if not newer:
            return ft.Container()
        notice = ft.Container(
            ft.Row([ft.Icon(ft.Icons.DOWNLOAD, size=16, color=C.TEXT_2),
                    T(f"Вышла {newer}", size=C.FS_SMALL, color=C.TEXT_2)],
                   spacing=8, tight=True),
            tooltip="Скачать новую версию", padding=ft.Padding.symmetric(vertical=6, horizontal=8),
            border_radius=C.R,
            on_click=lambda e: self.ui.open_url(self.ui.updates.url()))
        return ft.Container(Wg.hoverable(notice, None, C.CARD),
                            border=ft.Border.only(top=ft.BorderSide(1, C.LINE)),
                            padding=ft.Padding.only(top=8))

    def build_toolbar(self):
        select = Wg.secondary_btn(
            "Выбрать",
            self.ui.toggle_select_mode,
            ft.Icons.CHECK_BOX if self.ui.view.select_mode
            else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            active=self.ui.view.select_mode, height=32)
        left = [select]
        if self.ui.view.select_mode:
            label = ("Выбрать всё" if self.ui.is_all_view()
                     else f"Выбрать всё в «{self.ui._current_title()}»")
            left.append(Wg.quiet_btn(label, self.ui._select_all_visible))
        sort_btn = ft.Container(
            ft.Row([T(queries.SORT_LABELS[self.ui.view.sort], size=C.FS_BODY, color=C.TEXT_2),
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=C.FAINT)],
                   spacing=8),
            height=32, padding=ft.Padding.symmetric(horizontal=12),
            border_radius=C.R,
            on_click=lambda e: self.ui.context_menus.sort_menu(e), alignment=ft.Alignment.CENTER,
            tooltip="Порядок плиток",
        )
        Wg.hoverable(sort_btn, None, C.RAISED)

        def view_btn(icon_name, m, tip):
            active = self.ui.view.mode == m
            return Wg.icon_btn(icon_name, tip, lambda: self.ui._set_mode(m), size=32,
                               active=active)
        view_toggle = ft.Row([view_btn(ft.Icons.GRID_VIEW, "grid", "Сетка"),
                              view_btn(ft.Icons.VIEW_LIST, "list", "Список")], spacing=4)
        # «Добавить» — второстепенная: после первой настройки ею почти не
        # пользуются, и самое яркое пятно в окне уводило глаз от плиток.
        right = Wg.secondary_btn("Добавить", self.ui.open_add, ft.Icons.ADD, height=32)
        return ft.Container(
            ft.Row(left + [sort_btn, view_toggle, ft.Container(expand=True), right],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=24, top=16, right=24, bottom=8),
        )
