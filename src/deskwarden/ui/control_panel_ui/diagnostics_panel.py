"""
DeskWarden - ui/control_panel_ui/diagnostics_panel.py
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QPlainTextEdit,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QCursor

from ...core.paths import (
    DIAGNOSTIC_LOG_PATH as _DIAG_PATH,
    CRASH_LOG_PATH as _CRASH_PATH,
)

from .theme import _BG, _CARD2, _BORD, _ACC, _TEAL, _GREEN, _FG, _MUTE
from .widgets import _Card


class _DiagnosticsPanelMixin:

    # ── Diagnostic Log: build ────────────────────────────────────────────

    def _build_diag_log_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(12)

        # ── Top action bar ────────────────────────────────────────
        top_row = QWidget(); top_row.setStyleSheet(f"background: {_BG};")
        trl = QHBoxLayout(top_row)
        trl.setContentsMargins(0, 0, 0, 0); trl.setSpacing(8)

        back_btn = QPushButton("← Settings")
        back_btn.setFixedHeight(34)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setFont(QFont("Segoe UI", 9))
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTE};
                border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {_FG}; }}""")
        back_btn.clicked.connect(lambda: self._switch("settings_cfg"))
        trl.addWidget(back_btn)

        sep_lbl = QLabel("|")
        sep_lbl.setStyleSheet(f"color: {_BORD}; background: transparent;")
        trl.addWidget(sep_lbl)

        self._diag_refresh_btn = QPushButton("↺  Refresh")
        self._diag_refresh_btn.setFixedHeight(34)
        self._diag_refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._diag_refresh_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._diag_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_ACC}; border-color: {_ACC}; color: white; }}
            QPushButton:pressed {{ background: #5b21b6; }}""")
        self._diag_refresh_btn.clicked.connect(self._refresh_diag_log)

        self._diagrefresh_glow = QGraphicsDropShadowEffect()
        self._diagrefresh_glow.setBlurRadius(0)
        self._diagrefresh_glow.setColor(QColor(_ACC))
        self._diagrefresh_glow.setOffset(0, 0)
        self._diag_refresh_btn.setGraphicsEffect(self._diagrefresh_glow)

        def _diagrefresh_enter(ev):
            self._diagrefresh_glow.setBlurRadius(18)
            QPushButton.enterEvent(self._diag_refresh_btn, ev)
        def _diagrefresh_leave(ev):
            self._diagrefresh_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._diag_refresh_btn, ev)
        self._diag_refresh_btn.enterEvent = _diagrefresh_enter
        self._diag_refresh_btn.leaveEvent = _diagrefresh_leave

        trl.addWidget(self._diag_refresh_btn)

        self._diag_open_btn = QPushButton("📂  Open File")
        self._diag_open_btn.setFixedHeight(34)
        self._diag_open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._diag_open_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._diag_open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_TEAL}; border-color: {_TEAL}; color: white; }}
            QPushButton:pressed {{ background: #0e7490; }}""")
        self._diag_open_btn.clicked.connect(self._open_diag_file)

        self._diagopen_glow = QGraphicsDropShadowEffect()
        self._diagopen_glow.setBlurRadius(0)
        self._diagopen_glow.setColor(QColor(_TEAL))
        self._diagopen_glow.setOffset(0, 0)
        self._diag_open_btn.setGraphicsEffect(self._diagopen_glow)

        def _diagopen_enter(ev):
            self._diagopen_glow.setBlurRadius(18)
            QPushButton.enterEvent(self._diag_open_btn, ev)
        def _diagopen_leave(ev):
            self._diagopen_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._diag_open_btn, ev)
        self._diag_open_btn.enterEvent = _diagopen_enter
        self._diag_open_btn.leaveEvent = _diagopen_leave

        trl.addWidget(self._diag_open_btn)

        self._diag_copy_btn = QPushButton("⎘  Copy All")
        self._diag_copy_btn.setFixedHeight(34)
        self._diag_copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._diag_copy_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._diag_copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: #334155; border-color: #475569; color: white; }}
            QPushButton:pressed {{ background: #1e293b; }}""")
        self._diag_copy_btn.clicked.connect(self._copy_diag_log)

        self._diagcopy_glow = QGraphicsDropShadowEffect()
        self._diagcopy_glow.setBlurRadius(0)
        self._diagcopy_glow.setColor(QColor("#475569"))
        self._diagcopy_glow.setOffset(0, 0)
        self._diag_copy_btn.setGraphicsEffect(self._diagcopy_glow)

        def _diagcopy_enter(ev):
            self._diagcopy_glow.setBlurRadius(16)
            QPushButton.enterEvent(self._diag_copy_btn, ev)
        def _diagcopy_leave(ev):
            self._diagcopy_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._diag_copy_btn, ev)
        self._diag_copy_btn.enterEvent = _diagcopy_enter
        self._diag_copy_btn.leaveEvent = _diagcopy_leave

        trl.addWidget(self._diag_copy_btn)

        trl.addStretch()

        self._diag_line_count = QLabel("")
        self._diag_line_count.setFont(QFont("Segoe UI", 8))
        self._diag_line_count.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        trl.addWidget(self._diag_line_count)

        pl.addWidget(top_row)

        # ── Log viewer card ───────────────────────────────────────
        log_card = _Card(panel, bg="#07050f", border=_BORD, radius=12)
        lcl = QVBoxLayout(log_card)
        lcl.setContentsMargins(0, 0, 0, 0); lcl.setSpacing(0)

        self._diag_viewer = QPlainTextEdit()
        self._diag_viewer.setReadOnly(True)
        self._diag_viewer.setFont(QFont("Consolas", 8))
        self._diag_viewer.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #07050f; color: #c9d1d9;
                border: none; border-radius: 12px;
                padding: 12px; selection-background-color: {_ACC};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border-radius: 3px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORD}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._diag_viewer.setMinimumHeight(385)
        lcl.addWidget(self._diag_viewer)
        pl.addWidget(log_card)

        # ── Footer hint ───────────────────────────────────────────
        hint = QLabel(f"📁  File: %APPDATA%\\DeskWarden\\diagnostic_log.txt  ·  Auto-cleaned every 7 days  ·  Max 3000 lines")
        hint.setFont(QFont("Segoe UI", 7))
        hint.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        pl.addWidget(hint)

        self._scroll_lay.addWidget(panel)
        self._section_widgets["diag_log"] = panel
        panel.setVisible(False)

    # ── Diagnostic Log: actions ──────────────────────────────────────────

    def _refresh_diag_log(self):
        try:
            if not os.path.exists(_DIAG_PATH):
                self._diag_viewer.setPlainText("No diagnostic log found yet.\nRun DeskWarden for a while and come back.")
                self._diag_line_count.setText("0 lines")
                return
            with open(_DIAG_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Show last 500 lines so it stays fast
            MAX_SHOW = 500
            if len(lines) > MAX_SHOW:
                shown = lines[-MAX_SHOW:]
                header = f"[ Showing last {MAX_SHOW} of {len(lines)} lines ]\n\n"
            else:
                shown = lines
                header = ""
            self._diag_viewer.setPlainText(header + "".join(shown))
            # Scroll to bottom
            sb = self._diag_viewer.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._diag_line_count.setText(f"{len(lines)} lines")
        except Exception as e:
            self._diag_viewer.setPlainText(f"Could not read diagnostic log: {e}")
            self._diag_line_count.setText("error")

    def _open_diag_file(self):
        try:
            import subprocess
            if os.path.exists(_DIAG_PATH):
                subprocess.Popen(["notepad.exe", _DIAG_PATH])
            else:
                self._diag_viewer.setPlainText("Diagnostic log file does not exist yet.")
        except Exception as e:
            self._diag_viewer.setPlainText(f"Could not open file: {e}")

    def _pulse_copy_glow(self, btn, glow_fx, normal_color):

        try:
            glow_fx.setColor(QColor(_GREEN))
            pulse_up = QPropertyAnimation(glow_fx, b"blurRadius", self)
            pulse_up.setDuration(120)
            pulse_up.setStartValue(glow_fx.blurRadius())
            pulse_up.setEndValue(26)
            pulse_up.setEasingCurve(QEasingCurve.Type.OutQuad)

            def _settle():
                pulse_down = QPropertyAnimation(glow_fx, b"blurRadius", self)
                pulse_down.setDuration(280)
                pulse_down.setStartValue(26)
                pulse_down.setEndValue(16 if btn.underMouse() else 0)
                pulse_down.setEasingCurve(QEasingCurve.Type.InQuad)
                pulse_down.finished.connect(
                    lambda: glow_fx.setColor(QColor(normal_color)))
                self._copy_pulse_down = pulse_down
                pulse_down.start()

            pulse_up.finished.connect(_settle)
            self._copy_pulse_up = pulse_up
            pulse_up.start()
        except Exception:
            pass

    def _copy_diag_log(self):
        try:
            from PyQt6.QtWidgets import QApplication as _QApp
            text = self._diag_viewer.toPlainText()
            if text:
                _QApp.clipboard().setText(text)
                self._diag_copy_btn.setText("✓  Copied!")
                self._pulse_copy_glow(self._diag_copy_btn, self._diagcopy_glow, "#475569")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(2000, lambda: self._diag_copy_btn.setText("⎘  Copy All"))
        except Exception:
            pass

    # ── Crash Log: build ─────────────────────────────────────────────────

    def _build_crash_log_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(12)

        # ── Top action bar ────────────────────────────────────────
        top_row = QWidget(); top_row.setStyleSheet(f"background: {_BG};")
        trl = QHBoxLayout(top_row)
        trl.setContentsMargins(0, 0, 0, 0); trl.setSpacing(8)

        back_btn = QPushButton("← Settings")
        back_btn.setFixedHeight(34)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setFont(QFont("Segoe UI", 9))
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_MUTE};
                border: none; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {_FG}; }}""")
        back_btn.clicked.connect(lambda: self._switch("settings_cfg"))
        trl.addWidget(back_btn)

        sep_lbl = QLabel("|")
        sep_lbl.setStyleSheet(f"color: {_BORD}; background: transparent;")
        trl.addWidget(sep_lbl)

        self._crash_refresh_btn = QPushButton("↺  Refresh")
        self._crash_refresh_btn.setFixedHeight(34)
        self._crash_refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._crash_refresh_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._crash_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_ACC}; border-color: {_ACC}; color: white; }}
            QPushButton:pressed {{ background: #5b21b6; }}""")
        self._crash_refresh_btn.clicked.connect(self._refresh_crash_log)

        self._crashrefresh_glow = QGraphicsDropShadowEffect()
        self._crashrefresh_glow.setBlurRadius(0)
        self._crashrefresh_glow.setColor(QColor(_ACC))
        self._crashrefresh_glow.setOffset(0, 0)
        self._crash_refresh_btn.setGraphicsEffect(self._crashrefresh_glow)

        def _crashrefresh_enter(ev):
            self._crashrefresh_glow.setBlurRadius(18)
            QPushButton.enterEvent(self._crash_refresh_btn, ev)
        def _crashrefresh_leave(ev):
            self._crashrefresh_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._crash_refresh_btn, ev)
        self._crash_refresh_btn.enterEvent = _crashrefresh_enter
        self._crash_refresh_btn.leaveEvent = _crashrefresh_leave

        trl.addWidget(self._crash_refresh_btn)

        self._crash_open_btn = QPushButton("📂  Open File")
        self._crash_open_btn.setFixedHeight(34)
        self._crash_open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._crash_open_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._crash_open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {_TEAL}; border-color: {_TEAL}; color: white; }}
            QPushButton:pressed {{ background: #0e7490; }}""")
        self._crash_open_btn.clicked.connect(self._open_crash_file)

        self._crashopen_glow = QGraphicsDropShadowEffect()
        self._crashopen_glow.setBlurRadius(0)
        self._crashopen_glow.setColor(QColor(_TEAL))
        self._crashopen_glow.setOffset(0, 0)
        self._crash_open_btn.setGraphicsEffect(self._crashopen_glow)

        def _crashopen_enter(ev):
            self._crashopen_glow.setBlurRadius(18)
            QPushButton.enterEvent(self._crash_open_btn, ev)
        def _crashopen_leave(ev):
            self._crashopen_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._crash_open_btn, ev)
        self._crash_open_btn.enterEvent = _crashopen_enter
        self._crash_open_btn.leaveEvent = _crashopen_leave

        trl.addWidget(self._crash_open_btn)

        self._crash_copy_btn = QPushButton("⎘  Copy All")
        self._crash_copy_btn.setFixedHeight(34)
        self._crash_copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._crash_copy_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._crash_copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 14px;
            }}
            QPushButton:hover {{ background: #334155; border-color: #475569; color: white; }}
            QPushButton:pressed {{ background: #1e293b; }}""")
        self._crash_copy_btn.clicked.connect(self._copy_crash_log)

        self._crashcopy_glow = QGraphicsDropShadowEffect()
        self._crashcopy_glow.setBlurRadius(0)
        self._crashcopy_glow.setColor(QColor("#475569"))
        self._crashcopy_glow.setOffset(0, 0)
        self._crash_copy_btn.setGraphicsEffect(self._crashcopy_glow)

        def _crashcopy_enter(ev):
            self._crashcopy_glow.setBlurRadius(16)
            QPushButton.enterEvent(self._crash_copy_btn, ev)
        def _crashcopy_leave(ev):
            self._crashcopy_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._crash_copy_btn, ev)
        self._crash_copy_btn.enterEvent = _crashcopy_enter
        self._crash_copy_btn.leaveEvent = _crashcopy_leave

        trl.addWidget(self._crash_copy_btn)

        trl.addStretch()

        self._crash_line_count = QLabel("")
        self._crash_line_count.setFont(QFont("Segoe UI", 8))
        self._crash_line_count.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        trl.addWidget(self._crash_line_count)

        pl.addWidget(top_row)

        # ── Log viewer card ───────────────────────────────────────
        log_card = _Card(panel, bg="#07050f", border=_BORD, radius=12)
        lcl = QVBoxLayout(log_card)
        lcl.setContentsMargins(0, 0, 0, 0); lcl.setSpacing(0)

        self._crash_viewer = QPlainTextEdit()
        self._crash_viewer.setReadOnly(True)
        self._crash_viewer.setFont(QFont("Consolas", 8))
        self._crash_viewer.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #07050f; color: #c9d1d9;
                border: none; border-radius: 12px;
                padding: 12px; selection-background-color: {_ACC};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border-radius: 3px; margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORD}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._crash_viewer.setMinimumHeight(385)
        lcl.addWidget(self._crash_viewer)
        pl.addWidget(log_card)

        # ── Footer hint ───────────────────────────────────────────
        hint = QLabel(f"📁  File: %APPDATA%\\DeskWarden\\crash_log.txt  ·  Error & exception reports")
        hint.setFont(QFont("Segoe UI", 7))
        hint.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        pl.addWidget(hint)

        self._scroll_lay.addWidget(panel)
        self._section_widgets["crash_log"] = panel
        panel.setVisible(False)

    # ── Crash Log: actions ───────────────────────────────────────────────

    def _refresh_crash_log(self):
        try:
            if not os.path.exists(_CRASH_PATH):
                self._crash_viewer.setPlainText("No crash log found — great news, no crashes recorded!")
                self._crash_line_count.setText("0 lines")
                return
            with open(_CRASH_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            MAX_SHOW = 500
            if len(lines) > MAX_SHOW:
                shown = lines[-MAX_SHOW:]
                header = f"[ Showing last {MAX_SHOW} of {len(lines)} lines ]\n\n"
            else:
                shown = lines
                header = ""
            self._crash_viewer.setPlainText(header + "".join(shown))
            sb = self._crash_viewer.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._crash_line_count.setText(f"{len(lines)} lines")
        except Exception as e:
            self._crash_viewer.setPlainText(f"Could not read crash log: {e}")
            self._crash_line_count.setText("error")

    def _open_crash_file(self):
        try:
            import subprocess
            if os.path.exists(_CRASH_PATH):
                subprocess.Popen(["notepad.exe", _CRASH_PATH])
            else:
                self._crash_viewer.setPlainText("Crash log file does not exist yet.")
        except Exception as e:
            self._crash_viewer.setPlainText(f"Could not open file: {e}")

    def _copy_crash_log(self):
        try:
            from PyQt6.QtWidgets import QApplication as _QApp
            text = self._crash_viewer.toPlainText()
            if text:
                _QApp.clipboard().setText(text)
                self._crash_copy_btn.setText("✓  Copied!")
                self._pulse_copy_glow(self._crash_copy_btn, self._crashcopy_glow, "#475569")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(2000, lambda: self._crash_copy_btn.setText("⎘  Copy All"))
        except Exception:
            pass
