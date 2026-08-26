"""Интерфейс, который контроллеры ждут от интерфейса приложения.

Контроллеры (`scan`, `sets`, `triage`) получают на вход `CenturioUI` целиком
и держат обратную ссылку — 132 метода и 62 поля объекта-бога (С-1/С-2 в
ATTESTATION.md). Настоящая же их потребность узкая: хранилище, лаунчер,
состояние представления, перерисовка и несколько команд. `UIHost` называет
ровно эту потребность.

Протокол определён здесь, на стороне потребителя (слой `controllers`), а не
рядом с `CenturioUI` в слое `ui`: контроллеры не имеют права импортировать
интерфейс наружу (это ловит `test_layers_do_not_depend_outwards`). `CenturioUI`
удовлетворяет протоколу структурно, ничего от него не наследуя.

Проверку «контроллеры трогают только публичную поверхность» держит
`test_controllers_depend_only_on_the_public_ui_surface`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..core.store import Store
    from ..core.view_state import ViewState
    from ..platform.launcher import Launcher


class UIHost(Protocol):
    store: Store
    launcher: Launcher
    view: ViewState
    notify: Any
    running: set
    relocating: str | None

    def refresh(self, content_only: bool = ...) -> None: ...
    def safe_refresh(self) -> None: ...
    def on_library_changed(self) -> None: ...
    def clear_search(self) -> None: ...
    def icon_cache_dir(self) -> str: ...
    def categories(self) -> list: ...
    def apps(self) -> list: ...
    def setting(self, key: str, default: Any = ...) -> Any: ...
    def open_triage(self) -> None: ...
    def open_add(self) -> None: ...
    def toggle_select_mode(self) -> None: ...
    def after_launch(self, *args: Any, **kwargs: Any) -> Any: ...
    def ask_for_file(self, *args: Any, **kwargs: Any) -> Any: ...
