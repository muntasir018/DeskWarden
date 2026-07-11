"""
DeskWarden - ui/control_panel_ui/security_log_panel.py
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor

from ...core.security import load_security_log, _save_security_log

from .theme import _BG, _CARD, _CARD2, _BORD, _RED, _GREEN, _FG, _MUTE
from .widgets import _Card


class _SecurityLogPanelMixin:

    # ── Build ────────────────────────────────────────────────────────────

    def _build_log_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

        card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(8)

        hdr = QHBoxLayout()
        hl = QLabel("🛡️  AUTH EVENTS")
        hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hl.setStyleSheet(f"color: #b794f6; background: transparent;")
        hdr.addWidget(hl); hdr.addStretch()
        clr_btn = QPushButton("🗑  Clear Log")
        clr_btn.setFixedHeight(28)
        clr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clr_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1e0d18; color: #fca5a5;
                border: 1px solid #3d1020; border-radius: 6px;
                padding: 0 10px; font-size: 8pt;
            }}
            QPushButton:hover {{ background: #3d0d10; color: white; }}""")
        clr_btn.clicked.connect(self._clear_log)
        hdr.addWidget(clr_btn)

        self._clrlog_glow = QGraphicsDropShadowEffect()
        self._clrlog_glow.setBlurRadius(0)
        self._clrlog_glow.setColor(QColor(_RED))
        self._clrlog_glow.setOffset(0, 0)
        clr_btn.setGraphicsEffect(self._clrlog_glow)

        def _clrlog_enter(ev):
            self._clrlog_glow.setBlurRadius(16)
            QPushButton.enterEvent(clr_btn, ev)

        def _clrlog_leave(ev):
            self._clrlog_glow.setBlurRadius(0)
            QPushButton.leaveEvent(clr_btn, ev)

        clr_btn.enterEvent = _clrlog_enter
        clr_btn.leaveEvent = _clrlog_leave
        cl.addLayout(hdr)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(div)

        self._log_container_lay = cl
        self._log_card = card

        pl.addWidget(card)
        pl.addStretch()
        self._scroll_lay.addWidget(panel)
        self._section_widgets["log"] = panel
        panel.setVisible(False)

    # ── Refresh ──────────────────────────────────────────────────────────

    def _refresh_log(self):
        while self._log_container_lay.count() > 2:
            item = self._log_container_lay.takeAt(2)
            if item and item.widget():
                item.widget().deleteLater()

        entries = load_security_log()
        recent = list(reversed(entries))[:30]
        EVENT_ICON = {
            "wrong_password": ("⚠", "#f59e0b"),
            "lockout_start":  ("🔒", _RED),
            "lockout_end":    ("🔓", _GREEN),
            "success":        ("✅", _GREEN),
        }
        type_map = {
            "wrong_password": "Wrong Password",
            "lockout_start":  "Locked Out",
            "lockout_end":    "Lockout Ended",
            "success":        "Unlocked",
        }
        if not recent:
            el = QLabel("No security events recorded yet.")
            el.setFont(QFont("Segoe UI", 9))
            el.setStyleSheet(f"color: {_MUTE}; background: transparent; padding: 8px 0;")
            self._log_container_lay.addWidget(el)
            return

        for ev in recent:
            et = ev.get("type", "")
            icon_g, color = EVENT_ICON.get(et, ("ℹ️", _MUTE))

            row = _Card(bg=_CARD2, border=_BORD, radius=8,
                        accent_color=color)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 8, 16, 8); rl.setSpacing(10)

            il = QLabel(icon_g)
            il.setFont(QFont("Segoe UI Emoji", 14))
            il.setStyleSheet(f"color: {color}; background: transparent;")
            il.setFixedWidth(28)
            rl.addWidget(il)

            info_w = QWidget(); info_w.setStyleSheet("background: transparent;")
            infl = QVBoxLayout(info_w)
            infl.setContentsMargins(0, 0, 0, 0); infl.setSpacing(1)

            lbl_txt = type_map.get(et, et)
            where_  = ev.get("where", "")
            tl_l = QLabel(f"{lbl_txt}  —  {where_}")
            tl_l.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            tl_l.setStyleSheet(f"color: {_FG}; background: transparent;")
            infl.addWidget(tl_l)

            tl_t = QLabel(ev.get("time", ""))
            tl_t.setFont(QFont("Segoe UI", 8))
            tl_t.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            infl.addWidget(tl_t)

            if ev.get("note"):
                nl = QLabel(ev["note"])
                nl.setFont(QFont("Segoe UI", 8))
                nl.setStyleSheet(f"color: {color}; background: transparent;")
                infl.addWidget(nl)

            rl.addWidget(info_w, 1)
            self._log_container_lay.addWidget(row)

    # ── Actions ──────────────────────────────────────────────────────────

    def _clear_log(self):
        _save_security_log([])
        self._refresh_log()
