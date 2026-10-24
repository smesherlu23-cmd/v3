"""Палитра поиска: строка в шапке, выдача, Enter и стрелки."""
from __future__ import annotations

import time

import flet as ft

from ..core import queries
from . import menus, screens
from . import widgets as Wg

# Сколько после нажатия клавиши не верить «наведению» мыши: строки палитры
# перестраиваются под неподвижным курсором, Flutter честно сообщает, что
# курсор «вошёл» в новую строку, — и выделение уезжало с лучшего совпадения.
PALETTE_HOVER_GRACE = 0.6


class PaletteMixin:
    def _refresh_palette_only(self):
        if not self._visible:
            self._dirty = True
            return
        with self._refresh_lock:
            self._snapshot = self.store.state()
            try:
                self._render_palette()
                self._render_bulk_bar()
                self.chrome.sync_search_box()
                self._render_popover()
            finally:
                self._snapshot = None
            self.page.update()

    def _palette_rows(self):
        state = self.state()
        apps = state["apps"]
        cats = sorted(state["categories"], key=lambda c: c.get("order", 0))
        sets = sorted(state["sets"], key=lambda r: r.get("order", 0))
        rows = [dict(r, kind="app") for r in
                queries.search_rows(apps, self.view.query, self.running, cats)]
        for entry in queries.set_rows(sets, apps, self.view.query):
            rows.append({"kind": "set", "set": entry["set"], "members": entry["members"]})
        for index, row in enumerate(rows):
            row["index"] = index
        return rows

    def palette_current(self, rows=None):
        rows = self._palette_rows() if rows is None else rows
        if not rows:
            return None
        if self.view.palette_focus == "actions":
            return rows[min(self.view.palette_result, len(rows) - 1)]
        return rows[min(self.view.palette_index, len(rows) - 1)]

    def _palette_app(self, rows=None):
        rows = self._palette_rows() if rows is None else rows
        current = self.palette_current(rows)
        if current is not None and current["kind"] == "app":
            return current["app"]
        # У набора своих действий нет: «Открыть папку» первой попавшейся
        # программы под строкой набора только путало.
        return None

    def _render_palette(self):
        if not self.view.palette_open:
            self.palette_layer.visible = False
            self.palette_card.content = None
            self.palette_card.opacity = 0
            self.palette_card.scale = 0.97
            return
        rows = self._palette_rows()
        self.palette_card.content = screens.build_palette(self, rows)
        if not self.palette_layer.visible:
            # Палитра раскрывается из-под строки поиска: чуть меньше и
            # прозрачная, кадр спустя — на месте, с лёгкой пружиной.
            self.palette_layer.visible = True
            Wg.enter(self.palette_card, {"opacity": 0, "scale": 0.97},
                     {"opacity": 1, "scale": 1.0})
        else:
            self.palette_card.opacity = 1
            self.palette_card.scale = 1.0

    def _focus(self, field):
        if Wg.attached(field):
            self.run_async(field.focus)

    def refocus_search(self):
        """Вернуть курсор в поиск — в конец запроса.

        Вернувшийся фокус выделяет весь текст поля, и следующая буква
        заменила бы запрос целиком («tel» + «e» давало «e»).
        """
        field = self.search_field
        # По одному Tab курсор возвращают и палитра, и поле, перехватившее
        # фокус. Второй focus() приходил уже после того, как курсор встал в
        # конец, и снова выделял весь текст.
        if not Wg.attached(field) or getattr(self, "_refocusing", False):
            return
        self._refocusing = True

        async def back():
            try:
                await field.focus()
                end = len(field.value or "")
                field.selection = ft.TextSelection(base_offset=end, extent_offset=end)
                field.update()
            finally:
                self._refocusing = False
        self.run_async(back)

    def _focus_search(self):
        # Сначала фокус, потом палитра: буквы, набранные сразу за Ctrl+K,
        # пока шла полная перерисовка окна, никуда не попадали — первая
        # буква запроса пропадала (это поймал scripts/ui_check.py).
        self.view.open_palette()
        self._focus(self.search_field)
        self._refresh_palette_only()

    def toggle_search(self):
        if self.view.palette_open:
            self._close_palette()
            return False
        self._focus_search()
        return True

    def clear_search(self):
        self.search_field.value = ""

    def _open_palette(self):
        if self.view.palette_open:
            return
        self.view.open_palette()
        self._refresh_palette_only()

    def _close_palette(self):
        self.view.close_palette()
        self.search_field.value = ""
        self.refresh()

    def note_palette_keys(self):
        self._palette_keyed_at = time.monotonic()

    def sync_query(self):
        """Запрос из поля, а не из последнего обработанного on_change.

        Enter сразу после последней буквы мог обработаться раньше её
        on_change и запустить лучшее совпадение для запроса без этой буквы.
        Значение поля Flet обновляет до того, как раздаёт события, — оно
        всегда свежее.
        """
        value = self.search_field.value or ""
        if value != self.view.query:
            self.view.set_query(value)

    def _on_search(self, e):
        self.note_palette_keys()
        self.view.set_query(e.control.value)
        if not self.view.palette_open:
            self.view.open_palette()
        self._refresh_palette_only()

    def run_palette_action(self, key: str):
        app = self._palette_app()
        if app is None:
            return
        if key == "folder":
            self._show_in_folder(app["id"])
        elif key == "admin":
            self._launch(app["id"], as_admin=True, from_palette=True)
        elif key == "set":
            self.view.close_palette()
            self.search_field.value = ""
            self.refresh()
            self.menu.show(self._window_width() / 2, 200.0, self.context_menus.set_submenu([app["id"]]),
                           header=menus.text_header("Добавить в набор…"))

    def palette_click(self, row):
        if row["kind"] == "set":
            self.set_ops.launch_set(row["set"]["id"], from_palette=True)
        else:
            self._launch(row["app"]["id"], from_palette=True)

    def palette_hover(self, index: int, e):
        if time.monotonic() - self._palette_keyed_at < PALETTE_HOVER_GRACE:
            return
        if Wg.entered(e) and (self.view.palette_index != index
                                 or self.view.palette_focus != "results"):
            self.view.palette_index = index
            self.view.palette_focus = "results"
            self._refresh_palette_only()
