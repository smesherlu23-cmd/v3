from __future__ import annotations

import glob
import json
import os
import re
import threading

from ...infra import log

# Публичный (без авторизации) каталог-сервис Epic — тот же, которым пользуются
# Legendary и Heroic, раз собственного «магазина» у Centurio нет и обёрткой
# над официальным лаунчером быть не выйдет.
_CATALOG_HOST = "catalog-public-service-prod06.ol.epicgames.com"

_CATALOG_TIMEOUT = 4

_ART_TIMEOUT = 4

_CATALOG_MAX_BYTES = 512 * 1024

_ART_MAX_BYTES = 8 * 1024 * 1024

_CDN_MAX_FAILURES = 3

# Порядок предпочтения обложек в keyImages каталога: сперва вертикальные —
# они ближе всего по пропорциям к плитке постера, — потом что найдётся.
_PORTRAIT_TYPES = ("OfferImageTall", "DieselStoreFrontTall", "DieselGameBoxTall",
                   "Thumbnail", "OfferImageWide", "DieselStoreFrontWide")

_cdn_lock = threading.Lock()

_cdn_failures = 0

_cdn_misses: set[str] = set()


def _cdn_available() -> bool:
    with _cdn_lock:
        return _cdn_failures < _CDN_MAX_FAILURES

def _cdn_record(reachable: bool) -> None:
    global _cdn_failures
    with _cdn_lock:
        if reachable:
            _cdn_failures = 0
            return
        _cdn_failures += 1
        tripped = _cdn_failures == _CDN_MAX_FAILURES
    if tripped:
        log.warning("Каталог Epic недоступен, пропуск загрузки обложек")

def _cdn_missed(key: str) -> bool:
    with _cdn_lock:
        return key in _cdn_misses

def _cdn_mark_missed(key: str) -> None:
    with _cdn_lock:
        _cdn_misses.add(key)

def reset_epic_cdn_state() -> None:
    global _cdn_failures
    with _cdn_lock:
        _cdn_failures = 0
        _cdn_misses.clear()

def _http_get(url: str, timeout: int = _ART_TIMEOUT,
              max_bytes: int = _ART_MAX_BYTES) -> bytes | None:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Centurio"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError:
        _cdn_record(True)
        return None
    except Exception:
        _cdn_record(False)
        return None
    _cdn_record(True)
    return None if len(data) > max_bytes else data

def _catalog_lookup(namespace: str, item_id: str) -> dict | None:
    url = (f"https://{_CATALOG_HOST}/catalog/api/shared/namespace/{namespace}"
           f"/bulk/items?id={item_id}&country=US&locale=en&includeMainGameDetails=true")
    data = _http_get(url, timeout=_CATALOG_TIMEOUT, max_bytes=_CATALOG_MAX_BYTES)
    if not data:
        return None
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    entry = parsed.get(item_id) if isinstance(parsed, dict) else None
    return entry if isinstance(entry, dict) else None

def _best_key_image(entry: dict) -> str | None:
    images = entry.get("keyImages")
    if not isinstance(images, list):
        return None
    by_type: dict[str, str] = {}
    for img in images:
        if isinstance(img, dict) and img.get("type") and img.get("url"):
            by_type.setdefault(img["type"], img["url"])
    for kind in _PORTRAIT_TYPES:
        if kind in by_type:
            return by_type[kind]
    return None

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")

def poster_for_ids(namespace: str | None, item_id: str | None,
                   icon_cache: str | None = None, posters: bool = True) -> str | None:
    """Обложка по паре `CatalogNamespace`/`CatalogItemId` из манифеста Epic."""
    if not namespace or not item_id or not icon_cache:
        return None
    safe_id = _SAFE_ID.sub("_", item_id)
    out = os.path.join(icon_cache, f"epic_{safe_id}_portrait.jpg")
    if os.path.exists(out):
        return out
    if not posters:
        return None
    key = f"art:{item_id}"
    if _cdn_missed(key) or not _cdn_available():
        return None
    entry = _catalog_lookup(namespace, item_id)
    if not entry:
        _cdn_mark_missed(key)
        return None
    url = _best_key_image(entry)
    if not url:
        _cdn_mark_missed(key)
        return None
    if not _cdn_available():
        return None
    data = _http_get(url)
    if not data or len(data) < 1024:
        _cdn_mark_missed(key)
        return None
    try:
        os.makedirs(icon_cache, exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(data)
        return out
    except OSError:
        return None

def _manifests_dir() -> str | None:
    root = os.environ.get("ProgramData", r"C:\ProgramData")
    d = os.path.join(root, "Epic", "EpicGamesLauncher", "Data", "Manifests")
    return d if os.path.isdir(d) else None

def _catalog_ids_for_app(app_name: str) -> tuple[str | None, str | None]:
    mani = _manifests_dir()
    if not mani:
        return None, None
    for f in glob.glob(os.path.join(mani, "*.item")):
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if app_name not in (d.get("MainGameAppName"), d.get("AppName")):
            continue
        return (d.get("CatalogNamespace") or d.get("MainGameCatalogNamespace"),
                d.get("CatalogItemId") or d.get("MainGameCatalogItemId"))
    return None, None

_APP_URI_RE = re.compile(r"com\.epicgames\.launcher://apps/([^?]+)")

def poster_for(path: str, icon_cache: str | None = None, posters: bool = True) -> str | None:
    """Обложка по launch-URI Epic — та же форма вызова, что у `steam_art.poster_for`.

    В отличие от Steam, `AppName` в URI не несёт `CatalogNamespace`/`CatalogItemId`
    напрямую, поэтому при отсутствии кэша на диске манифест перечитывается заново.
    Для дозаполнения (`backfill_icons`), которое вызывается нечасто, это приемлемо.
    """
    m = _APP_URI_RE.match(path or "")
    if not m:
        return None
    namespace, item_id = _catalog_ids_for_app(m.group(1))
    return poster_for_ids(namespace, item_id, icon_cache, posters)
