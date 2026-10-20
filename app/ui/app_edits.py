"""Правки записей библиотеки: имя, значок, параметры, порядок, удаление."""
from __future__ import annotations

import uuid
from pathlib import Path

import flet as ft

from ..core.text import plu_apps, split_args
from ..infra import log
from . import colors as C

APP_ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".ico")
APP_ICON_SIZE = 256


class AppEditsMixin:
    def _toast_hint_quick(self):
        self.toast.show("Закрепить можно правой кнопкой по плитке — «В быстрый запуск»",
                        icon=ft.Icons.BOLT, icon_color=C.MUTED)

    def _toggle_fav(self, app_id):
        a = self.store.get_app(app_id)
        if a:
            self.store.update_app(app_id, {"favorite": not a.get("favorite")})
        self.refresh()

    def _toggle_quick(self, app_id, value):
        self.store.update_app(app_id, {"quick": bool(value)})
        self.on_library_changed()
        accel = self._accels.get(app_id)
        self.toast.show(f"Закреплено · {accel}" if value and accel
                        else "Закреплено" if value else "Откреплено",
                        icon=ft.Icons.BOLT, icon_color=C.MUTED)

    def _toggle_set_quick(self, set_id, value):
        self.set_ops.toggle_set_quick(set_id, value)

    def _hide_apps(self, ids, hidden: bool):
        ids = [i for i in ids if i]
        touched = self.store.update_apps(ids, {"hidden": bool(hidden)})
        if not touched:
            return
        self.view.clear_selection()
        text = (f"Скрыто {touched}" if hidden else f"Снова видно: {touched}")
        self.toast.show(text, icon=ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY,
                        icon_color=C.MUTED,
                        action=lambda: self._hide_apps(ids, not hidden),
                        action_label="Отменить")
        self.on_library_changed()

    def rename_app(self, app_id, name):
        name = (name or "").strip()
        app = self.store.get_app(app_id)
        if not app or not name or name == app["name"]:
            return
        self.store.update_app(app_id, {"name": name})
        self.on_library_changed()

    def set_aliases(self, app_id, text):
        app = self.store.get_app(app_id)
        if not app or ", ".join(app.get("aliases") or []) == (text or "").strip():
            return
        self.store.update_app(app_id, {"aliases": text or ""})
        self.refresh()

    def pick_app_icon(self, app_id):
        def picked(src):
            if not src:
                return
            stored = self._store_app_icon(app_id, src)
            if stored:
                self.store.update_app(app_id, {"icon": stored, "icon_fit": "contain",
                                               "custom_icon": True})
                self.on_library_changed()
        self.ask_for_file("Значок программы", picked,
                          extensions=[e.lstrip(".") for e in APP_ICON_EXTS])

    def _store_app_icon(self, app_id, src) -> str | None:
        """Своя картинка → PNG в кэше значков, под новым именем на каждую смену.

        Новое имя нужно, чтобы ни кэш плиток, ни кэш картинок Flutter не
        показали прежний значок.
        """
        if Path(src).suffix.lower() not in APP_ICON_EXTS:
            self.toast.error("Подойдёт PNG, JPG, WEBP, GIF, BMP или ICO")
            return None
        dest_dir = Path(self.icon_cache_dir()) / "custom"
        dest = dest_dir / f"{app_id}-{uuid.uuid4().hex[:8]}.png"
        try:
            from PIL import Image

            dest_dir.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im = im.convert("RGBA")
                im.thumbnail((APP_ICON_SIZE, APP_ICON_SIZE))
                im.save(dest, "PNG")
        except Exception:
            log.exception("не удалось подготовить значок из %s", src)
            self.toast.error("Не удалось прочитать картинку")
            return None
        self._drop_custom_icons(app_id, keep=dest)
        return str(dest)

    def _drop_custom_icons(self, app_id, keep=None):
        for stale in (Path(self.icon_cache_dir()) / "custom").glob(f"{app_id}-*"):
            if stale != keep:
                try:
                    stale.unlink()
                except OSError:
                    pass

    def reset_app_icon(self, app_id):
        self.store.update_app(app_id, {"icon": None, "custom_icon": False})
        self._drop_custom_icons(app_id)
        self.on_library_changed()
        self.scan.backfill_icons_async()

    def _set_args(self, app_id, value):
        text = (value or "").strip()
        try:
            args = split_args(text) if text else []
        except ValueError:
            self.toast.error("В аргументах не закрыта кавычка — не сохранено", detail=text)
            self.refresh()
            return
        self.store.update_app(app_id, {"args": args})
        self.refresh()

    def _set_admin(self, app_id, value):
        self.store.update_app(app_id, {"run_as_admin": bool(value)})
        self.refresh()

    def _pick_working_dir(self, app_id):
        def picked(path):
            if path:
                self.store.update_app(app_id, {"working_dir": path})
                self.refresh()
        self.ask_for_folder("Выберите рабочую папку", picked)

    def _move_apps_to_category(self, app_ids, cat_id):
        cat = next((c for c in self.categories() if c["id"] == cat_id), None)
        ids = [i for i in app_ids if i]
        if not cat or not ids:
            return
        before = {a["id"]: a.get("category_id") for a in self.apps() if a["id"] in set(ids)}
        moved = self.store.update_apps(ids, {"category_id": cat_id})
        if not moved:
            return

        def undo():
            for app_id, old in before.items():
                self.store.update_app(app_id, {"category_id": old}, persist=False)
            self.store.flush()
            self.on_library_changed()

        first = next((a["name"] for a in self.apps() if a["id"] == ids[0]), "")
        text = (f"{first} переложен в «{cat['name']}»" if moved == 1
                else f"Переложено {moved} в «{cat['name']}»")
        self.toast.show(text, icon=ft.Icons.FOLDER, icon_color=C.MUTED,
                        action=undo, action_label="Вернуть")
        self.on_library_changed()

    def _bulk_favorite(self, ids):
        before = [i for i in ids if not (self.store.get_app(i) or {}).get("favorite")]
        self.store.update_apps(ids, {"favorite": True})
        self.toast.show(f"В избранном: {len(ids)}", icon=ft.Icons.STAR, icon_color=C.STAR,
                        action=lambda: self._undo_favorite(before),
                        action_label="Отменить")
        self.refresh()

    def _undo_favorite(self, ids):
        self.store.update_apps(ids, {"favorite": False})
        self.refresh()

    def _remove_apps(self, app_ids):
        if not app_ids:
            return
        bundle = self.store.remove_apps_with_sets(app_ids)
        gone = bundle["apps"]
        if not gone:
            return
        # Убранное руками больше не предлагать при сканировании; отмена
        # (restore_apps) вычёркивает из списка обратно.
        self.store.ignore(gone)
        self.view.close_inspector()
        text = (f"{gone[0]['name']} убран из библиотеки" if len(gone) == 1
                else f"Убрано {len(gone)} {plu_apps(len(gone))}")
        self.toast.show(text, icon=ft.Icons.DELETE_OUTLINE, icon_color=C.MUTED,
                        action=lambda: self._restore_apps(bundle), action_label="Вернуть")
        self.on_library_changed()

    def _restore_apps(self, bundle):
        self.store.restore_apps_and_sets(bundle)
        self.on_library_changed()

    def _reorder_apps(self, section_ids, dragged_ids, target_id):
        dragged = [i for i in dragged_ids if i in section_ids]
        if not dragged or target_id in dragged or target_id not in section_ids:
            return
        moving_right = section_ids.index(target_id) > section_ids.index(dragged[0])
        order = [i for i in section_ids if i not in dragged]
        idx = order.index(target_id) + (1 if moving_right else 0)
        order[idx:idx] = dragged
        self.store.reorder_apps(order)
        if self.view.sort != "manual":
            self.view.set_sort("manual")
        self.refresh()
