from __future__ import annotations

import threading

import flet as ft

from ..infra import log
from . import colors as C
from . import widgets as Wg
from .format import T

PLAIN_SECONDS = 2.6
UNDO_SECONDS = 8
MARGIN = 16
BOTTOM_LIFTED = 88
# Сколько прежних уведомлений остаётся видно над новым.
STACK = 2


class _Older:
    """Уведомление, которое сменилось новым, но ещё не истекло.

    Остаётся в стопке над новым со своим отсчётом; его «Вернуть» работает
    до конца отсчёта — новое уведомление не отнимает отмену у старого.
    """

    def __init__(self, card, action, left, countdown):
        self.card = card
        self.action = action
        self.left = left
        self.countdown = countdown
        self.timer: threading.Timer | None = None


class ToastHost:
    """Уведомления в правом нижнем углу окна, как системные в Windows.

    Посередине окна они закрывали плитки. Новое встаёт внизу, прежнее — над
    ним, пока не истечёт. Поля `text`, `icon`, `card`… — это новое.
    """

    def __init__(self, page: ft.Page, accent=None):
        self.page = page
        # «Вернуть» — кнопка цвета акцента: главное, что можно тут сделать.
        self.accent = accent or (lambda: C.ACCENT)
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._token = 0
        self._left = 0
        self._action = None
        self._error = False
        self._queued: dict | None = None
        self._older: list[_Older] = []
        self._current_on = False

        self.icon = ft.Icon(ft.Icons.CHECK_ROUNDED, size=18, color=C.GREEN)
        self.text = T("", size=C.FS_BODY, color=C.TEXT, max_lines=2,
                      overflow=ft.TextOverflow.ELLIPSIS)
        self.detail = T("", size=C.FS_SMALL, color=C.MUTED, max_lines=2, visible=False,
                        overflow=ft.TextOverflow.ELLIPSIS)
        self.body = ft.Column([self.text, self.detail], spacing=2, expand=True, tight=True)
        self.action_label = T("", size=C.FS_BODY, weight=ft.FontWeight.W_600, color=C.TEXT)
        self.action_btn = ft.Container(
            self.action_label, visible=False, border_radius=C.R_SMALL,
            padding=ft.Padding.symmetric(vertical=4, horizontal=8),
            on_click=lambda e: self.fire_action())
        self.countdown = T("", size=C.FS_CAPTION, color=C.MUTED_2, font_family="monospace",
                           visible=False)

        # Стекло, как у уведомлений macOS; новое выезжает снизу.
        self.card = ft.Container(
            ft.Row([self.icon, self.body, self.action_btn, self.countdown],
                   spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=C.TOAST_W, border_radius=C.R_XL, blur=ft.Blur(30, 30),
            padding=ft.Padding.symmetric(vertical=12, horizontal=16),
            animate_opacity=Wg.anim(C.ANIM_POP),
            animate_offset=Wg.anim(C.ANIM_POP, spring=True),
        )
        self.stack = ft.Column([self.card], spacing=8, tight=True,
                               horizontal_alignment=ft.CrossAxisAlignment.END)
        self.control = ft.Container(self.stack, right=MARGIN, bottom=MARGIN, visible=False)
        self._paint(error=False)

    def _paint(self, error: bool):
        """Цвета темы — при каждом показе: тема могла смениться с прошлого раза."""
        self.card.bgcolor = C.with_alpha(C.ERR_BG, 0.92) if error else C.GLASS
        self.card.border = ft.Border.all(1, C.ERR_BORDER if error else C.EDGE)
        self.card.shadow = ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 14),
                                        color=C.SHADOW)
        self.text.color = C.TEXT
        self.detail.color = C.MUTED
        self.action_label.color = C.TEXT
        self.countdown.color = C.MUTED_2
        self.action_label.color = C.on_color(self.accent()) if not error else C.TEXT
        Wg.hoverable(self.action_btn, None if error else self.accent(),
                     C.RAISED if error else C.mix(self.accent(), C.WHITE, 0.12))
        if not error:
            self.action_btn.bgcolor = self.accent()

    def lift(self, above: bool):
        self.control.bottom = BOTTOM_LIFTED if above else MARGIN

    def recenter(self):
        """Оставлено для совместимости: место уведомлений больше не считается."""

    def show(self, text: str, icon=ft.Icons.CHECK_ROUNDED, icon_color=None,
             action=None, action_label: str | None = None, error: bool = False,
             detail: str | None = None, wait_for_undo: bool = False):
        """`wait_for_undo` — для новостей из фона: они не затирают «Вернуть».

        Иначе «Нашлось нового» от автопроверки молча отнимало отмену удаления,
        сделанного секунду назад. Ответ на действие самого человека, как и
        ошибка, показывается сразу, а прежнее уведомление поднимается выше.
        """
        with self._lock:
            if wait_for_undo and self._action and not error:
                self._queued = {"text": text, "icon": icon, "icon_color": icon_color,
                                "detail": detail, "action": action,
                                "action_label": action_label}
                return
            self._queued = None
            self._push_current()
            self._cancel_timer()
            self._token += 1
            token = self._token
            self._action = action
            self._error = error
            self._left = UNDO_SECONDS if action else 0

            self.icon.icon = ft.Icons.ERROR_OUTLINE_ROUNDED if error else icon
            self.icon.color = C.DANGER if error else (icon_color or C.GREEN)
            self.text.value = text
            self.detail.value = detail or ""
            self.detail.visible = bool(detail)
            self._paint(error)
            self.action_btn.visible = bool(action)
            self.action_label.value = action_label or "Вернуть"
            self.countdown.visible = bool(action)
            self.countdown.value = str(self._left) if action else ""
            if not self._current_on:
                Wg.enter(self.card, {"offset": ft.Offset(0, 0.5), "opacity": 0},
                         {"offset": ft.Offset(0, 0), "opacity": 1})
            self.control.visible = True
            self._arm(1.0 if action else PLAIN_SECONDS, token)
            self._restack()
        self._safe_update()

    def error(self, text: str, action=None, action_label: str | None = None,
              detail: str | None = None):
        self.show(text, error=True, action=action, action_label=action_label, detail=detail)

    def _push_current(self):
        """Текущее уведомление уходит в стопку, если оно ещё на экране."""
        if not self._current_on or not self.text.value:
            return
        countdown = T(str(self._left), size=C.FS_CAPTION, color=C.MUTED_2,
                      font_family="monospace", visible=bool(self._action))
        entry = _Older(None, self._action, self._left if self._action else 0, countdown)
        row = [ft.Icon(self.icon.icon, size=18, color=self.icon.color),
               ft.Column([T(self.text.value, size=C.FS_BODY, color=C.TEXT, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS)]
                         + ([T(self.detail.value, size=C.FS_SMALL, color=C.MUTED, max_lines=2,
                               overflow=ft.TextOverflow.ELLIPSIS)]
                            if self.detail.visible else []),
                         spacing=2, expand=True, tight=True)]
        if self._action:
            # Та же кнопка, что у нового: у ошибки — серая, иначе цвета акцента.
            fill = None if self._error else self.accent()
            btn = ft.Container(T(self.action_label.value, size=C.FS_BODY,
                                 weight=ft.FontWeight.W_600,
                                 color=C.on_color(fill) if fill else C.TEXT),
                               border_radius=C.R_SMALL,
                               padding=ft.Padding.symmetric(vertical=4, horizontal=8),
                               on_click=lambda e, en=entry: self._fire_older(en))
            row += [Wg.hoverable(btn, fill, C.mix(fill, C.WHITE, 0.12) if fill else C.RAISED),
                    countdown]
        entry.card = ft.Container(
            ft.Row(row, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            width=C.TOAST_W, border_radius=C.R_XL, opacity=0.92, blur=ft.Blur(30, 30),
            padding=ft.Padding.symmetric(vertical=12, horizontal=16),
            bgcolor=self.card.bgcolor, border=self.card.border, shadow=self.card.shadow)
        self._older.append(entry)
        while len(self._older) > STACK:
            self._drop_older(self._older[0], update=False)
        self._arm_older(entry, 1.0 if entry.action else PLAIN_SECONDS)

    def _arm_older(self, entry: _Older, delay: float):
        timer = threading.Timer(delay, self._tick_older, args=(entry,))
        timer.daemon = True
        entry.timer = timer
        timer.start()

    def _tick_older(self, entry: _Older):
        with self._lock:
            if entry not in self._older:
                return
            if entry.action and entry.left > 1:
                entry.left -= 1
                entry.countdown.value = str(entry.left)
                self._arm_older(entry, 1.0)
            else:
                self._drop_older(entry, update=False)
        self._safe_update()

    def _fire_older(self, entry: _Older):
        with self._lock:
            action = entry.action
            entry.action = None
            self._drop_older(entry, update=False)
        self._safe_update()
        if action:
            try:
                action()
            except Exception:
                log.exception("отменить тост не удалось")

    def _drop_older(self, entry: _Older, update: bool = True):
        if entry.timer is not None:
            entry.timer.cancel()
            entry.timer = None
        if entry in self._older:
            self._older.remove(entry)
        self._restack()
        if update:
            self._safe_update()

    def _restack(self):
        cards = [e.card for e in self._older]
        if self._current_on:
            cards.append(self.card)
        self.stack.controls = cards
        self.control.visible = bool(cards)

    def fire_action(self):
        with self._lock:
            action = self._action
            self._action = None
            self._cancel_timer()
            self._hide_current()
            token = self._token
        self._safe_update()
        if action:
            try:
                action()
            except Exception:
                log.exception("отменить тост не удалось")
        if self._token == token:
            self._show_queued()

    def _hide_current(self):
        self._current_on = False
        self._restack()

    def _show_queued(self):
        with self._lock:
            queued, self._queued = self._queued, None
        if queued:
            self.show(**queued)

    def dismiss(self):
        with self._lock:
            self._cancel_timer()
            self._action = None
            self._hide_current()
        self._safe_update()

    def dismiss_if(self, action) -> None:
        """Убрать уведомление, чья кнопка ведёт туда, где человек уже стоит.

        «В разборе: 4 · Разобрать» висело на самом экране разбора.
        """
        # Связанные методы сравниваются через ==: каждый `ui.open_triage` —
        # новый объект, но равный прежнему.
        with self._lock:
            changed = False
            if self._current_on and self._action is not None and self._action == action:
                self._cancel_timer()
                self._action = None
                self._hide_current()
                changed = True
            for entry in list(self._older):
                if entry.action is not None and entry.action == action:
                    self._drop_older(entry, update=False)
                    changed = True
        if changed:
            self._safe_update()

    def stop(self):
        with self._lock:
            self._cancel_timer()
            self._action = None
            self._queued = None
            for entry in list(self._older):
                if entry.timer is not None:
                    entry.timer.cancel()
            self._older = []

    def _arm(self, delay: float, token: int):
        self._current_on = True
        timer = threading.Timer(delay, self._tick, args=(token,))
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _tick(self, token: int):
        with self._lock:
            if token != self._token:
                return
            self._timer = None
            expired = False
            if not self._action:
                self._hide_current()
            else:
                self._left -= 1
                if self._left <= 0:
                    self._action = None
                    self._hide_current()
                    expired = True
                else:
                    self.countdown.value = str(self._left)
                    self._arm(1.0, token)
        self._safe_update()
        if expired:
            self._show_queued()

    def _safe_update(self):
        try:
            if Wg.attached(self.control):
                self.control.update()
        except Exception:
            log.exception("сбой при обновлении тоста")


NOTE_ICONS = {
    "check": ft.Icons.CHECK_ROUNDED,
    "check_circle": ft.Icons.CHECK_CIRCLE_ROUNDED,
    "search": ft.Icons.SEARCH_ROUNDED,
    "inbox": ft.Icons.INBOX_ROUNDED,
    "layers": ft.Icons.LAYERS_ROUNDED,
    "folder": ft.Icons.FOLDER_ROUNDED,
    "link": ft.Icons.LINK_ROUNDED,
    "save": ft.Icons.SAVE_ROUNDED,
    "close": ft.Icons.CLOSE_ROUNDED,
    "arrange": ft.Icons.CROP_FREE_ROUNDED,
    "monitor": ft.Icons.DESKTOP_WINDOWS_ROUNDED,
    "delete": ft.Icons.DELETE_OUTLINE_ROUNDED,
    "magic": ft.Icons.AUTO_AWESOME_ROUNDED,
    "download": ft.Icons.DOWNLOAD_ROUNDED,
}


class Notifier:

    def __init__(self, toast: ToastHost):
        self.toast = toast

    def show(self, text: str, icon: str = "check", tone: str = "good",
             action=None, action_label: str | None = None, detail: str | None = None,
             wait_for_undo: bool = False):
        # Цвет — в момент показа: тема (светлая, тёмная) могла смениться.
        color = C.MUTED if tone == "muted" else C.GREEN
        self.toast.show(text, icon=NOTE_ICONS.get(icon, ft.Icons.CHECK_ROUNDED), icon_color=color,
                        action=action, action_label=action_label, detail=detail,
                        wait_for_undo=wait_for_undo)

    def error(self, text: str, action=None, action_label: str | None = None,
              detail: str | None = None):
        self.toast.error(text, action=action, action_label=action_label, detail=detail)
