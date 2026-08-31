from __future__ import annotations

import os
import threading
from typing import NamedTuple

from ..infra import log


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
_WM_STOP = 0x0400 + 1  

_MOD_FLAGS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}

_KEY_ALIASES = {
    "arrow up": "up", "arrow down": "down",
    "arrow left": "left", "arrow right": "right",
    "escape": "esc", "return": "enter", "numpad enter": "enter",
    "page up": "page_up", "page down": "page_down",
    "caps lock": "caps_lock", "num lock": "num_lock",
    "scroll lock": "scroll_lock", "print screen": "print_screen",
    "del": "delete", "ins": "insert", "spacebar": "space", " ": "space",
    "break": "pause",
}

_VK = {
    "space": 0x20, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pause": 0x13, "print_screen": 0x2C, "scroll_lock": 0x91,
    "caps_lock": 0x14, "num_lock": 0x90, "menu": 0x5D,
    "media_next": 0xB0, "media_previous": 0xB1, "media_play_pause": 0xB3,
    "media_volume_mute": 0xAD, "media_volume_down": 0xAE, "media_volume_up": 0xAF,
}
_VK.update({f"f{n}": 0x6F + n for n in range(1, 25)})  

_NAMED_KEYS = frozenset(_VK)
_STANDALONE_KEYS = {
    "pause", "print_screen", "scroll_lock",
    "media_next", "media_previous", "media_play_pause",
    "media_volume_up", "media_volume_down", "media_volume_mute",
} | {f"f{n}" for n in range(1, 25)}


def canonical_key(token: str) -> str:
    key = str(token or "").strip().lower()
    return _KEY_ALIASES.get(key, key)


def _key_vk(key: str) -> int | None:
    vk = _VK.get(key)
    if vk is not None:
        return vk
    if len(key) == 1:
        ch = key.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    return None


def to_win_hotkey(accel: str) -> tuple[int, int] | None:
    mods, key = split_accel(accel)
    if not key:
        return None
    vk = _key_vk(key)
    if vk is None:
        return None
    flags = 0
    for m in mods:
        f = _MOD_FLAGS.get(m)
        if f is None:
            return None
        flags |= f
    return flags, vk


_MOD_ORDER = ("ctrl", "alt", "shift", "win")
_MOD_ALIASES = {"control": "ctrl", "option": "alt", "cmd": "win", "super": "win", "meta": "win"}


def split_accel(accel: str) -> tuple[set[str], str]:
    tokens = [t.strip().lower() for t in str(accel or "").split("+") if t.strip()]
    if not tokens:
        return set(), ""
    mods = {_MOD_ALIASES.get(t, t) for t in tokens[:-1]}
    return mods, canonical_key(tokens[-1])


def normalize_accel(accel: str) -> str:
    mods, key = split_accel(accel)
    if not key:
        return ""
    return "+".join([m for m in _MOD_ORDER if m in mods] + [key])


def is_bindable(accel: str) -> tuple[bool, str]:
    mods, key = split_accel(accel)
    if not key:
        return False, "Не разобрал комбинацию"
    if len(key) != 1 and key not in _NAMED_KEYS:
        return False, "Эту клавишу назначить нельзя"
    if not mods and key not in _STANDALONE_KEYS:
        return False, "Нужен модификатор — Ctrl, Alt, Shift или Win"
    if is_reserved(accel):
        return False, "Комбинацию занимает Windows — система её не отдаст"
    return True, ""

RESERVED_COMBOS = {normalize_accel(c) for c in (
    "Alt+F4", "Alt+Tab", "Alt+Shift+Tab", "Ctrl+Alt+Tab", "Alt+Esc", "Alt+Escape",
    "Ctrl+Esc", "Ctrl+Shift+Esc", "Ctrl+Alt+Delete", "Ctrl+Alt+Del",
    "Win+L", "Win+D", "Win+E", "Win+R", "Win+I", "Win+A", "Win+X", "Win+U",
    "Win+P", "Win+S", "Win+Q", "Win+M", "Win+Tab", "Win+Pause", "Win+Comma",
    "Win+Period", "Win+Space", "Win+Shift+S", "Win+Ctrl+D", "Win+Ctrl+F4",
    "Win+Ctrl+Left", "Win+Ctrl+Right", "Win+Shift+M", "Win+Break",
)}


def is_reserved(accel: str) -> bool:
    return normalize_accel(accel) in RESERVED_COMBOS


_KEY_LABELS = {"space": "Пробел", "enter": "Ввод", "esc": "Esc", "escape": "Esc",
               "tab": "Tab", "backspace": "Backspace"}


def format_accel(accel: str | None) -> str:
    if not accel:
        return "не задана"
    parts = []
    for raw in str(accel).split("+"):
        token = raw.strip()
        if not token:
            continue
        parts.append(_KEY_LABELS.get(token.lower(), token if len(token) > 1 else token.upper()))
    return "+".join(parts)


TOGGLE_LAUNCH = "__centurio_toggle_launch__"
SET_PREFIX = "set:"


class _Binding(NamedTuple):
    target: str
    accel: str
    flags: int
    vk: int


