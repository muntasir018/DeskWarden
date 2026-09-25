"""
DeskWarden - ui/recovery_dialog.py

Dedicated modular dialog for resetting the master password using
the Master Recovery Key. Matches DeskWarden's dark theme aesthetic.
"""

import os
import time
import threading
try:
    import ctypes
    _kernel32 = ctypes.windll.kernel32
    _user32   = ctypes.windll.user32
except Exception:
    _kernel32 = None
    _user32   = None

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QGraphicsDropShadowEffect, QApplication,
    QFileDialog, QStackedWidget,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCursor, QPainter, QPainterPath, QBrush, QPen, QPixmap

from ..core.paths import asset_path
from ..core.config import load_config, save_config
from ..core.logging_utils import dlog, suppress_faulthandler
from ..core.security import (
    hash_pw, generate_recovery_key, hash_recovery_key, verify_recovery_key,
    generate_otp_code, mask_email, send_recovery_otp_worker,
    record_wrong_attempt, check_locked_out, reset_attempt_state,
    log_security_event, PENALTY_THRES, check_daily_otp_limit,
)
from ..core.sound_utils import play_unlock_sound, play_error_sound
from .ui_thread import _run_on_ui_thread


_BG    = "#09070f"
_CARD  = "#110f1e"
_CARD2 = "#171528"
_BORD  = "#2a2545"
_ACC   = "#7c3aed"
_ACC2  = "#9d5cff"
_FG    = "#ede9ff"
_MUTE  = "#5a5478"
_GREEN = "#22c55e"
_RED   = "#ef4444"


class _RCard(QFrame):
    def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=16):
        super().__init__(parent)
        self._bg = QColor(bg)
        self._border = QColor(border)
        self._radius = radius
        self.setAutoFillBackground(False)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), self._radius, self._radius)
        p.fillPath(path, QBrush(self._bg))
        p.setPen(QPen(self._border, 1))
        p.drawPath(path)


def _glow(widget, color=_ACC, radius=18):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(radius)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    widget.setGraphicsEffect(fx)
    return fx


RECOVERY_WINDOW_TITLE = "DeskWarden_AccountRecovery_Window"
RECOVERY_MUTEX_NAME   = "Local\\DeskWarden_AccountRecovery_Mutex"


def flash_existing_window(hwnd: int) -> None:
    """Safely flashes a target Win32 window to indicate activity without causing window-manager z-order flicker."""
    if not hwnd or not _user32 or not _user32.IsWindow(hwnd):
        return
    try:
        _user32.FlashWindow(hwnd, True)
    except Exception as e:
        dlog("WARNING", f"flash_existing_window failed: {e}")


def bring_existing_recovery_to_front() -> bool:
    """Checks if a RecoveryDialog is already open anywhere in the system
    (in this process or in another DeskWarden process such as Control Panel).
    If found, brings it to front, plays the shake animation, and returns True.
    If not found or not visible, returns False."""
    try:
        # 1. In-process check
        inst = getattr(RecoveryDialog, "_current_active_instance", None)
        if inst is not None:
            try:
                if inst.isVisible():
                    if inst.isMinimized():
                        inst.setWindowState(inst.windowState() & ~Qt.WindowState.WindowMinimized)
                        inst.show()
                    inst.raise_()
                    inst.activateWindow()
                    inst.shake()
                    return True
                else:
                    RecoveryDialog._current_active_instance = None
            except Exception:
                RecoveryDialog._current_active_instance = None

        # 2. Cross-process check by window title and actual visibility
        if _user32:
            hwnd = _user32.FindWindowW(None, RECOVERY_WINDOW_TITLE)
            if hwnd and _user32.IsWindow(hwnd) and _user32.IsWindowVisible(hwnd):
                flash_existing_window(hwnd)
                try:
                    _user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                return True

        return False
    except Exception as e:
        dlog("WARNING", f"bring_existing_recovery_to_front failed: {e}")
        return False


