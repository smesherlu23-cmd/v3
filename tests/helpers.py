"""Общее для тестов Centurio: проверки ok()/skip(), поддельные окно и страница,
поиск по дереву контролов. Тесты разложены по темам в tests/test_*.py;
без pytest их все запускает `python tests/run_all.py`.
"""
import os
import sys
import time
from pathlib import Path

try:
    import flet as ft
except Exception:            # проверяется отдельно, тесты интерфейса пропустятся
    ft = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


try:
    import pytest
except ImportError:
    pytest = None

_passed = 0
_failed = 0
_skipped: list[str] = []


class CheckFailed(AssertionError):
    """One ok() check that did not hold."""


def ok(cond, msg):
    """Assert one named expectation.

    Raises rather than counting, so pytest attributes the failure to the test
    that produced it and the rest of the suite still runs. Before this, a
    failed check only incremented a counter, so under pytest every test
    reported green; under the standalone runner the first unhandled error
    ended the whole run.
    """
    global _passed, _failed
    if cond:
        _passed += 1
        return
    _failed += 1
    raise CheckFailed(msg)


def skip(name, reason):
    """Skip a test that needs Flet, or fail if Flet should have been there.

    Under CI the workflow installs Flet as a hard requirement, so a skip means
    something is actually wrong rather than "Flet isn't installed, which is
    fine for a local logic-only run". _summarize() keeps the same rule for the
    standalone runner as a second guard.
    """
    _skipped.append(name)
    message = f"{name} (Flet unavailable): {reason}"
    if os.environ.get("CI"):
        raise CheckFailed(f"skipped under CI, where Flet is required — {message}")
    if pytest is not None and "PYTEST_CURRENT_TEST" in os.environ:
        pytest.skip(message)
    print("SKIP", message)


def _summarize(passed: int, failed: int, skipped: list[str], is_ci: bool) -> tuple[int, str]:
    """Turn the run's counters into (exit_code, report_line).

    Pulled out of the __main__ block so the CI-escalation rule — any skip
    under CI is a failure — is itself testable, not just exercised by the
    one real run of this file. Reports by returning, never by printing: the
    escalation branch used to print "FAIL: ..." as a side effect, so the test
    that exercises it stamped a fake failure into the log of a green run.
    """
    note = ""
    if skipped and is_ci:
        failed += 1
        note = (f"\nFAIL: {len(skipped)} test(s) skipped under CI (Flet should be installed "
                f"here): {', '.join(skipped)}")
    line = f"{passed} passed, {failed} failed" + (f", {len(skipped)} skipped" if skipped else "")
    return (1 if failed else 0), line + note


class _FakeNotify:
    def __init__(self):
        self.messages: list[str] = []

    def show(self, msg, **kw):
        self.messages.append(msg)

    def error(self, msg, **kw):
        self.messages.append(msg)


class _FakeView:
    def __init__(self):
        self.manual_path = ""
        self.add_sel: set[str] = set()
        self.add_query = ""
        self.only_new = False


class _FakeScanUI:
    """Минимальная реализация `UIHost`-протокола для теста `ScanController`."""

    def __init__(self, store, cache_dir, posters=True):
        self.store = store
        self.notify = _FakeNotify()
        self.view = _FakeView()
        self.relocating = None
        self.running: set[str] = set()
        self.launcher = None
        self._cache_dir = cache_dir
        self._settings = {"game_posters": posters}

    def icon_cache_dir(self):
        return self._cache_dir

    def setting(self, key, default=None):
        return self._settings.get(key, default)

    def categories(self):
        return []

    def apps(self):
        return self.store.state()["apps"]

    def on_library_changed(self):
        pass

    def refresh(self, content_only=False):
        pass

    def select_one(self, app_id):
        pass


def _completes(fn, seconds=2.0) -> bool:
    """Run fn on a throwaway thread; False if it is still stuck afterwards.

    Keeps a deadlock regression a reported failure instead of a hung suite.
    """
    import threading
    done = threading.Event()
    threading.Thread(target=lambda: (fn(), done.set()), daemon=True).start()
    return done.wait(seconds)


def _settle_threads(before, timeout=3.0) -> bool:
    """Wait until the worker threads a test started have finished.

    Deleting a temp dir while a background scan is still writing into it used
    to be papered over with a fixed sleep; this waits for the actual condition
    instead, so the test is neither slow nor racy.
    """
    import threading
    deadline = time.time() + timeout
    while time.time() < deadline:
        # A toast's countdown is a threading.Timer meant to outlive the action
        # it reports on — waiting for it would be waiting out the undo window.
        live = [t for t in threading.enumerate()
                if t not in before and t.is_alive() and not isinstance(t, threading.Timer)]
        if not live:
            return True
        time.sleep(0.01)
    return False


def types_ns(**kw):
    """A stand-in object with just the attributes a test hands it."""
    import types
    return types.SimpleNamespace(**kw)


def _find_control(node, pred, _depth=0):
    """Depth-first search of a built Flet tree, so dialog tests don't index
    into `content.controls[2].controls[0]` and break on every re-layout."""
    if _depth > 40 or node is None or isinstance(node, str):
        return None
    if pred(node):
        return node
    for attr in ("controls", "actions"):
        for child in getattr(node, attr, None) or []:
            found = _find_control(child, pred, _depth + 1)
            if found is not None:
                return found
    return _find_control(getattr(node, "content", None), pred, _depth + 1)


