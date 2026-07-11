"""
DeskWarden.py - Thin Entrypoint

"""

import sys


try:
    import faulthandler as _faulthandler
    import os as _os
    _appdata_dir = _os.path.join(_os.environ.get("APPDATA", "."), "DeskWarden")
    _os.makedirs(_appdata_dir, exist_ok=True)
    _early_crash_log = _os.path.join(_appdata_dir, "crash_log.txt")
    _early_fault_file = open(_early_crash_log, "a", encoding="utf-8", buffering=1)
    _faulthandler.enable(file=_early_fault_file, all_threads=True)
except Exception:
    pass


try:
    from deskwarden.core.logging_utils import (
        dlog, log_crash, redirect_stdio_to_crash_log, start_log_cleanup_threads,
    )
    from deskwarden.system import single_instance, ipc
    from deskwarden.system.service import _SERVICE_AVAILABLE, DeskWardenWindowsService
    from deskwarden import app as deskwarden_app
except Exception:
    import os
    import traceback
    import datetime

    try:
        _appdata_dir = os.path.join(os.environ.get("APPDATA", "."), "DeskWarden")
        os.makedirs(_appdata_dir, exist_ok=True)
        _startup_log = os.path.join(_appdata_dir, "startup_crash.txt")
        with open(_startup_log, "a", encoding="utf-8") as _f:
            _f.write(
                f"\n{'=' * 60}\n"
                f"STARTUP IMPORT FAILURE: {datetime.datetime.now()}\n"
                f"{'=' * 60}\n"
            )
            traceback.print_exc(file=_f)
    except Exception:
        pass
    raise


if __name__ == "__main__":

    redirect_stdio_to_crash_log()
    start_log_cleanup_threads()

    # ── Windows Service কমান্ড ────────────────────────────────────────────────
    if len(sys.argv) >= 2 and sys.argv[1] in (
            "install", "remove", "start", "stop",
            "update", "debug", "--startup"):
        if not _SERVICE_AVAILABLE:
            print("ERROR: pywin32 is required for service mode.  "
                  "Run: pip install pywin32")
            sys.exit(1)
        import win32serviceutil
        win32serviceutil.HandleCommandLine(DeskWardenWindowsService)
        sys.exit(0)

    # ── Shortcut / Second-instance: --open-control-panel ─────────────────────
    if "--open-control-panel" in sys.argv:
        existing_pid = single_instance._read_existing_pid()
        if existing_pid and single_instance._pid_is_deskwarden(existing_pid):
            dlog("INFO", "--open-control-panel: existing instance found — sending OPEN_CONTROL_PANEL")
            ipc.notify_existing_instance(log_prefix="--open-control-panel")
            sys.exit(0)
        else:
            dlog("INFO", "--open-control-panel: no running instance — starting main()")
            sys.argv = [sys.argv[0]]

    # ── Control Panel UI  ───────────────────
    if "--control-panel" in sys.argv:
     
        from deskwarden.ui.control_panel_ui import run_control_panel_mode
        run_control_panel_mode()
        sys.exit(0)

    # ── GUI mode  ───────────────────────
    if "--gui" in sys.argv:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass
        try:
            deskwarden_app.main()
        except Exception as e:
            dlog("ERROR", f"main() --gui crash: {type(e).__name__}: {e}")
            log_crash("main() --gui", e)
            raise
        sys.exit(0)

# ── Default ──────────────────────────────
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass
    try:
        deskwarden_app.main()
    except Exception as e:
        dlog("ERROR", f"main() top-level crash: {type(e).__name__}: {e}")
        log_crash("main()", e)
        raise