def close_active_recovery_dialog(source_context: str = None) -> bool:
    """Closes any active Account Recovery dialog across the system
    (in this process or across processes via Win32 WM_CLOSE).
    If source_context is specified, only closes if the recovery dialog
    was opened from that matching source context."""
    closed = False
    try:
        # 1. In-process instance
        inst = getattr(RecoveryDialog, "_current_active_instance", None)
        if inst is not None:
            if source_context is not None and getattr(inst, "_source_context", None) != source_context:
                return False
            try:
                inst.hide()
                inst.close()
                inst.deleteLater()
                closed = True
                dlog("INFO", f"close_active_recovery_dialog: in-process RecoveryDialog closed (source_context={source_context})")
            except Exception as e:
                dlog("WARNING", f"close_active_recovery_dialog: failed to close in-process dialog: {e}")
            finally:
                RecoveryDialog._current_active_instance = None

        if source_context is not None:
            return closed

        # 2. Cross-process Win32 check with FindWindowW and EnumWindows
        if _user32:
            try:
                # Direct FindWindowW
                hwnd = _user32.FindWindowW(None, RECOVERY_WINDOW_TITLE)
                if hwnd and _user32.IsWindow(hwnd):
                    _user32.ShowWindow(hwnd, 0)  # SW_HIDE
                    _user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                    closed = True
                    dlog("INFO", f"close_active_recovery_dialog: sent WM_CLOSE to recovery window HWND {hwnd}")
            except Exception:
                pass

            try:
                # Enumerate all top-level windows to catch any cross-process recovery windows
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                def _enum_cb(hwnd_item, _):
                    try:
                        if _user32.IsWindow(hwnd_item) and _user32.IsWindowVisible(hwnd_item):
                            length = _user32.GetWindowTextLengthW(hwnd_item)
                            if length > 0:
                                buff = ctypes.create_unicode_buffer(length + 1)
                                _user32.GetWindowTextW(hwnd_item, buff, length + 1)
                                title = buff.value
                                if RECOVERY_WINDOW_TITLE in title or "Account Recovery" in title:
                                    _user32.ShowWindow(hwnd_item, 0)
                                    _user32.PostMessageW(hwnd_item, 0x0010, 0, 0)  # WM_CLOSE
                    except Exception:
                        pass
                    return True
                cb = WNDENUMPROC(_enum_cb)
                _user32.EnumWindows(cb, 0)
            except Exception as e:
                dlog("WARNING", f"close_active_recovery_dialog EnumWindows failed: {e}")

        return closed
    except Exception as e:
        dlog("WARNING", f"close_active_recovery_dialog failed: {e}")
        return False


dismiss_recovery_dialog = close_active_recovery_dialog


def _is_valid_widget(w):
    if w is None:
        return False
    try:
        return w.isVisible() or True
    except (RuntimeError, AttributeError):
        return False


