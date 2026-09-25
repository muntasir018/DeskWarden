"""
DeskWarden - ui/control_panel_ui/settings_io.py
"""

import os
import json
import time
import threading
import datetime as _dt

from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QLabel, QPushButton, QWidget,
    QVBoxLayout, QHBoxLayout, QFrame, QLineEdit,
    QGraphicsDropShadowEffect, QApplication, QStackedWidget, QStyle,
)
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QFont, QCursor, QPixmap, QColor, QPainter, QPen, QBrush, QLinearGradient, QPolygonF
)

from ...core.config import load_config, save_config
from ...core.security import (
    load_security_log, _save_security_log, hash_pw,
    verify_recovery_key, generate_otp_code, mask_email,
    send_recovery_otp_worker, log_security_event, check_daily_otp_limit,
)
from ...core.backup_crypto import (
    pack_backup_container, unpack_backup_container, unpack_safe_backup, inspect_backup_header,
    is_deskwarden_backup, BackupAuthError, InvalidBackupFormatError, decrypt_with_safe_cipher,
)
from ...core.process_utils import set_autostart
from ...core.paths import asset_path
from ...core.logging_utils import suppress_faulthandler

from .theme import (
    _RED, _GREEN, _MUTE, _FG, _CARD, _CARD2, _BORD, _ACC, _ACC2, _ACC3,
)
from .widgets import _Card


