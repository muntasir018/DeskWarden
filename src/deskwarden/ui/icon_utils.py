"""
DeskWarden - ui/icon_utils.py

"""

import os
import psutil


# ═════════════════════════════════════════════════════════════════════════
# Method 1: raw SHGetFileInfoW + GDI bitmap extraction
# ═════════════════════════════════════════════════════════════════════════

def get_exe_icon_pixmap(exe_path, size=56):
    try:
        if not (exe_path and os.path.isfile(exe_path)):
            return None
        import ctypes as _ct
        from PyQt6.QtGui import QPixmap, QImage
        from PyQt6.QtCore import Qt
        _shell32 = _ct.windll.shell32
        _SHGFI_ICON      = 0x000000100
        _SHGFI_LARGEICON = 0x000000000

        class _SHFILEINFOW(_ct.Structure):
            _fields_ = [
                ("hIcon",         _ct.c_void_p),
                ("iIcon",         _ct.c_int),
                ("dwAttributes",  _ct.c_uint),
                ("szDisplayName", _ct.c_wchar * 260),
                ("szTypeName",    _ct.c_wchar * 80),
            ]

        info = _SHFILEINFOW()
        res = _shell32.SHGetFileInfoW(
            exe_path, 0, _ct.byref(info),
            _ct.sizeof(info), _SHGFI_ICON | _SHGFI_LARGEICON
        )
        if not res or not info.hIcon:
            return None

        _user32 = _ct.windll.user32
        _gdi32  = _ct.windll.gdi32
        hdc_screen = _user32.GetDC(None)
        hdc_mem    = _gdi32.CreateCompatibleDC(hdc_screen)

        class _BITMAPINFOHEADER(_ct.Structure):
            _fields_ = [
                ("biSize",          _ct.c_uint32),
                ("biWidth",         _ct.c_int32),
                ("biHeight",        _ct.c_int32),
                ("biPlanes",        _ct.c_uint16),
                ("biBitCount",      _ct.c_uint16),
                ("biCompression",   _ct.c_uint32),
                ("biSizeImage",     _ct.c_uint32),
                ("biXPelsPerMeter", _ct.c_int32),
                ("biYPelsPerMeter", _ct.c_int32),
                ("biClrUsed",       _ct.c_uint32),
                ("biClrImportant",  _ct.c_uint32),
            ]

        bmi = _BITMAPINFOHEADER()
        bmi.biSize      = _ct.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth     = 32
        bmi.biHeight    = -32
        bmi.biPlanes    = 1
        bmi.biBitCount  = 32
        bmi.biCompression = 0

        bits = (_ct.c_ubyte * (32 * 32 * 4))()
        hbmp = _gdi32.CreateDIBSection(
            hdc_mem, _ct.byref(bmi), 0,
            _ct.byref(_ct.c_void_p()), None, 0
        )
        old_bmp = _gdi32.SelectObject(hdc_mem, hbmp)
        _user32.DrawIconEx(hdc_mem, 0, 0, info.hIcon, 32, 32, 0, None, 3)
        _gdi32.GetDIBits(hdc_mem, hbmp, 0, 32,
                         _ct.byref(bits), _ct.byref(bmi), 0)
        _gdi32.SelectObject(hdc_mem, old_bmp)
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(None, hdc_screen)
        _user32.DestroyIcon(info.hIcon)

        raw = bytes(bits)
        rgba = bytearray(len(raw))
        for i in range(0, len(raw), 4):
            rgba[i+0] = raw[i+2]
            rgba[i+1] = raw[i+1]
            rgba[i+2] = raw[i+0]
            rgba[i+3] = raw[i+3]

        img = QImage(bytes(rgba), 32, 32, QImage.Format.Format_RGBA8888)
        pm  = QPixmap.fromImage(img)
        if pm and not pm.isNull():
            return pm.scaled(size, size,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


# ═════════════════════════════════════════════════════════════════════════
# Method 2: QFileIconProvider — Control Panel 'Locked Apps'
# ═════════════════════════════════════════════════════════════════════════

def get_exe_icon_pixmap_qt(exe_path, size=48):

    try:
        if not (exe_path and os.path.isfile(exe_path)):
            return None
        from PyQt6.QtWidgets import QFileIconProvider
        from PyQt6.QtCore import QFileInfo, Qt as _Qt
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(exe_path))
        if icon and not icon.isNull():
            pm = icon.pixmap(size, size)
            if pm and not pm.isNull():
                return pm.scaled(size, size,
                    _Qt.AspectRatioMode.KeepAspectRatio,
                    _Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


# ═════════════════════════════════════════════════════════════════════════
# Best .exe path resolver (config-stored path preferred, live process fallback)
# ═════════════════════════════════════════════════════════════════════════

def _resolve_icon_exe_path(pid, cfg_item):
 
    stored_path = ""
    try:
        stored_path = cfg_item.get("path", "") if isinstance(cfg_item, dict) else ""
    except Exception:
        stored_path = ""
    if stored_path and os.path.isfile(stored_path):
        return stored_path
    try:
        live_path = psutil.Process(pid).exe()
        if live_path and os.path.isfile(live_path):
            return live_path
    except Exception:
        pass
    return stored_path or None
