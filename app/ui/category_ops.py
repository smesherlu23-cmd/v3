"""Категории: создание, порядок, оформление, картинка, удаление."""
from __future__ import annotations

import uuid
from pathlib import Path

import flet as ft

from ..core.text import plu_apps
from ..infra import log
from . import colors as C
from . import screens

CATEGORY_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")


class CategoryMixin:
    def _add_category(self):
        cat = self.store.add_category("Новая категория")
        self.view.set_filter(f"category:{cat['id']}")
        self.view.open_popover(cat["id"])
        self.on_library_changed()

    def _move_category(self, cat_id, delta):
        self.store.move_category(cat_id, delta)
        self.refresh()

    def _reorder_category(self, dragged_id, target_id):
        if dragged_id == target_id:
            return
        ids = [c["id"] for c in self.categories()]
        if dragged_id not in ids or target_id not in ids:
            return
        moving_down = ids.index(target_id) > ids.index(dragged_id)
        ids.remove(dragged_id)
        ids.insert(ids.index(target_id) + (1 if moving_down else 0), dragged_id)
        self.store.reorder_categories(ids)
        self.refresh()

    def _open_popover(self, cat_id):
        self.view.open_popover(cat_id)
        self.refresh()

    def close_popover(self):
        self.view.close_popover()
        self.refresh()

    def rename_category(self, cat_id, name):
        if (name or "").strip():
            self.store.update_category(cat_id, {"name": name.strip()})
            self.on_library_changed()

    def set_category_color(self, cat_id, color):
        self.store.update_category(cat_id, {"color": color})
        self.refresh()

    def set_category_icon(self, cat_id, icon):
        self.store.update_category(cat_id, {"icon": icon, "image": None})
        self.refresh()

    def pick_category_image(self, cat_id):
        def picked(src):
            if not src:
                return
            stored = self._store_category_image(cat_id, src)
            if stored:
                self.store.update_category(cat_id, {"image": stored})
                self.refresh()
        self.ask_for_file("Картинка категории", picked,
                          extensions=[e.lstrip(".") for e in CATEGORY_IMAGE_EXTS])

    def _store_category_image(self, cat_id, src) -> str | None:
        import shutil
        suffix = Path(src).suffix.lower()
        if suffix not in CATEGORY_IMAGE_EXTS:
            self.toast.error("Подойдёт PNG, JPG, WEBP, GIF, BMP или SVG")
            return None
        dest_dir = Path(self.icon_cache_dir()) / "categories"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            # Новое имя на каждую смену: по старому пути Flutter показывал бы
            # прежнюю картинку из своего кэша до перезапуска.
            dest = dest_dir / f"{cat_id}-{uuid.uuid4().hex[:8]}{suffix}"
            shutil.copyfile(src, dest)
        except OSError:
            log.exception("не удалось скопировать изображение категории")
            self.toast.error("Не удалось прочитать файл")
            return None

        for stale in [*dest_dir.glob(f"{cat_id}.*"), *dest_dir.glob(f"{cat_id}-*")]:
            if stale != dest:
                try:
                    stale.unlink()
                except OSError:
                    pass
        return str(dest)

    def clear_category_image(self, cat_id):
        self.store.update_category(cat_id, {"image": None})
        self.refresh()

    def _remove_category(self, cat_id):
        if len(self.categories()) <= 1:
            self.toast.error("Это последняя категория — программам некуда деться")
            return
        cat = next((c for c in self.categories() if c["id"] == cat_id), None)
        undo = self.store.remove_category(cat_id)
        if not undo:
            return
        self.view.close_popover()
        moved = len(undo["apps"])
        text = f"Категория «{cat['name']}» удалена" if cat else "Категория удалена"
        if moved:
            text += f", {moved} {plu_apps(moved)} перенесено"
        self.toast.show(text, icon=ft.Icons.DELETE_OUTLINE, icon_color=C.MUTED,
                        action=lambda: self._restore_category(undo), action_label="Вернуть")
        self.on_library_changed()

    def _restore_category(self, undo):
        self.store.restore_category(undo)
        self.on_library_changed()

    def _render_popover(self):
        cat_id = self.view.popover
        cat = next((c for c in self.categories() if c["id"] == cat_id), None)
        if cat is None:
            self.popover_layer.visible = False
            self.popover_layer.content = None
            return
        index = [c["id"] for c in self.categories()].index(cat_id)
        metrics = self.rail()
        top = (C.HEADER_H + 14 + (2 + index) * (metrics["btn"] + metrics["gap"]) + 9
               - self._rail_scroll)
        height = self._window_height()
        self.popover_layer.left = metrics["rail"] + 8
        self.popover_layer.top = max(C.HEADER_H + 6, min(top, height - C.POPOVER_H - 8))
        self.popover_layer.content = screens.build_category_popover(self, cat)
        self.popover_layer.visible = True
