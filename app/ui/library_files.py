"""Файлы вокруг библиотеки: выбор файла и папки, копии, кэш значков."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import flet as ft

from ..core.text import moment_label, plu_programs
from ..infra import log
from . import colors as C
from . import menus

ICON_SIZE_TTL = 30.0


class LibraryFilesMixin:
    def ask_for_file(self, title, on_path, extensions=None):
        picker = getattr(self, "_file_picker", None)
        if picker is None:
            picker = ft.FilePicker()
            self._file_picker = picker
            self.page.overlay.append(picker)
            self.page.update()

        def on_result(e):
            if not e.files:
                on_path(None)
                return
            picked = e.files[0]
            on_path(picked.path or picked.name)
        picker.on_result = on_result
        picker.pick_files(dialog_title=title, allow_multiple=False,
                          allowed_extensions=extensions)

    def ask_for_folder(self, title, on_path):
        picker = getattr(self, "_dir_picker", None)
        if picker is None:
            picker = ft.FilePicker()
            self._dir_picker = picker
            self.page.overlay.append(picker)
            self.page.update()
        picker.on_result = lambda e: on_path(e.path or None)
        picker.get_directory_path(dialog_title=title)

    def icon_cache_dir(self) -> str:
        return str(Path(self.store.path).parent / "icons")

    def backup(self):
        try:
            path = self.store.backup()
        except Exception:
            log.exception("не удалось создать копию")
            self.toast.error("Не удалось создать копию", action=self.backup,
                             action_label="Повторить")
            return
        self.toast.show(f"Копия сохранена: {path.name}", icon=ft.Icons.BACKUP,
                        icon_color=C.MUTED)

    def pick_backup(self):
        self.ask_for_file("Копия библиотеки", self.restore_backup, extensions=["json"])

    def open_url(self, url: str):
        import webbrowser

        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    def restore_menu(self):
        """Восстановить из автокопии — или выбрать файл, если их ещё нет."""
        copies = self.store.auto_backups()
        if not copies:
            self.pick_backup()
            return
        rows = []
        for path in copies:
            summary = self.store.backup_summary(path)
            if summary is None:
                continue
            try:
                when = moment_label(path.stat().st_mtime)
            except OSError:
                continue
            count = summary["apps"]
            rows.append(menus.item(ft.Icons.HISTORY, when,
                                   lambda p=path: self.restore_backup(str(p)),
                                   hint=f"{count} {plu_programs(count)}"))
        rows += [menus.separator(),
                 menus.item(ft.Icons.FOLDER_OPEN, "Из файла…", self.pick_backup)]
        self.menu.show(self._window_width() / 2 - 120, 180.0, rows,
                       header=menus.text_header("Восстановить библиотеку"))

    def last_auto_backup(self) -> str:
        copies = self.store.auto_backups()
        try:
            return moment_label(copies[0].stat().st_mtime) if copies else ""
        except OSError:
            return ""

    def restore_backup(self, src):
        """Заменить библиотеку копией. Текущая сначала сама уходит в копию."""
        if not src:
            return
        try:
            safety = self.store.backup()
        except Exception:
            log.exception("не удалось сохранить текущую библиотеку перед восстановлением")
            self.toast.error("Не удалось сохранить текущую библиотеку — восстановление отменено")
            return
        if not self.store.import_data(src):
            self.toast.error("Это не копия библиотеки Centurio или она от более новой версии",
                             detail=str(src))
            return
        self.view.set_screen("grid")
        self.toast.show(f"Библиотека восстановлена из {Path(src).name}", icon=ft.Icons.RESTORE,
                        icon_color=C.MUTED, action=lambda: self._undo_restore(safety),
                        action_label="Вернуть")
        self.on_library_changed()

    def _undo_restore(self, safety):
        if self.store.import_data(safety):
            self.on_library_changed()

    def show_data_folder(self):
        res = self.launcher.show_in_folder({"path": str(self.store.path)})
        if not res.get("ok"):
            self.toast.error(res.get("error", "Папка не найдена"))

    def icon_cache_size(self) -> int:
        now = time.monotonic()
        if self._icon_size_at and now - self._icon_size_at <= ICON_SIZE_TTL:
            return self._icon_size
        total = 0
        try:
            for entry in Path(self.icon_cache_dir()).rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except OSError:
            total = 0
        self._icon_size, self._icon_size_at = total, now
        return total

    def forget_icon_cache_size(self) -> None:
        self._icon_size_at = 0.0

    def clear_icon_cache(self):
        removed = 0
        keep = {(c.get("image") or "") for c in self.categories()}
        keep |= {a.get("icon") or "" for a in self.apps() if a.get("custom_icon")}
        try:
            for entry in Path(self.icon_cache_dir()).rglob("*"):
                if entry.is_file() and str(entry) not in keep:
                    entry.unlink()
                    removed += 1
        except OSError:
            log.exception("не удалось очистить кэш иконок")
            self.toast.error("Не удалось очистить кэш")
            return
        self.store.update_apps([a["id"] for a in self.apps() if not a.get("custom_icon")],
                               {"icon": None})
        self.store.update_apps([a["id"] for a in self.apps()], {"poster": None})
        self.forget_icon_cache_size()
        self.toast.show(f"Кэш очищен, файлов удалено: {removed}")
        self.scan.backfill_icons_async()
        self.refresh()
