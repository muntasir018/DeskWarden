"""
DeskWarden - ui/control_panel_ui/first_run_dialog.py

"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGraphicsDropShadowEffect, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor, QPixmap, QPainter, QPainterPath

from ...core.paths import asset_path
from ...core.config import load_config, save_config
from ...core.security import hash_pw
from .theme import _CARD, _CARD2, _BORD, _ACC, _ACC2, _FG, _MUTE, _RED
from .widgets import _Card


class _FirstRunSetupDialog(QWidget):
    """Forces the user to set a master password on first run,
    before the Control Panel interface is shown."""
    def __init__(self, on_done):
        super().__init__()
        self._on_done = on_done
        self._allow_close = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 490)
        sg = QApplication.instance().primaryScreen().geometry()
        self.move(sg.x() + (sg.width() - 420) // 2,
                  sg.y() + (sg.height() - 490) // 2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = _Card(self, bg=_CARD, border=_BORD, radius=16)
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24); cl.setSpacing(8)

        # ── Logo in first-run dialog ──
        _pm2 = QPixmap(asset_path("icon.png"))
        if not _pm2.isNull():
            _pm2 = _pm2.scaled(72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            class _SetupLogoBox(QWidget):
                def __init__(self, px, sz=72, parent=None):
                    super().__init__(parent)
                    self._px = px
                    self.setFixedSize(sz, sz)
                    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                def paintEvent(self, ev):
                    p2 = QPainter(self)
                    p2.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    path2 = QPainterPath()
                    path2.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
                    p2.setClipPath(path2)
                    p2.drawPixmap(0, 0, self.width(), self.height(), self._px)
                    p2.end()
            icon = _SetupLogoBox(_pm2, 72)
        else:
            icon = QLabel("🔒")
            icon.setFont(QFont("Segoe UI Emoji", 32))
            icon.setStyleSheet(f"color: {_ACC2}; background: transparent;")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Center the logo horizontally
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        cl.addLayout(icon_row)

        title = QLabel("Welcome to DeskWarden")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_FG}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        sub = QLabel(
            "Set a password for the app before you start using it.\n"
            "This password will be used to unlock locked apps and access Control Panel.")
        sub.setFont(QFont("Segoe UI", 9))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        cl.addWidget(sub)

        cl.addSpacing(6)

        _pw_style = f"""
            QLineEdit {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {_ACC}; }}"""

        nl = QLabel("New Password")
        nl.setFont(QFont("Segoe UI", 9))
        nl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        cl.addWidget(nl)
        self._new_pw = QLineEdit()
        self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pw.setFixedHeight(38)
        self._new_pw.setStyleSheet(_pw_style)
        cl.addWidget(self._new_pw)

        cnl = QLabel("Confirm Password")
        cnl.setFont(QFont("Segoe UI", 9))
        cnl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        cl.addWidget(cnl)
        self._con_pw = QLineEdit()
        self._con_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._con_pw.setFixedHeight(38)
        self._con_pw.setStyleSheet(_pw_style)
        cl.addWidget(self._con_pw)

        self._err = QLabel("")
        self._err.setFont(QFont("Segoe UI", 9))
        self._err.setStyleSheet(f"color: {_RED}; background: transparent;")
        self._err.setWordWrap(True)
        cl.addWidget(self._err)

        save_btn = QPushButton("✓  Set Password")
        save_btn.setFixedHeight(40)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 10px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        save_btn.clicked.connect(self._submit)
        cl.addWidget(save_btn)

        _BLUE = "#3b82f6"
        self._save_glow = QGraphicsDropShadowEffect()
        self._save_glow.setBlurRadius(0)
        self._save_glow.setColor(QColor(_BLUE))
        self._save_glow.setOffset(0, 0)
        save_btn.setGraphicsEffect(self._save_glow)

        def _save_enter(ev):
            self._save_glow.setBlurRadius(25)
            QPushButton.enterEvent(save_btn, ev)

        def _save_leave(ev):
            self._save_glow.setBlurRadius(0)
            QPushButton.leaveEvent(save_btn, ev)

        save_btn.enterEvent = _save_enter
        save_btn.leaveEvent = _save_leave

        skip_btn = QPushButton("Skip for now")
        skip_btn.setFixedHeight(34)
        skip_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        skip_btn.setFont(QFont("Segoe UI", 9))
        skip_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTE}; border: none;
                border-radius: 8px; padding: 0 20px;
            }}
            QPushButton:hover {{ color: {_FG}; }}""")
        skip_btn.clicked.connect(self._skip)
        cl.addWidget(skip_btn)

        self._skip_glow = QGraphicsDropShadowEffect()
        self._skip_glow.setBlurRadius(0)
        self._skip_glow.setColor(QColor(_RED))
        self._skip_glow.setOffset(0, 0)
        skip_btn.setGraphicsEffect(self._skip_glow)

        def _skip_enter(ev):
            self._skip_glow.setBlurRadius(20)
            QPushButton.enterEvent(skip_btn, ev)

        def _skip_leave(ev):
            self._skip_glow.setBlurRadius(0)
            QPushButton.leaveEvent(skip_btn, ev)

        skip_btn.enterEvent = _skip_enter
        skip_btn.leaveEvent = _skip_leave

        self._new_pw.returnPressed.connect(self._submit)
        self._con_pw.returnPressed.connect(self._submit)
        self._new_pw.setFocus()

    def keyPressEvent(self, ev):
      
        if ev.key() == Qt.Key.Key_Escape:
            ev.ignore(); return
        if (ev.key() == Qt.Key.Key_F4 and
                ev.modifiers() & Qt.KeyboardModifier.AltModifier):
            ev.ignore(); return
        super().keyPressEvent(ev)

    def closeEvent(self, ev):
        if self._allow_close:
            ev.accept()
        else:
            ev.ignore()

    def _submit(self):
        n = self._new_pw.text()
        c = self._con_pw.text()
        if len(n) < 4:
            self._err.setText("✗ Must be at least 4 characters."); return
        if n != c:
            self._err.setText("✗ Passwords do not match."); return
        cfg = load_config()
        cfg["password_hash"] = hash_pw(n)
        save_config(cfg)
        self._allow_close = True
        self.close()
        self._on_done()

    def _skip(self):
        self._allow_close = True
        self.close()
        self._on_done()

