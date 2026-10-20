"""Проверка интерфейса на настоящем окне: щелчки и нажатия через xdotool.

Тесты без окна не видят, что происходит на стороне Flutter: например, что
поле поиска после щелчка теряло фокус и набранное никуда не шло. Здесь
запускается настоящий Centurio, а нажатия идут через X-сервер — как от
человека. Что дошло до программы, видно по снимку состояния, который она
пишет при `CENTURIO_UI_CHECK` (см. `app/ui/ui_check.py`).

Только Linux, нужны xdotool и X-сервер; обычно под виртуальным экраном:

    xvfb-run -a -s "-screen 0 1440x900x24" python scripts/ui_check.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

START_TIMEOUT = 120.0
STEP_TIMEOUT = 15.0
APPS = ("Telegram", "Microsoft Teams", "Google Chrome", "Visual Studio Code", "Slack",
        "Notion", "Figma", "Spotify")


class CheckFailed(Exception):
    pass


def make_library(folder: Path) -> None:
    from app.core.store import Store

    store = Store(str(folder / "Centurio" / "centurio-data.json"))
    for name in APPS:
        store.add_app({"name": name, "path": f"/nonexistent/{name.lower()}.exe",
                       "category_id": "work"})
    for key, value in (("win_w", 1280), ("win_h", 800), ("win_x", 40), ("win_y", 40),
                       ("hide_after", False), ("tray_hint_shown", True),
                       ("first_run_done", True), ("autostart_adopted", True)):
        store.set_setting(key, value, persist=False)
    store.flush()


class Session:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.state_path = workdir / "state.json"
        self.log_path = workdir / "app.log"
        self.proc = None
        self.wid = ""
        self.geometry = {}

    def start(self) -> None:
        env = dict(os.environ, APPDATA=str(self.workdir), CENTURIO_NO_DIALOG="1",
                   CENTURIO_UI_CHECK=str(self.state_path))
        env.pop("CENTURIO_WEB", None)
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT),
                                     env=env, stdout=open(self.log_path, "w"),
                                     stderr=subprocess.STDOUT)
        self.wait(lambda s: True, "приложение пишет состояние", START_TIMEOUT)
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            out = self.xdo("search", "--onlyvisible", "--name", "^Centurio$", check=False)
            if out:
                self.wid = out.split()[0]
                break
            time.sleep(0.5)
        if not self.wid:
            raise CheckFailed("окно Centurio так и не появилось")
        time.sleep(2)
        for line in self.xdo("getwindowgeometry", "--shell", self.wid).splitlines():
            key, _, value = line.partition("=")
            if value.isdigit():
                self.geometry[key] = int(value)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    @staticmethod
    def xdo(*args, check=True) -> str:
        res = subprocess.run(["xdotool", *args], capture_output=True, text=True, timeout=30)
        if check and res.returncode != 0:
            raise CheckFailed(f"xdotool {' '.join(args)}: {res.stderr.strip()}")
        return res.stdout.strip()

    def state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def wait(self, cond, what: str, timeout: float = STEP_TIMEOUT) -> dict:
        deadline = time.monotonic() + timeout
        last = {}
        while time.monotonic() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise CheckFailed(f"Centurio завершился (код {self.proc.returncode}) — {what}")
            last = self.state()
            if last and cond(last):
                return last
            time.sleep(0.1)
        raise CheckFailed(f"не дождался: {what}. Состояние: {json.dumps(last, ensure_ascii=False)}")

    def click(self, x: int, y: int) -> None:
        gx, gy = self.geometry.get("X", 0) + x, self.geometry.get("Y", 0) + y
        self.xdo("mousemove", "--sync", str(gx), str(gy))
        self.xdo("click", "1")

    def click_search(self) -> None:
        self.click(self.geometry.get("WIDTH", 1280) // 2, 26)

    def type(self, text: str) -> None:
        self.xdo("type", "--delay", "90", text)

    def key(self, *names: str) -> None:
        self.xdo("key", *names)


def scenarios(s: Session):
    def search_takes_text_after_click():
        s.click_search()
        s.type("tel")
        s.wait(lambda st: st["query"] == "tel" and st["palette_open"],
               "после щелчка по строке поиска набранное «tel» дошло до программы")

    def enter_launches_first_row():
        first = s.state()["palette"][0]
        s.key("Return")
        s.wait(lambda st: st["launched"][-1:] == [first] and not st["palette_open"],
               f"Enter запустил первую строку ({first}) и закрыл палитру")

    def second_click_keeps_focus():
        s.click_search()
        s.type("vis")
        s.wait(lambda st: st["query"] == "vis", "набрано «vis»")
        s.click_search()
        s.type("u")
        s.wait(lambda st: st["query"] == "visu",
               "повторный щелчок по строке поиска не сбросил фокус")
        s.key("ctrl+a", "BackSpace")
        s.wait(lambda st: st["query"] == "", "строка очищена")

    def arrows_pick_the_row_to_launch():
        s.type("te")
        st = s.wait(lambda st: st["query"] == "te" and len(st["palette"]) >= 2,
                    "на «te» нашлось хотя бы две строки")
        s.key("Down")
        s.wait(lambda st: st["palette_index"] == 1, "стрелка вниз выбрала вторую строку")
        second = st["palette"][1]
        s.key("Return")
        s.wait(lambda st: st["launched"][-1:] == [second],
               f"Enter запустил выбранную стрелкой строку ({second})")

    def ctrl_k_opens_search():
        s.key("ctrl+k")
        s.type("chr")
        s.wait(lambda st: st["query"] == "chr" and st["palette"][:1] == ["Google Chrome"],
               "Ctrl+K ставит курсор в поиск, «chr» находит Chrome")
        s.key("Escape")
        s.wait(lambda st: not st["palette_open"], "Esc закрыл палитру")

    def settings_open_and_close():
        s.key("ctrl+comma")
        s.wait(lambda st: st["screen"] == "settings", "Ctrl+, открыл настройки")
        s.key("Escape")
        s.wait(lambda st: st["screen"] == "grid", "Esc вернул к библиотеке")

    return [search_takes_text_after_click, enter_launches_first_row,
            second_click_keeps_focus, arrows_pick_the_row_to_launch,
            ctrl_k_opens_search, settings_open_and_close]


def screenshot(path: Path) -> None:
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
    except Exception as exc:
        print(f"  (снимок экрана не вышел: {exc})")


def main() -> int:
    if not shutil.which("xdotool") or not os.environ.get("DISPLAY"):
        print("Нужны xdotool и X-сервер (DISPLAY); запустите через xvfb-run.")
        return 2
    out_dir = Path(os.environ.get("UI_CHECK_OUT") or ROOT / "ui-check-output")
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        session = Session(Path(tmp))
        make_library(Path(tmp))
        try:
            session.start()
            for check in scenarios(session):
                label = check.__name__.replace("_", " ")
                try:
                    check()
                    print(f"ok    {label}")
                except CheckFailed as exc:
                    failed += 1
                    print(f"FAIL  {label}: {exc}")
                    screenshot(out_dir / f"{check.__name__}.png")
        except CheckFailed as exc:
            failed += 1
            print(f"FAIL  запуск: {exc}")
            screenshot(out_dir / "start.png")
        finally:
            session.stop()
            shutil.copy(session.log_path, out_dir / "app.log")
    print("Проверка интерфейса: " + ("всё прошло" if not failed else f"провалено {failed}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
