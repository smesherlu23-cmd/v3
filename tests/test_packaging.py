"""Сборка, выпуск и устройство проекта: версии, слои, README, CI."""
import os
import tempfile
from pathlib import Path

from helpers import _ROOT, _read, _sources, _summarize, ok, skip

from app.core.store import Store
from app.ui import colors as C


def test_ci_skip_escalation():
    """A Flet skip is fine for a local run and a failure under CI.

    The workflow installs Flet as a hard requirement (no `pip install ... ||
    echo` fallback), but that alone doesn't catch every way the install can
    come up broken — a wrong-platform wheel, a partial install that satisfies
    `pip` but not `import flet`. _summarize() is the second guard: it turns a
    skip into a failure whenever CI=true, which GitHub Actions sets on every
    run, so a skip there can never quietly report success.
    """
    code, line = _summarize(10, 0, [], is_ci=True)
    ok(code == 0 and "10 passed, 0 failed" in line, "no skips, CI=true -> still green")

    code, line = _summarize(10, 0, ["UI tests"], is_ci=False)
    ok(code == 0, "a skip outside CI is not a failure (local run without Flet)")
    ok("1 skipped" in line, "the report mentions the skip even when it isn't fatal")

    code, line = _summarize(10, 0, ["UI tests", "UI settings-cache test"], is_ci=True)
    ok(code == 1, "any skip under CI fails the run")
    ok("1 failed" in line and "2 skipped" in line,
       "escalation adds one failure and the report still names the skip count")
    ok("UI tests" in line, "the escalation names the skipped tests in the returned report")

    code, line = _summarize(10, 0, [], is_ci=True)
    ok("FAIL" not in line, "a clean run's report carries no failure text")

    code, line = _summarize(10, 2, [], is_ci=True)
    ok(code == 1 and "2 failed" in line, "a genuine failure with no skips isn't inflated by escalation")


def test_no_duplicate_icon_lists():
    """format.ICON_PACK is the one list of category icons.

    store.CATEGORY_ICONS and format.CATEGORY_ICON_CHOICES were byte-identical
    copies of each other that nothing read.
    """
    from app.core import store as store_mod
    try:
        from app.ui import format as fmt
    except Exception as exc:
        skip("no-duplicate-icon-lists test", exc)
        return

    ok(not hasattr(store_mod, "CATEGORY_ICONS"), "store carries no icon list of its own")
    ok(not hasattr(fmt, "CATEGORY_ICON_CHOICES"), "the unread choices copy is gone")
    ok(isinstance(fmt.ICON_PACK, list) and len(fmt.ICON_PACK) > 10,
       "ICON_PACK is the surviving list")
    ok(not any("CATEGORY_ICON" in src for _label, src in _sources("ui")),
       "the UI no longer imports a constant it never used")


def test_controllers_depend_only_on_the_public_ui_surface():
    """Контроллеры знают об интерфейсе лишь его публичную поверхность — UIHost.

    `CenturioUI` — объект-бог (132 метода, 62 поля), и контроллеры получают
    его целиком. Чтобы связь не расползалась (С-1/С-2 в ATTESTATION.md), она
    сужена до протокола `UIHost`: контроллеры не лезут в приватные `ui._…` и
    не зовут ничего, чего в протоколе нет. Обход AST держит обе границы.
    """
    import ast

    from app.controllers.host import UIHost

    allowed = set(UIHost.__annotations__) | {
        n for n, v in vars(UIHost).items() if not n.startswith("_") and callable(v)}

    private: list[str] = []
    unknown: list[str] = []
    for label, src in _sources("controllers"):
        if label.endswith("controllers/host.py"):
            continue
        for node in ast.walk(ast.parse(src)):
            # Обращения вида `self.ui.<member>` или `ui.<member>`.
            if not isinstance(node, ast.Attribute):
                continue
            base = node.value
            is_ui = (isinstance(base, ast.Name) and base.id == "ui") or (
                isinstance(base, ast.Attribute) and base.attr == "ui"
                and isinstance(base.value, ast.Name) and base.value.id == "self")
            if not is_ui:
                continue
            if node.attr.startswith("_"):
                private.append(f"{label}: ui.{node.attr}")
            elif node.attr not in allowed:
                unknown.append(f"{label}: ui.{node.attr}")

    ok(not private, "controllers reach into UI privates: " + "; ".join(private))
    ok(not unknown,
       "controllers use UI members missing from UIHost (add them to the protocol): "
       + "; ".join(sorted(set(unknown))))