class _ImportBackupDialog(QDialog):
    """
    Fixed, non-movable modal dialog styled in the classic DeskWarden warning dialog aesthetic.
    Authenticates and decrypts an authentic .deskwarden backup container via:
    1. Master Password (PBKDF2 + AES-256-GCM)
    2. Master Recovery Key (PBKDF2 + AES-256-GCM)
    3. Email OTP (Cloudflare Worker proxy with Daily Rate Limiting)
    Allows Safe Import (apps & preferences only) or Full Restore (credentials & all settings).
    """
    _otp_result_signal = pyqtSignal(bool, str)

    def __init__(self, raw_bytes: bytes, header_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(450, 205)

        self._raw_bytes = raw_bytes
        self._header_info = header_info
        self._meta = header_info.get("metadata", {})
        self._action = None  # "safe" or "full"
        self._target_action = "full"
        self._data = None

        self._backup_has_pw = header_info.get("has_pw_slot", True)
        self._backup_has_key = header_info.get("has_key_slot", False)
        self._backup_has_email = header_info.get("has_email_slot", False)
        self._backup_email = self._meta.get("masked_email", "").strip()
        
        # Resolve recovery email: decrypt via safe cipher or fallback to legacy field
        enc_em = self._meta.get("enc_recovery_email", "").strip()
        if enc_em:
            self._real_email = decrypt_with_safe_cipher(enc_em)
        else:
            self._real_email = self._meta.get("recovery_email", "").strip()

        self._pending_otp = None
        self._otp_expiry = 0
        self._otp_result_signal.connect(self._on_otp_dispatched)

        self._build_ui()

    def showEvent(self, ev):
        super().showEvent(ev)
        p = self.parent()
        if p is not None:
            cx = p.x() + (p.width() - self.width()) // 2
            cy = p.y() + (p.height() - self.height()) // 2
            self.move(max(0, cx), max(0, cy))
        else:
            qapp = QApplication.instance()
            if qapp:
                sg = qapp.primaryScreen().geometry()
                self.move(
                    sg.x() + (sg.width() - self.width()) // 2,
                    sg.y() + (sg.height() - self.height()) // 2,
                )

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(ev)

    def get_action(self) -> str | None:
        return self._action

    def get_data(self) -> dict | None:
        return self._data

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Card with soft translucent purple accent border and drop shadow
        card = _Card(self, bg=_CARD, border="#558b5cf6", radius=12)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 16)
        cl.setSpacing(10)

        # ── QStackedWidget for glitch-free transitions ────────────────────────
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        cl.addWidget(self._stack, 1)

        self._page_choice = self._create_choice_page()
        self._page_pw = self._create_pw_page()
        self._page_key = self._create_key_page()
        self._page_otp = self._create_otp_page()

        self._stack.addWidget(self._page_choice)  # 0
        self._stack.addWidget(self._page_pw)      # 1
        self._stack.addWidget(self._page_key)     # 2
        self._stack.addWidget(self._page_otp)     # 3

        self._stack.setCurrentWidget(self._page_choice)

    def _start_unlock(self, action: str):
        self._target_action = action
        if action == "safe":
            self._pw_sub.setText("Enter backup password to unlock and import apps:")
            self._pw_vbtn.setText("Import Apps")
        else:
            self._pw_sub.setText("Enter this backup's password to replace current credentials:")
            self._pw_vbtn.setText("Full Restore")
        self._go_page(self._page_pw)

    def _do_safe_import(self):
        try:
            self._data = unpack_safe_backup(self._raw_bytes)
            self._action = "safe"
            self.accept()
        except Exception:
            # Fallback if safe decryption fails (e.g. legacy container)
            self._start_unlock("safe")

    # ── Page 0: Choice (Classic Warning Vibe) ─────────────────────────────────
    def _create_choice_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        # Top section: Warning icon on left, Title + Text on right
        top_row = QHBoxLayout(); top_row.setSpacing(14); top_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        warn_icon = QLabel()
        pm = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(40, 40)
        warn_icon.setPixmap(pm)
        warn_icon.setFixedSize(40, 40)
        top_row.addWidget(warn_icon)

        txt_lay = QVBoxLayout(); txt_lay.setSpacing(5)
        title_lbl = QLabel("Password-Protected Backup")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
        txt_lay.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Do you remember the previous password?<br><br>"
            "Choose <b>Safe Import</b> to restore locked applications and preferences directly without entering password, or <b>Full Restore</b> to restore everything including previous credentials."
        )
        desc_lbl.setFont(QFont("Segoe UI", 8))
        desc_lbl.setStyleSheet(f"color: {_FG}; background: transparent; line-height: 135%;")
        desc_lbl.setWordWrap(True)
        txt_lay.addWidget(desc_lbl)

        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row, 1)

        # Bottom row: Native DeskWarden buttons matching original classic dialog
        btn_row = QHBoxLayout(); btn_row.setSpacing(8); btn_row.setAlignment(Qt.AlignmentFlag.AlignRight)

        btn_style = f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 6px 14px; min-width: 80px; font-size: 8pt;
            }}
            QPushButton:hover {{ background: #1f1c34; border-color: {_ACC3}; }}
        """

        safe_btn = QPushButton("Safe Import")
        safe_btn.setFixedHeight(30)
        safe_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        safe_btn.setFont(QFont("Segoe UI", 8))
        safe_btn.setStyleSheet(btn_style)
        safe_btn.setToolTip("Restores locked applications and preferences directly without asking for password.")
        safe_btn.clicked.connect(self._do_safe_import)
        btn_row.addWidget(safe_btn)

        full_btn = QPushButton("Full Restore")
        full_btn.setFixedHeight(30)
        full_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        full_btn.setFont(QFont("Segoe UI", 8))
        full_btn.setStyleSheet(btn_style)
        full_btn.setToolTip("Restores all settings, including previous password and recovery system.")
        full_btn.clicked.connect(lambda: self._start_unlock("full"))
        btn_row.addWidget(full_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(30)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setFont(QFont("Segoe UI", 8))
        cancel_btn.setStyleSheet(btn_style)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        wl.addLayout(btn_row)
        return w

    # ── Page 1: Password Verification ────────────────────────────────────────
    def _create_pw_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        top_row = QHBoxLayout(); top_row.setSpacing(14); top_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        key_ico = QLabel("🔑")
        key_ico.setFont(QFont("Segoe UI Emoji", 14))
        top_row.addWidget(key_ico)

        txt_lay = QVBoxLayout(); txt_lay.setSpacing(2)
        hdr = QLabel("Verify Master Password")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #c4b5fd; background: transparent;")
        txt_lay.addWidget(hdr)

        self._pw_sub = QLabel("Enter this backup's password to replace current credentials:")
        self._pw_sub.setFont(QFont("Segoe UI", 8))
        self._pw_sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        txt_lay.addWidget(self._pw_sub)
        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row)

        wl.addSpacing(2)
        row = QHBoxLayout(); row.setSpacing(6)
        self._pw_in = QLineEdit()
        self._pw_in.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_in.setPlaceholderText("Enter backup's master password")
        self._pw_in.setFixedHeight(32)
        self._pw_in.setStyleSheet(f"""
            QLineEdit {{
                background: #100c1a; color: {_FG}; border: 1px solid {_BORD};
                border-radius: 8px; padding: 0 10px; font-size: 8pt;
            }}
            QLineEdit:focus {{ border-color: {_ACC2}; }}""")
        row.addWidget(self._pw_in, 1)

        self._pw_vbtn = QPushButton("Restore")
        self._pw_vbtn.setFixedHeight(32)
        self._pw_vbtn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._pw_vbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pw_vbtn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 8px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        row.addWidget(self._pw_vbtn)
        wl.addLayout(row)

        self._pw_err = QLabel("")
        self._pw_err.setFont(QFont("Segoe UI", 7))
        self._pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        wl.addWidget(self._pw_err)

        def _verify():
            entered = self._pw_in.text()
            if not entered:
                self._pw_err.setText("✗ Please enter password.")
                return
            try:
                self._data = unpack_backup_container(self._raw_bytes, password=entered)
                self._action = self._target_action
                self.accept()
            except BackupAuthError:
                log_security_event("wrong_password", "Backup Decryption", "Incorrect password entered for backup")
                self._pw_err.setText("✗ Incorrect password for this backup.")
                self._pw_in.clear()
                self._pw_in.setFocus()
            except Exception as e:
                self._pw_err.setText(f"✗ Decryption error: {e}")

        self._pw_vbtn.clicked.connect(_verify)
        self._pw_in.returnPressed.connect(_verify)

        wl.addStretch()
        alt_row = QHBoxLayout(); alt_row.setSpacing(10)
        back_btn = QPushButton("← Back")
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {_MUTE}; border: none; font-size: 8pt; }} QPushButton:hover {{ color: {_FG}; }}")
        back_btn.clicked.connect(lambda: self._go_page(self._page_choice))
        alt_row.addWidget(back_btn)
        alt_row.addStretch()

        if self._backup_has_key:
            key_link = QPushButton("⚡ Use Recovery Key")
            key_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            key_link.setStyleSheet(f"QPushButton {{ background: transparent; color: #a78bfa; border: none; font-size: 8pt; text-decoration: none; }} QPushButton:hover {{ color: white; }}")
            key_link.clicked.connect(lambda: self._go_page(self._page_key))
            alt_row.addWidget(key_link)

        if self._backup_has_email:
            em_link = QPushButton("✉️ Use Email OTP")
            em_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            em_link.setStyleSheet(f"QPushButton {{ background: transparent; color: #a78bfa; border: none; font-size: 8pt; text-decoration: none; }} QPushButton:hover {{ color: white; }}")
            em_link.clicked.connect(lambda: self._go_page(self._page_otp))
            alt_row.addWidget(em_link)

        wl.addLayout(alt_row)
        return w

    # ── Page 2: Recovery Key Verification ────────────────────────────────────
    def _create_key_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        top_row = QHBoxLayout(); top_row.setSpacing(14); top_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        key_ico = QLabel("⚡")
        key_ico.setFont(QFont("Segoe UI Emoji", 18))
        key_ico.setFixedSize(40, 40)
        key_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(key_ico)

        txt_lay = QVBoxLayout(); txt_lay.setSpacing(2)
        hdr = QLabel("Verify with Recovery Key")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #c4b5fd; background: transparent;")
        txt_lay.addWidget(hdr)

        sub = QLabel("Enter the 16-character recovery key from this backup:")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        txt_lay.addWidget(sub)
        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row)

        wl.addSpacing(2)
        row = QHBoxLayout(); row.setSpacing(6)
        self._key_in = QLineEdit()
        self._key_in.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self._key_in.setFixedHeight(32)
        self._key_in.setStyleSheet(f"""
            QLineEdit {{
                background: #100c1a; color: {_FG}; border: 1px solid {_BORD};
                border-radius: 8px; padding: 0 10px; font-family: Consolas; font-size: 8pt;
            }}
            QLineEdit:focus {{ border-color: {_ACC2}; }}""")
        row.addWidget(self._key_in, 1)

        vbtn = QPushButton("Restore")
        vbtn.setFixedHeight(32)
        vbtn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        vbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        vbtn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 8px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        row.addWidget(vbtn)
        wl.addLayout(row)

        self._key_err = QLabel("")
        self._key_err.setFont(QFont("Segoe UI", 7))
        self._key_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        wl.addWidget(self._key_err)

        def _verify_k():
            entered = self._key_in.text().strip()
            if not entered:
                self._key_err.setText("✗ Please enter recovery key.")
                return
            try:
                self._data = unpack_backup_container(self._raw_bytes, recovery_key=entered)
                log_security_event("recovery_key_verified", "Backup Decryption", "Recovery key verified for backup restore")
                self._action = self._target_action
                self.accept()
            except BackupAuthError:
                log_security_event("wrong_recovery_key", "Backup Decryption", "Incorrect recovery key entered for backup")
                self._key_err.setText("✗ Invalid recovery key.")
                self._key_in.clear()
                self._key_in.setFocus()
            except Exception as e:
                self._key_err.setText(f"✗ Decryption error: {e}")

        vbtn.clicked.connect(_verify_k)
        self._key_in.returnPressed.connect(_verify_k)

        wl.addStretch()
        alt_row = QHBoxLayout(); alt_row.setSpacing(10)
        back_btn = QPushButton("← Use Password")
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {_MUTE}; border: none; font-size: 8pt; }} QPushButton:hover {{ color: {_FG}; }}")
        back_btn.clicked.connect(lambda: self._go_page(self._page_pw))
        alt_row.addWidget(back_btn)
        alt_row.addStretch()

        if self._backup_has_email:
            em_link = QPushButton("✉️ Use Email OTP")
            em_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            em_link.setStyleSheet(f"QPushButton {{ background: transparent; color: #a78bfa; border: none; font-size: 8pt; text-decoration: none; }} QPushButton:hover {{ color: white; }}")
            em_link.clicked.connect(lambda: self._go_page(self._page_otp))
            alt_row.addWidget(em_link)

        wl.addLayout(alt_row)
        return w

    # ── Page 3: Email OTP Verification ───────────────────────────────────────
    def _create_otp_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        top_row = QHBoxLayout(); top_row.setSpacing(14); top_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        em_ico = QLabel("✉️")
        em_ico.setFont(QFont("Segoe UI Emoji", 18))
        em_ico.setFixedSize(40, 40)
        em_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(em_ico)

        txt_lay = QVBoxLayout(); txt_lay.setSpacing(2)
        hdr = QLabel("Verify with Email OTP")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #c4b5fd; background: transparent;")
        txt_lay.addWidget(hdr)

        masked = self._backup_email if self._backup_email else "No email"
        sub = QLabel(f"Send 6-digit code to: <b style='color:{_FG};'>{masked}</b>")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        txt_lay.addWidget(sub)
        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row)

        send_row = QHBoxLayout(); send_row.setSpacing(8)
        self._send_btn = QPushButton("⚡ Send Verification Code")
        self._send_btn.setFixedHeight(28)
        self._send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._send_btn.setFont(QFont("Segoe UI", 8))
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: #c4b5fd; border: 1px solid {_BORD};
                border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #1e1a35; border-color: {_ACC2}; }}
            QPushButton:disabled {{ color: {_MUTE}; }}""")
        send_row.addWidget(self._send_btn)

        self._otp_status = QLabel("")
        self._otp_status.setFont(QFont("Segoe UI", 7))
        self._otp_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        send_row.addWidget(self._otp_status, 1)
        wl.addLayout(send_row)

        # Proactively check daily OTP quota
        can_send_init, cur_init, max_init = check_daily_otp_limit("import_verify")
        if not can_send_init:
            self._send_btn.setEnabled(False)
            self._otp_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._otp_status.setText(f"Daily limit reached ({cur_init}/{max_init}). Use Password or Key.")

        verify_row = QHBoxLayout(); verify_row.setSpacing(6)
        self._otp_in = QLineEdit()
        self._otp_in.setPlaceholderText("6-digit code")
        self._otp_in.setMaxLength(6)
        self._otp_in.setFixedHeight(32)
        self._otp_in.setStyleSheet(f"""
            QLineEdit {{
                background: #100c1a; color: {_FG}; border: 1px solid {_BORD};
                border-radius: 8px; padding: 0 10px; font-weight: bold; letter-spacing: 2px; font-size: 8pt;
            }}
            QLineEdit:focus {{ border-color: {_ACC2}; }}""")
        verify_row.addWidget(self._otp_in, 1)

        vbtn = QPushButton("Restore")
        vbtn.setFixedHeight(32)
        vbtn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        vbtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        vbtn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 8px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        verify_row.addWidget(vbtn)
        wl.addLayout(verify_row)

        self._otp_err = QLabel("")
        self._otp_err.setFont(QFont("Segoe UI", 7))
        self._otp_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        wl.addWidget(self._otp_err)

        def _send():
            can_send, cur_c, max_l = check_daily_otp_limit("import_verify")
            if not can_send:
                self._send_btn.setEnabled(False)
                self._otp_err.setText(f"✗ Daily email code limit reached ({cur_c}/{max_l} today).")
                return

            code = generate_otp_code()
            self._pending_otp = code
            self._otp_expiry = time.time() + 600
            self._send_btn.setEnabled(False)
            self._otp_status.setStyleSheet(f"color: #c4b5fd; background: transparent;")
            self._otp_status.setText("Sending...")
            self._otp_err.setText("")

            def _w():
                target_email = self._real_email or self._backup_email
                ok, msg = send_recovery_otp_worker(target_email, code, purpose="import_verify")
                self._otp_result_signal.emit(ok, msg)

            threading.Thread(target=_w, daemon=True).start()

        def _verify_o():
            if not self._pending_otp:
                self._otp_err.setText("✗ Click 'Send Verification Code' first.")
                return
            if time.time() > self._otp_expiry:
                self._otp_err.setText("✗ Code expired.")
                return
            if self._otp_in.text().strip() == self._pending_otp:
                try:
                    target_email = self._real_email or self._backup_email
                    self._data = unpack_backup_container(self._raw_bytes, recovery_email=target_email)
                    log_security_event("otp_verified", "Backup Decryption", "Email OTP verified for backup restore")
                    self._action = self._target_action
                    self.accept()
                except Exception as e:
                    self._otp_err.setText(f"✗ Authentication failed: {e}")
            else:
                log_security_event("wrong_otp", "Backup Decryption", "Incorrect email OTP entered for backup")
                self._otp_err.setText("✗ Invalid code.")
                self._otp_in.clear()
                self._otp_in.setFocus()

        self._send_btn.clicked.connect(_send)
        vbtn.clicked.connect(_verify_o)
        self._otp_in.returnPressed.connect(_verify_o)

        alt_row = QHBoxLayout(); alt_row.setSpacing(10)
        back_btn = QPushButton("← Use Password")
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {_MUTE}; border: none; font-size: 8pt; }} QPushButton:hover {{ color: {_FG}; }}")
        back_btn.clicked.connect(lambda: self._go_page(self._page_pw))
        alt_row.addWidget(back_btn)
        alt_row.addStretch()

        if self._backup_has_key:
            key_link = QPushButton("⚡ Use Recovery Key")
            key_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            key_link.setStyleSheet(f"QPushButton {{ background: transparent; color: #a78bfa; border: none; font-size: 8pt; text-decoration: none; }} QPushButton:hover {{ color: white; }}")
            key_link.clicked.connect(lambda: self._go_page(self._page_key))
            alt_row.addWidget(key_link)

        wl.addLayout(alt_row)
        return w

    def _go_page(self, page_widget: QWidget):
        self._stack.setCurrentWidget(page_widget)
        if page_widget == self._page_pw:
            self._pw_err.setText("")
            QTimer.singleShot(40, self._pw_in.setFocus)
        elif page_widget == self._page_key:
            self._key_err.setText("")
            QTimer.singleShot(40, self._key_in.setFocus)
        elif page_widget == self._page_otp:
            self._otp_err.setText("")

    def _on_otp_dispatched(self, ok: bool, msg: str):
        if not self.isVisible():
            return
        if ok:
            target_mask = self._backup_email or "recovery email"
            log_security_event("otp_sent", "Backup Decryption", f"Verification code sent to {target_mask}")
            self._otp_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            self._otp_status.setText("✓ Sent!")
            self._otp_in.setFocus()
            self._start_otp_cooldown(60)
        else:
            self._otp_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._otp_status.setText(f"✗ {msg}")
            if hasattr(self, "_send_btn"):
                self._send_btn.setEnabled(True)
                self._send_btn.setText("⚡ Retry")

    def _start_otp_cooldown(self, seconds: int = 60):
        if not hasattr(self, "_send_btn"):
            return
        self._send_btn.setEnabled(False)
        cd = [seconds]

        def _tick():
            if not self.isVisible() or not hasattr(self, "_send_btn"):
                return
            r = cd[0]
            if r <= 0:
                self._send_btn.setEnabled(True)
                self._send_btn.setText("⚡ Resend Code")
                return
            self._send_btn.setText(f"Wait {r}s")
            cd[0] -= 1
            QTimer.singleShot(1000, _tick)

        _tick()


