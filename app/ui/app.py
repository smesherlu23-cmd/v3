from __future__ import annotations

import os
import threading
from collections import OrderedDict

import flet as ft

from ..controllers.scan import ScanController
from ..controllers.sets import SetsController
from ..controllers.triage import TriageController
from ..controllers.updates import UpdatesController
from ..core import queries
from ..core.hotkeys import resolve_accels
from ..core.store import Store
from ..core.view_state import PERSISTENT_FIELDS, SEARCH_FIELD, ViewState
from ..infra import log
from . import colors as C
from . import theme
from . import widgets as Wg
from .app_edits import AppEditsMixin
from .category_ops import CategoryMixin
from .chrome import Chrome
from .context_menus import ContextMenus
from .grid import GridView
from .inspector import InspectorPanel
from .keymap import Keymap
from .launching import LaunchMixin
from .library_files import LibraryFilesMixin
from .menus import MenuHost
from .palette_ops import PaletteMixin
from .selection import SelectionMixin
from .toast import Notifier, ToastHost

PALETTE_GAP = 8
TILE_CACHE_MAX = 600


class CenturioUI(PaletteMixin, SelectionMixin, LaunchMixin, AppEditsMixin, CategoryMixin,
                 LibraryFilesMixin):
    """Окно Centurio: состояние, сборка и перерисовка.

    Действия разнесены по примесям рядом: палитра поиска (`palette_ops`),
    выбор плиток (`selection`), запуск (`launching`), правки записей
    (`app_edits`), категории (`category_ops`), файлы и копии (`library_files`).
    """

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
        # Программы, чьего файла нет на диске: метка на плитке и «Найти…» в
        # меню держатся, пока путь не исправят, а не 8 секунд уведомления.
        self.missing: set[str] = set()
        self._mode = None
        self._visible = True
        self._dirty = False
        self._header_key = None
        # Панель, развёрнутая кнопкой в узком окне, — только до конца сеанса.
        self._narrow_sidebar = False
        self._palette_keyed_at = 0.0
        self._deferred = None
        self.view.on_typing_done = self._run_deferred_refresh
        self.view.on_stray_focus = lambda: self.refocus_search()

        self.toast = ToastHost(page, accent=self._accent)
        self.notify = Notifier(self.toast)
        self.context_menus = ContextMenus(self)
        self.keymap = Keymap(self)
        self.chrome = Chrome(self)
        self.grid = GridView(self)
        self.inspector_panel = InspectorPanel(self)
        self.menu = MenuHost(page, on_dismiss=self.context_menus.on_menu_dismissed,
                             accent=self._accent)
        self.set_ops = SetsController(self)
        self.scan = ScanController(self)
        self.triage = TriageController(self)
        self.updates = UpdatesController(self)

        self.search_field = Wg.track_typing(ft.TextField(
            value="", hint_text="Найти или запустить", border=ft.NoInputBorder(),
            filled=False, dense=True, content_padding=ft.Padding.symmetric(vertical=0, horizontal=0),
            text_size=C.FS_BODY, color=C.TEXT,
            hint_style=ft.TextStyle(color=C.MUTED_2, size=C.FS_BODY),
            cursor_color=C.TEXT, on_change=self._on_search,
            on_click=lambda e: self._open_palette(), always_call_on_tap=True, expand=True,
        ), self.view, SEARCH_FIELD)
        self.search_icon = ft.Icon(ft.Icons.SEARCH_ROUNDED, size=17, color=C.MUTED_2)
        self.search_tail = ft.Container()
        self.search_box = ft.Container(
            ft.Row([self.search_icon, self.search_field, self.search_tail],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=34, border_radius=C.R, animate=Wg.anim(C.ANIM_FAST),
            padding=ft.Padding.only(left=10, top=0, right=8, bottom=0))

        self.header_holder = ft.Container()
        # Одна боковая панель, как в Finder: развёрнута или полосой значков.
        # Ширина меняется плавно.
        self.sidebar_container = ft.Container(width=C.SIDEBAR_W, animate=Wg.anim(C.ANIM_BAR),
                                              clip_behavior=ft.ClipBehavior.HARD_EDGE)
        self.content_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        # Смена экрана — мягким переходом: новая колонка проявляется поверх
        # старой. Внутри одного экрана колонка та же, и перерисовки не мигают.
        self.content_switcher = ft.AnimatedSwitcher(
            self.content_col, transition=ft.AnimatedSwitcherTransition.FADE,
            duration=C.ANIM_BAR, reverse_duration=C.ANIM_FAST,
            switch_in_curve=ft.AnimationCurve(C.EASE),
            switch_out_curve=ft.AnimationCurve(C.EASE), expand=True)
        self._screen_key = None
        self.content_holder = ft.Container(self.content_switcher, expand=True,
                                           padding=ft.Padding.only(left=24, top=16, right=24))
        # Инструменты сетки живут в заголовке окна, как в macOS.
        self.toolbar_holder = ft.Container()
        # Панель свойств лежит поверх сетки отдельной стеклянной карточкой: сбоку
        # она отнимала у сетки две колонки, и плитка уезжала в другой ряд.
        self.inspector_overlay = ft.Container(
            width=C.INSPECTOR_W, right=12, top=C.HEADER_H + 12, bottom=12, visible=False,
            animate_offset=Wg.anim(C.ANIM_BAR), animate_opacity=Wg.anim(C.ANIM_FAST))
        self.library_body = ft.Container(expand=True)
        self.body = ft.Container(left=0, top=0, right=0, bottom=0)

        self.palette_card = ft.Container(
            opacity=0, scale=0.97,
            animate_opacity=Wg.anim(C.ANIM_FAST),
            animate_scale=Wg.anim(C.ANIM_POP, spring=True))
        self.palette_scrim = ft.Container(
            left=0, top=0, right=0, bottom=0, bgcolor=C.SCRIM,
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
            opacity=0, offset=ft.Offset(0, 0.4),
            animate_opacity=Wg.anim(C.ANIM_BAR),
            animate_offset=Wg.anim(C.ANIM_BAR, spring=True))
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
        return theme.effective_accent(self._settings.get("accent"))

    def _on_accent(self):
        return C.on_color(self._accent())

    def _system_brightness(self) -> str | None:
        value = getattr(self.page, "platform_brightness", None)
        value = getattr(value, "value", value)
        return value if value in ("light", "dark") else None

    def _apply_theme(self):
        mode = theme.apply_theme(self._settings, system=self._system_brightness())
        if mode != self._mode:
            self._mode = mode
            try:
                self.page.theme_mode = (ft.ThemeMode.LIGHT if mode == "light"
                                        else ft.ThemeMode.DARK)
                self.page.bgcolor = C.BG
            except Exception:
                log.exception("не удалось переключить оформление окна")

    def _window_width(self) -> float:
        win = getattr(self.page, "window", None)
        return getattr(win, "width", None) or C.LIBRARY_W

    def _window_height(self) -> float:
        win = getattr(self.page, "window", None)
        return getattr(win, "height", None) or C.LIBRARY_H

    def _full_width_screen(self) -> bool:
        # Настройки — своё окно со своей навигацией: полоса категорий и
        # панель библиотеки рядом с ними давали три колонки до первого
        # переключателя.
        return self.view.screen == "settings"

    def _show_sidebar(self) -> bool:
        return not self._full_width_screen()

    def _narrow_window(self) -> bool:
        return self._window_width() < C.NARROW_SIDEBAR

    def _sidebar_expanded(self) -> bool:
        """Панель с подписями; иначе — полоса значков.

        В узком окне она сама сворачивается, а кнопка разворачивает её до
        конца сеанса — сохранённый выбор для широкого окна при этом не
        меняется. Раньше кнопка в узком окне молча переключала его, ничего
        не показав.
        """
        if self._narrow_window():
            return self._narrow_sidebar
        return self.view.sidebar_open

    def _sidebar_width(self) -> int:
        if not self._show_sidebar():
            return 0
        return C.SIDEBAR_W if self._sidebar_expanded() else C.SIDEBAR_RAIL_W

    def _content_width(self) -> float:
        return max(240.0, self._window_width() - self._sidebar_width())

    def _inspector_visible(self) -> bool:
        return bool(self.view.inspector and self.view.screen == "grid"
                    and not self.view.active_set and not self.view.select_mode)

    def mount(self):
        # Сервис выбора файла регистрируется на странице при создании — то есть
        # здесь, пока известна текущая страница, а не в обработчике щелчка.
        self.file_picker = ft.FilePicker()
        self.store.on_error = self._on_store_error
        body = ft.Row([self.sidebar_container, self.content_holder], spacing=0, expand=True)
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

    def in_background(self, fn, *args):
        """Долгое (значок через PowerShell, обложка из сети) — не в обработчике.

        Во Flet 1.0 обычный обработчик события выполняется прямо в цикле
        событий, и пока он работает, окно не отвечает.
        """
        def run():
            try:
                fn(*args)
            except Exception:
                log.exception("сбой фоновой операции")
        threading.Thread(target=run, daemon=True).start()

    def run_async(self, coro_fn, *args):
        """Асинхронный метод Flet (фокус, окно, выбор файла) из обычного кода."""
        try:
            self.page.run_task(coro_fn, *args)
        except Exception:
            log.exception("не удалось запустить асинхронный вызов Flet")

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
            self._apply_theme()
            self._accels, self._set_accels = resolve_accels(self._snapshot["apps"], self.sets())
            self._cat_index = {c["id"]: c for c in self._snapshot["categories"]}
            self._tile_epoch = (
                self._mode,
                self._settings.get("tile_size"),
                self._settings.get("accent", C.ACCENT),
                self._settings.get("bg_tint"),
                self._settings.get("contrast", theme.DEFAULT_CONTRAST),
                bool(self._settings.get("game_posters", True)),
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
                          self._settings.get("contrast"), self._mode)
            if self.header_holder.content is None or header_key != self._header_key:
                self._header_key = header_key
                self.header_holder.content = self.chrome.build_header()
        show_sidebar = self._show_sidebar()
        self.sidebar_container.visible = show_sidebar
        self.sidebar_container.width = self._sidebar_width()
        self.sidebar_container.content = self.chrome.build_sidebar() if show_sidebar else None
        screen = self.view.screen
        on_grid = screen == "grid" and not self.view.active_set
        self.chrome.sync_header()
        key = (screen, self.view.active_set)
        if key != self._screen_key:
            # Новый экран — новая колонка: переключатель проявит её поверх старой.
            if self._screen_key is not None:
                self.content_col = ft.Column(spacing=0, expand=True)
                self.content_switcher.content = self.content_col
            self._screen_key = key
        self.content_col.controls = self.grid.build_content()
        self.content_col.scroll = ft.ScrollMode.AUTO if on_grid else None
        self.content_holder.padding = (ft.Padding.only(left=24, top=16, right=24) if on_grid
                                       else ft.Padding.all(0))
        inspector = self.inspector_panel.build_inspector() if self._inspector_visible() else None
        appearing = inspector is not None and not self.inspector_overlay.visible
        self.inspector_overlay.visible = inspector is not None
        self.inspector_overlay.content = inspector
        if appearing:
            # Панель выезжает справа, а не возникает.
            Wg.enter(self.inspector_overlay,
                     {"offset": ft.Offset(0.08, 0), "opacity": 0},
                     {"offset": ft.Offset(0, 0), "opacity": 1})

    def set_visible(self, visible: bool):
        visible = bool(visible)
        if visible == self._visible:
            return
        self._visible = visible
        log.info("окно %s", "показано" if visible else "скрыто — перерисовки ждут показа")
        if visible and self._dirty:
            self.refresh()

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

    def set_mosaic(self, rec, size: int, radius: int):
        by_id = {a["id"]: a for a in self.apps()}
        members = [by_id[i] for i in rec.get("apps", []) if i in by_id][:4]
        cell = Wg.mosaic_cell(size, len(members))
        cells = [self.icon_slot(a, cell, max(2, cell // 4), glyph=max(8, round(cell * 0.6)))
                 for a in members]
        return Wg.mosaic(cells, size, radius)

    def check_missing(self):
        """Какие файлы пропали с диска — в фоне: при запуске и при показе окна.

        Пока Centurio сидел в трее, программу могли удалить или переставить.
        Только под Windows: пути в библиотеке — пути Windows, а сеть (\\\\сервер)
        не трогаем вовсе, чтобы не ждать спящий диск.
        """
        if os.name != "nt":
            return

        def work():
            from ..platform.launcher import file_missing
            gone = {a["id"] for a in self.store.state()["apps"] if file_missing(a)}
            if gone != self.missing:
                self.missing = gone
                self.background_refresh(content_only=True)
        self.in_background(work)

    def set_missing(self, app_id: str, missing: bool):
        if missing == (app_id in self.missing):
            return
        self.missing = (self.missing | {app_id}) if missing else (self.missing - {app_id})

    def is_all_view(self):
        return self.view.is_all_view()

    def sections(self):
        return queries.build_sections(self.apps(), self.categories(), self.view.filter,
                                      self.view.sort, self.running)

    def _toggle_sidebar(self):
        if self._narrow_window():
            self._narrow_sidebar = not self._narrow_sidebar
        else:
            self.view.toggle_sidebar()
        self.refresh()

    def set_sidebar_open(self, value: bool):
        self.view.set_sidebar(bool(value))
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
        self.toast.dismiss_if(self.open_triage)
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

    def safe_refresh(self):
        self.background_refresh()


_KIND_GLYPHS = {"web": "language", "folder": "folder", "file": "description"}


def _source_glyph(source: str) -> str:
    return queries.SOURCES.get(source or "", {}).get("icon", "apps")