def test_domain_types_match_runtime_shapes():
    """TypedDict-схема домена не расходится с тем, что реально кладётся в dict.

    `app/core/types.py` — единственное авторитетное определение формы записей.
    Толку от него ноль, если оно тихо отстанет от `Store`/`sanitize`, поэтому
    ключи сверяются с настоящими записями: добавил поле в запись, забыл в тип
    (или наоборот) — тест красный.
    """
    from app.core import types
    from app.core.store import sanitize

    def keys(td) -> set:
        return set(td.__annotations__)

    ok(keys(types.Settings) == set(sanitize.DEFAULT_SETTINGS),
       "Settings covers exactly the default settings keys")

    with tempfile.TemporaryDirectory() as d:
        store = Store(os.path.join(d, "data.json"))
        rec = store.add_app({"name": "X", "path": "C:/x.exe"})
        ok(set(rec) == keys(types.App),
           f"App matches a stored record (diff: {set(rec) ^ keys(types.App)})")

    cat = sanitize.clean_category(
        {"id": "c", "name": "n", "icon": "i", "color": "#fff", "order": 0}, 0)
    ok(set(cat) == keys(types.Category), "Category matches clean_category output")

    layout = sanitize.clean_layout({})
    ok(set(layout) == keys(types.SetLayout), "SetLayout matches clean_layout output")

    item = sanitize.clean_item({"app_id": "a"}, "half", 0)
    ok(set(item) == keys(types.SetItem), "SetItem matches clean_item output")

    aset = sanitize.clean_set({"id": "s", "name": "n", "items": [{"app_id": "a"}]}, 0)
    ok(set(aset) == keys(types.AppSet),
       f"AppSet matches clean_set output (diff: {set(aset) ^ keys(types.AppSet)})")

    inbox = sanitize.clean_inbox({"path": "C:/p.exe", "name": "n"}, 0)
    ok(set(inbox) == keys(types.InboxItem), "InboxItem matches clean_inbox output")


def test_release_notes_and_package_manifests():
    """Релиз по тегу берёт описание из CHANGELOG.md и выкладывает манифесты winget/scoop."""
    import importlib.util
    import json as _json

    from app import __version__

    def load(name):
        spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, "scripts",
                                                                          f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    notes = load("release_notes")
    ok(notes.notes_for(__version__), f"CHANGELOG.md has a section for {__version__}, "
                                     "or a tag for this version would stop the release")
    sample = "# x\n\n## 2.0.0\n\n- новое\n\n## 1.0.0\n\n- старое\n"
    ok(notes.notes_for("2.0.0", sample) == "- новое", "only that version's section is taken")
    ok(notes.notes_for("3.0.0", sample) is None, "and a missing one is reported, not invented")
    body = notes.release_body("- новое", unsigned=True)
    ok(body.startswith("- новое") and "CenturioSetup.exe" in body
       and "Выполнить в любом случае" in body,
       "the release page says which file to take and how to get past the unsigned-build warning")
    ok("Выполнить в любом случае" not in notes.release_body("- новое", unsigned=False),
       "and drops that warning once the build is signed")

    manifests = load("package_manifests")
    with tempfile.TemporaryDirectory() as d:
        written = manifests.build("1.2.3", "AB" * 32, Path(d))
        names = sorted(p.name for p in written)
        ok(names == ["Centurio.Centurio.installer.yaml", "Centurio.Centurio.locale.ru-RU.yaml",
                     "Centurio.Centurio.yaml", "centurio.json"],
           f"winget gets its three files, scoop its one ({names})")
        scoop = _json.loads((Path(d) / "scoop" / "centurio.json").read_text(encoding="utf-8"))
        url = scoop["architecture"]["64bit"]["url"]
        ok(url.endswith("/releases/download/v1.2.3/CenturioSetup.exe")
           and scoop["architecture"]["64bit"]["hash"] == "ab" * 32,
           "scoop points at this release's installer and its hash")
        installer = next(p for p in written if p.name.endswith(".installer.yaml"))
        text = installer.read_text(encoding="utf-8")
        ok(url in text and "AB" * 32 in text and "_is1" in text,
           "winget gets the same installer, hash and the Inno Setup product code")
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is not None:
            for path in written:
                if path.suffix == ".yaml":
                    yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        manifests.build("1.2.3", "not-a-hash", Path(tempfile.gettempdir()))
        ok(False, "a broken hash must stop the release")
    except SystemExit:
        ok(True, "a broken hash stops the release")


