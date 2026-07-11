"""
DeskWarden - ui/control_panel_ui/update_dialog.py

"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGraphicsDropShadowEffect, QApplication,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QCursor

from ...core.logging_utils import dlog
from ...core.updater import CURRENT_VERSION
from ...core.website_link import get_website_url
from .theme import _CARD, _CARD2, _BORD, _FG, _MUTE, _ACC2
from .widgets import _Card


class _UpdateCatalogDialog(QWidget):
   
    def __init__(self, version, notes, download_url, release_url,
                 on_skip=None, parent=None):
        super().__init__(parent)
        self._on_skip = on_skip
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        _DIALOG_W = 440
        _NOTES_MIN_H = 50
        _NOTES_MAX_H = 220

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = _Card(self, bg=_CARD, border=_BORD, radius=16)
        outer.addWidget(card)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(26, 20, 26, 20); cl.setSpacing(10)

        hrow = QHBoxLayout()
        badge = QLabel("🎉")
        badge.setFont(QFont("Segoe UI Emoji", 22))
        badge.setStyleSheet("background: transparent;")
        hrow.addWidget(badge)
        tcol = QVBoxLayout(); tcol.setSpacing(1)
        title = QLabel(f"New version available — {version}")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_FG}; background: transparent;")
        title.setWordWrap(True)
        sub = QLabel(f"You're currently on {CURRENT_VERSION}")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        tcol.addWidget(title); tcol.addWidget(sub)
        hrow.addLayout(tcol, 1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {_MUTE};
                border: none; border-radius: 13px; font-size: 11pt; }}
            QPushButton:hover {{ background: {_CARD2}; color: {_FG}; }}""")
        close_btn.clicked.connect(self.close)
        hrow.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        cl.addLayout(hrow)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(sep)

        notes_lbl = QLabel("What's new")
        notes_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        notes_lbl.setStyleSheet(f"color: {_ACC2}; background: transparent;")
        cl.addWidget(notes_lbl)

        notes_scroll = QScrollArea()
        notes_scroll.setWidgetResizable(True)
        notes_scroll.setStyleSheet("background: transparent; border: none;")
        notes_inner = QWidget(); notes_inner.setStyleSheet("background: transparent;")
        nil = QVBoxLayout(notes_inner)
        nil.setContentsMargins(2, 2, 2, 2); nil.setSpacing(6)
        if notes:
            for line in notes:
                item = QLabel(f"•  {line}")
                item.setFont(QFont("Segoe UI", 9))
                item.setStyleSheet(f"color: {_FG}; background: transparent;")
                item.setWordWrap(True)
                nil.addWidget(item)
        else:
            item = QLabel("See the release page for full details.")
            item.setFont(QFont("Segoe UI", 9))
            item.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            nil.addWidget(item)
        nil.addStretch()
        notes_scroll.setWidget(notes_inner)
        cl.addWidget(notes_scroll)
        self._notes_scroll = notes_scroll
        self._notes_inner = notes_inner
        self._dialog_w = _DIALOG_W
        self._notes_min_h = _NOTES_MIN_H
        self._notes_max_h = _NOTES_MAX_H

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        gh_btn = QPushButton("🌐  Visit Website")
        gh_btn.setFixedHeight(36)
        gh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        gh_btn.setFont(QFont("Segoe UI", 9))
        gh_btn.setStyleSheet("""
            QPushButton { background: rgba(59, 130, 246, 0.12); color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.45); border-radius: 9px; padding: 0 12px; }
            QPushButton:hover { background: rgba(59, 130, 246, 0.22); color: #93c5fd;
                border: 1px solid #60a5fa; }""")
        def _open_release():
            import webbrowser
            webbrowser.open(get_website_url())
            self.close()
        gh_btn.clicked.connect(_open_release)
        btn_row.addWidget(gh_btn, 1)

        self._gh_glow = QGraphicsDropShadowEffect()
        self._gh_glow.setBlurRadius(0)
        self._gh_glow.setColor(QColor(59, 130, 246, 150))
        self._gh_glow.setOffset(0, 0)
        gh_btn.setGraphicsEffect(self._gh_glow)

        def _gh_animate(target_radius, duration):
            if getattr(self, "_gh_glow_anim", None) is not None:
                self._gh_glow_anim.stop()
            anim = QPropertyAnimation(self._gh_glow, b"blurRadius", self)
            anim.setDuration(duration)
            anim.setStartValue(self._gh_glow.blurRadius())
            anim.setEndValue(target_radius)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._gh_glow_anim = anim 

        def _gh_enter(ev):
            _gh_animate(16, 180)
            QPushButton.enterEvent(gh_btn, ev)

        def _gh_leave(ev):
            _gh_animate(0, 220)
            QPushButton.leaveEvent(gh_btn, ev)

        gh_btn.enterEvent = _gh_enter
        gh_btn.leaveEvent = _gh_leave

        dl_btn = QPushButton("⬇  Download Now")
        dl_btn.setFixedHeight(36)
        dl_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        dl_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        dl_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #22c55e, stop:1 #16a34a); color: #06170d;
                border: none; border-radius: 9px; padding: 0 12px; }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #34d399, stop:1 #22c55e); }""")
        def _open_download():
            import webbrowser
            webbrowser.open(download_url or release_url)
            self.close()
        dl_btn.clicked.connect(_open_download)
        btn_row.addWidget(dl_btn, 1)

        self._dl_glow = QGraphicsDropShadowEffect()
        self._dl_glow.setBlurRadius(0)
        self._dl_glow.setColor(QColor(52, 211, 153, 150))
        self._dl_glow.setOffset(0, 0)
        dl_btn.setGraphicsEffect(self._dl_glow)

        def _dl_animate(target_radius, duration):
            if getattr(self, "_dl_glow_anim", None) is not None:
                self._dl_glow_anim.stop()
            anim = QPropertyAnimation(self._dl_glow, b"blurRadius", self)
            anim.setDuration(duration)
            anim.setStartValue(self._dl_glow.blurRadius())
            anim.setEndValue(target_radius)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            self._dl_glow_anim = anim  

        def _dl_enter(ev):
            _dl_animate(16, 180)
            QPushButton.enterEvent(dl_btn, ev)

        def _dl_leave(ev):
            _dl_animate(0, 220)
            QPushButton.leaveEvent(dl_btn, ev)

        dl_btn.enterEvent = _dl_enter
        dl_btn.leaveEvent = _dl_leave

        cl.addLayout(btn_row)


        skip_btn = QPushButton("⏭  Skip for today")
        skip_btn.setFixedHeight(28)
        skip_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        skip_btn.setFont(QFont("Segoe UI", 8))
        skip_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {_MUTE}; border: none; }}
            QPushButton:hover {{ color: #f87171; }}""")
        def _do_skip():
            if self._on_skip:
                try: self._on_skip()
                except Exception: pass
            self.close()
        skip_btn.clicked.connect(_do_skip)
        cl.addWidget(skip_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self._skip_glow2 = QGraphicsDropShadowEffect()
        self._skip_glow2.setBlurRadius(0)
        self._skip_glow2.setColor(QColor("#f87171"))
        self._skip_glow2.setOffset(0, 0)
        skip_btn.setGraphicsEffect(self._skip_glow2)

        def _skip2_enter(ev):
            self._skip_glow2.setBlurRadius(14)
            QPushButton.enterEvent(skip_btn, ev)

        def _skip2_leave(ev):
            self._skip_glow2.setBlurRadius(0)
            QPushButton.leaveEvent(skip_btn, ev)

        skip_btn.enterEvent = _skip2_enter
        skip_btn.leaveEvent = _skip2_leave

        self._resize_to_content()

    def _resize_to_content(self):
        
        try:
            content_w = self._dialog_w - 52 - 4
            self._notes_inner.setFixedWidth(content_w)
            self._notes_inner.layout().activate()
            needed = self._notes_inner.sizeHint().height()
            notes_h = max(self._notes_min_h, min(needed, self._notes_max_h))
            self._notes_scroll.setFixedHeight(notes_h)

            self.layout().activate()
            total_h = self.sizeHint().height()
            if not total_h or total_h < 200:
                raise ValueError(f"unreasonable computed height: {total_h}")

            self.setFixedSize(self._dialog_w, total_h)
            sg = QApplication.instance().primaryScreen().geometry()
            self.move(sg.x() + (sg.width() - self._dialog_w) // 2,
                      sg.y() + (sg.height() - total_h) // 2)
        except Exception as e:
            dlog("ERROR", f"_UpdateCatalogDialog._resize_to_content failed, "
                           f"falling back to fixed size: {type(e).__name__}: {e}")
            self.setFixedSize(self._dialog_w, 420)
            sg = QApplication.instance().primaryScreen().geometry()
            self.move(sg.x() + (sg.width() - self._dialog_w) // 2,
                      sg.y() + (sg.height() - 420) // 2)

