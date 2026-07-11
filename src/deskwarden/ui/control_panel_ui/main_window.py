"""
DeskWarden - ui/control_panel_ui/main_window.py

The Control Panel main window shell. Behavior is unchanged from the
original monolithic _ControlPanelWin — it's now assembled from mixins
(see ARCHITECTURE.md / REFACTOR_PLAN.md), each holding one panel's worth
of logic.
"""

from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

from ...core.config import load_config

from .theme import _ACC, _TEAL, _RED, _BG

from .window_chrome import _WindowChromeMixin
from .nav_shell import _NavShellMixin
from .apps_panel import _AppsPanelMixin
from .password_panel import _PasswordPanelMixin
from .security_log_panel import _SecurityLogPanelMixin
from .settings_panel import _SettingsPanelMixin
from .diagnostics_panel import _DiagnosticsPanelMixin
from .update_panel import _UpdatePanelMixin
from .settings_io import _SettingsIOMixin


class _ControlPanelWin(
    _WindowChromeMixin,
    _NavShellMixin,
    _AppsPanelMixin,
    _PasswordPanelMixin,
    _SecurityLogPanelMixin,
    _SettingsPanelMixin,
    _DiagnosticsPanelMixin,
    _UpdatePanelMixin,
    _SettingsIOMixin,
    QMainWindow,
):
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
