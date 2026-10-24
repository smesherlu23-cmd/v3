"""Что человек вставил или выбрал: программа, сайт, папка или документ."""
from __future__ import annotations

import ntpath
import os

from ..core.text import web_address, web_name
from ..platform import discovery

_PROGRAM_EXTS = (".exe", ".bat", ".cmd", ".com", ".lnk")


def _title(stem: str) -> str:
    name = stem.replace("-", " ").replace("_", " ").strip()
    return (name[:1].upper() + name[1:]) if name else ""


def describe(raw: str, icon_cache: str | None) -> tuple[dict | None, str | None]:
    """Запись для библиотеки — или None и то, что сказать человеку."""
    text = (raw or "").strip().strip('"')
    if not text:
        return None, "Вставьте путь к программе, папке или файлу — или адрес сайта"
    if os.path.isdir(text):
        name = ntpath.basename(text.rstrip("\\/")) or text
        return {"name": name, "path": text, "source": "manual", "kind": "folder"}, None
    if os.path.isfile(text):
        base = ntpath.basename(text)
        stem = ntpath.splitext(base)[0]
        if base.lower().endswith(_PROGRAM_EXTS):
            return {"name": _title(stem) or "Программа", "path": text, "source": "manual",
                    "icon": discovery.extract_icon(text, icon_cache)}, None
        return {"name": stem or base, "path": text, "source": "manual", "kind": "file"}, None
    url = web_address(text)
    if url:
        return {"name": web_name(url), "path": url, "source": "manual", "kind": "web"}, None
    return None, "Нет ни такого файла, ни папки, ни сайта"
