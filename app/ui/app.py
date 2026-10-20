from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import flet as ft

from ..controllers.scan import ScanController
from ..controllers.sets import SetsController
from ..controllers.triage import TriageController
from ..core import queries
from ..core.hotkeys import resolve_accels
from ..core.store import Store
from ..core.text import moment_label, plu_apps, plu_programs, plu_windows, split_args
from ..core.view_state import PERSISTENT_FIELDS, SEARCH_FIELD, ViewState
from ..infra import log
from ..platform import windows as W
from . import colors as C
from . import menus, screens, theme
from . import widgets as Wg
from .chrome import Chrome
from .context_menus import ContextMenus
from .grid import GridView
from .inspector import InspectorPanel
from .keymap import Keymap
from .menus import MenuHost
from .toast import Notifier, ToastHost

WINDOW_TTL = 2.0
PALETTE_GAP = 8
# Сколько после нажатия клавиши не верить «наведению» мыши: строки палитры
# перестраиваются под неподвижным курсором, Flutter честно сообщает, что
# курсор «вошёл» в новую строку, — и выделение уезжало с лучшего совпадения.
PALETTE_HOVER_GRACE = 0.6
TILE_CACHE_MAX = 600
ICON_SIZE_TTL = 30.0

CATEGORY_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
APP_ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".ico")
APP_ICON_SIZE = 256