# ── Custom Export Badge ───────────────────────────────────────────────────────
def _create_export_badge() -> QPixmap:
    pm = QPixmap(40, 40)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg_grad = QLinearGradient(0, 0, 40, 40)
    bg_grad.setColorAt(0.0, QColor("#2e1065"))
    bg_grad.setColorAt(1.0, QColor("#1e1b4b"))
    p.setBrush(QBrush(bg_grad))
    p.setPen(QPen(QColor("#7c3aed"), 1.2))
    p.drawRoundedRect(1, 1, 38, 38, 10, 10)

    # Box base
    p.setPen(QPen(QColor("#c4b5fd"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawRoundedRect(9, 17, 22, 14, 3, 3)

    # Cyan download/save arrow
    p.setPen(QPen(QColor("#38bdf8"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(20, 7, 20, 22)

    arrow = QPolygonF([QPointF(15, 17), QPointF(20, 23), QPointF(25, 17)])
    p.setPen(QPen(QColor("#38bdf8"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline(arrow)

    # Tray line
    p.setPen(QPen(QColor("#a78bfa"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(14, 25, 26, 25)

    p.end()
    return pm


# ── Reciprocal Export Dialog ──────────────────────────────────────────────────
class _ExportBackupDialog(QDialog):
    """Dialog asking whether to export a Safe Backup (apps & preferences only)
    or an Encrypted Full Backup (including password and recovery system)."""

    def __init__(self, expected_pw_hash: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(450, 205)

        self._expected_pw_hash = expected_pw_hash
        self._action = None  # "safe" or "full"
        self._password = None
        self._build_ui()

    def showEvent(self, ev):
        super().showEvent(ev)
        p = self.parent()
        if p is not None:
            cx = p.x() + (p.width() - self.width()) // 2
            cy = p.y() + (p.height() - self.height()) // 2
            self.move(max(0, cx), max(0, cy))
        else:
            qapp = QApplication.instance()
            if qapp:
                sg = qapp.primaryScreen().geometry()
                self.move(
                    sg.x() + (sg.width() - self.width()) // 2,
                    sg.y() + (sg.height() - self.height()) // 2,
                )

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(ev)

    def get_action(self) -> str | None:
        return self._action

    def get_password(self) -> str | None:
        return self._password

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = _Card(self, bg=_CARD, border="#558b5cf6", radius=12)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 16)
        cl.setSpacing(10)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        cl.addWidget(self._stack, 1)

        self._page_choice = self._create_choice_page()
        self._page_confirm_pw = self._create_confirm_pw_page()

        self._stack.addWidget(self._page_choice)      # 0
        self._stack.addWidget(self._page_confirm_pw)  # 1
        self._stack.setCurrentWidget(self._page_choice)

    def _create_choice_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        top_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(_create_export_badge())
        icon_lbl.setFixedSize(40, 40)
        top_row.addWidget(icon_lbl)

        txt_lay = QVBoxLayout()
        txt_lay.setSpacing(5)
        title_lbl = QLabel("Export DeskWarden Backup")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #c4b5fd; background: transparent;")
        txt_lay.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Include your password and recovery credentials?<br><br>"
            "Choose <b>Safe Export</b> to back up locked applications and preferences only, or <b>Full Backup</b> to also include your password and recovery system."
        )
        desc_lbl.setFont(QFont("Segoe UI", 8))
        desc_lbl.setStyleSheet(f"color: {_FG}; background: transparent; line-height: 135%;")
        desc_lbl.setWordWrap(True)
        txt_lay.addWidget(desc_lbl)

        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignRight)

        btn_style = f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 6px 14px; min-width: 80px; font-size: 8pt;
            }}
            QPushButton:hover {{ background: #1f1c34; border-color: {_ACC3}; }}
        """

        safe_btn = QPushButton("Safe Export")
        safe_btn.setFixedHeight(30)
        safe_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        safe_btn.setFont(QFont("Segoe UI", 8))
        safe_btn.setStyleSheet(btn_style)
        safe_btn.setToolTip("Backs up locked applications and preferences only, without passwords.")
        safe_btn.clicked.connect(self._select_safe)
        btn_row.addWidget(safe_btn)

        full_btn = QPushButton("Full Backup")
        full_btn.setFixedHeight(30)
        full_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        full_btn.setFont(QFont("Segoe UI", 8))
        full_btn.setStyleSheet(btn_style)
        full_btn.setToolTip("Backs up all settings, including your password and recovery system.")
        full_btn.clicked.connect(self._select_full)
        btn_row.addWidget(full_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(30)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setFont(QFont("Segoe UI", 8))
        cancel_btn.setStyleSheet(btn_style)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        wl.addLayout(btn_row)
        return w

    def _create_confirm_pw_page(self) -> QWidget:
        w = QWidget(); wl = QVBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(10)

        top_row = QHBoxLayout(); top_row.setSpacing(14); top_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        key_ico = QLabel("🔒")
        key_ico.setFont(QFont("Segoe UI Emoji", 15))
        top_row.addWidget(key_ico)

        txt_lay = QVBoxLayout(); txt_lay.setSpacing(2)
        hdr = QLabel("Encrypt Full Backup")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #c4b5fd; background: transparent;")
        txt_lay.addWidget(hdr)

        sub = QLabel("Enter your Master Password to encrypt this backup container:")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        txt_lay.addWidget(sub)
        top_row.addLayout(txt_lay, 1)
        wl.addLayout(top_row)

        wl.addSpacing(2)
        row = QHBoxLayout(); row.setSpacing(6)
        self._exp_pw_in = QLineEdit()
        self._exp_pw_in.setEchoMode(QLineEdit.EchoMode.Password)
        self._exp_pw_in.setPlaceholderText("Enter master password")
        self._exp_pw_in.setFixedHeight(32)
        self._exp_pw_in.setStyleSheet(f"""
            QLineEdit {{
                background: #100c1a; color: {_FG}; border: 1px solid {_BORD};
                border-radius: 8px; padding: 0 10px; font-size: 8pt;
            }}
            QLineEdit:focus {{ border-color: {_ACC2}; }}""")
        row.addWidget(self._exp_pw_in, 1)

        exp_btn = QPushButton("Export")
        exp_btn.setFixedHeight(32)
        exp_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        exp_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        exp_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACC}; color: white; border: none;
                border-radius: 8px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        row.addWidget(exp_btn)
        wl.addLayout(row)

        self._exp_pw_err = QLabel("")
        self._exp_pw_err.setFont(QFont("Segoe UI", 7))
        self._exp_pw_err.setStyleSheet(f"color: {_RED}; background: transparent;")
        wl.addWidget(self._exp_pw_err)

        def _confirm_export():
            entered = self._exp_pw_in.text()
            if not entered:
                self._exp_pw_err.setText("✗ Please enter your master password.")
                return
            if self._expected_pw_hash and hash_pw(entered) != self._expected_pw_hash:
                self._exp_pw_err.setText("✗ Incorrect master password.")
                self._exp_pw_in.clear()
                self._exp_pw_in.setFocus()
                return
            self._action = "full"
            self._password = entered
            self.accept()

        exp_btn.clicked.connect(_confirm_export)
        self._exp_pw_in.returnPressed.connect(_confirm_export)

        wl.addStretch()
        back_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {_MUTE}; border: none; font-size: 8pt; }} QPushButton:hover {{ color: {_FG}; }}")
        back_btn.clicked.connect(lambda: self._stack.setCurrentWidget(self._page_choice))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        wl.addLayout(back_row)
        return w

    def _select_safe(self):
        self._action = "safe"
        self._password = None
        self.accept()

    def _select_full(self):
        if self._expected_pw_hash:
            self._stack.setCurrentWidget(self._page_confirm_pw)
            self._exp_pw_err.setText("")
            QTimer.singleShot(40, self._exp_pw_in.setFocus)
        else:
            self._action = "full"
            self._password = None
            self.accept()


class _SettingsIOMixin:

    # ── Export ───────────────────────────────────────────────────────────

    def _export_settings(self):
        cfg = load_config()

        # If a password is set, prompt user to choose Safe Export vs Full Backup
        if cfg.get("password_hash"):
            dlg = _ExportBackupDialog(expected_pw_hash=cfg.get("password_hash", ""), parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._backup_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                self._backup_status.setText("Export cancelled.")
                return
            action = dlg.get_action()
            entered_pw = dlg.get_password()
        else:
            action = "safe"
            entered_pw = None

        default_name = f"deskwarden_backup_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.deskwarden"
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop_dir):
            desktop_dir = os.path.expanduser("~")
        default_target = os.path.join(desktop_dir, default_name)
        with suppress_faulthandler():
            path, _f = QFileDialog.getSaveFileName(
                self, "Export DeskWarden Settings", default_target,
                "DeskWarden Backup (*.deskwarden *.dwbackup)"
            )
        if not path:
            return
        if not (path.lower().endswith(".deskwarden") or path.lower().endswith(".dwbackup")):
            path += ".deskwarden"
        try:
            rec_em = cfg.get("recovery_email", "").strip() if cfg.get("recovery_email_enabled", True) else ""
            rec_key_hash = cfg.get("recovery_key_hash", "").strip() if cfg.get("recovery_key_enabled", True) else ""
            if action == "safe":
                export_cfg = dict(cfg)
                export_cfg.pop("password_hash", None)
                export_cfg.pop("recovery_key_hash", None)
                export_cfg.pop("recovery_email", None)
                data = {
                    "app": "DeskWarden",
                    "export_version": 2,
                    "exported_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "config": export_cfg,
                    "security_log": [],
                }
                raw = pack_backup_container(data, password=None, is_full=False)
                status_msg = f"✓ Safe backup exported to {os.path.basename(path)}"
            else:
                export_cfg = dict(cfg)
                sec_log = load_security_log()
                data = {
                    "app": "DeskWarden",
                    "export_version": 2,
                    "exported_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "config": export_cfg,
                    "security_log": sec_log,
                }
                raw = pack_backup_container(
                    data,
                    password=entered_pw,
                    recovery_key_hash=rec_key_hash,
                    recovery_email=rec_em,
                    is_full=True,
                )
                status_msg = f"✓ Encrypted Full backup exported to {os.path.basename(path)}"

            with open(path, "wb") as f:
                f.write(raw)
            if action == "safe":
                apps_n = len(export_cfg.get("locked_apps", []))
                log_security_event("backup_exported", "Settings", f"Safe backup exported ({apps_n} app rules)")
            else:
                apps_n = len(export_cfg.get("locked_apps", []))
                log_security_event("backup_exported", "Settings", f"Encrypted Full backup exported ({apps_n} app rules & credentials)")
            if hasattr(self, "_refresh_log"):
                self._refresh_log()
            self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            self._backup_status.setText(status_msg)
        except Exception as e:
            self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._backup_status.setText(f"✗ Export failed: {e}")

    # ── Import ───────────────────────────────────────────────────────────

    def _import_settings(self):
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop_dir):
            desktop_dir = os.path.expanduser("~")
        with suppress_faulthandler():
            path, _f = QFileDialog.getOpenFileName(
                self, "Import DeskWarden Settings", desktop_dir,
                "DeskWarden Backup (*.deskwarden *.dwbackup)"
            )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                raw_bytes = f.read()

            # STRICT CHECK: Reject any file that is not an authentic DeskWarden backup (e.g. plain .json)
            if not is_deskwarden_backup(raw_bytes):
                self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
                self._backup_status.setText("✗ Invalid file: Not an authentic DeskWarden backup file.")
                return

            header_info = inspect_backup_header(raw_bytes)
            is_encrypted = header_info.get("is_encrypted", False)

            # If unencrypted safe backup container: restore apps & preferences without touching password
            if not is_encrypted:
                try:
                    data = unpack_safe_backup(raw_bytes)
                except Exception:
                    data = unpack_backup_container(raw_bytes)
                backup_cfg = data.get("config", {})
                cur_cfg = load_config()
                cur_cfg["locked_apps"] = backup_cfg.get("locked_apps", [])
                cur_cfg["autostart"] = backup_cfg.get("autostart", cur_cfg.get("autostart", True))
                cur_cfg["auto_update"] = backup_cfg.get("auto_update", cur_cfg.get("auto_update", True))
                cur_cfg["sound_enabled"] = backup_cfg.get("sound_enabled", cur_cfg.get("sound_enabled", True))
                if "recovery_key_enabled" in backup_cfg:
                    cur_cfg["recovery_key_enabled"] = backup_cfg["recovery_key_enabled"]
                if "recovery_email_enabled" in backup_cfg:
                    cur_cfg["recovery_email_enabled"] = backup_cfg["recovery_email_enabled"]
                save_config(cur_cfg)

                self._cfg = load_config()
                self._refresh_apps()
                self._auto_cb.setChecked(self._cfg.get("autostart", False))
                if hasattr(self, "_snd_cb"):
                    self._snd_cb.setChecked(self._cfg.get("sound_enabled", True))
                set_autostart(self._cfg.get("autostart", False))
                if hasattr(self, "_refresh_security_panel"):
                    self._refresh_security_panel()

                self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                apps_n = len(backup_cfg.get("locked_apps", []))
                self._backup_status.setText(f"✓ Safe backup imported: {apps_n} app rules updated (current password unchanged).")
                log_security_event("backup_imported", "Settings", f"Safe backup imported ({apps_n} app rules, password unchanged)")
                if hasattr(self, "_refresh_log"):
                    self._refresh_log()
                return

            # If encrypted backup: show authentic modal
            dlg = _ImportBackupDialog(raw_bytes, header_info, parent=self)
            dlg.exec()

            action = dlg.get_action()
            data = dlg.get_data()
            if not action or not data:
                self._backup_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                self._backup_status.setText("Import cancelled.")
                return

            backup_cfg = data.get("config", {})
            if action == "safe":
                cur_cfg = load_config()
                cur_cfg["locked_apps"] = backup_cfg.get("locked_apps", [])
                cur_cfg["autostart"] = backup_cfg.get("autostart", cur_cfg.get("autostart", True))
                cur_cfg["auto_update"] = backup_cfg.get("auto_update", cur_cfg.get("auto_update", True))
                cur_cfg["sound_enabled"] = backup_cfg.get("sound_enabled", cur_cfg.get("sound_enabled", True))
                if "recovery_key_enabled" in backup_cfg:
                    cur_cfg["recovery_key_enabled"] = backup_cfg["recovery_key_enabled"]
                if "recovery_email_enabled" in backup_cfg:
                    cur_cfg["recovery_email_enabled"] = backup_cfg["recovery_email_enabled"]
                save_config(cur_cfg)

                self._cfg = load_config()
                self._refresh_apps()
                self._auto_cb.setChecked(self._cfg.get("autostart", False))
                if hasattr(self, "_snd_cb"):
                    self._snd_cb.setChecked(self._cfg.get("sound_enabled", True))
                set_autostart(self._cfg.get("autostart", False))
                if hasattr(self, "_refresh_security_panel"):
                    self._refresh_security_panel()

                self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                apps_n = len(backup_cfg.get("locked_apps", []))
                self._backup_status.setText(f"✓ Safe Import complete: {apps_n} app rules updated (password unchanged).")
                log_security_event("backup_imported", "Settings", f"Safe backup imported ({apps_n} app rules, password unchanged)")
                if hasattr(self, "_refresh_log"):
                    self._refresh_log()

            elif action == "full":
                save_config(backup_cfg)
                if "security_log" in data and isinstance(data["security_log"], list):
                    _save_security_log(data["security_log"])

                self._cfg = load_config()
                self._refresh_apps()

                has_pw = bool(self._cfg.get("password_hash"))
                self._pw_badge.setText("✓ Set" if has_pw else "✗ Not set")
                self._pw_badge.setStyleSheet(f"""
                    color: white; background: {_GREEN if has_pw else _RED};
                    border-radius: 10px; padding: 2px 10px;""")
                self._reset_pw_form()

                self._auto_cb.setChecked(self._cfg.get("autostart", False))
                if hasattr(self, "_snd_cb"):
                    self._snd_cb.setChecked(self._cfg.get("sound_enabled", True))
                set_autostart(self._cfg.get("autostart", False))
                if hasattr(self, "_refresh_security_panel"):
                    self._refresh_security_panel()

                self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
                self._backup_status.setText("✓ Full Restore complete: all settings & credentials restored.")
                apps_n = len(backup_cfg.get("locked_apps", []))
                log_security_event("backup_imported", "Settings", f"Full backup restored ({apps_n} app rules & credentials)")
                if hasattr(self, "_refresh_log"):
                    self._refresh_log()

        except Exception as e:
            self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._backup_status.setText(f"✗ Import failed: {e}")
