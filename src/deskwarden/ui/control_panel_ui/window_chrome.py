"""
DeskWarden - ui/control_panel_ui/window_chrome.py
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from ...core.updater import check_for_update_auto_async, get_cached_update_snapshot

from .theme import _BG, _CARD2, _BORD, _ACC, _FG


class _WindowChromeMixin:

    # ── Qt events ────────────────────────────────────────────────────────

    def closeEvent(self, ev):

        ev.accept()
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
        self._update_handles()
        self.repaint()
        self._refresh_settings_badge()
        _cached = get_cached_update_snapshot()
        if _cached.get("checked") and _cached.get("latest"):
            from PyQt6.QtCore import QTimer as _QT2
            _QT2.singleShot(0, lambda: self._maybe_show_catalog(_cached))

        if not getattr(self, "_auto_checked_update", False):
            self._auto_checked_update = True
            if self._cfg.get("auto_update", True):
                def _silent_check(res):
                    self._update_result_pending = res
                    from PyQt6.QtCore import QTimer as _QT
                    _QT.singleShot(0, self._apply_update_result)

                check_for_update_auto_async(callback=_silent_check)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_handles()

        ov = getattr(self, "_switch_overlay", None)
        if ov is not None:
            ov.setGeometry(self._content.rect())

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
