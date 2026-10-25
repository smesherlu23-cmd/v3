from __future__ import annotations

import flet as ft

from ..core.text import short_ago, time_ago
from . import colors as C
from . import widgets as Wg
from .format import T, as_icon

PAD = 20


def _short_path(path: str) -> str:
    if not path:
        return ""
    if "://" in path:
        return path
    parts = str(path).replace("/", "\\").split("\\")
    tail = "\\".join(parts[-2:]) if len(parts) > 2 else "\\".join(parts)
    return f"…\\{tail}" if len(parts) > 2 else tail


def _field(view, key, value, hint, on_commit, mono=False, tooltip=None):
    return Wg.track_typing(ft.TextField(
        value=value, hint_text=hint, height=34, text_size=C.FS_BODY if not mono else C.FS_SMALL,
        color=C.TEXT, bgcolor=C.CARD, border_color=C.LINE, focused_border_color=C.BORDER,
        border_radius=C.R, cursor_color=C.TEXT, tooltip=tooltip,
        content_padding=ft.Padding.symmetric(horizontal=12),
        # Подсказка — обычным шрифтом: моноширинный растягивал «не заданы»
        # в «не  заданы». Моноширинный — только для набранного значения.
        hint_style=ft.TextStyle(color=C.MUTED_2, size=C.FS_SMALL, font_family="Inter"),
        text_style=ft.TextStyle(font_family="mono") if mono else None, expand=True,
        on_blur=lambda e: on_commit(e.control.value),
        on_submit=lambda e: on_commit(e.control.value)), view, key)


