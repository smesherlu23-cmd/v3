from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .. import __version__
from ..infra import log, updates

if TYPE_CHECKING:
    from .host import UIHost

# Раз в сутки, с запасом на «включил утром, а вчера — чуть позже».
CHECK_EVERY = 20 * 3600


class UpdatesController:

    def __init__(self, ui: UIHost):
        self.ui = ui
        self.store = ui.store
        self.notify = ui.notify
        self._checking = threading.Lock()
        self.fetch = updates.fetch_latest

    def available(self) -> str:
        """Версия новее установленной, если о ней уже известно."""
        version = self.ui.setting("update_version", "") or ""
        return version if updates.is_newer(version, __version__) else ""

    def url(self) -> str:
        return self.ui.setting("update_url", "") or updates.RELEASES_URL

    def due(self, now: float | None = None) -> bool:
        if not self.ui.setting("check_updates", True):
            return False
        now = time.time() if now is None else now
        return now - int(self.ui.setting("update_checked_at", 0) or 0) >= CHECK_EVERY

    def check(self, quiet: bool = True) -> None:
        """Спросить GitHub. `quiet` — фоновая проверка: молчит, если нового нет."""
        if not self._checking.acquire(blocking=False):
            return
        try:
            try:
                latest = self.fetch()
            except Exception as exc:
                log.warning("не удалось проверить обновления: %s", exc)
                if not quiet:
                    self.notify.error("Не удалось проверить обновления",
                                      detail="Нет связи с GitHub — попробуйте позже")
                return
            self.store.set_setting("update_checked_at", int(time.time()))
            newer = latest and updates.is_newer(latest["version"], __version__)
            self.store.set_setting("update_version", latest["version"] if newer else "")
            self.store.set_setting("update_url", latest["url"] if newer else "")
            if not newer:
                if not quiet:
                    self.notify.show(f"У вас последняя версия — {__version__}", icon="check",
                                     tone="muted")
                self.ui.safe_refresh()
                return
            if quiet and self.ui.setting("update_seen", "") == latest["version"]:
                self.ui.safe_refresh()
                return
            self.store.set_setting("update_seen", latest["version"])
            self.notify.show(f"Вышла Centurio {latest['version']}", icon="download",
                             action=lambda: self.ui.open_url(self.url()),
                             action_label="Скачать", wait_for_undo=quiet)
            self.ui.safe_refresh()
        finally:
            self._checking.release()

    def check_if_due(self) -> None:
        if self.due():
            self.check(quiet=True)

    def check_now(self) -> None:
        threading.Thread(target=lambda: self.check(quiet=False), daemon=True).start()
