"""Запуск, переключение на открытое окно, «где лежит»."""
from __future__ import annotations

import time

import flet as ft

from ..core.text import plu_windows
from ..infra import log
from ..platform import windows as W
from . import colors as C

WINDOW_TTL = 2.0


class LaunchMixin:
    def _windows_snapshot(self) -> list[dict]:
        if not W.available():
            return []
        now = time.monotonic()
        with self._win_lock:
            if now - self._win_at <= WINDOW_TTL:
                return self._win_snapshot
        snapshot = W.list_windows()
        with self._win_lock:
            self._win_snapshot = snapshot
            self._win_at = time.monotonic()
        return snapshot

    def window_count(self, app) -> int:
        if app["id"] not in self.running:
            return 0
        return W.count_for(W.exe_names_for(app), self._windows_snapshot())

    def _app_windows(self, app) -> list[dict]:
        return W.windows_for(W.exe_names_for(app), self._windows_snapshot())

    def running_note(self, app) -> str:
        count = self.window_count(app)
        return f"открыто · {count} {plu_windows(count)}" if count > 1 else "открыто"

    def set_running(self, ids):
        self.running = set(ids)
        with self._win_lock:
            self._win_at = 0.0
        self.background_refresh(content_only=True)

    def _switch_to(self, app) -> bool:
        for win in self._app_windows(app):
            if W.activate(win["hwnd"]):
                return True
        return False

    def _launch(self, app_id, again: bool = False, as_admin: bool = False,
                from_palette: bool = False):
        app = self.store.get_app(app_id)
        if not app:
            return
        if not again and not as_admin and app_id in self.running and self._switch_to(app):
            self.toast.show(f"{app['name']} — переключились", icon=ft.Icons.SYNC_ALT,
                            icon_color=C.MUTED)
            self.after_launch(from_palette)
            return
        payload = dict(app, run_as_admin=True) if as_admin and not app.get("kind") else app
        try:
            res = self.launcher.launch(payload)
        except Exception as exc:
            log.exception("launching %s failed", app.get("path"))
            res = {"ok": False, "error": str(exc)}
        if not res.get("ok"):
            self._launch_failed(app, res.get("error", "Не удалось запустить"))
            return
        self.store.mark_launched(app_id)
        self.running = set(self.launcher.running_ids())
        if not again:
            self.toast.show(f"{app['name']} открыт", icon=ft.Icons.PLAY_ARROW)
        self.after_launch(from_palette)

    def _launch_failed(self, app, message):
        missing = "не найден" in message.lower()
        self.toast.error(f"{app['name']} не нашёлся на диске" if missing else message,
                         detail="Программу переустановили или перенесли" if missing else None,
                         action=(lambda: self._relocate(app["id"])) if missing else None,
                         action_label="Найти" if missing else None)
        self.refresh()

    def after_launch(self, from_palette: bool = False):
        if from_palette:
            self.view.close_palette()
            self.search_field.value = ""
            if self.setting("hide_after", True):
                self._hide_to_tray()
        self.safe_refresh()

    def _relocate(self, app_id):
        self.relocating = app_id
        self.scan.pick_file()

    def _show_in_folder(self, app_id):
        a = self.store.get_app(app_id)
        if a:
            res = self.launcher.show_in_folder(a)
            if not res.get("ok"):
                self.toast.error(res.get("error", "Не найдено"))