class InspectorPanel:
    """Свойства программы — панель поверх сетки, справа.

    Открывается пунктом «Свойства…» в меню плитки (или стрелками и Enter в
    меню), закрывается Esc или крестиком.
    """

    def __init__(self, ui):
        self.ui = ui
        self.name_field = None

    def focus_name(self):
        if self.name_field is not None:
            self.ui._focus(self.name_field)

    def build_inspector(self):
        app = next((a for a in self.ui.apps() if a["id"] == self.ui.view.inspector), None)
        if app is None:
            self.name_field = None
            return None
        running = app["id"] in self.ui.running
        missing = app["id"] in self.ui.missing

        if missing:
            status = ft.Row([ft.Icon(ft.Icons.PRIORITY_HIGH_ROUNDED, size=14, color=C.WARN),
                             T("файл не найден", size=C.FS_SMALL, color=C.WARN_TEXT)],
                            spacing=4, tight=True)
        elif running:
            status = ft.Row([Wg.dot(8), T(self.ui.running_note(app), size=C.FS_SMALL,
                                          color=C.GREEN_TEXT)], spacing=8, tight=True)
        else:
            status = T(short_ago(app.get("last_launched")) or "ещё не открывали",
                       size=C.FS_SMALL, color=C.MUTED_2)
        name = Wg.track_typing(ft.TextField(
            value=app["name"], border=ft.NoInputBorder(), filled=False, dense=True,
            text_size=C.FS_TITLE, color=C.TEXT, cursor_color=C.TEXT,
            content_padding=ft.Padding.symmetric(vertical=0, horizontal=0),
            tooltip="Переименовать",
            text_style=ft.TextStyle(weight=ft.FontWeight.BOLD, font_family="Inter Bold"),
            on_blur=lambda e: self.ui.rename_app(app["id"], e.control.value),
            on_submit=lambda e: self.ui.rename_app(app["id"], e.control.value)),
            self.ui.view, "app_name")
        self.name_field = name
        icon = ft.Container(self.ui.icon_slot(app, 48, Wg.squircle(48), glyph=24),
                            tooltip="Сменить значок",
                            on_click=lambda e: self.ui.context_menus.app_icon_menu(app, e))
        fav = bool(app.get("favorite"))
        header = ft.Container(
            ft.Row([icon,
                    ft.Column([name, status], spacing=4, expand=True, tight=True),
                    Wg.icon_btn(ft.Icons.STAR_ROUNDED if fav else ft.Icons.STAR_OUTLINE_ROUNDED,
                                "Убрать из избранного" if fav else "В избранное",
                                lambda: self.ui._toggle_fav(app["id"]),
                                color=C.STAR if fav else C.MUTED),
                    Wg.icon_btn(ft.Icons.CLOSE_ROUNDED, "Закрыть панель",
                                self.ui._close_inspector)],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=ft.Padding.only(left=PAD, top=PAD, right=12, bottom=16))

        def square(icon_name, tooltip, handler):
            btn = ft.Container(ft.Icon(as_icon(icon_name), size=16, color=C.TEXT_2),
                               width=32, height=32, border_radius=C.R,
                               alignment=ft.Alignment.CENTER,
                               tooltip=tooltip, on_click=lambda e: handler())
            return Wg.hoverable(btn, C.CARD, C.RAISED)

        kind = app.get("kind")
        if missing:
            primary = Wg.primary_btn("Найти файл…", lambda: self.ui._relocate(app["id"]),
                                     self.ui._accent(), ft.Icons.SEARCH_ROUNDED, expand=True)
        else:
            primary = Wg.primary_btn(
                "Переключиться" if running else ("Открыть" if kind else "Запустить"),
                lambda: self.ui._launch(app["id"]), self.ui._accent(),
                ft.Icons.SYNC_ALT_ROUNDED if running
                else (ft.Icons.OPEN_IN_NEW_ROUNDED if kind else ft.Icons.PLAY_ARROW_ROUNDED),
                expand=True)
        buttons = [primary]
        if kind != "web":
            buttons.append(square(ft.Icons.FOLDER_OPEN_ROUNDED, "Показать в папке",
                                  lambda: self.ui._show_in_folder(app["id"])))
        if not kind:
            buttons.append(square(ft.Icons.MORE_HORIZ_ROUNDED, "Ещё способы запуска",
                                  lambda: self.ui.context_menus.launch_more_menu(app, None)))
        actions = ft.Container(ft.Row(buttons, spacing=8), padding=ft.Padding.symmetric(horizontal=PAD))

        cat = self.ui.cat_of(app)
        props = [
            self._insp_row("Категория", self._cat_selector(app, cat)),
            self._insp_row("Быстрый запуск",
                           Wg.toggle(bool(app.get("quick")),
                                     lambda v: self.ui._toggle_quick(app["id"], v),
                                     self.ui._accent()),
                           sub=self._quick_sub(app)),
            self._stacked("В наборах", self._set_chips(app)),
            self._stacked("Другие имена", self._aliases_field(app),
                          sub="Для поиска, через запятую: «пс, фотошоп»"),
            Wg.divider(),
            self._insp_tech(app),
        ]
        placement = ft.Container(ft.Column(props, spacing=16),
                                 padding=ft.Padding.only(left=PAD, top=24, right=PAD))

        footer = ft.Container(
            ft.Row([ft.Container(expand=True),
                    Wg.secondary_btn("Убрать из библиотеки",
                                     lambda: self.ui._remove_apps([app["id"]]),
                                     ft.Icons.DELETE_OUTLINE_ROUNDED, danger=True, height=30)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=12, horizontal=PAD),
            border=ft.Border.only(top=ft.BorderSide(1, C.LINE)))

        return ft.Container(
            ft.Column([header, actions,
                       ft.Column([placement,
                                  ft.Container() if kind else self._insp_advanced(app),
                                  ft.Container(height=16)],
                                 spacing=0, expand=True, scroll=ft.ScrollMode.AUTO),
                       footer], spacing=0, expand=True),
            # Плавающая стеклянная панель, как инспектор в приложениях macOS.
            bgcolor=C.GLASS, border=ft.Border.all(1, C.EDGE), border_radius=C.R_XL,
            blur=ft.Blur(30, 30), clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16), color=C.SHADOW),
            expand=True)

    def _insp_row(self, label, control, sub=None):
        left = [T(label, size=C.FS_BODY, color=C.TEXT_2)]
        if sub:
            left.append(T(sub, size=C.FS_SMALL, color=C.MUTED_2))
        return ft.Row([ft.Column(left, spacing=2, tight=True, expand=True), control],
                      spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _stacked(self, label, control, sub=None):
        """Подпись над полем: в узкой колонке слева «Другие имена» шли в две строки."""
        head = [T(label, size=C.FS_BODY, color=C.TEXT_2)]
        if sub:
            head.append(T(sub, size=C.FS_SMALL, color=C.MUTED_2))
        return ft.Column([ft.Column(head, spacing=2, tight=True), ft.Row([control])],
                         spacing=8, tight=True)

    def _insp_tech(self, app):
        lines = []
        if app.get("path"):
            lines.append(T(app["path"], size=C.FS_SMALL, color=C.MUTED_2, selectable=True))
        stats = []
        if app.get("launch_count"):
            stats.append(T(f"Запусков: {app['launch_count']}", size=C.FS_SMALL, color=C.MUTED))
        ago = time_ago(app.get("last_launched"))
        if ago:
            stats.append(T(f"Последний: {ago}", size=C.FS_SMALL, color=C.MUTED))
        if stats:
            lines.append(ft.Row(stats, spacing=16, wrap=True, run_spacing=4))
        if not lines:
            return ft.Container(height=0)
        return ft.Column(lines, spacing=8, tight=True)

    def _aliases_field(self, app):
        return _field(self.ui.view, "app_aliases", ", ".join(app.get("aliases") or []),
                      "сокращения", lambda value: self.ui.set_aliases(app["id"], value),
                      tooltip="Например, «пс, фотошоп» для Adobe Photoshop")

    def _set_chips(self, app):
        members = [rec for rec in self.ui.sets() if app["id"] in rec.get("apps", [])]
        chips = []
        for rec in members:
            chip = ft.Container(
                ft.Row([self.ui.set_mosaic(rec, 18, 4),
                        T(rec["name"], size=C.FS_SMALL, color=C.TEXT_2, max_lines=1,
                          overflow=ft.TextOverflow.ELLIPSIS)], spacing=8, tight=True),
                height=28, border_radius=14, bgcolor=C.CARD,
                padding=ft.Padding.only(left=6, right=12),
                on_click=lambda e, sid=rec["id"]: self.ui._open_set(sid))
            chips.append(Wg.hoverable(chip, C.CARD, C.RAISED))
        add = ft.Container(
            ft.Row([ft.Icon(ft.Icons.ADD_ROUNDED, size=14, color=C.MUTED),
                    T("Ещё" if members else "В набор", size=C.FS_SMALL, color=C.MUTED)],
                   spacing=4, tight=True),
            height=28, border_radius=14, border=ft.Border.all(1, C.BORDER),
            padding=ft.Padding.symmetric(horizontal=12), tooltip="Добавить в набор",
            on_click=lambda e: self.ui.context_menus.add_to_set_menu(app, e))
        chips.append(Wg.hoverable(add, None, C.RAISED))
        return ft.Row(chips, spacing=8, wrap=True, run_spacing=8, expand=True)

    def _cat_selector(self, app, cat):
        box = ft.Container(
            ft.Row([
                ft.Row([Wg.cat_glyph(cat, size=16) if cat
                        else ft.Icon(ft.Icons.FOLDER_ROUNDED, size=16, color=C.MUTED),
                        T(cat["name"] if cat else "Без категории", size=C.FS_BODY,
                          color=C.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)],
                       spacing=8, tight=True, expand=True),
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN_ROUNDED, size=16, color=C.FAINT),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=168, height=34, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE),
            border_radius=C.R, padding=ft.Padding.symmetric(horizontal=12),
            tooltip="Выбрать категорию",
            on_click=lambda e: self.ui.context_menus.category_picker(app, e))
        return Wg.hoverable(box, C.CARD, C.RAISED)

    def _quick_sub(self, app) -> str:
        accel = self.ui._accels.get(app["id"])
        if app.get("quick") and accel:
            return f"Место {accel.split('+')[-1]} · {accel} в окне"
        if app.get("quick"):
            return "Свободных мест не осталось"
        return "Появится на полке сверху"

    def _insp_advanced(self, app):
        args_value = " ".join(app.get("args") or []) if isinstance(app.get("args"), list) \
            else str(app.get("args") or "")
        open_now = self.ui.view.adv or bool(args_value) or bool(app.get("run_as_admin")) \
            or bool(app.get("working_dir"))
        head = ft.Container(
            ft.Row([ft.Icon(ft.Icons.EXPAND_MORE_ROUNDED if open_now else ft.Icons.CHEVRON_RIGHT_ROUNDED,
                            size=18, color=C.FAINT),
                    Wg.caps("Параметры запуска")],
                   spacing=6, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda e: self.ui._toggle_adv())
        if not open_now:
            return ft.Container(head, padding=ft.Padding.only(left=PAD, top=24, right=PAD))

        args_field = _field(self.ui.view, "app_args", args_value, "не заданы",
                            lambda value: self.ui._set_args(app["id"], value), mono=True)

        workdir = (app.get("working_dir") or "").strip()
        folder = ft.Container(
            ft.Row([T(_short_path(workdir) if workdir else "как у файла", size=C.FS_SMALL,
                      color=C.TEXT_2 if workdir else C.MUTED_2,
                      font_family="monospace" if workdir else None,
                      expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    Wg.icon_btn(ft.Icons.FOLDER_OPEN_ROUNDED, "Выбрать папку",
                                lambda: self.ui._pick_working_dir(app["id"]), size=26)],
                   spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=34, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE), border_radius=C.R,
            padding=ft.Padding.only(left=12, right=4), expand=True)

        proc = (app.get("track_exe") or "").strip()
        proc_box = ft.Container(
            ft.Row([T(proc or "не определён", size=C.FS_SMALL,
                      font_family="monospace" if proc else None,
                      color=C.TEXT if proc else C.MUTED_2, expand=True,
                      max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    T("найден" if proc and app["id"] in self.ui.running else "",
                      size=C.FS_SMALL, color=C.GREEN_TEXT)],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=34, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE), border_radius=C.R,
            padding=ft.Padding.symmetric(horizontal=12), expand=True)

        def labelled(label, control):
            return ft.Row([T(label, size=C.FS_SMALL, color=C.MUTED, width=72), control],
                          spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(ft.Column([
            head,
            labelled("Аргументы", args_field),
            labelled("Папка", folder),
            labelled("Процесс", proc_box),
            self._insp_row("От администратора",
                           Wg.toggle(bool(app.get("run_as_admin")),
                                     lambda v: self.ui._set_admin(app["id"], v),
                                     self.ui._accent())),
        ], spacing=12), padding=ft.Padding.only(left=PAD, top=24, right=PAD))
