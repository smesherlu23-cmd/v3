from __future__ import annotations

from typing import TypedDict


class Settings(TypedDict, total=False):
    autostart: bool
    autostart_adopted: bool
    minimize_to_tray: bool
    close_to_tray: bool
    accent: str
    bg_tint: int | None
    contrast: str
    tile_size: str
    rail_size: str
    show_quick_row: bool
    game_posters: bool
    auto_rescan: bool
    view_filter: str
    view_sort: str
    view_mode: str
    win_w: int | None
    win_h: int | None
    win_x: int | None
    win_y: int | None
    win_max: bool
    icon_schema: int
    launch_hotkey: str
    hide_after: bool
    triage: bool
    debug_log: bool
    collapsed: list[str]
    ui_defaults_version: int


class App(TypedDict, total=False):
    id: str
    name: str
    path: str
    args: list[str]
    working_dir: str
    run_as_admin: bool
    sub: str
    category_id: str | None
    hue: int
    icon: str | None
    icon_fit: str
    poster: str | None
    favorite: bool
    quick: bool
    hidden: bool
    hotkey: str | None
    track_exe: str | None
    order: int
    last_launched: int
    launch_count: int
    added_at: int


class Category(TypedDict, total=False):
    id: str
    name: str
    icon: str
    color: str
    order: int
    image: str | None


class SetLayout(TypedDict, total=False):
    preset: str
    split: float
    vsplit: float


class SetItem(TypedDict, total=False):
    app_id: str
    slot: int | None
    minimized: bool
    rect: list | None


class AppSet(TypedDict, total=False):
    id: str
    name: str
    order: int
    quick: bool
    layout: SetLayout
    hotkey: str | None
    monitor: int
    close_together: bool
    delay_seconds: float
    items: list[SetItem]
    apps: list[str]


class InboxItem(TypedDict, total=False):
    id: str
    path: str
    name: str
    source: str
    order: int
    found_at: int


class StoreState(TypedDict, total=False):
    version: int
    apps: list[App]
    categories: list[Category]
    sets: list[AppSet]
    inbox: list[InboxItem]
    settings: Settings
