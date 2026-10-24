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
import signal
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
    # 1280×720 — размер, с которым клиент Flet под Linux создаёт окно. Если
    # программа сразу просит другой, клиент на экране без видеокарты в
    # нескольких запусках из ста падает на этом изменении размера (SIGSEGV
    # после «Timed out waiting for OpenGL frame»), и Centurio выходит до окна.
    for key, value in (("win_w", 1280), ("win_h", 720), ("win_x", 40), ("win_y", 40),
                       ("hide_after", False), ("tray_hint_shown", True),
                       ("first_run_done", True), ("autostart_adopted", True),
                       ("check_updates", False), ("debug_log", True)):
        store.set_setting(key, value, persist=False)
    store.flush()


class Session:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.state_path = workdir / "state.json"
        self.log_path = workdir / "app.log"
        self.proc = None
        self.geometry = {}

    def start(self) -> None:
        # Клиент Flet под Linux на экране без видеокарты может упасть при
        # старте (см. размер окна в make_library). Повтор один, и он виден в
        # выводе; второй провал — настоящий.
        try:
            self._start_once()
        except CheckFailed as exc:
            print(f"  запуск не удался ({exc}) — повторяю один раз")
            self.stop()
            self._start_once()

    def _start_once(self) -> None:
        self.state_path.unlink(missing_ok=True)
        env = dict(os.environ, APPDATA=str(self.workdir), CENTURIO_NO_DIALOG="1",
                   CENTURIO_UI_CHECK=str(self.state_path))
        env.pop("CENTURIO_WEB", None)
        # Своя группа процессов: клиент Flet — дочерний процесс Python, и при
        # остановке его надо гасить вместе с программой, иначе окна копятся.
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT),
                                     env=env, stdout=open(self.log_path, "a"),
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.wait(lambda s: True, "приложение пишет состояние", START_TIMEOUT)
        # Клиент Flet 1.0 может пересоздать окно после первого показа, и номер,
        # найденный слишком рано, к запросу размеров уже недействителен. Окно
        # считается готовым, когда два замера подряд совпали.
        deadline = time.monotonic() + START_TIMEOUT
        last = {}
        while time.monotonic() < deadline:
            time.sleep(1)
            if self.proc.poll() is not None:
                raise CheckFailed(f"Centurio завершился (код {self.proc.returncode}) до окна")
            current = self.window_geometry()
            if current and current == last:
                self.geometry = current
                return
            last = current
        raise CheckFailed("окно Centurio так и не появилось")

    def window_geometry(self) -> dict:
        found = self.xdo("search", "--onlyvisible", "--name", "^Centurio$", check=False)
        if not found:
            return {}
        geometry = {}
        out = self.xdo("getwindowgeometry", "--shell", found.split()[0], check=False)
        for line in out.splitlines():
            key, _, value = line.partition("=")
            if value.isdigit():
                geometry[key] = int(value)
        return geometry if "WIDTH" in geometry else {}

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        # Клиент Flet из той же группы мог пережить Python: добиваем всю группу.
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait(10)

    @staticmethod
    def xdo(*args, check=True) -> str:
        try:
            res = subprocess.run(["xdotool", *args], capture_output=True, text=True,
                                 timeout=30)
        except subprocess.TimeoutExpired as exc:
            raise CheckFailed(f"xdotool {' '.join(args)} не ответил за 30 с") from exc
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

    def click(self, x: int, y: int, button: str = "1") -> None:
        gx, gy = self.geometry.get("X", 0) + x, self.geometry.get("Y", 0) + y
        # Без --sync: если указатель уже стоит в этой точке (второй щелчок по
        # тому же месту), xdotool ждёт движения, которого не будет.
        self.xdo("mousemove", str(gx), str(gy))
        time.sleep(0.1)
        self.xdo("click", button)

    def drag(self, start: tuple[int, int], end: tuple[int, int], steps: int = 8) -> None:
        """Как человек: нажал, подержал, повёл и отпустил."""
        ox, oy = self.geometry.get("X", 0), self.geometry.get("Y", 0)
        (x0, y0), (x1, y1) = start, end
        self.xdo("mousemove", str(ox + x0), str(oy + y0))
        time.sleep(0.1)
        self.xdo("mousedown", "1")
        # Дольше 100 мс, после которых Flutter уже сообщает о нажатии.
        time.sleep(0.3)
        for i in range(1, steps + 1):
            self.xdo("mousemove", str(ox + x0 + (x1 - x0) * i // steps),
                     str(oy + y0 + (y1 - y0) * i // steps))
            time.sleep(0.05)
        time.sleep(0.2)
        self.xdo("mouseup", "1")

    def click_search(self) -> None:
        # Человек щёлкает по тому, что уже видит (см. human_pause).
        self.human_pause()
        self.click(self.geometry.get("WIDTH", 1280) // 2, 26)

    def type(self, text: str) -> None:
        self.xdo("type", "--delay", "90", text)

    def key(self, *names: str) -> None:
        self.xdo("key", *names)

    @staticmethod
    def human_pause() -> None:
        """Пауза человека: он нажимает, глядя на то, что уже нарисовано.

        xdotool печатает по 90 мс на букву, а на раннере CI без видеокарты
        кадры отстают сильнее. Снимки строки поиска с раннера показали, что
        из этого выходит: щелчок ставит курсор в конец того текста, который
        успел отрисоваться («vis» набрано, нарисовано «v» — курсор после
        «v»), а значение, пришедшее из Python (очистка поля после запуска
        или Ctrl+K), Flet применяет к полю только со следующим кадром — и
        буквы, набранные раньше, ложатся в старый текст. Путь «клавиша →
        Python → Flutter» тоже бывает дольше 90 мс, и первая буква после
        Ctrl+K уходила мимо.
        """
        time.sleep(1.0)


# «+» в заголовке окна 1280×720 — левее кнопок окна и выбора нескольких.
ADD_BUTTON = (1124, 25)
# Середина значка первой программы (по алфавиту это Figma): над ней полка
# «Быстрый запуск» и заголовок категории.
FIRST_TILE = (316, 300)


def scenarios(s: Session):
    def search_takes_text_after_click():
        s.click_search()
        s.type("tel")
        s.wait(lambda st: st["query"] == "tel" and st["palette_open"]
               and st["palette"][:1] == ["Telegram"],
               "после щелчка по строке поиска набранное «tel» дошло до программы")

    def enter_launches_first_row():
        first = s.state()["palette"][0]
        s.key("Return")
        s.wait(lambda st: st["launched"][-1:] == [first] and not st["palette_open"],
               f"Enter запустил первую строку ({first}) и закрыл палитру")
        # Enter сам снимает фокус с поля (так делает Flutter), а Python в тот же
        # миг его очищает. Человек не щёлкает обратно в поиск через 0,2 с.
        s.human_pause()

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
        st = s.wait(lambda st: st["query"] == st["palette_query"] == "te"
                    and len(st["palette"]) >= 2,
                    "на «te» нашлось хотя бы две строки")
        s.key("Down")
        s.wait(lambda st: st["palette_index"] == 1, "стрелка вниз выбрала вторую строку")
        second = st["palette"][1]
        s.key("Return")
        s.wait(lambda st: st["launched"][-1:] == [second],
               f"Enter запустил выбранную стрелкой строку ({second})")

    def ctrl_k_opens_search():
        s.key("ctrl+k")
        s.human_pause()
        s.type("chr")
        s.wait(lambda st: st["query"] == "chr" and st["palette"][:1] == ["Google Chrome"],
               "Ctrl+K ставит курсор в поиск, «chr» находит Chrome")
        s.key("Escape")
        s.wait(lambda st: not st["palette_open"], "Esc закрыл палитру")

    def tab_keeps_typing_in_the_search():
        # Над «Найти и добавить»: там своё поле ввода, куда Flutter уводил
        # фокус по Tab, — и продолжение запроса набиралось туда.
        s.click(*ADD_BUTTON)
        s.wait(lambda st: st["screen"] == "add", "открылся экран «Найти и добавить»")
        s.key("ctrl+k")
        s.human_pause()
        s.type("tel")
        s.wait(lambda st: st["query"] == "tel", "набрано «tel»")
        s.key("Tab")
        s.wait(lambda st: st["palette_focus"] == "actions", "Tab перевёл выбор на действия")
        s.human_pause()
        s.type("e")
        # Вернувшийся фокус Flutter может выделить весь запрос, и буква его
        # заменит («e» вместо «tele») — это не страшно. Страшно было, когда
        # буквы уходили в другое поле окна и меняли, например, цвет или имя.
        s.wait(lambda st: st["query"] in ("tele", "e") and st["typing"] == "search"
               and not st["add_query"] and not st["add_path"],
               "после Tab буквы по-прежнему идут в поиск, а не в другое поле окна")
        s.key("Escape")
        s.wait(lambda st: not st["palette_open"], "Esc закрыл палитру")
        s.key("Escape")
        s.wait(lambda st: st["screen"] == "grid", "Esc вернул к библиотеке")

    def settings_open_and_close():
        s.key("ctrl+comma")
        s.wait(lambda st: st["screen"] == "settings", "Ctrl+, открыл настройки")
        s.key("Escape")
        s.wait(lambda st: st["screen"] == "grid", "Esc вернул к библиотеке")

    def dragging_a_tile_does_not_launch_it():
        tile = FIRST_TILE
        before = s.state()["launched"]
        s.drag(tile, (tile[0], tile[1] + 260))
        time.sleep(1)
        if s.state()["launched"] != before:
            raise CheckFailed("плитку только перетащили, а программа запустилась")
        # Щелчок по той же точке: убеждаемся, что тянули именно плитку.
        s.click(*tile)
        s.wait(lambda st: st["launched"] == [*before, "Figma"],
               "щелчок по той же плитке запустил Figma")

    def right_click_opens_the_menu():
        # Правый щелчок по плитке — меню, как везде в Windows, а не панель
        # свойств; сама плитка при этом не запускается.
        before = s.state()["launched"]
        s.human_pause()
        s.click(*FIRST_TILE, button="3")
        s.wait(lambda st: st["menu"] and not st["inspector"],
               "правый щелчок открыл меню плитки, а не панель свойств")
        s.key("Escape")
        s.wait(lambda st: not st["menu"], "Esc закрыл меню")
        if s.state()["launched"] != before:
            raise CheckFailed("правый щелчок запустил программу")

    return [search_takes_text_after_click, enter_launches_first_row,
            second_click_keeps_focus, arrows_pick_the_row_to_launch,
            ctrl_k_opens_search, tab_keeps_typing_in_the_search, settings_open_and_close,
            right_click_opens_the_menu, dragging_a_tile_does_not_launch_it]


def screenshot(path: Path) -> None:
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
    except Exception as exc:
        print(f"  (снимок экрана не вышел: {exc})")


def print_search_strip(session: Session) -> None:
    """Строка поиска как она видна на экране — прямо в вывод.

    Артефакт со снимками в CI не всегда доступен тому, кто разбирает
    провал, а по одному снимку состояния не понять, что на самом деле в
    поле и где курсор. Полоса 640×36 в оттенках серого — несколько КБ base64.
    """
    try:
        import base64
        import io

        from PIL import ImageGrab
        g = session.geometry
        cx = g.get("X", 0) + g.get("WIDTH", 1280) // 2
        top = g.get("Y", 0) + 8
        strip = ImageGrab.grab(bbox=(cx - 320, top, cx + 320, top + 36)).convert("L")
        buf = io.BytesIO()
        strip.quantize(16).save(buf, "PNG", optimize=True)
        pointer = session.xdo("getmouselocation", check=False)
        print(f"  окно {g}, указатель: {pointer}")
        print(f"  строка поиска (PNG base64): {base64.b64encode(buf.getvalue()).decode()}")
    except Exception as exc:
        print(f"  (полоса поиска не вышла: {exc})")


def main() -> int:
    if not shutil.which("xdotool") or not os.environ.get("DISPLAY"):
        print("Нужны xdotool и X-сервер (DISPLAY); запустите через xvfb-run.")
        return 2
    out_dir = Path(os.environ.get("UI_CHECK_OUT") or ROOT / "ui-check-output")
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    start_failed = False
    with tempfile.TemporaryDirectory() as tmp:
        session = Session(Path(tmp))
        make_library(Path(tmp))
        try:
            session.start()
            # Как выглядит библиотека в начале — по снимку видно, куда целятся
            # щелчки сценариев, если окно поменялось.
            screenshot(out_dir / "library.png")
            for check in scenarios(session):
                label = check.__name__.replace("_", " ")
                try:
                    check()
                    print(f"ok    {label}")
                except CheckFailed as exc:
                    failed += 1
                    print(f"FAIL  {label}: {exc}")
                    screenshot(out_dir / f"{check.__name__}.png")
                    if failed == 1:
                        print_search_strip(session)
        except CheckFailed as exc:
            failed += 1
            start_failed = True
            print(f"FAIL  запуск: {exc}")
            screenshot(out_dir / "start.png")
        finally:
            session.stop()
            shutil.copy(session.log_path, out_dir / "app.log")
            for name in ("centurio.log", "centurio-crash.log"):
                own = Path(tmp) / "Centurio" / name
                if own.exists():
                    shutil.copy(own, out_dir / name)
    if start_failed:
        # Программа закрылась до окна — значит, закрылся клиент Flet, и
        # причина в его выводе, а не в centurio.log.
        print("--- вывод программы и клиента Flet ---")
        lines = (out_dir / "app.log").read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join(lines[-60:]))
    own_log = out_dir / "centurio.log"
    if failed and own_log.exists():
        # Хвост лога прямо в выводе: в CI это видно без скачивания артефакта.
        print("--- centurio.log: поле поиска и ошибки ---")
        lines = own_log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join([ln for ln in lines if "ui-check:" in ln or "ERROR" in ln][-60:]))
    print("Проверка интерфейса: " + ("всё прошло" if not failed else f"провалено {failed}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
