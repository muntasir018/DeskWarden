"""
DeskWarden - system/control_panel_launcher.py

"""

import subprocess
import threading

from ..core.paths import build_relaunch_args
from ..core.logging_utils import dlog, log_crash
from .monitor import AppMonitor


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

        args = build_relaunch_args("--control-panel")

        def _run():
            try:
                dlog("INFO", f"ControlPanel.open: spawning subprocess: {' '.join(args)}")
                self._proc = subprocess.Popen(
                    args,
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
