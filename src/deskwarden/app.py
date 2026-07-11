"""
DeskWarden - app.py

"""

import os
import sys
import time
import threading

from .core.logging_utils import dlog, log_crash
from .core.config import load_config
from .core.updater import CURRENT_VERSION, check_for_update_auto_async
from .core.security import UNLOCK_GRACE_SECONDS
from .core.process_utils import (
    suspend_process, resume_process, hide_process_windows,
    restore_process_windows, _get_process_tree_pids,
)
from .core.paths import APPDATA_DIR

from .ui.icon_utils import _resolve_icon_exe_path
from .ui.lock_screen import LockScreen
from .ui.block_notice import BlockNotice
from .ui.auth_dialogs import (
    show_control_panel_auth, show_quit_auth, release_control_panel_lock,
)
from .ui.ui_thread import (
    _run_on_ui_thread, _run_on_ui_thread_sync, _ui_thread_loop, _ui_ready_event,
)

from .system.monitor import AppMonitor
from .system.tray import NativeTray
from .system.control_panel_launcher import ControlPanelWindow
from .system.single_instance import check_single_instance
from .system.ipc import start_ipc_pipe_server


def main():
    import datetime as _main_dt

    # ── Single-instance check ─────────────────────────────────────────────────
    
    if not check_single_instance():
        sys.exit(0)

    # ── Normal startup ────────────────────────────────────────────────────────
    dlog("INFO", f"DeskWarden {CURRENT_VERSION} starting")
    dlog("INFO", f"Python: {sys.version.split()[0]} | PID: {os.getpid()}")
    dlog("INFO", f"Script: {os.path.abspath(sys.argv[0])}")
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
        
        release_control_panel_lock()
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
            marker = os.path.join(APPDATA_DIR, "clean_exit.marker")
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

    # ── Startup update check ──────────────────────────────────────────────────
    
    def _on_startup_update_result(res):
        try:
            if res.get("update_available"):
                tray.set_badge(True)
                tray.show_update_toast(res.get("latest", "?"))
        except Exception as e:
            log_crash("_on_startup_update_result", e)

    try:
        _cfg_upd = load_config()
        if _cfg_upd.get("auto_update", True):
            check_for_update_auto_async(callback=_on_startup_update_result)
    except Exception as e:
        log_crash("startup update check", e)

    # ── IPC Named Pipe Server ─────────────────────────────────────────────────
    
    start_ipc_pipe_server(on_open_control_panel=open_control_panel)

    try:
        while True:
            time.sleep(5)
    except (SystemExit, KeyboardInterrupt):
        dlog("INFO", "DeskWarden shutting down (SystemExit/KeyboardInterrupt)")
    except Exception as e:
        dlog("ERROR", f"main sleep loop exception: {type(e).__name__}: {e}")
        log_crash("main sleep loop", e)