def test_installer_respects_a_running_centurio():
    """Обновление и удаление не трогают запущенный Centurio.

    Он живёт в трее, а сообщение о новой версии ведёт ставить её, пока он
    работает. AppMutex установщика — мьютекс единственного экземпляра, и
    release.yml проверяет установщик (install_check.ps1) до публикации.
    """
    import re

    from app.infra import updates
    from app.platform import single_instance

    iss = _read("installer", "centurio.iss")
    m = re.search(r"^AppMutex=(.+)$", iss, re.M)
    ok(m and m.group(1).strip() == single_instance.MUTEX_NAME,
       "the installer's AppMutex is the app's single-instance mutex")
    check = _read("scripts", "install_check.ps1")
    ok(f'"{single_instance.MUTEX_NAME}"' in check,
       "install_check.ps1 waits for the same mutex before trying the upgrade")
    url = re.search(r'#define MyAppURL "([^"]+)"', iss)
    ok(url and url.group(1) == f"https://github.com/{updates.REPO}",
       "«Приложения» link to the repository the update check asks")

    release = _read(".github", "workflows", "release.yml")
    installer = release.find("ISCC.exe")
    check_step = release.find("install_check.ps1")
    publish = release.find("gh release create")
    ok(-1 < installer < check_step < publish,
       "release.yml installs, updates and removes the built installer before publishing it")


def test_packaging_metadata():
    """The version and the dependency list live in files that can't import
    each other, so the check that they agree belongs here."""
    import re

    from app import __version__

    ok(re.fullmatch(r"\d+\.\d+\.\d+", __version__), "app.__version__ is a plain version number")

    pyproject = _read("pyproject.toml")
    installer = _read("installer", "centurio.iss")
    ui_source = _read("app", "ui", "app.py")

    quoted = re.escape(f'"{__version__}"')
    ok(re.search(rf"^version = {quoted}$", pyproject, re.M),
       "pyproject [project].version matches app.__version__")
    ok(re.search(rf"^build_version = {quoted}$", pyproject, re.M),
       "pyproject [tool.flet].build_version matches app.__version__")
    ok(re.search(rf"#define MyAppVersion {quoted}", installer),
       "the installer's MyAppVersion matches app.__version__")
    ok(__version__ not in ui_source, "the sidebar footer renders the version instead of repeating it")

    readme = re.search(r'^readme = "([^"]+)"$', pyproject, re.M)
    ok(readme is not None, "pyproject declares a readme")
    ok(readme and os.path.exists(os.path.join(_ROOT, readme.group(1))),
       "the declared readme exists — otherwise `pip install .` fails on it")

    block = re.search(r"^dependencies = \[(.*?)^\]", pyproject, re.M | re.S)
    ok(block is not None, "pyproject declares dependencies")
    declared = set(re.findall(r'"([^"]+)"', block.group(1) if block else ""))
    required = {line.strip() for line in _read("requirements.txt").splitlines()
                if line.strip() and not line.startswith("#")}
    ok(declared == required,
       f"requirements.txt and pyproject agree (pyproject-only: {declared - required}, "
       f"requirements-only: {required - declared})")

    flet = re.search(r"flet\[desktop\]==([\d.]+)", _read("requirements.txt"))
    cli = re.search(r"flet-cli==([\d.]+)", _read(".github", "workflows", "release.yml"))
    ok(flet and cli and flet.group(1) == cli.group(1),
       "the release builds with flet-cli of the same version as flet itself")
    ok(re.search(r"flet build windows .*--yes", _read(".github", "workflows", "release.yml")),
       "and answers its «install Flutter SDK?» up front: the runner has no one to ask")


