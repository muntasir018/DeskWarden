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
    reset_attempt_state, log_security_event, PENALTY_THRES,
)
from . import ui_thread

# ═════════════════════════════════════════════════════════════════════════
# Control-Panel-open tracking state
# ═════════════════════════════════════════════════════════════════════════

_cp_open_lock = threading.Lock()
_cp_currently_open = False
_auth_dlg_ref = None


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
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
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
        
        def closeEvent(self, ev):
            ev.accept()
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
    dlg.setFixedSize(460, 270)

    qapp = ui_thread._qapp
    sg = qapp.primaryScreen().geometry()
    dlg.move(sg.x() + (sg.width() - 460) // 2, sg.y() + (sg.height() - 270) // 2)

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

    sb = QWidget(); sb.setFixedWidth(140)
    sb.setStyleSheet("background: transparent;")
    sbl = QVBoxLayout(sb); sbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sbl.setContentsMargins(0, 24, 0, 16); sbl.setSpacing(6)

    # ── Auth dialog logo size adjustment ──
    _AUTH_LOGO_SIZE = 44   
    _AUTH_RING_SIZE = 56   
    from PyQt6.QtGui import QPixmap

    icon_container = QWidget()
    icon_container.setFixedSize(_AUTH_RING_SIZE, _AUTH_RING_SIZE)
    icon_container.setStyleSheet("background: transparent;")

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
        _avatar_lbl.setStyleSheet(_avatar_lbl.styleSheet() + f"color: {_ACC2}; font-size: 16pt;")

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
        p.setPen(QPen(QBrush(grad), 2))
        p.drawEllipse(r)

    icon_ring.paintEvent = lambda ev: _draw_auth_ring(icon_ring, ev)

    sbl.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
    al = QLabel("DeskWarden")
    al.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    al.setStyleSheet(f"color: {_FG}; background: transparent;")
    al.setAlignment(Qt.AlignmentFlag.AlignCenter); sbl.addWidget(al)
    sl = QLabel("Control Panel Auth")
    sl.setFont(QFont("Segoe UI", 7))
    sl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
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

    def _release_lock():
        global _cp_currently_open, _auth_dlg_ref
        _auth_dlg_ref = None  
        with _cp_open_lock:
            _cp_currently_open = False
        dlog("INFO", "show_control_panel_auth: auth dialog closed — lock released")

    def _on_close():
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

    def _attempt():
        is_locked, wait_s = check_locked_out(CTX)
        if is_locked: _start_cd(wait_s); return
        if hash_pw(pw_edit.text()) == cfg.get("password_hash", ""):
            reset_attempt_state(CTX)
            log_security_event("success", CTX, "opened control panel")
            _unlocked[0] = True
            dlg.close()
        else:
            state = record_wrong_attempt(CTX); pw_edit.clear()
            if state["locked"]:
                _start_cd(state["wait"])
            else:
                rem = PENALTY_THRES - state["count"]
                err_lbl.setText(f"✗ Wrong password. {rem} attempt(s) remaining." if rem > 0
                                else "✗ Wrong password")
            pw_edit.setFocus()

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
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QPushButton, QFrame, QGraphicsDropShadowEffect
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

    # ── Main dialog window ────────────────────────────────────────────────────
    dlg = QWidget()
    dlg.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedSize(460, 270)

    qapp = ui_thread._qapp
    sg = qapp.primaryScreen().geometry()
    dlg.move(sg.x() + (sg.width()  - 460) // 2,
             sg.y() + (sg.height() - 270) // 2)

    def _block_key(ev):
        if (ev.key() == Qt.Key.Key_F4 and
                ev.modifiers() & Qt.KeyboardModifier.AltModifier):
            ev.ignore()
    dlg.keyPressEvent = _block_key

    outer_lay = QVBoxLayout(dlg)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    # ── Outer card (shadow removed to avoid checkered corner artifacts) ───────
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

    tbl.addSpacing(0)

    # ── Logo offset adjustment (Quit dialog titlebar) ──
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
    q_eye_btn.setFixedSize(32, 22)
    q_eye_btn.move(231, 8)
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
        QPushButton:hover   {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #cc4536, stop:1 #a01f1f); }}
        QPushButton:pressed  {{ background: #7f1d1d; }}
        QPushButton:disabled {{ background: #1e1a30; color: {_MUTE}; }}""")

    _quit_glow = QGraphicsDropShadowEffect()
    _quit_glow.setBlurRadius(0)
    _quit_glow.setColor(QColor(_RED))
    _quit_glow.setOffset(0, 0)
    quit_btn.setGraphicsEffect(_quit_glow)

    def _quit_enter(ev):
        _quit_glow.setBlurRadius(25)
        QPushButton.enterEvent(quit_btn, ev)

    def _quit_leave(ev):
        _quit_glow.setBlurRadius(0)
        QPushButton.leaveEvent(quit_btn, ev)

    quit_btn.enterEvent = _quit_enter
    quit_btn.leaveEvent = _quit_leave

    rpl.addWidget(quit_btn)

    body_lay.addWidget(rp, 1)
    card_lay.addWidget(body, 1)

    # ── Drag support ──────────────────────────────────────────────────────────
    _drag = [False, 0, 0]

    def _tb_press(ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            _drag[0] = True
            _drag[1] = ev.globalPosition().x() - dlg.x()
            _drag[2] = ev.globalPosition().y() - dlg.y()

    def _tb_move(ev):
        if _drag[0]:
            dlg.move(int(ev.globalPosition().x() - _drag[1]),
                     int(ev.globalPosition().y() - _drag[2]))

    def _tb_release(ev):
        _drag[0] = False

    tb.mousePressEvent  = _tb_press
    tb.mouseMoveEvent   = _tb_move
    tb.mouseReleaseEvent = _tb_release

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

    def _attempt():
        is_locked, wait_s = check_locked_out(CTX_Q)
        if is_locked:
            _start_cd(wait_s)
            return
        if hash_pw(pw_edit.text()) == cfg.get("password_hash", ""):
            reset_attempt_state(CTX_Q)
            log_security_event("success", CTX_Q, "quit confirmed")
            dlg.close()
            on_success()
        else:
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

    quit_btn.clicked.connect(_attempt)
    pw_edit.returnPressed.connect(_attempt)

    dlg.show()
    dlg.activateWindow()
    pw_edit.setFocus()
    QTimer.singleShot(200, lambda: (dlg.activateWindow(), pw_edit.setFocus()))

   
    _lk, _ws = check_locked_out(CTX_Q)
    if _lk:
        _start_cd(_ws)

    from PyQt6.QtCore import QEventLoop as _QEventLoop
    _local_loop = _QEventLoop()
    close_b.clicked.connect(_local_loop.quit)
    dlg.destroyed.connect(_local_loop.quit)
    _orig_close = dlg.close

    def _close_and_quit():
        _orig_close()
        _local_loop.quit()

    dlg.close = _close_and_quit
    _local_loop.exec()


def release_control_panel_lock():
    
    global _cp_currently_open
    with _cp_open_lock:
        _cp_currently_open = False
