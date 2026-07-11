"""
DeskWarden - ui/control_panel_ui/nav_shell.py
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QButtonGroup, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QFont, QCursor, QPixmap

from ...core.paths import asset_path
from ...core.logging_utils import dlog

from .theme import _BG, _SIDE, _CARD, _BORD, _ACC, _FG, _MUTE, _GREEN, _glow
from .widgets import _IconBox, _NavBtn, _StatusSpinner, _RotatingStatus
from .status_items import _sidebar_status_items


class _NavShellMixin:

    # ── Build ────────────────────────────────────────────────────────────

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        class _DragBar(QWidget):
            def mousePressEvent(self_, ev):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            def mouseMoveEvent(self_, ev):
                if self._drag_pos is not None and ev.buttons() == Qt.MouseButton.LeftButton:
                    self.move(ev.globalPosition().toPoint() - self._drag_pos)
            def mouseReleaseEvent(self_, ev):
                self._drag_pos = None
        tb = _DragBar(); tb.setFixedHeight(42)
        tb.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0d0b1a, stop:1 {_SIDE});")
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(16, 0, 12, 0)
        _traffic_colors = ("#a855f7", "#22d3ee", "#E74C3C", "#89F336")
        _traffic_dots = []
        for dc in _traffic_colors:
            dot = QLabel(); dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background: {dc}; border-radius: 6px;")
            try:
                from PyQt6.QtWidgets import QGraphicsOpacityEffect as _DotOpacityFx
                _fx = _DotOpacityFx(dot)
                _fx.setOpacity(1.0)
                dot.setGraphicsEffect(_fx)
                dot._opacity_fx = _fx
            except Exception:
                pass
            tbl.addWidget(dot)
            _traffic_dots.append(dot)
        tb._traffic_dots = _traffic_dots

        def _animate_traffic_dots():
            try:
                import random as _dotrandom
                live_dots = [d for d in _traffic_dots if getattr(d, "_opacity_fx", None) is not None]
                if live_dots:
                    target_dot = _dotrandom.choice(live_dots)
                    target_opacity = _dotrandom.choice([0.3, 0.45, 1.0, 1.0])
                    anim = QPropertyAnimation(target_dot._opacity_fx, b"opacity")
                    anim.setDuration(_dotrandom.randint(450, 900))
                    anim.setStartValue(target_dot._opacity_fx.opacity())
                    anim.setEndValue(target_opacity)
                    anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
                    target_dot._cur_anim = anim
                    anim.start()
            except Exception:
                pass
            finally:
                try:
                    from PyQt6.QtCore import QTimer as _DotTimer
                    _DotTimer.singleShot(__import__("random").randint(500, 1400), _animate_traffic_dots)
                except Exception:
                    pass

        try:
            from PyQt6.QtCore import QTimer as _DotTimer
            _DotTimer.singleShot(400, _animate_traffic_dots)
        except Exception:
            pass
        tbl.addSpacing(10)
        tl = QLabel("DeskWarden  ·  Control Panel")
        tl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        tl.setStyleSheet(f"color: #7a70a0; background: transparent;")
        tbl.addWidget(tl); tbl.addStretch()
        close_b = QPushButton("✕"); close_b.setFixedSize(28, 22)
        close_b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {_MUTE};
                border: none; font-size: 10pt; border-radius: 4px; }}
            QPushButton:hover {{ background: #7f1d1d; color: white;
                border-radius: 4px; }}""")
        close_b.clicked.connect(self.close)
        tbl.addWidget(close_b)
        rl.addWidget(tb)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORD};")
        rl.addWidget(sep)

        body = QWidget(); bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)

        sb = QWidget(); sb.setMinimumWidth(216); sb.setMaximumWidth(280)
        sb.setStyleSheet(f"background: {_SIDE};")
        sbl = QVBoxLayout(sb)
        sbl.setContentsMargins(0, 0, 0, 0); sbl.setSpacing(0)

        brand = QWidget()
        brand.setStyleSheet(f"background: {_SIDE};")
        brandl = QHBoxLayout(brand)
        brandl.setContentsMargins(16, 18, 16, 18); brandl.setSpacing(12)
        # ── Load full icon from assets folder ──
        _full_icon_path = asset_path("deskwarden_full_icon.png")
        _pm = QPixmap(_full_icon_path)
        li = None
        if not _pm.isNull():
            _pm = _pm.scaled(56, 56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            class _LogoBox(QWidget):
                def __init__(self, px, sz=56, parent=None):
                    super().__init__(parent)
                    self._px = px
                    self.setFixedSize(sz, sz)
                    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                def paintEvent(self, ev):
                    p2 = QPainter(self)
                    p2.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    p2.drawPixmap(0, 0, self.width(), self.height(), self._px)
                    p2.end()
            li = _LogoBox(_pm, 56)
        if li is None:
            li = _IconBox("🔒", 56, "#1e0840", "#c4b5fd", 14)
        _glow(li, _ACC, 16)
        brandl.addWidget(li)
        btl = QVBoxLayout(); btl.setSpacing(2)
        anl = QLabel("DeskWarden")
        anl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        anl.setStyleSheet(
            "color: #f5f0ff;"
            " background: transparent;"
        )
        _glow(anl, QColor(200, 180, 255, 80), 16)
        avl = QLabel("v1.1.0  ·  Windows")
        avl.setFont(QFont("Segoe UI", 8))
        avl.setStyleSheet(f"color: #7c6da8; background: transparent; letter-spacing: 0.3px;")
        btl.addWidget(anl); btl.addWidget(avl)
        brandl.addLayout(btl)
        sbl.addWidget(brand)

        ssep = QFrame(); ssep.setFixedHeight(1)
        ssep.setStyleSheet(f"background: {_BORD};")
        sbl.addWidget(ssep); sbl.addSpacing(8)

        def _make_pulsing_dot(size=9, color="#ef4444"):
            """A small filled circle that continuously breathes
            (opacity fades 1.0 → 0.35 → 1.0 forever). Used for any
            'something needs attention' indicator — e.g. the Settings
            nav badge when an update is available."""
            dot = QLabel()
            dot.setFixedSize(size, size)
            dot.setStyleSheet(
                f"background: {color}; border-radius: {size // 2}px;")
            fx = QGraphicsOpacityEffect(dot)
            fx.setOpacity(1.0)
            dot.setGraphicsEffect(fx)
            dot._opacity_fx = fx
            dot._breathing = False

            def _pulse_step(going_dim=True):
                if not dot._breathing:
                    return
                anim = QPropertyAnimation(fx, b"opacity", dot)
                anim.setDuration(900)
                anim.setStartValue(fx.opacity())
                anim.setEndValue(0.30 if going_dim else 1.0)
                anim.setEasingCurve(QEasingCurve.Type.InOutSine)
                anim.finished.connect(lambda: _pulse_step(not going_dim))
                dot._cur_anim = anim
                anim.start()

            def start_breathing():
                if dot._breathing:
                    return
                dot._breathing = True
                _pulse_step(True)

            def stop_breathing():
                dot._breathing = False
                fx.setOpacity(1.0)

            dot.start_breathing = start_breathing
            dot.stop_breathing = stop_breathing
            return dot

        nav_grp = QButtonGroup(self); nav_grp.setExclusive(True)
        self._nav_btns = {}
        nav_items = [
            ("🛡️", "Locked Apps",    "apps"),
            ("🔑", "Password",       "password"),
            ("📋", "Security Log",   "log"),
            ("⚙️", "Settings",       "settings_cfg"),
        ]
        self._settings_nav_lbl_base = "Settings"
        for icon, lbl_txt, key in nav_items:
            nb = _NavBtn(icon, lbl_txt, active=(key == "apps"))
            nav_grp.addButton(nb)
            self._nav_btns[key] = nb
            wrap = QWidget(); wrap.setStyleSheet(f"background: {_SIDE};")
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(10, 2, 10, 2); wl.addWidget(nb, 1)
            if key == "settings_cfg":
                self._settings_nav_btn = nb
                self._settings_nav_icon = icon
                dot = _make_pulsing_dot(9, "#ef4444")
                dot.hide()
                wl.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
                self._settings_nav_dot = dot
            sbl.addWidget(wrap)
            nb.clicked.connect(lambda _=False, k=key: self._switch(k))

        sbl.addStretch()

        # ════════════════════════════════════════════════════════

        STATUS_GAP_ABOVE_LINE   = 8
        STATUS_MARGIN_LEFT      = 16
        STATUS_MARGIN_TOP       = 6
        STATUS_MARGIN_RIGHT     = 16
        STATUS_MARGIN_BOTTOM    = 12
        STATUS_SPINNER_TEXT_GAP = 8

        SPINNER_OFFSET_LEFT  = 0
        SPINNER_OFFSET_TOP   = 0
        SPINNER_OFFSET_RIGHT = 0
        SPINNER_OFFSET_BOTTOM= 0

        TEXT_OFFSET_LEFT     = 0
        TEXT_OFFSET_TOP      = 8
        TEXT_OFFSET_RIGHT    = 0
        TEXT_OFFSET_BOTTOM   = -1
        # ════════════════════════════════════════════════════════

        _status_sep = QFrame(); _status_sep.setFixedHeight(1)
        _status_sep.setStyleSheet(f"background: {_BORD};")
        sbl.addWidget(_status_sep)
        sbl.addSpacing(STATUS_GAP_ABOVE_LINE)

        status_bar = QWidget()
        status_bar.setStyleSheet(f"background: {_SIDE};")
        stl = QHBoxLayout(status_bar)
        stl.setContentsMargins(STATUS_MARGIN_LEFT, STATUS_MARGIN_TOP,
                                STATUS_MARGIN_RIGHT, STATUS_MARGIN_BOTTOM)
        stl.setSpacing(STATUS_SPINNER_TEXT_GAP)
        stl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._status_rotator = None
        self._status_spinner = None
        try:
            spinner = _StatusSpinner(size=12, color=_GREEN)
            _glow(spinner, _GREEN, 10)

            spinner_wrap = QWidget(); spinner_wrap.setStyleSheet("background: transparent;")
            spinner_wrap_l = QHBoxLayout(spinner_wrap)
            spinner_wrap_l.setContentsMargins(
                SPINNER_OFFSET_LEFT, SPINNER_OFFSET_TOP,
                SPINNER_OFFSET_RIGHT, SPINNER_OFFSET_BOTTOM)
            spinner_wrap_l.addWidget(spinner, 0, Qt.AlignmentFlag.AlignVCenter)
            stl.addWidget(spinner_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

            rot_status = _RotatingStatus(_sidebar_status_items, spinner=spinner, interval_ms=3000)

            text_wrap = QWidget(); text_wrap.setStyleSheet("background: transparent;")
            text_wrap_l = QHBoxLayout(text_wrap)
            text_wrap_l.setContentsMargins(
                TEXT_OFFSET_LEFT, TEXT_OFFSET_TOP,
                TEXT_OFFSET_RIGHT, TEXT_OFFSET_BOTTOM)
            text_wrap_l.addWidget(rot_status, 0, Qt.AlignmentFlag.AlignVCenter)
            stl.addWidget(text_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

            self._status_spinner = spinner
            self._status_rotator = rot_status
        except Exception as _e:
            try:
                dlog("ERROR", f"sidebar status widget failed to build: {type(_e).__name__}: {_e}")
            except Exception:
                pass

            dot_s = QLabel(); dot_s.setFixedSize(8, 8)
            dot_s.setStyleSheet(f"background: #fbbf24; border-radius: 4px;")
            stl.addWidget(dot_s, 0, Qt.AlignmentFlag.AlignVCenter)
            stl_l = QLabel(f"Status widget failed: {type(_e).__name__}")
            stl_l.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            stl_l.setStyleSheet(f"color: #fbbf24; background: transparent;")
            stl.addWidget(stl_l, 0, Qt.AlignmentFlag.AlignVCenter)
        stl.addStretch()
        sbl.addWidget(status_bar)

        bl.addWidget(sb, 1)
        vsep = QFrame(); vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background: {_BORD};")
        bl.addWidget(vsep)

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {_BG};")
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        topbar = QWidget(); topbar.setFixedHeight(58)
        topbar.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #131120, stop:1 {_CARD}); border-bottom: 1px solid {_BORD};")
        topl = QHBoxLayout(topbar)
        topl.setContentsMargins(24, 0, 24, 0)
        self._section_title_lbl = QLabel("Locked Apps")
        self._section_title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._section_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
        topl.addWidget(self._section_title_lbl); topl.addSpacing(10)
        self._section_sub_lbl = QLabel("Apps that require password on launch")
        self._section_sub_lbl.setFont(QFont("Segoe UI", 9))
        self._section_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        topl.addWidget(self._section_sub_lbl); topl.addStretch()
        cl.addWidget(topbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_inner = QWidget()
        self._scroll_inner.setStyleSheet(f"background: {_BG};")
        self._scroll_lay = QVBoxLayout(self._scroll_inner)
        self._scroll_lay.setContentsMargins(18, 16, 18, 16)
        self._scroll_lay.setSpacing(12)
        self._scroll_inner.setMaximumWidth(1200)
        self._scroll.setWidget(self._scroll_inner)
        cl.addWidget(self._scroll)

        bl.addWidget(self._content, 4)
        rl.addWidget(body, 1)

        self._build_apps_panel()
        self._build_password_panel()
        self._build_log_panel()
        self._build_cp_panel()
        self._build_diag_log_panel()
        self._build_crash_log_panel()
        self._scroll_lay.addStretch()
        self._switch("apps")

    # ── Page switching ───────────────────────────────────────────────────

    def _switch(self, key):
        titles = {
            "apps":         ("Locked Apps",  "Apps that require password on launch"),
            "password":     ("Password",     "Set or change your master password"),
            "log":          ("Security Log", "Recent authentication events"),
            "settings_cfg": ("Settings",     "Startup and general preferences"),
            "diag_log":     ("Diagnostic Log", "Real-time event log for troubleshooting"),
            "crash_log":    ("Crash Log",       "Error & exception reports"),
        }
        t, s = titles.get(key, ("", ""))
        old_key = getattr(self, "_active_section", None)

        if old_key == key:
            if key == "log":       self._refresh_log()
            if key == "diag_log":  self._refresh_diag_log()
            if key == "crash_log": self._refresh_crash_log()
            return

        self._active_section = key

        # ── Overlay fade approach ────────────────────────────────────────

        overlay = getattr(self, "_switch_overlay", None)
        if overlay is None:
            from PyQt6.QtWidgets import QGraphicsOpacityEffect as _OFx
            overlay = __import__("PyQt6.QtWidgets", fromlist=["QWidget"]).QWidget(self._content)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            overlay.setStyleSheet(f"background: {_BG}; border: none;")
            overlay.hide()
            overlay.raise_()
            self._switch_overlay = overlay

            _ofx = _OFx(overlay)
            _ofx.setOpacity(0.0)
            overlay.setGraphicsEffect(_ofx)
            self._switch_overlay_fx = _ofx

        overlay.setGeometry(self._content.rect())
        overlay.raise_()
        overlay.show()

        overlay_fx = self._switch_overlay_fx

        for a in ("_ov_anim_out", "_ov_anim_in"):
            anim = getattr(self, a, None)
            if anim:
                anim.stop()
            setattr(self, a, None)

        def _do_switch():

            self._section_title_lbl.setText(t)
            self._section_sub_lbl.setText(s)
            for k, w in self._section_widgets.items():
                w.setVisible(k == key)
            for k, nb in self._nav_btns.items():
                nb.setChecked(k == key)
            self._scroll.verticalScrollBar().setValue(0)
            if key == "log":       self._refresh_log()
            if key == "diag_log":  self._refresh_diag_log()
            if key == "crash_log": self._refresh_crash_log()
            if key != "password":  self._reset_pw_form()
            # overlay fade-out (reveal new content)
            anim_in = QPropertyAnimation(overlay_fx, b"opacity", overlay)
            anim_in.setDuration(160)
            anim_in.setStartValue(1.0)
            anim_in.setEndValue(0.0)
            anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            def _on_done():
                overlay.hide()
            anim_in.finished.connect(_on_done)
            self._ov_anim_in = anim_in
            anim_in.start()

        # overlay fade-in (hide old content)
        overlay_fx.setOpacity(0.0)
        anim_out = QPropertyAnimation(overlay_fx, b"opacity", overlay)
        anim_out.setDuration(110)
        anim_out.setStartValue(0.0)
        anim_out.setEndValue(1.0)
        anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        anim_out.finished.connect(_do_switch)
        self._ov_anim_out = anim_out
        anim_out.start()