def test_release_fixes_the_code_page_and_runs_the_built_exe():
    """Релиз обязан перевести exe на UTF-8 и запустить его до подписи.

    serious_python передаёт пути в PYTHONHOME/PYTHONPATH узкими строками в
    UTF-8, а Windows читает их в cp1251. У пользователя с кириллицей в имени
    профиля собранный exe поэтому выходил с кодом 1 за секунду — без логов и
    без записей в журнале Windows; на windows-раннере это воспроизведено
    `smoke.ps1 -NonAsciiProfile` и вылечено манифестом activeCodePage=UTF-8.
    Порядок важен: правка ресурса ломает подпись, а непроверенный exe не
    должен доехать до установщика. `continue-on-error` превратил бы проверку
    в украшение.
    """
    text = _read(".github", "workflows", "release.yml")
    build = text.find("flet build windows")
    manifest = text.find("utf8_manifest.ps1")
    smoke = text.find("smoke.ps1 -BuildDir")
    cyrillic = text.find("-NonAsciiProfile")
    sign = text.find("sign.ps1")
    ok(-1 < build < manifest < smoke < sign, "release.yml: сборка → UTF-8 → запуск → подпись")
    ok(-1 < cyrillic < sign, "release.yml: запуск проверяется и в профиле с кириллицей")
    ok("continue-on-error" not in text, "release.yml: проверки не отключены молча")

    local = _read("scripts", "build_release.ps1")
    manifest = local.find("utf8_manifest.ps1")
    ok(-1 < local.find("flet build windows") < manifest < local.find("sign.ps1"),
       "локальная сборка тоже переводит exe на UTF-8 до подписи")


def test_app_package_leaves_the_repository_out():
    """В app.zip уезжает только приложение, а не весь репозиторий.

    С `[tool.flet.app] path = "."` и без списка исключений в дистрибутив
    попадали .git (на раннере в .git/config лежал токен actions/checkout),
    тесты, скрипты сборки и кэши — это видно в распакованном приложении у
    пользователя. serious_python сравнивает исключения с точным путём от
    корня проекта, поэтому каталоги перечислены поимённо.
    """
    import re

    pyproject = _read("pyproject.toml")
    section = re.search(r"^\[tool\.flet\.app\]\n(.*?)(?=^\[|\Z)", pyproject, re.M | re.S)
    ok(section is not None, "pyproject содержит [tool.flet.app]")
    block = re.search(r"^exclude = \[(.*?)^\]", section.group(1) if section else "", re.M | re.S)
    excluded = set(re.findall(r'"([^"]+)"', block.group(1) if block else ""))
    for name in (".git", ".github", "tests", "scripts", "installer",
                 ".pytest_cache", ".ruff_cache"):
        ok(name in excluded, f"{name} не упаковывается в дистрибутив")
    for name in ("app", "assets", "main.py"):
        ok(name not in excluded, f"{name} нужен приложению и остаётся в пакете")

    release = _read(".github", "workflows", "release.yml")
    ok("persist-credentials: false" in release,
       "релизная сборка не оставляет токен в .git/config")


