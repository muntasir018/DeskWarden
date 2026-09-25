"""
DeskWarden - ui/control_panel_ui/window_chrome.py
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QCursor, QPainterPath, QRegion, QBitmap, QPainter, QBrush

from ...core.updater import check_for_update_auto_async, get_cached_update_snapshot
from ...core.logging_utils import dlog

from .theme import _BG, _CARD2, _BORD, _ACC, _FG

# 5 minutes of user inactivity (idle timeout)
IDLE_TIMEOUT_MS = 5 * 60 * 1000


class _WindowChromeMixin:

    # ── Idle timeout (auto-close after 5 min of inactivity) ─────────────

    def _setup_idle_timer(self):
        if not hasattr(self, "_idle_timer"):
            self._idle_timer = QTimer(self)
            self._idle_timer.setSingleShot(True)
            self._idle_timer.timeout.connect(self._on_idle_timeout)
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    app.installEventFilter(self)
            except Exception:
                pass
        self._reset_idle_timer()

    def _reset_idle_timer(self):
        timer = getattr(self, "_idle_timer", None)
        if timer is not None:
            timer.start(IDLE_TIMEOUT_MS)

    def _on_idle_timeout(self):
        try:
            dlog("INFO", "ControlPanel: auto-closing due to 5 minutes of inactivity (idle timeout)")
        except Exception:
            pass
        self.close()

    def eventFilter(self, obj, ev):
        try:
            if ev.type() in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseMove,
                QEvent.Type.KeyPress,
                QEvent.Type.KeyRelease,
                QEvent.Type.Wheel,
                QEvent.Type.TouchBegin,
                QEvent.Type.TouchUpdate,
            ):
                self._reset_idle_timer()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    # ── Qt events ────────────────────────────────────────────────────────

    def closeEvent(self, ev):
        ev.accept()
        try:
            if getattr(self, "_idle_timer", None):
                self._idle_timer.stop()
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
        except Exception:
            pass
        try:
            if getattr(self, "_status_rotator", None):
                self._status_rotator.stop()
            if getattr(self, "_status_spinner", None):
                self._status_spinner.stop()
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._setup_idle_timer()
        self._update_window_mask()
        self._update_handles()
        self.repaint()
        self._refresh_settings_badge()
        _cached = get_cached_update_snapshot()
        if _cached.get("checked") and _cached.get("latest"):
            self._update_result_pending = _cached
            self._apply_update_result()
            from PyQt6.QtCore import QTimer as _QT2
            _QT2.singleShot(0, lambda: self._maybe_show_catalog(_cached))

        if not getattr(self, "_auto_checked_update", False):
            self._auto_checked_update = True
            if self._cfg.get("auto_update", True):
                def _silent_check(res):
                    try:
                        sig = getattr(self, "_update_result_signal", None)
                        if sig is not None:
                            sig.emit(res, False)
                        else:
                            self._update_result_pending = res
                            self._apply_update_result()
                    except Exception:
                        pass

                check_for_update_auto_async(callback=_silent_check)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_window_mask()
        self._update_handles()

        ov = getattr(self, "_switch_overlay", None)
        if ov is not None:
            ov.setGeometry(self._content.rect())

    def _update_window_mask(self, radius=14.0):
        try:
            w = self.width()
            h = self.height()
            if w <= 0 or h <= 0:
                return
            path = QPainterPath()
            path.addRoundedRect(0.0, 0.0, float(w), float(h), float(radius), float(radius))
            mask = QBitmap(self.size())
            mask.fill(Qt.GlobalColor.color0)
            p = QPainter(mask)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.fillPath(path, QBrush(Qt.GlobalColor.color1))
            p.end()
            self.setMask(QRegion(mask))
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── Resize handles (transparent edge widgets) ───────────────────────

    def _make_handles(self):
        """Create 8 transparent resize-handle widgets on top of window."""
        B = 7
        win = self

        _cur = {
            "L":  Qt.CursorShape.SizeHorCursor,
            "R":  Qt.CursorShape.SizeHorCursor,
            "T":  Qt.CursorShape.SizeVerCursor,
            "B":  Qt.CursorShape.SizeVerCursor,
            "TL": Qt.CursorShape.SizeFDiagCursor,
            "TR": Qt.CursorShape.SizeBDiagCursor,
            "BL": Qt.CursorShape.SizeBDiagCursor,
            "BR": Qt.CursorShape.SizeFDiagCursor,
        }

        class _Handle(QWidget):
            def __init__(self_, edge):
                super().__init__(win)
                self_._edge = edge
                self_._dragging = False
                self_._start_geom = None
                self_._start_mouse = None
                self_.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                self_.setCursor(QCursor(_cur[edge]))
                self_.raise_()

            def mousePressEvent(self_, ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self_._dragging   = True
                    self_._start_geom  = win.geometry()
                    self_._start_mouse = ev.globalPosition().toPoint()
                    win._drag_pos = None

            def mouseMoveEvent(self_, ev):
                if not self_._dragging:
                    return
                gpos = ev.globalPosition().toPoint()
                dx   = gpos.x() - self_._start_mouse.x()
                dy   = gpos.y() - self_._start_mouse.y()
                sg   = self_._start_geom
                minW = win.minimumWidth()
                minH = win.minimumHeight()
                x, y, w, h = sg.x(), sg.y(), sg.width(), sg.height()
                e = self_._edge
                if "R" in e:
                    w = max(minW, sg.width()  + dx)
                if "B" in e:
                    h = max(minH, sg.height() + dy)
                if "L" in e:
                    nw = max(minW, sg.width() - dx)
                    x  = sg.x() + (sg.width() - nw)
                    w  = nw
                if "T" in e:
                    nh = max(minH, sg.height() - dy)
                    y  = sg.y() + (sg.height() - nh)
                    h  = nh
                win.setGeometry(x, y, w, h)

            def mouseReleaseEvent(self_, ev):
                self_._dragging = False

        self._handles = {}
        for edge in ("L", "R", "T", "B", "TL", "TR", "BL", "BR"):
            h = _Handle(edge)
            h.show()
            self._handles[edge] = h

    def _update_handles(self):
        """Reposition all 8 resize handles to match current window size."""
        if not hasattr(self, "_handles"):
            self._make_handles()
        B = 7
        w = self.width()
        h = self.height()
        geom = {
            "TL": (0,       0,       B,   B),
            "T":  (B,       0,       w-2*B, B),
            "TR": (w-B,     0,       B,   B),
            "L":  (0,       B,       B,   h-2*B),
            "R":  (w-B,     B,       B,   h-2*B),
            "BL": (0,       h-B,     B,   B),
            "B":  (B,       h-B,     w-2*B, B),
            "BR": (w-B,     h-B,     B,   B),
        }
        for edge, (ex, ey, ew, eh) in geom.items():
            hdl = self._handles[edge]
            hdl.setGeometry(ex, ey, ew, eh)
            hdl.raise_()

    # ── Global stylesheet ────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {_BG};
            }}
            QMainWindow > QWidget {{
                background: {_BG}; color: {_FG};
                font-family: 'Segoe UI';
            }}
            QWidget {{
                background: {_BG}; color: {_FG};
                font-family: 'Segoe UI';
            }}
            QScrollArea {{ border: none; background: {_BG}; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border-radius: 3px;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORD}; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {_ACC}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QLineEdit {{
                background: #08061a; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 8px;
                padding: 6px 10px; font-size: 10pt;
                selection-background-color: {_ACC};
            }}
            QCheckBox {{ color: {_FG}; }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border: 1px solid {_BORD}; border-radius: 5px;
                background: {_CARD2};
            }}
            QCheckBox::indicator:checked {{
                background: {_ACC}; border-color: {_ACC};
            }}
        """)
