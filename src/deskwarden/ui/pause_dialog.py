"""
DeskWarden - ui/pause_dialog.py

Dedicated modular dialog for temporarily pausing application protection
with Master Password verification. Matches DeskWarden's dark glass aesthetic.
"""

import threading

from ..core.paths import asset_path
from ..core.logging_utils import dlog, log_crash
from ..core.config import load_config
from ..core.security import (
    hash_pw, record_wrong_attempt, check_locked_out,
    reset_attempt_state, log_security_event, PENALTY_THRES, is_caps_lock_on,
)
from ..core.sound_utils import play_unlock_sound, play_error_sound
from . import ui_thread


_pause_auth_dlg_ref = None


def show_pause_protection_auth(on_success, on_cancel=None, duration_seconds=None):
    global _pause_auth_dlg_ref
    if _pause_auth_dlg_ref is not None:
        try:
            if _pause_auth_dlg_ref.isVisible():
                _pause_auth_dlg_ref.activateWindow()
                _pause_auth_dlg_ref.raise_()
                return
        except Exception:
            _pause_auth_dlg_ref = None

    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame, QGraphicsDropShadowEffect
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor, QPixmap, QLinearGradient

    cfg = load_config()
    if not cfg.get("password_hash"):
        on_success()
        return

    _BG   = "#09070f"; _SIDE = "#0c0a16"; _CARD = "#110f1e"
    _BORD = "#2a2545"; _ACC  = "#7c3aed"; _ACC2 = "#9d5cff"
    _FG   = "#ede9ff"; _MUTE = "#5a5478"; _RED  = "#f87171"

    dur_title = ""
    if duration_seconds:
        if duration_seconds >= 3600:
            hrs = duration_seconds // 3600
            dur_title = f" ({hrs} Hour{'s' if hrs > 1 else ''})"
        else:
            mins = duration_seconds // 60
            dur_title = f" ({mins} Min{'s' if mins > 1 else ''})"

    default_btn_text = f"Pause Protection{dur_title}" if dur_title else "Pause All Protection"

    _close_handler = [None]

    class _PauseAuthDialog(QWidget):
        def keyPressEvent(self, ev):
            if ev.key() == Qt.Key.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(ev)

        def closeEvent(self, ev):
            global _pause_auth_dlg_ref
            _pause_auth_dlg_ref = None
            ev.accept()
            try:
                from .recovery_dialog import close_active_recovery_dialog
                close_active_recovery_dialog(source_context="pause_auth")
            except Exception:
                pass
            if _close_handler[0]:
                _close_handler[0]()

    class _RCard(QFrame):
        def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
            super().__init__(parent)
            self._bg = QColor(bg); self._border = QColor(border); self._radius = radius
            self.setAutoFillBackground(False)
        def paintEvent(self, ev):
            p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = self.rect().adjusted(1,1,-1,-1)
            path = QPainterPath()
            path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), self._radius, self._radius)
            p.fillPath(path, QBrush(self._bg))
            p.setPen(QPen(self._border, 1)); p.drawPath(path)

    dlg = _PauseAuthDialog()
    dlg.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedSize(480, 270)

    qapp = ui_thread._qapp or QApplication.instance()
    sg = qapp.primaryScreen().geometry()
    dlg.move(sg.x() + (sg.width() - 480) // 2, sg.y() + (sg.height() - 270) // 2)

    outer_lay = QVBoxLayout(dlg)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    card = _RCard(dlg, bg=_CARD, border=_BORD, radius=16)
    outer_lay.addWidget(card)

    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0); card_lay.setSpacing(0)

    tb = QWidget(); tb.setFixedHeight(40)
    tb.setStyleSheet("background: transparent;")
    tbl = QHBoxLayout(tb); tbl.setContentsMargins(16, 0, 10, 0); tbl.setSpacing(0)
    tl = QLabel("DeskWarden  ·  Pause Protection")
    tl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
    tl.setStyleSheet(f"color: {_FG}; background: transparent;")
    tbl.addWidget(tl); tbl.addStretch()
    close_b = QPushButton("✕"); close_b.setFixedSize(28, 22)
    close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    close_b.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE}; border: none;
            font-size: 10pt; border-radius: 4px; }}
        QPushButton:hover {{ background: #7f1d1d; color: white; }}""")
    close_b.clicked.connect(dlg.close)
    tbl.addWidget(close_b)
    card_lay.addWidget(tb)

    sep = QFrame(); sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORD};"); card_lay.addWidget(sep)

    body = QWidget(); body.setStyleSheet("background: transparent;")
    body_lay = QHBoxLayout(body); body_lay.setContentsMargins(0,0,0,0); body_lay.setSpacing(0)

    sb = QWidget(); sb.setFixedWidth(145)
    sb.setStyleSheet("background: #0c0a17; border-bottom-left-radius: 14px;")
    sbl = QVBoxLayout(sb); sbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.setContentsMargins(0, 26, 0, 24); sbl.setSpacing(10)

    _AUTH_LOGO_SIZE = 56   
    _AUTH_RING_SIZE = 72   

    icon_container = QWidget()
    icon_container.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_container.setStyleSheet("background: transparent;")

    _avatar_glow = QGraphicsDropShadowEffect()
    _avatar_glow.setBlurRadius(22)
    _avatar_glow.setColor(QColor("#7c3aed"))
    _avatar_glow.setOffset(0, 0)
    icon_container.setGraphicsEffect(_avatar_glow)

    _avatar_lbl = QLabel(icon_container)
    _avatar_lbl.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    _avatar_lbl.move(0, 0)
    _avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    _avatar_lbl.setStyleSheet(f"background: {_CARD}; border-radius: {_AUTH_RING_SIZE // 2}px;")

    _sa_pm = QPixmap(asset_path("icon.png"))
    if not _sa_pm.isNull():
        _sa_pm = _sa_pm.scaled(_AUTH_LOGO_SIZE, _AUTH_LOGO_SIZE,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        _circ_pm = QPixmap(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
        _circ_pm.fill(Qt.GlobalColor.transparent)
        _cp = QPainter(_circ_pm)
        _cp.setRenderHint(QPainter.RenderHint.Antialiasing)
        _cpath = QPainterPath()
        _cpath.addEllipse(0, 0, _AUTH_RING_SIZE, _AUTH_RING_SIZE)
        _cp.setClipPath(_cpath)
        _cp.fillRect(_circ_pm.rect(), QBrush(QColor(_CARD)))
        _cx = (_AUTH_RING_SIZE - _sa_pm.width()) // 2
        _cy = (_AUTH_RING_SIZE - _sa_pm.height()) // 2
        _cp.drawPixmap(_cx, _cy, _sa_pm)
        _cp.end()
        _avatar_lbl.setPixmap(_circ_pm)
    else:
        _avatar_lbl.setText("⏸")
        _avatar_lbl.setStyleSheet(_avatar_lbl.styleSheet() + f"color: {_ACC2}; font-size: 20pt;")

    icon_ring = QWidget(icon_container)
    icon_ring.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_ring.setStyleSheet("background: transparent;")

    def _draw_auth_ring(widget, ev):
        p = QPainter(widget)
        r = widget.rect().adjusted(1, 1, -1, -1)
        grad = QLinearGradient(0, 0, r.width(), r.height())
        grad.setColorAt(0.0, QColor("#7c3aed"))
        grad.setColorAt(0.5, QColor("#9d5cff"))
        grad.setColorAt(1.0, QColor("#4c1d95"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QBrush(grad), 2.5))
        p.drawEllipse(r)

    icon_ring.paintEvent = lambda ev: _draw_auth_ring(icon_ring, ev)

    sbl.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
    al = QLabel("DeskWarden")
    al.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    al.setStyleSheet(f"color: {_FG}; background: transparent;")
    al.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(al)
    sl = QLabel("Pause Protection")
    sl.setFont(QFont("Segoe UI", 8))
    sl.setStyleSheet("color: #8b82af; background: transparent;")
    sl.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(sl)
    body_lay.addWidget(sb)

    vsep = QFrame(); vsep.setFixedWidth(1)
    vsep.setStyleSheet(f"background: {_BORD};"); body_lay.addWidget(vsep)

    rp = QWidget()
    rp.setStyleSheet("background: transparent;")
    rpl = QVBoxLayout(rp); rpl.setContentsMargins(22, 24, 22, 24); rpl.setSpacing(10)
    rpl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    prompt = QLabel(f"Enter password to pause protection{dur_title}")
    prompt.setFont(QFont("Segoe UI", 10))
    prompt.setStyleSheet(f"color: {_FG}; background: transparent;")
    rpl.addWidget(prompt)

    pw_edit = QLineEdit()
    pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    pw_edit.setFont(QFont("Segoe UI", 11))
    pw_edit.setFixedHeight(40)
    pw_edit.setStyleSheet(f"""
        QLineEdit {{
            background: {_CARD}; color: {_FG}; border: 1px solid {_BORD};
            border-radius: 10px; padding: 0 46px 0 14px;
        }}
        QLineEdit:focus {{
            border: 1px solid #9d5cff;
            background: #14102c;
        }}
    """)
    rpl.addWidget(pw_edit)

    eye_btn = QPushButton("Show", pw_edit)
    eye_btn.setFixedSize(40, 26)
    eye_btn.move(pw_edit.width() - 44, (40 - 26) // 2)
    eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    eye_btn.setFont(QFont("Segoe UI", 7))
    eye_btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {_MUTE}; border: none;
            padding: 0; margin: 0;
        }}
        QPushButton:hover {{ color: #9d5cff; }}
    """)
    _show_pw = [False]
    def _toggle_pw():
        _show_pw[0] = not _show_pw[0]
        if _show_pw[0]:
            pw_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            eye_btn.setText("Hide")
        else:
            pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
            eye_btn.setText("Show")
    eye_btn.clicked.connect(_toggle_pw)
    def _reposition_eye(ev):
        eye_btn.move(pw_edit.width() - 44, (pw_edit.height() - 26) // 2)
        QLineEdit.resizeEvent(pw_edit, ev)
    def _on_txt_changed(t):
        _check_caps()
        if err_lbl.text() == "Please enter your password.":
            err_lbl.setText("")

    # Caps Lock indicator
    caps_lbl = QLabel("⚠️ Caps Lock is ON")
    caps_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    caps_lbl.setStyleSheet("color: #f59e0b; background: transparent;")
    caps_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    caps_lbl.setFixedHeight(12)
    caps_lbl.setVisible(is_caps_lock_on())
    rpl.addWidget(caps_lbl)

    def _check_caps():
        if dlg.isVisible():
            caps_lbl.setVisible(is_caps_lock_on())

    _orig_p_kp = pw_edit.keyPressEvent
    _orig_p_kr = pw_edit.keyReleaseEvent
    def _p_kp(ev):
        _orig_p_kp(ev)
        _check_caps()
    def _p_kr(ev):
        _orig_p_kr(ev)
        _check_caps()
    pw_edit.keyPressEvent = _p_kp
    pw_edit.keyReleaseEvent = _p_kr
    pw_edit.textChanged.connect(_on_txt_changed)

    err_lbl = QLabel("")
    err_lbl.setFont(QFont("Segoe UI", 8))
    err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
    err_lbl.setWordWrap(True)
    rpl.addWidget(err_lbl)

    pause_btn = QPushButton(default_btn_text)
    pause_btn.setFixedHeight(38)
    pause_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    pause_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    pause_btn.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #7c3aed, stop:1 #9d5cff);
            color: white; border: none; border-radius: 10px;
        }}
        QPushButton:hover {{ background: #9d5cff; }}
        QPushButton:disabled {{ background: #1a1630; color: {_MUTE}; }}
    """)
    _pause_glow = QGraphicsDropShadowEffect()
    _pause_glow.setBlurRadius(0)
    _pause_glow.setColor(QColor("#7c3aed"))
    _pause_glow.setOffset(0, 0)
    pause_btn.setGraphicsEffect(_pause_glow)

    _orig_enter = pause_btn.enterEvent
    _orig_leave = pause_btn.leaveEvent
    def _pb_enter(ev):
        _pause_glow.setBlurRadius(24)
        _orig_enter(ev)
    def _pb_leave(ev):
        _pause_glow.setBlurRadius(0)
        _orig_leave(ev)
    pause_btn.enterEvent = _pb_enter
    pause_btn.leaveEvent = _pb_leave

    rpl.addWidget(pause_btn)

    # ── Forgot password link ───────────────────────────────────────────────
    forgot_row = QWidget()
    forgot_row.setFixedHeight(20)
    forgot_row.setStyleSheet("background: transparent;")
    frl = QHBoxLayout(forgot_row)
    frl.setContentsMargins(0, 0, 0, 0)
    frl.setSpacing(0)
    frl.addStretch()

    forgot_btn = QPushButton("Forgot password?")
    forgot_btn.setFont(QFont("Segoe UI", 8))
    forgot_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    forgot_btn.setAutoDefault(False)
    forgot_btn.setDefault(False)
    forgot_btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE}; border: none; }}
        QPushButton:hover {{ color: #9d5cff; text-decoration: none; }}
    """)

    def _open_recovery():
        try:
            from .recovery_dialog import show_recovery_modal
            def _on_rec_success():
                _unlocked[0] = True
                dlg.close()
                on_success()
            def _on_rec_close():
                if not _unlocked[0] and not _closed_flag[0]:
                    dlg.raise_()
                    dlg.activateWindow()
                    pw_edit.setFocus()
            rec = show_recovery_modal(on_success=_on_rec_success, on_close=_on_rec_close, source_context="pause_auth", parent=None)
            if not rec:
                dlg.raise_()
                dlg.activateWindow()
        except Exception as e:
            dlg.raise_()
            dlg.activateWindow()
            log_crash("show_pause_protection_auth/_open_recovery", e)

    forgot_btn.clicked.connect(_open_recovery)
    frl.addWidget(forgot_btn)
    frl.addStretch()

    try:
        from .recovery_dialog import is_recovery_available
        if not is_recovery_available(load_config()):
            forgot_btn.setVisible(False)
    except Exception:
        pass

    rpl.addWidget(forgot_row)
    body_lay.addWidget(rp, 1)
    card_lay.addWidget(body, 1)

    _drag = [False, 0, 0]
    def _tb_press(ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            _drag[0] = True
            _drag[1] = ev.globalPosition().x() - dlg.x()
            _drag[2] = ev.globalPosition().y() - dlg.y()
    def _tb_move(ev):
        if _drag[0]:
            dlg.move(int(ev.globalPosition().x()-_drag[1]),
                     int(ev.globalPosition().y()-_drag[2]))
    def _tb_release(ev): _drag[0] = False
    tb.mousePressEvent = _tb_press; tb.mouseMoveEvent = _tb_move

    CTX_P = "Pause Protection"
    _closed_flag = [False]
    _unlocked = [False]

    def _on_close():
        if _closed_flag[0]:
            return
        _closed_flag[0] = True
        try:
            from .recovery_dialog import close_active_recovery_dialog
            if _unlocked[0]:
                close_active_recovery_dialog()
            else:
                close_active_recovery_dialog(source_context="pause_auth")
        except Exception:
            pass
        if _unlocked[0]:
            try:
                on_success()
            except Exception as e:
                log_crash("show_pause_protection_auth/on_success", e)
        elif on_cancel:
            try:
                on_cancel()
            except Exception:
                pass

    _close_handler[0] = _on_close

    def _start_cd(seconds):
        pw_edit.setEnabled(False); pause_btn.setEnabled(False)
        _cd = [seconds]
        def _tick():
            if not dlg.isVisible(): return
            r = _cd[0]
            if r <= 0:
                pw_edit.setEnabled(True); pause_btn.setEnabled(True)
                pause_btn.setText(default_btn_text); err_lbl.setText(""); pw_edit.setFocus()
                return
            err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
            pause_btn.setText(f"⏳  Wait {r}s")
            _cd[0] -= 1; QTimer.singleShot(1000, _tick)
        _tick()


    _attempting = [False]

    def _attempt():
        if _attempting[0] or _unlocked[0]:
            return
        _attempting[0] = True
        try:
            entered_txt = pw_edit.text()
            if not entered_txt:
                err_lbl.setText("Please enter your password.")
                pw_edit.setFocus()
                return
            is_locked, wait_s = check_locked_out(CTX_P)
            if is_locked:
                _start_cd(wait_s)
                return
            current_pw_hash = load_config().get("password_hash", cfg.get("password_hash", ""))
            if hash_pw(entered_txt) == current_pw_hash:
                play_unlock_sound()
                reset_attempt_state(CTX_P)
                log_security_event("success", CTX_P, "protection paused")
                _unlocked[0] = True
                try:
                    from .recovery_dialog import close_active_recovery_dialog
                    close_active_recovery_dialog()
                except Exception:
                    pass
                dlg.hide()
                dlg.close()
            else:
                play_error_sound()
                state = record_wrong_attempt(CTX_P)
                pw_edit.clear()
                if state["locked"]:
                    _start_cd(state["wait"])
                else:
                    rem = PENALTY_THRES - state["count"]
                    if rem > 0:
                        err_lbl.setText(f"✗ Wrong password. {rem} attempt(s) remaining.")
                    else:
                        err_lbl.setText("✗ Wrong password.")
                pw_edit.setFocus()
        finally:
            _attempting[0] = False

    pause_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)

    dlg.show()
    dlg.activateWindow()
    pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

    _lk, _ws = check_locked_out(CTX_P)
    if _lk:
        _start_cd(_ws)

    _pause_auth_dlg_ref = dlg