def test_readme_points_at_files_that_exist():
    """README не должен описывать то, чего в репозитории нет.

    Раздел «Релиз» пережил удаление `scripts/build_release.ps1` и продолжал
    описывать скрипт с его флагами и `Get-Help`, которого не было: новый
    разработчик шёл по инструкции и упирался в пустоту. Проверяются только
    пути внутри репозитория — то, что появляется при сборке или при работе
    программы, сюда не попадает.
    """
    import re

    roots = ("app", "tests", "scripts", "installer", "assets", ".github")
    generated = ("installer/Output",)

    mentioned = set()
    for word in re.split(r"[\s`|(),]+", _read("README.md")):
        path = word.replace("\\", "/")
        if path.startswith("./"):
            path = path[2:]
        path = path.rstrip(".,;:")
        if "/" not in path or path.split("/")[0] not in roots:
            continue
        if path.startswith(generated):
            continue
        mentioned.add(path)

    ok(len(mentioned) >= 8, f"README вообще ссылается на файлы репозитория ({mentioned})")
    missing = sorted(p for p in mentioned if not os.path.exists(os.path.join(_ROOT, p)))
    ok(not missing, f"README ссылается на несуществующее: {missing}")


def test_no_global_hotkeys():
    """Ни хуков клавиатуры, ни системных сочетаний.

    `SetWindowsHookEx(WH_KEYBOARD_LL)` (pynput.GlobalHotKeys) получает каждое
    нажатие в системе — по этому признаку антивирусы опознают кейлоггер.
    `RegisterHotKey` отбирал Ctrl+1…9 у браузеров и офиса, а Ctrl+Alt+N на
    раскладках с AltGr — символы. Клавиши Centurio работают только в его окне.
    """
    import io
    import re
    import tokenize

    def _code_only(src: str) -> str:
        # Отбрасываем комментарии и строковые литералы, чтобы объяснение
        # в docstring, где эти имена и должны звучать, не считалось нарушением.
        out = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                    out.append(tok.string)
        except tokenize.TokenError:
            return src
        return "\n".join(out)

    offenders = []
    for path in sorted((Path(_ROOT) / "app").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        code = _code_only(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(_ROOT))
        if re.search(r"\bpynput\b", code):
            offenders.append(f"{rel}: references pynput")
        if "GlobalHotKeys" in code:
            offenders.append(f"{rel}: uses pynput GlobalHotKeys")
        if re.search(r"SetWindowsHookEx|WH_KEYBOARD", code):
            offenders.append(f"{rel}: installs a keyboard hook")
        if re.search(r"RegisterHotKey|WM_HOTKEY", code):
            offenders.append(f"{rel}: registers a system-wide hotkey")
    ok(not offenders, "keyboard-hook signatures crept back in: " + "; ".join(offenders))

    pyproject = _read("pyproject.toml")
    requirements = _read("requirements.txt")
    ok("pynput" not in pyproject, "pynput is gone from pyproject dependencies")
    ok("pynput" not in requirements, "pynput is gone from requirements.txt")


def test_single_entry_point():
    """app/main.py builds the page; only the root main.py launches it."""
    root_main = _read("main.py")
    page_module = _read("app", "main.py")
    ok('if __name__ == "__main__"' in root_main and "ft.run(" in root_main,
       "the root main.py starts the app")
    ok('host="127.0.0.1"' in root_main,
       "the browser mode listens on this machine only — it can launch any program")
    # app/main.py still reads CENTURIO_WEB — that's is_web inside the page
    # builder, not a second launcher.
    ok('if __name__ == "__main__"' not in page_module,
       "app/main.py doesn't carry a second entry point")
    code = "\n".join(line for line in page_module.splitlines()
                     if not line.lstrip().startswith("#"))
    ok("ft.run(" not in code and "ft.app(" not in code, "app/main.py doesn't start Flet itself")


def test_no_modal_dialogs():
    """Приёмка: ни одного AlertDialog в коде."""
    screens = _sources("ui", "main.py")
    for label, source in screens:
        ok("AlertDialog(" not in source, f"{label} opens no modal dialog")
        ok("SnackBar(" not in source, f"{label} doesn't fall back to a snack bar")

    everything = "".join(source for _label, source in screens)
    for gone in ("open_app_dialog", "open_context_menu", "open_settings_dialog",
                 "open_categories_dialog", "def confirm("):
        ok(gone not in everything, f"the old {gone.strip('def (')} entry point is gone")


def test_translucent_colours_put_alpha_first():
    """Приёмка: восьмизначный цвет — это #AARRGGBB, а не CSS-порядок.

    Записанный по-CSS (#RRGGBBAA) он молча превращается в прозрачный: у всех
    теней альфа выходила 00, а затемнение под палитрой давало синеватый оттенок
    вместо затемнения. Глазами это видно только в собранном окне, поэтому
    правило сторожит тест.
    """
    import re

    offenders = []
    for name in dir(C):
        if name.startswith("_"):
            continue
        values = getattr(C, name)
        for value in (values if isinstance(values, tuple) else [values]):
            if not (isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{8}", value)):
                continue
            alpha, rgb = value[1:3], value[3:]
            # Полностью прозрачный цвет — единственный, у кого альфа 00.
            if int(alpha, 16) == 0 and int(rgb, 16) != 0:
                offenders.append(f"C.{name} = {value}")
    ok(not offenders,
       "alpha comes first in every translucent colour: "
       + ("; ".join(offenders) or "all good"))

    ok(C.with_alpha("#112233", 0.5) == "#80112233",
       "with_alpha() builds #AARRGGBB too")
    ok(C.with_alpha("#112233", 1) == "#ff112233", "opaque is ff, not 00")


def test_colours_come_from_one_file():
    """Приёмка: в интерфейсе нет цветов, которых нет в app/colors.py.

    Иначе редизайн растекается по файлам: один и тот же серый оказывается
    #23232b в одном месте и #23232c в другом, и починить это уже негде.
    """
    import re

    offenders = []
    for label, source in _sources("ui"):
        if label.endswith("ui/colors.py"):
            continue
        for index, line in enumerate(source.splitlines(), 1):
            for hexval in re.findall(r'"(#[0-9a-fA-F]{3,8})"', line):
                offenders.append(f"{label}:{index} {hexval}")
    ok(not offenders,
       "every colour is a token: " + ("; ".join(offenders[:5]) or "no literals"))


def test_ui_text_stays_inside_the_bundled_fonts():
    """Приёмка: интерфейс не показывает символов, которых нет в наших шрифтах.

    Flet ships only what assets/fonts holds, and a codepoint none of them covers
    is drawn as an empty box — «↵» looked like a stray dot in the menus until
    this was noticed. Rather than parse five cmap tables, the check works from
    the other side: letters, digits and a short list of symbols known to be
    present. Anything else has to be justified by adding it here.
    """
    import ast
    import unicodedata

    allowed = set("«»—–…·×→↑↓№°")
    offenders = []
    for label, source in _sources("ui", "core", "platform/windows.py"):
        module = label
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for ch in node.value:
                if ord(ch) < 128 or ch.isalpha() or ch in allowed:
                    continue
                offenders.append(f"{module}:{node.lineno} {ch!r} "
                                 f"({unicodedata.name(ch, '?')})")
    ok(not offenders, "every character shown has a glyph: " + ("; ".join(offenders[:5])
                                                               or "none missing"))
    ok(not any("↵" in source for _label, source in _sources("ui")),
       "the Enter arrow in particular is spelled out, because no bundled font has it")
