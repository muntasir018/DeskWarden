"""
            ===============================================
            DESKWARDEN - WINDOWS APPLICATION LOCKER v1.0.0
            ===============================================

            


©️ Copyright (c) 2026 Tahasinur Rahman Muntasir
Licensed under the MIT License

https://github.com/muntasir018/DeskWarden




"""
import os, sys, json, time, hashlib, threading, traceback, queue, webbrowser
import urllib.request, urllib.error

# ── Redirect all stderr/stdout to error log immediately on startup ────────────
try:
    _log_dir = os.path.join(os.environ.get("APPDATA", "."), "DeskWarden")
    os.makedirs(_log_dir, exist_ok=True)
    _err_path = os.path.join(_log_dir, "crash_log.txt")
    _err_file = open(_err_path, "a", encoding="utf-8", buffering=1)
    import datetime as _dt
    _err_file.write(f"\n{'='*60}\nSTARTED: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")
    sys.stderr = _err_file
    sys.stdout = _err_file
except Exception:
    pass

# ── Diagnostic Log System ─────────────────────────────────────────────────────

_DIAG_PATH       = os.path.join(os.path.join(os.environ.get("APPDATA", "."), "DeskWarden"), "diagnostic_log.txt")
_CRASH_PATH      = os.path.join(os.path.join(os.environ.get("APPDATA", "."), "DeskWarden"), "crash_log.txt")
_DIAG_LOCK       = threading.Lock()
_DIAG_MAX_LINES  = 3000      
_DIAG_MAX_DAYS   = 7         
_DIAG_DATE_FMT   = "%Y-%m-%d %H:%M:%S"

def dlog(level: str, msg: str):
   
    try:
        import datetime as _ddt
        line = f"[{_ddt.datetime.now().strftime(_DIAG_DATE_FMT)}] [{level:<7}] {msg}\n"
        with _DIAG_LOCK:
            with open(_DIAG_PATH, "a", encoding="utf-8") as _f:
                _f.write(line)
    except Exception:
        pass  

