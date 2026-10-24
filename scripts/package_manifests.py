"""Манифесты для winget и scoop по готовому релизу.

Вызывается из .github/workflows/release.yml после сборки установщика:

    python scripts/package_manifests.py --version 1.3.0 --sha256 <хеш> --out <папка>

Получается папка с файлами, которые остаётся отправить в каталоги:
winget — pull request в microsoft/winget-pkgs (папка `winget/manifests/…`
копируется как есть), scoop — файл `scoop/centurio.json` в свой bucket.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.infra.updates import REPO  # noqa: E402

PACKAGE_ID = "Centurio.Centurio"
MANIFEST_VERSION = "1.6.0"
# Каталоги требуют поле лицензии. Пока в репозитории нет LICENSE — так.
LICENSE = "Proprietary"


def _iss_define(name: str) -> str:
    text = (ROOT / "installer" / "centurio.iss").read_text(encoding="utf-8")
    m = re.search(rf'^#define {name} "([^"]*)"', text, re.M)
    if not m:
        raise SystemExit(f"в installer/centurio.iss нет #define {name}")
    return m.group(1)


def _app_id() -> str:
    text = (ROOT / "installer" / "centurio.iss").read_text(encoding="utf-8")
    m = re.search(r"^AppId=\{(\{[0-9A-Fa-f-]+\})\}", text, re.M)
    if not m:
        raise SystemExit("в installer/centurio.iss нет AppId")
    return m.group(1)


def _q(value) -> str:
    # Строка JSON — допустимая строка YAML в двойных кавычках: так не нужно
    # думать, какие символы в описании или адресе YAML понял бы иначе.
    return json.dumps(str(value), ensure_ascii=False)


def _yaml(kind: str, fields: list[tuple[str, object]]) -> str:
    lines = [f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}"
             f".{MANIFEST_VERSION}.schema.json", ""]
    for key, value in fields:
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    for n, (k, v) in enumerate(item.items()):
                        lines.append(f"{'- ' if n == 0 else '  '}{k}: {_q(v)}")
                else:
                    lines.append(f"- {_q(item)}")
        else:
            lines.append(f"{key}: {_q(value)}")
    return "\n".join(lines) + "\n"


def build(version: str, sha256: str, out: Path) -> list[Path]:
    sha256 = sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise SystemExit(f"это не SHA-256: {sha256!r}")
    url = f"https://github.com/{REPO}/releases/download/v{version}/CenturioSetup.exe"
    home = f"https://github.com/{REPO}"
    description = _iss_define("MyAppDescription")
    publisher = _iss_define("MyAppPublisher")

    written = []
    winget = out / "winget" / "manifests" / "c" / "Centurio" / "Centurio" / version
    winget.mkdir(parents=True, exist_ok=True)
    files = {
        f"{PACKAGE_ID}.yaml": _yaml("version", [
            ("PackageIdentifier", PACKAGE_ID), ("PackageVersion", version),
            ("DefaultLocale", "ru-RU"), ("ManifestType", "version"),
            ("ManifestVersion", MANIFEST_VERSION)]),
        f"{PACKAGE_ID}.installer.yaml": _yaml("installer", [
            ("PackageIdentifier", PACKAGE_ID), ("PackageVersion", version),
            ("InstallerLocale", "ru-RU"), ("InstallerType", "inno"), ("Scope", "user"),
            ("UpgradeBehavior", "install"), ("ProductCode", f"{_app_id()}_is1"),
            ("Installers", [{"Architecture": "x64", "InstallerUrl": url,
                             "InstallerSha256": sha256.upper()}]),
            ("ManifestType", "installer"), ("ManifestVersion", MANIFEST_VERSION)]),
        f"{PACKAGE_ID}.locale.ru-RU.yaml": _yaml("defaultLocale", [
            ("PackageIdentifier", PACKAGE_ID), ("PackageVersion", version),
            ("PackageLocale", "ru-RU"), ("Publisher", publisher), ("PackageName", "Centurio"),
            ("PackageUrl", home), ("License", LICENSE), ("ShortDescription", description),
            ("Tags", ["launcher", "tray", "productivity"]),
            ("ReleaseNotesUrl", f"{home}/releases/tag/v{version}"),
            ("ManifestType", "defaultLocale"), ("ManifestVersion", MANIFEST_VERSION)]),
    }
    for name, body in files.items():
        path = winget / name
        path.write_text(body, encoding="utf-8")
        written.append(path)

    scoop = out / "scoop"
    scoop.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "description": description,
        "homepage": home,
        "license": LICENSE,
        "suggest": {"vcredist": "extras/vcredist2022"},
        "architecture": {"64bit": {"url": url, "hash": sha256}},
        "innosetup": True,
        "shortcuts": [["Centurio.exe", "Centurio"]],
        "checkver": {"github": home},
        "autoupdate": {"architecture": {"64bit": {
            "url": f"{home}/releases/download/v$version/CenturioSetup.exe"}}},
    }
    path = scoop / "centurio.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    for path in build(args.version, args.sha256, args.out):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
