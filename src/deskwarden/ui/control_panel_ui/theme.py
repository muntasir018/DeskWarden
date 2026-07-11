"""
DeskWarden - ui/control_panel_ui/theme.py

"""

from PyQt6.QtWidgets import QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor

_BG    = "#07050d"
_SIDE  = "#0a0818"
_CARD  = "#100e1c"
_CARD2 = "#161426"
_BORD  = "#241f42"
_ACC   = "#8b5cf6"
_ACC2  = "#a78bfa"
_ACC3  = "#6d28d9"
_FG    = "#f0ecff"
_MUTE  = "#6b6490"
_GREEN = "#34d399"
_RED   = "#f87171"
_TEAL  = "#22d3ee"

_STRIP_X_OFFSET = -1
_STRIP_WIDTH    = 4


def _glow(widget, color=_ACC, radius=18):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(radius)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    widget.setGraphicsEffect(fx)
