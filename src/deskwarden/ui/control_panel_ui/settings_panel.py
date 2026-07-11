"""
DeskWarden - ui/control_panel_ui/settings_panel.py
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor, QPixmap

from ...core.updater import CURRENT_VERSION
from ...core.website_link import get_website_url

from .theme import (
    _BG, _CARD, _CARD2, _BORD, _ACC, _ACC2, _ACC3, _TEAL,
    _FG, _MUTE, _GREEN, _RED,
)
from .widgets import _Card, _IconBox


class _SettingsPanelMixin:

    # ── Build ────────────────────────────────────────────────────────────

    def _build_cp_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(10)

        # helper: compact section header row
        def _sec_hdr(icon, title, subtitle, icon_bg, icon_fg):
            hw = QWidget(); hw.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(hw); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(10)
            ib = _IconBox(icon, 32, icon_bg, icon_fg, 9)
            hl.addWidget(ib)
            tl = QVBoxLayout(); tl.setSpacing(0)
            t = QLabel(title)
            t.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            t.setStyleSheet(f"color: {_FG}; background: transparent;")
            s = QLabel(subtitle)
            s.setFont(QFont("Segoe UI", 8))
            s.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            tl.addWidget(t); tl.addWidget(s)
            hl.addLayout(tl); hl.addStretch()
            return hw

        # ── STARTUP card ──────────────────────────────────────────
        card = _Card(panel, bg=_CARD, border=_BORD, radius=14)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(10)

        cl.addWidget(_sec_hdr("⚡", "Startup", "Launch behavior", "#1a1030", "#c4b5fd"))

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(div)

        row_w = QWidget(); row_w.setStyleSheet("background: transparent;")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0); row_l.setSpacing(0)
        cb_lbl = QWidget(); cb_lbl.setStyleSheet("background: transparent;")
        cb_lbl_l = QVBoxLayout(cb_lbl); cb_lbl_l.setSpacing(1); cb_lbl_l.setContentsMargins(0,0,0,0)
        cb_title = QLabel("Start DeskWarden with Windows")
        cb_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        cb_title.setStyleSheet(f"color: {_FG}; background: transparent;")
        cb_sub = QLabel("DeskWarden will start automatically when you log in")
        cb_sub.setFont(QFont("Segoe UI", 8))
        cb_sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        cb_lbl_l.addWidget(cb_title); cb_lbl_l.addWidget(cb_sub)
        row_l.addWidget(cb_lbl, 1)
        self._auto_cb = QCheckBox("")
        self._auto_cb.setFont(QFont("Segoe UI", 9))
        self._auto_cb.setChecked(self._cfg.get("autostart", True))
        self._auto_cb.stateChanged.connect(self._toggle_auto)
        row_l.addWidget(self._auto_cb)
        cl.addWidget(row_w)

        warn = QLabel("⚠  If disabled, DeskWarden will not protect your apps after a restart.")
        warn.setFont(QFont("Segoe UI", 8))
        warn.setStyleSheet("color: #f59e0b; background: #1a1200; border: 1px solid #3d2e00; border-radius: 7px; padding: 5px 10px;")
        warn.setWordWrap(True)
        cl.addWidget(warn)

        pl.addWidget(card)

        # ── BACKUP & RESTORE card ─────────────────────────────────
        bcard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
        bcl = QVBoxLayout(bcard)
        bcl.setContentsMargins(18, 14, 18, 16); bcl.setSpacing(10)

        bcl.addWidget(_sec_hdr("💾", "Backup & Restore", "Save or load your settings", "#0e1a10", "#86efac"))

        bdiv = QFrame(); bdiv.setFixedHeight(1)
        bdiv.setStyleSheet(f"background: {_BORD};")
        bcl.addWidget(bdiv)

        bdesc = QLabel("Keep a backup of your locked apps and settings. Restore them anytime — useful before reinstalling DeskWarden.")
        bdesc.setFont(QFont("Segoe UI", 8))
        bdesc.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        bdesc.setWordWrap(True)
        bcl.addWidget(bdesc)

        brow = QHBoxLayout(); brow.setSpacing(8)

        export_btn = QPushButton("⬇  Export Settings")
        export_btn.setFixedHeight(34)
        export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        export_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_ACC}, stop:1 {_ACC3});
                color: white; border: none; border-radius: 9px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}""")
        export_btn.clicked.connect(self._export_settings)
        brow.addWidget(export_btn)

        self._export_glow = QGraphicsDropShadowEffect()
        self._export_glow.setBlurRadius(0)
        self._export_glow.setColor(QColor(_ACC))
        self._export_glow.setOffset(0, 0)
        export_btn.setGraphicsEffect(self._export_glow)

        def _export_enter(ev):
            self._export_glow.setBlurRadius(18)
            QPushButton.enterEvent(export_btn, ev)

        def _export_leave(ev):
            self._export_glow.setBlurRadius(0)
            QPushButton.leaveEvent(export_btn, ev)

        export_btn.enterEvent = _export_enter
        export_btn.leaveEvent = _export_leave

        import_btn = QPushButton("⬆  Import Settings")
        import_btn.setFixedHeight(34)
        import_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        import_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        import_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_FG};
                border: 1px solid {_BORD}; border-radius: 9px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: #1e1a34; border-color: {_ACC}; }}""")
        import_btn.clicked.connect(self._import_settings)
        brow.addWidget(import_btn)

        self._import_glow = QGraphicsDropShadowEffect()
        self._import_glow.setBlurRadius(0)
        self._import_glow.setColor(QColor(_TEAL))
        self._import_glow.setOffset(0, 0)
        import_btn.setGraphicsEffect(self._import_glow)

        def _import_enter(ev):
            self._import_glow.setBlurRadius(18)
            QPushButton.enterEvent(import_btn, ev)

        def _import_leave(ev):
            self._import_glow.setBlurRadius(0)
            QPushButton.leaveEvent(import_btn, ev)

        import_btn.enterEvent = _import_enter
        import_btn.leaveEvent = _import_leave
        brow.addStretch()

        bcl.addLayout(brow)

        self._backup_status = QLabel("")
        self._backup_status.setFont(QFont("Segoe UI", 8))
        self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
        self._backup_status.setWordWrap(True)
        bcl.addWidget(self._backup_status)

        pl.addWidget(bcard)

        # ── AUTO UPDATE card ──────────────────────────────────────
        ucard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
        ucl = QVBoxLayout(ucard)
        ucl.setContentsMargins(18, 14, 18, 16); ucl.setSpacing(10)

        ucl.addWidget(_sec_hdr("🔄", "Auto Update", "Keep DeskWarden up to date", "#071828", "#67e8f9"))

        udiv = QFrame(); udiv.setFixedHeight(1)
        udiv.setStyleSheet(f"background: {_BORD};")
        ucl.addWidget(udiv)

        # Auto update toggle row
        auto_upd_row = QWidget(); auto_upd_row.setStyleSheet("background: transparent;")
        auto_upd_l = QHBoxLayout(auto_upd_row)
        auto_upd_l.setContentsMargins(0, 0, 0, 0); auto_upd_l.setSpacing(0)
        au_lbl_w = QWidget(); au_lbl_w.setStyleSheet("background: transparent;")
        au_lbl_vl = QVBoxLayout(au_lbl_w); au_lbl_vl.setSpacing(1); au_lbl_vl.setContentsMargins(0,0,0,0)
        au_title = QLabel("Automatically check for updates")
        au_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        au_title.setStyleSheet(f"color: {_FG}; background: transparent;")
        au_sub = QLabel("DeskWarden will check when you open Control Panel")
        au_sub.setFont(QFont("Segoe UI", 8))
        au_sub.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        au_lbl_vl.addWidget(au_title); au_lbl_vl.addWidget(au_sub)
        auto_upd_l.addWidget(au_lbl_w, 1)
        self._auto_update_cb = QCheckBox("")
        self._auto_update_cb.setChecked(self._cfg.get("auto_update", True))
        self._auto_update_cb.stateChanged.connect(self._toggle_auto_update)
        auto_upd_l.addWidget(self._auto_update_cb)
        ucl.addWidget(auto_upd_row)

        # Last checked label
        last_checked = self._cfg.get("last_update_check", "")
        last_checked_txt = f"Last checked: {last_checked}" if last_checked else "Last checked: Never"
        self._last_checked_lbl = QLabel(last_checked_txt)
        self._last_checked_lbl.setFont(QFont("Segoe UI", 8))
        self._last_checked_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        ucl.addWidget(self._last_checked_lbl)

        urow = QHBoxLayout(); urow.setSpacing(10)

        self._update_btn = QPushButton("🔍  Check for Update")
        self._update_btn.setFixedHeight(34)
        self._update_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._update_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_ACC}, stop:1 {_ACC3});
                color: white; border: none; border-radius: 9px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_ACC2}; }}
            QPushButton:disabled {{ background: {_CARD2}; color: {_MUTE}; }}""")
        self._update_btn.clicked.connect(self._check_update)
        urow.addWidget(self._update_btn)

        self._updchk_glow = QGraphicsDropShadowEffect()
        self._updchk_glow.setBlurRadius(0)
        self._updchk_glow.setColor(QColor(_ACC))
        self._updchk_glow.setOffset(0, 0)
        self._update_btn.setGraphicsEffect(self._updchk_glow)

        def _updchk_enter(ev):
            self._updchk_glow.setBlurRadius(20)
            QPushButton.enterEvent(self._update_btn, ev)

        def _updchk_leave(ev):
            self._updchk_glow.setBlurRadius(0)
            QPushButton.leaveEvent(self._update_btn, ev)

        self._update_btn.enterEvent = _updchk_enter
        self._update_btn.leaveEvent = _updchk_leave

        self._update_status_box = QWidget()
        self._update_status_box.setStyleSheet("background: transparent;")
        self._update_status_layout = QHBoxLayout(self._update_status_box)
        self._update_status_layout.setContentsMargins(0, 0, 0, 0)
        self._update_status_layout.setSpacing(0)
        self._update_status = QLabel(f"Current version: {CURRENT_VERSION}")
        self._update_status.setFont(QFont("Segoe UI", 8))
        self._update_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        self._update_status.setWordWrap(True)
        self._update_status_layout.addWidget(self._update_status, 1)
        urow.addWidget(self._update_status_box, 1)

        ucl.addLayout(urow)

        pl.addWidget(ucard)
        # ── end AUTO UPDATE card ──────────────────────────────────

        # ── ADVANCED card ─────────────────────────────────────────
        acard = _Card(panel, bg=_CARD, border=_BORD, radius=14)
        acl = QVBoxLayout(acard)
        acl.setContentsMargins(18, 14, 18, 16); acl.setSpacing(10)

        acl.addWidget(_sec_hdr("🛠️", "Advanced", "Developer & troubleshooting tools", "#0f1620", "#94a3b8"))

        adiv = QFrame(); adiv.setFixedHeight(1)
        adiv.setStyleSheet(f"background: {_BORD};")
        acl.addWidget(adiv)

        arow = QWidget(); arow.setStyleSheet("background: transparent;")
        arow_l = QHBoxLayout(arow)
        arow_l.setContentsMargins(0, 0, 0, 0); arow_l.setSpacing(12)

        diag_icon = QLabel("🔍")
        diag_icon.setFont(QFont("Segoe UI", 14))
        diag_icon.setStyleSheet("background: transparent;")
        diag_icon.setFixedWidth(24)
        arow_l.addWidget(diag_icon)

        diag_txt_w = QWidget(); diag_txt_w.setStyleSheet("background: transparent;")
        diag_txt_l = QVBoxLayout(diag_txt_w); diag_txt_l.setSpacing(1); diag_txt_l.setContentsMargins(0,0,0,0)
        diag_title_lbl = QLabel("Diagnostic Log")
        diag_title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        diag_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
        diag_sub_lbl = QLabel("Real-time event log for troubleshooting")
        diag_sub_lbl.setFont(QFont("Segoe UI", 8))
        diag_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        diag_txt_l.addWidget(diag_title_lbl); diag_txt_l.addWidget(diag_sub_lbl)
        arow_l.addWidget(diag_txt_w, 1)

        open_diag_btn = QPushButton("View Log →")
        open_diag_btn.setFixedHeight(30)
        open_diag_btn.setFixedWidth(90)
        open_diag_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_diag_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        open_diag_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_MUTE};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 10px;
            }}
            QPushButton:hover {{
                background: #1e1a34; border-color: {_ACC}; color: {_FG};
            }}
            QPushButton:pressed {{ background: #5b21b6; color: white; }}""")
        open_diag_btn.clicked.connect(lambda: self._switch("diag_log"))

        self._open_diag_glow = QGraphicsDropShadowEffect()
        self._open_diag_glow.setBlurRadius(0)
        self._open_diag_glow.setColor(QColor(_ACC))
        self._open_diag_glow.setOffset(0, 0)
        open_diag_btn.setGraphicsEffect(self._open_diag_glow)

        def _open_diag_enter(ev):
            self._open_diag_glow.setBlurRadius(14)
            QPushButton.enterEvent(open_diag_btn, ev)
        def _open_diag_leave(ev):
            self._open_diag_glow.setBlurRadius(0)
            QPushButton.leaveEvent(open_diag_btn, ev)
        open_diag_btn.enterEvent = _open_diag_enter
        open_diag_btn.leaveEvent = _open_diag_leave

        arow_l.addWidget(open_diag_btn)

        acl.addWidget(arow)

        # divider between rows
        crow_div = QFrame(); crow_div.setFixedHeight(1)
        crow_div.setStyleSheet(f"background: {_BORD};")
        acl.addWidget(crow_div)

        # ── Crash Log row ─────────────────────────────────────────
        crash_row = QWidget(); crash_row.setStyleSheet("background: transparent;")
        crash_row_l = QHBoxLayout(crash_row)
        crash_row_l.setContentsMargins(0, 0, 0, 0); crash_row_l.setSpacing(12)

        crash_icon = QLabel("💥")
        crash_icon.setFont(QFont("Segoe UI", 14))
        crash_icon.setStyleSheet("background: transparent;")
        crash_icon.setFixedWidth(24)
        crash_row_l.addWidget(crash_icon)

        crash_txt_w = QWidget(); crash_txt_w.setStyleSheet("background: transparent;")
        crash_txt_l = QVBoxLayout(crash_txt_w); crash_txt_l.setSpacing(1); crash_txt_l.setContentsMargins(0,0,0,0)
        crash_title_lbl = QLabel("Crash Log")
        crash_title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        crash_title_lbl.setStyleSheet(f"color: {_FG}; background: transparent;")
        crash_sub_lbl = QLabel("Error & exception reports")
        crash_sub_lbl.setFont(QFont("Segoe UI", 8))
        crash_sub_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        crash_txt_l.addWidget(crash_title_lbl); crash_txt_l.addWidget(crash_sub_lbl)
        crash_row_l.addWidget(crash_txt_w, 1)

        open_crash_btn = QPushButton("View Log →")
        open_crash_btn.setFixedHeight(30)
        open_crash_btn.setFixedWidth(90)
        open_crash_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_crash_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        open_crash_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD2}; color: {_MUTE};
                border: 1px solid {_BORD}; border-radius: 8px; padding: 0 10px;
            }}
            QPushButton:hover {{
                background: #2a1010; border-color: #ef4444; color: #fca5a5;
            }}
            QPushButton:pressed {{ background: #7f1d1d; color: white; }}""")

        open_crash_btn.clicked.connect(lambda: self._switch("crash_log"))

        self._open_crash_glow = QGraphicsDropShadowEffect()
        self._open_crash_glow.setBlurRadius(0)
        self._open_crash_glow.setColor(QColor(_RED))
        self._open_crash_glow.setOffset(0, 0)
        open_crash_btn.setGraphicsEffect(self._open_crash_glow)

        def _open_crash_enter(ev):
            self._open_crash_glow.setBlurRadius(14)
            QPushButton.enterEvent(open_crash_btn, ev)
        def _open_crash_leave(ev):
            self._open_crash_glow.setBlurRadius(0)
            QPushButton.leaveEvent(open_crash_btn, ev)
        open_crash_btn.enterEvent = _open_crash_enter
        open_crash_btn.leaveEvent = _open_crash_leave

        crash_row_l.addWidget(open_crash_btn)

        acl.addWidget(crash_row)
        pl.addWidget(acard)
        # ── end ADVANCED card ─────────────────────────────────────

        pl.addStretch()

        # ── Footer ────────────────────────────────────────────────
        footer = QWidget(); footer.setStyleSheet("background: transparent;")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(0, 4, 0, 14); fl.setSpacing(4)

        ver_lbl = QLabel(
            '<span style="color:#f5f0ff; font-weight:700;">DeskWarden</span>'
            '&nbsp;&nbsp;'
            '<span style="color:#c4b5fd;">v1.1.0</span>'
        )
        ver_lbl.setFont(QFont("Segoe UI", 9))
        ver_lbl.setStyleSheet("background: transparent;")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setTextFormat(Qt.TextFormat.RichText)
        fl.addWidget(ver_lbl)

        crafted = QLabel(
            'Crafted with <span style="color:#ff6b9d;">❤️</span> by '
            '<span style="color:#c4b5fd; font-weight:700;">'
            'Tahasinur Rahman Muntasir</span>'
        )
        crafted.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        crafted.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        crafted.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crafted.setTextFormat(Qt.TextFormat.RichText)
        fl.addWidget(crafted)

        _GH_ICON_B64 = "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"
        _FB_ICON_B64 = "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"
        # ── Credit row (QHBoxLayout for pixel-perfect icon alignment) ──
        credit_row = QWidget(); credit_row.setStyleSheet("background: transparent;")
        credit_hl  = QHBoxLayout(credit_row)
        credit_hl.setContentsMargins(0, 0, 0, 0); credit_hl.setSpacing(4)
        credit_hl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        def _make_icon_link(b64, url, label_text, icon_top_offset=0, icon_left_offset=0):
            """Return a QWidget containing [icon] [text] as a clickable link."""
            w = QWidget(); w.setStyleSheet("background: transparent;")
            h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(3)
            h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            
            left_pad = max(0, -icon_left_offset)   
            right_pad = max(0, icon_left_offset)  
            ico_lbl = QLabel(); ico_lbl.setStyleSheet("background: transparent;")
            px = QPixmap()
            px.loadFromData(__import__("base64").b64decode(b64))
            ico_lbl.setPixmap(px.scaled(13, 13,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            ico_lbl.setFixedSize(13 + left_pad + right_pad, 13)
            align = Qt.AlignmentFlag.AlignRight if right_pad else Qt.AlignmentFlag.AlignLeft
            ico_lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            ico_lbl.setContentsMargins(0, icon_top_offset, 0, 0)

            txt_lbl = QLabel(f'<a href="{url}" style="color:#9d5cff; text-decoration:none;">{label_text}</a>')
            txt_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            txt_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            txt_lbl.setTextFormat(Qt.TextFormat.RichText)
            txt_lbl.setOpenExternalLinks(True)
            txt_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

            h.addWidget(ico_lbl)
            h.addWidget(txt_lbl)
            return w

        gh_w  = _make_icon_link(_GH_ICON_B64,  "https://github.com/muntasir018/DeskWarden",         "GitHub",   icon_top_offset=-3, icon_left_offset=-1)
        fb_w  = _make_icon_link(_FB_ICON_B64,  "https://www.facebook.com/muntasir017",   "Facebook", icon_top_offset=0,  icon_left_offset=0)

        def _open_website():
            import webbrowser
            webbrowser.open(get_website_url())

        web_w = QWidget(); web_w.setStyleSheet("background: transparent;")
        web_hl = QHBoxLayout(web_w)
        web_hl.setContentsMargins(0, 0, 0, 0); web_hl.setSpacing(3)
        web_hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        web_icon = QLabel("🌐")
        web_icon.setFont(QFont("Segoe UI", 8))
        web_icon.setStyleSheet("background: transparent;")
        web_icon.setFixedSize(13, 13)
        web_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        web_txt = QLabel('<a href="#" style="color:#9d5cff; text-decoration:none;">Website</a>')
        web_txt.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
        web_txt.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        web_txt.setTextFormat(Qt.TextFormat.RichText)
        web_txt.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        web_txt.linkActivated.connect(lambda _url: _open_website())

        web_hl.addWidget(web_icon)
        web_hl.addWidget(web_txt)

        sep = QLabel("·"); sep.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sep.setFont(QFont("Segoe UI", 8))

        sep2 = QLabel("·"); sep2.setStyleSheet(f"color: {_MUTE}; background: transparent;")
        sep2.setFont(QFont("Segoe UI", 8))

        credit_hl.addWidget(web_w)
        credit_hl.addWidget(sep2)
        credit_hl.addWidget(gh_w)
        credit_hl.addWidget(sep)
        credit_hl.addWidget(fb_w)
        fl.addWidget(credit_row)

        pl.addWidget(footer)
        self._scroll_lay.addWidget(panel)
        self._section_widgets["settings_cfg"] = panel
        panel.setVisible(False)
