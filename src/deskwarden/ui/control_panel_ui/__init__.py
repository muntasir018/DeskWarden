"""
DeskWarden - ui/control_panel_ui/__init__.py

Entry point for Control Panel mode: sets up the QApplication, wires the
Qt-event-loop crash safety net, then shows either the first-run setup
dialog or the main Control Panel window.

This package replaces the old monolithic control_panel_ui.py module.
The import used from DeskWarden.py —
`from deskwarden.ui.control_panel_ui import run_control_panel_mode` —
is unchanged, since Python treats a package's __init__.py the same way
as the old single module for that purpose.

Behavior is unchanged from the original single-file version; code was
only reorganized into:
  - theme.py             color palette + _glow()
  - widgets.py            _Card, _IconBox, _AppIconBox, _NavBtn, _PillBtn,
                          _StatusSpinner, _RotatingStatus
  - status_items.py       the sidebar's rotating status line
  - update_dialog.py      _UpdateCatalogDialog ("what's new" popup)
  - first_run_dialog.py   _FirstRunSetupDialog (set master password)
  - main_window.py        _ControlPanelWin (the main window itself)
"""

from ...core.paths import CRASH_LOG_PATH as _CRASH_PATH
from ...core.logging_utils import dlog, log_crash
from ...core.config import load_config

from .first_run_dialog import _FirstRunSetupDialog
from .main_window import _ControlPanelWin


def run_control_panel_mode():
    try:
        from PyQt6.QtWidgets import QApplication
        import sys as _sys

        _app = QApplication(_sys.argv)
        _app.setStyle("Fusion")
        _app.setQuitOnLastWindowClosed(True)

        # ── Global safety net ──────────────────────────────────────────
        # PyQt slots/callbacks (button clicks, QTimer.singleShot, showEvent,
        # etc.) run inside the C++ event loop. An unhandled Python exception
        # there does NOT propagate back through the try/except that wraps
        # this whole function — it can silently kill this subprocess with
        # nothing in the crash log, which looks exactly like "Control Panel
        # doesn't open." This hook makes sure every such exception is
        # written to crash_log.txt / diagnostic_log.txt before Qt gets a
        # chance to swallow it.
        def _qt_excepthook(exc_type, exc_value, exc_tb):
            try:
                import traceback as _tb
                dlog("ERROR", f"CRASH [Qt event loop]: {exc_type.__name__}: {exc_value}")
                with open(_CRASH_PATH, "a", encoding="utf-8") as _f:
                    _f.write(f"\n{'=' * 60}\nWHERE  : Qt event loop\n")
                    _f.write("".join(_tb.format_exception(exc_type, exc_value, exc_tb)))
            except Exception:
                pass
            _sys.__excepthook__(exc_type, exc_value, exc_tb)
        _sys.excepthook = _qt_excepthook

        try:
            from PyQt6.QtSvg import QSvgRenderer as _QSvgRenderer
            _HAS_SVG = True
        except ImportError:
            _HAS_SVG = False

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