def _diag_cleanup():

    try:
        if not os.path.exists(_DIAG_PATH):
            return
        import datetime as _ddt
        cutoff = _ddt.datetime.now() - _ddt.timedelta(days=_DIAG_MAX_DAYS)
        kept = []
        with open(_DIAG_PATH, "r", encoding="utf-8", errors="replace") as _f:
            for raw_line in _f:
                # "[YYYY-MM-DD HH:MM:SS]"
                try:
                    ts_str = raw_line[1:20] 
                    line_dt = _ddt.datetime.strptime(ts_str, _DIAG_DATE_FMT)
                    if line_dt >= cutoff:
                        kept.append(raw_line)
                    
                except Exception:
                    kept.append(raw_line) 

        
        if len(kept) > _DIAG_MAX_LINES:
            kept = kept[-(  _DIAG_MAX_LINES // 2):]

        with open(_DIAG_PATH, "w", encoding="utf-8") as _f:
            _f.writelines(kept)
    except Exception:
        pass  

def _crash_cleanup():
    
    try:
        if not os.path.exists(_CRASH_PATH):
            return
        import datetime as _ddt
        cutoff = _ddt.datetime.now() - _ddt.timedelta(days=30)
        kept = []
        with open(_CRASH_PATH, "r", encoding="utf-8", errors="replace") as _f:
            for raw_line in _f:
                try:
                    ts_str = raw_line[1:20]
                    line_dt = _ddt.datetime.strptime(ts_str, _DIAG_DATE_FMT)
                    if line_dt >= cutoff:
                        kept.append(raw_line)
                except Exception:
                    kept.append(raw_line)

        
        if len(kept) > 500:
            kept = kept[-(500 // 2):]

        with open(_CRASH_PATH, "w", encoding="utf-8") as _f:
            _f.writelines(kept)
    except Exception:
        pass  

# Startup-এ background thread-এ cleanup

threading.Thread(target=_diag_cleanup, daemon=True, name="DiagCleanup").start()
threading.Thread(target=_crash_cleanup, daemon=True, name="CrashCleanup").start()
try:
    import psutil
    import win32gui, win32con, win32process, win32api
    import win32api as _w32api
    from PIL import Image, ImageDraw
    import winreg
    import struct as _struct
    import ctypes as _ctypes
except ImportError as e:
    dlog("ERROR", f"Required library missing: {e} — Run DeskWarden.bat to install")
    try:
        import ctypes as _ct
        _ct.windll.user32.MessageBoxW(
            0,
            f"Missing library: {e}\nRun DeskWarden.bat to install.",
            "DeskWarden — Error",
            0x10
        )
    except Exception:
        pass
    sys.exit(1)

# ── Process Suspend / Resume ─────────────────────────────────────────────────
_ntdll = _ctypes.WinDLL("ntdll.dll")
_kernel32 = _ctypes.WinDLL("kernel32.dll", use_last_error=True)

_NtSuspendProcess = _ntdll.NtSuspendProcess
_NtResumeProcess  = _ntdll.NtResumeProcess
_NtSuspendProcess.restype = _ctypes.c_long
_NtResumeProcess.restype  = _ctypes.c_long

PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_TERMINATE      = 0x0001

def _open_process(pid: int, access: int):
    handle = _kernel32.OpenProcess(access, False, pid)
    return handle if handle else None

def suspend_process(pid: int) -> bool:
    handle = _open_process(pid, PROCESS_SUSPEND_RESUME)
    if not handle:
        dlog("WARNING", f"suspend_process: OpenProcess failed for PID {pid}")
        return False
    try:
        status = _NtSuspendProcess(handle)
        if status != 0:
            dlog("WARNING", f"suspend_process: NtSuspendProcess returned {status} for PID {pid}")
        return status == 0
    except Exception as e:
        dlog("ERROR", f"suspend_process exception PID {pid}: {e}")
        return False
    finally:
        _kernel32.CloseHandle(handle)

def resume_process(pid: int) -> bool:
    handle = _open_process(pid, PROCESS_SUSPEND_RESUME)
    if not handle:
        dlog("WARNING", f"resume_process: OpenProcess failed for PID {pid}")
        return False
    try:
        status = _NtResumeProcess(handle)
        if status != 0:
            dlog("WARNING", f"resume_process: NtResumeProcess returned {status} for PID {pid}")
        return status == 0
    except Exception as e:
        dlog("ERROR", f"resume_process exception PID {pid}: {e}")
        return False
    finally:
        _kernel32.CloseHandle(handle)

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_DIR  = os.path.join(os.environ.get("APPDATA", "."), "DeskWarden")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

def _get_python_exe() -> str:
    base = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "python.exe"):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path
    return sys.executable

# ── Config cache ──────────────────────────────────────────────────────────────
_config_cache_lock = threading.Lock()
_config_cache = {"mtime": None, "data": None}

def _migrate_config(c: dict) -> dict:
    default = {"password_hash": "", "locked_apps": [], "autostart": True,
               "auto_update": True, "last_update_check": ""}
    for k, v in default.items():
        c.setdefault(k, v)
    migrated = []
    for item in c.get("locked_apps", []):
        if isinstance(item, str):
            migrated.append({"exe": item.lower(), "mode": "ask_always"})
        elif isinstance(item, dict):
            item.setdefault("mode", "ask_always")
            item["exe"] = item.get("exe", "").lower()
            migrated.append(item)
    c["locked_apps"] = migrated
    return c

def _deep_copy_config(c: dict) -> dict:
    
    return {
        "password_hash": c.get("password_hash", ""),
        "locked_apps": [dict(item) for item in c.get("locked_apps", [])],
        "autostart": c.get("autostart", True),
        "auto_update": c.get("auto_update", True),
        "last_update_check": c.get("last_update_check", ""),
        **{k: v for k, v in c.items() if k not in (
            "password_hash", "locked_apps", "autostart",
            "auto_update", "last_update_check")},
    }

def load_config():
    default = {"password_hash": "", "locked_apps": [], "autostart": True,
               "auto_update": True, "last_update_check": ""}

    if os.path.exists(CONFIG_PATH):
        try:
            disk_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            disk_mtime = None

        with _config_cache_lock:
            if (disk_mtime is not None
                    and _config_cache["data"] is not None
                    and _config_cache["mtime"] == disk_mtime):
                return _deep_copy_config(_config_cache["data"])

        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                c = json.load(f)
            c = _migrate_config(c)
            with _config_cache_lock:
                _config_cache["mtime"] = disk_mtime
                _config_cache["data"] = c
            return _deep_copy_config(c)
        except Exception as e:
            dlog("ERROR", f"load_config: failed to read config.json: {e} — using defaults")

    try:
        save_config(default)
        set_autostart(True)
    except Exception:
        pass
    dlog("INFO", "load_config: config.json not found, creating default config")
    return default

def save_config(cfg):
    tmp_path = CONFIG_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
        try:
            new_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            new_mtime = None
        with _config_cache_lock:
            _config_cache["mtime"] = new_mtime
            _config_cache["data"] = _migrate_config(_deep_copy_config(cfg))
    except Exception as e:
        dlog("ERROR", f"save_config: failed to write config.json: {e}")

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── Single-instance IPC (Named Pipe) ─────────────────────────────────────────

_IPC_PIPE_NAME = r"\\.\pipe\DeskWardenIPC"

_cp_open_lock = threading.Lock()
_cp_currently_open = False  
_auth_dlg_ref = None  

# ── Auto Update ───────────────────────────────────────────────────────────────
CURRENT_VERSION  = "v1.0.0"
GITHUB_API_URL   = "https://api.github.com/repos/muntasir018/DeskWarden/releases/latest"
_update_result   = {"checked": False, "latest": None, "url": None, "error": None}
_update_lock     = threading.Lock()

def _version_tuple(v: str):
    """Convert 'v1.0.0' → (1, 0, 0) for numeric comparison."""
    clean = v.lstrip("vV").strip()
    try:
        return tuple(int(x) for x in clean.split("."))
    except Exception:
        return (0,)

def check_for_update(timeout: int = 8) -> dict:
    """
    Query GitHub Releases API and return a dict:
      { "update_available": bool, "latest": str, "url": str, "error": str|None }
    Runs synchronously — call from a background thread.
    """
    result = {"update_available": False, "latest": CURRENT_VERSION,
              "url": "", "error": None}
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": "DeskWarden-updater/1.0",
                     "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        latest  = data.get("tag_name", "").strip()
        html_url = data.get("html_url", "")

        result["latest"] = latest
        result["url"]    = html_url
        result["update_available"] = (
            bool(latest) and
            _version_tuple(latest) > _version_tuple(CURRENT_VERSION)
        )
    except urllib.error.URLError as e:
        result["error"] = f"Network error: {e.reason}"
    except Exception as e:
        result["error"] = str(e)

    with _update_lock:
        _update_result.update({"checked": True,
                                "latest": result["latest"],
                                "url":    result["url"],
                                "error":  result["error"]})
    # Save last check time to config (only on success or "up to date")
    if not result.get("error"):
        try:
            import datetime as _dt2
            _cfg_tmp = load_config()
            _cfg_tmp["last_update_check"] = _dt2.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_config(_cfg_tmp)
        except Exception:
            pass
    return result

def check_for_update_async(callback=None):
    """Start update check in background thread. Optional callback(result) on finish."""
    def _worker():
        res = check_for_update()
        if callback:
            try:
                callback(res)
            except Exception:
                pass
    t = threading.Thread(target=_worker, daemon=True, name="update-checker")
    t.start()
    return t

def log_crash(context: str, exc: Exception):
    try:
        crash_path = os.path.join(CONFIG_DIR, "crash_log.txt")
        with open(crash_path, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"\n{'='*60}\n")
            f.write(f"TIME   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"WHERE  : {context}\n")
            f.write(f"ERROR  : {type(exc).__name__}: {exc}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass
    # diagnostic log- crash record
    dlog("ERROR", f"CRASH [{context}]: {type(exc).__name__}: {exc}")

# ── Security Log ─────────────────────────────────────────────────────────────
import datetime

SECURITY_LOG_PATH = os.path.join(CONFIG_DIR, "security_log.json")
MAX_LOG_ENTRIES   = 200

PENALTY_THRES = 3
PENALTY_BASE  = 30
PENALTY_MAX   = 300


UNLOCK_GRACE_SECONDS = 15

MIN_GRACE_LIVENESS_DELAY = 2.0

_attempt_state: dict = {}
_attempt_lock = threading.Lock()

def load_security_log():
    if os.path.exists(SECURITY_LOG_PATH):
        try:
            return json.load(open(SECURITY_LOG_PATH, encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_security_log(entries):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        json.dump(entries[-MAX_LOG_ENTRIES:],
                  open(SECURITY_LOG_PATH, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    except Exception:
        pass

def log_security_event(event_type: str, context: str, extra: str = ""):
    entry = {
        "time":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type":  event_type,
        "where": context,
        "note":  extra,
    }
    entries = load_security_log()
    entries.append(entry)
    _save_security_log(entries)

def record_wrong_attempt(context: str) -> dict:
    with _attempt_lock:
        st = _attempt_state.setdefault(context, {"count": 0, "until": 0.0})
        st["count"] += 1
        log_security_event("wrong_password", context, f"attempt #{st['count']}")
        if st["count"] >= PENALTY_THRES:
            excess  = st["count"] - PENALTY_THRES
            penalty = min(PENALTY_BASE * (2 ** excess), PENALTY_MAX)
            st["until"] = time.time() + penalty
            log_security_event("lockout_start", context,
                               f"{int(penalty)}s lockout after {st['count']} wrong attempts")
        locked = time.time() < st["until"]
        wait   = max(0, int(st["until"] - time.time()))
        return {"count": st["count"], "until": st["until"], "locked": locked, "wait": wait}

def reset_attempt_state(context: str):
    with _attempt_lock:
        _attempt_state.pop(context, None)

def check_locked_out(context: str):
    with _attempt_lock:
        st = _attempt_state.get(context, {"until": 0.0})
        remaining = max(0, int(st["until"] - time.time()))
        return remaining > 0, remaining

# ── Autostart ─────────────────────────────────────────────────────────────────
def set_autostart(enable):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if enable:
           
            pythonw = _get_python_exe()
            script = os.path.abspath(__file__)
            winreg.SetValueEx(key, "DeskWarden", 0, winreg.REG_SZ, f'"{pythonw}" "{script}"')
            dlog("INFO", f"set_autostart: Windows startup enabled")
        else:
            try: winreg.DeleteValue(key, "DeskWarden")
            except Exception: pass
            dlog("INFO", "set_autostart: Windows startup disabled")
        winreg.CloseKey(key)
    except Exception as e:
        dlog("ERROR", f"set_autostart: failed to write registry: {e}")

# ── Hide all windows of a process ────────────────────────────────────────────
def _get_process_tree_pids(root_pid: int) -> set:
    import psutil as _ps
    import os as _os

    pids = set()
    try:
        proc = _ps.Process(root_pid)
        exe_name = _os.path.basename(proc.exe()).lower()

        true_root = proc
        try:
            parent = proc.parent()
            while parent is not None:
                try:
                    parent_exe = _os.path.basename(parent.exe()).lower()
                except (_ps.NoSuchProcess, _ps.AccessDenied):
                    break
                if parent_exe == exe_name:
                    true_root = parent
                    parent = parent.parent()
                else:
                    break
        except (_ps.NoSuchProcess, _ps.AccessDenied):
            pass

        pids.add(true_root.pid)
        try:
            for child in true_root.children(recursive=True):
                pids.add(child.pid)
        except (_ps.NoSuchProcess, _ps.AccessDenied):
            pass

    except Exception:
        pids.add(root_pid)

    return pids

_hidden_hwnds: set = set()
_hidden_lock = threading.Lock()

def _hwnd_in_pids(hwnd, pids):
    try:
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        return wpid in pids
    except Exception:
        return False

def hide_process_windows(pid):
    target_pids = _get_process_tree_pids(pid)
    newly_hidden = []

    def callback(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid not in target_pids:
                return
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            if win32gui.IsWindowVisible(hwnd) or (style & win32con.WS_VISIBLE):
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                newly_hidden.append(hwnd)
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)

    with _hidden_lock:
        _hidden_hwnds.update(newly_hidden)

def restore_process_windows(pid):
    target_pids = _get_process_tree_pids(pid)

    with _hidden_lock:
        to_restore = [h for h in list(_hidden_hwnds)
                      if _hwnd_in_pids(h, target_pids)]
        for h in to_restore:
            _hidden_hwnds.discard(h)

    restored = False
    for hwnd in to_restore:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            if not restored:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                restored = True
        except Exception:
            pass

# ── Common icon extraction ───────────────────────────────────────────────────
def get_exe_icon_pixmap(exe_path, size=56):
    try:
        if not (exe_path and os.path.isfile(exe_path)):
            return None
        import ctypes as _ct
        from PyQt6.QtGui import QPixmap, QImage
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

def get_exe_icon_pixmap_qt(exe_path, size=48):
    """Extract a .exe's shell icon using QFileIconProvider — the same
    mechanism the Control Panel 'Locked Apps' list uses (via QFileSystemModel),
    which is far more reliable across different apps/icon formats than the
    raw SHGetFileInfoW + GDI bitmap extraction in get_exe_icon_pixmap().
    Must be called from the Qt UI thread."""
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

def _resolve_icon_exe_path(pid, cfg_item):
    """Pick the best .exe path to use for icon lookup on the lock / block
    screens. Prefer the path stored in config (set when the app was added
    via the file browser in Control Panel — this is exactly what the Control Panel
    'Locked Apps' list uses, and is known-good even if the running process
    can't be queried for its image path). Fall back to the live process's
    .exe() if no usable stored path exists."""
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


_ui_queue: queue.Queue = queue.Queue()
_qapp = None
_ui_ready_event = threading.Event()

def _ui_thread_loop():
    global _qapp, _ui_ready_event
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    _qapp = QApplication.instance() or QApplication(sys.argv)
    _qapp.setQuitOnLastWindowClosed(False) 

    timer = QTimer()

    def _process_queue():

        while True:
            try:
                fn = _ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as _e:
                log_crash("_process_queue fn()", _e)

    timer.timeout.connect(_process_queue)
    timer.start(10)  

    _ui_ready_event.set()
    _qapp.exec()

def _run_on_ui_thread(fn):
    _ui_queue.put(fn)

def _run_on_ui_thread_sync(fn):
    result_holder = [None]
    done_event = threading.Event()
    def wrapper():
        try:
            result_holder[0] = fn()
        except Exception as e:
            log_crash("_run_on_ui_thread_sync wrapper", e)
        finally:
            done_event.set()
    _ui_queue.put(wrapper)
    if not done_event.wait(timeout=30.0):
        log_crash("_run_on_ui_thread_sync", TimeoutError("UI thread did not respond in 30s"))
        return None
    return result_holder[0]

class LockScreen:
    def show(self, password_hash, app_name="Application", app_exe_path=None):
        result = {"ok": False}
        done_event = threading.Event()

        _display_name = app_name
        if _display_name.lower().endswith(".exe"):
            _display_name = _display_name[:-4]
        _exe_path = app_exe_path

        def _build_ui():
            try:
                from PyQt6.QtWidgets import (
                    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                    QLabel, QPushButton, QFrame, QLineEdit, QGraphicsDropShadowEffect,
                    QSizePolicy
                )
                from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
                from PyQt6.QtGui import (
                    QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor,
                    QLinearGradient, QKeyEvent, QPixmap
                )
            except ImportError:
                done_event.set()
                return

            _BG    = "#09070f"
            _SIDE  = "#0c0a16"
            _CARD  = "#110f1e"
            _CARD2 = "#171528"
            _BORD  = "#2a2545"
            _ACC   = "#7c3aed"
            _ACC2  = "#9d5cff"
            _FG    = "#ede9ff"
            _MUTE  = "#5a5478"
            _GREEN = "#22c55e"
            _RED   = "#ef4444"

            _qapp = QApplication.instance()
            if _qapp is None:
                _qapp = QApplication([])

            class _RCard(QFrame):
                def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
                    super().__init__(parent)
                    self._bg     = QColor(bg)
                    self._border = QColor(border)
                    self._radius = radius
                    self.setAutoFillBackground(False)

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    r = self.rect().adjusted(1, 1, -1, -1)
                    path = QPainterPath()
                    path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                        self._radius, self._radius)
                    grad = QLinearGradient(0, 0, 0, self.height())
                    grad.setColorAt(0.0, self._bg.lighter(116))
                    grad.setColorAt(1.0, self._bg.darker(110))
                    p.fillPath(path, QBrush(grad))
                    p.setPen(QPen(self._border, 1))
                    p.drawPath(path)

            class _IconBox(QLabel):
                def __init__(self, glyph, size=46, bg="#1e0d40", fg="#c4b5fd",
                             radius=14, parent=None):
                    super().__init__(glyph, parent)
                    self._bg = QColor(bg)
                    self._r  = radius
                    self.setFixedSize(size, size)
                    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setFont(QFont("Segoe UI Emoji", size // 3))
                    self.setStyleSheet(f"color: {fg}; background: transparent;")

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.width(), self.height(),
                                        self._r, self._r)
                    p.fillPath(path, QBrush(self._bg))
                    super().paintEvent(ev)

            def _glow(widget, color=_ACC, radius=18):
                fx = QGraphicsDropShadowEffect()
                fx.setBlurRadius(radius)
                fx.setColor(QColor(color))
                fx.setOffset(0, 0)
                widget.setGraphicsEffect(fx)

            class _OverlayWidget(QWidget):
                def __init__(self, c1, c2, c3, parent=None):
                    super().__init__(parent)
                    self._c1, self._c2, self._c3 = c1, c2, c3
                    self._bg_pixmap = None

                def _rebuild_pixmap(self):
                    from PyQt6.QtGui import QRadialGradient
                    w, h = max(1, self.width()), max(1, self.height())
                    pm = QPixmap(w, h)
                    pm.fill(QColor(0, 0, 0))
                    p = QPainter(pm)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    cx, cy = w / 2, h * 0.46
                    radius = max(w, h) * 0.9
                    grad = QRadialGradient(cx, cy, radius)
                    grad.setColorAt(0.0, QColor(*self._c1))
                    grad.setColorAt(0.35, QColor(*self._c2))
                    grad.setColorAt(1.0, QColor(*self._c3))
                    p.fillRect(pm.rect(), QBrush(grad))
                    p.end()
                    self._bg_pixmap = pm

                def resizeEvent(self, ev):
                    self._rebuild_pixmap()
                    super().resizeEvent(ev)

                def paintEvent(self, ev):
                    if self._bg_pixmap is None:
                        self._rebuild_pixmap()
                    p = QPainter(self)
                    p.drawPixmap(0, 0, self._bg_pixmap)

            overlay = _OverlayWidget(
                (45, 26, 90, 235), (15, 10, 28, 245), (3, 2, 8, 252)
            )
            overlay.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            screen_geom = _qapp.primaryScreen().geometry()
            overlay.setGeometry(screen_geom)
            overlay.setWindowOpacity(0.0)

            modal = QWidget()
            modal.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            modal.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            _MW, _MH = 520, 292
            modal.setFixedSize(_MW, _MH)
            modal.move(
                screen_geom.x() + (screen_geom.width()  - _MW) // 2,
                screen_geom.y() + (screen_geom.height() - _MH) // 2,
            )
            modal.setStyleSheet("background: transparent;")
            modal.setWindowOpacity(0.0)

            def _block_key(obj):
                def _kp(ev):
                    if (ev.key() == Qt.Key.Key_F4 and
                            ev.modifiers() & Qt.KeyboardModifier.AltModifier):
                        ev.ignore()
                obj.keyPressEvent = _kp

            _block_key(overlay)
            _block_key(modal)

            _alive = [True]
            _loop_ref = [None]
            _focus_conn = None
            _geom_conn = None

            def _update_overlay_geometry():
                if _alive[0]:
                    overlay.setGeometry(_qapp.primaryScreen().geometry())

            _geom_conn = _qapp.primaryScreen().geometryChanged.connect(_update_overlay_geometry)

            def _finish(ok: bool):
                if not _alive[0]:
                    return
                nonlocal _focus_conn, _geom_conn
                if _focus_conn is not None:
                    try:
                        _qapp.focusWindowChanged.disconnect(_focus_conn)
                    except Exception:
                        pass
                if _geom_conn is not None:
                    try:
                        _qapp.primaryScreen().geometryChanged.disconnect(_geom_conn)
                    except Exception:
                        pass
                result["ok"] = ok
                _alive[0] = False

                try:
                    _top_timer.stop()
                except Exception:
                    pass

                FADE_STEPS    = 14
                FADE_INTERVAL = 16
                OVERLAY_MAX   = 0.70
                _fo_step      = [0]

                def _fade_out():
                    s = _fo_step[0]
                    if s > FADE_STEPS:
                        try: overlay.hide(); overlay.deleteLater()
                        except Exception: pass
                        try: modal.hide(); modal.deleteLater()
                        except Exception: pass
                        try:
                            if _loop_ref[0] is not None:
                                _loop_ref[0].quit()
                        except Exception: pass
                        done_event.set()
                        return
                    t = s / FADE_STEPS
                    eased = (1 - t) ** 2
                    try:
                        overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                        modal.setWindowOpacity(round(eased, 3))
                    except Exception:
                        pass
                    _fo_step[0] += 1
                    QTimer.singleShot(FADE_INTERVAL, _fade_out)

                _fade_out()

            # ── Main Card ────────────────────────────────────────────
            outer_lay = QVBoxLayout(modal)
            outer_lay.setContentsMargins(0, 0, 0, 0)

            card = _RCard(modal, bg=_CARD, border=_BORD, radius=22)
            outer_lay.addWidget(card)

            # ── Custom Title Bar ────────────────────────────────────
            title_bar = QWidget(card)
            title_bar.setFixedHeight(32)
            title_bar.setStyleSheet("background: transparent;")
            title_bar.setGeometry(16, 0, _MW - 32, 32)
            tbl = QHBoxLayout(title_bar)
            tbl.setContentsMargins(6, 0, 0, 0)
            # ── Logo offset adjustment (Lock Screen titlebar) ──
            _LOCK_LOGO_OFFSET_X = 3   # positive = RIGHT, negative = LEFT
            _LOCK_LOGO_OFFSET_Y = 2   # positive = DOWN,  negative = UP
            _tb_pm1 = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
            if not _tb_pm1.isNull():
                _tb_pm1 = _tb_pm1.scaled(18, 18,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                lock_icon = QLabel()
                lock_icon.setPixmap(_tb_pm1)
                lock_icon.setFixedSize(18, 18)
                lock_icon.setContentsMargins(_LOCK_LOGO_OFFSET_X, _LOCK_LOGO_OFFSET_Y, 0, 0)
                lock_icon.setStyleSheet("background: transparent;")
            else:
                lock_icon = QLabel("🔒")
                lock_icon.setFont(QFont("Segoe UI Emoji", 9))
                lock_icon.setStyleSheet(f"color: {_ACC2}; background: transparent;")
            tbl.addWidget(lock_icon)
            tb_title = QLabel("DeskWarden")
            tb_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            tb_title.setStyleSheet(f"color: {_MUTE}; background: transparent; letter-spacing: 0.5px;")
            tbl.addWidget(tb_title)
            tbl.addStretch()

            close_b = QPushButton("✕")
            close_b.setFixedSize(24, 24)
            close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            close_b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {_MUTE};
                    border: none; font-size: 9pt; border-radius: 12px; }}
                QPushButton:hover {{ background: #2a2545; color: white; }}""")
            close_b.clicked.connect(lambda: _finish(False))
            tbl.addWidget(close_b)

            # ── Body Layout ─────────────────────────────────────────
            body_lay = QHBoxLayout(card)
            body_lay.setContentsMargins(0, 28, 0, 0)
            body_lay.setSpacing(0)

            # ── LEFT PANEL ──────────────────────────────────────────
            left_w = QWidget(); left_w.setStyleSheet("background: transparent;")
            left_l = QVBoxLayout(left_w)
            left_l.setContentsMargins(30, 20, 18, 28); left_l.setSpacing(8)
            left_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(left_w, 1)

            # Gradient ring around icon
            icon_container = QWidget()
            icon_container.setFixedSize(68, 68)
            icon_container.setStyleSheet("background: transparent;")
            _app_pm = get_exe_icon_pixmap_qt(_exe_path, 48) or get_exe_icon_pixmap(_exe_path, 48)
            if _app_pm:
                app_icon_lbl = QLabel(icon_container)
                app_icon_lbl.setPixmap(_app_pm)
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")
            else:
                _fb_pm = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
                if not _fb_pm.isNull():
                    _fb_pm = _fb_pm.scaled(48, 48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    app_icon_lbl = QLabel(icon_container)
                    app_icon_lbl.setPixmap(_fb_pm)
                else:
                    app_icon_lbl = QLabel("🔒", icon_container)
                    app_icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
                    app_icon_lbl.setStyleSheet("color: #c4b5fd; background: transparent;")
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")

            ring = QWidget(icon_container)
            ring.setFixedSize(68, 68)
            ring.setStyleSheet("""
                background: transparent;
                border: 2px solid transparent;
                border-radius: 34px;
            """)
            ring.lower()

            def _draw_ring(widget, painter):
                r = widget.rect().adjusted(2, 2, -2, -2)
                grad = QLinearGradient(0, 0, r.width(), r.height())
                grad.setColorAt(0.0, QColor(_ACC))
                grad.setColorAt(0.5, QColor(_ACC2))
                grad.setColorAt(1.0, QColor("#4c1d95"))
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QBrush(grad), 2))
                painter.drawEllipse(r)

            ring.paintEvent = lambda ev: _draw_ring(ring, QPainter(ring))

            left_l.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
            left_l.addSpacing(4)

            app_lbl = QLabel(_display_name)
            app_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            app_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
            app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            app_lbl.setWordWrap(True)
            left_l.addWidget(app_lbl)

            sub_lbl = QLabel("Authentication required")
            sub_lbl.setFont(QFont("Segoe UI", 7))
            sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_l.addWidget(sub_lbl)

            # ── Vertical Divider ────────────────────────────────────
            vdiv = QFrame(); vdiv.setFixedWidth(1)
            vdiv.setStyleSheet(f"background: {_BORD};")
            body_lay.addWidget(vdiv)

            # ── RIGHT PANEL ─────────────────────────────────────────
            right_w = QWidget(); right_w.setStyleSheet("background: transparent;")
            right_l = QVBoxLayout(right_w)
            right_l.setContentsMargins(28, 20, 28, 24); right_l.setSpacing(5)
            right_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(right_w, 1)

            pw_container = QWidget()
            pw_container.setStyleSheet("background: transparent;")
            pw_cl = QHBoxLayout(pw_container)
            pw_cl.setContentsMargins(0, 0, 0, 0); pw_cl.setSpacing(0)

            pw_edit = QLineEdit()
            pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
            pw_edit.setPlaceholderText("Enter master password")
            pw_edit.setFont(QFont("Segoe UI", 10))
            pw_edit.setFixedHeight(44)
            pw_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: #100c1a; color: {_FG};
                    border: 1px solid {_BORD}; border-radius: 12px;
                    padding: 0 48px 0 14px;
                    selection-background-color: {_ACC};
                }}
                QLineEdit:focus {{
                    border: 1px solid {_ACC2};
                    background: #15112e;
                }}""")

            pw_cl.addWidget(pw_edit)
            _glow(pw_container, QColor(124, 58, 237, 50), 12)
            right_l.addWidget(pw_container)

            # Show/Hide toggle (right side of field)
            eye_btn = QPushButton("Show", pw_edit)
            eye_btn.setFixedSize(36, 26)
            eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            eye_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {_MUTE};
                    border: none; font-size: 7.5pt; font-weight: 600; }}
                QPushButton:hover {{ color: {_FG}; }}""")
            def _position_eye_btn():
                eye_btn.move(pw_edit.width() - eye_btn.width() - 6, 9)
            _orig_resize = pw_edit.resizeEvent
            def _pw_resize(ev):
                _orig_resize(ev)
                _position_eye_btn()
            pw_edit.resizeEvent = _pw_resize
            _position_eye_btn()
            _pw_visible = [False]
            def _toggle_eye():
                _pw_visible[0] = not _pw_visible[0]
                pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _pw_visible[0]
                                    else QLineEdit.EchoMode.Password)
                eye_btn.setText("Hide" if _pw_visible[0] else "Show")
            eye_btn.clicked.connect(_toggle_eye)

            # Strength indicator
            strength_w = QWidget()
            strength_w.setFixedHeight(4)
            strength_w.setStyleSheet("background: #1a1535; border-radius: 2px;")
            strength_bar = QWidget(strength_w)
            strength_bar.setFixedHeight(4)
            strength_bar.setFixedWidth(0)
            strength_bar.setStyleSheet(f"""
                background: {_MUTE}; border-radius: 2px;
            """)
            right_l.addWidget(strength_w)

            def _update_strength(txt):
                l = len(txt)
                if l == 0:
                    strength_bar.setFixedWidth(0)
                    strength_bar.setStyleSheet(f"background: {_MUTE}; border-radius: 2px;")
                elif l < 4:
                    strength_bar.setFixedWidth(int(strength_w.width() * 0.3))
                    strength_bar.setStyleSheet(f"background: {_RED}; border-radius: 2px;")
                elif l < 8:
                    strength_bar.setFixedWidth(int(strength_w.width() * 0.6))
                    strength_bar.setStyleSheet(f"background: #f59e0b; border-radius: 2px;")
                else:
                    strength_bar.setFixedWidth(strength_w.width())
                    strength_bar.setStyleSheet(f"background: {_GREEN}; border-radius: 2px;")

            pw_edit.textChanged.connect(_update_strength)

            # Error label
            err_lbl = QLabel("")
            _err_font1 = QFont("Segoe UI", 8)
            _err_font1.setFamilies(["Segoe UI", "Segoe UI Symbol"])
            err_lbl.setFont(_err_font1)
            err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
            err_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            err_lbl.setWordWrap(True)
            err_lbl.setFixedHeight(12)
            right_l.addWidget(err_lbl)

            # Unlock button
            unlock_btn = QPushButton("Unlock")
            unlock_btn.setFixedHeight(44)
            unlock_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            unlock_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            unlock_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {_ACC}, stop:1 #5b21b6);
                    color: white; border: none; border-radius: 12px;
                    padding: 0 20px; letter-spacing: 0.5px;
                }}
                QPushButton:hover  {{ background: {_ACC2}; }}
                QPushButton:pressed {{ background: #4c1d95; }}
                QPushButton:disabled {{
                    background: {_CARD2}; color: {_MUTE};
                }}""")
            _glow(unlock_btn, QColor(124, 58, 237, 140), 18)
            right_l.addWidget(unlock_btn)

            # Hint
            hint_lbl = QLabel("Press Enter ↵")
            hint_lbl.setFont(QFont("Segoe UI", 7))
            hint_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(hint_lbl)

            # Status
            stat_w = QWidget(); stat_w.setStyleSheet("background: transparent;")
            statl = QHBoxLayout(stat_w)
            statl.setContentsMargins(0, 0, 0, 0); statl.setSpacing(5)
            statl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot_s = QLabel(); dot_s.setFixedSize(5, 5)
            dot_s.setStyleSheet(f"background: {_GREEN}; border-radius: 3px;")
            _glow(dot_s, _GREEN, 6)
            statl.addWidget(dot_s)
            stl = QLabel("SHA-256 Encrypted")
            stl.setFont(QFont("Segoe UI", 6))
            stl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            statl.addWidget(stl)
            right_l.addWidget(stat_w)

            overlay.show()
            modal.show()

            FADE_STEPS    = 14
            FADE_INTERVAL = 16
            OVERLAY_MAX   = 0.70
            _fade_step    = [0]

            def _fade_in():
                s = _fade_step[0]
                if s > FADE_STEPS:
                    return
                t = s / FADE_STEPS
                eased = 1 - (1 - t) ** 2
                try:
                    overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                    modal.setWindowOpacity(round(eased, 3))
                except Exception:
                    pass
                _fade_step[0] += 1
                if _fade_step[0] <= FADE_STEPS:
                    QTimer.singleShot(FADE_INTERVAL, _fade_in)

            QTimer.singleShot(30, _fade_in)

            _drag = [False, 0, 0]
            def _tb_press(ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    _drag[0] = True
                    _drag[1] = ev.globalPosition().x() - modal.x()
                    _drag[2] = ev.globalPosition().y() - modal.y()
            def _tb_move(ev):
                if _drag[0]:
                    modal.move(
                        int(ev.globalPosition().x() - _drag[1]),
                        int(ev.globalPosition().y() - _drag[2])
                    )
            def _tb_release(ev):
                _drag[0] = False
            card.mousePressEvent   = _tb_press
            card.mouseMoveEvent    = _tb_move
            card.mouseReleaseEvent = _tb_release

            _raising = [False]

            def _raise_zorder():
                if not _alive[0] or _raising[0]:
                    return
                _raising[0] = True
                try:
                    overlay.raise_()
                    modal.raise_()
                except Exception:
                    pass
                finally:
                    _raising[0] = False

            _top_timer = QTimer()
            _top_timer.timeout.connect(_raise_zorder)
            _top_timer.start(300)

            try:
                _focus_conn = _qapp.focusWindowChanged.connect(lambda *_: _raise_zorder())
            except Exception:
                pass

            ctx_key = f"App:{app_name}"

            def _start_countdown(seconds):
                pw_edit.setEnabled(False)
                unlock_btn.setEnabled(False)
                _cd = [seconds]
                def _tick():
                    if not _alive[0]:
                        return
                    r = _cd[0]
                    if r <= 0:
                        pw_edit.setEnabled(True)
                        unlock_btn.setEnabled(True)
                        unlock_btn.setText("Unlock")
                        err_lbl.setText("")
                        pw_edit.setFocus()
                        return
                    err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
                    unlock_btn.setText(f"⏳  Wait {r}s")
                    _cd[0] -= 1
                    QTimer.singleShot(1000, _tick)
                _tick()

            def attempt():
                is_locked, wait_s = check_locked_out(ctx_key)
                if is_locked:
                    _start_countdown(wait_s)
                    return
                if hash_pw(pw_edit.text()) == password_hash:
                    reset_attempt_state(ctx_key)
                    log_security_event("success", ctx_key, "unlocked")
                    _top_timer.stop()
                    _finish(True)
                else:
                    state = record_wrong_attempt(ctx_key)
                    pw_edit.clear()
                    if state["locked"]:
                        _start_countdown(state["wait"])
                    else:
                        rem = PENALTY_THRES - state["count"]
                        if rem > 0:
                            err_lbl.setText(f"Wrong password. {rem} attempt(s) remaining.")
                        else:
                            err_lbl.setText("Wrong password.")
                    pw_edit.setFocus()

            unlock_btn.clicked.connect(attempt)
            pw_edit.returnPressed.connect(attempt)
            modal.activateWindow()
            pw_edit.setFocus()
            QTimer.singleShot(300, lambda: (modal.activateWindow(), pw_edit.setFocus()))

            _lk, _ws = check_locked_out(ctx_key)
            if _lk:
                _start_countdown(_ws)

            from PyQt6.QtCore import QEventLoop as _QEventLoop
            _local_loop = _QEventLoop()
            _loop_ref[0] = _local_loop
            _local_loop.exec()

        _run_on_ui_thread(_build_ui)
        done_event.wait()
        return result["ok"]

class BlockNotice:
    def show(self, app_name="Application", app_exe_path=None):
        done_event = threading.Event()

        _display_name = app_name
        if _display_name.lower().endswith(".exe"):
            _display_name = _display_name[:-4]
        _exe_path = app_exe_path

        def _build_ui():
            try:
                from PyQt6.QtWidgets import (
                    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect
                )
                from PyQt6.QtCore import Qt, QTimer
                from PyQt6.QtGui import (
                    QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor,
                    QLinearGradient, QPixmap
                )
            except ImportError:
                done_event.set()
                return

            _BG    = "#09070f"
            _SIDE  = "#120810"
            _CARD  = "#110f1e"
            _BORD  = "#3d1020"
            _RED   = "#ef4444"
            _FG    = "#fca5a5"
            _MUTE  = "#5a5478"
            _ACC   = "#7f1d1d"

            _qapp = QApplication.instance()
            if _qapp is None:
                _qapp = QApplication([])

            class _RCard(QFrame):
                def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=16):
                    super().__init__(parent)
                    self._bg     = QColor(bg)
                    self._border = QColor(border)
                    self._radius = radius
                    self.setAutoFillBackground(False)

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    r = self.rect().adjusted(1, 1, -1, -1)
                    path = QPainterPath()
                    path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                        self._radius, self._radius)
                    grad = QLinearGradient(0, 0, 0, self.height())
                    grad.setColorAt(0.0, self._bg.lighter(116))
                    grad.setColorAt(1.0, self._bg.darker(110))
                    p.fillPath(path, QBrush(grad))
                    p.setPen(QPen(self._border, 1))
                    p.drawPath(path)

            class _IconBox(QLabel):
                def __init__(self, glyph, size=46, bg="#200810", fg="#ef4444",
                             radius=14, parent=None):
                    super().__init__(glyph, parent)
                    self._bg = QColor(bg)
                    self._r  = radius
                    self.setFixedSize(size, size)
                    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setFont(QFont("Segoe UI Emoji", size // 3))
                    self.setStyleSheet(f"color: {fg}; background: transparent;")

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.width(), self.height(),
                                        self._r, self._r)
                    p.fillPath(path, QBrush(self._bg))
                    super().paintEvent(ev)

            def _glow(widget, color=_RED, radius=18):
                fx = QGraphicsDropShadowEffect()
                fx.setBlurRadius(radius)
                fx.setColor(QColor(color))
                fx.setOffset(0, 0)
                widget.setGraphicsEffect(fx)

            class _OverlayWidget(QWidget):
                def __init__(self, c1, c2, c3, parent=None):
                    super().__init__(parent)
                    self._c1, self._c2, self._c3 = c1, c2, c3
                    self._bg_pixmap = None

                def _rebuild_pixmap(self):
                    from PyQt6.QtGui import QRadialGradient
                    w, h = max(1, self.width()), max(1, self.height())
                    pm = QPixmap(w, h)
                    pm.fill(QColor(0, 0, 0))
                    p = QPainter(pm)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    cx, cy = w / 2, h * 0.46
                    radius = max(w, h) * 0.9
                    grad = QRadialGradient(cx, cy, radius)
                    grad.setColorAt(0.0, QColor(*self._c1))
                    grad.setColorAt(0.35, QColor(*self._c2))
                    grad.setColorAt(1.0, QColor(*self._c3))
                    p.fillRect(pm.rect(), QBrush(grad))
                    p.end()
                    self._bg_pixmap = pm

                def resizeEvent(self, ev):
                    self._rebuild_pixmap()
                    super().resizeEvent(ev)

                def paintEvent(self, ev):
                    if self._bg_pixmap is None:
                        self._rebuild_pixmap()
                    p = QPainter(self)
                    p.drawPixmap(0, 0, self._bg_pixmap)

            overlay = _OverlayWidget(
                (80, 20, 30, 235), (20, 8, 14, 245), (3, 2, 8, 252)
            )
            overlay.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            screen_geom = _qapp.primaryScreen().geometry()
            overlay.setGeometry(screen_geom)
            overlay.setWindowOpacity(0.0)

            modal = QWidget()
            modal.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            modal.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            _MW, _MH = 520, 292
            modal.setFixedSize(_MW, _MH)
            modal.move(
                screen_geom.x() + (screen_geom.width()  - _MW) // 2,
                screen_geom.y() + (screen_geom.height() - _MH) // 2,
            )
            modal.setWindowOpacity(0.0)

            _alive = [True]
            _loop_ref = [None]
            _focus_conn = None
            _geom_conn = None

            def _update_overlay_geometry():
                if _alive[0]:
                    overlay.setGeometry(_qapp.primaryScreen().geometry())

            _geom_conn = _qapp.primaryScreen().geometryChanged.connect(_update_overlay_geometry)

            def _finish():
                if not _alive[0]:
                    return
                nonlocal _focus_conn, _geom_conn
                if _focus_conn is not None:
                    try:
                        _qapp.focusWindowChanged.disconnect(_focus_conn)
                    except Exception:
                        pass
                if _geom_conn is not None:
                    try:
                        _qapp.primaryScreen().geometryChanged.disconnect(_geom_conn)
                    except Exception:
                        pass
                _alive[0] = False
                try:
                    _top_timer.stop()
                except Exception:
                    pass
                FADE_STEPS    = 14
                FADE_INTERVAL = 16
                OVERLAY_MAX   = 0.70
                _fo_step      = [0]
                def _fade_out():
                    s = _fo_step[0]
                    if s > FADE_STEPS:
                        try: overlay.hide(); overlay.deleteLater()
                        except Exception: pass
                        try: modal.hide(); modal.deleteLater()
                        except Exception: pass
                        try:
                            if _loop_ref[0] is not None:
                                _loop_ref[0].quit()
                        except Exception: pass
                        done_event.set()
                        return
                    t = s / FADE_STEPS
                    eased = (1 - t) ** 2
                    try:
                        overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                        modal.setWindowOpacity(round(eased, 3))
                    except Exception:
                        pass
                    _fo_step[0] += 1
                    QTimer.singleShot(FADE_INTERVAL, _fade_out)
                _fade_out()

            # ── Main Card ────────────────────────────────────────────
            outer_lay = QVBoxLayout(modal)
            outer_lay.setContentsMargins(0, 0, 0, 0)

            card = _RCard(modal, bg=_CARD, border=_BORD, radius=22)
            outer_lay.addWidget(card)

            # ── Title bar ───────────────────────────────────────────
            title_bar = QWidget(card)
            title_bar.setFixedHeight(32)
            title_bar.setStyleSheet("background: transparent;")
            title_bar.setGeometry(16, 0, _MW - 32, 32)
            tbl = QHBoxLayout(title_bar)
            tbl.setContentsMargins(6, 0, 0, 0)
            # ── Logo offset adjustment (Block Notice titlebar) ──
            _BLOCK_LOGO_OFFSET_X = 3   # positive = RIGHT, negative = LEFT
            _BLOCK_LOGO_OFFSET_Y = 2   # positive = DOWN,  negative = UP
            _tb_pm2 = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
            if not _tb_pm2.isNull():
                _tb_pm2 = _tb_pm2.scaled(18, 18,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                lock_icon = QLabel()
                lock_icon.setPixmap(_tb_pm2)
                lock_icon.setFixedSize(18, 18)
                lock_icon.setContentsMargins(_BLOCK_LOGO_OFFSET_X, _BLOCK_LOGO_OFFSET_Y, 0, 0)
                lock_icon.setStyleSheet("background: transparent;")
            else:
                lock_icon = QLabel("🚫")
                lock_icon.setFont(QFont("Segoe UI Emoji", 9))
                lock_icon.setStyleSheet(f"color: {_RED}; background: transparent;")
            tbl.addWidget(lock_icon)
            tb_title = QLabel("DeskWarden")
            tb_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            tb_title.setStyleSheet(f"color: {_MUTE}; background: transparent; letter-spacing: 0.5px;")
            tbl.addWidget(tb_title)
            tbl.addStretch()
            close_b = QPushButton("✕")
            close_b.setFixedSize(24, 24)
            close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            close_b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {_MUTE};
                    border: none; font-size: 9pt; border-radius: 12px; }}
                QPushButton:hover {{ background: #3d1020; color: white; }}""")
            close_b.clicked.connect(_finish)
            tbl.addWidget(close_b)

            # ── Body ────────────────────────────────────────────────
            body_lay = QHBoxLayout(card)
            body_lay.setContentsMargins(0, 28, 0, 0); body_lay.setSpacing(0)

            # LEFT
            left_w = QWidget(); left_w.setStyleSheet("background: transparent;")
            left_l = QVBoxLayout(left_w)
            left_l.setContentsMargins(30, 20, 18, 28); left_l.setSpacing(8)
            left_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(left_w, 1)

            icon_container = QWidget()
            icon_container.setFixedSize(68, 68)
            icon_container.setStyleSheet("background: transparent;")
            _app_pm = get_exe_icon_pixmap_qt(_exe_path, 48) or get_exe_icon_pixmap(_exe_path, 48)
            if _app_pm:
                app_icon_lbl = QLabel(icon_container)
                app_icon_lbl.setPixmap(_app_pm)
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")
            else:
                _fb2_pm = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
                if not _fb2_pm.isNull():
                    _fb2_pm = _fb2_pm.scaled(48, 48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    app_icon_lbl = QLabel(icon_container)
                    app_icon_lbl.setPixmap(_fb2_pm)
                else:
                    app_icon_lbl = QLabel("🚫", icon_container)
                    app_icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
                    app_icon_lbl.setStyleSheet("color: #f87171; background: transparent;")
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")

            ring = QWidget(icon_container)
            ring.setFixedSize(68, 68)
            ring.setStyleSheet("background: transparent; border: 2px solid transparent; border-radius: 34px;")
            ring.lower()
            def _draw_ring(widget, painter):
                r = widget.rect().adjusted(2, 2, -2, -2)
                grad = QLinearGradient(0, 0, r.width(), r.height())
                grad.setColorAt(0.0, QColor("#b91c1c"))
                grad.setColorAt(0.5, QColor(_RED))
                grad.setColorAt(1.0, QColor("#7f1d1d"))
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QBrush(grad), 2))
                painter.drawEllipse(r)
            ring.paintEvent = lambda ev: _draw_ring(ring, QPainter(ring))

            left_l.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
            left_l.addSpacing(4)

            app_lbl = QLabel(_display_name)
            app_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            app_lbl.setStyleSheet("color: #fca5a5; background: transparent;")
            app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            app_lbl.setWordWrap(True)
            left_l.addWidget(app_lbl)

            sub_lbl = QLabel("Permanently blocked")
            sub_lbl.setFont(QFont("Segoe UI", 7))
            sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_l.addWidget(sub_lbl)

            # DIVIDER
            vdiv = QFrame(); vdiv.setFixedWidth(1)
            vdiv.setStyleSheet(f"background: {_BORD};")
            body_lay.addWidget(vdiv)

            # RIGHT
            right_w = QWidget(); right_w.setStyleSheet("background: transparent;")
            right_l = QVBoxLayout(right_w)
            right_l.setContentsMargins(28, 20, 28, 24); right_l.setSpacing(12)
            right_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(right_w, 1)

            msg1 = QLabel("Access Denied")
            msg1.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            msg1.setStyleSheet("color: #f5a3a3; background: transparent; letter-spacing: 0.5px;")
            msg1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(msg1)

            msg2 = QLabel("This application is permanently blocked.\nChange the mode in Control Panel to unblock.")
            msg2.setFont(QFont("Segoe UI", 8))
            msg2.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            msg2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg2.setWordWrap(True)
            right_l.addWidget(msg2)

            close_btn = QPushButton("✕  Close")
            close_btn.setFixedHeight(44)
            close_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #b91c1c, stop:1 #7f1d1d);
                    color: white; border: none; border-radius: 12px;
                    padding: 0 20px; letter-spacing: 0.5px;
                }}
                QPushButton:hover  {{ background: #dc2626; }}
                QPushButton:pressed {{ background: #7f1d1d; }}""")
            _glow(close_btn, QColor(239, 68, 68, 160), 22)
            close_btn.clicked.connect(_finish)
            right_l.addWidget(close_btn)

            sl = QLabel("Permanent Restriction · DeskWarden")
            sl.setFont(QFont("Segoe UI", 6))
            sl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(sl)

            overlay.show()
            modal.show()

            FADE_STEPS    = 14
            FADE_INTERVAL = 16
            OVERLAY_MAX   = 0.70
            _fade_step    = [0]

            def _fade_in():
                s = _fade_step[0]
                if s > FADE_STEPS:
                    return
                t = s / FADE_STEPS
                eased = 1 - (1 - t) ** 2
                try:
                    overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                    modal.setWindowOpacity(round(eased, 3))
                except Exception:
                    pass
                _fade_step[0] += 1
                if _fade_step[0] <= FADE_STEPS:
                    QTimer.singleShot(FADE_INTERVAL, _fade_in)

            QTimer.singleShot(30, _fade_in)

            _drag = [False, 0, 0]
            def _tb_press(ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    _drag[0] = True
                    _drag[1] = ev.globalPosition().x() - modal.x()
                    _drag[2] = ev.globalPosition().y() - modal.y()
            def _tb_move(ev):
                if _drag[0]:
                    modal.move(
                        int(ev.globalPosition().x() - _drag[1]),
                        int(ev.globalPosition().y() - _drag[2])
                    )
            def _tb_release(ev):
                _drag[0] = False
            card.mousePressEvent   = _tb_press
            card.mouseMoveEvent    = _tb_move
            card.mouseReleaseEvent = _tb_release

            _raising = [False]

            def _raise_zorder():
                if not _alive[0] or _raising[0]:
                    return
                _raising[0] = True
                try:
                    overlay.raise_()
                    modal.raise_()
                except Exception:
                    pass
                finally:
                    _raising[0] = False

            _top_timer = QTimer()
            _top_timer.timeout.connect(_raise_zorder)
            _top_timer.start(300)

            try:
                _focus_conn = _qapp.focusWindowChanged.connect(lambda *_: _raise_zorder())
            except Exception:
                pass

            from PyQt6.QtCore import QEventLoop as _QEventLoop
            _local_loop = _QEventLoop()
            _loop_ref[0] = _local_loop
            _local_loop.exec()

        _run_on_ui_thread(_build_ui)
        done_event.wait()
        return False

# ── App Monitor ───────────────────────────────────────────────────────────────
class AppMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        
        self._unlocked_pids: dict = {}
        self._seen_pids: dict = {}
        self._session_unlocked_exes = set()
        self._busy           = False
        self._busy_exe       = None
        self._unlock_grace: dict = {}
        self._unlock_exe_pids: dict = {}
        self._close_watchlist: set = set()
        self._lock           = threading.Lock()
        self._lock_queue     = queue.Queue()

    def run(self):
        dlog("INFO", "AppMonitor: process scan loop started (every 300ms)")
        time.sleep(1)
        cleanup_counter = 0
        while True:
            try:
                self._scan_all_processes()
                self._check_grace_liveness()
                self._cleanup_close_watchlist()
                cleanup_counter += 1
                if cleanup_counter >= 100:
                    self._cleanup_dead_pids()
                    cleanup_counter = 0
            except Exception as e:
                dlog("ERROR", f"AppMonitor.run/scan exception: {type(e).__name__}: {e}")
                log_crash("AppMonitor.run/scan", e)
            time.sleep(0.3)

    def _cleanup_dead_pids(self):
        with self._lock:
            # _unlocked_pids dict
            dead_unlocked = [pid for pid in self._unlocked_pids if not psutil.pid_exists(pid)]
            for pid in dead_unlocked:
                del self._unlocked_pids[pid]

            # _seen_pids dict
            dead_seen = [pid for pid in self._seen_pids if not psutil.pid_exists(pid)]
            for pid in dead_seen:
                del self._seen_pids[pid]

    def _get_locked_item(self, exe_name, cfg):
        exe_name = exe_name.lower()
        base = os.path.basename(exe_name)
        for item in cfg.get("locked_apps", []):
            locked_exe = item.get("exe", "").lower() if isinstance(item, dict) else item.lower()
            if locked_exe in (exe_name, base):
                return item
        return None

    def _is_locked(self, exe_name, cfg):
        return self._get_locked_item(exe_name, cfg) is not None

    def _ancestor_in_unlocked(self, pid, exe_lower):
    
        try:
            proc = psutil.Process(pid)
            for _ in range(12):
                try:
                    parent = proc.parent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return False
                if parent is None:
                    return False
                with self._lock:
                    stored_exe = self._unlocked_pids.get(parent.pid)
                    if stored_exe and stored_exe == exe_lower:
                        return True
                proc = parent
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    def _exe_in_grace(self, exe_lower):
        if not exe_lower:
            return False
        now = time.time()
        with self._lock:
            expiry = self._unlock_grace.get(exe_lower)
            if expiry is None:
                return False
            if now >= expiry:
                del self._unlock_grace[exe_lower]
                return False
            return True

    def set_unlock_grace(self, exe_lower):
        if not exe_lower:
            return
        with self._lock:
            self._unlock_grace[exe_lower] = time.time() + UNLOCK_GRACE_SECONDS

    def _track_unlocked_pid(self, exe_lower, pid):
        if not exe_lower:
            return
        with self._lock:
            self._unlock_exe_pids.setdefault(exe_lower, set()).add(pid)

    def _check_grace_liveness(self):
        now = time.time()
        with self._lock:
            candidates = list(self._unlock_grace.items())

        for exe_lower, expiry in candidates:
            grace_start = expiry - UNLOCK_GRACE_SECONDS
            if now - grace_start < MIN_GRACE_LIVENESS_DELAY:
                continue

            with self._lock:
                tracked = set(self._unlock_exe_pids.get(exe_lower, ()))

            if not tracked:
                continue

            alive = False
            for p in tracked:
                try:
                    proc = psutil.Process(p)
                    if proc.is_running() and (proc.name() or "").lower() == exe_lower:
                        alive = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            if not alive:

                if self._is_uac_consent_active():
                    continue
                with self._lock:
                    self._unlock_grace.pop(exe_lower, None)
                    dead = self._unlock_exe_pids.pop(exe_lower, set())
                    for pid in dead:
                        self._unlocked_pids.pop(pid, None)
                        self._seen_pids.pop(pid, None)

    def _silent_kill_if_watched(self, exe_lower, pid):
        if exe_lower in self._close_watchlist:
            try:
                for p in _get_process_tree_pids(pid):
                    try: psutil.Process(p).kill()
                    except Exception: pass
            except Exception:
                pass
            with self._lock:
                self._seen_pids.pop(pid, None)
                self._unlocked_pids.pop(pid, None)
            return True
        return False

    def _cleanup_close_watchlist(self):
        if not self._close_watchlist:
            return
        for exe in list(self._close_watchlist):
            found = False
            try:
                for proc in psutil.process_iter(["name"]):
                    if (proc.info["name"] or "").lower() == exe:
                        found = True
                        break
            except Exception:
                pass
            if not found:
                self._close_watchlist.discard(exe)

    @staticmethod
    def _is_uac_consent_active():

        try:
            for proc in psutil.process_iter(["name"]):
                if (proc.info["name"] or "").lower() == "consent.exe":
                    return True
        except Exception:
            pass
        return False

    def _scan_all_processes(self):
        cfg = load_config()
        if not cfg["locked_apps"] or not cfg["password_hash"]:
            return

        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pid  = proc.info["pid"]
                name = (proc.info["name"] or "").lower()
                exe  = (proc.info["exe"] or "").lower()

                
                app_item = self._get_locked_item(name or exe, cfg)
                exe_lower = app_item.get("exe", "").lower() if app_item else exe

                with self._lock:
                    
                    unlocked_exe = self._unlocked_pids.get(pid)
                    if unlocked_exe:
                        if unlocked_exe == exe_lower:
                            continue   
                        else:
                            
                            del self._unlocked_pids[pid]

                    # seen_pids check
                    seen_exe = self._seen_pids.get(pid)
                    if seen_exe:
                        if seen_exe == exe_lower:
                            continue  
                        else:
                            del self._seen_pids[pid] 

                if not app_item:
                   
                    with self._lock:
                        self._seen_pids[pid] = exe
                    continue

                mode = app_item.get("mode")

                # paused:
                if mode == "paused":
                    with self._lock:
                        self._unlocked_pids[pid] = exe_lower
                        self._seen_pids[pid] = exe_lower
                    continue

                # permanent
                if mode != "permanent_block":
                    if mode == "session_once" and exe_lower in self._session_unlocked_exes:
                        with self._lock:
                            self._unlocked_pids[pid] = exe_lower
                            self._seen_pids[pid] = exe_lower
                        continue

                    if self._exe_in_grace(exe_lower):
                        with self._lock:
                            self._unlocked_pids[pid] = exe_lower
                            self._seen_pids[pid] = exe_lower
                        self._track_unlocked_pid(exe_lower, pid)
                        continue

                    if self._ancestor_in_unlocked(pid, exe_lower):
                        with self._lock:
                            self._unlocked_pids[pid] = exe_lower
                            self._seen_pids[pid] = exe_lower
                        self._track_unlocked_pid(exe_lower, pid)
                        continue

                if exe_lower and self._silent_kill_if_watched(exe_lower, pid):
                    continue

                if self._is_uac_consent_active():
                    # UAC প্রম্পট চলমান থাকলে এই pass-এ lock trigger করা হবে না,
                    # যাতে elevated প্রসেসটা consent.exe শেষ হওয়ার আগেই
                    # suspend/lock-screen রেসে না পড়ে। পরের scan cycle-এ
                    # consent.exe চলে গেলে স্বাভাবিকভাবেই lock trigger হবে।
                    continue

                lock_payload = dict(app_item)
                lock_payload["password_hash"] = cfg["password_hash"]
                self._trigger_lock_and_mark(pid, name or os.path.basename(exe), lock_payload)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _trigger_lock_and_mark(self, pid, display_name, cfg):
        exe_lower = cfg.get("exe", "").lower()
        with self._lock:
            # unlocked_pids
            if self._unlocked_pids.get(pid) == exe_lower:
                return
            # seen_pids
            if self._seen_pids.get(pid) == exe_lower:
                return

            if self._busy:
                if exe_lower and exe_lower == self._busy_exe:
                    return
                self._seen_pids[pid] = exe_lower
                kill_now = True
            else:
                self._seen_pids[pid] = exe_lower
                self._busy = True
                self._busy_exe = exe_lower
                kill_now = False

        if kill_now:
            dlog("INFO", f"_trigger_lock: {display_name} (PID {pid}) — monitor busy, killing duplicate")
            try:
                import psutil as _ps
                for _p in _get_process_tree_pids(pid):
                    try: _ps.Process(_p).kill()
                    except Exception: pass
            except Exception:
                pass
            with self._lock:
                self._seen_pids.pop(pid, None)
            return

        dlog("INFO", f"LOCKED APP DETECTED: {display_name} (PID {pid})")
        self._lock_queue.put((pid, display_name, cfg))

    def _flush_held(self):
        with self._lock:
            self._busy = False
            self._busy_exe = None

    def reset(self):
        cfg = load_config()
        still_session_once = {
            item.get("exe", "").lower()
            for item in cfg.get("locked_apps", [])
            if isinstance(item, dict) and item.get("mode") == "session_once"
        }

        with self._lock:
            # unlocked_pids dict preserve
            alive_unlocked = {
                pid: exe for pid, exe in self._unlocked_pids.items()
                if psutil.pid_exists(pid)
            }
            # seen_pids dict preserve
            alive_seen = {
                pid: exe for pid, exe in self._seen_pids.items()
                if psutil.pid_exists(pid)
            }
            saved_session_exes = set(self._session_unlocked_exes) & still_session_once

            self._unlocked_pids.clear()
            self._seen_pids.clear()
            self._session_unlocked_exes.clear()
            self._unlock_grace.clear()
            self._unlock_exe_pids.clear()
            self._close_watchlist.clear()
            self._busy = False
            self._busy_exe = None

            self._unlocked_pids.update(alive_unlocked)
            self._seen_pids.update(alive_seen)
            self._session_unlocked_exes.update(saved_session_exes)

# ── Control Panel Window ─────────────────────────────────────────────────────
class ControlPanelWindow:
    def __init__(self, monitor: AppMonitor):
        self.monitor = monitor
        self._proc   = None
        self._on_closed = None   
        self._open_lock = threading.Lock()  

    def is_busy(self) -> bool:
        
        return bool(self._proc and self._proc.poll() is None)

    def open(self):
        
        if not self._open_lock.acquire(blocking=False):
            dlog("INFO", "ControlPanel.open: already opening/open — ignoring duplicate call")
            return
        if self._proc and self._proc.poll() is None:
            
            self._open_lock.release()
            dlog("INFO", "ControlPanel.open: existing Control Panel process still running — skip")
            return

        script  = os.path.abspath(__file__)
        pythonw = _get_python_exe()

        def _run():
            try:
                import subprocess
                dlog("INFO", f"ControlPanel.open: spawning subprocess: {pythonw} {script} --control-panel")
                self._proc = subprocess.Popen(
                    [pythonw, script, "--control-panel"],
                    creationflags=0x00000008
                )
                dlog("INFO", f"ControlPanel.open: subprocess spawned (PID {self._proc.pid}), waiting...")
                rc = self._proc.wait()
                dlog("INFO", f"ControlPanel.open: subprocess (PID {self._proc.pid}) exited with code {rc}")
            except Exception as e:
                log_crash("ControlPanel.open/_run", e)
            finally:
                
                try:
                    self.monitor.reset()
                except Exception as e:
                    log_crash("ControlPanel.open/_run monitor.reset", e)
                try:
                    self._open_lock.release()
                except RuntimeError:
                    pass
                dlog("INFO", "ControlPanel.open: _run finally block complete, calling _on_closed")
                
                if self._on_closed:
                    try:
                        self._on_closed()
                    except Exception as e:
                        log_crash("ControlPanel.open/_run _on_closed", e)

        threading.Thread(target=_run, daemon=True, name="ControlPanelProc").start()

    def stop(self):
        
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

# ── Tray icon ─────────────────────────────────────────────────────────────────
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
WM_LBUTTONUP    = 0x0202
WM_RBUTTONUP    = 0x0205
WM_DESTROY      = 0x0002
IDM_CONTROL_PANEL = 1001
IDM_QUIT        = 1002
MF_STRING       = 0x00000000
MF_SEPARATOR    = 0x00000800
TPM_LEFTALIGN   = 0x0000
TPM_RETURNCMD   = 0x0100

Shell_NotifyIcon = ctypes.windll.shell32.Shell_NotifyIconW

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",           wintypes.DWORD),
        ("hWnd",             wintypes.HWND),
        ("uID",              wintypes.UINT),
        ("uFlags",           wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon",            wintypes.HICON),
        ("szTip",            wintypes.WCHAR * 128),
    ]

def _pil_to_hicon(img):
    import tempfile, os
    img = img.resize((32, 32), Image.LANCZOS).convert("RGBA")
    tmp = tempfile.NamedTemporaryFile(suffix=".ico", delete=False)
    tmp.close()
    img.save(tmp.name, format="ICO")
    hicon = ctypes.windll.user32.LoadImageW(
        None, tmp.name, 1, 32, 32, 0x00000010)
    try: os.unlink(tmp.name)
    except Exception: pass
    return hicon

class NativeTray:
    def __init__(self, on_control_panel, on_quit):
        self._on_control_panel = on_control_panel
        self._on_quit      = on_quit
        self._hwnd         = None
        self._hicon        = None
        self._alive        = threading.Event()
        self._thread       = threading.Thread(target=self._run, daemon=False, name="TrayThread")

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
        elif msg == WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

# ── Main ──────────────────────────────────────────────────────────────────────
def show_control_panel_auth(on_success, cp_obj=None):
    global _cp_currently_open

    if cp_obj is not None and cp_obj.is_busy():
        dlog("INFO", "show_control_panel_auth: Control Panel process is busy (is_busy=True) — ignoring duplicate request")
        return

    with _cp_open_lock:
        if _cp_currently_open:
            dlog("INFO", "show_control_panel_auth: already open — ignoring duplicate request")
            return
        _cp_currently_open = True
    dlog("INFO", "show_control_panel_auth: opening (lock acquired)")

    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame, QGraphicsDropShadowEffect
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor

    cfg = load_config()
    if not cfg.get("password_hash"):

        try:
            on_success()
        except Exception as e:
            log_crash("show_control_panel_auth/on_success (no password)", e)
            with _cp_open_lock:
                _cp_currently_open = False
            dlog("ERROR", "show_control_panel_auth: on_success() raised — lock released immediately")
            return


        def _force_release_if_stuck():
            global _cp_currently_open
            if cp_obj is not None and cp_obj.is_busy():
                dlog("INFO", "show_control_panel_auth: 60s check — Control Panel process still legitimately busy, skipping force-release")
                return
            with _cp_open_lock:
                if _cp_currently_open:
                    _cp_currently_open = False
                    dlog("WARNING",
                         "show_control_panel_auth: lock force-released after timeout "
                         "(on_closed callback never fired)")
        threading.Timer(60.0, _force_release_if_stuck).start()
        return

    _BG   = "#09070f"; _SIDE = "#0c0a16"; _CARD = "#110f1e"
    _BORD = "#2a2545"; _ACC  = "#7c3aed"; _ACC2 = "#9d5cff"
    _FG   = "#ede9ff"; _MUTE = "#5a5478"; _RED  = "#f87171"

    # _on_close
    _close_handler = [None]

    class _AuthDialog(QWidget):
        
        def closeEvent(self, ev):
            ev.accept()
            if _close_handler[0]:
                _close_handler[0]()

    class _RCard(QFrame):
        def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
            super().__init__(parent)
            self._bg = QColor(bg); self._border = QColor(border); self._radius = radius
            self.setAutoFillBackground(False)
        def paintEvent(self, ev):
            p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = self.rect().adjusted(1,1,-1,-1)
            path = QPainterPath()
            path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), self._radius, self._radius)
            p.fillPath(path, QBrush(self._bg))
            p.setPen(QPen(self._border, 1)); p.drawPath(path)

    dlg = _AuthDialog()
    dlg.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedSize(460, 270)

    qapp = _qapp
    sg = qapp.primaryScreen().geometry()
    dlg.move(sg.x() + (sg.width() - 460) // 2, sg.y() + (sg.height() - 270) // 2)

    outer_lay = QVBoxLayout(dlg)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    card = _RCard(dlg, bg=_CARD, border=_BORD, radius=16)
    outer_lay.addWidget(card)

    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0); card_lay.setSpacing(0)

    tb = QWidget(); tb.setFixedHeight(40)
    tb.setStyleSheet("background: transparent;")
    tbl = QHBoxLayout(tb); tbl.setContentsMargins(16, 0, 10, 0); tbl.setSpacing(0)
    tl = QLabel("DeskWarden  ·  Control Panel")
    tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
    tl.setStyleSheet(f"color: {_FG}; background: transparent;")
    tbl.addWidget(tl); tbl.addStretch()
    close_b = QPushButton("✕"); close_b.setFixedSize(28, 22)
    close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    close_b.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE}; border: none;
            font-size: 10pt; border-radius: 4px; }}
        QPushButton:hover {{ background: #7f1d1d; color: white; }}""")
    close_b.clicked.connect(dlg.close)
    tbl.addWidget(close_b)
    card_lay.addWidget(tb)

    sep = QFrame(); sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORD};"); card_lay.addWidget(sep)

    body = QWidget(); body.setStyleSheet("background: transparent;")
    body_lay = QHBoxLayout(body); body_lay.setContentsMargins(0,0,0,0); body_lay.setSpacing(0)

    sb = QWidget(); sb.setFixedWidth(140)
    sb.setStyleSheet("background: transparent;")
    sbl = QVBoxLayout(sb); sbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.setContentsMargins(0, 24, 0, 16); sbl.setSpacing(6)

    # ── Auth dialog logo size adjustment ──
    _AUTH_LOGO_SIZE = 44   # লোগোর সাইজ (pixel) — বড় করতে বাড়াও, ছোট করতে কমাও
    _AUTH_RING_SIZE = 56   # বাইরের গ্রেডিয়েন্ট রিং-এর সাইজ
    from PyQt6.QtGui import QPixmap

    icon_container = QWidget()
    icon_container.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_container.setStyleSheet("background: transparent;")

    _avatar_lbl = QLabel(icon_container)
    _avatar_lbl.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    _avatar_lbl.move(0, 0)
    _avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    _avatar_lbl.setStyleSheet(f"background: {_CARD}; border-radius: {_AUTH_RING_SIZE // 2}px;")

    from PyQt6.QtGui import QLinearGradient
    _sa_pm = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
    if not _sa_pm.isNull():
        _sa_pm = _sa_pm.scaled(_AUTH_LOGO_SIZE, _AUTH_LOGO_SIZE,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        # Clip the pixmap itself into a circle so corners never show
        _circ_pm = QPixmap(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
        _circ_pm.fill(Qt.GlobalColor.transparent)
        _cp = QPainter(_circ_pm)
        _cp.setRenderHint(QPainter.RenderHint.Antialiasing)
        _cpath = QPainterPath()
        _cpath.addEllipse(0, 0, _AUTH_RING_SIZE, _AUTH_RING_SIZE)
        _cp.setClipPath(_cpath)
        _cp.fillRect(_circ_pm.rect(), QBrush(QColor(_CARD)))
        _cx = (_AUTH_RING_SIZE - _sa_pm.width()) // 2
        _cy = (_AUTH_RING_SIZE - _sa_pm.height()) // 2
        _cp.drawPixmap(_cx, _cy, _sa_pm)
        _cp.end()
        _avatar_lbl.setPixmap(_circ_pm)
    else:
        _avatar_lbl.setText("\U0001F512")
        _avatar_lbl.setStyleSheet(_avatar_lbl.styleSheet() + f"color: {_ACC2}; font-size: 16pt;")

    icon_ring = QWidget(icon_container)
    icon_ring.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_ring.setStyleSheet("background: transparent;")

    def _draw_auth_ring(widget, ev):
        p = QPainter(widget)
        r = widget.rect().adjusted(1, 1, -1, -1)
        grad = QLinearGradient(0, 0, r.width(), r.height())
        grad.setColorAt(0.0, QColor(_ACC))
        grad.setColorAt(0.5, QColor(_ACC2))
        grad.setColorAt(1.0, QColor("#4c1d95"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QBrush(grad), 2))
        p.drawEllipse(r)

    icon_ring.paintEvent = lambda ev: _draw_auth_ring(icon_ring, ev)

    sbl.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
    al = QLabel("DeskWarden")
    al.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    al.setStyleSheet(f"color: {_FG}; background: transparent;")
    al.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(al)
    sl = QLabel("Control Panel Auth")
    sl.setFont(QFont("Segoe UI", 7))
    sl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
    sl.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(sl)
    body_lay.addWidget(sb)

    vsep = QFrame(); vsep.setFixedWidth(1)
    vsep.setStyleSheet(f"background: {_BORD};"); body_lay.addWidget(vsep)

    rp = QWidget()
    rp.setStyleSheet("background: transparent;")
    rpl = QVBoxLayout(rp); rpl.setContentsMargins(24, 24, 24, 24); rpl.setSpacing(10)
    rpl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    prompt = QLabel("Enter password to open Control Panel")
    prompt.setFont(QFont("Segoe UI", 10))
    prompt.setStyleSheet(f"color: {_FG}; background: transparent;")
    rpl.addWidget(prompt)

    pw_edit = QLineEdit()
    pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    pw_edit.setFont(QFont("Segoe UI", 11))
    pw_edit.setFixedHeight(40)
    pw_edit.setStyleSheet(f"""
        QLineEdit {{
            background: {_CARD}; color: {_FG}; border: 1px solid {_BORD};
            border-radius: 10px; padding: 0 46px 0 14px;
        }}
        QLineEdit:focus {{ border: 1px solid {_ACC2}; }}""")
    rpl.addWidget(pw_edit)

    cp_eye_btn = QPushButton("Show", pw_edit)
    cp_eye_btn.setFixedSize(34, 24)
    cp_eye_btn.move(229, 8)
    cp_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    cp_eye_btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE};
            border: none; font-size: 7.5pt; font-weight: 600; }}
        QPushButton:hover {{ color: {_FG}; }}""")
    _cp_pw_visible = [False]
    def _cp_toggle_eye():
        _cp_pw_visible[0] = not _cp_pw_visible[0]
        pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _cp_pw_visible[0]
                            else QLineEdit.EchoMode.Password)
        cp_eye_btn.setText("Hide" if _cp_pw_visible[0] else "Show")
    cp_eye_btn.clicked.connect(_cp_toggle_eye)

    err_lbl = QLabel("")
    _err_font2 = QFont("Segoe UI", 9)
    _err_font2.setFamilies(["Segoe UI", "Segoe UI Symbol"])
    err_lbl.setFont(_err_font2)
    err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
    err_lbl.setFixedHeight(14)
    rpl.addWidget(err_lbl)

    unlock_btn = QPushButton("Unlock Control Panel")
    unlock_btn.setFixedHeight(40)
    unlock_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    unlock_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    unlock_btn.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {_ACC}, stop:1 {_ACC2});
            color: white; border: none; border-radius: 10px; padding: 0 20px;
        }}
        QPushButton:hover {{ background: {_ACC2}; }}
        QPushButton:pressed {{ background: #5b21b6; }}
        QPushButton:disabled {{ background: #1e1a30; color: {_MUTE}; }}""")
    rpl.addWidget(unlock_btn)

    _unlock_glow = QGraphicsDropShadowEffect(unlock_btn)
    _unlock_glow.setBlurRadius(0)
    _unlock_glow.setColor(QColor(_ACC2))
    _unlock_glow.setOffset(0, 0)
    unlock_btn.setGraphicsEffect(_unlock_glow)

    _orig_enter = unlock_btn.enterEvent
    _orig_leave = unlock_btn.leaveEvent
    def _ub_enter(ev):
        _unlock_glow.setBlurRadius(24)
        _orig_enter(ev)
    def _ub_leave(ev):
        _unlock_glow.setBlurRadius(0)
        _orig_leave(ev)
    unlock_btn.enterEvent = _ub_enter
    unlock_btn.leaveEvent = _ub_leave

    body_lay.addWidget(rp, 1)
    card_lay.addWidget(body, 1)

    _drag = [False, 0, 0]
    def _tb_press(ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            _drag[0] = True
            _drag[1] = ev.globalPosition().x() - dlg.x()
            _drag[2] = ev.globalPosition().y() - dlg.y()
    def _tb_move(ev):
        if _drag[0]:
            dlg.move(int(ev.globalPosition().x()-_drag[1]),
                     int(ev.globalPosition().y()-_drag[2]))
    def _tb_release(ev): _drag[0] = False
    tb.mousePressEvent = _tb_press; tb.mouseMoveEvent = _tb_move
    tb.mouseReleaseEvent = _tb_release

    CTX = "Control Panel"


    _unlocked = [False]

    def _release_lock():
        global _cp_currently_open, _auth_dlg_ref
        _auth_dlg_ref = None  
        with _cp_open_lock:
            _cp_currently_open = False
        dlog("INFO", "show_control_panel_auth: auth dialog closed — lock released")

    def _on_close():
        if _unlocked[0]:
            dlog("INFO", "show_control_panel_auth: closed after successful unlock — lock stays with Control Panel window")
            global _auth_dlg_ref
            _auth_dlg_ref = None
            try:
                on_success()
            except Exception as e:
                log_crash("show_control_panel_auth/on_success", e)
                _release_lock()
        else:
            _release_lock()

    _close_handler[0] = _on_close

    def _start_cd(seconds):
        pw_edit.setEnabled(False); unlock_btn.setEnabled(False)
        _cd = [seconds]
        def _tick():
            if not dlg.isVisible(): return
            r = _cd[0]
            if r <= 0:
                pw_edit.setEnabled(True); unlock_btn.setEnabled(True)
                unlock_btn.setText("Unlock Control Panel"); err_lbl.setText(""); pw_edit.setFocus()
                return
            err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
            unlock_btn.setText(f"⏳  Wait {r}s")
            _cd[0] -= 1; QTimer.singleShot(1000, _tick)
        _tick()

    def _attempt():
        is_locked, wait_s = check_locked_out(CTX)
        if is_locked: _start_cd(wait_s); return
        if hash_pw(pw_edit.text()) == cfg.get("password_hash", ""):
            reset_attempt_state(CTX)
            log_security_event("success", CTX, "opened control panel")
            _unlocked[0] = True
            dlg.close()
        else:
            state = record_wrong_attempt(CTX); pw_edit.clear()
            if state["locked"]:
                _start_cd(state["wait"])
            else:
                rem = PENALTY_THRES - state["count"]
                err_lbl.setText(f"✗ Wrong password. {rem} attempt(s) remaining." if rem > 0
                                else "✗ Wrong password")
            pw_edit.setFocus()

    unlock_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)
    close_b.clicked.connect(dlg.close)

    dlg.show(); dlg.activateWindow(); pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

    # NOTE: lockout check must come AFTER dlg.show() so that
    # _tick() does not exit early because dlg.isVisible() is False.
    _lk, _ws = check_locked_out(CTX)
    if _lk:
        _start_cd(_ws)
    global _auth_dlg_ref
    _auth_dlg_ref = dlg  

