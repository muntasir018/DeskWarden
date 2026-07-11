"""
DeskWarden - system/monitor.py

"""

import os
import time
import queue
import threading

import psutil

from ..core.logging_utils import dlog, log_crash
from ..core.config import load_config
from ..core.security import UNLOCK_GRACE_SECONDS, MIN_GRACE_LIVENESS_DELAY
from ..core.process_utils import _get_process_tree_pids


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
