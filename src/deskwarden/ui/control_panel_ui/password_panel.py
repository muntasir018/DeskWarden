"""
DeskWarden - ui/control_panel_ui/password_panel.py
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor

from ...core.config import save_config
from ...core.security import hash_pw

from .theme import _BG, _CARD, _CARD2, _BORD, _ACC, _ACC2, _FG, _MUTE, _RED, _GREEN
from .widgets import _Card


class _PasswordPanelMixin:

    # ── Build ────────────────────────────────────────────────────────────

    def _build_password_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

        card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 20); cl.setSpacing(10)

        hdr = QHBoxLayout()
        hl = QLabel("MASTER PASSWORD")
        hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hl.setStyleSheet(f"color: #b794f6; background: transparent;")
        hdr.addWidget(hl); hdr.addStretch()
        has_pw = bool(self._cfg.get("password_hash"))
        bc = _GREEN if has_pw else _RED
        bt = "✓ Set" if has_pw else "✗ Not set"
        badge = QLabel(bt)
        badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"""
            color: white; background: {bc};
            border-radius: 10px; padding: 2px 10px;""")
        hdr.addWidget(badge)
        self._pw_badge = badge
        cl.addLayout(hdr)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(div)

        self._pw_toggle_btn = QPushButton(
            "🔑  Change Password" if has_pw else "🔑  Set Password")
        self._pw_toggle_btn.setFixedHeight(36)
        self._pw_toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pw_toggle_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._pw_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 0 20px; text-align: left;
            }}
            QPushButton:hover {{ background: {_BORD}; }}""")
        self._pw_toggle_btn.clicked.connect(self._toggle_pw_form)

        self._pwtoggle_glow = QGraphicsDropShadowEffect()
        self._pwtoggle_glow.setBlurRadius(0)
        self._pwtoggle_glow.setColor(QColor(_ACC))
        self._pwtoggle_glow.setOffset(0, 0)
        self._pw_toggle_btn.setGraphicsEffect(self._pwtoggle_glow)

        def _pwtoggle_enter(ev):
            self._pwtoggle_glow.setBlurRadius(16)
            QPushButton.enterEvent(self._pw_toggle_btn, ev)
        def _pwtoggle_leave(ev):
            self._pwtoggle_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._pw_toggle_btn, ev)
        self._pw_toggle_btn.enterEvent = _pwtoggle_enter
        self._pw_toggle_btn.leaveEvent = _pwtoggle_leave

        cl.addWidget(self._pw_toggle_btn)

        self._pw_form = QWidget(); self._pw_form.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(self._pw_form)
        fl.setContentsMargins(0, 8, 0, 0); fl.setSpacing(8)

        if has_pw:
            ol = QLabel("Current Password")
            ol.setFont(QFont("Segoe UI", 9))
            ol.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            fl.addWidget(ol)
            self._old_pw = QLineEdit(); self._old_pw.setEchoMode(QLineEdit.EchoMode.Password)
            fl.addWidget(self._old_pw)
        else:
            self._old_pw = None

        nl = QLabel("New Password")
        nl.setFont(QFont("Segoe UI", 9))
        nl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        fl.addWidget(nl)
        self._new_pw = QLineEdit(); self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addWidget(self._new_pw)

        cnl = QLabel("Confirm New Password")
        cnl.setFont(QFont("Segoe UI", 9))
        cnl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        fl.addWidget(cnl)
        self._con_pw = QLineEdit(); self._con_pw.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addWidget(self._con_pw)

        self._pw_err = QLabel("")
        self._pw_err.setFont(QFont("Segoe UI", 9))
        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        fl.addWidget(self._pw_err)

        save_btn = QPushButton("💾  Save Password")
        save_btn.setFixedHeight(36)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 8px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        save_btn.clicked.connect(self._save_pw)
        fl.addWidget(save_btn)

        self._savepw_glow = QGraphicsDropShadowEffect()
        self._savepw_glow.setBlurRadius(0)
        self._savepw_glow.setColor(QColor(_ACC))
        self._savepw_glow.setOffset(0, 0)
        save_btn.setGraphicsEffect(self._savepw_glow)

        def _savepw_enter(ev):
            self._savepw_glow.setBlurRadius(22)
            QPushButton.enterEvent(save_btn, ev)

        def _savepw_leave(ev):
            self._savepw_glow.setBlurRadius(0)
            QPushButton.leaveEvent(save_btn, ev)

        save_btn.enterEvent = _savepw_enter
        save_btn.leaveEvent = _savepw_leave

        self._pw_form.setVisible(False)
        cl.addWidget(self._pw_form)

        pl.addWidget(card)
        pl.addStretch()
        self._scroll_lay.addWidget(panel)
        self._section_widgets["password"] = panel
        panel.setVisible(False)

    # ── Form state ───────────────────────────────────────────────────────

    def _toggle_pw_form(self):
        showing = not self._pw_form.isVisible()
        self._pw_form.setVisible(showing)
        has_pw = bool(self._cfg.get("password_hash"))
        if showing:
            self._pw_toggle_btn.setText("✕  Cancel")
        else:
            self._pw_toggle_btn.setText(
                "🔑  Change Password" if has_pw else "🔑  Set Password")
            self._reset_pw_form()

    def _reset_pw_form(self):
        if getattr(self, "_old_pw", None):
            self._old_pw.clear()
        if getattr(self, "_new_pw", None):
            self._new_pw.clear()
        if getattr(self, "_con_pw", None):
            self._con_pw.clear()
        if getattr(self, "_pw_err", None):
            self._pw_err.setText("")
        if getattr(self, "_pw_form", None):
            self._pw_form.setVisible(False)
        if getattr(self, "_pw_toggle_btn", None):
            has_pw = bool(self._cfg.get("password_hash"))
            self._pw_toggle_btn.setText(
                "🔑  Change Password" if has_pw else "🔑  Set Password")

    # ── Actions ──────────────────────────────────────────────────────────

    def _save_pw(self):
        o = self._old_pw.text() if self._old_pw else ""
        n = self._new_pw.text()
        c = self._con_pw.text()
        has_pw = bool(self._cfg.get("password_hash"))
        if has_pw and hash_pw(o) != self._cfg.get("password_hash",""):
            self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._pw_err.setText("✗ Current password is incorrect."); return
        if len(n) < 4:
            self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._pw_err.setText("✗ Must be at least 4 characters."); return
        if n != c:
            self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._pw_err.setText("✗ Passwords do not match."); return
        self._cfg["password_hash"] = hash_pw(n)
        save_config(self._cfg)
        self._pw_err.setStyleSheet(f"color: {_GREEN}; background: transparent;")
        self._pw_err.setText("✓ Password saved.")
        if self._old_pw: self._old_pw.clear()
        self._new_pw.clear(); self._con_pw.clear()
        self._pw_badge.setText("✓ Set")
        self._pw_badge.setStyleSheet(f"""
            color: white; background: {_GREEN};
            border-radius: 10px; padding: 2px 10px;""")