def show_quit_auth(on_success):
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame, QGraphicsDropShadowEffect
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor

    cfg = load_config()
    if not cfg.get("password_hash"):
        on_success()
        return

    _BG   = "#09070f"
    _SIDE = "#100810"
    _CARD = "#110f1e"
    _BORD = "#3d1020"
    _RED  = "#ef4444"
    _FG   = "#fca5a5"
    _MUTE = "#5a5478"
    _ERR  = "#f87171"

    # ── Rounded card frame ────────────────────────────────────────────────────
    class _RCard(QFrame):
        def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
            super().__init__(parent)
            self._bg = QColor(bg)
            self._border = QColor(border)
            self._radius = radius
            self.setAutoFillBackground(False)

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = self.rect().adjusted(1, 1, -1, -1)
            path = QPainterPath()
            path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                self._radius, self._radius)
            p.fillPath(path, QBrush(self._bg))
            p.setPen(QPen(self._border, 1))
            p.drawPath(path)

    # ── Main dialog window ────────────────────────────────────────────────────
    dlg = QWidget()
    dlg.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedSize(460, 270)

    qapp = _qapp
    sg = qapp.primaryScreen().geometry()
    dlg.move(sg.x() + (sg.width()  - 460) // 2,
             sg.y() + (sg.height() - 270) // 2)

    def _block_key(ev):
        if (ev.key() == Qt.Key.Key_F4 and
                ev.modifiers() & Qt.KeyboardModifier.AltModifier):
            ev.ignore()
    dlg.keyPressEvent = _block_key

    outer_lay = QVBoxLayout(dlg)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    # ── Outer card (shadow removed to avoid checkered corner artifacts) ───────
    card = _RCard(dlg, bg=_CARD, border=_BORD, radius=16)
    outer_lay.addWidget(card)

    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0)
    card_lay.setSpacing(0)

    # ── Title bar ─────────────────────────────────────────────────────────────
    tb = QWidget()
    tb.setFixedHeight(36)
    tb.setStyleSheet(f"""
        background: {_SIDE};
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
        border-bottom-left-radius: 0px;
        border-bottom-right-radius: 0px;
    """)
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(14, 0, 10, 0)
    tbl.setSpacing(0)

    tbl.addSpacing(0)

    # ── Logo offset adjustment (Quit dialog titlebar) ──
    _QUIT_LOGO_OFFSET_X = 3   # positive = RIGHT, negative = LEFT
    _QUIT_LOGO_OFFSET_Y = 2   # positive = DOWN,  negative = UP

    tb_logo = QLabel()
    tb_logo.setFixedSize(16, 16)
    from PyQt6.QtGui import QPixmap
    _qb_pm = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
    if not _qb_pm.isNull():
        _qb_pm = _qb_pm.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        tb_logo.setPixmap(_qb_pm)
    tb_logo.setStyleSheet("background: transparent;")
    tb_logo.setContentsMargins(_QUIT_LOGO_OFFSET_X, _QUIT_LOGO_OFFSET_Y, 0, 0)
    tbl.addWidget(tb_logo)
    tbl.addSpacing(6)

    tl = QLabel("DeskWarden  ·  Quit")
    tl.setFont(QFont("Segoe UI", 8))
    tl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
    tbl.addWidget(tl)
    tbl.addStretch()

    close_b = QPushButton("✕")
    close_b.setFixedSize(28, 22)
    close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    close_b.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {_MUTE}; border: none;
            font-size: 10pt; border-radius: 4px;
        }}
        QPushButton:hover {{ background: #7f1d1d; color: white; }}""")
    close_b.clicked.connect(dlg.close)
    tbl.addWidget(close_b)
    card_lay.addWidget(tb)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORD};")
    card_lay.addWidget(sep)

    # ── Rounded bottom-corner panels ─────
    _RADIUS = 16

    class _SidePanel(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAutoFillBackground(False)

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            W, H = self.width(), self.height()
            path = QPainterPath()
            path.moveTo(0, 0)
            path.lineTo(W, 0)
            path.lineTo(W, H)
            path.lineTo(_RADIUS, H)
            path.arcTo(0, H - _RADIUS * 2, _RADIUS * 2, _RADIUS * 2, 270, -90)
            path.closeSubpath()
            p.fillPath(path, QBrush(QColor(_SIDE)))

    class _RightPanel(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAutoFillBackground(False)

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            W, H = self.width(), self.height()
            path = QPainterPath()
            path.moveTo(0, 0)
            path.lineTo(W, 0)
            path.lineTo(W, H - _RADIUS)
            path.arcTo(W - _RADIUS * 2, H - _RADIUS * 2, _RADIUS * 2, _RADIUS * 2, 0, -90)
            path.lineTo(0, H)
            path.closeSubpath()
            p.fillPath(path, QBrush(QColor(_BG)))

    # ── Body (sidebar + right panel) ──────────────────────────────────────────
    body = QWidget()
    body.setStyleSheet("background: transparent;")
    body_lay = QHBoxLayout(body)
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)

    # Left sidebar
    sb = _SidePanel()
    sb.setFixedWidth(140)
    sbl = QVBoxLayout(sb)
    sbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.setContentsMargins(0, 24, 0, 16)
    sbl.setSpacing(6)

    icon_lbl = QLabel("⛔")
    icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
    icon_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(icon_lbl)

    al = QLabel("Quit")
    al.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    al.setStyleSheet(f"color: {_FG}; background: transparent;")
    al.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(al)

    sl = QLabel("Protection stops")
    sl.setFont(QFont("Segoe UI", 7))
    sl.setStyleSheet("color: #6a3040; background: transparent;")
    sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(sl)

    body_lay.addWidget(sb)

    vsep = QFrame()
    vsep.setFixedWidth(1)
    vsep.setStyleSheet(f"background: {_BORD};")
    body_lay.addWidget(vsep)

    # Right panel
    rp = _RightPanel()
    rpl = QVBoxLayout(rp)
    rpl.setContentsMargins(22, 20, 22, 22)
    rpl.setSpacing(8)
    rpl.setAlignment(Qt.AlignmentFlag.AlignTop)

    prompt = QLabel("Confirm password to quit DeskWarden")
    prompt.setFont(QFont("Segoe UI", 10))
    prompt.setStyleSheet("color: #ede9ff; background: transparent;")
    rpl.addWidget(prompt)

    sub = QLabel("Protection will stop after quitting.")
    sub.setFont(QFont("Segoe UI", 8))
    sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
    rpl.addWidget(sub)

    pw_edit = QLineEdit()
    pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    pw_edit.setFont(QFont("Segoe UI", 11))
    pw_edit.setFixedHeight(38)
    pw_edit.setStyleSheet(f"""
        QLineEdit {{
            background: {_CARD}; color: #ede9ff;
            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 44px 0 12px;
        }}
        QLineEdit:focus {{ border: 1px solid {_RED}; }}""")
    rpl.addWidget(pw_edit)

    q_eye_btn = QPushButton("Show", pw_edit)
    q_eye_btn.setFixedSize(32, 22)
    q_eye_btn.move(231, 8)
    q_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    q_eye_btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE};
            border: none; font-size: 7.5pt; font-weight: 600; }}
        QPushButton:hover {{ color: #ede9ff; }}""")
    _q_pw_visible = [False]
    def _q_toggle_eye():
        _q_pw_visible[0] = not _q_pw_visible[0]
        pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _q_pw_visible[0]
                            else QLineEdit.EchoMode.Password)
        q_eye_btn.setText("Hide" if _q_pw_visible[0] else "Show")
    q_eye_btn.clicked.connect(_q_toggle_eye)

    acc_line = QFrame()
    acc_line.setFixedHeight(2)
    acc_line.setStyleSheet(f"background: {_RED}; border-radius: 1px;")
    rpl.addWidget(acc_line)

    err_lbl = QLabel("")
    _err_font3 = QFont("Segoe UI", 9)
    _err_font3.setFamilies(["Segoe UI", "Segoe UI Symbol"])
    err_lbl.setFont(_err_font3)
    err_lbl.setStyleSheet(f"color: {_ERR}; background: transparent;")
    rpl.addWidget(err_lbl)

    quit_btn = QPushButton("✓  Confirm Quit")
    quit_btn.setFixedHeight(40)
    quit_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    quit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    quit_btn.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #c0392b, stop:1 #991b1b);
            color: white; border: none; border-radius: 10px; padding: 0 20px;
        }}
        QPushButton:hover   {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #cc4536, stop:1 #a01f1f); }}
        QPushButton:pressed  {{ background: #7f1d1d; }}
        QPushButton:disabled {{ background: #1e1a30; color: {_MUTE}; }}""")

    _quit_glow = QGraphicsDropShadowEffect()
    _quit_glow.setBlurRadius(0)
    _quit_glow.setColor(QColor(_RED))
    _quit_glow.setOffset(0, 0)
    quit_btn.setGraphicsEffect(_quit_glow)

    def _quit_enter(ev):
        _quit_glow.setBlurRadius(25)
        QPushButton.enterEvent(quit_btn, ev)

    def _quit_leave(ev):
        _quit_glow.setBlurRadius(0)
        QPushButton.leaveEvent(quit_btn, ev)

    quit_btn.enterEvent = _quit_enter
    quit_btn.leaveEvent = _quit_leave

    rpl.addWidget(quit_btn)

    body_lay.addWidget(rp, 1)
    card_lay.addWidget(body, 1)

    # ── Drag support ──────────────────────────────────────────────────────────
    _drag = [False, 0, 0]

    def _tb_press(ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            _drag[0] = True
            _drag[1] = ev.globalPosition().x() - dlg.x()
            _drag[2] = ev.globalPosition().y() - dlg.y()

    def _tb_move(ev):
        if _drag[0]:
            dlg.move(int(ev.globalPosition().x() - _drag[1]),
                     int(ev.globalPosition().y() - _drag[2]))

    def _tb_release(ev):
        _drag[0] = False

    tb.mousePressEvent  = _tb_press
    tb.mouseMoveEvent   = _tb_move
    tb.mouseReleaseEvent = _tb_release

    # ── Auth logic ────────────────────────────────────────────────────────────
    CTX_Q = "Quit"

    def _start_cd(seconds):
        pw_edit.setEnabled(False)
        quit_btn.setEnabled(False)
        _cd = [seconds]

        def _tick():
            r = _cd[0]
            if r <= 0:
                pw_edit.setEnabled(True)
                quit_btn.setEnabled(True)
                quit_btn.setText("✓  Confirm Quit")
                err_lbl.setText("")
                pw_edit.setFocus()
                return
            err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
            quit_btn.setText(f"⏳  Wait {r}s")
            _cd[0] -= 1
            QTimer.singleShot(1000, _tick)

        _tick()

    def _attempt():
        is_locked, wait_s = check_locked_out(CTX_Q)
        if is_locked:
            _start_cd(wait_s)
            return
        if hash_pw(pw_edit.text()) == cfg.get("password_hash", ""):
            reset_attempt_state(CTX_Q)
            log_security_event("success", CTX_Q, "quit confirmed")
            dlg.close()
            on_success()
        else:
            state = record_wrong_attempt(CTX_Q)
            pw_edit.clear()
            if state["locked"]:
                _start_cd(state["wait"])
            else:
                rem = PENALTY_THRES - state["count"]
                err_lbl.setText(
                    f"✗ Wrong password. {rem} attempt(s) remaining." if rem > 0
                    else "✗ Wrong password — Quit cancelled.")
            pw_edit.setFocus()

    quit_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)

    dlg.show()
    dlg.activateWindow()
    pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

    # NOTE: lockout check must come AFTER dlg.show() so that
    # _tick() does not exit early because dlg.isVisible() is False.
    _lk, _ws = check_locked_out(CTX_Q)
    if _lk:
        _start_cd(_ws)

    from PyQt6.QtCore import QEventLoop as _QEventLoop
    _local_loop = _QEventLoop()
    close_b.clicked.connect(_local_loop.quit)
    dlg.destroyed.connect(_local_loop.quit)
    _orig_close = dlg.close

    def _close_and_quit():
        _orig_close()
        _local_loop.quit()

    dlg.close = _close_and_quit
    _local_loop.exec()

def main():
    import datetime as _main_dt

    # ── Single-instance (PID lockfile) ───────────────────────────────────────

    _PID_FILE = os.path.join(CONFIG_DIR, "instance.pid")
    _my_pid   = os.getpid()

    def _read_existing_pid():
        try:
            with open(_PID_FILE, "r") as _pf:
                return int(_pf.read().strip())
        except Exception:
            return None

    def _write_my_pid():
        try:
            with open(_PID_FILE, "w") as _pf:
                _pf.write(str(_my_pid))
        except Exception:
            pass

    def _pid_is_deskwarden(pid):
      
        try:
            proc = psutil.Process(pid)
            if not proc.is_running():
                return False
            try:
                cmdline = " ".join(proc.cmdline()).lower()
                if "deskwarden" in cmdline:
                    return True
                exe = (proc.exe() or "").lower()
                if "python" in exe or "deskwarden" in exe:
                    return True
                return False
            except psutil.AccessDenied:
            
                return True
        except Exception:
            return False

    existing_pid = _read_existing_pid()
    if existing_pid and existing_pid != _my_pid and _pid_is_deskwarden(existing_pid):
            dlog("INFO", f"main(): instance already running (PID {existing_pid}) — sending OPEN_CONTROL_PANEL")
            try:
                import ctypes as _ct_si
                _k32 = _ct_si.WinDLL("kernel32.dll", use_last_error=True)
                GENERIC_WRITE  = 0x40000000
                OPEN_EXISTING  = 3
                
                _k32.CreateFileW.argtypes = [
                    _ct_si.c_wchar_p, _ct_si.c_ulong, _ct_si.c_ulong, _ct_si.c_void_p,
                    _ct_si.c_ulong, _ct_si.c_ulong, _ct_si.c_void_p
                ]
                _k32.CreateFileW.restype = _ct_si.c_void_p
                _invalid = _ct_si.c_void_p(-1).value
                
                for _attempt in range(10):
                    h = _k32.CreateFileW(_IPC_PIPE_NAME, GENERIC_WRITE, 0, None,
                                         OPEN_EXISTING, 0, None)
                    if h and h != _invalid and h != 0:
                        msg = b"OPEN_CONTROL_PANEL"
                        written = _ct_si.c_ulong(0)
                        _k32.WriteFile.argtypes = [_ct_si.c_void_p, _ct_si.c_void_p, _ct_si.c_ulong, _ct_si.POINTER(_ct_si.c_ulong), _ct_si.c_void_p]
                        _k32.WriteFile(h, msg, len(msg), _ct_si.byref(written), None)
                        
                        _k32.CloseHandle.argtypes = [_ct_si.c_void_p]
                        _k32.CloseHandle(h)
                        dlog("INFO", "main(): OPEN_CONTROL_PANEL signal sent via pipe")
                        break
                    time.sleep(0.5)
                else:
                    dlog("WARNING", f"main(): pipe unavailable after retries. Error: {_ct_si.get_last_error()}")
            except Exception as _e:
                dlog("ERROR", f"main(): pipe signal error: {_e}")
            sys.exit(0)


    _write_my_pid()
    dlog("INFO", f"main(): I am the main instance (PID {_my_pid})")

    # ── Normal startup ────────────────────────────────────────────────────────
    dlog("INFO", f"DeskWarden {CURRENT_VERSION} starting")
    dlog("INFO", f"Python: {sys.version.split()[0]} | PID: {os.getpid()}")
    dlog("INFO", f"Script: {os.path.abspath(__file__)}")
    cfg_check = load_config()
    locked_count = len(cfg_check.get("locked_apps", []))
    has_pw = bool(cfg_check.get("password_hash"))
    autostart = cfg_check.get("autostart", False)
    dlog("INFO", f"Config: locked_apps={locked_count} | password={'set' if has_pw else 'NOT SET'} | autostart={autostart}")
    if locked_count > 0:
        app_names = [item.get("exe", "?") if isinstance(item, dict) else str(item) for item in cfg_check.get("locked_apps", [])]
        dlog("INFO", f"Locked apps: {', '.join(app_names)}")
    dlog("INFO", "=" * 55)

    monitor = AppMonitor()
    monitor.start()

    ui_thread = threading.Thread(target=_ui_thread_loop, daemon=True, name="UIThread")
    ui_thread.start()
    _ui_ready_event.wait(timeout=10)
    dlog("INFO", "UI thread ready")

    def _lock_worker_wrapper():
        import psutil as _psutil
        dlog("INFO", "LockWorker thread started")
        while True:
            try:
                pid, display_name, cfg_item = monitor._lock_queue.get()
                lock_mode = cfg_item.get("mode", "ask_always")
                dlog("INFO", f"--- Lock start: {display_name} (PID {pid}) | mode={lock_mode} ---")
                suspended = False
                try:
                    _tree_pids = _get_process_tree_pids(pid)
                    dlog("DEBUG", f"Process tree PIDs: {_tree_pids}")

                    def _do_hide():
                        hide_process_windows(pid)
                    _run_on_ui_thread_sync(_do_hide)
                    dlog("DEBUG", f"{display_name}: windows hidden")

                    suspended_pids = set()
                    for _p in _tree_pids:
                        if suspend_process(_p):
                            suspended = True
                            suspended_pids.add(_p)
                    dlog("DEBUG", f"{display_name}: {len(suspended_pids)}/{len(_tree_pids)} processes suspended")


                    for _delay in (0.02, 0.03, 0.05, 0.05):
                        time.sleep(_delay)
                        try:
                            _fresh_pids = _get_process_tree_pids(pid)
                        except Exception:
                            _fresh_pids = set()
                        _new_pids = _fresh_pids - suspended_pids
                        if not _new_pids:
                            continue
                        for _np in _new_pids:
                            if suspend_process(_np):
                                suspended = True
                                suspended_pids.add(_np)
                        _tree_pids = _tree_pids | _fresh_pids
                        dlog("DEBUG", f"{display_name}: late-spawned PIDs caught & suspended: {_new_pids}")


                    _watcher_stop = threading.Event()

                    def _late_spawn_watcher():
                        nonlocal _tree_pids
                        while not _watcher_stop.wait(0.5):
                            try:
                                _fresh = _get_process_tree_pids(pid)
                            except Exception:
                                continue
                            _unseen = _fresh - suspended_pids
                            if not _unseen:
                                continue
                            for _up in _unseen:
                                if suspend_process(_up):
                                    suspended_pids.add(_up)
                            _tree_pids = _tree_pids | _fresh
                            dlog("DEBUG", f"{display_name}: late-spawned PID(s) caught while prompt open & suspended: {_unseen}")

                    
                    _watcher_thread = threading.Thread(
                        target=_late_spawn_watcher, daemon=True,
                        name=f"LateSpawnWatcher-{pid}"
                    )
                    _watcher_thread.start()

                    
                    try:
                        if lock_mode == "permanent_block":
                            dlog("INFO", f"{display_name}: permanent_block — showing BlockNotice")
                            _exe_path_for_icon = _resolve_icon_exe_path(pid, cfg_item)
                            BlockNotice().show(display_name, _exe_path_for_icon)
                            ok = False
                        else:
                            dlog("INFO", f"{display_name}: showing lock screen (password prompt)")
                            _exe_path_for_icon = _resolve_icon_exe_path(pid, cfg_item)
                            ok = LockScreen().show(cfg_item["password_hash"], display_name, _exe_path_for_icon)
                    finally:
                        _watcher_stop.set()
                        _watcher_thread.join(timeout=2)   

                    if ok:
                        dlog("INFO", f"✓ UNLOCK: {display_name} (PID {pid}) — correct password entered")
                        _exe_lower = cfg_item.get("exe", "").lower()
                        with monitor._lock:
                            if lock_mode == "session_once":
                                monitor._unlocked_pids[pid] = _exe_lower
                                try:
                                    for child in _psutil.Process(pid).children(recursive=True):
                                        monitor._unlocked_pids[child.pid] = _exe_lower
                                        monitor._seen_pids[child.pid] = _exe_lower
                                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                                    pass
                                monitor._session_unlocked_exes.add(_exe_lower)
                                dlog("DEBUG", f"{display_name}: session_once — will not prompt again this session")
                            else:
                                monitor._unlocked_pids[pid] = _exe_lower
                                try:
                                    for child in _psutil.Process(pid).children(recursive=True):
                                        monitor._unlocked_pids[child.pid] = _exe_lower
                                        monitor._seen_pids[child.pid] = _exe_lower
                                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                                    pass

                        
                        monitor._track_unlocked_pid(_exe_lower, pid)
                        try:
                            for child in _psutil.Process(pid).children(recursive=True):
                                monitor._track_unlocked_pid(_exe_lower, child.pid)
                        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                            pass

                        
                        monitor.set_unlock_grace(_exe_lower)
                        dlog("DEBUG", f"{display_name}: {UNLOCK_GRACE_SECONDS}s grace period started")

                        if suspended:
                            for _p in _tree_pids:
                                try: resume_process(_p)
                                except Exception: pass
                            suspended = False
                            dlog("DEBUG", f"{display_name}: processes resumed")

                        time.sleep(0.4)
                        _run_on_ui_thread_sync(lambda: restore_process_windows(pid))
                        time.sleep(0.3)
                        _run_on_ui_thread_sync(lambda: restore_process_windows(pid))
                        dlog("INFO", f"--- Lock end: {display_name} unlocked ---")
                    else:
                        dlog("INFO", f"✗ BLOCKED: {display_name} (PID {pid}) — wrong password or closed, killing process")
                        if suspended:
                            for _p in _tree_pids:
                                try: resume_process(_p)
                                except Exception: pass
                            suspended = False
                            time.sleep(0.05)
                        try:
                            for _p in reversed(list(_tree_pids)):
                                try: _psutil.Process(_p).kill()
                                except Exception: pass
                        except Exception:
                            pass
                        with monitor._lock:
                            monitor._seen_pids.pop(pid, None)
                            monitor._unlocked_pids.pop(pid, None)

                        
                        _exe_lower = cfg_item.get("exe", "").lower()
                        if _exe_lower:
                            monitor._close_watchlist.add(_exe_lower)
                        dlog("INFO", f"--- Lock end: {display_name} killed ---")

                except Exception as e:
                    dlog("ERROR", f"LockWorker exception [{display_name} PID={pid}]: {type(e).__name__}: {e}")
                    log_crash(f"_lock_worker(pid={pid}, app={display_name})", e)
                    if suspended:
                        for _p in _tree_pids:
                            try: resume_process(_p)
                            except Exception: pass
                finally:
                    monitor._flush_held()

            except Exception as e:
                dlog("ERROR", f"LockWorker outer exception: {type(e).__name__}: {e}")
                log_crash("_lock_worker outer", e)

    lock_worker = threading.Thread(target=_lock_worker_wrapper, daemon=True, name="LockWorker")
    lock_worker.start()

    control_panel = ControlPanelWindow(monitor)

    def _on_control_panel_window_closed():
        """Control Panel process exit হলে lock ছেড়ে দাও।"""
        global _cp_currently_open
        with _cp_open_lock:
            _cp_currently_open = False
        dlog("INFO", "ControlPanel: process exited — Control Panel lock released")

    control_panel._on_closed = _on_control_panel_window_closed

    def open_control_panel():
        _run_on_ui_thread(lambda: show_control_panel_auth(control_panel.open, control_panel))  

    cfg = load_config()                    
    if not cfg.get("password_hash"):       
        threading.Timer(1.5, open_control_panel).start()  


    def _do_quit():
        control_panel.stop()          
        try:
            marker = os.path.join(CONFIG_DIR, "clean_exit.marker")
            with open(marker, "w") as f:
                f.write("clean")
        except Exception:
            pass
        dlog("INFO", "DeskWarden shutting down (clean exit)")
        tray.stop()
        os._exit(0)

    def _quit_with_auth():
        _run_on_ui_thread(lambda: show_quit_auth(_do_quit))

    tray = NativeTray(
        on_control_panel=lambda: open_control_panel(),
        on_quit=_quit_with_auth,
    )
    tray.start()

    # ── IPC Named Pipe Server ─────────────────────────────────────────────────

    def _ipc_handle_client(kernel32, _ct, _wt, h_pipe):
        
        try:
            buf = (_ct.c_char * 512)()
            bytes_read = _wt.DWORD(0)
            ok = kernel32.ReadFile(h_pipe, buf, 512, _ct.byref(bytes_read), None)

            if ok and bytes_read.value > 0:
                msg = buf.raw[:bytes_read.value].decode("utf-8", errors="ignore").strip()
                dlog("INFO", f"IPC pipe: received '{msg}'")
                if msg == "OPEN_CONTROL_PANEL":
                    threading.Thread(target=open_control_panel, daemon=True,
                                     name="IPCControlPanelOpen").start()
            elif not ok:
                dlog("WARNING", f"IPC pipe: ReadFile failed (error {_ct.get_last_error()})")

            try:
                kernel32.FlushFileBuffers(h_pipe)
            except Exception:
                pass
            kernel32.DisconnectNamedPipe(h_pipe)

        except Exception as e:
            dlog("ERROR", f"IPC pipe client-handler exception: {type(e).__name__}: {e}")
        finally:
            try:
                kernel32.CloseHandle(h_pipe)
            except Exception:
                pass

    def _ipc_pipe_server():
        import ctypes as _ct
        from ctypes import wintypes as _wt
        kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)
        advapi32 = _ct.WinDLL("advapi32.dll", use_last_error=True)

        class SECURITY_ATTRIBUTES(_ct.Structure):
            _fields_ = [
                ("nLength", _wt.DWORD),
                ("lpSecurityDescriptor", _ct.c_void_p),
                ("bInheritHandle", _wt.BOOL),
            ]

        
        sddl = "D:(A;;GA;;;WD)S:(ML;;NW;;;LW)"
        sd_ptr = _ct.c_void_p()

        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            _ct.c_wchar_p, _wt.DWORD, _ct.POINTER(_ct.c_void_p), _ct.POINTER(_wt.DWORD)
        ]

        sa = SECURITY_ATTRIBUTES()
        sa.nLength = _ct.sizeof(SECURITY_ATTRIBUTES)

        if advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, _ct.byref(sd_ptr), None):
            sa.lpSecurityDescriptor = sd_ptr
        else:
            sa.lpSecurityDescriptor = None
            dlog("WARNING", f"IPC pipe: Security descriptor failed (error {_ct.get_last_error()})")

        sa.bInheritHandle = False
        sa_ptr = _ct.byref(sa) if sa.lpSecurityDescriptor else None

        kernel32.CreateNamedPipeW.restype = _ct.c_void_p
        kernel32.ConnectNamedPipe.argtypes = [_ct.c_void_p, _ct.c_void_p]
        kernel32.DisconnectNamedPipe.argtypes = [_ct.c_void_p]
        kernel32.ReadFile.argtypes = [_ct.c_void_p, _ct.c_void_p, _wt.DWORD,
                                       _ct.POINTER(_wt.DWORD), _ct.c_void_p]
        kernel32.CloseHandle.argtypes = [_ct.c_void_p]
        kernel32.FlushFileBuffers.argtypes = [_ct.c_void_p]

        PIPE_ACCESS_INBOUND    = 0x00000001
        PIPE_TYPE_MESSAGE      = 0x00000004
        PIPE_READMODE_MESSAGE  = 0x00000002
        PIPE_WAIT              = 0x00000000
        INVALID_HANDLE_VALUE   = _ct.c_void_p(-1).value
        PIPE_UNLIMITED_INSTANCES = 255

        dlog("INFO", "IPC pipe server: starting (multi-threaded accept loop)")

        while True:
            try:
                h_pipe = kernel32.CreateNamedPipeW(
                    _IPC_PIPE_NAME,
                    PIPE_ACCESS_INBOUND,
                    PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                    PIPE_UNLIMITED_INSTANCES,
                    512, 512, 0, sa_ptr
                )
                if h_pipe == INVALID_HANDLE_VALUE or not h_pipe:
                    dlog("ERROR", f"IPC pipe: CreateNamedPipeW failed (error {_ct.get_last_error()})")
                    time.sleep(2)
                    continue

              
                connected = kernel32.ConnectNamedPipe(h_pipe, None)
                err = _ct.get_last_error()

                if not connected and err not in (0, 535, 232):
                    kernel32.CloseHandle(h_pipe)
                    continue


                threading.Thread(
                    target=_ipc_handle_client,
                    args=(kernel32, _ct, _wt, h_pipe),
                    daemon=True,
                    name="IPCClientHandler"
                ).start()

            except Exception as e:
                dlog("ERROR", f"IPC pipe server exception: {type(e).__name__}: {e}")
                time.sleep(1)

    threading.Thread(target=_ipc_pipe_server, daemon=True, name="IPCPipeServer").start()
    dlog("INFO", "IPC pipe server thread started")

    try:
        while True:
            time.sleep(5)
    except (SystemExit, KeyboardInterrupt):
        dlog("INFO", "DeskWarden shutting down (SystemExit/KeyboardInterrupt)")
    except Exception as e:
        dlog("ERROR", f"main sleep loop exception: {type(e).__name__}: {e}")
        log_crash("main sleep loop", e)

# ── Service support ───────────────────────────────────────────────────────────
SERVICE_NAME    = "DeskWardenService"
SERVICE_DISPLAY = "DeskWarden – Application Locker"
SERVICE_DESC    = "Monitors and locks configured applications. Managed by DeskWarden."

_running_as_service = False

def _is_admin() -> bool:
    try:
        import ctypes as _ct
        return bool(_ct.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def _launch_gui_in_user_session():
    try:
        import ctypes as _ct
        import ctypes.wintypes as _wt

        wtsapi   = _ct.WinDLL("wtsapi32.dll")
        advapi   = _ct.WinDLL("advapi32.dll", use_last_error=True)
        userenv  = _ct.WinDLL("userenv.dll",  use_last_error=True)
        kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)

        WTS_CURRENT_SERVER_HANDLE = None
        session_id = wtsapi.WTSGetActiveConsoleSessionId()
        if session_id == 0xFFFFFFFF:
            log_crash("_launch_gui_in_user_session", Exception("No active console session"))
            return None

        h_token = _wt.HANDLE()
        if not wtsapi.WTSQueryUserToken(session_id, _ct.byref(h_token)):
            log_crash("_launch_gui_in_user_session",
                      Exception(f"WTSQueryUserToken failed: {_ct.get_last_error()}"))
            return None

        h_dup = _wt.HANDLE()
        TOKEN_DUPLICATE     = 0x0002
        TOKEN_QUERY         = 0x0008
        TOKEN_ASSIGN_PRIMARY = 0x0001
        SECURITY_IMPERSONATION = 2
        TokenPrimary = 1
        sa = _ct.c_void_p(None)
        if not advapi.DuplicateTokenEx(h_token, TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY,
                                       sa, SECURITY_IMPERSONATION, TokenPrimary,
                                       _ct.byref(h_dup)):
            kernel32.CloseHandle(h_token)
            log_crash("_launch_gui_in_user_session",
                      Exception(f"DuplicateTokenEx failed: {_ct.get_last_error()}"))
            return None

        env_block = _ct.c_void_p()
        userenv.CreateEnvironmentBlock(_ct.byref(env_block), h_dup, False)

        script  = os.path.abspath(__file__)
        pythonw = _get_python_exe()
        cmdline = f'"{pythonw}" "{script}" --gui'

        class STARTUPINFO(_ct.Structure):
            _fields_ = [("cb",              _wt.DWORD),
                        ("lpReserved",      _wt.LPWSTR),
                        ("lpDesktop",       _wt.LPWSTR),
                        ("lpTitle",         _wt.LPWSTR),
                        ("dwX",             _wt.DWORD),
                        ("dwY",             _wt.DWORD),
                        ("dwXSize",         _wt.DWORD),
                        ("dwYSize",         _wt.DWORD),
                        ("dwXCountChars",   _wt.DWORD),
                        ("dwYCountChars",   _wt.DWORD),
                        ("dwFillAttribute", _wt.DWORD),
                        ("dwFlags",         _wt.DWORD),
                        ("wShowWindow",     _wt.WORD),
                        ("cbReserved2",     _wt.WORD),
                        ("lpReserved2",     _ct.c_void_p),
                        ("hStdInput",       _wt.HANDLE),
                        ("hStdOutput",      _wt.HANDLE),
                        ("hStdError",       _wt.HANDLE)]
        class PROCESS_INFORMATION(_ct.Structure):
            _fields_ = [("hProcess",    _wt.HANDLE),
                        ("hThread",     _wt.HANDLE),
                        ("dwProcessId", _wt.DWORD),
                        ("dwThreadId",  _wt.DWORD)]

        si = STARTUPINFO()
        si.cb        = _ct.sizeof(STARTUPINFO)
        si.lpDesktop = "winsta0\\default"
        pi = PROCESS_INFORMATION()

        CREATE_UNICODE_ENVIRONMENT = 0x00000400
        NORMAL_PRIORITY_CLASS      = 0x00000020

        ok = advapi.CreateProcessAsUserW(
            h_dup,
            None,
            cmdline,
            None, None,
            False,
            CREATE_UNICODE_ENVIRONMENT | NORMAL_PRIORITY_CLASS,
            env_block,
            None,
            _ct.byref(si),
            _ct.byref(pi)
        )

        if env_block: userenv.DestroyEnvironmentBlock(env_block)
        kernel32.CloseHandle(h_token)
        kernel32.CloseHandle(h_dup)

        if ok:
            kernel32.CloseHandle(pi.hThread)
            return pi.hProcess
        else:
            log_crash("_launch_gui_in_user_session",
                      Exception(f"CreateProcessAsUserW failed: {_ct.get_last_error()}"))
            return None

    except Exception as e:
        log_crash("_launch_gui_in_user_session", e)
        return None

def _monitor_and_restart_gui():
    import ctypes as _ct
    kernel32 = _ct.WinDLL("kernel32.dll", use_last_error=True)
    WAIT_OBJECT_0  = 0x00000000
    WAIT_TIMEOUT   = 0x00000102
    INFINITE       = 0xFFFFFFFF

    h_proc = None

    while _running_as_service:
        marker = os.path.join(CONFIG_DIR, "clean_exit.marker")
        if os.path.exists(marker):
            try:
                os.unlink(marker)
            except Exception:
                pass
            os._exit(0)

        if h_proc is None:
            time.sleep(2)
            h_proc = _launch_gui_in_user_session()
            if h_proc is None:
                time.sleep(5)
                continue
            log_security_event("service_event", "GUI helper launched",
                               f"handle={h_proc}")

        result = kernel32.WaitForSingleObject(h_proc, 3000)
        if result == WAIT_OBJECT_0:
            exit_code = _ct.wintypes.DWORD()
            kernel32.GetExitCodeProcess(h_proc, _ct.byref(exit_code))
            kernel32.CloseHandle(h_proc)
            h_proc = None
            log_security_event("service_event", "GUI helper exited",
                               f"exit_code={exit_code.value}")

    if h_proc:
        kernel32.TerminateProcess(h_proc, 0)
        kernel32.CloseHandle(h_proc)

try:
    import win32serviceutil, win32service, win32event, servicemanager

    class DeskWardenWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_        = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_  = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            global _running_as_service
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            _running_as_service = False
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            global _running_as_service
            _running_as_service = True
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, "")
            )
            gui_thread = threading.Thread(target=_monitor_and_restart_gui,
                                          daemon=True, name="GuiWatchdog")
            gui_thread.start()
            win32event.WaitForSingleObject(self._stop_event,
                                           win32event.INFINITE)

    _SERVICE_AVAILABLE = True