class RecoveryDialog(QWidget):
    """Modal dialog allowing password reset via Master Recovery Key or Email OTP."""

    _current_active_instance = None
    _otp_result_signal = pyqtSignal(bool, str)

    def __init__(self, on_success=None, on_close=None, source_context=None, parent=None):
        super().__init__(parent)
        self._otp_result_signal.connect(self._on_otp_dispatched)
        self._on_success = on_success
        self._on_close = on_close
        self._source_context = source_context
        self._step = 1  # 1: Verify Identity, 2: Set New Password, 3: Show New Key
        self._active_tab = "key"  # "key" or "email"
        self._pending_otp = None
        self._otp_expiry = 0
        self._new_key = None
        self._password_reset_done = False
        self._countdown_seconds = 0
        self._mutex_handle = None
        self._is_duplicate = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(RECOVERY_WINDOW_TITLE)
        self.setFixedSize(490, 365)

        # In-process singleton check
        existing = RecoveryDialog._current_active_instance
        if existing is not None and existing is not self:
            try:
                if existing.isVisible():
                    self._is_duplicate = True
                    existing.raise_()
                    existing.activateWindow()
                    existing.shake()
                    QTimer.singleShot(0, self.deleteLater)
                    return
                else:
                    RecoveryDialog._current_active_instance = None
            except Exception:
                RecoveryDialog._current_active_instance = None

        # Acquire system-wide Win32 mutex
        if _kernel32:
            try:
                self._mutex_handle = _kernel32.CreateMutexW(None, False, RECOVERY_MUTEX_NAME)
            except Exception:
                self._mutex_handle = None

        RecoveryDialog._current_active_instance = self
        self.destroyed.connect(lambda *_: self._release_singleton_lock())

        qapp = QApplication.instance()
        if qapp:
            sg = qapp.primaryScreen().geometry()
            self.move(sg.x() + (sg.width() - 490) // 2,
                      sg.y() + (sg.height() - 365) // 2)

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = _RCard(self, bg=_CARD, border=_BORD, radius=18)
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 16, 24, 18)
        cl.setSpacing(8)

        # ── Title bar ──
        tb = QWidget()
        tb.setFixedHeight(28)
        tb.setStyleSheet("background: transparent;")
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(0, 0, 0, 0)

        icon_pm = QPixmap(asset_path("icon.png"))
        if not icon_pm.isNull():
            icon_pm = icon_pm.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            ico = QLabel()
            ico.setPixmap(icon_pm)
            ico.setFixedSize(18, 18)
            tbl.addWidget(ico)
        else:
            ico = QLabel("🛡️")
            ico.setFont(QFont("Segoe UI Emoji", 10))
            tbl.addWidget(ico)

        tl = QLabel("DeskWarden  ·  Account Recovery")
        tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tl.setStyleSheet(f"color: {_FG}; background: transparent; letter-spacing: 0.3px;")
        tbl.addWidget(tl)
        tbl.addStretch()

        close_b = QPushButton("✕")
        close_b.setFixedSize(24, 24)
        close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {_MUTE};
                border: none; font-size: 9.5pt; border-radius: 12px; }}
            QPushButton:hover {{ background: #7f1d1d; color: white; }}""")
        close_b.clicked.connect(self._on_close_clicked)
        tbl.addWidget(close_b)
        cl.addWidget(tb)

        def _tb_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                ev.accept()
        def _tb_move(ev):
            if getattr(self, "_drag_pos", None) is not None and ev.buttons() & Qt.MouseButton.LeftButton:
                self.move(ev.globalPosition().toPoint() - self._drag_pos)
                ev.accept()
        def _tb_release(ev):
            self._drag_pos = None
            ev.accept()
        tb.mousePressEvent = _tb_press
        tb.mouseMoveEvent = _tb_move
        tb.mouseReleaseEvent = _tb_release
        tl.mousePressEvent = _tb_press
        tl.mouseMoveEvent = _tb_move
        tl.mouseReleaseEvent = _tb_release

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(sep)

        # ── Draggable Title Bar ──
        self._drag = [False, 0, 0]
        def _tb_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._drag[0] = True
                self._drag[1] = ev.globalPosition().x() - self.x()
                self._drag[2] = ev.globalPosition().y() - self.y()
        def _tb_move(ev):
            if self._drag[0]:
                self.move(int(ev.globalPosition().x() - self._drag[1]),
                          int(ev.globalPosition().y() - self._drag[2]))
        def _tb_release(ev):
            self._drag[0] = False
        tb.mousePressEvent = _tb_press
        tb.mouseMoveEvent = _tb_move
        tb.mouseReleaseEvent = _tb_release

        # ── Dynamic Content Container ──
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_lay = QVBoxLayout(self._container)
        self._container_lay.setContentsMargins(0, 2, 0, 0)
        self._container_lay.setSpacing(8)
        cl.addWidget(self._container, 1)

        self._show_step_1()

    def _clear_container(self):
        def _purge_layout(lay):
            while lay.count():
                item = lay.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                child_lay = item.layout()
                if child_lay is not None:
                    _purge_layout(child_lay)
        _purge_layout(self._container_lay)

    # ═════════════════════════════════════════════════════════════════════
    # Step 1: Verify Identity (Key or Email OTP)
    # ═════════════════════════════════════════════════════════════════════

    def _show_step_1(self):
        self._clear_container()
        self._step = 1

        h = QLabel("Reset Master Password")
        h.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        h.setStyleSheet(f"color: {_FG}; background: transparent;")
        self._container_lay.addWidget(h)

        # Method Switcher Row
        self._tab_bar = tab_bar = QWidget()
        tab_bar.setStyleSheet("background: transparent;")
        tab_row = QHBoxLayout(tab_bar)
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(8)

        self._tab_key_btn = QPushButton("🔑  Master Recovery Key")
        self._tab_key_btn.setFixedHeight(32)
        self._tab_key_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._tab_key_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._tab_key_btn.clicked.connect(lambda: self._switch_tab("key"))

        self._tab_email_btn = QPushButton("✉️  Email OTP")
        self._tab_email_btn.setFixedHeight(32)
        self._tab_email_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._tab_email_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._tab_email_btn.clicked.connect(lambda: self._switch_tab("email"))

        tab_row.addWidget(self._tab_key_btn, 1)
        tab_row.addWidget(self._tab_email_btn, 1)
        self._container_lay.addWidget(tab_bar)

        self._sub_stack = QStackedWidget()
        self._sub_stack.setStyleSheet("background: transparent;")

        self._key_page = self._create_key_page()
        self._email_page = self._create_email_page()

        self._sub_stack.addWidget(self._key_page)
        self._sub_stack.addWidget(self._email_page)

        self._container_lay.addWidget(self._sub_stack, 1)

        cfg = load_config()
        key_hash = cfg.get("recovery_key_hash", "").strip()
        key_enabled = bool(cfg.get("recovery_key_enabled", True if key_hash else False))
        email = cfg.get("recovery_email", "").strip()
        email_enabled = bool(cfg.get("recovery_email_enabled", True if email else False))

        key_avail = bool(key_hash and key_enabled)
        email_avail = bool(email and email_enabled)

        if key_avail and email_avail:
            self._tab_bar.setVisible(True)
            if self._active_tab not in ("key", "email"):
                self._active_tab = "key"
        elif email_avail:
            self._tab_bar.setVisible(False)
            self._active_tab = "email"
        elif key_avail:
            self._tab_bar.setVisible(False)
            self._active_tab = "key"
        else:
            self._tab_bar.setVisible(False)
            self._active_tab = "key"

        self._update_tab_buttons()
        self._sub_stack.setCurrentIndex(0 if self._active_tab == "key" else 1)

        is_locked, wait_s = check_locked_out("Recovery")
        if is_locked:
            self._start_countdown(wait_s)
        else:
            if self._active_tab == "key" and hasattr(self, "_key_input"):
                self._key_input.setFocus()
            elif self._active_tab == "email" and hasattr(self, "_tab_email_btn"):
                self._tab_email_btn.setFocus()

    def _switch_tab(self, tab):
        if self._active_tab == tab:
            return
        cfg = load_config()
        key_hash = cfg.get("recovery_key_hash", "").strip()
        key_enabled = bool(cfg.get("recovery_key_enabled", True if key_hash else False))
        email = cfg.get("recovery_email", "").strip()
        email_enabled = bool(cfg.get("recovery_email_enabled", True if email else False))
        if tab == "key" and not (key_hash and key_enabled):
            return
        if tab == "email" and not (email and email_enabled):
            return
        self._active_tab = tab
        self._update_tab_buttons()
        if hasattr(self, "_sub_stack"):
            self._sub_stack.setCurrentIndex(0 if tab == "key" else 1)
        is_locked, wait_s = check_locked_out("Recovery")
        if is_locked:
            self._start_countdown(wait_s)
        else:
            if tab == "key" and hasattr(self, "_key_input"):
                self._key_input.setFocus()
            elif tab == "email" and hasattr(self, "_tab_email_btn"):
                self._tab_email_btn.setFocus()

    def _update_tab_buttons(self):
        active_style = f"""
            QPushButton {{
                background: {_ACC}; color: white;
                border: 1px solid {_ACC2}; border-radius: 8px;
                outline: none;
            }}"""
        inactive_style = f"""
            QPushButton {{
                background: {_CARD2}; color: {_MUTE};
                border: 1px solid {_BORD}; border-radius: 8px;
                outline: none;
            }}
            QPushButton:hover {{ background: #221d3b; color: {_FG}; }}"""
        if self._active_tab == "key":
            self._tab_key_btn.setStyleSheet(active_style)
            self._tab_email_btn.setStyleSheet(inactive_style)
        else:
            self._tab_key_btn.setStyleSheet(inactive_style)
            self._tab_email_btn.setStyleSheet(active_style)

    # ── Tab 1: Recovery Key Page ──

    def _create_key_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        sub = QLabel("Enter your 16-character Emergency Recovery Key below to prove ownership.")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        kl = QLabel("Emergency Recovery Key")
        kl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        kl.setStyleSheet(f"color: {_ACC2}; background: transparent;")
        lay.addWidget(kl)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("DW-XXXX-XXXX-XXXX-XXXX")
        self._key_input.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self._key_input.setFixedHeight(36)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 0 12px; letter-spacing: 1.2px;
            }}
            QLineEdit:focus {{
                border: 1px solid {_ACC2};
                background: #14102c;
            }}""")
        lay.addWidget(self._key_input)

        self._err_lbl = QLabel("")
        self._err_lbl.setFont(QFont("Segoe UI", 8))
        self._err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
        self._err_lbl.setWordWrap(True)
        lay.addWidget(self._err_lbl)

        self._verify_btn = QPushButton("Verify Recovery Key →")
        self._verify_btn.setFixedHeight(36)
        self._verify_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._verify_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._verify_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {_ACC}, stop:1 {_ACC2});
                color: white; border: none; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}
            QPushButton:disabled {{ background: {_CARD2}; color: {_MUTE}; }}
        """)
        _glow(self._verify_btn, _ACC, 14)
        self._verify_btn.clicked.connect(self._verify_key_submit)
        self._key_input.returnPressed.connect(self._verify_key_submit)
        lay.addWidget(self._verify_btn)

        lay.addStretch()
        return page

    # ── Tab 2: Email OTP Page ──

    def _create_email_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        cfg = load_config()
        email = cfg.get("recovery_email", "").strip()

        if not email:
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background: {_CARD2}; border: 1px dashed {_BORD};
                    border-radius: 8px; padding: 10px;
                }}""")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            bl.setSpacing(4)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            no_lbl = QLabel("✉️  No Recovery Email Configured")
            no_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            no_lbl.setStyleSheet(f"color: #fca5a5; background: transparent;")
            bl.addWidget(no_lbl)

            desc = QLabel(
                "You haven't set up a recovery email yet. Use your Master "
                "Recovery Key, or register an email in Control Panel settings."
            )
            desc.setFont(QFont("Segoe UI", 8))
            desc.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc.setWordWrap(True)
            bl.addWidget(desc)

            switch_btn = QPushButton("← Switch to Recovery Key")
            switch_btn.setFixedHeight(30)
            switch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            switch_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            switch_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_ACC}; color: white; border: none;
                    border-radius: 6px; padding: 0 14px; margin-top: 4px;
                }}
                QPushButton:hover {{ background: {_ACC2}; }}""")
            switch_btn.clicked.connect(lambda: self._switch_tab("key"))
            bl.addWidget(switch_btn)

            lay.addWidget(box)
            lay.addStretch()
            return page

        # Registered email exists
        sub = QLabel("Send a 6-digit verification code to your registered email address:")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # Email Card Pill
        em_box = QFrame()
        em_box.setObjectName("em_box")
        em_box.setFixedHeight(36)
        em_box.setStyleSheet(f"""
            .QFrame#em_box {{
                background: {_CARD2};
                border: 1px solid {_BORD};
                border-radius: 8px;
            }}
        """)
        ebl = QHBoxLayout(em_box)
        ebl.setContentsMargins(10, 0, 8, 0)
        em_lbl = QLabel(f"🛡️  {mask_email(email)}")
        em_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        em_lbl.setStyleSheet("color: #c4b5fd; background: transparent; border: none;")
        ebl.addWidget(em_lbl)
        ebl.addStretch()

        self._send_otp_btn = QPushButton("⚡ Send Code")
        self._send_otp_btn.setFixedHeight(26)
        self._send_otp_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._send_otp_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._send_otp_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}
            QPushButton:disabled {{ background: #2a2545; color: {_MUTE}; }}""")
        self._send_otp_btn.clicked.connect(lambda: self._trigger_send_otp(email))
        ebl.addWidget(self._send_otp_btn)
        lay.addWidget(em_box)

        self._email_status = QLabel("")
        self._email_status.setFont(QFont("Segoe UI", 8))
        self._email_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        self._email_status.setWordWrap(True)
        lay.addWidget(self._email_status)

        # Proactively check daily OTP quota
        can_send_otp, cur_otp_count, max_otp_limit = check_daily_otp_limit("reset_password")
        if not can_send_otp:
            self._send_otp_btn.setEnabled(False)
            self._email_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._email_status.setText(f"✗ Daily email code limit reached ({cur_otp_count}/{max_otp_limit}). Use your Recovery Key.")

        # OTP Entry
        ol = QLabel("Enter 6-Digit Code")
        ol.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        ol.setStyleSheet(f"color: {_ACC2}; background: transparent;")
        lay.addWidget(ol)

        self._otp_input = QLineEdit()
        self._otp_input.setMaxLength(6)
        self._otp_input.setPlaceholderText("· · · · · ·")
        self._otp_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._otp_input.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        self._otp_input.setFixedHeight(36)
        self._otp_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                letter-spacing: 6px;
            }}
            QLineEdit:focus {{
                border: 1px solid {_ACC2};
                background: #14102c;
            }}""")
        lay.addWidget(self._otp_input)

        self._otp_err_lbl = QLabel("")
        self._otp_err_lbl.setFont(QFont("Segoe UI", 8))
        self._otp_err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
        self._otp_err_lbl.setWordWrap(True)
        lay.addWidget(self._otp_err_lbl)

        self._verify_otp_btn = QPushButton("Verify Code →")
        self._verify_otp_btn.setFixedHeight(36)
        self._verify_otp_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._verify_otp_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._verify_otp_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {_ACC}, stop:1 {_ACC2});
                color: white; border: none; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}
            QPushButton:disabled {{ background: {_CARD2}; color: {_MUTE}; }}
        """)
        _glow(self._verify_otp_btn, _ACC, 14)
        self._verify_otp_btn.clicked.connect(self._verify_otp_submit)
        self._otp_input.returnPressed.connect(self._verify_otp_submit)
        lay.addWidget(self._verify_otp_btn)

        lay.addStretch()
        return page

    def _trigger_send_otp(self, email):
        is_locked, wait_s = check_locked_out("Account Recovery")
        if is_locked:
            self._start_countdown(wait_s)
            return

        can_send_otp, cur_otp_count, max_otp_limit = check_daily_otp_limit("reset_password")
        if not can_send_otp:
            self._send_otp_btn.setEnabled(False)
            self._email_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._email_status.setText(f"✗ Daily email code limit reached ({cur_otp_count}/{max_otp_limit} sent today). Please try again tomorrow or use your Master Recovery Key.")
            return

        code = generate_otp_code()
        self._pending_otp = code
        self._otp_expiry = time.time() + 600  # 10 minutes

        self._send_otp_btn.setEnabled(False)
        self._send_otp_btn.setText("Sending...")
        self._email_status.setStyleSheet(f"color: #c4b5fd; background: transparent;")
        self._email_status.setText("⏳ Connecting to server and dispatching verification email...")

        def _worker_thread():
            ok, msg = send_recovery_otp_worker(email, code, purpose="reset_password")
            self._otp_result_signal.emit(ok, msg)

        threading.Thread(target=_worker_thread, daemon=True).start()

    def _on_otp_dispatched(self, ok, msg):
        if not self.isVisible():
            return
        if ok:
            self._email_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            self._email_status.setText("✓ Verification code sent! Check your inbox (or Spam folder).")
            self._start_resend_cooldown(60)
        else:
            self._email_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._email_status.setText(f"✗ {msg}")
            if hasattr(self, "_send_otp_btn"):
                self._send_otp_btn.setEnabled(True)
                self._send_otp_btn.setText("⚡  Retry")

    def _start_resend_cooldown(self, seconds):
        if not hasattr(self, "_send_otp_btn"):
            return
        self._send_otp_btn.setEnabled(False)
        cd = [seconds]
        def _resend_tick():
            if not self.isVisible() or not hasattr(self, "_send_otp_btn"):
                return
            r = cd[0]
            if r <= 0:
                self._send_otp_btn.setEnabled(True)
                self._send_otp_btn.setText("⚡  Resend Code")
                return
            self._send_otp_btn.setText(f"Wait {r}s")
            cd[0] -= 1
            QTimer.singleShot(1000, _resend_tick)
        _resend_tick()

    def _verify_otp_submit(self):
        is_locked, wait_s = check_locked_out("Account Recovery")
        if is_locked:
            self._start_countdown(wait_s)
            return

        if not self._pending_otp:
            self._otp_err_lbl.setText("Please click 'Send Code' first.")
            return

        if time.time() > self._otp_expiry:
            self._otp_err_lbl.setText("Verification code has expired. Please request a new code.")
            return

        entered = self._otp_input.text().strip()
        if not entered:
            self._otp_err_lbl.setText("Please enter the 6-digit code.")
            return

        if entered == self._pending_otp:
            play_unlock_sound()
            reset_attempt_state("Account Recovery")
            log_security_event("otp_verified", "Account Recovery", "Email OTP code validated successfully")
            self._show_step_2_new_password()
        else:
            play_error_sound()
            state = record_wrong_attempt("Account Recovery", event_type="wrong_otp")
            self._otp_input.clear()
            if state["locked"]:
                self._start_countdown(state["wait"])
            else:
                rem = PENALTY_THRES - state["count"]
                if rem > 0:
                    self._otp_err_lbl.setText(f"Invalid code. {rem} attempt(s) remaining.")
                else:
                    self._otp_err_lbl.setText("Invalid verification code.")
            self._otp_input.setFocus()

    def _update_countdown_ui(self, r):
        msg = f"🔒 Locked out due to wrong attempts. Please wait {r}s."
        wait_text = f"⏳ Wait {r}s"
        if self._active_tab == "key":
            if _is_valid_widget(getattr(self, "_key_input", None)):
                self._key_input.setEnabled(False)
            if _is_valid_widget(getattr(self, "_verify_btn", None)):
                self._verify_btn.setEnabled(False)
                self._verify_btn.setText(wait_text)
            if _is_valid_widget(getattr(self, "_err_lbl", None)):
                self._err_lbl.setText(msg)
        else:
            if _is_valid_widget(getattr(self, "_otp_input", None)):
                self._otp_input.setEnabled(False)
            if _is_valid_widget(getattr(self, "_verify_otp_btn", None)):
                self._verify_otp_btn.setEnabled(False)
                self._verify_otp_btn.setText(wait_text)
            if _is_valid_widget(getattr(self, "_send_otp_btn", None)):
                self._send_otp_btn.setEnabled(False)
            if _is_valid_widget(getattr(self, "_otp_err_lbl", None)):
                self._otp_err_lbl.setText(msg)

    def _restore_countdown_ui(self):
        if self._active_tab == "key":
            if _is_valid_widget(getattr(self, "_key_input", None)):
                self._key_input.setEnabled(True)
                self._key_input.setFocus()
            if _is_valid_widget(getattr(self, "_verify_btn", None)):
                self._verify_btn.setEnabled(True)
                self._verify_btn.setText("Verify Recovery Key →")
            if _is_valid_widget(getattr(self, "_err_lbl", None)):
                self._err_lbl.setText("")
        else:
            if _is_valid_widget(getattr(self, "_otp_input", None)):
                self._otp_input.setEnabled(True)
            if _is_valid_widget(getattr(self, "_verify_otp_btn", None)):
                self._verify_otp_btn.setEnabled(True)
                self._verify_otp_btn.setText("Verify Code →")
            if _is_valid_widget(getattr(self, "_send_otp_btn", None)):
                self._send_otp_btn.setEnabled(True)
            if _is_valid_widget(getattr(self, "_otp_err_lbl", None)):
                self._otp_err_lbl.setText("")

    def _start_countdown(self, seconds):
        self._countdown_seconds = seconds
        self._update_countdown_ui(seconds)
        cd = [seconds]
        def _tick():
            if not self.isVisible():
                return
            r = cd[0]
            if r <= 0:
                self._countdown_seconds = 0
                self._restore_countdown_ui()
                return
            self._countdown_seconds = r
            self._update_countdown_ui(r)
            cd[0] -= 1
            QTimer.singleShot(1000, _tick)
        _tick()

    def _verify_key_submit(self):
        is_locked, wait_s = check_locked_out("Account Recovery")
        if is_locked:
            self._start_countdown(wait_s)
            return

        entered = self._key_input.text().strip()
        if not entered:
            self._err_lbl.setText("Please enter your Recovery Key.")
            return

        cfg = load_config()
        stored_hash = cfg.get("recovery_key_hash", "")
        key_enabled = bool(cfg.get("recovery_key_enabled", True if stored_hash else False))

        if not (stored_hash and key_enabled):
            self._err_lbl.setText("Recovery Key method is disabled or not configured.")
            return

        if verify_recovery_key(entered, stored_hash):
            play_unlock_sound()
            reset_attempt_state("Account Recovery")
            log_security_event("recovery_key_verified", "Account Recovery", "Recovery key validated successfully")
            self._verified_key = entered
            self._show_step_2_new_password()
        else:
            play_error_sound()
            state = record_wrong_attempt("Account Recovery", event_type="wrong_recovery_key")
            self._key_input.clear()
            if state["locked"]:
                self._start_countdown(state["wait"])
            else:
                rem = PENALTY_THRES - state["count"]
                if rem > 0:
                    self._err_lbl.setText(f"Invalid Recovery Key. {rem} attempt(s) remaining.")
                else:
                    self._err_lbl.setText("Invalid Recovery Key.")
            self._key_input.setFocus()

    # ═════════════════════════════════════════════════════════════════════
    # Step 2: Set New Password
    # ═════════════════════════════════════════════════════════════════════

    def _show_step_2_new_password(self):
        self._clear_container()
        self._step = 2

        h = QLabel("Set New Master Password")
        h.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        h.setStyleSheet(f"color: {_GREEN}; background: transparent;")
        self._container_lay.addWidget(h)

        sub = QLabel("Recovery Key verified! Choose a strong master password to secure your apps.")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sub.setWordWrap(True)
        self._container_lay.addWidget(sub)

        _pw_style = f"""
            QLineEdit {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 0 12px; font-size: 9pt;
            }}
            QLineEdit:focus {{
                border: 1px solid {_ACC2};
                background: #14102c;
            }}"""

        nl = QLabel("New Password")
        nl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        nl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        self._container_lay.addWidget(nl)

        self._new_pw = QLineEdit()
        self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pw.setFixedHeight(34)
        self._new_pw.setStyleSheet(_pw_style)
        self._container_lay.addWidget(self._new_pw)

        cnl = QLabel("Confirm New Password")
        cnl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        cnl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        self._container_lay.addWidget(cnl)

        self._con_pw = QLineEdit()
        self._con_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._con_pw.setFixedHeight(34)
        self._con_pw.setStyleSheet(_pw_style)
        self._container_lay.addWidget(self._con_pw)

        self._pw_err = QLabel("")
        self._pw_err.setFont(QFont("Segoe UI", 8))
        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        self._container_lay.addWidget(self._pw_err)

        save_btn = QPushButton("✓  Save Password && Generate New Key")
        save_btn.setFixedHeight(36)
        save_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #16a34a, stop:1 {_GREEN});
                color: #05160c; border: none; border-radius: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #34d399; }}
        """)
        _glow(save_btn, _GREEN, 14)
        save_btn.clicked.connect(self._save_new_password_submit)
        self._new_pw.returnPressed.connect(self._save_new_password_submit)
        self._con_pw.returnPressed.connect(self._save_new_password_submit)
        self._container_lay.addWidget(save_btn)

        self._container_lay.addStretch()
        self._new_pw.setFocus()

    def _save_new_password_submit(self):
        n = self._new_pw.text()
        c = self._con_pw.text()
        if len(n) < 4:
            self._pw_err.setText("Password must be at least 4 characters.")
            return
        if n != c:
            self._pw_err.setText("Passwords do not match.")
            return

        # Generate fresh recovery key
        self._new_key = generate_recovery_key()
        cfg = load_config()
        cfg["password_hash"] = hash_pw(n)
        cfg["recovery_key_hash"] = hash_recovery_key(self._new_key)
        cfg["recovery_key_enabled"] = True
        save_config(cfg)
        self._password_reset_done = True

        via_method = "Master Recovery Key" if self._active_tab == "key" else f"Email OTP ({mask_email(cfg.get('recovery_email', ''))})"
        log_security_event("password_reset", "Account Recovery", f"Master password reset via {via_method}")
        self._show_step_3_new_key()

    # ═════════════════════════════════════════════════════════════════════
    # Step 3: Display New Recovery Key
    # ═════════════════════════════════════════════════════════════════════

    def _show_step_3_new_key(self):
        self._clear_container()
        self._step = 3

        h = QLabel("🎉 Password Successfully Reset!")
        h.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        h.setStyleSheet(f"color: {_GREEN}; background: transparent;")
        self._container_lay.addWidget(h)

        sub = QLabel("For your security, a new Emergency Recovery Key has been generated. Save it now:")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sub.setWordWrap(True)
        self._container_lay.addWidget(sub)

        # Key display box
        box = QFrame()
        box.setObjectName("key_box")
        box.setStyleSheet(f"""
            .QFrame#key_box {{
                background: {_CARD2};
                border: 1px solid {_BORD};
                border-radius: 8px;
            }}
        """)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        key_lbl = QLabel(self._new_key)
        key_lbl.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        key_lbl.setStyleSheet("color: #c4b5fd; background: transparent; letter-spacing: 1.5px; border: none;")
        key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(key_lbl)
        self._container_lay.addWidget(box)

        # Action buttons: Copy & Save
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background: transparent;")
        btn_row = QHBoxLayout(btn_bar)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)

        copy_btn = QPushButton("📋  Copy Key")
        copy_btn.setFixedHeight(32)
        copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
            }}
            QPushButton:hover {{ background: #251e40; border-color: {_ACC2}; }}""")
        copy_btn.clicked.connect(lambda: self._copy_key(copy_btn))
        btn_row.addWidget(copy_btn, 1)

        save_txt_btn = QPushButton("💾  Save as File")
        save_txt_btn.setFixedHeight(32)
        save_txt_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_txt_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        save_txt_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
            }}
            QPushButton:hover {{ background: #251e40; border-color: {_ACC2}; }}""")
        save_txt_btn.clicked.connect(self._save_to_file)
        btn_row.addWidget(save_txt_btn, 1)

        self._container_lay.addWidget(btn_bar)

        finish_btn = QPushButton("✓  Finish && Continue")
        finish_btn.setFixedHeight(36)
        finish_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        finish_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        finish_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {_ACC}, stop:1 {_ACC2});
                color: white; border: none; border-radius: 8px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}
        """)
        _glow(finish_btn, _ACC, 14)
        finish_btn.clicked.connect(self._finish)
        self._container_lay.addWidget(finish_btn)

        self._container_lay.addStretch()

    def _copy_key(self, btn):
        clip = QApplication.clipboard()
        if clip and self._new_key:
            clip.setText(self._new_key)
            btn.setText("✓  Copied!")
            QTimer.singleShot(2000, lambda: btn.setText("📋  Copy Key"))

    def _save_to_file(self):
        if not self._new_key:
            return
        import os
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop_dir):
            desktop_dir = os.path.expanduser("~")
        default_target = os.path.join(desktop_dir, "DeskWarden_Recovery_Key.txt")

        with suppress_faulthandler():
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Emergency Recovery Key", default_target,
                "Text File (*.txt)"
            )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("DeskWarden Emergency Recovery Key\n")
                    f.write("=" * 40 + "\n\n")
                    f.write(f"Recovery Key: {self._new_key}\n\n")
                    f.write("Keep this key safe. You can use it to reset your\n")
                    f.write("DeskWarden master password if you ever forget it.\n")
            except Exception:
                pass

    def add_on_success_callback(self, cb):
        if cb and callable(cb):
            if not hasattr(self, "_callbacks"):
                self._callbacks = []
            self._callbacks.append(cb)

    def _trigger_success_once(self):
        callbacks = []
        if self._on_success:
            callbacks.append(self._on_success)
            self._on_success = None
        if hasattr(self, "_callbacks"):
            callbacks.extend(self._callbacks)
            self._callbacks = []
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                dlog("WARNING", f"_trigger_success_once callback error: {e}")

    def _on_close_clicked(self):
        if self._password_reset_done:
            self._finish()
        else:
            self.close()

    def _release_singleton_lock(self):
        if hasattr(self, "_mutex_handle") and self._mutex_handle:
            try:
                if _kernel32:
                    _kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None
        if getattr(RecoveryDialog, "_current_active_instance", None) is self:
            RecoveryDialog._current_active_instance = None

    def shake(self):
        """Plays a gentle horizontal shake animation to indicate window is already active."""
        if getattr(self, "_is_shaking", False):
            return
        self._is_shaking = True
        orig_pos = self.pos()
        offsets = [-10, 10, -8, 8, -4, 4, 0]
        delay = 0
        for i, dx in enumerate(offsets):
            is_last = (i == len(offsets) - 1)
            def _apply(x=orig_pos.x() + dx, y=orig_pos.y(), done=is_last):
                self.move(x, y)
                if done:
                    self._is_shaking = False
            QTimer.singleShot(delay, _apply)
            delay += 35

    def show(self):
        if getattr(self, "_is_duplicate", False):
            bring_existing_recovery_to_front()
            return
        super().show()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if getattr(self, "_drag_pos", None) is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()
        else:
            super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.raise_()
        self.activateWindow()
        try:
            self.setWindowTitle(RECOVERY_WINDOW_TITLE)
            if _user32:
                hwnd = int(self.winId())
                _user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                _user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def closeEvent(self, ev):
        if self._password_reset_done:
            self._trigger_success_once()
        elif hasattr(self, "_on_close") and callable(self._on_close):
            try:
                self._on_close()
            except Exception:
                pass
        self._release_singleton_lock()
        super().closeEvent(ev)

    def _finish(self):
        self._release_singleton_lock()
        self.close()
        self._trigger_success_once()


def is_recovery_available(cfg: dict = None) -> bool:
    """Returns True if at least one recovery method (Recovery Key or Recovery Email)
    is configured and enabled in the settings."""
    if cfg is None:
        cfg = load_config()
    key_hash = cfg.get("recovery_key_hash", "").strip()
    key_enabled = bool(cfg.get("recovery_key_enabled", True if key_hash else False))
    email = cfg.get("recovery_email", "").strip()
    email_enabled = bool(cfg.get("recovery_email_enabled", True if email else False))

    key_avail = bool(key_hash and key_enabled)
    email_avail = bool(email and email_enabled)
    return bool(key_avail or email_avail)


def show_recovery_modal(on_success=None, on_close=None, source_context=None, parent=None):
    """Convenience helper to instantiate and display the RecoveryDialog with system-wide single-instance enforcement."""
    cfg = load_config()
    if not is_recovery_available(cfg):
        dlog("INFO", "show_recovery_modal: no recovery methods enabled or configured")
        return None

    inst = getattr(RecoveryDialog, "_current_active_instance", None)
    if inst is not None and inst.isVisible():
        if on_success:
            inst.add_on_success_callback(on_success)
        if source_context == "lock_screen" and getattr(inst, "_source_context", None) != "lock_screen":
            inst.shake()
            return None
        inst.raise_()
        inst.activateWindow()
        inst.shake()
        return inst

    if _user32:
        hwnd = _user32.FindWindowW(None, RECOVERY_WINDOW_TITLE)
        if hwnd and _user32.IsWindow(hwnd) and _user32.IsWindowVisible(hwnd):
            flash_existing_window(hwnd)
            if source_context == "lock_screen":
                return None
            try:
                _user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return None

    dlg = RecoveryDialog(on_success=on_success, on_close=on_close, source_context=source_context, parent=parent)
    if getattr(dlg, "_is_duplicate", False):
        return getattr(RecoveryDialog, "_current_active_instance", None)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    try:
        if _user32:
            hwnd = int(dlg.winId())
            _user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            _user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return dlg


show_recovery_dialog = show_recovery_modal

