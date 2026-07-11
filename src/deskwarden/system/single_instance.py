"""
DeskWarden - system/single_instance.py

"""

import os

import psutil

from ..core.paths import APPDATA_DIR
from ..core.logging_utils import dlog
from .ipc import notify_existing_instance

PID_FILE = os.path.join(APPDATA_DIR, "instance.pid")


def _read_existing_pid():
    try:
        with open(PID_FILE, "r") as _pf:
            content = _pf.read().strip()
        pid = int(content)
        dlog("INFO", f"_read_existing_pid: PID_FILE={PID_FILE} content='{content}' -> {pid}")
        return pid
    except FileNotFoundError:
        dlog("INFO", f"_read_existing_pid: PID_FILE not found at {PID_FILE}")
        return None
    except Exception as e:
        dlog("WARNING", f"_read_existing_pid: failed reading {PID_FILE}: {type(e).__name__}: {e}")
        return None


def _write_my_pid(my_pid: int):
    try:
        with open(PID_FILE, "w") as _pf:
            _pf.write(str(my_pid))
        dlog("INFO", f"_write_my_pid: wrote PID {my_pid} to {PID_FILE}")
    except Exception as e:
        dlog("ERROR", f"_write_my_pid: FAILED writing PID {my_pid} to {PID_FILE}: {type(e).__name__}: {e}")


def _pid_is_deskwarden(pid):
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            dlog("INFO", f"_pid_is_deskwarden: PID {pid} not running")
            return False
        try:
            cmdline = " ".join(proc.cmdline()).lower()
            if "deskwarden" in cmdline:
                return True
            exe = (proc.exe() or "").lower()
            if "python" in exe or "deskwarden" in exe:
                return True
            dlog("INFO", f"_pid_is_deskwarden: PID {pid} cmdline='{cmdline}' exe='{exe}' — no match")
            return False
        except psutil.AccessDenied:
            dlog("INFO", f"_pid_is_deskwarden: PID {pid} AccessDenied — assuming it IS DeskWarden")
            return True
    except Exception as e:
        dlog("WARNING", f"_pid_is_deskwarden: PID {pid} check failed: {type(e).__name__}: {e}")
        return False


def check_single_instance() -> bool:

    my_pid = os.getpid()
    existing_pid = _read_existing_pid()

    if existing_pid and existing_pid != my_pid and _pid_is_deskwarden(existing_pid):
        dlog("INFO", f"main(): instance already running (PID {existing_pid}) — sending OPEN_CONTROL_PANEL")
        notify_existing_instance(log_prefix="main()")
        return False

    _write_my_pid(my_pid)
    dlog("INFO", f"main(): I am the main instance (PID {my_pid})")
    return True