except ImportError:
    _SERVICE_AVAILABLE = False
    DeskWardenWindowsService = None

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in (
            "install", "remove", "start", "stop",
            "update", "debug", "--startup"):
        if not _SERVICE_AVAILABLE:
            print("ERROR: pywin32 is required for service mode.  "
                  "Run: pip install pywin32")
            sys.exit(1)
        win32serviceutil.HandleCommandLine(DeskWardenWindowsService)
        sys.exit(0)

    # ── Shortcut / Second-instance: --open-control-panel ──────────────────────

    if "--open-control-panel" in sys.argv:
        _pid_file_path = os.path.join(CONFIG_DIR, "instance.pid")
        _existing_pid = None
        try:
            with open(_pid_file_path, "r") as _pf2:
                _existing_pid = int(_pf2.read().strip())
        except Exception:
            pass

        _instance_running = False
        if _existing_pid:
            try:
                _chk = psutil.Process(_existing_pid)
                if _chk.is_running() and _chk.status() != psutil.STATUS_ZOMBIE:

                    try:
                        _exe = (_chk.exe() or "").lower()
                        if "python" in _exe or "deskwarden" in _exe:
                            _instance_running = True
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
    
                        _instance_running = True
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                pass  
            except Exception:
                pass

        if _instance_running:
            # Main instance চলছে → pipe signal পাঠাও
            try:
                import ctypes as _ct2
                _k32b = _ct2.WinDLL("kernel32.dll", use_last_error=True)
                GENERIC_WRITE = 0x40000000
                OPEN_EXISTING = 3
                
                _k32b.CreateFileW.argtypes = [
                    _ct2.c_wchar_p, _ct2.c_ulong, _ct2.c_ulong, _ct2.c_void_p,
                    _ct2.c_ulong, _ct2.c_ulong, _ct2.c_void_p
                ]
                _k32b.CreateFileW.restype = _ct2.c_void_p
                _inv = _ct2.c_void_p(-1).value
                
                for _try in range(10):
                    h = _k32b.CreateFileW(_IPC_PIPE_NAME, GENERIC_WRITE, 0, None,
                                          OPEN_EXISTING, 0, None)
                    if h and h != _inv and h != 0:
                        msg = b"OPEN_CONTROL_PANEL"
                        written = _ct2.c_ulong(0)
                        _k32b.WriteFile.argtypes = [_ct2.c_void_p, _ct2.c_void_p, _ct2.c_ulong, _ct2.POINTER(_ct2.c_ulong), _ct2.c_void_p]
                        _k32b.WriteFile(h, msg, len(msg), _ct2.byref(written), None)
                        
                        _k32b.CloseHandle.argtypes = [_ct2.c_void_p]
                        _k32b.CloseHandle(h)
                        dlog("INFO", "--open-control-panel: OPEN_CONTROL_PANEL signal sent")
                        break
                    time.sleep(0.5)
                else:
                    dlog("WARNING", f"--open-control-panel: pipe unavailable after retries. Error: {_ct2.get_last_error()}")
            except Exception as _e2:
                dlog("ERROR", f"--open-control-panel: pipe error: {_e2}")
            sys.exit(0)

        else:
           
            dlog("INFO", "--open-control-panel: no running instance — starting main()")
            sys.argv = [sys.argv[0]]
            

    if "--control-panel" in sys.argv:
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import Qt
            import sys as _sys

            _app = QApplication(_sys.argv)
            _app.setStyle("Fusion")
            _app.setQuitOnLastWindowClosed(True)

            from PyQt6.QtWidgets import (
                QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QLabel, QPushButton, QFrame, QScrollArea, QButtonGroup,
                QSizePolicy, QGraphicsDropShadowEffect, QLineEdit,
                QFileDialog, QCheckBox, QMessageBox
            )
            from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QRect, QByteArray, QTimer
            from PyQt6.QtGui import (
                QColor, QPainter, QPainterPath, QBrush, QPen, QFont,
                QLinearGradient, QCursor, QIcon, QPixmap, QFileSystemModel,
                QRegion
            )
            try:
                from PyQt6.QtSvg import QSvgRenderer as _QSvgRenderer
                _HAS_SVG = True
            except ImportError:
                _HAS_SVG = False

            _BG    = "#07050d"
            _SIDE  = "#0a0818"
            _CARD  = "#100e1c"
            _CARD2 = "#161426"
            _BORD  = "#241f42"
            _ACC   = "#8b5cf6"
            _ACC2  = "#a78bfa"
            _ACC3  = "#6d28d9"
            _FG    = "#f0ecff"
            _MUTE  = "#6b6490"
            _GREEN = "#34d399"
            _RED   = "#f87171"
            _TEAL  = "#22d3ee"

            _STRIP_X_OFFSET = -1   
            _STRIP_WIDTH    = 4   
            # ─────────────────────────────────────────────────────────────────

            def _glow(widget, color=_ACC, radius=18):
                fx = QGraphicsDropShadowEffect()
                fx.setBlurRadius(radius)
                fx.setColor(QColor(color))
                fx.setOffset(0, 0)
                widget.setGraphicsEffect(fx)

            class _Card(QFrame):
                def __init__(self, parent=None, bg=_CARD, border=_BORD,
                             radius=14, accent_color=None, hoverable=False):
                    super().__init__(parent)
                    self._bg       = QColor(bg)
                    self._border   = QColor(border)
                    self._radius   = radius
                    self._accent   = QColor(accent_color) if accent_color else None
                    self._hoverable = hoverable
                    self._hovered  = False
                    self.setAutoFillBackground(False)
                    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

                def enterEvent(self, ev):
                    if self._hoverable:
                        self._hovered = True
                        self.update()
                    super().enterEvent(ev)

                def leaveEvent(self, ev):
                    if self._hoverable:
                        self._hovered = False
                        self.update()
                    super().leaveEvent(ev)

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    r = self.rect().adjusted(1, 1, -1, -1)
                    path = QPainterPath()
                    path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                        self._radius, self._radius)
                    p.fillPath(path, QBrush(self._bg))
                    border_color = self._border
                    if self._hoverable and self._hovered:
                        border_color = self._accent if self._accent else QColor(_ACC2)
                    p.setPen(QPen(border_color, 1))
                    p.drawPath(path)
                    if self._accent:
                        strip = QPainterPath()
                        strip.addRoundedRect(r.x() + _STRIP_X_OFFSET, r.y(),
                                             _STRIP_WIDTH, r.height(), 2, 2)
                        p.fillPath(strip, QBrush(self._accent))



            class _IconBox(QLabel):
                def __init__(self, glyph, size=38, bg="#1e0d40", fg="#c4b5fd",
                             radius=10, parent=None):
                    super().__init__(glyph, parent)
                    self._bg = QColor(bg)
                    self._r  = radius
                    self.setFixedSize(size, size)
                    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setFont(QFont("Segoe UI Emoji", size // 3))
                    self.setStyleSheet(f"color: {fg}; background: transparent;")

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.width(), self.height(),
                                        self._r, self._r)
                    p.fillPath(path, QBrush(self._bg))
                    super().paintEvent(ev)

            class _AppIconBox(QFrame):
                def __init__(self, pixmap=None, glyph="🔒", size=40,
                             bg="#1e0d40", fg="#c4b5fd", radius=12, parent=None):
                    super().__init__(parent)
                    self._pixmap = pixmap if (pixmap and not pixmap.isNull()) else None
                    self._glyph  = glyph
                    self._fg     = QColor(fg)
                    self._bg     = QColor("#1c1830" if self._pixmap else bg)
                    self._r      = radius
                    self.setFixedSize(size, size)

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.width(), self.height(),
                                        self._r, self._r)
                    p.fillPath(path, QBrush(self._bg))
                    if self._pixmap:
                        p.setClipPath(path)
                        x = (self.width() - self._pixmap.width()) // 2
                        y = (self.height() - self._pixmap.height()) // 2
                        p.drawPixmap(x, y, self._pixmap)
                    else:
                        p.setPen(QPen(self._fg))
                        p.setFont(QFont("Segoe UI Emoji", self.width() // 3))
                        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)

            class _NavBtn(QPushButton):
                def __init__(self, icon, text, active=False, parent=None):
                    super().__init__(f"  {icon}  {text}", parent)
                    self.setCheckable(True)
                    self.setChecked(active)
                    self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self.setFixedHeight(40)
                    self.setFont(QFont("Segoe UI", 9))
                    self._upd(active)
                    self.toggled.connect(self._upd)

                def _upd(self, c=False):
                    if c:
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                    stop:0 #221050, stop:1 #160d38);
                                color: {_ACC2}; border: none;
                                border-left: 3px solid {_ACC};
                                border-radius: 10px; text-align: left;
                                padding-left: 10px; font-size: 9pt; font-weight: bold;
                            }}""")
                    else:
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: transparent; color: {_MUTE};
                                border: none; border-radius: 10px;
                                text-align: left; padding-left: 14px; font-size: 9pt;
                            }}
                            QPushButton:hover {{
                                background: #130f24; color: #b0a0e0;
                            }}""")

            class _PillBtn(QPushButton):
                def __init__(self, text, active=False, color=_ACC, parent=None):
                    super().__init__(text, parent)
                    self._color = color
                    self._active_glow = None
                    self.setCheckable(True)
                    self.setChecked(active)
                    self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)
                    self.setFixedHeight(32)
                    f = QFont("Segoe UI", 9)
                    f.setBold(active)
                    self.setFont(f)
                    self._upd(active)
                    self.toggled.connect(self._on_tog)

                def _on_tog(self, c):
                    f = self.font(); f.setBold(c); self.setFont(f)
                    self._upd(c)
                    if c:
                        fx = QGraphicsDropShadowEffect()
                        fx.setBlurRadius(8)
                        fx.setColor(QColor(self._color))
                        fx.setOffset(0, 0)
                        self._active_glow = fx
                        self.setGraphicsEffect(fx)
                    else:
                        self._active_glow = None
                        self.setGraphicsEffect(None)

                def enterEvent(self, ev):
                    if self.isChecked() and self._active_glow:
                        self._active_glow.setBlurRadius(14)
                        _second = {
                            "#22d3ee": "#7c3aed",   # Session Once (teal) -> purple
                            "#22c55e": "#22d3ee",   # None / Paused (green) -> teal
                        }.get(self._color, f"{self._color}cc")
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {self._color}, stop:1 {_second});
                                color: white;
                                border: 1.5px solid rgba(255,255,255,0.55);
                                border-radius: 8px; padding: 0 12px;
                            }}""")
                    elif not self.isChecked():
                        r = int(self._color[1:3], 16)
                        g = int(self._color[3:5], 16)
                        b = int(self._color[5:7], 16)
                        # ── OPACITY TUNING: 0.0 থেকে 1.0 ──
                        _opacity = 0.4   # ← শুধু এটা বদলাও
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: {_CARD2}; color: {_FG};
                                border: 1px solid rgba({r},{g},{b},{_opacity});
                                border-radius: 8px; padding: 0 12px;
                            }}""")
                    super().enterEvent(ev)

                def leaveEvent(self, ev):
                    if self.isChecked() and self._active_glow:
                        self._active_glow.setBlurRadius(8)
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: {self._color}; color: white;
                                border: none; border-radius: 8px; padding: 0 12px;
                            }}
                            QPushButton:hover {{
                                background: {self._color};
                                border: 1px solid rgba(255,255,255,0.35);
                            }}""")
                    elif not self.isChecked():
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: {_CARD2}; color: {_MUTE};
                                border: 1px solid {_BORD}; border-radius: 8px;
                                padding: 0 12px;
                            }}""")
                    super().leaveEvent(ev)

                def _upd(self, c):
                    if c:
                        fx = QGraphicsDropShadowEffect()
                        fx.setBlurRadius(8)
                        fx.setColor(QColor(self._color))
                        fx.setOffset(0, 0)
                        self._active_glow = fx
                        self.setGraphicsEffect(fx)
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: {self._color}; color: white;
                                border: none; border-radius: 8px; padding: 0 12px;
                            }}
                            QPushButton:hover {{
                                background: {self._color};
                                border: 1px solid rgba(255,255,255,0.35);
                            }}""")
                    else:
                        self._active_glow = None
                        self.setStyleSheet(f"""
                            QPushButton {{
                                background: {_CARD2}; color: {_MUTE};
                                border: 1px solid {_BORD}; border-radius: 8px;
                                padding: 0 12px;
                            }}""")

            # ── Sidebar live-status widgets (spinner + rotating info ticker) ────
    
            class _StatusSpinner(QWidget):
                
                def __init__(self, size=12, color=_GREEN, parent=None):
                    super().__init__(parent)
                    self.setFixedSize(size, size)
                    self._angle = 0
                    self._color = QColor(color)
                    self._timer = QTimer(self)
                    self._timer.timeout.connect(self._tick)
                    self._timer.start(45)

                def set_color(self, color):
                    try:
                        self._color = QColor(color)
                        self.update()
                    except Exception:
                        pass

                def _tick(self):
                    self._angle = (self._angle + 9) % 360
                    self.update()

                def paintEvent(self, ev):
                    try:
                        p = QPainter(self)
                        p.setRenderHint(QPainter.RenderHint.Antialiasing)
                        pen = QPen(self._color)
                        pen.setWidth(2)
                        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                        p.setPen(pen)
                        r = self.rect().adjusted(1, 1, -1, -1)
                        p.drawArc(r, int(self._angle * 16), int(250 * 16))
                        p.end()
                    except Exception:
                        pass

                def stop(self):
                    try:
                        self._timer.stop()
                    except Exception:
                        pass

            class _RotatingStatus(QWidget):
                """প্রতি ~3 সেকেন্ডে একটা করে status item দেখায় (CPU/RAM,
                সর্বশেষ log, আজকের unlock count, failed attempts, version,
                update info), fade-in/fade-out দিয়ে — এবং প্রতিটির রঙ তার
                কন্টেন্ট অনুযায়ী বদলায়। get_items_fn ব্যর্থ হলে নিরাপদ
                fallback টেক্সট দেখানো হয়, app চালু/বন্ধে কোনো প্রভাব ফেলে না।"""
                def __init__(self, get_items_fn, spinner=None, interval_ms=3000, parent=None):
                    super().__init__(parent)
                    self._get_items = get_items_fn
                    self._spinner = spinner
                    self._idx = 0
                    self._cur_anim = None
                    lay = QHBoxLayout(self)
                    lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
                    self._label = QLabel("")
                    self._label.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
                    self._label.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                    self._label.setWordWrap(False)
                    self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    self._full_text = ""
                    self._label_max_w = 168   
                    self._label.setMaximumWidth(self._label_max_w)
                    lay.addWidget(self._label)
                    try:
                        from PyQt6.QtWidgets import QGraphicsOpacityEffect as _RSOpacityFx
                        self._fx = _RSOpacityFx(self._label)
                        self._fx.setOpacity(1.0)
                        self._label.setGraphicsEffect(self._fx)
                    except Exception:
                        self._fx = None
                    self._set_current(initial=True)
                    self._timer = QTimer(self)
                    self._timer.timeout.connect(self._advance)
                    self._timer.start(max(int(interval_ms), 1000))

                def _safe_items(self):
                    try:
                        items = self._get_items()
                        if items:
                            return items
                    except Exception as _e:
                        try:
                            dlog("ERROR", f"_sidebar_status_items failed: {type(_e).__name__}: {_e}")
                        except Exception:
                            pass
                        return [(f"Status error: {type(_e).__name__}", "#fbbf24")]
                    return [("Status: no items", "#fbbf24")]

                def _set_current(self, initial=False):
                    try:
                        items = self._safe_items()
                        if self._idx >= len(items):
                            self._idx = 0
                        text, color = items[self._idx]
                        self._full_text = text
                        fm = self._label.fontMetrics()
                        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, self._label_max_w)
                        self._label.setText(elided)
                        self._label.setToolTip(text)
                        self._label.setStyleSheet(f"color: {color}; background: transparent;")
                        if self._spinner is not None:
                            self._spinner.set_color(color)
                        if self._fx is not None:
                            if initial:
                                self._fx.setOpacity(1.0)
                            else:
                                self._fx.setOpacity(0.0)
                                anim = QPropertyAnimation(self._fx, b"opacity", self)
                                anim.setDuration(320)
                                anim.setStartValue(0.0)
                                anim.setEndValue(1.0)
                                anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
                                self._cur_anim = anim
                                anim.start()
                    except Exception:
                        pass

                def _advance(self):
                    try:
                        items = self._safe_items()
                        if not items:
                            return
                        if self._fx is None:
                            self._idx = (self._idx + 1) % len(items)
                            self._set_current()
                            return
                        fade_out = QPropertyAnimation(self._fx, b"opacity", self)
                        fade_out.setDuration(260)
                        fade_out.setStartValue(self._fx.opacity())
                        fade_out.setEndValue(0.0)
                        fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
                        n_items = len(items)
                        def _on_out_done():
                            try:
                                self._idx = (self._idx + 1) % max(n_items, 1)
                                self._set_current()
                            except Exception:
                                pass
                        fade_out.finished.connect(_on_out_done)
                        self._cur_anim = fade_out
                        fade_out.start()
                    except Exception:
                        pass

                def stop(self):
                    try:
                        self._timer.stop()
                    except Exception:
                        pass

            def _sidebar_status_items():
                
                items = []
                try:
                    proc = psutil.Process(os.getpid())
                    cpu_pct = proc.cpu_percent(interval=None)
                    mem_mb = proc.memory_info().rss / (1024 * 1024)
                    items.append((f"CPU {cpu_pct:.0f}%  ·  RAM {mem_mb:.0f}MB", _TEAL))
                except Exception:
                    pass
                try:
                    entries = load_security_log()
                    lbl_map = {"wrong_password": "Wrong password", "lockout_start": "Locked out",
                               "lockout_end": "Lockout ended", "success": "Unlocked"}
                    color_map = {"wrong_password": "#f59e0b", "lockout_start": _RED,
                                 "lockout_end": _GREEN, "success": _GREEN}
                    
                    _SKIP_WHERE = {"Control Panel", "Quit"}
                    last = None
                    for e in reversed(entries):
                        if e.get("where") not in _SKIP_WHERE:
                            last = e
                            break
                    if last:
                        et = last.get("type", "")
                        where = last.get("where", "")
                        if where.startswith("App:"):
                            where = where[4:]
                        if where.lower().endswith(".exe"):
                            where = where[:-4]
                        txt = f"Last: {lbl_map.get(et, et or '—')} — {where}"
                        items.append((txt[:46], color_map.get(et, _MUTE)))
                    else:
                        items.append(("No security events yet", _MUTE))
                except Exception:
                    pass
                try:
                    today = datetime.datetime.now().strftime("%Y-%m-%d")
                    entries = load_security_log()
                    unlocks_today = sum(1 for e in entries
                                         if e.get("type") == "success" and e.get("time", "").startswith(today))
                    items.append((f"{unlocks_today} unlock{'s' if unlocks_today != 1 else ''} today", _GREEN))
                except Exception:
                    pass
                try:
                    today = datetime.datetime.now().strftime("%Y-%m-%d")
                    entries = load_security_log()
                    failed_today = sum(1 for e in entries
                                        if e.get("type") == "wrong_password" and e.get("time", "").startswith(today))
                    items.append((f"{failed_today} failed attempt{'s' if failed_today != 1 else ''} today",
                                  _RED if failed_today else _MUTE))
                except Exception:
                    pass
                try:
                    items.append((f"DeskWarden {CURRENT_VERSION}", _ACC2))
                except Exception:
                    pass
                try:
                    with _update_lock:
                        checked = _update_result.get("checked")
                        latest = _update_result.get("latest")
                    if checked and latest and _version_tuple(latest) > _version_tuple(CURRENT_VERSION):
                        items.append((f"Update available: {latest}", "#fbbf24"))
                except Exception:
                    pass
                if not items:
                    items = [("Active · monitoring", _GREEN)]
                return items

            class _FirstRunSetupDialog(QWidget):
                """Forces the user to set a master password on first run,
                before the Control Panel interface is shown."""
                def __init__(self, on_done):
                    super().__init__()
                    self._on_done = on_done
                    self._allow_close = False
                    self.setWindowFlags(
                        Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint |
                        Qt.WindowType.Tool
                    )
                    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                    self.setFixedSize(420, 490)
                    sg = _app.primaryScreen().geometry()
                    self.move(sg.x() + (sg.width() - 420) // 2,
                              sg.y() + (sg.height() - 490) // 2)

                    outer = QVBoxLayout(self)
                    outer.setContentsMargins(0, 0, 0, 0)

                    card = _Card(self, bg=_CARD, border=_BORD, radius=16)
                    outer.addWidget(card)

                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(28, 24, 28, 24); cl.setSpacing(8)

                    # ── Logo in first-run dialog ──
                    _pm2 = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"))
                    if not _pm2.isNull():
                        _pm2 = _pm2.scaled(72, 72,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        class _SetupLogoBox(QWidget):
                            def __init__(self, px, sz=72, parent=None):
                                super().__init__(parent)
                                self._px = px
                                self.setFixedSize(sz, sz)
                                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                            def paintEvent(self, ev):
                                p2 = QPainter(self)
                                p2.setRenderHint(QPainter.RenderHint.Antialiasing)
                                p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                                path2 = QPainterPath()
                                path2.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
                                p2.setClipPath(path2)
                                p2.drawPixmap(0, 0, self.width(), self.height(), self._px)
                                p2.end()
                        icon = _SetupLogoBox(_pm2, 72)
                    else:
                        icon = QLabel("🔒")
                        icon.setFont(QFont("Segoe UI Emoji", 32))
                        icon.setStyleSheet(f"color: {_ACC2}; background: transparent;")
                        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    # Center the logo horizontally
                    icon_row = QHBoxLayout()
                    icon_row.addStretch()
                    icon_row.addWidget(icon)
                    icon_row.addStretch()
                    cl.addLayout(icon_row)

                    title = QLabel("Welcome to DeskWarden")
                    title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                    title.setStyleSheet(f"color: {_FG}; background: transparent;")
                    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cl.addWidget(title)

                    sub = QLabel(
                        "Set a password for the app before you start using it.\n"
                        "This password will be used to unlock locked apps and access Control Panel.")
                    sub.setFont(QFont("Segoe UI", 9))
                    sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    sub.setWordWrap(True)
                    cl.addWidget(sub)

                    cl.addSpacing(6)

                    _pw_style = f"""
                        QLineEdit {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 12px;
                        }}
                        QLineEdit:focus {{ border: 1px solid {_ACC}; }}"""

                    nl = QLabel("New Password")
                    nl.setFont(QFont("Segoe UI", 9))
                    nl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    cl.addWidget(nl)
                    self._new_pw = QLineEdit()
                    self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
                    self._new_pw.setFixedHeight(38)
                    self._new_pw.setStyleSheet(_pw_style)
                    cl.addWidget(self._new_pw)

                    cnl = QLabel("Confirm Password")
                    cnl.setFont(QFont("Segoe UI", 9))
                    cnl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    cl.addWidget(cnl)
                    self._con_pw = QLineEdit()
                    self._con_pw.setEchoMode(QLineEdit.EchoMode.Password)
                    self._con_pw.setFixedHeight(38)
                    self._con_pw.setStyleSheet(_pw_style)
                    cl.addWidget(self._con_pw)

                    self._err = QLabel("")
                    self._err.setFont(QFont("Segoe UI", 9))
                    self._err.setStyleSheet(f"color: {_RED}; background: transparent;")
                    self._err.setWordWrap(True)
                    cl.addWidget(self._err)

                    save_btn = QPushButton("✓  Set Password")
                    save_btn.setFixedHeight(40)
                    save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    save_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    save_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_ACC}; color: white; border: none;
                            border-radius: 10px; padding: 0 20px;
                        }}
                        QPushButton:hover {{ background: {_ACC2}; }}""")
                    save_btn.clicked.connect(self._submit)
                    cl.addWidget(save_btn)

                    _BLUE = "#3b82f6"
                    self._save_glow = QGraphicsDropShadowEffect()
                    self._save_glow.setBlurRadius(0)
                    self._save_glow.setColor(QColor(_BLUE))
                    self._save_glow.setOffset(0, 0)
                    save_btn.setGraphicsEffect(self._save_glow)

                    def _save_enter(ev):
                        self._save_glow.setBlurRadius(25)
                        QPushButton.enterEvent(save_btn, ev)

                    def _save_leave(ev):
                        self._save_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(save_btn, ev)

                    save_btn.enterEvent = _save_enter
                    save_btn.leaveEvent = _save_leave

                    skip_btn = QPushButton("Skip for now")
                    skip_btn.setFixedHeight(34)
                    skip_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    skip_btn.setFont(QFont("Segoe UI", 9))
                    skip_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; color: {_MUTE}; border: none;
                            border-radius: 8px; padding: 0 20px;
                        }}
                        QPushButton:hover {{ color: {_FG}; }}""")
                    skip_btn.clicked.connect(self._skip)
                    cl.addWidget(skip_btn)

                    self._skip_glow = QGraphicsDropShadowEffect()
                    self._skip_glow.setBlurRadius(0)
                    self._skip_glow.setColor(QColor(_RED))
                    self._skip_glow.setOffset(0, 0)
                    skip_btn.setGraphicsEffect(self._skip_glow)

                    def _skip_enter(ev):
                        self._skip_glow.setBlurRadius(20)
                        QPushButton.enterEvent(skip_btn, ev)

                    def _skip_leave(ev):
                        self._skip_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(skip_btn, ev)

                    skip_btn.enterEvent = _skip_enter
                    skip_btn.leaveEvent = _skip_leave

                    self._new_pw.returnPressed.connect(self._submit)
                    self._con_pw.returnPressed.connect(self._submit)
                    self._new_pw.setFocus()

                def keyPressEvent(self, ev):
                    # Block Esc and Alt+F4
                    if ev.key() == Qt.Key.Key_Escape:
                        ev.ignore(); return
                    if (ev.key() == Qt.Key.Key_F4 and
                            ev.modifiers() & Qt.KeyboardModifier.AltModifier):
                        ev.ignore(); return
                    super().keyPressEvent(ev)

                def closeEvent(self, ev):
                    if self._allow_close:
                        ev.accept()
                    else:
                        ev.ignore()

                def _submit(self):
                    n = self._new_pw.text()
                    c = self._con_pw.text()
                    if len(n) < 4:
                        self._err.setText("✗ Must be at least 4 characters."); return
                    if n != c:
                        self._err.setText("✗ Passwords do not match."); return
                    cfg = load_config()
                    cfg["password_hash"] = hash_pw(n)
                    save_config(cfg)
                    self._allow_close = True
                    self.close()
                    self._on_done()

                def _skip(self):
                    self._allow_close = True
                    self.close()
                    self._on_done()

            class _ControlPanelWin(QMainWindow):
                MODE_CFG = {
                    "ask_always":      ("🔑", "#1e0d40", "#c4b5fd", _ACC,  "🔑  Ask Always",           "Asks for password every time the app is opened"),
                    "session_once":    ("✅", "#071e28", "#67e8f9", _TEAL, "✅  Session Once",          "Once unlocked, stays unlocked until the PC is shut down"),
                    "permanent_block": ("🚫", "#200810", "#fca5a5", _RED,  "🚫  Always Block",          "Always blocked — cannot open unless unlocked from Control Panel"),
                    "paused":          ("⏸", "#0f1a0f", "#86efac", "#22c55e", "⏸  None",               "In the list but no restriction — switch anytime"),
                }

                def __init__(self):
                    super().__init__()
                    self.setWindowTitle("DeskWarden — Control Panel")
                    self.setWindowFlags(
                        Qt.WindowType.Window |
                        Qt.WindowType.Tool |
                        Qt.WindowType.FramelessWindowHint
                    )
                    self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
                    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                    from PyQt6.QtGui import QPalette, QColor
                    pal = self.palette()
                    pal.setColor(QPalette.ColorRole.Window, QColor(_BG))
                    self.setPalette(pal)
                    self.resize(900, 600)
                    self.setMinimumSize(900, 600)
                    self._cfg = load_config()
                    self._active_section = "apps"
                    self._section_widgets = {}
                    self._drag_pos = None
                    self._build()
                    self._apply_style()

                def closeEvent(self, ev):
                    
                    ev.accept()
                    try:
                        if getattr(self, "_status_rotator", None):
                            self._status_rotator.stop()
                        if getattr(self, "_status_spinner", None):
                            self._status_spinner.stop()
                    except Exception:
                        pass
                    try:
                        from PyQt6.QtWidgets import QApplication
                        app = QApplication.instance()
                        if app:
                            app.quit()
                    except Exception:
                        pass

                # ── events ────────────────────────────────────────────────────
                def showEvent(self, event):
                    super().showEvent(event)
                    self._update_handles()
                    self.repaint()
                    
                    if not getattr(self, "_auto_checked_update", False):
                        self._auto_checked_update = True
                        if self._cfg.get("auto_update", True):
                            def _silent_check(res):
                                if res.get("update_available"):
                                    from PyQt6.QtCore import QTimer as _QT
                                    _QT.singleShot(0, self._apply_update_result)
                                    self._update_result_pending = res
                            check_for_update_async(callback=_silent_check)

                def resizeEvent(self, event):
                    super().resizeEvent(event)
                    self._update_handles()
                   
                    ov = getattr(self, "_switch_overlay", None)
                    if ov is not None:
                        ov.setGeometry(self._content.rect())

                def mousePressEvent(self, event):
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    super().mousePressEvent(event)

                def mouseMoveEvent(self, event):
                    if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
                        self.move(event.globalPosition().toPoint() - self._drag_pos)
                    super().mouseMoveEvent(event)

                def mouseReleaseEvent(self, event):
                    self._drag_pos = None
                    super().mouseReleaseEvent(event)

                # ── Resize handles (transparent edge widgets) ─────────────────
                def _make_handles(self):
                    """Create 8 transparent resize-handle widgets on top of window."""
                    B = 7  
                    win = self

                    _cur = {
                        "L":  Qt.CursorShape.SizeHorCursor,
                        "R":  Qt.CursorShape.SizeHorCursor,
                        "T":  Qt.CursorShape.SizeVerCursor,
                        "B":  Qt.CursorShape.SizeVerCursor,
                        "TL": Qt.CursorShape.SizeFDiagCursor,
                        "TR": Qt.CursorShape.SizeBDiagCursor,
                        "BL": Qt.CursorShape.SizeBDiagCursor,
                        "BR": Qt.CursorShape.SizeFDiagCursor,
                    }

                    class _Handle(QWidget):
                        def __init__(self_, edge):
                            super().__init__(win)
                            self_._edge = edge
                            self_._dragging = False
                            self_._start_geom = None
                            self_._start_mouse = None
                            self_.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                            self_.setCursor(QCursor(_cur[edge]))
                            self_.raise_()

                        def mousePressEvent(self_, ev):
                            if ev.button() == Qt.MouseButton.LeftButton:
                                self_._dragging   = True
                                self_._start_geom  = win.geometry()
                                self_._start_mouse = ev.globalPosition().toPoint()
                                win._drag_pos = None   

                        def mouseMoveEvent(self_, ev):
                            if not self_._dragging:
                                return
                            gpos = ev.globalPosition().toPoint()
                            dx   = gpos.x() - self_._start_mouse.x()
                            dy   = gpos.y() - self_._start_mouse.y()
                            sg   = self_._start_geom
                            minW = win.minimumWidth()
                            minH = win.minimumHeight()
                            x, y, w, h = sg.x(), sg.y(), sg.width(), sg.height()
                            e = self_._edge
                            if "R" in e:
                                w = max(minW, sg.width()  + dx)
                            if "B" in e:
                                h = max(minH, sg.height() + dy)
                            if "L" in e:
                                nw = max(minW, sg.width() - dx)
                                x  = sg.x() + (sg.width() - nw)
                                w  = nw
                            if "T" in e:
                                nh = max(minH, sg.height() - dy)
                                y  = sg.y() + (sg.height() - nh)
                                h  = nh
                            win.setGeometry(x, y, w, h)

                        def mouseReleaseEvent(self_, ev):
                            self_._dragging = False

                    self._handles = {}
                    for edge in ("L", "R", "T", "B", "TL", "TR", "BL", "BR"):
                        h = _Handle(edge)
                        h.show()
                        self._handles[edge] = h

                def _update_handles(self):
                    """Reposition all 8 resize handles to match current window size."""
                    if not hasattr(self, "_handles"):
                        self._make_handles()
                    B = 7
                    w = self.width()
                    h = self.height()
                    geom = {
                        "TL": (0,       0,       B,   B),
                        "T":  (B,       0,       w-2*B, B),
                        "TR": (w-B,     0,       B,   B),
                        "L":  (0,       B,       B,   h-2*B),
                        "R":  (w-B,     B,       B,   h-2*B),
                        "BL": (0,       h-B,     B,   B),
                        "B":  (B,       h-B,     w-2*B, B),
                        "BR": (w-B,     h-B,     B,   B),
                    }
                    for edge, (ex, ey, ew, eh) in geom.items():
                        hdl = self._handles[edge]
                        hdl.setGeometry(ex, ey, ew, eh)
                        hdl.raise_()

                def _apply_style(self):
                    self.setStyleSheet(f"""
                        QMainWindow {{
                            background: {_BG};
                        }}
                        QMainWindow > QWidget {{
                            background: {_BG}; color: {_FG};
                            font-family: 'Segoe UI';
                        }}
                        QWidget {{
                            background: {_BG}; color: {_FG};
                            font-family: 'Segoe UI';
                        }}
                        QScrollArea {{ border: none; background: {_BG}; }}
                        QScrollBar:vertical {{
                            background: transparent; width: 6px; border-radius: 3px;
                            margin: 4px 0;
                        }}
                        QScrollBar::handle:vertical {{
                            background: {_BORD}; border-radius: 3px; min-height: 30px;
                        }}
                        QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
                        QScrollBar::add-line:vertical,
                        QScrollBar::sub-line:vertical {{ height: 0; }}
                        QLineEdit {{
                            background: #08061a; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px;
                            padding: 6px 10px; font-size: 10pt;
                            selection-background-color: {_ACC};
                        }}
                        QCheckBox {{ color: {_FG}; }}
                        QCheckBox::indicator {{
                            width: 18px; height: 18px;
                            border: 1px solid {_BORD}; border-radius: 5px;
                            background: {_CARD2};
                        }}
                        QCheckBox::indicator:checked {{
                            background: {_ACC}; border-color: {_ACC};
                        }}
                    """)

                def _build(self):
                    root = QWidget()
                    self.setCentralWidget(root)
                    rl = QVBoxLayout(root)
                    rl.setContentsMargins(0, 0, 0, 0)
                    rl.setSpacing(0)

                    class _DragBar(QWidget):
                        def mousePressEvent(self_, ev):
                            if ev.button() == Qt.MouseButton.LeftButton:
                                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                        def mouseMoveEvent(self_, ev):
                            if self._drag_pos is not None and ev.buttons() == Qt.MouseButton.LeftButton:
                                self.move(ev.globalPosition().toPoint() - self._drag_pos)
                        def mouseReleaseEvent(self_, ev):
                            self._drag_pos = None
                    tb = _DragBar(); tb.setFixedHeight(42)
                    tb.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0d0b1a, stop:1 {_SIDE});")
                    tbl = QHBoxLayout(tb)
                    tbl.setContentsMargins(16, 0, 12, 0)
                    _traffic_colors = ("#a855f7", "#22d3ee", "#E74C3C", "#89F336")  
                    _traffic_dots = []
                    for dc in _traffic_colors:
                        dot = QLabel(); dot.setFixedSize(12, 12)
                        dot.setStyleSheet(f"background: {dc}; border-radius: 6px;")
                        try:
                            from PyQt6.QtWidgets import QGraphicsOpacityEffect as _DotOpacityFx
                            _fx = _DotOpacityFx(dot)
                            _fx.setOpacity(1.0)
                            dot.setGraphicsEffect(_fx)
                            dot._opacity_fx = _fx
                        except Exception:
                            pass
                        tbl.addWidget(dot)
                        _traffic_dots.append(dot)
                    tb._traffic_dots = _traffic_dots

                    def _animate_traffic_dots():
                        try:
                            import random as _dotrandom
                            live_dots = [d for d in _traffic_dots if getattr(d, "_opacity_fx", None) is not None]
                            if live_dots:
                                target_dot = _dotrandom.choice(live_dots)
                                target_opacity = _dotrandom.choice([0.3, 0.45, 1.0, 1.0])
                                anim = QPropertyAnimation(target_dot._opacity_fx, b"opacity")
                                anim.setDuration(_dotrandom.randint(450, 900))
                                anim.setStartValue(target_dot._opacity_fx.opacity())
                                anim.setEndValue(target_opacity)
                                anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
                                target_dot._cur_anim = anim
                                anim.start()
                        except Exception:
                            pass
                        finally:
                            try:
                                from PyQt6.QtCore import QTimer as _DotTimer
                                _DotTimer.singleShot(__import__("random").randint(500, 1400), _animate_traffic_dots)
                            except Exception:
                                pass

                    try:
                        from PyQt6.QtCore import QTimer as _DotTimer
                        _DotTimer.singleShot(400, _animate_traffic_dots)
                    except Exception:
                        pass
                    tbl.addSpacing(10)
                    tl = QLabel("DeskWarden  ·  Control Panel")
                    tl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
                    tl.setStyleSheet(f"color: #7a70a0; background: transparent;")
                    tbl.addWidget(tl); tbl.addStretch()
                    close_b = QPushButton("✕"); close_b.setFixedSize(28, 22)
                    close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    close_b.setStyleSheet(f"""
                        QPushButton {{ background: transparent; color: {_MUTE};
                            border: none; font-size: 10pt; border-radius: 4px; }}
                        QPushButton:hover {{ background: #7f1d1d; color: white;
                            border-radius: 4px; }}""")
                    close_b.clicked.connect(self.close)
                    tbl.addWidget(close_b)
                    rl.addWidget(tb)

                    sep = QFrame(); sep.setFixedHeight(1)
                    sep.setStyleSheet(f"background: {_BORD};")
                    rl.addWidget(sep)

                    body = QWidget(); bl = QHBoxLayout(body)
                    bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)

                    sb = QWidget(); sb.setMinimumWidth(216); sb.setMaximumWidth(280)
                    sb.setStyleSheet(f"background: {_SIDE};")
                    sbl = QVBoxLayout(sb)
                    sbl.setContentsMargins(0, 0, 0, 0); sbl.setSpacing(0)

                    brand = QWidget()
                    brand.setStyleSheet(f"background: {_SIDE};")
                    brandl = QHBoxLayout(brand)
                    brandl.setContentsMargins(16, 18, 16, 18); brandl.setSpacing(12)
                    _script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    # ── Load full icon from assets folder ──
                    _full_icon_path = os.path.join(_script_dir, "assets", "deskwarden_full_icon.png")
                    _pm = QPixmap(_full_icon_path)
                    li = None
                    if not _pm.isNull():
                        _pm = _pm.scaled(56, 56,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        class _LogoBox(QWidget):
                            def __init__(self, px, sz=56, parent=None):
                                super().__init__(parent)
                                self._px = px
                                self.setFixedSize(sz, sz)
                                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                            def paintEvent(self, ev):
                                p2 = QPainter(self)
                                p2.setRenderHint(QPainter.RenderHint.Antialiasing)
                                p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                                p2.drawPixmap(0, 0, self.width(), self.height(), self._px)
                                p2.end()
                        li = _LogoBox(_pm, 56)
                    if li is None:
                        li = _IconBox("🔒", 56, "#1e0840", "#c4b5fd", 14)
                    _glow(li, _ACC, 16)
                    brandl.addWidget(li)
                    btl = QVBoxLayout(); btl.setSpacing(2)
                    anl = QLabel("DeskWarden")
                    anl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
                    anl.setStyleSheet(
                        "color: #f5f0ff;"
                        " background: transparent;"
                    )
                    _glow(anl, QColor(200, 180, 255, 80), 16)
                    avl = QLabel("v1.0.0  ·  Windows")
                    avl.setFont(QFont("Segoe UI", 8))
                    avl.setStyleSheet(f"color: #7c6da8; background: transparent; letter-spacing: 0.3px;")
                    btl.addWidget(anl); btl.addWidget(avl)
                    brandl.addLayout(btl)
                    sbl.addWidget(brand)

                    ssep = QFrame(); ssep.setFixedHeight(1)
                    ssep.setStyleSheet(f"background: {_BORD};")
                    sbl.addWidget(ssep); sbl.addSpacing(8)

                    nav_grp = QButtonGroup(self); nav_grp.setExclusive(True)
                    self._nav_btns = {}
                    nav_items = [
                        ("🛡️", "Locked Apps",    "apps"),
                        ("🔑", "Password",       "password"),
                        ("📋", "Security Log",   "log"),
                        ("⚙️", "Settings",       "settings_cfg"),
                    ]
                    for icon, lbl_txt, key in nav_items:
                        nb = _NavBtn(icon, lbl_txt, active=(key == "apps"))
                        nav_grp.addButton(nb)
                        self._nav_btns[key] = nb
                        wrap = QWidget(); wrap.setStyleSheet(f"background: {_SIDE};")
                        wl = QHBoxLayout(wrap)
                        wl.setContentsMargins(10, 2, 10, 2); wl.addWidget(nb)
                        sbl.addWidget(wrap)
                        nb.clicked.connect(lambda _=False, k=key: self._switch(k))

                    sbl.addStretch()

                    # ════════════════════════════════════════════════════════
                    
                    STATUS_GAP_ABOVE_LINE   = 8    
                    STATUS_MARGIN_LEFT      = 16   
                    STATUS_MARGIN_TOP       = 6    
                    STATUS_MARGIN_RIGHT     = 16   
                    STATUS_MARGIN_BOTTOM    = 12   
                    STATUS_SPINNER_TEXT_GAP = 8    
                
                    SPINNER_OFFSET_LEFT  = 0   
                    SPINNER_OFFSET_TOP   = 0  
                    SPINNER_OFFSET_RIGHT = 0   
                    SPINNER_OFFSET_BOTTOM= 0   

                    TEXT_OFFSET_LEFT     = 0   
                    TEXT_OFFSET_TOP      = 8   
                    TEXT_OFFSET_RIGHT    = 0  
                    TEXT_OFFSET_BOTTOM   = -1   
                    # ════════════════════════════════════════════════════════

                    _status_sep = QFrame(); _status_sep.setFixedHeight(1)
                    _status_sep.setStyleSheet(f"background: {_BORD};")
                    sbl.addWidget(_status_sep)
                    sbl.addSpacing(STATUS_GAP_ABOVE_LINE)

                    status_bar = QWidget()
                    status_bar.setStyleSheet(f"background: {_SIDE};")
                    stl = QHBoxLayout(status_bar)
                    stl.setContentsMargins(STATUS_MARGIN_LEFT, STATUS_MARGIN_TOP,
                                            STATUS_MARGIN_RIGHT, STATUS_MARGIN_BOTTOM)
                    stl.setSpacing(STATUS_SPINNER_TEXT_GAP)
                    stl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                    self._status_rotator = None
                    self._status_spinner = None
                    try:
                        spinner = _StatusSpinner(size=12, color=_GREEN)
                        _glow(spinner, _GREEN, 10)
                      
                        spinner_wrap = QWidget(); spinner_wrap.setStyleSheet("background: transparent;")
                        spinner_wrap_l = QHBoxLayout(spinner_wrap)
                        spinner_wrap_l.setContentsMargins(
                            SPINNER_OFFSET_LEFT, SPINNER_OFFSET_TOP,
                            SPINNER_OFFSET_RIGHT, SPINNER_OFFSET_BOTTOM)
                        spinner_wrap_l.addWidget(spinner, 0, Qt.AlignmentFlag.AlignVCenter)
                        stl.addWidget(spinner_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

                        rot_status = _RotatingStatus(_sidebar_status_items, spinner=spinner, interval_ms=3000)
                       
                        text_wrap = QWidget(); text_wrap.setStyleSheet("background: transparent;")
                        text_wrap_l = QHBoxLayout(text_wrap)
                        text_wrap_l.setContentsMargins(
                            TEXT_OFFSET_LEFT, TEXT_OFFSET_TOP,
                            TEXT_OFFSET_RIGHT, TEXT_OFFSET_BOTTOM)
                        text_wrap_l.addWidget(rot_status, 0, Qt.AlignmentFlag.AlignVCenter)
                        stl.addWidget(text_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

                        self._status_spinner = spinner
                        self._status_rotator = rot_status
                    except Exception as _e:
                        try:
                            dlog("ERROR", f"sidebar status widget failed to build: {type(_e).__name__}: {_e}")
                        except Exception:
                            pass
                      
                        dot_s = QLabel(); dot_s.setFixedSize(8, 8)
                        dot_s.setStyleSheet(f"background: #fbbf24; border-radius: 4px;")
                        stl.addWidget(dot_s, 0, Qt.AlignmentFlag.AlignVCenter)
                        stl_l = QLabel(f"Status widget failed: {type(_e).__name__}")
                        stl_l.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
                        stl_l.setStyleSheet(f"color: #fbbf24; background: transparent;")
                        stl.addWidget(stl_l, 0, Qt.AlignmentFlag.AlignVCenter)
                    stl.addStretch()
                    sbl.addWidget(status_bar)

                    bl.addWidget(sb, 1)
                    vsep = QFrame(); vsep.setFixedWidth(1)
                    vsep.setStyleSheet(f"background: {_BORD};")
                    bl.addWidget(vsep)

                    self._content = QWidget()
                    self._content.setStyleSheet(f"background: {_BG};")
                    cl = QVBoxLayout(self._content)
                    cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

                    topbar = QWidget(); topbar.setFixedHeight(58)
                    topbar.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #131120, stop:1 {_CARD}); border-bottom: 1px solid {_BORD};")
                    topl = QHBoxLayout(topbar)
                    topl.setContentsMargins(24, 0, 24, 0)
                    self._section_title_lbl = QLabel("Locked Apps")
                    self._section_title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
                    self._section_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
                    topl.addWidget(self._section_title_lbl); topl.addSpacing(10)
                    self._section_sub_lbl = QLabel("Apps that require password on launch")
                    self._section_sub_lbl.setFont(QFont("Segoe UI", 9))
                    self._section_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    topl.addWidget(self._section_sub_lbl); topl.addStretch()
                    cl.addWidget(topbar)

                    self._scroll = QScrollArea()
                    self._scroll.setWidgetResizable(True)
                    self._scroll.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    self._scroll_inner = QWidget()
                    self._scroll_inner.setStyleSheet(f"background: {_BG};")
                    self._scroll_lay = QVBoxLayout(self._scroll_inner)
                    self._scroll_lay.setContentsMargins(18, 16, 18, 16)
                    self._scroll_lay.setSpacing(12)
                    self._scroll_inner.setMaximumWidth(1200)
                    self._scroll.setWidget(self._scroll_inner)
                    cl.addWidget(self._scroll)

                    bl.addWidget(self._content, 4)
                    rl.addWidget(body, 1)

                    self._build_apps_panel()
                    self._build_password_panel()
                    self._build_log_panel()
                    self._build_cp_panel()
                    self._build_diag_log_panel()
                    self._build_crash_log_panel()
                    self._scroll_lay.addStretch()
                    self._switch("apps")

                def _switch(self, key):
                    titles = {
                        "apps":         ("Locked Apps",  "Apps that require password on launch"),
                        "password":     ("Password",     "Set or change your master password"),
                        "log":          ("Security Log", "Recent authentication events"),
                        "settings_cfg": ("Settings",     "Startup and general preferences"),
                        "diag_log":     ("Diagnostic Log", "Real-time event log for troubleshooting"),
                        "crash_log":    ("Crash Log",       "Error & exception reports"),
                    }
                    t, s = titles.get(key, ("", ""))
                    old_key = getattr(self, "_active_section", None)

                   
                    if old_key == key:
                        if key == "log":       self._refresh_log()
                        if key == "diag_log":  self._refresh_diag_log()
                        if key == "crash_log": self._refresh_crash_log()
                        return

                    self._active_section = key

                    # ── Overlay fade approach ─────────────────────────────────────
                   

                    overlay = getattr(self, "_switch_overlay", None)
                    if overlay is None:
                        from PyQt6.QtWidgets import QGraphicsOpacityEffect as _OFx
                        overlay = __import__("PyQt6.QtWidgets", fromlist=["QWidget"]).QWidget(self._content)
                        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                        overlay.setStyleSheet(f"background: {_BG}; border: none;")
                        overlay.hide()
                        overlay.raise_()
                        self._switch_overlay = overlay

                        _ofx = _OFx(overlay)
                        _ofx.setOpacity(0.0)
                        overlay.setGraphicsEffect(_ofx)
                        self._switch_overlay_fx = _ofx

                    
                    overlay.setGeometry(self._content.rect())
                    overlay.raise_()
                    overlay.show()

                    overlay_fx = self._switch_overlay_fx

                    for a in ("_ov_anim_out", "_ov_anim_in"):
                        anim = getattr(self, a, None)
                        if anim:
                            anim.stop()
                        setattr(self, a, None)

                    def _do_switch():
                        
                        self._section_title_lbl.setText(t)
                        self._section_sub_lbl.setText(s)
                        for k, w in self._section_widgets.items():
                            w.setVisible(k == key)
                        for k, nb in self._nav_btns.items():
                            nb.setChecked(k == key)
                        self._scroll.verticalScrollBar().setValue(0)
                        if key == "log":       self._refresh_log()
                        if key == "diag_log":  self._refresh_diag_log()
                        if key == "crash_log": self._refresh_crash_log()
                        if key != "password":  self._reset_pw_form()
                        # overlay fade-out (reveal new content)
                        anim_in = QPropertyAnimation(overlay_fx, b"opacity", overlay)
                        anim_in.setDuration(160)
                        anim_in.setStartValue(1.0)
                        anim_in.setEndValue(0.0)
                        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
                        def _on_done():
                            overlay.hide()
                        anim_in.finished.connect(_on_done)
                        self._ov_anim_in = anim_in
                        anim_in.start()

                    # overlay fade-in (hide old content)
                    overlay_fx.setOpacity(0.0)
                    anim_out = QPropertyAnimation(overlay_fx, b"opacity", overlay)
                    anim_out.setDuration(110)
                    anim_out.setStartValue(0.0)
                    anim_out.setEndValue(1.0)
                    anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
                    anim_out.finished.connect(_do_switch)
                    self._ov_anim_out = anim_out
                    anim_out.start()


                def _build_apps_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

                    card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(12)

                    hdr = QHBoxLayout()
                    hl = QLabel("PROTECTED APPS")
                    hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    hl.setStyleSheet(f"color: #b794f6; background: transparent;")
                    hdr.addWidget(hl); hdr.addStretch()
                    self._count_badge = QLabel("0 app(s)")
                    self._count_badge.setFont(QFont("Segoe UI", 8))
                    self._count_badge.setStyleSheet(f"""
                        color: {_MUTE}; background: {_CARD2};
                        border: 1px solid {_BORD}; border-radius: 10px;
                        padding: 2px 10px;""")
                    hdr.addWidget(self._count_badge)
                    cl.addLayout(hdr)

                    div = QFrame(); div.setFixedHeight(1)
                    div.setStyleSheet(f"background: {_BORD};")
                    cl.addWidget(div)

                    self._apps_container_lay = cl
                    self._apps_card = card

                    add_btn = QPushButton("＋  Add App")
                    add_btn.setFixedHeight(38)
                    add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    add_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    add_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 {_ACC}, stop:1 {_ACC3});
                            color: white; border: none; border-radius: 10px;
                            padding: 0 20px;
                        }}
                        QPushButton:hover {{
                            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 {_ACC2}, stop:1 {_ACC});
                        }}""")
                    _glow(add_btn, _ACC, 20)
                    add_btn.clicked.connect(self._add_app)

                    pl.addWidget(card)
                    cl.addWidget(add_btn)

                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["apps"] = panel
                    self._refresh_apps()

                def _refresh_apps(self):
                    self._cfg = load_config()
                    apps = self._cfg.get("locked_apps", [])
                    self._count_badge.setText(f"{len(apps)} app(s)")
                    while self._apps_container_lay.count() > 3:
                        item = self._apps_container_lay.takeAt(2)
                        if item and item.widget():
                            item.widget().deleteLater()

                    if not apps:
                        empty = QLabel("No apps locked yet. Click '＋ Add App' below.")
                        empty.setFont(QFont("Segoe UI", 9))
                        empty.setStyleSheet(f"color: {_MUTE}; background: transparent; padding: 10px 0;")
                        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        self._apps_container_lay.insertWidget(
                            self._apps_container_lay.count() - 1, empty)
                        return

                    for i, app_item in enumerate(apps):
                        exe  = app_item.get("exe", "") if isinstance(app_item, dict) else app_item
                        mode = app_item.get("mode", "ask_always") if isinstance(app_item, dict) else "ask_always"
                        mc   = self.MODE_CFG.get(mode, self.MODE_CFG["ask_always"])

                        ac = _Card(bg=_CARD2, border=_BORD, radius=14,
                                   accent_color=mc[3], hoverable=True)
                        acl = QVBoxLayout(ac)
                        acl.setContentsMargins(16, 12, 12, 12); acl.setSpacing(8)

                        top = QHBoxLayout(); top.setSpacing(12)
                        app_path = app_item.get("path", "") if isinstance(app_item, dict) else ""
                        pm = self._exe_icon_pixmap(app_path)
                        icon = _AppIconBox(pm, mc[0], 40, mc[1], mc[2], 12)
                        top.addWidget(icon)

                        info_l = QVBoxLayout(); info_l.setSpacing(2)
                        nl = QLabel(exe)
                        nl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                        nl.setStyleSheet(f"color: {_FG}; background: transparent;")
                        dl = QLabel(mc[5])
                        dl.setFont(QFont("Segoe UI", 8))
                        dl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                        info_l.addWidget(nl); info_l.addWidget(dl)
                        top.addLayout(info_l); top.addStretch()

                        rm_btn = QPushButton("✕  Remove")
                        rm_btn.setFixedHeight(30)
                        rm_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        rm_btn.setStyleSheet(f"""
                            QPushButton {{
                                background: #200810; color: #fca5a5;
                                border: 1px solid #3d1020; border-radius: 8px;
                                padding: 0 12px; font-size: 8pt; font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background: #3d1020; color: white;
                                border-color: {_RED};
                            }}""")
                        rm_btn.clicked.connect(lambda _=False, idx=i: self._remove_app(idx))
                        _glow(rm_btn, _RED, 0)

                        def _rm_enter(ev, b=rm_btn):
                            b.graphicsEffect().setBlurRadius(14)
                            QPushButton.enterEvent(b, ev)

                        def _rm_leave(ev, b=rm_btn):
                            b.graphicsEffect().setBlurRadius(0)
                            QPushButton.leaveEvent(b, ev)

                        rm_btn.enterEvent = _rm_enter
                        rm_btn.leaveEvent = _rm_leave
                        top.addWidget(rm_btn)
                        acl.addLayout(top)

                        div2 = QFrame(); div2.setFrameShape(QFrame.Shape.HLine)
                        div2.setStyleSheet(f"color: {_BORD};"); div2.setFixedHeight(1)
                        acl.addWidget(div2)

                        pills = QHBoxLayout(); pills.setSpacing(6)
                        bg2 = QButtonGroup(self); bg2.setExclusive(True)
                        for mk, (_, _, _, pc, pl_lbl, _) in self.MODE_CFG.items():
                            pb = _PillBtn(pl_lbl, active=(mk == mode), color=pc)
                            bg2.addButton(pb)
                            pills.addWidget(pb)
                            pb.clicked.connect(
                                lambda _=False, idx=i, mkey=mk, desc=dl:
                                    self._set_mode(idx, mkey, desc))
                        acl.addLayout(pills)

                        self._apps_container_lay.insertWidget(
                            self._apps_container_lay.count() - 1, ac)

                def _add_app(self):
                    path, _ = QFileDialog.getOpenFileName(
                        self, "Select .exe to lock", "",
                        "Executable (*.exe);;All files (*.*)")
                    if path:
                        name = os.path.basename(path).lower()
                        apps = self._cfg.get("locked_apps", [])
                        existing = [(a.get("exe","") if isinstance(a, dict) else a)
                                    for a in apps]
                        if name not in existing:
                            apps.append({"exe": name, "mode": "ask_always", "path": path})
                            self._cfg["locked_apps"] = apps
                            save_config(self._cfg)
                            self._refresh_apps()

                def _exe_icon_pixmap(self, path, size=28):
                    try:
                        if path and os.path.isfile(path):
                            if not hasattr(self, "_fs_icon_model"):
                                self._fs_icon_model = QFileSystemModel()
                                self._fs_icon_model.setRootPath("")
                            model = self._fs_icon_model
                            model.setRootPath(os.path.dirname(path))
                            idx = model.index(path)
                            icon = model.fileIcon(idx)
                            if icon and not icon.isNull():
                                pm = icon.pixmap(size, size)
                                if pm and not pm.isNull():
                                    return pm
                    except Exception:
                        pass
                    return None

                def _remove_app(self, idx):
                    apps = self._cfg.get("locked_apps", [])
                    if idx < len(apps):
                        apps.pop(idx)
                        self._cfg["locked_apps"] = apps
                        save_config(self._cfg)
                        self._refresh_apps()

                def _set_mode(self, idx, mode_key, desc_lbl):
                    apps = self._cfg.get("locked_apps", [])
                    if idx < len(apps):
                        if isinstance(apps[idx], dict):
                            apps[idx]["mode"] = mode_key
                        else:
                            apps[idx] = {"exe": apps[idx], "mode": mode_key}
                        self._cfg["locked_apps"] = apps
                        save_config(self._cfg)
                        mc = self.MODE_CFG.get(mode_key, self.MODE_CFG["ask_always"])
                        desc_lbl.setText(mc[5])
                        self._refresh_apps()

                def _build_password_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

                    card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(18, 14, 18, 20); cl.setSpacing(10)

                    hdr = QHBoxLayout()
                    hl = QLabel("MASTER PASSWORD")
                    hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    hl.setStyleSheet(f"color: #b794f6; background: transparent;")
                    hdr.addWidget(hl); hdr.addStretch()
                    has_pw = bool(self._cfg.get("password_hash"))
                    bc = _GREEN if has_pw else _RED
                    bt = "✓ Set" if has_pw else "✗ Not set"
                    badge = QLabel(bt)
                    badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    badge.setStyleSheet(f"""
                        color: white; background: {bc};
                        border-radius: 10px; padding: 2px 10px;""")
                    hdr.addWidget(badge)
                    self._pw_badge = badge
                    cl.addLayout(hdr)

                    div = QFrame(); div.setFixedHeight(1)
                    div.setStyleSheet(f"background: {_BORD};")
                    cl.addWidget(div)

                    self._pw_toggle_btn = QPushButton(
                        "🔑  Change Password" if has_pw else "🔑  Set Password")
                    self._pw_toggle_btn.setFixedHeight(36)
                    self._pw_toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._pw_toggle_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    self._pw_toggle_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px;
                            padding: 0 20px; text-align: left;
                        }}
                        QPushButton:hover {{ background: {_BORD}; }}""")
                    self._pw_toggle_btn.clicked.connect(self._toggle_pw_form)

                    self._pwtoggle_glow = QGraphicsDropShadowEffect()
                    self._pwtoggle_glow.setBlurRadius(0)
                    self._pwtoggle_glow.setColor(QColor(_ACC))
                    self._pwtoggle_glow.setOffset(0, 0)
                    self._pw_toggle_btn.setGraphicsEffect(self._pwtoggle_glow)

                    def _pwtoggle_enter(ev):
                        self._pwtoggle_glow.setBlurRadius(16)
                        QPushButton.enterEvent(self._pw_toggle_btn, ev)
                    def _pwtoggle_leave(ev):
                        self._pwtoggle_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._pw_toggle_btn, ev)
                    self._pw_toggle_btn.enterEvent = _pwtoggle_enter
                    self._pw_toggle_btn.leaveEvent = _pwtoggle_leave

                    cl.addWidget(self._pw_toggle_btn)

                    self._pw_form = QWidget(); self._pw_form.setStyleSheet("background: transparent;")
                    fl = QVBoxLayout(self._pw_form)
                    fl.setContentsMargins(0, 8, 0, 0); fl.setSpacing(8)

                    if has_pw:
                        ol = QLabel("Current Password")
                        ol.setFont(QFont("Segoe UI", 9))
                        ol.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                        fl.addWidget(ol)
                        self._old_pw = QLineEdit(); self._old_pw.setEchoMode(QLineEdit.EchoMode.Password)
                        fl.addWidget(self._old_pw)
                    else:
                        self._old_pw = None

                    nl = QLabel("New Password")
                    nl.setFont(QFont("Segoe UI", 9))
                    nl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    fl.addWidget(nl)
                    self._new_pw = QLineEdit(); self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
                    fl.addWidget(self._new_pw)

                    cnl = QLabel("Confirm New Password")
                    cnl.setFont(QFont("Segoe UI", 9))
                    cnl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    fl.addWidget(cnl)
                    self._con_pw = QLineEdit(); self._con_pw.setEchoMode(QLineEdit.EchoMode.Password)
                    fl.addWidget(self._con_pw)

                    self._pw_err = QLabel("")
                    self._pw_err.setFont(QFont("Segoe UI", 9))
                    self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
                    fl.addWidget(self._pw_err)

                    save_btn = QPushButton("💾  Save Password")
                    save_btn.setFixedHeight(36)
                    save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    save_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    save_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_ACC}; color: white; border: none;
                            border-radius: 8px; padding: 0 20px;
                        }}
                        QPushButton:hover {{ background: {_ACC2}; }}""")
                    save_btn.clicked.connect(self._save_pw)
                    fl.addWidget(save_btn)

                    self._savepw_glow = QGraphicsDropShadowEffect()
                    self._savepw_glow.setBlurRadius(0)
                    self._savepw_glow.setColor(QColor(_ACC))
                    self._savepw_glow.setOffset(0, 0)
                    save_btn.setGraphicsEffect(self._savepw_glow)

                    def _savepw_enter(ev):
                        self._savepw_glow.setBlurRadius(22)
                        QPushButton.enterEvent(save_btn, ev)

                    def _savepw_leave(ev):
                        self._savepw_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(save_btn, ev)

                    save_btn.enterEvent = _savepw_enter
                    save_btn.leaveEvent = _savepw_leave

                    self._pw_form.setVisible(False)
                    cl.addWidget(self._pw_form)

                    pl.addWidget(card)
                    pl.addStretch()
                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["password"] = panel
                    panel.setVisible(False)

                def _toggle_pw_form(self):
                    showing = not self._pw_form.isVisible()
                    self._pw_form.setVisible(showing)
                    has_pw = bool(self._cfg.get("password_hash"))
                    if showing:
                        self._pw_toggle_btn.setText("✕  Cancel")
                    else:
                        self._pw_toggle_btn.setText(
                            "🔑  Change Password" if has_pw else "🔑  Set Password")
                        self._reset_pw_form()

                def _reset_pw_form(self):
                    if getattr(self, "_old_pw", None):
                        self._old_pw.clear()
                    if getattr(self, "_new_pw", None):
                        self._new_pw.clear()
                    if getattr(self, "_con_pw", None):
                        self._con_pw.clear()
                    if getattr(self, "_pw_err", None):
                        self._pw_err.setText("")
                    if getattr(self, "_pw_form", None):
                        self._pw_form.setVisible(False)
                    if getattr(self, "_pw_toggle_btn", None):
                        has_pw = bool(self._cfg.get("password_hash"))
                        self._pw_toggle_btn.setText(
                            "🔑  Change Password" if has_pw else "🔑  Set Password")

                def _save_pw(self):
                    o = self._old_pw.text() if self._old_pw else ""
                    n = self._new_pw.text()
                    c = self._con_pw.text()
                    has_pw = bool(self._cfg.get("password_hash"))
                    if has_pw and hash_pw(o) != self._cfg.get("password_hash",""):
                        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
                        self._pw_err.setText("✗ Current password is incorrect."); return
                    if len(n) < 4:
                        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
                        self._pw_err.setText("✗ Must be at least 4 characters."); return
                    if n != c:
                        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
                        self._pw_err.setText("✗ Passwords do not match."); return
                    self._cfg["password_hash"] = hash_pw(n)
                    save_config(self._cfg)
                    self._pw_err.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                    self._pw_err.setText("✓ Password saved.")
                    if self._old_pw: self._old_pw.clear()
                    self._new_pw.clear(); self._con_pw.clear()
                    self._pw_badge.setText("✓ Set")
                    self._pw_badge.setStyleSheet(f"""
                        color: white; background: {_GREEN};
                        border-radius: 10px; padding: 2px 10px;""")

                def _build_log_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

                    card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(8)

                    hdr = QHBoxLayout()
                    hl = QLabel("🛡️  AUTH EVENTS")
                    hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    hl.setStyleSheet(f"color: #b794f6; background: transparent;")
                    hdr.addWidget(hl); hdr.addStretch()
                    clr_btn = QPushButton("🗑  Clear Log")
                    clr_btn.setFixedHeight(28)
                    clr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    clr_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: #1e0d18; color: #fca5a5;
                            border: 1px solid #3d1020; border-radius: 6px;
                            padding: 0 10px; font-size: 8pt;
                        }}
                        QPushButton:hover {{ background: #3d0d10; color: white; }}""")
                    clr_btn.clicked.connect(self._clear_log)
                    hdr.addWidget(clr_btn)

                    self._clrlog_glow = QGraphicsDropShadowEffect()
                    self._clrlog_glow.setBlurRadius(0)
                    self._clrlog_glow.setColor(QColor(_RED))
                    self._clrlog_glow.setOffset(0, 0)
                    clr_btn.setGraphicsEffect(self._clrlog_glow)

                    def _clrlog_enter(ev):
                        self._clrlog_glow.setBlurRadius(16)
                        QPushButton.enterEvent(clr_btn, ev)

                    def _clrlog_leave(ev):
                        self._clrlog_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(clr_btn, ev)

                    clr_btn.enterEvent = _clrlog_enter
                    clr_btn.leaveEvent = _clrlog_leave
                    cl.addLayout(hdr)

                    div = QFrame(); div.setFixedHeight(1)
                    div.setStyleSheet(f"background: {_BORD};")
                    cl.addWidget(div)

                    self._log_container_lay = cl
                    self._log_card = card

                    pl.addWidget(card)
                    pl.addStretch()
                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["log"] = panel
                    panel.setVisible(False)

                def _refresh_log(self):
                    while self._log_container_lay.count() > 2:
                        item = self._log_container_lay.takeAt(2)
                        if item and item.widget():
                            item.widget().deleteLater()

                    entries = load_security_log()
                    recent = list(reversed(entries))[:30]
                    EVENT_ICON = {
                        "wrong_password": ("⚠", "#f59e0b"),
                        "lockout_start":  ("🔒", _RED),
                        "lockout_end":    ("🔓", _GREEN),
                        "success":        ("✅", _GREEN),
                    }
                    type_map = {
                        "wrong_password": "Wrong Password",
                        "lockout_start":  "Locked Out",
                        "lockout_end":    "Lockout Ended",
                        "success":        "Unlocked",
                    }
                    if not recent:
                        el = QLabel("No security events recorded yet.")
                        el.setFont(QFont("Segoe UI", 9))
                        el.setStyleSheet(f"color: {_MUTE}; background: transparent; padding: 8px 0;")
                        self._log_container_lay.addWidget(el)
                        return

                    for ev in recent:
                        et = ev.get("type", "")
                        icon_g, color = EVENT_ICON.get(et, ("ℹ️", _MUTE))

                        row = _Card(bg=_CARD2, border=_BORD, radius=8,
                                    accent_color=color)
                        rl = QHBoxLayout(row)
                        rl.setContentsMargins(16, 8, 16, 8); rl.setSpacing(10)

                        il = QLabel(icon_g)
                        il.setFont(QFont("Segoe UI Emoji", 14))
                        il.setStyleSheet(f"color: {color}; background: transparent;")
                        il.setFixedWidth(28)
                        rl.addWidget(il)

                        info_w = QWidget(); info_w.setStyleSheet("background: transparent;")
                        infl = QVBoxLayout(info_w)
                        infl.setContentsMargins(0, 0, 0, 0); infl.setSpacing(1)

                        lbl_txt = type_map.get(et, et)
                        where_  = ev.get("where", "")
                        tl_l = QLabel(f"{lbl_txt}  —  {where_}")
                        tl_l.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                        tl_l.setStyleSheet(f"color: {_FG}; background: transparent;")
                        infl.addWidget(tl_l)

                        tl_t = QLabel(ev.get("time", ""))
                        tl_t.setFont(QFont("Segoe UI", 8))
                        tl_t.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                        infl.addWidget(tl_t)

                        if ev.get("note"):
                            nl = QLabel(ev["note"])
                            nl.setFont(QFont("Segoe UI", 8))
                            nl.setStyleSheet(f"color: {color}; background: transparent;")
                            infl.addWidget(nl)

                        rl.addWidget(info_w, 1)
                        self._log_container_lay.addWidget(row)

                def _clear_log(self):
                    _save_security_log([])
                    self._refresh_log()

                def _build_cp_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(10)

                    # helper: compact section header row
                    def _sec_hdr(icon, title, subtitle, icon_bg, icon_fg):
                        hw = QWidget(); hw.setStyleSheet("background: transparent;")
                        hl = QHBoxLayout(hw); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(10)
                        ib = _IconBox(icon, 32, icon_bg, icon_fg, 9)
                        hl.addWidget(ib)
                        tl = QVBoxLayout(); tl.setSpacing(0)
                        t = QLabel(title)
                        t.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                        t.setStyleSheet(f"color: {_FG}; background: transparent;")
                        s = QLabel(subtitle)
                        s.setFont(QFont("Segoe UI", 8))
                        s.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                        tl.addWidget(t); tl.addWidget(s)
                        hl.addLayout(tl); hl.addStretch()
                        return hw

                    # ── STARTUP card ──────────────────────────────────────────
                    card = _Card(panel, bg=_CARD, border=_BORD, radius=14)
                    cl = QVBoxLayout(card)
                    cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(10)

                    cl.addWidget(_sec_hdr("⚡", "Startup", "Launch behavior", "#1a1030", "#c4b5fd"))

                    div = QFrame(); div.setFixedHeight(1)
                    div.setStyleSheet(f"background: {_BORD};")
                    cl.addWidget(div)

                    row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
                    row_l = QHBoxLayout(row_w)
                    row_l.setContentsMargins(0, 0, 0, 0); row_l.setSpacing(0)
                    cb_lbl = QWidget(); cb_lbl.setStyleSheet("background: transparent;")
                    cb_lbl_l = QVBoxLayout(cb_lbl); cb_lbl_l.setSpacing(1); cb_lbl_l.setContentsMargins(0,0,0,0)
                    cb_title = QLabel("Start DeskWarden with Windows")
                    cb_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
                    cb_title.setStyleSheet(f"color: {_FG}; background: transparent;")
                    cb_sub = QLabel("DeskWarden will start automatically when you log in")
                    cb_sub.setFont(QFont("Segoe UI", 8))
                    cb_sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    cb_lbl_l.addWidget(cb_title); cb_lbl_l.addWidget(cb_sub)
                    row_l.addWidget(cb_lbl, 1)
                    self._auto_cb = QCheckBox("")
                    self._auto_cb.setFont(QFont("Segoe UI", 9))
                    self._auto_cb.setChecked(self._cfg.get("autostart", True))
                    self._auto_cb.stateChanged.connect(self._toggle_auto)
                    row_l.addWidget(self._auto_cb)
                    cl.addWidget(row_w)

                    warn = QLabel("⚠  If disabled, DeskWarden will not protect your apps after a restart.")
                    warn.setFont(QFont("Segoe UI", 8))
                    warn.setStyleSheet("color: #f59e0b; background: #1a1200; border: 1px solid #3d2e00; border-radius: 7px; padding: 5px 10px;")
                    warn.setWordWrap(True)
                    cl.addWidget(warn)

                    pl.addWidget(card)

                    # ── BACKUP & RESTORE card ─────────────────────────────────
                    bcard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
                    bcl = QVBoxLayout(bcard)
                    bcl.setContentsMargins(18, 14, 18, 16); bcl.setSpacing(10)

                    bcl.addWidget(_sec_hdr("💾", "Backup & Restore", "Save or load your settings", "#0e1a10", "#86efac"))

                    bdiv = QFrame(); bdiv.setFixedHeight(1)
                    bdiv.setStyleSheet(f"background: {_BORD};")
                    bcl.addWidget(bdiv)

                    bdesc = QLabel("Keep a backup of your locked apps and settings. Restore them anytime — useful before reinstalling DeskWarden.")
                    bdesc.setFont(QFont("Segoe UI", 8))
                    bdesc.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    bdesc.setWordWrap(True)
                    bcl.addWidget(bdesc)

                    brow = QHBoxLayout(); brow.setSpacing(8)

                    export_btn = QPushButton("⬇  Export Settings")
                    export_btn.setFixedHeight(34)
                    export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    export_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    export_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 {_ACC}, stop:1 {_ACC3});
                            color: white; border: none; border-radius: 9px; padding: 0 16px;
                        }}
                        QPushButton:hover {{ background: {_ACC2}; }}""")
                    export_btn.clicked.connect(self._export_settings)
                    brow.addWidget(export_btn)

                    self._export_glow = QGraphicsDropShadowEffect()
                    self._export_glow.setBlurRadius(0)
                    self._export_glow.setColor(QColor(_ACC))
                    self._export_glow.setOffset(0, 0)
                    export_btn.setGraphicsEffect(self._export_glow)

                    def _export_enter(ev):
                        self._export_glow.setBlurRadius(18)
                        QPushButton.enterEvent(export_btn, ev)

                    def _export_leave(ev):
                        self._export_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(export_btn, ev)

                    export_btn.enterEvent = _export_enter
                    export_btn.leaveEvent = _export_leave

                    import_btn = QPushButton("⬆  Import Settings")
                    import_btn.setFixedHeight(34)
                    import_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    import_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    import_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 9px; padding: 0 16px;
                        }}
                        QPushButton:hover {{ background: #1e1a34; border-color: {_ACC}; }}""")
                    import_btn.clicked.connect(self._import_settings)
                    brow.addWidget(import_btn)

                    self._import_glow = QGraphicsDropShadowEffect()
                    self._import_glow.setBlurRadius(0)
                    self._import_glow.setColor(QColor(_TEAL))
                    self._import_glow.setOffset(0, 0)
                    import_btn.setGraphicsEffect(self._import_glow)

                    def _import_enter(ev):
                        self._import_glow.setBlurRadius(18)
                        QPushButton.enterEvent(import_btn, ev)

                    def _import_leave(ev):
                        self._import_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(import_btn, ev)

                    import_btn.enterEvent = _import_enter
                    import_btn.leaveEvent = _import_leave
                    brow.addStretch()

                    bcl.addLayout(brow)

                    self._backup_status = QLabel("")
                    self._backup_status.setFont(QFont("Segoe UI", 8))
                    self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                    self._backup_status.setWordWrap(True)
                    bcl.addWidget(self._backup_status)

                    pl.addWidget(bcard)

                    # ── AUTO UPDATE card ──────────────────────────────────────
                    ucard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
                    ucl = QVBoxLayout(ucard)
                    ucl.setContentsMargins(18, 14, 18, 16); ucl.setSpacing(10)

                    ucl.addWidget(_sec_hdr("🔄", "Auto Update", "Keep DeskWarden up to date", "#071828", "#67e8f9"))

                    udiv = QFrame(); udiv.setFixedHeight(1)
                    udiv.setStyleSheet(f"background: {_BORD};")
                    ucl.addWidget(udiv)

                    # Auto update toggle row
                    auto_upd_row = QWidget(); auto_upd_row.setStyleSheet("background: transparent;")
                    auto_upd_l = QHBoxLayout(auto_upd_row)
                    auto_upd_l.setContentsMargins(0, 0, 0, 0); auto_upd_l.setSpacing(0)
                    au_lbl_w = QWidget(); au_lbl_w.setStyleSheet("background: transparent;")
                    au_lbl_vl = QVBoxLayout(au_lbl_w); au_lbl_vl.setSpacing(1); au_lbl_vl.setContentsMargins(0,0,0,0)
                    au_title = QLabel("Automatically check for updates")
                    au_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
                    au_title.setStyleSheet(f"color: {_FG}; background: transparent;")
                    au_sub = QLabel("DeskWarden will check when you open Control Panel")
                    au_sub.setFont(QFont("Segoe UI", 8))
                    au_sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    au_lbl_vl.addWidget(au_title); au_lbl_vl.addWidget(au_sub)
                    auto_upd_l.addWidget(au_lbl_w, 1)
                    self._auto_update_cb = QCheckBox("")
                    self._auto_update_cb.setChecked(self._cfg.get("auto_update", True))
                    self._auto_update_cb.stateChanged.connect(self._toggle_auto_update)
                    auto_upd_l.addWidget(self._auto_update_cb)
                    ucl.addWidget(auto_upd_row)

                    # Last checked label
                    last_checked = self._cfg.get("last_update_check", "")
                    last_checked_txt = f"Last checked: {last_checked}" if last_checked else "Last checked: Never"
                    self._last_checked_lbl = QLabel(last_checked_txt)
                    self._last_checked_lbl.setFont(QFont("Segoe UI", 8))
                    self._last_checked_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    ucl.addWidget(self._last_checked_lbl)

                    urow = QHBoxLayout(); urow.setSpacing(10)

                    self._update_btn = QPushButton("🔍  Check for Update")
                    self._update_btn.setFixedHeight(34)
                    self._update_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._update_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._update_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 {_ACC}, stop:1 {_ACC3});
                            color: white; border: none; border-radius: 9px; padding: 0 16px;
                        }}
                        QPushButton:hover {{ background: {_ACC2}; }}
                        QPushButton:disabled {{ background: {_CARD2}; color: {_MUTE}; }}""")
                    self._update_btn.clicked.connect(self._check_update)
                    urow.addWidget(self._update_btn)

                    self._updchk_glow = QGraphicsDropShadowEffect()
                    self._updchk_glow.setBlurRadius(0)
                    self._updchk_glow.setColor(QColor(_ACC))
                    self._updchk_glow.setOffset(0, 0)
                    self._update_btn.setGraphicsEffect(self._updchk_glow)

                    def _updchk_enter(ev):
                        self._updchk_glow.setBlurRadius(20)
                        QPushButton.enterEvent(self._update_btn, ev)

                    def _updchk_leave(ev):
                        self._updchk_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._update_btn, ev)

                    self._update_btn.enterEvent = _updchk_enter
                    self._update_btn.leaveEvent = _updchk_leave

                    self._update_status = QLabel(f"Current version: {CURRENT_VERSION}")
                    self._update_status.setFont(QFont("Segoe UI", 8))
                    self._update_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    self._update_status.setWordWrap(True)
                    urow.addWidget(self._update_status, 1)

                    ucl.addLayout(urow)

                    pl.addWidget(ucard)
                    # ── end AUTO UPDATE card ──────────────────────────────────

                    # ── ADVANCED card ─────────────────────────────────────────
                    acard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
                    acl = QVBoxLayout(acard)
                    acl.setContentsMargins(18, 14, 18, 16); acl.setSpacing(10)

                    acl.addWidget(_sec_hdr("🛠️", "Advanced", "Developer & troubleshooting tools", "#0f1620", "#94a3b8"))

                    adiv = QFrame(); adiv.setFixedHeight(1)
                    adiv.setStyleSheet(f"background: {_BORD};")
                    acl.addWidget(adiv)

                    arow = QWidget(); arow.setStyleSheet("background: transparent;")
                    arow_l = QHBoxLayout(arow)
                    arow_l.setContentsMargins(0, 0, 0, 0); arow_l.setSpacing(12)

                    diag_icon = QLabel("🔍")
                    diag_icon.setFont(QFont("Segoe UI", 14))
                    diag_icon.setStyleSheet("background: transparent;")
                    diag_icon.setFixedWidth(24)
                    arow_l.addWidget(diag_icon)

                    diag_txt_w = QWidget(); diag_txt_w.setStyleSheet("background: transparent;")
                    diag_txt_l = QVBoxLayout(diag_txt_w); diag_txt_l.setSpacing(1); diag_txt_l.setContentsMargins(0,0,0,0)
                    diag_title_lbl = QLabel("Diagnostic Log")
                    diag_title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
                    diag_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
                    diag_sub_lbl = QLabel("Real-time event log for troubleshooting")
                    diag_sub_lbl.setFont(QFont("Segoe UI", 8))
                    diag_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    diag_txt_l.addWidget(diag_title_lbl); diag_txt_l.addWidget(diag_sub_lbl)
                    arow_l.addWidget(diag_txt_w, 1)

                    open_diag_btn = QPushButton("View Log →")
                    open_diag_btn.setFixedHeight(30)
                    open_diag_btn.setFixedWidth(90)
                    open_diag_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    open_diag_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    open_diag_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_MUTE};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 10px;
                        }}
                        QPushButton:hover {{
                            background: #1e1a34; border-color: {_ACC}; color: {_FG};
                        }}
                        QPushButton:pressed {{ background: #5b21b6; color: white; }}""")
                    open_diag_btn.clicked.connect(lambda: self._switch("diag_log"))

                    self._open_diag_glow = QGraphicsDropShadowEffect()
                    self._open_diag_glow.setBlurRadius(0)
                    self._open_diag_glow.setColor(QColor(_ACC))
                    self._open_diag_glow.setOffset(0, 0)
                    open_diag_btn.setGraphicsEffect(self._open_diag_glow)

                    def _open_diag_enter(ev):
                        self._open_diag_glow.setBlurRadius(14)
                        QPushButton.enterEvent(open_diag_btn, ev)
                    def _open_diag_leave(ev):
                        self._open_diag_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(open_diag_btn, ev)
                    open_diag_btn.enterEvent = _open_diag_enter
                    open_diag_btn.leaveEvent = _open_diag_leave

                    arow_l.addWidget(open_diag_btn)

                    acl.addWidget(arow)

                    # divider between rows
                    crow_div = QFrame(); crow_div.setFixedHeight(1)
                    crow_div.setStyleSheet(f"background: {_BORD};")
                    acl.addWidget(crow_div)

                    # ── Crash Log row ─────────────────────────────────────────
                    crash_row = QWidget(); crash_row.setStyleSheet("background: transparent;")
                    crash_row_l = QHBoxLayout(crash_row)
                    crash_row_l.setContentsMargins(0, 0, 0, 0); crash_row_l.setSpacing(12)

                    crash_icon = QLabel("💥")
                    crash_icon.setFont(QFont("Segoe UI", 14))
                    crash_icon.setStyleSheet("background: transparent;")
                    crash_icon.setFixedWidth(24)
                    crash_row_l.addWidget(crash_icon)

                    crash_txt_w = QWidget(); crash_txt_w.setStyleSheet("background: transparent;")
                    crash_txt_l = QVBoxLayout(crash_txt_w); crash_txt_l.setSpacing(1); crash_txt_l.setContentsMargins(0,0,0,0)
                    crash_title_lbl = QLabel("Crash Log")
                    crash_title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
                    crash_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
                    crash_sub_lbl = QLabel("Error & exception reports")
                    crash_sub_lbl.setFont(QFont("Segoe UI", 8))
                    crash_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    crash_txt_l.addWidget(crash_title_lbl); crash_txt_l.addWidget(crash_sub_lbl)
                    crash_row_l.addWidget(crash_txt_w, 1)

                    open_crash_btn = QPushButton("View Log →")
                    open_crash_btn.setFixedHeight(30)
                    open_crash_btn.setFixedWidth(90)
                    open_crash_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    open_crash_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    open_crash_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_MUTE};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 10px;
                        }}
                        QPushButton:hover {{
                            background: #2a1010; border-color: #ef4444; color: #fca5a5;
                        }}
                        QPushButton:pressed {{ background: #7f1d1d; color: white; }}""")

                    open_crash_btn.clicked.connect(lambda: self._switch("crash_log"))

                    self._open_crash_glow = QGraphicsDropShadowEffect()
                    self._open_crash_glow.setBlurRadius(0)
                    self._open_crash_glow.setColor(QColor(_RED))
                    self._open_crash_glow.setOffset(0, 0)
                    open_crash_btn.setGraphicsEffect(self._open_crash_glow)

                    def _open_crash_enter(ev):
                        self._open_crash_glow.setBlurRadius(14)
                        QPushButton.enterEvent(open_crash_btn, ev)
                    def _open_crash_leave(ev):
                        self._open_crash_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(open_crash_btn, ev)
                    open_crash_btn.enterEvent = _open_crash_enter
                    open_crash_btn.leaveEvent = _open_crash_leave

                    crash_row_l.addWidget(open_crash_btn)

                    acl.addWidget(crash_row)
                    pl.addWidget(acard)
                    # ── end ADVANCED card ─────────────────────────────────────

                    pl.addStretch()

                    # ── Footer ────────────────────────────────────────────────
                    footer = QWidget(); footer.setStyleSheet("background: transparent;")
                    fl = QVBoxLayout(footer)
                    fl.setContentsMargins(0, 4, 0, 14); fl.setSpacing(4)

                    ver_lbl = QLabel(
                        '<span style="color:#f5f0ff; font-weight:700;">DeskWarden</span>'
                        '&nbsp;&nbsp;'
                        '<span style="color:#c4b5fd;">v1.0.0</span>'
                    )
                    ver_lbl.setFont(QFont("Segoe UI", 9))
                    ver_lbl.setStyleSheet("background: transparent;")
                    ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    ver_lbl.setTextFormat(Qt.TextFormat.RichText)
                    fl.addWidget(ver_lbl)

                    crafted = QLabel(
                        'Crafted with <span style="color:#ff6b9d;">❤️</span> by '
                        '<span style="color:#c4b5fd; font-weight:700;">'
                        'Tahasinur Rahman Muntasir</span>'
                    )
                    crafted.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
                    crafted.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    crafted.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    crafted.setTextFormat(Qt.TextFormat.RichText)
                    fl.addWidget(crafted)

                    _GH_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAQAAADZc7J/AAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAAAmJLR0QA/4ePzL8AAAAJcEhZcwAADsQAAA7EAZUrDhsAAAAHdElNRQfmCgEPKDcQeWFjAAACvklEQVRIx5WVTUhVURDHf+e8VxT6CqLCikwJLAkJBcssooIUoqLc9gEuItq1bdcqsE2QgRIhrduEm+iDsqDvVoKWQuhTovJFUfiReM+ZaXG73feh771mNjPc+/9z5sx/5hgKLcF2DrCXnVRTCcwyySAvGGAETwlLsJtuxnFonjvS3KCFRDH4Bq6QKYBme4arbFoK3sgTpCg89Gc0LwY/wFAZ4NDfcygf3vQf8JCiKbf2x/8FV5QnbAxvHSyXOBsyddApqzTDb1NY4xptl05dy1D4rRbhMWqAFvpZD7Ccu3LEBryVbvlot+raxLp5Q2bFd/lIjVy0u8xyc09OmoWQIsMJXoGlOzpWyr0JVFVV5+SnONG/5uSnzP7N3gSpWCO92CT1HI0O6eychtFKszJbXWb1v3jOuri8NuotB9kc5ZaFUkplARsn1bRbWmNxHpf9phTBftMhWcJvheGoogp56LQMe+QqYr0Ow3SUNMg3KYfgmzTEBNNJKv/12VSUvAGACrMmTiptWZgiZpmJwhmd13Ig8zod/zdjmYjiNOmyCNKajpMJy2AUfzf3yzr0Q/0RN3vE8jLec7fNkJSCD2lffG+el7CDsXhID/sRX6yFo77dZ430GDvAch212qStkhK0QfrksxSyePni+3yDz9kJPaGuW5gyesGNyx23UdBlWi9nfH+OKvuD067eL8vdmFPsiVrZhaKn3Iy/5pOKokZ6gmyCm84UrtuueK42MYAm5VYwq5elzle5NpfOqWLYr8sneJq73psZRvf5TyL6xY8t/MqbigmtzoV/KFzth3iPHnODQSCqgUgxghHaFmtxIwNIlT/mz8s593UpAlnqYQHYQBdTKFqtE4sTZOgK1/lSlqCFHsZq3GQOwaTWOMbpZU/+45rMI/C85h11te2pfWxjCylgmsnUaO3z9ANGC5/3P34ayHPeViwcAAAAJXRFWHRkYXRlOmNyZWF0ZQAyMDIyLTEwLTAxVDE1OjQwOjU1KzAwOjAww+IFgQAAACV0RVh0ZGF0ZTptb2RpZnkAMjAyMi0xMC0wMVQxNTo0MDo1NSswMDowMLK/vT0AAAAgdEVYdHNvZnR3YXJlAGh0dHBzOi8vaW1hZ2VtYWdpY2sub3JnvM8dnQAAABh0RVh0VGh1bWI6OkRvY3VtZW50OjpQYWdlcwAxp/+7LwAAABh0RVh0VGh1bWI6OkltYWdlOjpIZWlnaHQANTEyj41TgQAAABd0RVh0VGh1bWI6OkltYWdlOjpXaWR0aAA1MTIcfAPcAAAAGXRFWHRUaHVtYjo6TWltZXR5cGUAaW1hZ2UvcG5nP7JWTgAAABd0RVh0VGh1bWI6Ok1UaW1lADE2NjQ2Mzg4NTVnbLKnAAAAE3RFWHRUaHVtYjo6U2l6ZQAyMTg3MUJCQ8i0nAAAAEd0RVh0VGh1bWI6OlVSSQBmaWxlOi8vLi91cGxvYWRzLzU2L3FmNHRTSkMvMzY4NS9naXRodWJfbG9nb19pY29uXzIyOTI3OC5wbmehvAJxAAAAAElFTkSuQmCC"
                    _FB_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAABrVBMVEUAAAAYd/IWd/IYefQXd/IYePIXdvIZd/EZd/IYd/QadfQaefIYdvIXd/MZePEYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYePEYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/IZd/Ife/IbefIYd/JDkfSEtvirzvrE3Py31fuiyPqJufgYd/IcefJ9svjp8v4Yd/JyrPf3+v8Yd/IvhfPX5/0Yd/Jiovb7/f/V5v2hyPoYd/LU5v05i/QYd/IYd/IvhfMaePK31fsiffOz0vsbefKcxfkYd/J+s/gYd/KfxvpGkvUYd/IYd/IYePIYd/MYd/IYd/IYd/IYd/IYd/IYd/IYd/IYd/ITdPJ7sfj///+kyvoWdvIYd/IWdvIVdfIXdvIXd/IvhfP////3+v9RmfUUdfKgx/qbxPk6i/R3r/ehyPoSdPJ2rvefx/oogfM0h/Qzh/QwhfOHuPirzvoyhvOQvvnn8f7k7/3j7/3v9f70+P7m8P5opveiyfqexvrH3vzY6P3yoQV/AAAAanRSTlMAAAAAAAAAAAAAAAAAAAADK2ym1fP01qcDN5Pf/OCUOBmG6oobMb7+wTVA1EMy/v79Gvz9+/v4/vwC/vz96fz+Of39mP3+/f7e/fxyrP7+/f78/v2l/Wv+/XEqAgKJwNg2Qka/l6zU89WtRjs8oAAAAAFiS0dEZ1vT6bMAAAAJcEhZcwAAnXsAAJ17ATyfd8QAAAAHdElNRQfkBxEMGxXWdcnLAAABvElEQVQ4y2NggAJGfgFBIWGRrCxRMXFBAQlGBlTAyC8pJS2TBQUysnLy/MhKmBgVFJWyUICSsgojM0yehVVVTT0LHWhosrFD5DkYtbSzsAAxHUawNZyMusjy2Tl6+ga5ObkgFbqMXCD3GaohpPOyjIxNTM3MLfJBKtQMgUYwWioiyVtZ2xSAQGFRDoivbMnIwChvi2S+nX0BsgJbB0YGSymEfK6jUwGKgixnSwYBaYSCYhdXkKybe0lpWTZYxEOAQVAGSUE5SN7TKzs7Fxam3gxCWegKKrKRhHwYhDEUlCArEGYQgbswO7uyCqSgOgdhRZYIA1xtTW1dfQNIQWNTXa2vH0wYriC3uaW1rR2koKOttdM/IA+mAGZFdkkBEggMgluhjVVBMMyh2gwhWBWEFsO9GQYNqNyu7pKeXpBkX3VJeATUBJlIhigPfN70iGKIRooszIByjkGJbgwFoOhmtIzFrSDWEpSkVOJwKYhTYQRnCk0x7AriExi5QcmahzFRDJuC+CRGaO5iYdRNVkdXoK6hycuHlPVibVEVoGQ9cOaVT5GWgSmQkXZ24MfM31GRqWnpBQXpGZneUQhpAIofTG99su62AAAAJXRFWHRkYXRlOmNyZWF0ZQAyMDIwLTA3LTE3VDEyOjI3OjIxKzAwOjAwn0wkwwAAACV0RVh0ZGF0ZTptb2RpZnkAMjAyMC0wNy0xN1QxMjoyNzoyMSswMDowMO4RnH8AAAAgdEVYdHNvZnR3YXJlAGh0dHBzOi8vaW1hZ2VtYWdpY2sub3JnvM8dnQAAABh0RVh0VGh1bWI6OkRvY3VtZW50OjpQYWdlcwAxp/+7LwAAABh0RVh0VGh1bWI6OkltYWdlOjpIZWlnaHQANTEyj41TgQAAABd0RVh0VGh1bWI6OkltYWdlOjpXaWR0aAA1MTIcfAPcAAAAGXRFWHRUaHVtYjo6TWltZXR5cGUAaW1hZ2UvcG5nP7JWTgAAABd0RVh0VGh1bWI6Ok1UaW1lADE1OTQ5ODg4NDEfMepSAAAAE3RFWHRUaHVtYjo6U2l6ZQAxNjAyNEJCbkDnoQAAAEl0RVh0VGh1bWI6OlVSSQBmaWxlOi8vLi91cGxvYWRzLzU2L0JlaUgyNlMvMjQyOS9mYWNlYm9va19sb2dvX2ljb25fMTQ3MjkxLnBuZ18J7EEAAAAASUVORK5CYII="
                    # ── Credit row (QHBoxLayout for pixel-perfect icon alignment) ──
                    credit_row = QWidget(); credit_row.setStyleSheet("background: transparent;")
                    credit_hl  = QHBoxLayout(credit_row)
                    credit_hl.setContentsMargins(0, 0, 0, 0); credit_hl.setSpacing(4)
                    credit_hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

                    def _make_icon_link(b64, url, label_text, icon_top_offset=0, icon_left_offset=0):
                        """Return a QWidget containing [icon] [text] as a clickable link."""
                        w = QWidget(); w.setStyleSheet("background: transparent;")
                        h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(3)
                        h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

                        ico_lbl = QLabel(); ico_lbl.setStyleSheet("background: transparent;")
                        px = QPixmap()
                        px.loadFromData(__import__("base64").b64decode(b64))
                        ico_lbl.setPixmap(px.scaled(13, 13,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation))
                        ico_lbl.setFixedSize(13, 13)
                        # icon_top_offset:  positive = DOWN,  negative = UP
                        # icon_left_offset: positive = RIGHT, negative = LEFT
                        ico_lbl.setContentsMargins(icon_left_offset, icon_top_offset, 0, 0)

                        txt_lbl = QLabel(f'<a href="{url}" style="color:#9d5cff; text-decoration:none;">{label_text}</a>')
                        txt_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
                        txt_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                        txt_lbl.setTextFormat(Qt.TextFormat.RichText)
                        txt_lbl.setOpenExternalLinks(True)
                        txt_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

                        h.addWidget(ico_lbl)
                        h.addWidget(txt_lbl)
                        return w

                    gh_w  = _make_icon_link(_GH_ICON_B64,  "https://github.com/muntasir018",         "GitHub",   icon_top_offset=-3, icon_left_offset=2)
                    fb_w  = _make_icon_link(_FB_ICON_B64,  "https://www.facebook.com/muntasir017",   "Facebook", icon_top_offset=0,  icon_left_offset=0)

                    sep = QLabel("·"); sep.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    sep.setFont(QFont("Segoe UI", 8))

                    credit_hl.addWidget(gh_w)
                    credit_hl.addWidget(sep)
                    credit_hl.addWidget(fb_w)
                    fl.addWidget(credit_row)

                    pl.addWidget(footer)
                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["settings_cfg"] = panel
                    panel.setVisible(False)

                def _build_diag_log_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(12)

                    # ── Top action bar ────────────────────────────────────────
                    top_row = QWidget(); top_row.setStyleSheet(f"background: {_BG};")
                    trl = QHBoxLayout(top_row)
                    trl.setContentsMargins(0, 0, 0, 0); trl.setSpacing(8)

                    back_btn = QPushButton("← Settings")
                    back_btn.setFixedHeight(34)
                    back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    back_btn.setFont(QFont("Segoe UI", 9))
                    back_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; color: {_MUTE};
                            border: none; padding: 0 8px;
                        }}
                        QPushButton:hover {{ color: {_FG}; }}""")
                    back_btn.clicked.connect(lambda: self._switch("settings_cfg"))
                    trl.addWidget(back_btn)

                    sep_lbl = QLabel("|")
                    sep_lbl.setStyleSheet(f"color: {_BORD}; background: transparent;")
                    trl.addWidget(sep_lbl)

                    self._diag_refresh_btn = QPushButton("↺  Refresh")
                    self._diag_refresh_btn.setFixedHeight(34)
                    self._diag_refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._diag_refresh_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._diag_refresh_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: {_ACC}; border-color: {_ACC}; color: white; }}
                        QPushButton:pressed {{ background: #5b21b6; }}""")
                    self._diag_refresh_btn.clicked.connect(self._refresh_diag_log)

                    self._diagrefresh_glow = QGraphicsDropShadowEffect()
                    self._diagrefresh_glow.setBlurRadius(0)
                    self._diagrefresh_glow.setColor(QColor(_ACC))
                    self._diagrefresh_glow.setOffset(0, 0)
                    self._diag_refresh_btn.setGraphicsEffect(self._diagrefresh_glow)

                    def _diagrefresh_enter(ev):
                        self._diagrefresh_glow.setBlurRadius(18)
                        QPushButton.enterEvent(self._diag_refresh_btn, ev)
                    def _diagrefresh_leave(ev):
                        self._diagrefresh_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._diag_refresh_btn, ev)
                    self._diag_refresh_btn.enterEvent = _diagrefresh_enter
                    self._diag_refresh_btn.leaveEvent = _diagrefresh_leave

                    trl.addWidget(self._diag_refresh_btn)

                    self._diag_open_btn = QPushButton("📂  Open File")
                    self._diag_open_btn.setFixedHeight(34)
                    self._diag_open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._diag_open_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._diag_open_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: {_TEAL}; border-color: {_TEAL}; color: white; }}
                        QPushButton:pressed {{ background: #0e7490; }}""")
                    self._diag_open_btn.clicked.connect(self._open_diag_file)

                    self._diagopen_glow = QGraphicsDropShadowEffect()
                    self._diagopen_glow.setBlurRadius(0)
                    self._diagopen_glow.setColor(QColor(_TEAL))
                    self._diagopen_glow.setOffset(0, 0)
                    self._diag_open_btn.setGraphicsEffect(self._diagopen_glow)

                    def _diagopen_enter(ev):
                        self._diagopen_glow.setBlurRadius(18)
                        QPushButton.enterEvent(self._diag_open_btn, ev)
                    def _diagopen_leave(ev):
                        self._diagopen_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._diag_open_btn, ev)
                    self._diag_open_btn.enterEvent = _diagopen_enter
                    self._diag_open_btn.leaveEvent = _diagopen_leave

                    trl.addWidget(self._diag_open_btn)

                    self._diag_copy_btn = QPushButton("⎘  Copy All")
                    self._diag_copy_btn.setFixedHeight(34)
                    self._diag_copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._diag_copy_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._diag_copy_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: #334155; border-color: #475569; color: white; }}
                        QPushButton:pressed {{ background: #1e293b; }}""")
                    self._diag_copy_btn.clicked.connect(self._copy_diag_log)

                    self._diagcopy_glow = QGraphicsDropShadowEffect()
                    self._diagcopy_glow.setBlurRadius(0)
                    self._diagcopy_glow.setColor(QColor("#475569"))
                    self._diagcopy_glow.setOffset(0, 0)
                    self._diag_copy_btn.setGraphicsEffect(self._diagcopy_glow)

                    def _diagcopy_enter(ev):
                        self._diagcopy_glow.setBlurRadius(16)
                        QPushButton.enterEvent(self._diag_copy_btn, ev)
                    def _diagcopy_leave(ev):
                        self._diagcopy_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._diag_copy_btn, ev)
                    self._diag_copy_btn.enterEvent = _diagcopy_enter
                    self._diag_copy_btn.leaveEvent = _diagcopy_leave

                    trl.addWidget(self._diag_copy_btn)

                    trl.addStretch()

                    self._diag_line_count = QLabel("")
                    self._diag_line_count.setFont(QFont("Segoe UI", 8))
                    self._diag_line_count.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    trl.addWidget(self._diag_line_count)

                    pl.addWidget(top_row)

                    # ── Log viewer card ───────────────────────────────────────
                    log_card = _Card(panel, bg="#07050f", border=_BORD, radius=12)
                    lcl = QVBoxLayout(log_card)
                    lcl.setContentsMargins(0, 0, 0, 0); lcl.setSpacing(0)

                    from PyQt6.QtWidgets import QPlainTextEdit
                    self._diag_viewer = QPlainTextEdit()
                    self._diag_viewer.setReadOnly(True)
                    self._diag_viewer.setFont(QFont("Consolas", 8))
                    self._diag_viewer.setStyleSheet(f"""
                        QPlainTextEdit {{
                            background: #07050f; color: #c9d1d9;
                            border: none; border-radius: 12px;
                            padding: 12px; selection-background-color: {_ACC};
                        }}
                        QScrollBar:vertical {{
                            background: transparent; width: 6px; border-radius: 3px; margin: 4px 0;
                        }}
                        QScrollBar::handle:vertical {{
                            background: {_BORD}; border-radius: 3px; min-height: 30px;
                        }}
                        QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
                        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
                    """)
                    self._diag_viewer.setMinimumHeight(385)
                    lcl.addWidget(self._diag_viewer)
                    pl.addWidget(log_card)

                    # ── Footer hint ───────────────────────────────────────────
                    hint = QLabel(f"📁  File: %APPDATA%\\DeskWarden\\diagnostic_log.txt  ·  Auto-cleaned every 7 days  ·  Max 3000 lines")
                    hint.setFont(QFont("Segoe UI", 7))
                    hint.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    pl.addWidget(hint)

                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["diag_log"] = panel
                    panel.setVisible(False)

                def _refresh_diag_log(self):
                    try:
                        if not os.path.exists(_DIAG_PATH):
                            self._diag_viewer.setPlainText("No diagnostic log found yet.\nRun DeskWarden for a while and come back.")
                            self._diag_line_count.setText("0 lines")
                            return
                        with open(_DIAG_PATH, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                        # Show last 500 lines so it stays fast
                        MAX_SHOW = 500
                        if len(lines) > MAX_SHOW:
                            shown = lines[-MAX_SHOW:]
                            header = f"[ Showing last {MAX_SHOW} of {len(lines)} lines ]\n\n"
                        else:
                            shown = lines
                            header = ""
                        self._diag_viewer.setPlainText(header + "".join(shown))
                        # Scroll to bottom
                        sb = self._diag_viewer.verticalScrollBar()
                        sb.setValue(sb.maximum())
                        self._diag_line_count.setText(f"{len(lines)} lines")
                    except Exception as e:
                        self._diag_viewer.setPlainText(f"Could not read diagnostic log: {e}")
                        self._diag_line_count.setText("error")

                def _open_diag_file(self):
                    try:
                        import subprocess
                        if os.path.exists(_DIAG_PATH):
                            subprocess.Popen(["notepad.exe", _DIAG_PATH])
                        else:
                            self._diag_viewer.setPlainText("Diagnostic log file does not exist yet.")
                    except Exception as e:
                        self._diag_viewer.setPlainText(f"Could not open file: {e}")

                def _pulse_copy_glow(self, btn, glow_fx, normal_color):
                   
                    try:
                        glow_fx.setColor(QColor(_GREEN))
                        pulse_up = QPropertyAnimation(glow_fx, b"blurRadius", self)
                        pulse_up.setDuration(120)
                        pulse_up.setStartValue(glow_fx.blurRadius())
                        pulse_up.setEndValue(26)
                        pulse_up.setEasingCurve(QEasingCurve.Type.OutQuad)

                        def _settle():
                            pulse_down = QPropertyAnimation(glow_fx, b"blurRadius", self)
                            pulse_down.setDuration(280)
                            pulse_down.setStartValue(26)
                            pulse_down.setEndValue(16 if btn.underMouse() else 0)
                            pulse_down.setEasingCurve(QEasingCurve.Type.InQuad)
                            pulse_down.finished.connect(
                                lambda: glow_fx.setColor(QColor(normal_color)))
                            self._copy_pulse_down = pulse_down
                            pulse_down.start()

                        pulse_up.finished.connect(_settle)
                        self._copy_pulse_up = pulse_up
                        pulse_up.start()
                    except Exception:
                        pass

                def _copy_diag_log(self):
                    try:
                        from PyQt6.QtWidgets import QApplication as _QApp
                        text = self._diag_viewer.toPlainText()
                        if text:
                            _QApp.clipboard().setText(text)
                            self._diag_copy_btn.setText("✓  Copied!")
                            self._pulse_copy_glow(self._diag_copy_btn, self._diagcopy_glow, "#475569")
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(2000, lambda: self._diag_copy_btn.setText("⎘  Copy All"))
                    except Exception:
                        pass

                def _build_crash_log_panel(self):
                    panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
                    pl = QVBoxLayout(panel)
                    pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(12)

                    # ── Top action bar ────────────────────────────────────────
                    top_row = QWidget(); top_row.setStyleSheet(f"background: {_BG};")
                    trl = QHBoxLayout(top_row)
                    trl.setContentsMargins(0, 0, 0, 0); trl.setSpacing(8)

                    back_btn = QPushButton("← Settings")
                    back_btn.setFixedHeight(34)
                    back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    back_btn.setFont(QFont("Segoe UI", 9))
                    back_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: transparent; color: {_MUTE};
                            border: none; padding: 0 8px;
                        }}
                        QPushButton:hover {{ color: {_FG}; }}""")
                    back_btn.clicked.connect(lambda: self._switch("settings_cfg"))
                    trl.addWidget(back_btn)

                    sep_lbl = QLabel("|")
                    sep_lbl.setStyleSheet(f"color: {_BORD}; background: transparent;")
                    trl.addWidget(sep_lbl)

                    self._crash_refresh_btn = QPushButton("↺  Refresh")
                    self._crash_refresh_btn.setFixedHeight(34)
                    self._crash_refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._crash_refresh_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._crash_refresh_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: {_ACC}; border-color: {_ACC}; color: white; }}
                        QPushButton:pressed {{ background: #5b21b6; }}""")
                    self._crash_refresh_btn.clicked.connect(self._refresh_crash_log)

                    self._crashrefresh_glow = QGraphicsDropShadowEffect()
                    self._crashrefresh_glow.setBlurRadius(0)
                    self._crashrefresh_glow.setColor(QColor(_ACC))
                    self._crashrefresh_glow.setOffset(0, 0)
                    self._crash_refresh_btn.setGraphicsEffect(self._crashrefresh_glow)

                    def _crashrefresh_enter(ev):
                        self._crashrefresh_glow.setBlurRadius(18)
                        QPushButton.enterEvent(self._crash_refresh_btn, ev)
                    def _crashrefresh_leave(ev):
                        self._crashrefresh_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._crash_refresh_btn, ev)
                    self._crash_refresh_btn.enterEvent = _crashrefresh_enter
                    self._crash_refresh_btn.leaveEvent = _crashrefresh_leave

                    trl.addWidget(self._crash_refresh_btn)

                    self._crash_open_btn = QPushButton("📂  Open File")
                    self._crash_open_btn.setFixedHeight(34)
                    self._crash_open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._crash_open_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._crash_open_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: {_TEAL}; border-color: {_TEAL}; color: white; }}
                        QPushButton:pressed {{ background: #0e7490; }}""")
                    self._crash_open_btn.clicked.connect(self._open_crash_file)

                    self._crashopen_glow = QGraphicsDropShadowEffect()
                    self._crashopen_glow.setBlurRadius(0)
                    self._crashopen_glow.setColor(QColor(_TEAL))
                    self._crashopen_glow.setOffset(0, 0)
                    self._crash_open_btn.setGraphicsEffect(self._crashopen_glow)

                    def _crashopen_enter(ev):
                        self._crashopen_glow.setBlurRadius(18)
                        QPushButton.enterEvent(self._crash_open_btn, ev)
                    def _crashopen_leave(ev):
                        self._crashopen_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._crash_open_btn, ev)
                    self._crash_open_btn.enterEvent = _crashopen_enter
                    self._crash_open_btn.leaveEvent = _crashopen_leave

                    trl.addWidget(self._crash_open_btn)

                    self._crash_copy_btn = QPushButton("⎘  Copy All")
                    self._crash_copy_btn.setFixedHeight(34)
                    self._crash_copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._crash_copy_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    self._crash_copy_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {_CARD2}; color: {_FG};
                            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
                        }}
                        QPushButton:hover {{ background: #334155; border-color: #475569; color: white; }}
                        QPushButton:pressed {{ background: #1e293b; }}""")
                    self._crash_copy_btn.clicked.connect(self._copy_crash_log)

                    self._crashcopy_glow = QGraphicsDropShadowEffect()
                    self._crashcopy_glow.setBlurRadius(0)
                    self._crashcopy_glow.setColor(QColor("#475569"))
                    self._crashcopy_glow.setOffset(0, 0)
                    self._crash_copy_btn.setGraphicsEffect(self._crashcopy_glow)

                    def _crashcopy_enter(ev):
                        self._crashcopy_glow.setBlurRadius(16)
                        QPushButton.enterEvent(self._crash_copy_btn, ev)
                    def _crashcopy_leave(ev):
                        self._crashcopy_glow.setBlurRadius(0)
                        QPushButton.leaveEvent(self._crash_copy_btn, ev)
                    self._crash_copy_btn.enterEvent = _crashcopy_enter
                    self._crash_copy_btn.leaveEvent = _crashcopy_leave

                    trl.addWidget(self._crash_copy_btn)

                    trl.addStretch()

                    self._crash_line_count = QLabel("")
                    self._crash_line_count.setFont(QFont("Segoe UI", 8))
                    self._crash_line_count.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    trl.addWidget(self._crash_line_count)

                    pl.addWidget(top_row)

                    # ── Log viewer card ───────────────────────────────────────
                    log_card = _Card(panel, bg="#07050f", border=_BORD, radius=12)
                    lcl = QVBoxLayout(log_card)
                    lcl.setContentsMargins(0, 0, 0, 0); lcl.setSpacing(0)

                    from PyQt6.QtWidgets import QPlainTextEdit
                    self._crash_viewer = QPlainTextEdit()
                    self._crash_viewer.setReadOnly(True)
                    self._crash_viewer.setFont(QFont("Consolas", 8))
                    self._crash_viewer.setStyleSheet(f"""
                        QPlainTextEdit {{
                            background: #07050f; color: #c9d1d9;
                            border: none; border-radius: 12px;
                            padding: 12px; selection-background-color: {_ACC};
                        }}
                        QScrollBar:vertical {{
                            background: transparent; width: 6px; border-radius: 3px; margin: 4px 0;
                        }}
                        QScrollBar::handle:vertical {{
                            background: {_BORD}; border-radius: 3px; min-height: 30px;
                        }}
                        QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
                        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
                    """)
                    self._crash_viewer.setMinimumHeight(385)
                    lcl.addWidget(self._crash_viewer)
                    pl.addWidget(log_card)

                    # ── Footer hint ───────────────────────────────────────────
                    hint = QLabel(f"📁  File: %APPDATA%\\DeskWarden\\crash_log.txt  ·  Error & exception reports")
                    hint.setFont(QFont("Segoe UI", 7))
                    hint.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    pl.addWidget(hint)

                    self._scroll_lay.addWidget(panel)
                    self._section_widgets["crash_log"] = panel
                    panel.setVisible(False)

                def _refresh_crash_log(self):
                    try:
                        if not os.path.exists(_CRASH_PATH):
                            self._crash_viewer.setPlainText("No crash log found — great news, no crashes recorded!")
                            self._crash_line_count.setText("0 lines")
                            return
                        with open(_CRASH_PATH, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                        MAX_SHOW = 500
                        if len(lines) > MAX_SHOW:
                            shown = lines[-MAX_SHOW:]
                            header = f"[ Showing last {MAX_SHOW} of {len(lines)} lines ]\n\n"
                        else:
                            shown = lines
                            header = ""
                        self._crash_viewer.setPlainText(header + "".join(shown))
                        sb = self._crash_viewer.verticalScrollBar()
                        sb.setValue(sb.maximum())
                        self._crash_line_count.setText(f"{len(lines)} lines")
                    except Exception as e:
                        self._crash_viewer.setPlainText(f"Could not read crash log: {e}")
                        self._crash_line_count.setText("error")

                def _open_crash_file(self):
                    try:
                        import subprocess
                        if os.path.exists(_CRASH_PATH):
                            subprocess.Popen(["notepad.exe", _CRASH_PATH])
                        else:
                            self._crash_viewer.setPlainText("Crash log file does not exist yet.")
                    except Exception as e:
                        self._crash_viewer.setPlainText(f"Could not open file: {e}")

                def _copy_crash_log(self):
                    try:
                        from PyQt6.QtWidgets import QApplication as _QApp
                        text = self._crash_viewer.toPlainText()
                        if text:
                            _QApp.clipboard().setText(text)
                            self._crash_copy_btn.setText("✓  Copied!")
                            self._pulse_copy_glow(self._crash_copy_btn, self._crashcopy_glow, "#475569")
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(2000, lambda: self._crash_copy_btn.setText("⎘  Copy All"))
                    except Exception:
                        pass

                def _toggle_auto(self):
                    self._cfg["autostart"] = self._auto_cb.isChecked()
                    save_config(self._cfg)
                    set_autostart(self._cfg["autostart"])

                def _toggle_auto_update(self):
                    self._cfg["auto_update"] = self._auto_update_cb.isChecked()
                    save_config(self._cfg)

                def _check_update(self):
                    self._update_btn.setEnabled(False)
                    self._update_status.setStyleSheet(
                        f"color: {_MUTE}; background: transparent;")
                    self._update_status.setText("⏳ Checking for updates…")

                    def _on_result(res):
                        
                        from PyQt6.QtCore import QMetaObject, Qt as _Qt
                        
                        self._update_result_pending = res
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(0, self._apply_update_result)

                    check_for_update_async(callback=_on_result)

                def _apply_update_result(self):
                    res = getattr(self, "_update_result_pending", None)
                    self._update_btn.setEnabled(True)
                    if res is None:
                        return
                    
                    if not res.get("error") and hasattr(self, "_last_checked_lbl"):
                        self._cfg = load_config()
                        last_checked = self._cfg.get("last_update_check", "")
                        txt = f"Last checked: {last_checked}" if last_checked else "Last checked: Never"
                        self._last_checked_lbl.setText(txt)
                    if res.get("error"):
                        self._update_status.setStyleSheet(
                            f"color: {_RED}; background: transparent;")
                        self._update_status.setText(
                            f"✗ Could not check: {res['error']}")
                    elif res.get("update_available"):
                        latest = res.get("latest", "?")
                        url    = res.get("url", "")
                        self._update_status.setStyleSheet(
                            f"color: {_GREEN}; background: transparent;")
                        self._update_status.setText(
                            f"✅ New version available: {latest}  —  "
                            f'<a href="{url}" style="color:#9d5cff;">Download</a>')
                        self._update_status.setTextFormat(
                            Qt.TextFormat.RichText)
                        self._update_status.setOpenExternalLinks(True)
                    else:
                        self._update_status.setStyleSheet(
                            f"color: {_GREEN}; background: transparent;")
                        latest = res.get("latest") or CURRENT_VERSION
                        self._update_status.setText(
                            f"✓ You are up to date  ({latest})")

                def _export_settings(self):
                    import datetime as _dt
                    default_name = f"deskwarden_backup_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    path, _f = QFileDialog.getSaveFileName(
                        self, "Export DeskWarden Settings", default_name,
                        "DeskWarden Backup (*.json)")
                    if not path:
                        return
                    if not path.lower().endswith(".json"):
                        path += ".json"
                    try:
                        data = {
                            "app": "DeskWarden",
                            "export_version": 1,
                            "exported_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "config": load_config(),
                            "security_log": load_security_log(),
                        }
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                        self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                        self._backup_status.setText(f"✓ Exported to {path}")
                    except Exception as e:
                        self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
                        self._backup_status.setText(f"✗ Export failed: {e}")

                def _import_settings(self):
                    path, _f = QFileDialog.getOpenFileName(
                        self, "Import DeskWarden Settings", "",
                        "DeskWarden Backup (*.json)")
                    if not path:
                        return
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        cfg = data.get("config")
                        if not isinstance(cfg, dict) or "locked_apps" not in cfg:
                            raise ValueError("Not a valid DeskWarden backup file.")

                        
                        if cfg.get("password_hash"):
                            box = QMessageBox(self)
                            
                            box.setWindowFlags(
                                box.windowFlags() | Qt.WindowType.FramelessWindowHint)
                            box.setWindowTitle("Password-Protected Backup")
                            box.setIcon(QMessageBox.Icon.Warning)
                            box.setText(
                                f"<b style='font-size:11pt; color:{_RED};'>Password-Protected Backup</b>"
                                "<br><br>This backup file has a password set."
                            )
                            box.setInformativeText(
                                "Importing it will replace your current DeskWarden "
                                "password with the one saved in this backup.\n\n"
                                "Make sure you know that password before continuing — "
                                "otherwise you could lock yourself out of your apps."
                            )
                            yes_btn = box.addButton("Import Anyway", QMessageBox.ButtonRole.AcceptRole)
                            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                            box.setDefaultButton(yes_btn)
                            box.setStyleSheet(f"""
                                QMessageBox {{
                                    background: {_CARD}; border: 1px solid {_BORD};
                                    border-radius: 12px;
                                }}
                                QLabel {{ color: {_FG}; background: transparent; }}
                                QPushButton {{
                                    background: {_CARD2}; color: {_FG};
                                    border: 1px solid {_BORD}; border-radius: 8px;
                                    padding: 6px 14px; min-width: 90px;
                                }}
                                QPushButton:hover {{ background: #1f1c34; border-color: {_ACC3}; }}
                            """)
                            
                            for icon_name in ("qt_msgboxex_icon_label", "qt_msgbox_icon_label"):
                                icon_lbl = box.findChild(QLabel, icon_name)
                                if icon_lbl is not None:
                                    icon_lbl.setStyleSheet(
                                        f"background: {_CARD};"
                                        "border-top-left-radius: 12px;"
                                        "border-bottom-left-radius: 12px;"
                                    )
                            box.adjustSize()
                            parent_geo = self.geometry()
                            parent_center = self.mapToGlobal(parent_geo.center() - parent_geo.topLeft())
                            box.move(
                                parent_center.x() - box.width() // 2,
                                parent_center.y() - box.height() // 2,
                            )
                            box.exec()
                            if box.clickedButton() is not yes_btn:
                                self._backup_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                                self._backup_status.setText("Import cancelled.")
                                return

                        save_config(cfg)
                        if "security_log" in data and isinstance(data["security_log"], list):
                            _save_security_log(data["security_log"])

                        self._cfg = load_config()

                        # Refresh Locked Apps list
                        self._refresh_apps()

                        # Refresh Password badge / form state
                        has_pw = bool(self._cfg.get("password_hash"))
                        self._pw_badge.setText("✓ Set" if has_pw else "✗ Not set")
                        self._pw_badge.setStyleSheet(f"""
                            color: white; background: {_GREEN if has_pw else _RED};
                            border-radius: 10px; padding: 2px 10px;""")
                        self._reset_pw_form()

                        # Refresh autostart checkbox + registry entry
                        self._auto_cb.setChecked(self._cfg.get("autostart", False))
                        set_autostart(self._cfg.get("autostart", False))

                        # Refresh Security Log list
                        self._refresh_log()

                        self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                        self._backup_status.setText("✓ Settings imported successfully.")
                    except Exception as e:
                        self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
                        self._backup_status.setText(f"✗ Import failed: {e}")

            _startup_cfg = load_config()
            if not _startup_cfg.get("password_hash"):
                _win_holder = {}
                def _after_first_setup():
                    _win_holder["win"] = _ControlPanelWin()
                    _win_holder["win"].show()
                _setup_dlg = _FirstRunSetupDialog(_after_first_setup)
                _setup_dlg.show()
            else:
                win = _ControlPanelWin()
                win.show()
            _sys.exit(_app.exec())

        except Exception as e:
            dlog("ERROR", f"--control-panel mode crash: {type(e).__name__}: {e}")
            log_crash("--control-panel mode", e)
            raise

    if "--gui" in sys.argv:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass
        try:
            main()
        except Exception as e:
            dlog("ERROR", f"main() --gui crash: {type(e).__name__}: {e}")
            log_crash("main() --gui", e)
            raise
        sys.exit(0)

    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass
    try:
        main()
    except Exception as e:
        dlog("ERROR", f"main() top-level crash: {type(e).__name__}: {e}")
        log_crash("main()", e)
        raise