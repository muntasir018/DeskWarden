"""
DeskWarden - tests/test_main_window_smoke.py
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (winreg)",
)


def test_control_panel_window_can_be_created_shown_and_resized(qapp):
    from deskwarden.ui.control_panel_ui.main_window import _ControlPanelWin

    win = _ControlPanelWin()
    try:
        win.show()
        win.resize(950, 650)
        win.resize(700, 500)
        qapp.processEvents()
    finally:
        win.close()


def test_control_panel_window_mro_has_qmainwindow_after_mixins():
    from PyQt6.QtWidgets import QMainWindow
    from deskwarden.ui.control_panel_ui.main_window import _ControlPanelWin
    from deskwarden.ui.control_panel_ui.window_chrome import _WindowChromeMixin

    mro = _ControlPanelWin.__mro__
    mixin_index = mro.index(_WindowChromeMixin)
    qmainwindow_index = mro.index(QMainWindow)

    assert mixin_index < qmainwindow_index, (
        "_WindowChromeMixin must come before QMainWindow in MRO."
    )
