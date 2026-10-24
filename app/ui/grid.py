from __future__ import annotations

import flet as ft

from ..core import queries
from ..core.hotkeys import free_quick_slot
from ..core.text import KINDS
from . import colors as C
from . import screens
from . import widgets as Wg
from .format import T
from .images import icon_image, is_launcher_art, raster_path

BADGE = 16
# Значок с подложкой выделения вокруг, строка под именем — точка «открыто».
ICON_PAD = 4
STATUS_H = 14
DOCK_PAD = 8
DOCK_SPACING = 4
TIP_WAIT_MS = 700


class GridView:
    def __init__(self, ui):
        self.ui = ui
        self._section_holders = {}
        self._piece_cache = {}
        self._used = set()
        # Значки по программам — чтобы подбросить их при запуске, как в Dock.
        self._icons = {}

    def build_content(self):
        self._used = set()
        try:
            return self._build_content()
        finally:
            self._section_holders = {k: v for k, v in self._section_holders.items()
                                     if k in self._used}
            self._piece_cache = {k: v for k, v in self._piece_cache.items()
                                 if k in self._used}
            self._icons = {k: v for k, v in self._icons.items()
                           if k in self.ui._tile_cache or ("qcard", k) in self._piece_cache}

    def _build_content(self):
        screen = self.ui.view.screen
        if screen == "add":
            return [screens.build_add_screen(self.ui)]
        if screen == "settings":
            return [screens.build_settings_screen(self.ui)]
        if screen == "triage":
            return [screens.build_triage_screen(self.ui)]
        if self.ui.view.active_set:
            rec = next((s for s in self.ui.sets() if s["id"] == self.ui.view.active_set), None)
            if rec is not None:
                return [screens.build_set_screen(self.ui, rec)]

        apps = self.ui.apps()
        if not apps and not self.ui.sets():
            self.ui._sel_id = None
            return [self._first_run()]

        sections = self.ui.sections()
        self.ui._sel_id = self.ui._selected_id(sections)

        controls = []
        # В режиме выбора ряд «Быстрый запуск» остаётся на месте, только
        # приглушается: когда он исчезал, все плитки поднимались на 146 px,
        # и следующий щелчок попадал не туда.
        if self.ui.is_all_view() and self.ui.setting("show_quick_row", True):
            controls += self._quick_row()

        if not sections or all(not s["apps"] for s in sections):
            controls.append(self._empty_section())
            return controls

        shown = [sec for sec in sections if sec["apps"]]
        single = len(shown) == 1
        for sec in shown:
            key = sec.get("cid") or sec["name"]
            # Один раздел в категории — это та же категория, что в заголовке
            # панели слева: второй заголовок рядом только повторял его.
            if not (single and self._title_says_it(sec)):
                controls.append(self._section_head(sec, key, collapsible=not single))
            if not single and sec.get("cid") and sec["cid"] in self.ui.view.collapsed \
                    and not self.ui.view.select_mode:
                continue
            controls.append(self._grid(sec["apps"], key) if self.ui.view.mode == "grid"
                            else self._list(sec["apps"], key))
        controls.append(self._gap_holder())
        return controls

    def _title_says_it(self, sec) -> bool:
        return (self.ui.view.filter == f"category:{sec.get('cid')}"
                and self.ui._show_sidebar())

    def _cached_piece(self, key, sig, builder):
        self._used.add(key)
        hit = self._piece_cache.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1]
        built = builder()
        self._piece_cache[key] = (sig, built)
        return built

    def _gap_holder(self):
        self._used.add(("gap",))
        holder = self._section_holders.get(("gap",))
        if holder is None:
            holder = ft.Container(height=self._bottom_gap())
            self._section_holders[("gap",)] = holder
        else:
            holder.height = self._bottom_gap()
        return holder

    def _bottom_gap(self) -> int:
        return 96 if self.ui.view.select_mode and self.ui.view.sel else 16

    def _empty_section(self):
        if self.ui.view.filter == "hidden":
            return self._empty("Ничего не скрыто",
                               "«Скрыть» в панели массовых операций убирает плитки "
                               "отсюда, не удаляя их.", None, None)
        return self._empty("Здесь пока пусто",
                           "Добавьте программы — или перетащите плитку на значок "
                           "категории слева.", "Добавить", self.ui.open_add)

    def _quick_row(self):
        cells = []
        for rec in self.ui.sets():
            if rec.get("quick"):
                accel = self.ui._set_accels.get(rec["id"])
                members = tuple(rec.get("apps", [])[:4])
                icons = tuple((a.get("icon"), a.get("icon_fit")) for a in self.ui.apps()
                              if a["id"] in members)
                sig = (self.ui._tile_epoch, rec.get("name"), accel, members, icons)
                cells.append(self._cached_piece(("qset", rec["id"]), sig,
                                                lambda r=rec: self._dock_set(r)))
        for app in queries.hotkey_apps(queries.visible(self.ui.apps()), self.ui._accels):
            accel = self.ui._accels.get(app["id"])
            cat = self.ui.cat_of(app)
            running = app["id"] in self.ui.running
            missing = app["id"] in self.ui.missing
            sig = (self.ui._tile_epoch, app.get("name"), app.get("icon"), app.get("icon_fit"),
                   app.get("category_id"), app.get("source"), accel, running, missing,
                   (cat.get("color"), cat.get("icon")) if cat else None)
            cells.append(self._cached_piece(
                ("qcard", app["id"]), sig,
                lambda a=app, ac=accel, r=running, m=missing: self._dock_app(a, ac, r, m)))
        free = free_quick_slot(self.ui.apps())
        if free and (not cells or self._fits_in_row(len(cells))):
            cells.append(self._cached_piece(("qempty",), (self.ui._tile_epoch, free),
                                            lambda f=free: self._dock_empty(f)))

        head = self._cached_piece(("qhead",), self.ui._tile_epoch, self._build_quick_head)

        self._used.add(("qrow",))
        holder = self._section_holders.get(("qrow",))
        if holder is None:
            # Полка в духе Dock: значки на общей подложке, без карточек.
            shelf = ft.Container(
                ft.Row(cells, spacing=DOCK_SPACING, wrap=True, run_spacing=DOCK_SPACING),
                bgcolor=C.PANEL, border=ft.Border.all(1, C.LINE),
                border_radius=C.R_XL + 2, padding=ft.Padding.all(DOCK_PAD))
            holder = ft.Container(shelf, padding=ft.Padding.only(bottom=24),
                                  animate_opacity=Wg.anim(C.ANIM_FAST))
            self._section_holders[("qrow",)] = holder
        else:
            holder.content.content.controls = cells
        dim = self.ui.view.select_mode
        holder.opacity = 0.35 if dim else 1.0
        holder.disabled = dim
        holder.tooltip = "В режиме выбора быстрый запуск отдыхает" if dim else None
        return [head, holder]

    def _build_quick_head(self):
        return ft.Container(Wg.caps("Быстрый запуск"),
                            padding=ft.Padding.only(left=4, top=4, bottom=8))

    def _fits_in_row(self, count: int) -> bool:
        avail = self.ui._content_width() - 48 - 2 * DOCK_PAD - 2
        per_row = max(1, int((avail + DOCK_SPACING) // (C.DOCK_CELL + DOCK_SPACING)))
        return count % per_row != 0

    def _dock_cell(self, art, label, tooltip, on_click, running=False, label_color=None):
        """Ячейка полки: значок, подпись, точка «открыто». Под курсором значок
        увеличивается и приподнимается, как в Dock."""
        holder = ft.Container(art, animate_scale=Wg.anim(C.ANIM_HOVER, spring=True))
        cell = ft.Container(
            ft.Column([holder, ft.Container(height=6),
                       T(label, size=C.FS_CAPTION, weight=ft.FontWeight.W_500,
                         color=label_color or C.TEXT_2, max_lines=1,
                         overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER,
                         width=C.DOCK_CELL - 8),
                       ft.Container(height=3), Wg.dock_dot(running)],
                      spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=C.DOCK_CELL, padding=ft.Padding.only(top=4, bottom=2),
            tooltip=tooltip, on_click=lambda e: self._quick_launch(on_click))

        def on_hover(e):
            # Растёт от нижнего края, как значки Dock под курсором.
            holder.scale = ft.Scale(C.DOCK_SCALE if Wg.entered(e) else 1.0,
                                    alignment=ft.Alignment.BOTTOM_CENTER)
            Wg.safe_update(holder)
        cell.on_hover = on_hover
        return cell, holder

    def _dock_app(self, app, accel, running=False, missing=False):
        size = C.DOCK_ICON
        icon = self.ui.icon_slot(app, size, Wg.squircle(size), glyph=round(size * 0.5))
        if missing:
            icon = Wg.with_badge(icon, size, Wg.missing_badge(BADGE, C.PANEL), BADGE)
        tip = " · ".join(p for p in (app["name"], accel,
                                     "файл не найден" if missing else None) if p)
        cell, holder = self._dock_cell(icon, app["name"], tip,
                                       lambda i=app["id"]: self.ui._launch(i), running)
        self._icons.setdefault(app["id"], {})["dock"] = holder
        return ft.GestureDetector(
            cell, on_secondary_tap_down=lambda e, ap=app: self.ui.context_menus.app_menu(ap, e))

    def _quick_launch(self, run):
        # Ячейки собираются один раз и переживают вход в режим выбора, где
        # полка приглушена: щелчок по ней тогда ничего не запускает.
        if not self.ui.view.select_mode:
            run()

    def _dock_set(self, rec):
        size = C.DOCK_ICON
        cell, _holder = self._dock_cell(
            self.ui.set_mosaic(rec, size, Wg.squircle(size)), rec["name"],
            f"Набор «{rec['name']}»",
            lambda sid=rec["id"]: self.ui.set_ops.launch_set(sid))
        return ft.GestureDetector(
            cell, on_secondary_tap_down=lambda e, r=rec: self.ui.context_menus.set_menu(r, e))

    def _dock_empty(self, slot):
        size = C.DOCK_ICON
        plate = ft.Container(ft.Icon(ft.Icons.ADD_ROUNDED, size=20, color=C.FAINT),
                             width=size, height=size, border_radius=Wg.squircle(size),
                             border=ft.Border.all(1, C.BORDER), alignment=ft.Alignment.CENTER)
        cell, _holder = self._dock_cell(
            plate, f"Ctrl+{slot}", f"Закрепите приложение — оно встанет на Ctrl+{slot}",
            self.ui._toast_hint_quick, label_color=C.FAINT)
        return cell

    def _section_head(self, sec, key, collapsible=True):
        cat = next((c for c in self.ui.categories() if c["id"] == sec.get("cid")), None)
        collapsible = collapsible and bool(sec.get("cid")) and not self.ui.view.select_mode
        collapsed = collapsible and sec["cid"] in self.ui.view.collapsed
        sig = (self.ui._tile_epoch, sec["name"], collapsed, collapsible, len(sec["apps"]),
               (cat.get("name"), cat.get("icon"), cat.get("color"), cat.get("image"))
               if cat else None)
        return self._cached_piece(
            ("head", key), sig,
            lambda: self._build_section_head(sec, cat, collapsed, collapsible))

    def _build_section_head(self, sec, cat, collapsed, collapsible):
        """Заголовок раздела сворачивает его щелчком по названию.

        Стрелка стоит слева от названия: значок 14 px у правого края окна, в
        тысяче пикселей от «Работы», не находили. Линии через всё окно нет —
        разделы отделяет воздух.
        """
        row = []
        if collapsible:
            row.append(ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED if collapsed
                               else ft.Icons.EXPAND_MORE_ROUNDED, size=18, color=C.FAINT))
        row += [Wg.cat_glyph(cat, size=16) if cat
                else ft.Container(width=8, height=8, border_radius=4, bgcolor=C.FAINT),
                T(sec["name"], size=C.FS_TITLE, weight=ft.FontWeight.W_600, color=C.TEXT),
                T(str(len(sec["apps"])), size=C.FS_SMALL, color=C.FAINT)]
        label = ft.Container(
            ft.Row(row, spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=4, horizontal=6), border_radius=C.R,
            tooltip=("Развернуть" if collapsed else "Свернуть") if collapsible else None,
            on_click=(lambda e, cid=sec["cid"]: self.ui._toggle_section(cid))
            if collapsible else None)
        if collapsible:
            Wg.hoverable(label, None, C.CARD)
        head = ft.Container(ft.Row([label]), padding=ft.Padding.only(bottom=6))
        if not cat:
            return head
        return ft.GestureDetector(
            head,
            on_secondary_tap_down=lambda e, c=cat: self.ui.context_menus.category_menu(c, e))

    def _use_poster(self, a):
        return bool(self.ui._settings.get("game_posters", True)
                    and is_launcher_art(a) and raster_path(a.get("poster")))

    def _grid(self, apps, key):
        ids = [a["id"] for a in apps]
        tiles = [self._draggable_tile(a, ids) for a in apps]
        self._used.add(("grid", key))
        holder = self._section_holders.get(("grid", key))
        if holder is None:
            row = ft.Row(tiles, wrap=True, spacing=C.TILE_GAP, run_spacing=C.TILE_GAP,
                         vertical_alignment=ft.CrossAxisAlignment.START)
            holder = ft.Container(row, padding=ft.Padding.only(bottom=28))
            self._section_holders[("grid", key)] = holder
        else:
            holder.content.controls = tiles
        return holder

    def _tile_signature(self, a, running, selected, picked, cat):
        return (self.ui._tile_epoch, running, selected, picked,
                a["id"] in self.ui.missing,
                self.ui._accels.get(a["id"]),
                tuple(self.ui.view.sel) if picked else None,
                self.ui.window_count(a) if running else 0,
                a.get("name"), a.get("path"), a.get("sub"), a.get("source"), a.get("kind"),
                a.get("icon"), a.get("icon_fit"), a.get("poster"),
                a.get("category_id"), bool(a.get("favorite")),
                bool(a.get("hidden")), bool(a.get("quick")),
                a.get("last_launched"),
                (cat.get("name"), cat.get("icon"), cat.get("color"), cat.get("image"))
                if cat else None)

    def _draggable_tile(self, a, ids):
        app_id = a["id"]
        running = app_id in self.ui.running
        picked = app_id in self.ui.view.sel
        selected = picked or (not self.ui.view.select_mode and app_id == self.ui._sel_id)
        cat = self.ui.cat_of(a)
        sig = self._tile_signature(a, running, selected, picked, cat)
        self.ui._tiles_used.add(app_id)
        hit = self.ui._tile_cache.get(app_id)
        if hit is not None and hit[0] == sig:
            hit[2]["ids"] = ids
            self.ui._tile_cache.move_to_end(app_id)
            return hit[1]
        compact = self.ui._settings.get("tile_size") == "compact"
        box = {}
        ids_box = {"ids": ids}
        base = (self._build_poster_tile(a, compact, running, selected, ids_box, box)
                if self._use_poster(a) else
                self._build_tile(a, compact, running, selected, ids_box, box))
        draggable = ft.Draggable(group="apps", content=base,
                                 data={"ids": self.ui._drag_ids(app_id)})
        tile = ft.DragTarget(
            group="apps", content=draggable,
            on_accept=lambda e, i=app_id, b=box, ib=ids_box: self._accept_reorder(e, i, ib["ids"], b),
            on_will_accept=lambda e, b=box: self._mark_reorder(b, True),
            on_leave=lambda e, b=box: self._mark_reorder(b, False))
        self.ui._tile_cache[app_id] = (sig, tile, ids_box)
        self.ui._tile_cache.move_to_end(app_id)
        return tile

    def _mark_reorder(self, box, on: bool):
        ctl = box.get("tile")
        if ctl is None:
            return
        ctl.border = ft.Border.all(2, self.ui._accent()) if on else box.get("border")
        Wg.safe_update(ctl)

    def _accept_reorder(self, e, target_id, section_ids, box):
        self._mark_reorder(box, False)
        payload = Wg.dragged_data(e)
        if not isinstance(payload, dict) or not payload.get("ids"):
            return
        self.ui._reorder_apps(section_ids, list(payload["ids"]), target_id)

    def bounce(self, app_id):
        """Значок запущенной программы подпрыгивает — в сетке и на полке."""
        for holder in self._icons.get(app_id, {}).values():
            Wg.hop(holder)

    def _tile_meta(self, app, running: bool) -> tuple[str, str, bool]:
        """Пояснение к программе: (текст, цвет, моноширинный ли)."""
        if self.ui.view.select_mode:
            return "", C.MUTED_2, False
        if app["id"] in self.ui.missing:
            return "файл не найден", C.WARN_TEXT, False
        if running:
            return self.ui.running_note(app), C.GREEN_TEXT, False
        accel = self.ui._accels.get(app["id"])
        if accel:
            return accel, C.MUTED_2, True
        return KINDS.get(app.get("kind") or "", ""), C.MUTED_2, False

    def _tile_tip(self, app, running: bool, height: int) -> ft.Tooltip | None:
        """Подсказка у значка: полное имя и то, что под значком не поместилось.

        С задержкой, как в Finder: пока курсор просто идёт по сетке, подписи
        не закрываются всплывающими подсказками. И под ячейкой, а не на ней:
        иначе она ложилась ровно на подпись.
        """
        meta, _color, _mono = self._tile_meta(app, running)
        name = app["name"]
        text = f"{name} · {meta}" if meta else (name if len(name) > 14 else None)
        if not text:
            return None
        return ft.Tooltip(message=text, wait_duration=TIP_WAIT_MS, prefer_below=True,
                          vertical_offset=height / 2 + 4)

    def _select_box(self, picked):
        accent = self.ui._accent()
        return ft.Container(
            ft.Icon(ft.Icons.CHECK_ROUNDED, size=14, color=C.on_color(accent)) if picked else None,
            width=20, height=20, border_radius=10,
            bgcolor=accent if picked else C.with_alpha(C.BG, 0.85),
            border=None if picked else ft.Border.all(1.5, C.FAINT),
            shadow=ft.BoxShadow(blur_radius=4, offset=ft.Offset(0, 1),
                                color=C.with_alpha(C.INK, 0.25)),
            alignment=ft.Alignment.CENTER, animate=Wg.anim(C.ANIM_FAST))

    def _more_button(self, app, size=24, visible=False, bgcolor=None):
        """«···» у значка: то же меню, что правый щелчок. Видна под курсором.

        Нажатие, а не щелчок контейнера: у нажатия есть координаты, и меню
        встаёт у самой кнопки, а не посередине окна. Плитку под ней нажатие
        не запускает — его забирает кнопка.
        """
        return ft.GestureDetector(
            ft.Container(ft.Icon(ft.Icons.MORE_HORIZ_ROUNDED, size=16, color=C.TEXT_2),
                         width=size, height=size, border_radius=size / 2,
                         bgcolor=bgcolor or C.RAISED, alignment=ft.Alignment.CENTER,
                         tooltip="Меню"),
            mouse_cursor=ft.MouseCursor.CLICK, visible=visible,
            on_tap_down=lambda e, ap=app: self.ui.context_menus.app_menu(ap, e))

    def _corner_marks(self, a, more):
        marks = []
        if self.ui.view.select_mode:
            marks.append(ft.Container(self._select_box(a["id"] in self.ui.view.sel),
                                      left=10, top=4))
            return marks
        if a.get("favorite"):
            marks.append(ft.Container(ft.Icon(ft.Icons.STAR_ROUNDED, size=15, color=C.STAR),
                                      left=8, top=6, tooltip="В избранном"))
        marks.append(ft.Container(more, right=6, top=4))
        return marks

    def _label(self, text, width, selected, size=C.FS_SMALL):
        """Имя под значком. У выбранного — плашка акцента по ширине имени, как в Finder."""
        accent = self.ui._accent()
        pill = ft.Container(
            T(text, size=size, weight=ft.FontWeight.W_500,
              color=C.on_color(accent) if selected else C.TEXT, max_lines=1,
              overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER),
            bgcolor=accent if selected else None, border_radius=C.R_SMALL - 1,
            padding=ft.Padding.symmetric(vertical=1, horizontal=6),
            expand=True, expand_loose=True)
        return ft.Container(ft.Row([pill], alignment=ft.MainAxisAlignment.CENTER),
                            width=width)

    def _status_line(self, a, running, width):
        """Под именем: точка «открыто», как в Dock, или «файл не найден»."""
        if a["id"] in self.ui.missing and not self.ui.view.select_mode:
            return ft.Container(T("файл не найден", size=C.FS_CAPTION, color=C.WARN_TEXT,
                                  max_lines=1, text_align=ft.TextAlign.CENTER, width=width),
                                height=STATUS_H, alignment=ft.Alignment.CENTER)
        return ft.Container(Wg.dock_dot(running), height=STATUS_H,
                            alignment=ft.Alignment.CENTER)

    def _build_tile(self, a, compact, running, selected, ids_box, box=None):
        width = C.TILE_W_COMPACT if compact else C.TILE_W
        height = C.TILE_H_COMPACT if compact else C.TILE_H
        size = C.TILE_ICON_COMPACT if compact else C.TILE_ICON
        missing = a["id"] in self.ui.missing
        radius = Wg.squircle(size)
        icon = self.ui.icon_slot(a, size, radius, glyph=round(size * 0.5))
        if missing:
            icon = Wg.with_badge(icon, size, Wg.missing_badge(BADGE, C.BG), BADGE)
        # Выбранный значок — на серой подложке, имя — на плашке акцента.
        art = ft.Container(icon, padding=ft.Padding.all(ICON_PAD),
                           border_radius=radius + ICON_PAD,
                           bgcolor=C.RAISED if selected else None,
                           animate=Wg.anim(C.ANIM_FAST))
        self._icons.setdefault(a["id"], {})["grid"] = art
        body = ft.Column([
            art,
            ft.Container(height=4 if compact else 6),
            self._label(a["name"], width - 8, selected),
            self._status_line(a, running, width - 8),
        ], spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        more = self._more_button(a)
        border = ft.Border.all(2, C.TRANSPARENT)
        tile = ft.Container(
            ft.Stack([ft.Container(body, left=0, right=0, top=4 if compact else 6,
                                   alignment=ft.Alignment.TOP_CENTER)]
                     + self._corner_marks(a, more)),
            width=width, height=height, border=border, border_radius=C.R_LARGE,
            tooltip=self._tile_tip(a, running, height), animate=Wg.anim(C.ANIM_TILE))
        if box is not None:
            box["tile"] = tile
            box["border"] = border
        hover, down, up = Wg.lift(art)

        def on_hover(e):
            hot = Wg.entered(e)
            more.visible = hot and not self.ui.view.select_mode
            tile.bgcolor = C.CARD if hot and not selected else None
            Wg.safe_update(tile)
            hover(hot)
        tile.on_hover = on_hover
        return self._tile_gestures(tile, a, ids_box, down, up)

    def _build_poster_tile(self, a, compact, running, selected, ids_box, box=None):
        width = C.POSTER_W_COMPACT if compact else C.POSTER_W
        height = C.POSTER_H_COMPACT if compact else C.POSTER_H
        poster = icon_image(a.get("poster"), width=width, height=height,
                            fit=ft.BoxFit.COVER) or ft.Container()
        art = ft.Container(
            poster, width=width, height=height, bgcolor=C.CARD, border_radius=C.R_LARGE,
            border=ft.Border.all(3, self.ui._accent() if selected else C.TRANSPARENT),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(blur_radius=12, offset=ft.Offset(0, 4),
                                color=C.with_alpha(C.INK, 0.3)),
            animate=Wg.anim(C.ANIM_FAST))
        self._icons.setdefault(a["id"], {})["grid"] = art
        more = self._more_button(a)
        body = ft.Column([art, ft.Container(height=6),
                          self._label(a["name"], width, selected),
                          self._status_line(a, running, width)],
                         spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        border = ft.Border.all(2, C.TRANSPARENT)
        cell_h = height + 4 + 6 + 18 + STATUS_H + 6
        tile = ft.Container(
            ft.Stack([ft.Container(body, left=0, right=0, top=4)]
                     + self._corner_marks(a, more)),
            width=width + 8, height=cell_h, border=border, border_radius=C.R_LARGE,
            tooltip=self._tile_tip(a, running, cell_h), animate=Wg.anim(C.ANIM_TILE))
        if box is not None:
            box["tile"] = tile
            box["border"] = border
        hover, down, up = Wg.lift(art, hover=1.04)

        def on_hover(e):
            hot = Wg.entered(e)
            more.visible = hot and not self.ui.view.select_mode
            Wg.safe_update(more)
            hover(hot)
        tile.on_hover = on_hover
        return self._tile_gestures(tile, a, ids_box, down, up)

    def _tile_gestures(self, tile, a, ids_box, down=None, up=None):
        # Запуск по отпусканию, а не по нажатию: нажатие ещё может оказаться
        # началом перетаскивания плитки, и тогда программа запускаться не
        # должна. Нажатие только утапливает значок.
        return ft.GestureDetector(
            tile, mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=lambda e, i=a["id"], ib=ids_box: self.ui._tile_tap(i, ib["ids"], e),
            on_tap_down=down, on_tap_up=up, on_tap_cancel=up,
            on_secondary_tap_down=lambda e, ap=a: self.ui.context_menus.app_menu(ap, e))

    def _list(self, apps, key):
        ids = [a["id"] for a in apps]
        rows = [self._list_row(a, ids) for a in apps]
        self._used.add(("list", key))
        holder = self._section_holders.get(("list", key))
        if holder is None:
            col = ft.Column(rows, spacing=2)
            holder = ft.Container(col, padding=ft.Padding.only(bottom=24))
            self._section_holders[("list", key)] = holder
        else:
            holder.content.controls = rows
        return holder

    def _list_row(self, a, ids):
        """Строка списка как в Finder: без карточки, выбранная — залита акцентом."""
        running = a["id"] in self.ui.running
        picked = a["id"] in self.ui.view.sel
        selected = picked or (not self.ui.view.select_mode and a["id"] == self.ui._sel_id)
        cat = self.ui.cat_of(a)
        sig = self._tile_signature(a, running, selected, picked, cat)
        self.ui._tiles_used.add(a["id"])
        hit = self.ui._tile_cache.get(a["id"])
        if hit is not None and hit[0] == sig:
            hit[2]["ids"] = ids
            self.ui._tile_cache.move_to_end(a["id"])
            return hit[1]
        ids_box = {"ids": ids}
        missing = a["id"] in self.ui.missing
        accent = self.ui._accent()
        ink = C.on_color(accent) if selected else None
        meta, meta_color, mono = self._tile_meta(a, running)
        controls = []
        if self.ui.view.select_mode:
            controls.append(self._select_box(picked))
        icon = self.ui.icon_slot(a, 28, Wg.squircle(28), glyph=15)
        if missing:
            icon = Wg.with_badge(icon, 28, Wg.missing_badge(12, accent if selected else C.BG),
                                 12)
        controls += [ft.Container(Wg.dock_dot(running), width=6), icon,
                     T(a["name"], size=C.FS_BODY, weight=ft.FontWeight.W_500,
                       color=ink or C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                       expand=True)]
        if meta:
            controls.append(T(meta, size=C.FS_SMALL,
                              color=C.with_alpha(ink, 0.85) if ink else meta_color,
                              font_family="monospace" if mono else None, max_lines=1))
        if a.get("favorite"):
            controls.append(ft.Icon(ft.Icons.STAR_ROUNDED, size=16,
                                    color=ink or C.STAR))
        if not self.ui.view.select_mode:
            controls.append(self._more_button(a, size=26, visible=True,
                                              bgcolor=C.TRANSPARENT))
        row = ft.Container(ft.Row(controls, spacing=10,
                                  vertical_alignment=ft.CrossAxisAlignment.CENTER),
                           height=40, padding=ft.Padding.symmetric(horizontal=8),
                           border_radius=C.R, border=ft.Border.all(2, C.TRANSPARENT),
                           bgcolor=accent if selected else None,
                           animate=Wg.anim(C.ANIM_FAST))
        if not selected:
            Wg.hoverable(row, None, C.CARD)
        built = ft.GestureDetector(
            row,
            on_tap=lambda e, i=a["id"], ib=ids_box: self.ui._tile_tap(i, ib["ids"], e),
            on_secondary_tap_down=lambda e, ap=a: self.ui.context_menus.app_menu(ap, e))
        self.ui._tile_cache[a["id"]] = (sig, built, ids_box)
        self.ui._tile_cache.move_to_end(a["id"])
        return built

    def _first_run(self):
        scan = self.ui.scan
        if scan.wants_suggestions() and scan.scanning():
            return ft.Container(
                ft.Column([Wg.spinner(32),
                           T("Смотрю, что установлено", size=C.FS_TITLE,
                             weight=ft.FontWeight.W_600, color=C.TEXT),
                           T("Это несколько секунд. Потом предложу то, чем вы, похоже, "
                             "уже пользуетесь.", size=C.FS_BODY, color=C.MUTED,
                             text_align=ft.TextAlign.CENTER, width=380)],
                          spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=80, bottom=40))
        found = scan.suggestions()
        if not found:
            return self._empty("Библиотека пуста",
                               "Centurio посмотрит, что установлено, и предложит отметить "
                               "нужное. Можно и указать файл вручную.",
                               "Найти и добавить", self.ui.open_add)
        picked = sum(1 for s in found if s["on"])
        return ft.Container(
            ft.Column([
                T("Похоже, вы этим пользуетесь", size=C.FS_HEADING, weight=ft.FontWeight.W_600,
                  color=C.TEXT),
                ft.Container(height=8),
                T("Эти программы закреплены на панели задач, открыты сейчас, стоят в "
                  "автозагрузке или на рабочем столе. Снимите отметку с лишнего.",
                  size=C.FS_BODY, color=C.MUTED, text_align=ft.TextAlign.CENTER, width=440),
                ft.Container(height=24),
                ft.Container(ft.Row([self._suggestion_card(s) for s in found], wrap=True,
                                    spacing=8, run_spacing=8,
                                    alignment=ft.MainAxisAlignment.CENTER), width=720),
                ft.Container(height=24),
                ft.Row([Wg.primary_btn(f"Добавить {picked}" if picked else "Добавить",
                                       scan.add_suggestions, self.ui._accent(), ft.Icons.ADD_ROUNDED),
                        Wg.secondary_btn("Всё найденное", scan.review_suggestions,
                                         ft.Icons.SEARCH_ROUNDED)],
                       spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=12),
                Wg.quiet_btn("Не сейчас", scan.dismiss_suggestions, color=C.MUTED),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=56, bottom=40))

    def _suggestion_card(self, s):
        on = s["on"]
        accent = self.ui._accent()
        return ft.Container(
            ft.Row([self.ui.icon_slot(s["item"], 32, 8, glyph=16),
                    ft.Column([T(s["item"].get("name") or "", size=C.FS_BODY,
                                 weight=ft.FontWeight.W_500, color=C.TEXT, max_lines=1,
                                 overflow=ft.TextOverflow.ELLIPSIS),
                               T(s["hint"], size=C.FS_SMALL, color=C.MUTED_2, max_lines=1)],
                              spacing=2, tight=True, expand=True),
                    ft.Icon(ft.Icons.CHECK_BOX_ROUNDED if on else ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                            size=18, color=accent if on else C.FAINT)],
                   spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=232, height=56, padding=ft.Padding.symmetric(horizontal=12),
            border_radius=C.R, bgcolor=C.CARD if on else None,
            border=ft.Border.all(1, C.TRANSPARENT if on else C.LINE),
            opacity=1 if on else 0.6,
            on_click=lambda e, k=s["key"]: self.ui.scan.toggle_suggestion(k))

    def _empty(self, title, text, btn_label, on_click):
        controls = [
            T(title, size=C.FS_HEADING, weight=ft.FontWeight.W_600, color=C.TEXT),
            ft.Container(height=8),
            T(text, size=C.FS_BODY, color=C.MUTED, text_align=ft.TextAlign.CENTER, width=380),
        ]
        if btn_label:
            # В пустом состоянии «Добавить» — единственное, что тут можно
            # сделать, поэтому кнопка главная, залитая.
            controls += [ft.Container(height=24),
                         ft.Row([Wg.primary_btn(btn_label, on_click, self.ui._accent(),
                                                ft.Icons.ADD_ROUNDED)],
                                alignment=ft.MainAxisAlignment.CENTER)]
        return ft.Container(
            ft.Column(controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=80, bottom=40))
