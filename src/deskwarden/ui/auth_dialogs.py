"""
DeskWarden - ui/auth_dialogs.py

"""

import os
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

# ═════════════════════════════════════════════════════════════════════════
# Control-Panel-open tracking state
# ═════════════════════════════════════════════════════════════════════════

_cp_open_lock = threading.Lock()
_cp_currently_open = False
_auth_dlg_ref = None
_quit_dlg_ref = None


def show_control_panel_auth(on_success, cp_obj=None):
    global _cp_currently_open

    if cp_obj is not None and cp_obj.is_busy():
        dlog("INFO", "show_control_panel_auth: Control Panel process is busy (is_busy=True) — ignoring duplicate request")
        return

    with _cp_open_lock:
        if _cp_currently_open:
            dlog("INFO", "show_control_panel_auth: already open — ignoring duplicate request")
            return
        _cp_currently_open = True
    dlog("INFO", "show_control_panel_auth: opening (lock acquired)")

    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame, QGraphicsDropShadowEffect
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor

    cfg = load_config()
    if not cfg.get("password_hash"):

        try:
            on_success()
        except Exception as e:
            log_crash("show_control_panel_auth/on_success (no password)", e)
            with _cp_open_lock:
                _cp_currently_open = False
            dlog("ERROR", "show_control_panel_auth: on_success() raised — lock released immediately")
            return


        def _force_release_if_stuck():
            global _cp_currently_open
            if cp_obj is not None and cp_obj.is_busy():
                dlog("INFO", "show_control_panel_auth: 60s check — Control Panel process still legitimately busy, skipping force-release")
                return
            with _cp_open_lock:
                if _cp_currently_open:
                    _cp_currently_open = False
                    dlog("WARNING",
                         "show_control_panel_auth: lock force-released after timeout "
                         "(on_closed callback never fired)")
        threading.Timer(60.0, _force_release_if_stuck).start()
        return

    _BG   = "#09070f"; _SIDE = "#0c0a16"; _CARD = "#110f1e"
    _BORD = "#2a2545"; _ACC  = "#7c3aed"; _ACC2 = "#9d5cff"
    _FG   = "#ede9ff"; _MUTE = "#5a5478"; _RED  = "#f87171"

    # _on_close
    _close_handler = [None]

    class _AuthDialog(QWidget):
        def keyPressEvent(self, ev):
            if ev.key() == Qt.Key.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(ev)

        def closeEvent(self, ev):
            ev.accept()
            try:
                from .recovery_dialog import close_active_recovery_dialog
                close_active_recovery_dialog(source_context="control_panel")
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

    dlg = _AuthDialog()
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
    tl = QLabel("DeskWarden  ·  Control Panel")
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

    # ── Auth dialog logo size adjustment ──
    _AUTH_LOGO_SIZE = 56   
    _AUTH_RING_SIZE = 72   
    from PyQt6.QtGui import QPixmap

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

    from PyQt6.QtGui import QLinearGradient
    _sa_pm = QPixmap(asset_path("icon.png"))
    if not _sa_pm.isNull():
        _sa_pm = _sa_pm.scaled(_AUTH_LOGO_SIZE, _AUTH_LOGO_SIZE,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        # Clip the pixmap itself into a circle so corners never show
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
        _avatar_lbl.setText("\U0001F512")
        _avatar_lbl.setStyleSheet(_avatar_lbl.styleSheet() + f"color: {_ACC2}; font-size: 20pt;")

    icon_ring = QWidget(icon_container)
    icon_ring.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_ring.setStyleSheet("background: transparent;")

    def _draw_auth_ring(widget, ev):
        p = QPainter(widget)
        r = widget.rect().adjusted(1, 1, -1, -1)
        grad = QLinearGradient(0, 0, r.width(), r.height())
        grad.setColorAt(0.0, QColor(_ACC))
        grad.setColorAt(0.5, QColor(_ACC2))
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
    sl = QLabel("Control Panel Auth")
    sl.setFont(QFont("Segoe UI", 8))
    sl.setStyleSheet("color: #8b82af; background: transparent;")
    sl.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(sl)
    body_lay.addWidget(sb)

    vsep = QFrame(); vsep.setFixedWidth(1)
    vsep.setStyleSheet(f"background: {_BORD};"); body_lay.addWidget(vsep)

    rp = QWidget()
    rp.setStyleSheet("background: transparent;")
    rpl = QVBoxLayout(rp); rpl.setContentsMargins(24, 24, 24, 24); rpl.setSpacing(10)
    rpl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    prompt = QLabel("Enter password to open Control Panel")
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
        QLineEdit:focus {{ border: 1px solid {_ACC2}; }}""")
    rpl.addWidget(pw_edit)

    cp_eye_btn = QPushButton("Show", pw_edit)
    cp_eye_btn.setFixedSize(34, 24)
    cp_eye_btn.move(229, 8)
    cp_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    cp_eye_btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE};
            border: none; font-size: 7.5pt; font-weight: 600; }}
        QPushButton:hover {{ color: {_FG}; }}""")
    _cp_pw_visible = [False]
    def _cp_toggle_eye():
        _cp_pw_visible[0] = not _cp_pw_visible[0]
        pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _cp_pw_visible[0]
                            else QLineEdit.EchoMode.Password)
        cp_eye_btn.setText("Hide" if _cp_pw_visible[0] else "Show")
    cp_eye_btn.clicked.connect(_cp_toggle_eye)

    def _on_txt_changed(t):
        _check_cp_caps()
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

    def _check_cp_caps():
        if dlg.isVisible():
            caps_lbl.setVisible(is_caps_lock_on())

    _orig_cp_kp = pw_edit.keyPressEvent
    _orig_cp_kr = pw_edit.keyReleaseEvent
    def _cp_kp(ev):
        _orig_cp_kp(ev)
        _check_cp_caps()
    def _cp_kr(ev):
        _orig_cp_kr(ev)
        _check_cp_caps()
    pw_edit.keyPressEvent = _cp_kp
    pw_edit.keyReleaseEvent = _cp_kr
    pw_edit.textChanged.connect(_on_txt_changed)

    err_lbl = QLabel("")
    _err_font2 = QFont("Segoe UI", 9)
    _err_font2.setFamilies(["Segoe UI", "Segoe UI Symbol"])
    err_lbl.setFont(_err_font2)
    err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
    err_lbl.setFixedHeight(14)
    rpl.addWidget(err_lbl)

    unlock_btn = QPushButton("Unlock Control Panel")
    unlock_btn.setFixedHeight(40)
    unlock_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    unlock_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    unlock_btn.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {_ACC}, stop:1 {_ACC2});
            color: white; border: none; border-radius: 10px; padding: 0 20px;
        }}
        QPushButton:hover {{ background: {_ACC2}; }}
        QPushButton:pressed {{ background: #5b21b6; }}
        QPushButton:disabled {{ background: #1e1a30; color: {_MUTE}; }}""")
    unlock_btn.setAutoDefault(False)
    unlock_btn.setDefault(False)
    rpl.addWidget(unlock_btn)

    _unlock_glow = QGraphicsDropShadowEffect(unlock_btn)
    _unlock_glow.setBlurRadius(0)
    _unlock_glow.setColor(QColor(_ACC2))
    _unlock_glow.setOffset(0, 0)
    unlock_btn.setGraphicsEffect(_unlock_glow)

    _orig_enter = unlock_btn.enterEvent
    _orig_leave = unlock_btn.leaveEvent
    def _ub_enter(ev):
        _unlock_glow.setBlurRadius(24)
        _orig_enter(ev)
    def _ub_leave(ev):
        _unlock_glow.setBlurRadius(0)
        _orig_leave(ev)
    unlock_btn.enterEvent = _ub_enter
    unlock_btn.leaveEvent = _ub_leave

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
        QPushButton:hover {{ color: {_ACC2}; text-decoration: none; }}
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
            rec = show_recovery_modal(on_success=_on_rec_success, on_close=_on_rec_close, source_context="control_panel", parent=None)
            if not rec:
                dlg.raise_()
                dlg.activateWindow()
        except Exception as e:
            dlg.raise_()
            dlg.activateWindow()
            log_crash("show_control_panel_auth/_open_recovery", e)

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
    tb.mouseReleaseEvent = _tb_release

    CTX = "Control Panel"


    _unlocked = [False]
    _closed_flag = [False]

    def _release_lock():
        global _cp_currently_open, _auth_dlg_ref
        _auth_dlg_ref = None  
        with _cp_open_lock:
            _cp_currently_open = False
        dlog("INFO", "show_control_panel_auth: auth dialog closed — lock released")

    def _on_close():
        if _closed_flag[0]:
            return
        _closed_flag[0] = True
        try:
            from .recovery_dialog import close_active_recovery_dialog
            if _unlocked[0]:
                close_active_recovery_dialog()
            else:
                close_active_recovery_dialog(source_context="control_panel")
        except Exception:
            pass
        if _unlocked[0]:
            dlog("INFO", "show_control_panel_auth: closed after successful unlock — lock stays with Control Panel window")
            global _auth_dlg_ref
            _auth_dlg_ref = None
            try:
                on_success()
            except Exception as e:
                log_crash("show_control_panel_auth/on_success", e)
                _release_lock()
        else:
            _release_lock()

    _close_handler[0] = _on_close

    def _start_cd(seconds):
        pw_edit.setEnabled(False); unlock_btn.setEnabled(False)
        _cd = [seconds]
        def _tick():
            if not dlg.isVisible(): return
            r = _cd[0]
            if r <= 0:
                pw_edit.setEnabled(True); unlock_btn.setEnabled(True)
                unlock_btn.setText("Unlock Control Panel"); err_lbl.setText(""); pw_edit.setFocus()
                return
            err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
            unlock_btn.setText(f"⏳  Wait {r}s")
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
            is_locked, wait_s = check_locked_out(CTX)
            if is_locked:
                _start_cd(wait_s)
                return
            current_pw_hash = load_config().get("password_hash", cfg.get("password_hash", ""))
            if hash_pw(entered_txt) == current_pw_hash:
                play_unlock_sound()
                reset_attempt_state(CTX)
                log_security_event("success", CTX, "opened control panel")
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
                state = record_wrong_attempt(CTX)
                pw_edit.clear()
                if state["locked"]:
                    _start_cd(state["wait"])
                else:
                    rem = PENALTY_THRES - state["count"]
                    err_lbl.setText(f"✗ Wrong password. {rem} attempt(s) remaining." if rem > 0
                                    else "✗ Wrong password")
                pw_edit.setFocus()
        finally:
            _attempting[0] = False

    close_b.setAutoDefault(False)
    close_b.setDefault(False)
    unlock_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)
    close_b.clicked.connect(dlg.close)

    dlg.show(); dlg.activateWindow(); pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

    _lk, _ws = check_locked_out(CTX)
    if _lk:
        _start_cd(_ws)
    global _auth_dlg_ref
    _auth_dlg_ref = dlg


def show_quit_auth(on_success):
    global _quit_dlg_ref
    if _quit_dlg_ref is not None:
        try:
            if _quit_dlg_ref.isVisible():
                _quit_dlg_ref.activateWindow()
                _quit_dlg_ref.raise_()
                return
        except Exception:
            _quit_dlg_ref = None

    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor

    cfg = load_config()
    if not cfg.get("password_hash"):
        on_success()
        return

    _BG   = "#09070f"
    _SIDE = "#100810"
    _CARD = "#110f1e"
    _BORD = "#3d1020"
    _ACC  = "#7c3aed"
    _ACC2 = "#9d5cff"
    _RED  = "#ef4444"
    _FG   = "#fca5a5"
    _MUTE = "#5a5478"
    _ERR  = "#f87171"

    # ── Rounded card frame ────────────────────────────────────────────────────
    class _RCard(QFrame):
        def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
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
            path.addRoundedRect(r.x(), r.y(), r.width(), r.height(),
                                self._radius, self._radius)
            p.fillPath(path, QBrush(self._bg))
            p.setPen(QPen(self._border, 1))
            p.drawPath(path)

    class _QuitDialog(QWidget):
        def __init__(self):
            super().__init__()
            self._drag_pos = None

        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.LeftButton and ev.position().y() <= 36:
                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                ev.accept()
            else:
                super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):
            if self._drag_pos is not None and ev.buttons() == Qt.MouseButton.LeftButton:
                self.move(ev.globalPosition().toPoint() - self._drag_pos)
                ev.accept()
            else:
                super().mouseMoveEvent(ev)

        def mouseReleaseEvent(self, ev):
            self._drag_pos = None
            super().mouseReleaseEvent(ev)

        def keyPressEvent(self, ev):
            if ev.key() == Qt.Key.Key_Escape:
                self.close()
            elif ev.key() == Qt.Key.Key_F4 and ev.modifiers() & Qt.KeyboardModifier.AltModifier:
                ev.ignore()
            else:
                super().keyPressEvent(ev)

        def closeEvent(self, ev):
            global _quit_dlg_ref
            _quit_dlg_ref = None
            try:
                from .recovery_dialog import close_active_recovery_dialog
                close_active_recovery_dialog(source_context="quit_auth")
            except Exception:
                pass
            super().closeEvent(ev)

    # ── Main dialog window ────────────────────────────────────────────────────
    dlg = _QuitDialog()
    dlg.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedSize(460, 270)

    qapp = ui_thread._qapp or QApplication.instance()
    if qapp:
        sg = qapp.primaryScreen().geometry()
        dlg.move(sg.x() + (sg.width()  - 460) // 2,
                 sg.y() + (sg.height() - 270) // 2)

    outer_lay = QVBoxLayout(dlg)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    card = _RCard(dlg, bg=_CARD, border=_BORD, radius=16)
    outer_lay.addWidget(card)

    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0)
    card_lay.setSpacing(0)

    # ── Title bar ─────────────────────────────────────────────────────────────
    tb = QWidget()
    tb.setFixedHeight(36)
    tb.setStyleSheet(f"""
        background: {_SIDE};
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
        border-bottom-left-radius: 0px;
        border-bottom-right-radius: 0px;
    """)
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(14, 0, 10, 0)
    tbl.setSpacing(0)

    _QUIT_LOGO_OFFSET_X = 3   
    _QUIT_LOGO_OFFSET_Y = 2   

    tb_logo = QLabel()
    tb_logo.setFixedSize(16, 16)
    from PyQt6.QtGui import QPixmap
    _qb_pm = QPixmap(asset_path("icon.png"))
    if not _qb_pm.isNull():
        _qb_pm = _qb_pm.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        tb_logo.setPixmap(_qb_pm)
    tb_logo.setStyleSheet("background: transparent;")
    tb_logo.setContentsMargins(_QUIT_LOGO_OFFSET_X, _QUIT_LOGO_OFFSET_Y, 0, 0)
    tbl.addWidget(tb_logo)
    tbl.addSpacing(6)

    tl = QLabel("DeskWarden  ·  Quit")
    tl.setFont(QFont("Segoe UI", 8))
    tl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
    tbl.addWidget(tl)
    tbl.addStretch()

    close_b = QPushButton("✕")
    close_b.setFixedSize(28, 22)
    close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    close_b.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {_MUTE}; border: none;
            font-size: 10pt; border-radius: 4px;
        }}
        QPushButton:hover {{ background: #7f1d1d; color: white; }}""")
    close_b.clicked.connect(dlg.close)
    tbl.addWidget(close_b)
    card_lay.addWidget(tb)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORD};")
    card_lay.addWidget(sep)

    # ── Rounded bottom-corner panels ─────
    _RADIUS = 16

    class _SidePanel(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAutoFillBackground(False)

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            W, H = self.width(), self.height()
            path = QPainterPath()
            path.moveTo(0, 0)
            path.lineTo(W, 0)
            path.lineTo(W, H)
            path.lineTo(_RADIUS, H)
            path.arcTo(0, H - _RADIUS * 2, _RADIUS * 2, _RADIUS * 2, 270, -90)
            path.closeSubpath()
            p.fillPath(path, QBrush(QColor(_SIDE)))

    class _RightPanel(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAutoFillBackground(False)

        def paintEvent(self, ev):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            W, H = self.width(), self.height()
            path = QPainterPath()
            path.moveTo(0, 0)
            path.lineTo(W, 0)
            path.lineTo(W, H - _RADIUS)
            path.arcTo(W - _RADIUS * 2, H - _RADIUS * 2, _RADIUS * 2, _RADIUS * 2, 0, -90)
            path.lineTo(0, H)
            path.closeSubpath()
            p.fillPath(path, QBrush(QColor(_BG)))

    # ── Body (sidebar + right panel) ──────────────────────────────────────────
    body = QWidget()
    body.setStyleSheet("background: transparent;")
    body_lay = QHBoxLayout(body)
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)

    # Left sidebar
    sb = _SidePanel()
    sb.setFixedWidth(140)
    sbl = QVBoxLayout(sb)
    sbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.setContentsMargins(0, 24, 0, 16)
    sbl.setSpacing(6)

    icon_lbl = QLabel("⛔")
    icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
    icon_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(icon_lbl)

    al = QLabel("Quit")
    al.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    al.setStyleSheet(f"color: {_FG}; background: transparent;")
    al.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(al)

    sl = QLabel("Protection stops")
    sl.setFont(QFont("Segoe UI", 7))
    sl.setStyleSheet("color: #6a3040; background: transparent;")
    sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.addWidget(sl)

    body_lay.addWidget(sb)

    vsep = QFrame()
    vsep.setFixedWidth(1)
    vsep.setStyleSheet(f"background: {_BORD};")
    body_lay.addWidget(vsep)

    # Right panel
    rp = _RightPanel()
    rpl = QVBoxLayout(rp)
    rpl.setContentsMargins(22, 20, 22, 22)
    rpl.setSpacing(8)
    rpl.setAlignment(Qt.AlignmentFlag.AlignTop)

    prompt = QLabel("Confirm password to quit DeskWarden")
    prompt.setFont(QFont("Segoe UI", 10))
    prompt.setStyleSheet("color: #ede9ff; background: transparent;")
    rpl.addWidget(prompt)

    sub = QLabel("Protection will stop after quitting.")
    sub.setFont(QFont("Segoe UI", 8))
    sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
    rpl.addWidget(sub)

    pw_edit = QLineEdit()
    pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    pw_edit.setFont(QFont("Segoe UI", 11))
    pw_edit.setFixedHeight(38)
    pw_edit.setStyleSheet(f"""
        QLineEdit {{
            background: {_CARD}; color: #ede9ff;
            border: 1px solid {_BORD}; border-radius: 8px; padding: 0 44px 0 12px;
        }}
        QLineEdit:focus {{ border: 1px solid {_RED}; }}""")
    rpl.addWidget(pw_edit)

    q_eye_btn = QPushButton("Show", pw_edit)
    q_eye_btn.setFixedSize(34, 22)
    q_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    q_eye_btn.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE};
            border: none; font-size: 7.5pt; font-weight: 600; }}
        QPushButton:hover {{ color: #ede9ff; }}""")
    _q_pw_visible = [False]
    def _q_toggle_eye():
        _q_pw_visible[0] = not _q_pw_visible[0]
        pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _q_pw_visible[0]
                            else QLineEdit.EchoMode.Password)
        q_eye_btn.setText("Hide" if _q_pw_visible[0] else "Show")
    q_eye_btn.clicked.connect(_q_toggle_eye)

    def _pos_q_eye():
        q_eye_btn.move(pw_edit.width() - q_eye_btn.width() - 6,
                       (pw_edit.height() - q_eye_btn.height()) // 2)
    _orig_pw_resize = pw_edit.resizeEvent
    def _pw_resize(ev):
        _orig_pw_resize(ev)
        _pos_q_eye()
    pw_edit.resizeEvent = _pw_resize
    _pos_q_eye()

    def _on_txt_changed_q(t):
        _check_q_caps()
        if err_lbl.text() == "Please enter your password.":
            err_lbl.setText("")

    # Caps Lock indicator
    q_caps_lbl = QLabel("⚠️ Caps Lock is ON")
    q_caps_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    q_caps_lbl.setStyleSheet("color: #f59e0b; background: transparent;")
    q_caps_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    q_caps_lbl.setFixedHeight(12)
    q_caps_lbl.setVisible(is_caps_lock_on())
    rpl.addWidget(q_caps_lbl)

    def _check_q_caps():
        if dlg.isVisible():
            q_caps_lbl.setVisible(is_caps_lock_on())

    _orig_q_kp = pw_edit.keyPressEvent
    _orig_q_kr = pw_edit.keyReleaseEvent
    def _q_kp(ev):
        _orig_q_kp(ev)
        _check_q_caps()
    def _q_kr(ev):
        _orig_q_kr(ev)
        _check_q_caps()
    pw_edit.keyPressEvent = _q_kp
    pw_edit.keyReleaseEvent = _q_kr
    pw_edit.textChanged.connect(_on_txt_changed_q)

    acc_line = QFrame()
    acc_line.setFixedHeight(2)
    acc_line.setStyleSheet(f"background: {_RED}; border-radius: 1px;")
    rpl.addWidget(acc_line)

    err_lbl = QLabel("")
    _err_font3 = QFont("Segoe UI", 9)
    _err_font3.setFamilies(["Segoe UI", "Segoe UI Symbol"])
    err_lbl.setFont(_err_font3)
    err_lbl.setStyleSheet(f"color: {_ERR}; background: transparent;")
    rpl.addWidget(err_lbl)

    quit_btn = QPushButton("✓  Confirm Quit")
    quit_btn.setFixedHeight(40)
    quit_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    quit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    quit_btn.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #c0392b, stop:1 #991b1b);
            color: white; border: none; border-radius: 10px; padding: 0 20px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #dc2626, stop:1 #b91c1c);
        }}
        QPushButton:pressed  {{ background: #7f1d1d; }}
        QPushButton:disabled {{ background: #1e1a30; color: {_MUTE}; }}""")
    quit_btn.setAutoDefault(False)
    quit_btn.setDefault(False)
    rpl.addWidget(quit_btn)

    # ── Forgot password link ───────────────────────────────────────────────
    forgot_row_q = QWidget()
    forgot_row_q.setFixedHeight(20)
    forgot_row_q.setStyleSheet("background: transparent;")
    frl_q = QHBoxLayout(forgot_row_q)
    frl_q.setContentsMargins(0, 0, 0, 0)
    frl_q.setSpacing(0)
    frl_q.addStretch()

    forgot_btn_q = QPushButton("Forgot password?")
    forgot_btn_q.setFont(QFont("Segoe UI", 8))
    forgot_btn_q.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    forgot_btn_q.setAutoDefault(False)
    forgot_btn_q.setDefault(False)
    forgot_btn_q.setStyleSheet(f"""
        QPushButton {{ background: transparent; color: {_MUTE}; border: none; }}
        QPushButton:hover {{ color: #f87171; text-decoration: none; }}
    """)

    def _open_recovery_q():
        try:
            from .recovery_dialog import show_recovery_modal
            def _on_rec_success_q():
                _unlocked_q[0] = True
                dlg.close()
                on_success()
            def _on_rec_close_q():
                if not _unlocked_q[0]:
                    dlg.raise_()
                    dlg.activateWindow()
                    pw_edit.setFocus()
            rec = show_recovery_modal(on_success=_on_rec_success_q, on_close=_on_rec_close_q, source_context="quit_auth", parent=None)
            if not rec:
                dlg.raise_()
                dlg.activateWindow()
        except Exception as e:
            dlg.raise_()
            dlg.activateWindow()
            log_crash("show_quit_auth/_open_recovery_q", e)

    forgot_btn_q.clicked.connect(_open_recovery_q)
    frl_q.addWidget(forgot_btn_q)
    frl_q.addStretch()

    try:
        from .recovery_dialog import is_recovery_available
        if not is_recovery_available(load_config()):
            forgot_btn_q.setVisible(False)
    except Exception:
        pass

    rpl.addWidget(forgot_row_q)

    body_lay.addWidget(rp, 1)
    card_lay.addWidget(body, 1)

    # ── Auth logic ────────────────────────────────────────────────────────────
    CTX_Q = "Quit"


    def _start_cd(seconds):
        pw_edit.setEnabled(False)
        quit_btn.setEnabled(False)
        _cd = [seconds]

        def _tick():
            r = _cd[0]
            if r <= 0:
                pw_edit.setEnabled(True)
                quit_btn.setEnabled(True)
                quit_btn.setText("✓  Confirm Quit")
                err_lbl.setText("")
                pw_edit.setFocus()
                return
            err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
            quit_btn.setText(f"⏳  Wait {r}s")
            _cd[0] -= 1
            QTimer.singleShot(1000, _tick)

        _tick()

    _attempting_q = [False]
    _unlocked_q = [False]

    def _attempt():
        if _attempting_q[0] or _unlocked_q[0]:
            return
        _attempting_q[0] = True
        try:
            entered_txt = pw_edit.text()
            if not entered_txt:
                err_lbl.setText("Please enter your password.")
                pw_edit.setFocus()
                return
            is_locked, wait_s = check_locked_out(CTX_Q)
            if is_locked:
                _start_cd(wait_s)
                return
            current_pw_hash = load_config().get("password_hash", cfg.get("password_hash", ""))
            if hash_pw(entered_txt) == current_pw_hash:
                play_unlock_sound()
                _unlocked_q[0] = True
                reset_attempt_state(CTX_Q)
                log_security_event("success", CTX_Q, "quit confirmed")
                try:
                    from .recovery_dialog import close_active_recovery_dialog
                    close_active_recovery_dialog()
                except Exception:
                    pass
                dlg.hide()
                dlg.close()
                on_success()
            else:
                play_error_sound()
                state = record_wrong_attempt(CTX_Q)
                pw_edit.clear()
                if state["locked"]:
                    _start_cd(state["wait"])
                else:
                    rem = PENALTY_THRES - state["count"]
                    err_lbl.setText(
                        f"✗ Wrong password. {rem} attempt(s) remaining." if rem > 0
                        else "✗ Wrong password — Quit cancelled.")
                pw_edit.setFocus()
        finally:
            _attempting_q[0] = False

    quit_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)

    dlg.show()
    dlg.activateWindow()
    pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

    _lk, _ws = check_locked_out(CTX_Q)
    if _lk:
        _start_cd(_ws)

    _quit_dlg_ref = dlg


def release_control_panel_lock():
    
    global _cp_currently_open
    with _cp_open_lock:
        _cp_currently_open = False

