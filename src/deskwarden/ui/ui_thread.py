"""
DeskWarden - ui/ui_thread.py

"""

import sys
import queue
import threading

from ..core.logging_utils import dlog, log_crash

# ═════════════════════════════════════════════════════════════════════════
# Shared state
# ═════════════════════════════════════════════════════════════════════════

_ui_queue: queue.Queue = queue.Queue()
_qapp = None
_ui_ready_event = threading.Event()


# ═════════════════════════════════════════════════════════════════════════
# UI thread loop
# ═════════════════════════════════════════════════════════════════════════

def _ui_thread_loop():
    global _qapp, _ui_ready_event

    if threading.current_thread() is threading.main_thread():
        dlog("WARNING",
             "_ui_thread_loop: running on the MAIN thread, not a background "
             "thread as expected — check app.py's threading.Thread(...) call")

    if "PyQt6.QtWidgets" in sys.modules:
        dlog("WARNING",
             "_ui_thread_loop: PyQt6.QtWidgets was already imported before "
             "this thread started — if that import happened on a different "
             "thread, QApplication creation below is about to violate Qt's "
             "thread-affinity rule and may crash with an access violation. "
             "No deskwarden.ui.* module should import PyQt6 at module "
             "top-level unless it is guaranteed to only ever be imported "
             "from this thread.")

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    try:
        _qapp = QApplication.instance() or QApplication(sys.argv)
    except Exception as e:
      
        log_crash("_ui_thread_loop: QApplication() failed", e)
        raise
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
    dlog("INFO", "_ui_thread_loop: QApplication created, entering event loop")
    _qapp.exec()


# ═════════════════════════════════════════════════════════════════════════
# Background thread
# ═════════════════════════════════════════════════════════════════════════

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
