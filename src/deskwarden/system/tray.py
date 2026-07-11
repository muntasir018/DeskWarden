"""
DeskWarden - system/tray.py

"""

import os
import ctypes
from ctypes import wintypes
import threading

import win32gui
import win32api
from PIL import Image, ImageDraw

from ..core.logging_utils import log_crash
from ..core.paths import asset_path

try:
    from windows_toasts import Toast as _WTToast, InteractableWindowsToaster as _WTToaster
    _HAS_WINDOWS_TOASTS = True
except ImportError:
    _HAS_WINDOWS_TOASTS = False


def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 30, 54, 58], radius=8, fill="#7c3aed")
    d.arc([18, 8, 46, 36], start=200, end=340, fill="#c4b5fd", width=7)
    d.ellipse([27, 38, 37, 48], fill="#e2e8f0")
    d.rectangle([30, 45, 34, 53], fill="#e2e8f0")
    return img

import ctypes
from ctypes import wintypes

WM_USER         = 0x0400
TRAY_MSG        = WM_USER + 20
NIM_ADD         = 0x00000000
NIM_MODIFY      = 0x00000001
NIM_DELETE      = 0x00000002
NIF_MESSAGE     = 0x00000001
NIF_ICON        = 0x00000002
NIF_TIP         = 0x00000004
NIF_INFO        = 0x00000010
NIIF_INFO       = 0x00000001
NIIF_USER       = 0x00000004
NIIF_LARGE_ICON = 0x00000020
WM_LBUTTONUP    = 0x0202
WM_RBUTTONUP    = 0x0205
WM_DESTROY      = 0x0002
NIN_BALLOONUSERCLICK = 0x0400 + 5   # WM_USER + 5
IDM_CONTROL_PANEL = 1001
IDM_QUIT        = 1002
MF_STRING       = 0x00000000
MF_SEPARATOR    = 0x00000800
TPM_LEFTALIGN   = 0x0000
TPM_RETURNCMD   = 0x0100

Shell_NotifyIcon = ctypes.windll.shell32.Shell_NotifyIconW

_AUMID = "MuntasirRahman.DeskWarden.SecurityApp"

def _register_app_user_model_id():
    
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_AUMID)
    except Exception as e:
        log_crash("_register_app_user_model_id", e)


def _ensure_aumid_registered_in_registry():
    
    try:
        import winreg
        ico_path = os.path.join(os.path.dirname(asset_path("icon.png")),
                                 "deskwarden_toast.ico")
        if not os.path.isfile(ico_path):
            try:
                src = asset_path("icon.png")
                if os.path.isfile(src):
                    img = Image.open(src).convert("RGBA")
                    img.save(ico_path, format="ICO", sizes=[(48, 48), (32, 32)])
            except Exception as e:
                log_crash("_ensure_aumid_registered_in_registry: icon convert", e)

        key_path = rf"Software\Classes\AppUserModelId\{_AUMID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "DeskWarden")
            if os.path.isfile(ico_path):
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, ico_path)
            winreg.SetValueEx(key, "IconBackgroundColor", 0, winreg.REG_SZ, "7c3aed")
    except Exception as e:
        log_crash("_ensure_aumid_registered_in_registry", e)

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",              wintypes.DWORD),
        ("hWnd",                wintypes.HWND),
        ("uID",                 wintypes.UINT),
        ("uFlags",              wintypes.UINT),
        ("uCallbackMessage",    wintypes.UINT),
        ("hIcon",               wintypes.HICON),
        ("szTip",               wintypes.WCHAR * 128),
        ("dwState",             wintypes.DWORD),
        ("dwStateMask",         wintypes.DWORD),
        ("szInfo",              wintypes.WCHAR * 256),
        ("uTimeoutOrVersion",   wintypes.UINT),
        ("szInfoTitle",         wintypes.WCHAR * 64),
        ("dwInfoFlags",         wintypes.DWORD),
        ("guidItem",            ctypes.c_byte * 16),
        ("hBalloonIcon",        wintypes.HICON),
    ]

def _pil_to_hicon(img, size=32):
    import tempfile, os
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    tmp = tempfile.NamedTemporaryFile(suffix=".ico", delete=False)
    tmp.close()
    img.save(tmp.name, format="ICO")
    hicon = ctypes.windll.user32.LoadImageW(
        None, tmp.name, 1, size, size, 0x00000010)
    try: os.unlink(tmp.name)
    except Exception: pass
    return hicon


_custom_balloon_hicon = None  

def _get_balloon_hicon():
    
    global _custom_balloon_hicon
    if _custom_balloon_hicon is not None:
        return _custom_balloon_hicon
    try:
        from ..core.logging_utils import dlog
        logo_path = asset_path("deskwarden_with_text.png")
        found = os.path.isfile(logo_path)
        dlog("INFO", f"_get_balloon_hicon: looking for logo at "
                      f"'{logo_path}' — found={found}")
        if found:
            img = Image.open(logo_path).convert("RGBA")
            _custom_balloon_hicon = _pil_to_hicon(img, size=48)
    except Exception as e:
        log_crash("_get_balloon_hicon", e)
    return _custom_balloon_hicon

