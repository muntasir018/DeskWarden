"""
DeskWarden - ui/lock_screen.py

"""

import os
import threading

from ..core.paths import asset_path
from ..core.security import (
    hash_pw, record_wrong_attempt, check_locked_out,
    reset_attempt_state, log_security_event, PENALTY_THRES,
)
from .icon_utils import get_exe_icon_pixmap, get_exe_icon_pixmap_qt
from .ui_thread import _run_on_ui_thread


class LockScreen:
    def show(self, password_hash, app_name="Application", app_exe_path=None):
        result = {"ok": False}
        done_event = threading.Event()

        _display_name = app_name
        if _display_name.lower().endswith(".exe"):
            _display_name = _display_name[:-4]
        _exe_path = app_exe_path

        def _build_ui():
            try:
                from PyQt6.QtWidgets import (
                    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                    QLabel, QPushButton, QFrame, QLineEdit, QGraphicsDropShadowEffect,
                    QSizePolicy
                )
                from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
                from PyQt6.QtGui import (
                    QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor,
                    QLinearGradient, QKeyEvent, QPixmap
                )
            except ImportError:
                done_event.set()
                return

            _BG    = "#09070f"
            _SIDE  = "#0c0a16"
            _CARD  = "#110f1e"
            _CARD2 = "#171528"
            _BORD  = "#2a2545"
            _ACC   = "#7c3aed"
            _ACC2  = "#9d5cff"
            _FG    = "#ede9ff"
            _MUTE  = "#5a5478"
            _GREEN = "#22c55e"
            _RED   = "#ef4444"

            _qapp = QApplication.instance()
            if _qapp is None:
                _qapp = QApplication([])

            class _RCard(QFrame):
                def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=14):
                    super().__init__(parent)
                    self._bg     = QColor(bg)
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
                    grad = QLinearGradient(0, 0, 0, self.height())
                    grad.setColorAt(0.0, self._bg.lighter(116))
                    grad.setColorAt(1.0, self._bg.darker(110))
                    p.fillPath(path, QBrush(grad))
                    p.setPen(QPen(self._border, 1))
                    p.drawPath(path)

            class _IconBox(QLabel):
                def __init__(self, glyph, size=46, bg="#1e0d40", fg="#c4b5fd",
                             radius=14, parent=None):
                    super().__init__(glyph, parent)
                    self._bg = QColor(bg)
                    self._r  = radius
                    self.setFixedSize(size, size)
                    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setFont(QFont("Segoe UI Emoji", size // 3))
                    self.setStyleSheet(f"color: {fg}; background: transparent;")

                def paintEvent(self, ev):
                    p = QPainter(self)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.width(), self.height(),
                                        self._r, self._r)
                    p.fillPath(path, QBrush(self._bg))
                    super().paintEvent(ev)

            def _glow(widget, color=_ACC, radius=18):
                fx = QGraphicsDropShadowEffect()
                fx.setBlurRadius(radius)
                fx.setColor(QColor(color))
                fx.setOffset(0, 0)
                widget.setGraphicsEffect(fx)

            class _OverlayWidget(QWidget):
                def __init__(self, c1, c2, c3, parent=None):
                    super().__init__(parent)
                    self._c1, self._c2, self._c3 = c1, c2, c3
                    self._bg_pixmap = None

                def _rebuild_pixmap(self):
                    from PyQt6.QtGui import QRadialGradient
                    w, h = max(1, self.width()), max(1, self.height())
                    pm = QPixmap(w, h)
                    pm.fill(QColor(0, 0, 0))
                    p = QPainter(pm)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    cx, cy = w / 2, h * 0.46
                    radius = max(w, h) * 0.9
                    grad = QRadialGradient(cx, cy, radius)
                    grad.setColorAt(0.0, QColor(*self._c1))
                    grad.setColorAt(0.35, QColor(*self._c2))
                    grad.setColorAt(1.0, QColor(*self._c3))
                    p.fillRect(pm.rect(), QBrush(grad))
                    p.end()
                    self._bg_pixmap = pm

                def resizeEvent(self, ev):
                    self._rebuild_pixmap()
                    super().resizeEvent(ev)

                def paintEvent(self, ev):
                    if self._bg_pixmap is None:
                        self._rebuild_pixmap()
                    p = QPainter(self)
                    p.drawPixmap(0, 0, self._bg_pixmap)

            overlay = _OverlayWidget(
                (45, 26, 90, 235), (15, 10, 28, 245), (3, 2, 8, 252)
            )
            overlay.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            screen_geom = _qapp.primaryScreen().geometry()
            overlay.setGeometry(screen_geom)
            overlay.setWindowOpacity(0.0)

            modal = QWidget()
            modal.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            modal.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            _MW, _MH = 520, 292
            modal.setFixedSize(_MW, _MH)
            modal.move(
                screen_geom.x() + (screen_geom.width()  - _MW) // 2,
                screen_geom.y() + (screen_geom.height() - _MH) // 2,
            )
            modal.setStyleSheet("background: transparent;")
            modal.setWindowOpacity(0.0)

            def _block_key(obj):
                def _kp(ev):
                    if (ev.key() == Qt.Key.Key_F4 and
                            ev.modifiers() & Qt.KeyboardModifier.AltModifier):
                        ev.ignore()
                obj.keyPressEvent = _kp

            _block_key(overlay)
            _block_key(modal)

            _alive = [True]
            _loop_ref = [None]
            _focus_conn = None
            _geom_conn = None

            def _update_overlay_geometry():
                if _alive[0]:
                    overlay.setGeometry(_qapp.primaryScreen().geometry())

            _geom_conn = _qapp.primaryScreen().geometryChanged.connect(_update_overlay_geometry)

            def _finish(ok: bool):
                if not _alive[0]:
                    return
                nonlocal _focus_conn, _geom_conn
                if _focus_conn is not None:
                    try:
                        _qapp.focusWindowChanged.disconnect(_focus_conn)
                    except Exception:
                        pass
                if _geom_conn is not None:
                    try:
                        _qapp.primaryScreen().geometryChanged.disconnect(_geom_conn)
                    except Exception:
                        pass
                result["ok"] = ok
                _alive[0] = False

                try:
                    _top_timer.stop()
                except Exception:
                    pass

                FADE_STEPS    = 14
                FADE_INTERVAL = 16
                OVERLAY_MAX   = 0.70
                _fo_step      = [0]

                def _fade_out():
                    s = _fo_step[0]
                    if s > FADE_STEPS:
                        try: overlay.hide(); overlay.deleteLater()
                        except Exception: pass
                        try: modal.hide(); modal.deleteLater()
                        except Exception: pass
                        try:
                            if _loop_ref[0] is not None:
                                _loop_ref[0].quit()
                        except Exception: pass
                        done_event.set()
                        return
                    t = s / FADE_STEPS
                    eased = (1 - t) ** 2
                    try:
                        overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                        modal.setWindowOpacity(round(eased, 3))
                    except Exception:
                        pass
                    _fo_step[0] += 1
                    QTimer.singleShot(FADE_INTERVAL, _fade_out)

                _fade_out()

            # ── Main Card ────────────────────────────────────────────
            outer_lay = QVBoxLayout(modal)
            outer_lay.setContentsMargins(0, 0, 0, 0)

            card = _RCard(modal, bg=_CARD, border=_BORD, radius=22)
            outer_lay.addWidget(card)

            # ── Custom Title Bar ────────────────────────────────────
            title_bar = QWidget(card)
            title_bar.setFixedHeight(32)
            title_bar.setStyleSheet("background: transparent;")
            title_bar.setGeometry(16, 0, _MW - 32, 32)
            tbl = QHBoxLayout(title_bar)
            tbl.setContentsMargins(6, 0, 0, 0)
            # ── Logo offset adjustment (Lock Screen titlebar) ──
            _LOCK_LOGO_OFFSET_X = 3   
            _LOCK_LOGO_OFFSET_Y = 2   
            _tb_pm1 = QPixmap(asset_path("icon.png"))
            if not _tb_pm1.isNull():
                _tb_pm1 = _tb_pm1.scaled(18, 18,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                lock_icon = QLabel()
                lock_icon.setPixmap(_tb_pm1)
                lock_icon.setFixedSize(18, 18)
                lock_icon.setContentsMargins(_LOCK_LOGO_OFFSET_X, _LOCK_LOGO_OFFSET_Y, 0, 0)
                lock_icon.setStyleSheet("background: transparent;")
            else:
                lock_icon = QLabel("🔒")
                lock_icon.setFont(QFont("Segoe UI Emoji", 9))
                lock_icon.setStyleSheet(f"color: {_ACC2}; background: transparent;")
            tbl.addWidget(lock_icon)
            tb_title = QLabel("DeskWarden")
            tb_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            tb_title.setStyleSheet(f"color: {_MUTE}; background: transparent; letter-spacing: 0.5px;")
            tbl.addWidget(tb_title)
            tbl.addStretch()

            close_b = QPushButton("✕")
            close_b.setFixedSize(24, 24)
            close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            close_b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {_MUTE};
                    border: none; font-size: 9pt; border-radius: 12px; }}
                QPushButton:hover {{ background: #2a2545; color: white; }}""")
            close_b.clicked.connect(lambda: _finish(False))
            tbl.addWidget(close_b)

            # ── Body Layout ─────────────────────────────────────────
            body_lay = QHBoxLayout(card)
            body_lay.setContentsMargins(0, 28, 0, 0)
            body_lay.setSpacing(0)

            # ── LEFT PANEL ──────────────────────────────────────────
            left_w = QWidget(); left_w.setStyleSheet("background: transparent;")
            left_l = QVBoxLayout(left_w)
            left_l.setContentsMargins(30, 20, 18, 28); left_l.setSpacing(8)
            left_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(left_w, 1)

            # Gradient ring around icon
            icon_container = QWidget()
            icon_container.setFixedSize(68, 68)
            icon_container.setStyleSheet("background: transparent;")
            _app_pm = get_exe_icon_pixmap_qt(_exe_path, 48) or get_exe_icon_pixmap(_exe_path, 48)
            if _app_pm:
                app_icon_lbl = QLabel(icon_container)
                app_icon_lbl.setPixmap(_app_pm)
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")
            else:
                _fb_pm = QPixmap(asset_path("icon.png"))
                if not _fb_pm.isNull():
                    _fb_pm = _fb_pm.scaled(48, 48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    app_icon_lbl = QLabel(icon_container)
                    app_icon_lbl.setPixmap(_fb_pm)
                else:
                    app_icon_lbl = QLabel("🔒", icon_container)
                    app_icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
                    app_icon_lbl.setStyleSheet("color: #c4b5fd; background: transparent;")
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")

            ring = QWidget(icon_container)
            ring.setFixedSize(68, 68)
            ring.setStyleSheet("""
                background: transparent;
                border: 2px solid transparent;
                border-radius: 34px;
            """)
            ring.lower()

            def _draw_ring(widget, painter):
                r = widget.rect().adjusted(2, 2, -2, -2)
                grad = QLinearGradient(0, 0, r.width(), r.height())
                grad.setColorAt(0.0, QColor(_ACC))
                grad.setColorAt(0.5, QColor(_ACC2))
                grad.setColorAt(1.0, QColor("#4c1d95"))
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QBrush(grad), 2))
                painter.drawEllipse(r)

            ring.paintEvent = lambda ev: _draw_ring(ring, QPainter(ring))

            left_l.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
            left_l.addSpacing(4)

            app_lbl = QLabel(_display_name)
            app_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            app_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
            app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            app_lbl.setWordWrap(True)
            left_l.addWidget(app_lbl)

            sub_lbl = QLabel("Authentication required")
            sub_lbl.setFont(QFont("Segoe UI", 7))
            sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_l.addWidget(sub_lbl)

            # ── Vertical Divider ────────────────────────────────────
            vdiv = QFrame(); vdiv.setFixedWidth(1)
            vdiv.setStyleSheet(f"background: {_BORD};")
            body_lay.addWidget(vdiv)

            # ── RIGHT PANEL ─────────────────────────────────────────
            right_w = QWidget(); right_w.setStyleSheet("background: transparent;")
            right_l = QVBoxLayout(right_w)
            right_l.setContentsMargins(28, 20, 28, 24); right_l.setSpacing(5)
            right_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(right_w, 1)

            pw_container = QWidget()
            pw_container.setStyleSheet("background: transparent;")
            pw_cl = QHBoxLayout(pw_container)
            pw_cl.setContentsMargins(0, 0, 0, 0); pw_cl.setSpacing(0)

            pw_edit = QLineEdit()
            pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
            pw_edit.setPlaceholderText("Enter master password")
            pw_edit.setFont(QFont("Segoe UI", 10))
            pw_edit.setFixedHeight(44)
            pw_edit.setStyleSheet(f"""
                QLineEdit {{
                    background: #100c1a; color: {_FG};
                    border: 1px solid {_BORD}; border-radius: 12px;
                    padding: 0 48px 0 14px;
                    selection-background-color: {_ACC};
                }}
                QLineEdit:focus {{
                    border: 1px solid {_ACC2};
                    background: #15112e;
                }}""")

            pw_cl.addWidget(pw_edit)
            _glow(pw_container, QColor(124, 58, 237, 50), 12)
            right_l.addWidget(pw_container)

            # Show/Hide toggle (right side of field)
            eye_btn = QPushButton("Show", pw_edit)
            eye_btn.setFixedSize(36, 26)
            eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            eye_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {_MUTE};
                    border: none; font-size: 7.5pt; font-weight: 600; }}
                QPushButton:hover {{ color: {_FG}; }}""")
            def _position_eye_btn():
                eye_btn.move(pw_edit.width() - eye_btn.width() - 6, 9)
            _orig_resize = pw_edit.resizeEvent
            def _pw_resize(ev):
                _orig_resize(ev)
                _position_eye_btn()
            pw_edit.resizeEvent = _pw_resize
            _position_eye_btn()
            _pw_visible = [False]
            def _toggle_eye():
                _pw_visible[0] = not _pw_visible[0]
                pw_edit.setEchoMode(QLineEdit.EchoMode.Normal if _pw_visible[0]
                                    else QLineEdit.EchoMode.Password)
                eye_btn.setText("Hide" if _pw_visible[0] else "Show")
            eye_btn.clicked.connect(_toggle_eye)

            # Strength indicator
            strength_w = QWidget()
            strength_w.setFixedHeight(4)
            strength_w.setStyleSheet("background: #1a1535; border-radius: 2px;")
            strength_bar = QWidget(strength_w)
            strength_bar.setFixedHeight(4)
            strength_bar.setFixedWidth(0)
            strength_bar.setStyleSheet(f"""
                background: {_MUTE}; border-radius: 2px;
            """)
            right_l.addWidget(strength_w)

            def _update_strength(txt):
                l = len(txt)
                if l == 0:
                    strength_bar.setFixedWidth(0)
                    strength_bar.setStyleSheet(f"background: {_MUTE}; border-radius: 2px;")
                elif l < 4:
                    strength_bar.setFixedWidth(int(strength_w.width() * 0.3))
                    strength_bar.setStyleSheet(f"background: {_RED}; border-radius: 2px;")
                elif l < 8:
                    strength_bar.setFixedWidth(int(strength_w.width() * 0.6))
                    strength_bar.setStyleSheet(f"background: #f59e0b; border-radius: 2px;")
                else:
                    strength_bar.setFixedWidth(strength_w.width())
                    strength_bar.setStyleSheet(f"background: {_GREEN}; border-radius: 2px;")

            pw_edit.textChanged.connect(_update_strength)

            # Error label
            err_lbl = QLabel("")
            _err_font1 = QFont("Segoe UI", 8)
            _err_font1.setFamilies(["Segoe UI", "Segoe UI Symbol"])
            err_lbl.setFont(_err_font1)
            err_lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
            err_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            err_lbl.setWordWrap(True)
            err_lbl.setFixedHeight(12)
            right_l.addWidget(err_lbl)

            # Unlock button
            unlock_btn = QPushButton("Unlock")
            unlock_btn.setFixedHeight(44)
            unlock_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            unlock_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            unlock_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {_ACC}, stop:1 #5b21b6);
                    color: white; border: none; border-radius: 12px;
                    padding: 0 20px; letter-spacing: 0.5px;
                }}
                QPushButton:hover  {{ background: {_ACC2}; }}
                QPushButton:pressed {{ background: #4c1d95; }}
                QPushButton:disabled {{
                    background: {_CARD2}; color: {_MUTE};
                }}""")
            _glow(unlock_btn, QColor(124, 58, 237, 140), 18)
            right_l.addWidget(unlock_btn)

            # Hint
            hint_lbl = QLabel("Press Enter ↵")
            hint_lbl.setFont(QFont("Segoe UI", 7))
            hint_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(hint_lbl)

            # Status
            stat_w = QWidget(); stat_w.setStyleSheet("background: transparent;")
            statl = QHBoxLayout(stat_w)
            statl.setContentsMargins(0, 0, 0, 0); statl.setSpacing(5)
            statl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot_s = QLabel(); dot_s.setFixedSize(5, 5)
            dot_s.setStyleSheet(f"background: {_GREEN}; border-radius: 3px;")
            _glow(dot_s, _GREEN, 6)
            statl.addWidget(dot_s)
            stl = QLabel("SHA-256 Encrypted")
            stl.setFont(QFont("Segoe UI", 6))
            stl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            statl.addWidget(stl)
            right_l.addWidget(stat_w)

            overlay.show()
            modal.show()

            FADE_STEPS    = 14
            FADE_INTERVAL = 16
            OVERLAY_MAX   = 0.70
            _fade_step    = [0]

            def _fade_in():
                s = _fade_step[0]
                if s > FADE_STEPS:
                    return
                t = s / FADE_STEPS
                eased = 1 - (1 - t) ** 2
                try:
                    overlay.setWindowOpacity(round(eased * OVERLAY_MAX, 3))
                    modal.setWindowOpacity(round(eased, 3))
                except Exception:
                    pass
                _fade_step[0] += 1
                if _fade_step[0] <= FADE_STEPS:
                    QTimer.singleShot(FADE_INTERVAL, _fade_in)

            QTimer.singleShot(30, _fade_in)

            _drag = [False, 0, 0]
            def _tb_press(ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    _drag[0] = True
                    _drag[1] = ev.globalPosition().x() - modal.x()
                    _drag[2] = ev.globalPosition().y() - modal.y()
            def _tb_move(ev):
                if _drag[0]:
                    modal.move(
                        int(ev.globalPosition().x() - _drag[1]),
                        int(ev.globalPosition().y() - _drag[2])
                    )
            def _tb_release(ev):
                _drag[0] = False
            card.mousePressEvent   = _tb_press
            card.mouseMoveEvent    = _tb_move
            card.mouseReleaseEvent = _tb_release

            _raising = [False]

            def _raise_zorder():
                if not _alive[0] or _raising[0]:
                    return
                _raising[0] = True
                try:
                    overlay.raise_()
                    modal.raise_()
                except Exception:
                    pass
                finally:
                    _raising[0] = False

            _top_timer = QTimer()
            _top_timer.timeout.connect(_raise_zorder)
            _top_timer.start(300)

            try:
                _focus_conn = _qapp.focusWindowChanged.connect(lambda *_: _raise_zorder())
            except Exception:
                pass

            ctx_key = f"App:{app_name}"

            def _start_countdown(seconds):
                pw_edit.setEnabled(False)
                unlock_btn.setEnabled(False)
                _cd = [seconds]
                def _tick():
                    if not _alive[0]:
                        return
                    r = _cd[0]
                    if r <= 0:
                        pw_edit.setEnabled(True)
                        unlock_btn.setEnabled(True)
                        unlock_btn.setText("Unlock")
                        err_lbl.setText("")
                        pw_edit.setFocus()
                        return
                    err_lbl.setText(f"🔒︎ Locked — try again in {r}s")
                    unlock_btn.setText(f"⏳  Wait {r}s")
                    _cd[0] -= 1
                    QTimer.singleShot(1000, _tick)
                _tick()

            def attempt():
                is_locked, wait_s = check_locked_out(ctx_key)
                if is_locked:
                    _start_countdown(wait_s)
                    return
                if hash_pw(pw_edit.text()) == password_hash:
                    reset_attempt_state(ctx_key)
                    log_security_event("success", ctx_key, "unlocked")
                    _top_timer.stop()
                    _finish(True)
                else:
                    state = record_wrong_attempt(ctx_key)
                    pw_edit.clear()
                    if state["locked"]:
                        _start_countdown(state["wait"])
                    else:
                        rem = PENALTY_THRES - state["count"]
                        if rem > 0:
                            err_lbl.setText(f"Wrong password. {rem} attempt(s) remaining.")
                        else:
                            err_lbl.setText("Wrong password.")
                    pw_edit.setFocus()

            unlock_btn.clicked.connect(attempt)
            pw_edit.returnPressed.connect(attempt)
            modal.activateWindow()
            pw_edit.setFocus()
            QTimer.singleShot(300, lambda: (modal.activateWindow(), pw_edit.setFocus()))

            _lk, _ws = check_locked_out(ctx_key)
            if _lk:
                _start_countdown(_ws)

            from PyQt6.QtCore import QEventLoop as _QEventLoop
            _local_loop = _QEventLoop()
            _loop_ref[0] = _local_loop
            _local_loop.exec()

        _run_on_ui_thread(_build_ui)
        done_event.wait()
        return result["ok"]