class HotkeyManager:

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self.available = False
        self.rejected: list[str] = []
        self.bound: set[str] = set()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._lock = threading.Lock()

    def _build_mapping(self, bindings):
        mapping: dict[int, _Binding] = {}
        seen: dict[tuple[int, int], int] = {}
        rejected: list[str] = []
        self.bound = set()
        next_id = 1
        for accel, target in bindings:
            if not accel:
                continue
            combo = to_win_hotkey(accel)
            if combo is None:
                rejected.append(accel)
                log.warning("ignoring unbindable hotkey %r", accel)
                continue
            if combo in seen:
                rejected.append(accel)
                log.warning("ignoring duplicate hotkey %r", accel)
                continue
            flags, vk = combo
            hid = next_id
            next_id += 1
            seen[combo] = hid
            mapping[hid] = _Binding(target, accel, flags, vk)
            self.bound.add(normalize_accel(accel))
        return mapping, rejected

    def register(self, bindings) -> bool:
        self.stop()
        mapping, self.rejected = self._build_mapping(bindings)
        if not mapping or os.name != "nt":
            self.available = False
            self.bound = set()
            return False

        started = threading.Event()
        os_rejected: list[str] = []
        registered: set[str] = set()
        thread = threading.Thread(
            target=self._run, name="centurio-hotkeys", daemon=True,
            args=(mapping, started, os_rejected, registered))
        with self._lock:
            self._thread = thread
        thread.start()
        started.wait(2.0)
        if os_rejected:
            self.rejected = self.rejected + os_rejected
        self.bound = registered
        self.available = bool(registered)
        return self.available

    def _run(self, mapping, started, os_rejected, registered):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except Exception:
            log.exception("ctypes unavailable for global hotkeys")
            started.set()
            return

        active: list[int] = []
        try:
            with self._lock:
                self._thread_id = kernel32.GetCurrentThreadId()
            for hid, b in mapping.items():
                if user32.RegisterHotKey(None, hid, b.flags | MOD_NOREPEAT, b.vk):
                    active.append(hid)
                    registered.add(normalize_accel(b.accel))
                else:
                    os_rejected.append(b.accel)
                    log.warning("RegisterHotKey refused %r — taken by the "
                                "system or another app", b.accel)
        finally:
            started.set()

        try:
            msg = wintypes.MSG()
            while True:
                got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if got in (0, -1):
                    break
                if msg.message == _WM_STOP:
                    break
                if msg.message == WM_HOTKEY:
                    b = mapping.get(msg.wParam)
                    if b is not None:
                        self._fire(b.target)
        except Exception:
            log.exception("global hotkey message loop crashed")
        finally:
            for hid in active:
                try:
                    user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass

    def handles(self, accel: str) -> bool:
        return self.available and normalize_accel(accel) in self.bound

    def _fire(self, target):
        try:
            self.on_trigger(target)
        except Exception:
            log.exception("global hotkey handler for %s failed", target)

    def stop(self):
        with self._lock:
            thread = self._thread
            thread_id = self._thread_id
            self._thread = None
            self._thread_id = 0
        if thread is not None and thread_id:
            try:
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(thread_id, _WM_STOP, 0, 0)
            except Exception:
                log.exception("failed to signal the hotkey thread to stop")
            thread.join(2.0)
        self.available = False
        self.bound = set()


QUICK_SLOTS = 9


def _auto_accels(records, pattern: str, wanted, reserved=()) -> dict[str, str]:
    accels: dict[str, str] = {}
    used = {normalize_accel(a) for a in reserved if a}
    for rec in records:
        hk = (rec.get("hotkey") or "").strip()
        if hk:
            accels[rec["id"]] = hk
            used.add(normalize_accel(hk))
    slot = 1
    for rec in records:
        if rec["id"] in accels or not wanted(rec):
            continue
        while slot <= QUICK_SLOTS and normalize_accel(pattern.format(slot)) in used:
            slot += 1
        if slot > QUICK_SLOTS:
            break
        accel = pattern.format(slot)
        accels[rec["id"]] = accel
        used.add(normalize_accel(accel))
        slot += 1
    return accels


def quick_accels(apps, reserved=()) -> dict[str, str]:
    return _auto_accels(apps, "Ctrl+{}", lambda a: a.get("quick"), reserved)


def quick_bindings(apps, reserved=()) -> list[tuple[str, str]]:
    return [(accel, app_id) for app_id, accel in quick_accels(apps, reserved).items()]


def free_quick_slot(apps, reserved=()) -> int:
    taken = set()
    for accel in list(quick_accels(apps, reserved).values()) + [a for a in reserved if a]:
        mods, key = split_accel(accel)
        if mods == {"ctrl"} and key.isdigit():
            taken.add(key)
    return next((n for n in range(1, QUICK_SLOTS + 1) if str(n) not in taken), 0)


def app_for_accel(apps, accel: str, reserved=()) -> str | None:
    want = normalize_accel(accel)
    if not want:
        return None
    return next((aid for aid, ac in quick_accels(apps, reserved).items()
                 if normalize_accel(ac) == want), None)


def set_accels(sets, reserved=()) -> dict[str, str]:
    return _auto_accels(sets, "Ctrl+Alt+{}", lambda rec: True, reserved)


def set_bindings(sets, reserved=()) -> list[tuple[str, str]]:
    return [(accel, SET_PREFIX + set_id)
            for set_id, accel in set_accels(sets, reserved).items()]


def set_for_accel(sets, accel: str, reserved=()) -> str | None:
    want = normalize_accel(accel)
    if not want:
        return None
    return next((sid for sid, ac in set_accels(sets, reserved).items()
                 if normalize_accel(ac) == want), None)


def resolve_accels(apps, sets, launch_hotkey: str) -> tuple[dict[str, str], dict[str, str]]:
    app_accels = quick_accels(apps, reserved=[launch_hotkey])
    set_slots = set_accels(sets, reserved=[launch_hotkey, *app_accels.values()])
    return app_accels, set_slots


def split_binding(binding_id: str) -> tuple[str, str]:
    if (binding_id or "").startswith(SET_PREFIX):
        return "set", binding_id[len(SET_PREFIX):]
    return "app", binding_id
