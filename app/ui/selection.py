"""Выбор плиток: стрелки, щелчки, режим выбора, панель справа."""
from __future__ import annotations

import flet as ft

from ..core import queries
from . import screens


class SelectionMixin:
    def _render_bulk_bar(self):
        showing = bool(self.view.select_mode and self.view.sel)
        self.toast.lift(showing)
        if not showing:
            self.bulk_layer.visible = False
            self.bulk_card.content = None
            self.bulk_card.opacity = 0
            self.bulk_card.offset = ft.Offset(0, 0.3)
            return
        self.bulk_card.content = screens.build_bulk_bar(self)
        self.bulk_card.opacity = 1
        self.bulk_card.offset = ft.Offset(0, 0)
        self.bulk_layer.visible = True

    def _flat_apps(self, sections=None):
        """Плитки в том порядке, в каком они на экране, — без свёрнутых секций.

        Стрелки ходили и по плиткам свёрнутых категорий: выделение пропадало
        из виду, а Enter запускал невидимую программу. В режиме выбора свёрнутые
        секции раскрыты, и их плитки снова участвуют.
        """
        sections = self.sections() if sections is None else sections
        if not self.view.select_mode:
            sections = [sec for sec in sections
                        if not (sec.get("cid") and sec["cid"] in self.view.collapsed)]
        return queries.flatten_sections(sections)

    def _selected_id(self, sections=None):
        if self.view.inspector:
            return self.view.inspector
        flat = self._flat_apps(sections)
        if 0 <= self.view.selected < len(flat):
            return flat[self.view.selected]["id"]
        return None

    def move_selection(self, delta):
        with self._refresh_lock:
            flat = self._flat_apps()
            if not flat:
                self.view.selected = -1
                return
            self.view.move_selection(delta, len(flat))
            self.refresh()

    def activate_selected(self):
        with self._refresh_lock:
            flat = self._flat_apps()
            if not flat:
                return
            idx = self.view.selected if 0 <= self.view.selected < len(flat) else 0
        self._launch(flat[idx]["id"])

    def toggle_select_mode(self):
        if self.view.select_mode:
            self.view.leave_select_mode()
        else:
            self.view.enter_select_mode()
        self.refresh()

    def _select_all_visible(self):
        flat = self._flat_apps()
        if not self.view.select_mode:
            self.view.enter_select_mode()
        self.view.select_many([a["id"] for a in flat])
        self.refresh()

    def _tile_tap(self, app_id, ids, e=None):
        ctrl = bool(getattr(e, "ctrl", False)) if e is not None else False
        shift = bool(getattr(e, "shift", False)) if e is not None else False
        if not self.view.select_mode and not (ctrl or shift):
            self._launch(app_id)
            return
        if not self.view.select_mode:
            self.view.enter_select_mode()
        if shift:
            self.view.select_range(ids, app_id)
        else:
            self.view.toggle_selection(app_id)
        self.refresh()

    def _toggle_pick(self, app_id):
        self.view.toggle_selection(app_id)
        self.refresh()

    def _range_to(self, app_id):
        self.view.select_range([a["id"] for a in self._flat_apps()], app_id)
        self.refresh()

    def _select_tile(self, app_id):
        self.view.select_one(app_id)
        app = next((a for a in self.apps() if a["id"] == app_id), None)
        self.view.adv = bool(app and (app.get("args") or app.get("run_as_admin")
                                      or app.get("working_dir")))
        self.refresh()

    def _drag_ids(self, app_id):
        return list(self.view.sel) if app_id in self.view.sel else [app_id]

    def _close_inspector(self):
        self.view.close_inspector()
        self.refresh()

    def _toggle_adv(self):
        self.view.adv = not self.view.adv
        self.refresh()
