"""
DeskWarden - core/logging_utils.py

"""

import os
import sys
import platform
import threading
import traceback
import faulthandler
import datetime as _dt

from .paths import DIAGNOSTIC_LOG_PATH, CRASH_LOG_PATH, IS_FROZEN

# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

_DIAG_LOCK       = threading.Lock()
_DIAG_MAX_LINES  = 3000
_DIAG_MAX_DAYS   = 7
_CRASH_MAX_LINES = 500
_CRASH_MAX_DAYS  = 30
_DATE_FMT        = "%Y-%m-%d %H:%M:%S"


_crash_file_handle = None


# ═════════════════════════════════════════════════════════════════════════
# Environment banner
# ═════════════════════════════════════════════════════════════════════════

def _env_banner() -> str:
    try:
        mode = "FROZEN (exe)" if IS_FROZEN else "DEV (python script)"
        return (
            f"Mode    : {mode}\n"
            f"Python  : {sys.version.split()[0]}\n"
            f"OS      : {platform.platform()}\n"
            f"PID     : {os.getpid()}\n"
            f"Thread  : {threading.current_thread().name}\n"
        )
    except Exception:
        return ""


# ═════════════════════════════════════════════════════════════════════════
# Stdout/stderr redirect + native-crash (faulthandler) + excepthooks
# ═════════════════════════════════════════════════════════════════════════

def redirect_stdio_to_crash_log() -> None:
    
    global _crash_file_handle
    try:
        crash_file = open(CRASH_LOG_PATH, "a", encoding="utf-8", buffering=1)
        _crash_file_handle = crash_file
        crash_file.write(
            f"\n{'=' * 60}\n"
            f"STARTED: {_dt.datetime.now().strftime(_DATE_FMT)}\n"
            f"{_env_banner()}"
            f"{'=' * 60}\n"
        )
        sys.stderr = crash_file
        sys.stdout = crash_file

        faulthandler.enable(file=crash_file, all_threads=True)

        sys.excepthook = _global_excepthook
        threading.excepthook = _thread_excepthook
    except Exception:
        pass


def _write_crash_block(header: str, exc_type, exc_value, exc_tb) -> None:
    try:
        target = _crash_file_handle
        f = target if (target and not target.closed) else open(
            CRASH_LOG_PATH, "a", encoding="utf-8"
        )
        f.write(f"\n{'=' * 60}\n")
        f.write(f"{header}\n")
        f.write(f"TIME   : {_dt.datetime.now().strftime(_DATE_FMT)}\n")
        f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        f.flush()
        if f is not target:
            f.close()
    except Exception:
        pass


def _global_excepthook(exc_type, exc_value, exc_tb) -> None:
    """Catches anything that escapes all the way out of the main thread."""
    _write_crash_block("UNCAUGHT EXCEPTION (main thread)", exc_type, exc_value, exc_tb)
    dlog("ERROR", f"UNCAUGHT (main thread): {exc_type.__name__}: {exc_value}")
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _thread_excepthook(args) -> None:
   
    thread_name = getattr(args.thread, "name", "?")
    _write_crash_block(
        f"UNCAUGHT EXCEPTION (thread: {thread_name})",
        args.exc_type, args.exc_value, args.exc_traceback,
    )
    dlog("ERROR", f"UNCAUGHT (thread {thread_name}): {args.exc_type.__name__}: {args.exc_value}")


# ═════════════════════════════════════════════════════════════════════════
# Diagnostic log (dlog)
# ═════════════════════════════════════════════════════════════════════════

def dlog(level: str, msg: str) -> None:

    try:
        line = f"[{_dt.datetime.now().strftime(_DATE_FMT)}] [{level:<7}] {msg}\n"
        with _DIAG_LOCK:
            with open(DIAGNOSTIC_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:

        pass


# ═════════════════════════════════════════════════════════════════════════
# Crash log (explicit, caught exceptions — try/except sites call this)
# ═════════════════════════════════════════════════════════════════════════

def log_crash(context: str, exc: Exception) -> None:

    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"TIME   : {_dt.datetime.now().strftime(_DATE_FMT)}\n")
            f.write(f"WHERE  : {context}\n")
            f.write(f"ERROR  : {type(exc).__name__}: {exc}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass
    dlog("ERROR", f"CRASH [{context}]: {type(exc).__name__}: {exc}")


# ═════════════════════════════════════════════════════════════════════════
# log auto-cleanup
# ═════════════════════════════════════════════════════════════════════════

def _cleanup_by_age_and_size(path: str, max_days: int, max_lines: int) -> None:

    try:
        if not os.path.exists(path):
            return
        cutoff = _dt.datetime.now() - _dt.timedelta(days=max_days)
        kept = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                try:
                    ts_str = raw_line[1:20]  # "[YYYY-MM-DD HH:MM:SS]"
                    line_dt = _dt.datetime.strptime(ts_str, _DATE_FMT)
                    if line_dt >= cutoff:
                        kept.append(raw_line)
                except Exception:
          
                    kept.append(raw_line)

        if len(kept) > max_lines:
            kept = kept[-(max_lines // 2):]

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except Exception:
        pass


def diag_cleanup() -> None:
    
    _cleanup_by_age_and_size(DIAGNOSTIC_LOG_PATH, _DIAG_MAX_DAYS, _DIAG_MAX_LINES)


def crash_cleanup() -> None:
    
    _cleanup_by_age_and_size(CRASH_LOG_PATH, _CRASH_MAX_DAYS, _CRASH_MAX_LINES)


def start_log_cleanup_threads() -> None:

    threading.Thread(target=diag_cleanup, daemon=True, name="DiagCleanup").start()
    threading.Thread(target=crash_cleanup, daemon=True, name="CrashCleanup").start()
