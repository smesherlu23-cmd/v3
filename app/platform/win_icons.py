from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes

from ..infra import log

DEFAULT_SIZE = 256

_DI_NORMAL = 0x0003
_BI_RGB = 0
_DIB_RGB_COLORS = 0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


def available() -> bool:
    return os.name == "nt"


def cache_path(exe: str, icon_cache: str, size: int = DEFAULT_SIZE) -> str:
    digest = hashlib.md5(str(exe).lower().encode("utf-8"), usedforsecurity=False).hexdigest()
    return os.path.join(icon_cache, f"{digest}_{size}.png")


def _dlls():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.PrivateExtractIconsW.argtypes = [
        wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
        wintypes.UINT, wintypes.UINT,
    ]
    user32.PrivateExtractIconsW.restype = ctypes.c_int
    user32.DrawIconEx.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
        ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(_ICONINFO)]
    user32.GetIconInfo.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    return user32, gdi32


def _header(size: int) -> _BITMAPINFO:
    info = _BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    info.bmiHeader.biWidth = size
    info.bmiHeader.biHeight = -size   
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = _BI_RGB
    return info


def _mask_alpha(user32, gdi32, hicon, size: int) -> bytes | None:
    info = _ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        header = _header(size)
        buf = (ctypes.c_ubyte * (size * size * 4))()
        dc = gdi32.CreateCompatibleDC(None)
        if not dc:
            return None
        try:
            copied = gdi32.GetDIBits(dc, info.hbmMask, 0, size, buf,
                                     ctypes.byref(header), _DIB_RGB_COLORS)
        finally:
            gdi32.DeleteDC(dc)
        if not copied:
            return None
        raw = bytes(buf)
        return bytes(0 if raw[i] else 255 for i in range(0, len(raw), 4))
    finally:
        for handle in (info.hbmMask, info.hbmColor):
            if handle:
                gdi32.DeleteObject(handle)


def _render(user32, gdi32, hicon, size: int):
    from PIL import Image

    header = _header(size)
    bits = ctypes.c_void_p()
    dc = gdi32.CreateCompatibleDC(None)
    if not dc:
        return None
    dib = None
    prior = None
    try:
        dib = gdi32.CreateDIBSection(dc, ctypes.byref(header), _DIB_RGB_COLORS,
                                     ctypes.byref(bits), None, 0)
        if not dib or not bits:
            return None
        prior = gdi32.SelectObject(dc, dib)
        ctypes.memset(bits, 0, size * size * 4)
        if not user32.DrawIconEx(dc, 0, 0, hicon, size, size, 0, None, _DI_NORMAL):
            return None
        raw = ctypes.string_at(bits, size * size * 4)
    finally:
        if prior:
            gdi32.SelectObject(dc, prior)
        if dib:
            gdi32.DeleteObject(dib)
        gdi32.DeleteDC(dc)

    image = Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1)
    if image.getchannel("A").getbbox() is None:
        alpha = _mask_alpha(user32, gdi32, hicon, size)
        if alpha is None:
            return None
        image.putalpha(Image.frombytes("L", (size, size), alpha))
    return image


def extract_png(exe: str, out_path: str, size: int = DEFAULT_SIZE) -> bool:
    if not available() or not exe or not os.path.exists(exe):
        return False
    try:
        user32, gdi32 = _dlls()
        handles = (wintypes.HICON * 1)()
        ids = (wintypes.UINT * 1)()
        found = user32.PrivateExtractIconsW(exe, 0, size, size, handles, ids, 1, 0)
        if found <= 0 or not handles[0]:
            return False
        try:
            image = _render(user32, gdi32, handles[0], size)
        finally:
            user32.DestroyIcon(handles[0])
        if image is None:
            return False
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        image.save(out_path, "PNG")
        return True
    except Exception:
        log.exception("не удалось извлечь значок из %s", exe)
        return False
