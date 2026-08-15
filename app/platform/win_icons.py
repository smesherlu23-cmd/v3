"""Извлечение иконки из exe/dll напрямую через Win32, без PowerShell.

Раньше это делал PowerShell: скрытый процесс, внутри которого
`Add-Type -TypeDefinition` компилировал в рантайме C# с `DllImport("user32")`.
У такой связки две беды. Первая — цена: холодный старт PowerShell 0.3–1.5 с,
а процесс запускался по одному на файл, то есть библиотека из 50 игр без кэша
значков давала минуту фоновой работы и 50 порождённых процессов. Вторая —
репутация: скрытый PowerShell плюс компиляция C# с P/Invoke в рантайме это
классика offensive tooling, попадающая под AMSI, и два самых тяжёлых признака
из тех, по которым антивирусы принимают Centurio за infostealer.

Здесь то же самое делается тем же `PrivateExtractIcons`, только вызванным из
Python через `ctypes` — ровно так, как в `platform/windows.py` уже вызывается
`user32` для работы с окнами. Ни процесса, ни компиляции, ни AMSI.
"""
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
    """Есть ли вообще Win32 под рукой — на других системах модуль молчит."""
    return os.name == "nt"


def cache_path(exe: str, icon_cache: str, size: int = DEFAULT_SIZE) -> str:
    """Имя файла в кэше значков — то же, что складывал PowerShell.

    Совпадение обязательно: уже накопленный у пользователя кэш должен
    подхватиться как есть, без повторного извлечения всей библиотеки.
    """
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
    # Типы обязательны и для «очевидных» функций: без argtypes ctypes считает
    # целочисленный аргумент 32-битным int, а дескриптор GDI на 64-битной
    # Windows в него не влезает — вызов падает с OverflowError.
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
    info.bmiHeader.biHeight = -size   # сверху вниз, иначе картинка выйдет вверх ногами
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = _BI_RGB
    return info


def _mask_alpha(user32, gdi32, hicon, size: int) -> bytes | None:
    """Альфа из AND-маски — для старых иконок без собственного альфа-канала.

    В маске единица означает «прозрачно», поэтому непрозрачны как раз нули.
    """
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
    """HICON → изображение Pillow в RGBA или None."""
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
        # Вернуть прежний объект в DC до удаления: выбранную в контекст
        # картинку GDI удалить не даст, и она осталась бы утечкой.
        if prior:
            gdi32.SelectObject(dc, prior)
        if dib:
            gdi32.DeleteObject(dib)
        gdi32.DeleteDC(dc)

    image = Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1)
    if image.getchannel("A").getbbox() is None:
        # Иконка без собственной альфы: DrawIconEx оставил канал нулевым, и
        # картинка вышла целиком прозрачной. Берём альфу из AND-маски.
        alpha = _mask_alpha(user32, gdi32, hicon, size)
        if alpha is None:
            return None
        image.putalpha(Image.frombytes("L", (size, size), alpha))
    return image


def extract_png(exe: str, out_path: str, size: int = DEFAULT_SIZE) -> bool:
    """Сохранить иконку `exe` в PNG. False — не вышло, зовите запасной путь."""
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