def _find_all(node, pred, _depth=0, out=None):
    """Every control in a built tree matching pred — for counting sliders etc."""
    out = [] if out is None else out
    if _depth > 40 or node is None or isinstance(node, str):
        return out
    if pred(node):
        out.append(node)
    for attr in ("controls", "actions"):
        for child in getattr(node, attr, None) or []:
            _find_all(child, pred, _depth + 1, out)
    _find_all(getattr(node, "content", None), pred, _depth + 1, out)
    return out


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts) -> str:
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _sources(*relative_dirs) -> list[tuple[str, str]]:
    """Каждый .py под указанными каталогами app/ как (подпись, текст).

    Перечисление идёт по диску, а не списком имён: разбиение файла на модули
    не должно тихо выводить его из-под проверки.
    """
    out: list[tuple[str, str]] = []
    for relative in relative_dirs:
        base = Path(_ROOT) / "app" / relative
        paths = sorted(base.rglob("*.py")) if base.is_dir() else [base]
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            label = path.relative_to(Path(_ROOT)).as_posix()
            out.append((label, path.read_text(encoding="utf-8")))
    return out


def _reset_centurio_log():
    import importlib
    import logging

    from app.infra import log as _log
    importlib.reload(_log)
    logging.getLogger("centurio").handlers = []
    return _log


def _drop_log_handlers(_log):
    import logging

    for h in list(_log._LOGGER.handlers):
        h.close()
        _log._LOGGER.removeHandler(h)
    logging.getLogger("centurio").handlers = []


def _run_bounded(fn, seconds=20.0):
    """Выполнить fn на отдельном потоке → (успело ли, с каким исключением).

    Запуск `main()` трогает платформу, и любое зависание там обязано стать
    красным тестом за секунды, а не молчаливо висящей сборкой: модальное окно
    из `_report_startup_failure` однажды уже держало windows-раннер три часа
    вместо двадцати секунд. Тот же приём, что и в `_completes`.
    """
    import threading

    box = {}
    done = threading.Event()

    def run():
        try:
            fn()
        except BaseException as exc:      # noqa: BLE001 — донесём наружу как есть
            box["exc"] = exc
        finally:
            done.set()

    threading.Thread(target=run, daemon=True).start()
    return done.wait(seconds), box.get("exc")


class _FakeWindow:
    def __init__(self):
        self.width = 1400
        self.height = 880
        self.left = 0
        self.top = 0
        self.maximized = False
        self.minimized = False
        self.visible = True
        self.resizable = True
        self.min_width = 0
        self.min_height = 0
        self.on_event = None
        self.prevent_close = False
        self.title_bar_hidden = False
        self.frameless = False

    def center(self):
        pass


class _FakePage:
    def __init__(self):
        self.overlay = []
        self.opened = []
        self.controls = []
        self.window = _FakeWindow()
        self.web = False
        self.tasks = []

    def add(self, *controls):
        self.controls.extend(controls)

    def open(self, d):
        self.opened.append(d)

    def close(self, d):
        pass

    def update(self, *controls):
        pass

    def run_task(self, handler, *args):
        """Асинхронное (фокус, окно, выбор файла) в тестах не выполняется."""
        self.tasks.append((handler, args))

    def run_thread(self, handler, *args):
        handler(*args)


def _ui_for(store):
    from unittest.mock import MagicMock

    from app.ui.app import CenturioUI
    page = _FakePage()
    ui = CenturioUI(page, store, MagicMock())
    ui.mount()
    return ui, page


def _texts(control, depth=0, out=None):
    """Every ft.Text value in a built subtree, for asserting on what is shown."""
    import flet as ft
    out = [] if out is None else out
    if control is None or isinstance(control, str) or depth > 26:
        return out
    if isinstance(control, ft.Text):
        if control.value:
            out.append(control.value)
        for span in getattr(control, "spans", None) or []:
            if getattr(span, "text", None):
                out.append(span.text)
    for attr in ("controls", "actions"):
        for child in getattr(control, attr, None) or []:
            _texts(child, depth + 1, out)
    _texts(getattr(control, "content", None), depth + 1, out)
    return out


def _tap(x=300, y=250):
    return types_ns(global_position=types_ns(x=x, y=y), local_position=types_ns(x=x, y=y),
                    kind="mouse")


def _tap_mods(ctrl=False, shift=False):
    """Клик с модификаторами — то, чем берут диапазон и по одной."""
    return types_ns(global_position=types_ns(x=300, y=250),
                    local_position=types_ns(x=300, y=250),
                    kind="mouse", ctrl=ctrl, shift=shift, alt=False, meta=False)


def _key(name, ctrl=False, shift=False, alt=False, meta=False):
    return types_ns(key=name, ctrl=ctrl, alt=alt, shift=shift, meta=meta)


def _menu_labels(ui):
    return [r["label"] for r in ui.menu._rows if r["kind"] == "item"]


def _walk(control, depth=0):
    """Every control in a built subtree, so geometry can be asserted on it."""
    if control is None or isinstance(control, str) or depth > 30:
        return
    yield control
    for attr in ("controls", "actions"):
        for child in getattr(control, attr, None) or []:
            yield from _walk(child, depth + 1)
    yield from _walk(getattr(control, "content", None), depth + 1)


def _sized(root, width=None, height=None):
    """True when the subtree has at least one control of exactly this size."""
    for c in _walk(root):
        if width is not None and getattr(c, "width", None) != width:
            continue
        if height is not None and getattr(c, "height", None) != height:
            continue
        if width is None and getattr(c, "width", None) is not None:
            continue
        return True
    return False