class NativeTray:
    def __init__(self, on_control_panel, on_quit):
        self._on_control_panel = on_control_panel
        self._on_quit      = on_quit
        self._hwnd         = None
        self._hicon        = None
        self._alive        = threading.Event()
        self._thread       = threading.Thread(target=self._run, daemon=False, name="TrayThread")
        self._badge_active = False
        self._toaster       = None  
    def start(self):
        self._thread.start()
        self._alive.wait(timeout=5)

    def stop(self):
        if self._hwnd:
            try:
                win32gui.PostMessage(self._hwnd, WM_DESTROY, 0, 0)
            except Exception:
                pass

    def _run(self):
        try:
            _register_app_user_model_id()
            _ensure_aumid_registered_in_registry()

            if _HAS_WINDOWS_TOASTS:
                try:
                    self._toaster = _WTToaster(applicationText="DeskWarden", notifierAUMID=_AUMID)
                except Exception as e:
                    log_crash("NativeTray._run: InteractableWindowsToaster init", e)
                    self._toaster = None

            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = self._wnd_proc
            wc.lpszClassName = "DeskWardenTray"
            wc.hInstance = win32api.GetModuleHandle(None)
            win32gui.RegisterClass(wc)

            self._hwnd = win32gui.CreateWindow(
                wc.lpszClassName, "DeskWarden", 0,
                0, 0, 0, 0, 0, 0, wc.hInstance, None)

            self._hicon = _pil_to_hicon(make_icon())

            nid = NOTIFYICONDATA()
            nid.cbSize           = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd             = self._hwnd
            nid.uID              = 1
            nid.uFlags           = NIF_ICON | NIF_MESSAGE | NIF_TIP
            nid.uCallbackMessage = TRAY_MSG
            nid.hIcon            = self._hicon
            nid.szTip            = "DeskWarden — Running"
            Shell_NotifyIcon(NIM_ADD, ctypes.byref(nid))

            self._alive.set()
            win32gui.PumpMessages()

        except Exception as e:
            log_crash("NativeTray._run", e)
            self._alive.set()

        finally:
            try:
                nid2 = NOTIFYICONDATA()
                nid2.cbSize = ctypes.sizeof(NOTIFYICONDATA)
                nid2.hWnd   = self._hwnd
                nid2.uID    = 1
                Shell_NotifyIcon(NIM_DELETE, ctypes.byref(nid2))
            except Exception:
                pass

    def set_badge(self, active: bool):
       
        if not self._hwnd:
            return
        try:
            self._badge_active = bool(active)
            img = make_icon()
            if active:
                d = ImageDraw.Draw(img)
                d.ellipse([42, 2, 62, 22], fill="#ef4444", outline="#1a0f2e", width=3)
            new_hicon = _pil_to_hicon(img)

            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd   = self._hwnd
            nid.uID    = 1
            nid.uFlags = NIF_ICON
            nid.hIcon  = new_hicon
            Shell_NotifyIcon(NIM_MODIFY, ctypes.byref(nid))

            old_hicon = self._hicon
            self._hicon = new_hicon
            if old_hicon:
                try:
                    ctypes.windll.user32.DestroyIcon(old_hicon)
                except Exception:
                    pass
        except Exception as e:
            log_crash("NativeTray.set_badge", e)

    def show_update_toast(self, version: str, message: str = ""):
        
        title = f"DeskWarden {version} is available"[:63]
        body = message or "Click to see what's new and update."

        if self._toaster is not None:
            try:
                toast = _WTToast()
                toast.text_fields = [title, body]
                toast.on_activated = lambda _: threading.Thread(
                    target=self._on_control_panel, daemon=True).start()
                self._toaster.show_toast(toast)
                return
            except Exception as e:
                log_crash("NativeTray.show_update_toast (windows_toasts)", e)
                

        if not self._hwnd:
            return
        try:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd   = self._hwnd
            nid.uID    = 1
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = title
            nid.szInfo = body[:255]

            balloon_icon = _get_balloon_hicon()
            if balloon_icon:
                nid.dwInfoFlags = NIIF_USER | NIIF_LARGE_ICON
                nid.hBalloonIcon = balloon_icon
            else:
                nid.dwInfoFlags = NIIF_INFO

            Shell_NotifyIcon(NIM_MODIFY, ctypes.byref(nid))
        except Exception as e:
            log_crash("NativeTray.show_update_toast", e)

    def _show_menu(self):
        try:
            hmenu = win32gui.CreatePopupMenu()
            win32gui.AppendMenu(hmenu, MF_STRING,    IDM_CONTROL_PANEL, "Open Control Panel")
            win32gui.AppendMenu(hmenu, MF_SEPARATOR, 0,            "")
            win32gui.AppendMenu(hmenu, MF_STRING,    IDM_QUIT,     "Quit DeskWarden")
            pt = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(self._hwnd)
            cmd = ctypes.windll.user32.TrackPopupMenu(
                hmenu,
                TPM_LEFTALIGN | TPM_RETURNCMD,
                pt[0], pt[1], 0, self._hwnd, None)
            win32gui.DestroyMenu(hmenu)
            if cmd == IDM_CONTROL_PANEL:
                threading.Thread(target=self._on_control_panel, daemon=True).start()
            elif cmd == IDM_QUIT:
                threading.Thread(target=self._on_quit, daemon=True).start()
        except Exception as e:
            log_crash("NativeTray._show_menu", e)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == TRAY_MSG:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
                self._show_menu()
            elif lparam == NIN_BALLOONUSERCLICK:
                threading.Thread(target=self._on_control_panel, daemon=True).start()
        elif msg == WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
