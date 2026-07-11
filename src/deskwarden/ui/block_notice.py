"""
DeskWarden - ui/block_notice.py

"""

import os
import threading

from ..core.paths import asset_path
from .icon_utils import get_exe_icon_pixmap, get_exe_icon_pixmap_qt
from .ui_thread import _run_on_ui_thread


class BlockNotice:
    def show(self, app_name="Application", app_exe_path=None):
        done_event = threading.Event()

        _display_name = app_name
        if _display_name.lower().endswith(".exe"):
            _display_name = _display_name[:-4]
        _exe_path = app_exe_path

        def _build_ui():
            try:
                from PyQt6.QtWidgets import (
                    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect
                )
                from PyQt6.QtCore import Qt, QTimer
                from PyQt6.QtGui import (
                    QColor, QPainter, QPainterPath, QBrush, QPen, QFont, QCursor,
                    QLinearGradient, QPixmap
                )
            except ImportError:
                done_event.set()
                return

            _BG    = "#09070f"
            _SIDE  = "#120810"
            _CARD  = "#110f1e"
            _BORD  = "#3d1020"
            _RED   = "#ef4444"
            _FG    = "#fca5a5"
            _MUTE  = "#5a5478"
            _ACC   = "#7f1d1d"

            _qapp = QApplication.instance()
            if _qapp is None:
                _qapp = QApplication([])

            class _RCard(QFrame):
                def __init__(self, parent=None, bg=_CARD, border=_BORD, radius=16):
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
                def __init__(self, glyph, size=46, bg="#200810", fg="#ef4444",
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

            def _glow(widget, color=_RED, radius=18):
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
                (80, 20, 30, 235), (20, 8, 14, 245), (3, 2, 8, 252)
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
            modal.setWindowOpacity(0.0)

            _alive = [True]
            _loop_ref = [None]
            _focus_conn = None
            _geom_conn = None

            def _update_overlay_geometry():
                if _alive[0]:
                    overlay.setGeometry(_qapp.primaryScreen().geometry())

            _geom_conn = _qapp.primaryScreen().geometryChanged.connect(_update_overlay_geometry)

            def _finish():
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

            # ── Title bar ───────────────────────────────────────────
            title_bar = QWidget(card)
            title_bar.setFixedHeight(32)
            title_bar.setStyleSheet("background: transparent;")
            title_bar.setGeometry(16, 0, _MW - 32, 32)
            tbl = QHBoxLayout(title_bar)
            tbl.setContentsMargins(6, 0, 0, 0)
            # ── Logo offset adjustment (Block Notice titlebar) ──
            _BLOCK_LOGO_OFFSET_X = 3   
            _BLOCK_LOGO_OFFSET_Y = 2   
            _tb_pm2 = QPixmap(asset_path("icon.png"))
            if not _tb_pm2.isNull():
                _tb_pm2 = _tb_pm2.scaled(18, 18,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                lock_icon = QLabel()
                lock_icon.setPixmap(_tb_pm2)
                lock_icon.setFixedSize(18, 18)
                lock_icon.setContentsMargins(_BLOCK_LOGO_OFFSET_X, _BLOCK_LOGO_OFFSET_Y, 0, 0)
                lock_icon.setStyleSheet("background: transparent;")
            else:
                lock_icon = QLabel("🚫")
                lock_icon.setFont(QFont("Segoe UI Emoji", 9))
                lock_icon.setStyleSheet(f"color: {_RED}; background: transparent;")
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
                QPushButton:hover {{ background: #3d1020; color: white; }}""")
            close_b.clicked.connect(_finish)
            tbl.addWidget(close_b)

            # ── Body ────────────────────────────────────────────────
            body_lay = QHBoxLayout(card)
            body_lay.setContentsMargins(0, 28, 0, 0); body_lay.setSpacing(0)

            # LEFT
            left_w = QWidget(); left_w.setStyleSheet("background: transparent;")
            left_l = QVBoxLayout(left_w)
            left_l.setContentsMargins(30, 20, 18, 28); left_l.setSpacing(8)
            left_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(left_w, 1)

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
                _fb2_pm = QPixmap(asset_path("icon.png"))
                if not _fb2_pm.isNull():
                    _fb2_pm = _fb2_pm.scaled(48, 48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    app_icon_lbl = QLabel(icon_container)
                    app_icon_lbl.setPixmap(_fb2_pm)
                else:
                    app_icon_lbl = QLabel("🚫", icon_container)
                    app_icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
                    app_icon_lbl.setStyleSheet("color: #f87171; background: transparent;")
                app_icon_lbl.setFixedSize(48, 48)
                app_icon_lbl.move(10, 10)
                app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                app_icon_lbl.setStyleSheet("background: transparent;")

            ring = QWidget(icon_container)
            ring.setFixedSize(68, 68)
            ring.setStyleSheet("background: transparent; border: 2px solid transparent; border-radius: 34px;")
            ring.lower()
            def _draw_ring(widget, painter):
                r = widget.rect().adjusted(2, 2, -2, -2)
                grad = QLinearGradient(0, 0, r.width(), r.height())
                grad.setColorAt(0.0, QColor("#b91c1c"))
                grad.setColorAt(0.5, QColor(_RED))
                grad.setColorAt(1.0, QColor("#7f1d1d"))
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QBrush(grad), 2))
                painter.drawEllipse(r)
            ring.paintEvent = lambda ev: _draw_ring(ring, QPainter(ring))

            left_l.addWidget(icon_container, 0, Qt.AlignmentFlag.AlignHCenter)
            left_l.addSpacing(4)

            app_lbl = QLabel(_display_name)
            app_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            app_lbl.setStyleSheet("color: #fca5a5; background: transparent;")
            app_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            app_lbl.setWordWrap(True)
            left_l.addWidget(app_lbl)

            sub_lbl = QLabel("Permanently blocked")
            sub_lbl.setFont(QFont("Segoe UI", 7))
            sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_l.addWidget(sub_lbl)

            # DIVIDER
            vdiv = QFrame(); vdiv.setFixedWidth(1)
            vdiv.setStyleSheet(f"background: {_BORD};")
            body_lay.addWidget(vdiv)

            # RIGHT
            right_w = QWidget(); right_w.setStyleSheet("background: transparent;")
            right_l = QVBoxLayout(right_w)
            right_l.setContentsMargins(28, 20, 28, 24); right_l.setSpacing(12)
            right_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_lay.addWidget(right_w, 1)

            msg1 = QLabel("Access Denied")
            msg1.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            msg1.setStyleSheet("color: #f5a3a3; background: transparent; letter-spacing: 0.5px;")
            msg1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(msg1)

            msg2 = QLabel("This application is permanently blocked.\nChange the mode in Control Panel to unblock.")
            msg2.setFont(QFont("Segoe UI", 8))
            msg2.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            msg2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg2.setWordWrap(True)
            right_l.addWidget(msg2)

            close_btn = QPushButton("✕  Close")
            close_btn.setFixedHeight(44)
            close_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #b91c1c, stop:1 #7f1d1d);
                    color: white; border: none; border-radius: 12px;
                    padding: 0 20px; letter-spacing: 0.5px;
                }}
                QPushButton:hover  {{ background: #dc2626; }}
                QPushButton:pressed {{ background: #7f1d1d; }}""")
            _glow(close_btn, QColor(239, 68, 68, 160), 22)
            close_btn.clicked.connect(_finish)
            right_l.addWidget(close_btn)

            sl = QLabel("Permanent Restriction · DeskWarden")
            sl.setFont(QFont("Segoe UI", 6))
            sl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_l.addWidget(sl)

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

            from PyQt6.QtCore import QEventLoop as _QEventLoop
            _local_loop = _QEventLoop()
            _loop_ref[0] = _local_loop
            _local_loop.exec()

        _run_on_ui_thread(_build_ui)
        done_event.wait()
        return False

