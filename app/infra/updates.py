"""Новая версия Centurio — по последнему релизу на GitHub.

Запрос один: адрес последнего релиза. Ничего о компьютере и библиотеке не
отправляется; выключается в настройках.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

REPO = "smesherlu23-cmd/v3"
RELEASES_URL = f"https://github.com/{REPO}/releases"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT = 10.0


def parse_version(text) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", str(text or "").strip())
    return tuple(int(part) for part in m.group(1).split(".")) if m else None


def is_newer(latest, current) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def fetch_latest(timeout: float = TIMEOUT) -> dict | None:
    """Последний опубликованный релиз: {"version", "url"} — или None, если релизов нет."""
    req = urllib.request.Request(API_URL, headers={
        "User-Agent": "Centurio", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name") or "").strip().lstrip("v")
    if parse_version(version) is None:
        return None
    return {"version": version, "url": data.get("html_url") or RELEASES_URL}