class CenturioUI:
    def __init__(self, page: ft.Page, store: Store, launcher, controllers=None):
        self.page = page
        self.store = store
        self.launcher = launcher
        self.controllers = controllers or {}
        self.running: set[str] = set()
        self.view = ViewState(store)
        self._sel_id = None
        self._refresh_lock = threading.RLock()
        self._local = threading.local()
        self._settings = self.store.state()["settings"]
        self._accels: dict[str, str] = {}
        self._set_accels: dict[str, str] = {}
        self.relocating: str | None = None
        self._win_lock = threading.Lock()
        self._win_snapshot: list[dict] = []
        self._win_at = 0.0
        self._tile_cache: OrderedDict[str, tuple] = OrderedDict()
        self._tiles_used: set[str] = set()
        self._tile_epoch: tuple = ()
        self._add_ui: dict | None = None
        self._cat_index: dict[str, dict] = {}
        self._icon_size = 0
        self._icon_size_at = 0.0
        self._visible = True
        self._dirty = False
        self._rail_scroll = 0.0
        self._header_key = None
        self._palette_keyed_at = 0.0
        self._deferred = None
        self.view.on_typing_done = self._run_deferred_refresh

        self.toast = ToastHost(page)
        self.notify = Notifier(self.toast)
        self.context_menus = ContextMenus(self)
        self.keymap = Keymap(self)
        self.chrome = Chrome(self)
        self.grid = GridView(self)
        self.inspector_panel = InspectorPanel(self)
        self.menu = MenuHost(page, on_dismiss=self.context_menus.on_menu_dismissed)
        self.set_ops = SetsController(self)
        self.scan = ScanController(self)
        self.triage = TriageController(self)

        self.search_field = Wg.track_typing(ft.TextField(
            value="", hint_text="Найти или запустить", border=ft.InputBorder.NONE,
            filled=False, dense=True, content_padding=ft.padding.symmetric(0, 0),
            text_size=13.5, color=C.WHITE,
            hint_style=ft.TextStyle(color=C.MUTED_2, size=13.5),
            cursor_color=C.ACCENT, on_change=self._on_search,
            on_click=lambda e: self._open_palette(), always_call_on_tap=True, expand=True,
        ), self.view, SEARCH_FIELD)
        self.search_icon = ft.Icon(ft.Icons.SEARCH, size=15, color=C.MUTED_2)
        self.search_tail = ft.Container()
        self.search_box = ft.Container(
            ft.Row([self.search_icon, self.search_field, self.search_tail],
                   spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=36, border_radius=10, padding=ft.padding.only(12, 0, 8, 0))

        self.header_holder = ft.Container()
        self.rail_container = ft.Container(width=C.RAIL_W, bgcolor=C.BG_0)
        self.sidebar_container = ft.Container(width=C.SIDEBAR_W, bgcolor=C.BG_2)
        self.content_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self.content_holder = ft.Container(self.content_col, expand=True,
                                           padding=ft.padding.only(22, 4, 22, 0))
        self.toolbar_holder = ft.Container()
        self.inspector_container = ft.Container(width=C.INSPECTOR_W, bgcolor=C.BG_2,
                                                visible=False)
        self.inspector_overlay = ft.Container(
            width=C.INSPECTOR_W, bgcolor=C.BG_2, right=0, top=C.HEADER_H, bottom=0,
            visible=False,
            shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(-10, 0),
                                color=C.SHADOW_BAR))
        self.library_body = ft.Container(expand=True)
        self.body = ft.Container(left=0, top=0, right=0, bottom=0)

        self.palette_card = ft.Container(
            opacity=0, offset=ft.Offset(0, -0.02),
            animate_opacity=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT),
            animate_offset=ft.Animation(C.ANIM_FAST, ft.AnimationCurve.EASE_OUT))
        self.palette_scrim = ft.Container(
            left=0, top=0, right=0, bottom=0, bgcolor=C.SCRIM_BODY,
            on_click=lambda e: self._close_palette())
        # Слой начинается под шапкой: накрыв строку поиска, он забирал щелчок
        # по ней, и поле теряло фокус посреди набора.
        self.palette_layer = ft.Container(
            ft.Stack([self.palette_scrim,
                      ft.Container(ft.Row([self.palette_card],
                                          alignment=ft.MainAxisAlignment.CENTER),
                                   left=0, right=0, top=PALETTE_GAP)]),
            left=0, top=C.HEADER_H, right=0, bottom=0, visible=False)
        self.bulk_card = ft.Container(
            opacity=0, offset=ft.Offset(0, 0.3),
            animate_opacity=ft.Animation(C.ANIM_BAR, ft.AnimationCurve.EASE_OUT),
            animate_offset=ft.Animation(C.ANIM_BAR, ft.AnimationCurve.EASE_OUT))
        self.bulk_layer = ft.Container(
            ft.Row([self.bulk_card], alignment=ft.MainAxisAlignment.CENTER),
            left=0, right=0, bottom=26, visible=False)
        self.popover_layer = ft.Container(visible=False)

    @property
    def _snapshot(self):
        return getattr(self._local, "snapshot", None)

    @_snapshot.setter
    def _snapshot(self, value):
        self._local.snapshot = value

    def state(self):
        return self._snapshot if self._snapshot is not None else self.store.state()

    def categories(self):
        return sorted(self.state()["categories"], key=lambda c: c.get("order", 0))

    def apps(self):
        return self.state()["apps"]

    def sets(self):
        return sorted(self.state()["sets"], key=lambda s: s.get("order", 0))

    def inbox(self):
        return sorted(self.state()["inbox"], key=lambda i: i.get("order", 0))

    def setting(self, key, default=None):
        return self._settings.get(key, default)

    def _accent(self):
        return C.parse_hex(self._settings.get("accent")) or C.ACCENT

    def rail(self) -> dict:
        return C.rail_metrics(self._settings.get("rail_size", C.DEFAULT_RAIL_SIZE))

    def _window_width(self) -> float:
        win = getattr(self.page, "window", None)
        return getattr(win, "width", None) or C.LIBRARY_W

    def _window_height(self) -> float:
        win = getattr(self.page, "window", None)
        return getattr(win, "height", None) or C.LIBRARY_H

    def _show_sidebar(self) -> bool:
        return self.view.sidebar_open and self._window_width() >= C.NARROW_SIDEBAR

    def _inspector_floats(self) -> bool:
        return self._window_width() < C.NARROW_INSPECTOR

    def _content_width(self) -> float:
        width = self._window_width() - self.rail()["rail"]
        if self._show_sidebar():
            width -= C.SIDEBAR_W
        if self._inspector_visible() and not self._inspector_floats():
            width -= C.INSPECTOR_W
        return max(240.0, width)

    def _inspector_visible(self) -> bool:
        return bool(self.view.inspector and self.view.screen == "grid"
                    and not self.view.active_set and not self.view.select_mode)

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

    def mount(self):
        self.store.on_error = self._on_store_error
        main = ft.Column([self.toolbar_holder, self.content_holder], spacing=0, expand=True)
        body = ft.Row([self.rail_container, self.sidebar_container, main,
                       self.inspector_container], spacing=0, expand=True)
        self.library_body.content = ft.Column([self.header_holder, body],
                                              spacing=0, expand=True)
        root = ft.Stack([self.body, self.inspector_overlay, self.palette_layer,
                         self.bulk_layer, self.popover_layer,
                         self.menu.control, self.toast.control], expand=True)
        self.page.add(root)
        self.refresh()
        if self.store.write_error:
            self._on_store_error(self.store.write_error)
        if self.store.newer_version:
            self.toast.error(
                f"Файл данных сохранён более новой версией Centurio (схема "
                f"{self.store.newer_version}) — показываю то, что понимаю, "
                f"но ничего не сохраняю: иначе потерялось бы остальное",
                detail=str(self.store.path))

    def set_running(self, ids):
        self.running = set(ids)
        with self._win_lock:
            self._win_at = 0.0
        self.background_refresh(content_only=True)

    def _editing_rebuilt_field(self) -> bool:
        return bool(self.view.typing) and self.view.typing not in PERSISTENT_FIELDS

    def background_refresh(self, content_only: bool = False):
        """Перерисовка не по действию пользователя: монитор процессов, фоновые потоки.

        Пока курсор в поле, которое перерисовка собирает заново (имя или
        аргументы в панели справа, имя набора или категории), она стёрла бы
        набираемое вместе с полем. Тогда перерисовка ждёт, пока поле не
        потеряет фокус.
        """
        if self._editing_rebuilt_field():
            # None — ничего не ждёт; True — только содержимое; False — всё.
            self._deferred = content_only if self._deferred is None \
                else (self._deferred and content_only)
            return
        try:
            self.refresh(content_only=content_only)
        except Exception:
            log.exception("сбой при фоновом обновлении")

    def _run_deferred_refresh(self):
        pending, self._deferred = self._deferred, None
        if pending is not None:
            self.background_refresh(content_only=pending)

    def refresh(self, content_only=False):
        if not self._visible:
            self._dirty = True
            self._settings = self.store.settings()
            return
        with self._refresh_lock:
            self._snapshot = self.store.state()
            self._settings = self._snapshot["settings"]
            theme.apply_theme(self._settings)
            self._accels, self._set_accels = resolve_accels(self._snapshot["apps"], self.sets())
            self._cat_index = {c["id"]: c for c in self._snapshot["categories"]}
            self._tile_epoch = (
                self._settings.get("tile_size"),
                self._settings.get("accent", C.ACCENT),
                self._settings.get("bg_tint"),
                self._settings.get("contrast", theme.DEFAULT_CONTRAST),
                bool(self._settings.get("game_posters", True)),
                self._settings.get("rail_size", C.DEFAULT_RAIL_SIZE),
                self.view.select_mode,
                self.view.mode,
            )
            live = {a["id"] for a in self._snapshot["apps"]}
            self._tile_cache = OrderedDict(
                (k, v) for k, v in self._tile_cache.items() if k in live)
            self._tiles_used = set()
            try:
                self.view.drop_missing(a["id"] for a in self._snapshot["apps"])
                if self.view.active_set and not any(
                        s["id"] == self.view.active_set for s in self._snapshot["sets"]):
                    self.view.close_set()
                self._dirty = False
                self._refresh_library(content_only)
                self.body.content = self.library_body
                self._render_palette()
                self._render_bulk_bar()
                self.chrome.sync_search_box()
                self._render_popover()
                self._trim_tile_cache()
            finally:
                self._snapshot = None
            self.page.update()

    def _trim_tile_cache(self):
        cap = max(TILE_CACHE_MAX, len(self._tiles_used))
        if len(self._tile_cache) <= cap:
            return
        for app_id in list(self._tile_cache):
            if len(self._tile_cache) <= cap:
                break
            if app_id not in self._tiles_used:
                del self._tile_cache[app_id]

    def _refresh_library(self, content_only: bool):
        self.view.stop_typing_in_rebuilt_fields()
        if not content_only:
            # Шапку не пересобирать без нужды: строка поиска в ней, и новая
            # шапка — новое поле на стороне Flutter, без фокуса и с потерей
            # набранного. Меняется она только вместе с темой.
            header_key = (self._settings.get("accent"), self._settings.get("bg_tint"),
                          self._settings.get("contrast"))
            if self.header_holder.content is None or header_key != self._header_key:
                self._header_key = header_key
                self.header_holder.content = self.chrome.build_header()
            self.rail_container.width = self.rail()["rail"]
            self.rail_container.content = self.chrome.build_rail()
        show_sidebar = self._show_sidebar()
        self.sidebar_container.visible = show_sidebar
        self.sidebar_container.content = self.chrome.build_sidebar() if show_sidebar else None
        screen = self.view.screen
        on_grid = screen == "grid" and not self.view.active_set
        self.toolbar_holder.visible = on_grid
        if on_grid:
            self.toolbar_holder.content = self.chrome.build_toolbar()
        self.content_col.controls = self.grid.build_content()
        self.content_col.scroll = ft.ScrollMode.AUTO if on_grid else None
        self.content_holder.padding = (ft.padding.only(22, 4, 22, 0) if on_grid
                                       else ft.padding.all(0))
        inspector = self.inspector_panel.build_inspector() if self._inspector_visible() else None
        floating = inspector is not None and self._inspector_floats()
        self.inspector_container.visible = inspector is not None and not floating
        self.inspector_container.content = None if floating else inspector
        self.inspector_overlay.visible = floating
        self.inspector_overlay.content = inspector if floating else None

    def set_visible(self, visible: bool):
        visible = bool(visible)
        if visible == self._visible:
            return
        self._visible = visible
        if visible and self._dirty:
            self.refresh()

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

    def cat_of(self, app) -> dict | None:
        cid = app.get("category_id")
        if not cid:
            return None
        if self._snapshot is not None and self._cat_index:
            return self._cat_index.get(cid)
        return next((c for c in self.categories() if c["id"] == cid), None)

    def icon_slot(self, app, size: int, radius: int, glyph: int | None = None,
                  border=None, glyph_color=None, bgcolor=None):
        kind = _KIND_GLYPHS.get(app.get("kind") or "")
        cat = self.cat_of(app) if app.get("category_id") and not kind else None
        return Wg.icon_slot(app, size, radius, glyph=glyph, border=border,
                            glyph_color=glyph_color, bgcolor=bgcolor, cat=cat,
                            source_glyph=kind or _source_glyph(app.get("source")))

    def is_all_view(self):
        return self.view.is_all_view()

    def sections(self):
        return queries.build_sections(self.apps(), self.categories(), self.view.filter,
                                      self.view.sort, self.running)

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
            return next((r for r in rows if r["kind"] == "app"), None)
        return rows[min(self.view.palette_index, len(rows) - 1)]

    def _palette_app(self, rows=None):
        rows = self._palette_rows() if rows is None else rows
        current = self.palette_current(rows)
        if current is not None and current["kind"] == "app":
            return current["app"]
        return next((r["app"] for r in rows if r["kind"] == "app"), None)

    def _render_palette(self):
        if not self.view.palette_open:
            self.palette_layer.visible = False
            self.palette_card.content = None
            self.palette_card.opacity = 0
            self.palette_card.offset = ft.Offset(0, -0.02)
            return
        rows = self._palette_rows()
        self.palette_card.content = screens.build_palette(self, rows)
        self.palette_card.opacity = 1
        self.palette_card.offset = ft.Offset(0, 0)
        self.palette_layer.visible = True

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

    def _focus(self, field):
        try:
            if field.page:
                field.focus()
        except Exception:
            log.exception("сбой при фокусировке на поле")

    def _focus_search(self):
        self.view.open_palette()
        self.refresh()
        self._focus(self.search_field)

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

    def _toggle_sidebar(self):
        self.view.toggle_sidebar()
        self.refresh()

    def _set_filter(self, f):
        self.view.set_filter(f)
        self.refresh()

    def _set_mode(self, m):
        self.view.set_mode(m)
        self.refresh()

    def _set_sort(self, key):
        self.view.set_sort(key)
        self.refresh()

    def _toggle_section(self, cid):
        self.view.toggle_section(cid)
        self.refresh()

    def note_palette_keys(self):
        self._palette_keyed_at = time.monotonic()

    def sync_query(self):
        """Запрос из поля, а не из последнего обработанного on_change.

        Обработчики Flet идут в пуле потоков: Enter сразу после последней
        буквы мог обработаться раньше её on_change и запустить лучшее
        совпадение для запроса без этой буквы. Значение поля Flet обновляет
        до того, как раздаёт события, — оно всегда свежее.
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

    def _toast_hint_quick(self):
        self.toast.show("Закрепить можно правой кнопкой по плитке — «В быстрый запуск»",
                        icon=ft.Icons.BOLT, icon_color=C.MUTED)

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
        if e.data == "true" and (self.view.palette_index != index
                                 or self.view.palette_focus != "results"):
            self.view.palette_index = index
            self.view.palette_focus = "results"
            self._refresh_palette_only()

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
        picker = getattr(self, "_image_picker", None)
        if picker is None:
            picker = ft.FilePicker()
            self._image_picker = picker
            self.page.overlay.append(picker)
            self.page.update()

        def on_result(e):
            if not e.files:
                return
            src = e.files[0].path or e.files[0].name
            stored = self._store_category_image(cat_id, src)
            if stored:
                self.store.update_category(cat_id, {"image": stored})
                self.refresh()
        picker.on_result = on_result
        picker.pick_files(dialog_title="Картинка категории", allow_multiple=False,
                          allowed_extensions=[e.lstrip(".") for e in CATEGORY_IMAGE_EXTS])

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

    def open_add(self):
        self.view.set_screen("add")
        self.view.reset_add()
        self._add_ui = None
        self.scan.start_scan()
        self.refresh()

    def _open_settings(self):
        self.view.set_screen("settings")
        self.refresh()

    def set_settings_tab(self, tab: str):
        self.view.settings_tab = tab
        self.refresh()

    def open_triage(self):
        self.view.set_screen("triage")
        self.refresh()

    def _open_set(self, set_id):
        self.view.open_set(set_id)
        self.refresh()

    def back_to_grid(self):
        self.view.set_screen("grid")
        self.refresh()

    def open_library(self):
        """Показ окна из трея или повторным запуском: сразу можно печатать имя."""
        self.view.close_palette()
        self.view.set_screen("grid")
        self.refresh()
        self._focus(self.search_field)

    def set_setting(self, key, value):
        self.store.set_setting(key, value)
        cb = self.controllers.get("on_setting")
        if cb:
            cb(key, value)
        self.refresh()

    def set_settings(self, pairs: dict) -> None:
        items = list(pairs.items())
        for i, (key, value) in enumerate(items):
            self.store.set_setting(key, value, persist=(i == len(items) - 1))
            cb = self.controllers.get("on_setting")
            if cb:
                cb(key, value)
        self.refresh()

    def on_library_changed(self):
        self.view.revalidate(self.categories())
        cb = self.controllers.get("on_library_changed")
        if cb:
            cb()
        self.refresh()

    def _on_store_error(self, message):
        try:
            self.toast.error(f"Не удалось сохранить данные: {message}")
        except Exception:
            log.exception("не удалось сообщить пользователю о сбое записи в хранилище")

    def _show_in_folder(self, app_id):
        a = self.store.get_app(app_id)
        if a:
            res = self.launcher.show_in_folder(a)
            if not res.get("ok"):
                self.toast.error(res.get("error", "Не найдено"))

    def _minimize(self):
        cb = self.controllers.get("minimize")
        if cb:
            cb()

    def _toggle_maximize(self):
        cb = self.controllers.get("toggle_maximize")
        if cb:
            cb()

    def _close(self):
        cb = self.controllers.get("close")
        if cb:
            cb()

    def _hide_to_tray(self):
        cb = self.controllers.get("hide_to_tray")
        if cb:
            cb()

    def _current_title(self):
        return queries.current_title(self.view.filter, self.categories())

    def icon_cache_dir(self) -> str:
        return str(Path(self.store.path).parent / "icons")

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

    def safe_refresh(self):
        self.background_refresh()

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

_KIND_GLYPHS = {"web": "language", "folder": "folder", "file": "description"}


def _source_glyph(source: str) -> str:
    return queries.SOURCES.get(source or "", {}).get("icon", "apps")
