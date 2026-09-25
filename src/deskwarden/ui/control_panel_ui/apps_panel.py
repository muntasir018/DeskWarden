"""
DeskWarden - ui/control_panel_ui/apps_panel.py
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QButtonGroup, QFileDialog, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QCursor, QFileSystemModel

from ...core.config import load_config, save_config
from ...core.logging_utils import suppress_faulthandler

from .theme import (
    _BG, _CARD, _CARD2, _BORD, _ACC, _ACC2, _ACC3, _FG, _MUTE, _RED, _glow,
)
from .widgets import _Card, _AppIconBox, _PillBtn


class _AppsPanelMixin:

    # ── Build ────────────────────────────────────────────────────────────

    def _build_apps_panel(self):
        panel = QWidget(); panel.setStyleSheet(f"background: {_BG};")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)

        card = _Card(panel, bg=_CARD, border=_BORD, radius=16)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 16); cl.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(10)

        hl = QLabel("PROTECTED APPS")
        hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hl.setStyleSheet(f"color: #b794f6; background: transparent;")
        hdr.addWidget(hl)

        is_paused = bool(self._cfg.get("protection_paused", False))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Search apps...")
        self._search_input.setFixedWidth(145 if is_paused else 180)
        self._search_input.setFixedHeight(26)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: #0d0b1a;
                color: {_FG};
                border: 1px solid {_BORD};
                border-radius: 6px;
                padding: 1px 8px;
                font-size: 8.5pt;
                font-family: 'Segoe UI';
            }}
            QLineEdit:focus {{
                border-color: {_ACC};
                background: #140d28;
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        hdr.addWidget(self._search_input)

        self._pause_warn_lbl = QLabel("⚠ Protection Paused — All Apps Unlocked", card)
        self._pause_warn_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._pause_warn_lbl.setStyleSheet("""
            QLabel {
                color: #fca5a5;
                background: #2a1215;
                border: 1px solid #7f1d1d;
                border-radius: 8px;
                padding: 2px 9px;
            }
        """)
        self._pause_warn_lbl.setVisible(is_paused)
        hdr.addWidget(self._pause_warn_lbl)

        hdr.addStretch()

        self._count_badge = QLabel("0 app(s)")
        self._count_badge.setFont(QFont("Segoe UI", 8))
        self._count_badge.setStyleSheet(f"""
            color: {_MUTE}; background: {_CARD2};
            border: 1px solid {_BORD}; border-radius: 10px;
            padding: 2px 10px;""")
        hdr.addWidget(self._count_badge)
        cl.addLayout(hdr)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {_BORD};")
        cl.addWidget(div)

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_lay = QVBoxLayout(self._cards_container)
        self._cards_lay.setContentsMargins(0, 0, 0, 0)
        self._cards_lay.setSpacing(12)
        self._cards_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        cl.addWidget(self._cards_container)

        self._no_results_lbl = QLabel("")
        self._no_results_lbl.setFont(QFont("Segoe UI", 9))
        self._no_results_lbl.setStyleSheet(f"color: {_MUTE}; background: transparent; padding: 14px 0;")
        self._no_results_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_lbl.hide()
        cl.addWidget(self._no_results_lbl)

        self._app_cards = []

        add_btn = QPushButton("＋  Add App")
        add_btn.setFixedHeight(38)
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_ACC}, stop:1 {_ACC3});
                color: white; border: none; border-radius: 10px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {_ACC2}, stop:1 {_ACC});
            }}""")
        _glow(add_btn, _ACC, 20)
        add_btn.clicked.connect(self._add_app)
        cl.addWidget(add_btn)

        pl.addWidget(card)

        self._scroll_lay.addWidget(panel)
        self._section_widgets["apps"] = panel
        self._refresh_apps()

        self._pause_poll_timer = QTimer(panel)
        self._pause_poll_timer.setInterval(1000)
        self._pause_poll_timer.timeout.connect(self._sync_pause_badge)
        self._pause_poll_timer.start()

    # ── Refresh & Search ─────────────────────────────────────────────────

    def _apply_pause_warning_state(self, is_paused: bool):
        if hasattr(self, "_pause_warn_lbl"):
            self._pause_warn_lbl.setVisible(is_paused)
        if hasattr(self, "_search_input"):
            self._search_input.setFixedWidth(145 if is_paused else 180)

    def _sync_pause_badge(self):
        try:
            cfg = load_config()
            is_paused = bool(cfg.get("protection_paused", False))
            if hasattr(self, "_pause_warn_lbl"):
                if self._pause_warn_lbl.isVisible() != is_paused:
                    self._apply_pause_warning_state(is_paused)
        except Exception:
            pass

    def _on_search_changed(self, _text: str):
        self._filter_apps()

    def _filter_apps(self):
        query = self._search_input.text().strip().lower() if hasattr(self, "_search_input") else ""
        apps = self._cfg.get("locked_apps", []) if hasattr(self, "_cfg") else []
        if not apps:
            if hasattr(self, "_search_input"):
                self._search_input.setEnabled(False)
            if hasattr(self, "_no_results_lbl"):
                self._no_results_lbl.hide()
            return

        if hasattr(self, "_search_input"):
            self._search_input.setEnabled(True)
        visible_count = 0
        for item in getattr(self, "_app_cards", []):
            card = item["card"]
            match = (
                not query or
                query in item["exe"].lower() or
                query in item["display_name"].lower() or
                query in item["mode"].lower() or
                query in item["desc"].lower()
            )
            card.setVisible(match)
            if match:
                visible_count += 1

        if hasattr(self, "_no_results_lbl"):
            if visible_count == 0 and query:
                self._no_results_lbl.setText(f"No apps found matching \"{self._search_input.text().strip()}\"")
                self._no_results_lbl.show()
            else:
                self._no_results_lbl.hide()

        if hasattr(self, "_count_badge"):
            if query:
                self._count_badge.setText(f"{visible_count}/{len(apps)} app(s)")
            else:
                self._count_badge.setText(f"{len(apps)} app(s)")

    def _refresh_apps(self):
        self._cfg = load_config()
        apps = self._cfg.get("locked_apps", [])
        self._count_badge.setText(f"{len(apps)} app(s)")
        self._apply_pause_warning_state(bool(self._cfg.get("protection_paused", False)))
        self._app_cards = []

        while self._cards_lay.count():
            item = self._cards_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not apps:
            if hasattr(self, "_search_input"):
                self._search_input.setEnabled(False)
            empty_box = QWidget()
            empty_box.setStyleSheet("background: transparent;")
            el = QVBoxLayout(empty_box)
            el.setContentsMargins(4, 10, 4, 14)
            el.setSpacing(14)

            title_box = QVBoxLayout()
            title_box.setSpacing(4)
            title = QLabel("How to Lock an Application")
            title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            title.setStyleSheet(f"color: {_FG}; background: transparent;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_box.addWidget(title)

            subtitle = QLabel("Choose any of the 2 easy methods below to add your apps:")
            subtitle.setFont(QFont("Segoe UI", 8))
            subtitle.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_box.addWidget(subtitle)
            el.addLayout(title_box)

            # 2 Columns for Method 1 and Method 2
            methods_row = QHBoxLayout()
            methods_row.setSpacing(12)

            # Method 1 Card
            m1_card = _Card(bg="rgba(255, 255, 255, 0.02)", border=_BORD, radius=12)
            m1_lay = QVBoxLayout(m1_card)
            m1_lay.setContentsMargins(14, 12, 14, 12)
            m1_lay.setSpacing(8)

            m1_hdr = QLabel("Method 1: Direct Browse")
            m1_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            m1_hdr.setStyleSheet("color: #a78bfa; background: transparent; border: none;")
            m1_lay.addWidget(m1_hdr)

            m1_txt = QLabel(
                "<b>1.</b> Click <b>'＋ Add App'</b> button below.<br>"
                "<b>2.</b> Browse and select any <b>.exe</b> file or Desktop shortcut (<b>.lnk</b>)."
            )
            m1_txt.setFont(QFont("Segoe UI", 8))
            m1_txt.setWordWrap(True)
            m1_txt.setStyleSheet(f"color: {_FG}; background: transparent; border: none; line-height: 145%;")
            m1_lay.addWidget(m1_txt)
            m1_lay.addStretch()
            methods_row.addWidget(m1_card)

            # Method 2 Card
            m2_card = _Card(bg="rgba(255, 255, 255, 0.02)", border=_BORD, radius=12)
            m2_lay = QVBoxLayout(m2_card)
            m2_lay.setContentsMargins(14, 12, 14, 12)
            m2_lay.setSpacing(8)

            m2_hdr = QLabel("Method 2: Windows Search / Copy Path")
            m2_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            m2_hdr.setStyleSheet("color: #38bdf8; background: transparent; border: none;")
            m2_lay.addWidget(m2_hdr)

            m2_txt = QLabel(
                "<b>1.</b> Search app in Windows Start → Right-click → <b>'Open file location'</b>.<br>"
                "<b>2.</b> Right-click the app/shortcut → Click <b>'Copy as path'</b>.<br>"
                "<b>3.</b> Click <b>'＋ Add App'</b> below, paste (<b>Ctrl+V</b>) into File name, and click <b>Open</b>."
            )
            m2_txt.setFont(QFont("Segoe UI", 8))
            m2_txt.setWordWrap(True)
            m2_txt.setStyleSheet(f"color: {_FG}; background: transparent; border: none; line-height: 145%;")
            m2_lay.addWidget(m2_txt)
            m2_lay.addStretch()
            methods_row.addWidget(m2_card)

            el.addLayout(methods_row)

            # Future update note
            footer_note = QLabel(
                "<i>We sincerely apologize for this temporary manual step. We are actively working on automatic 1-click app detection for the upcoming update so you won't need to find paths manually!</i>"
            )
            footer_note.setFont(QFont("Segoe UI", 8))
            footer_note.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            footer_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer_note.setWordWrap(True)
            el.addWidget(footer_note)

            self._cards_lay.addWidget(empty_box)
            if hasattr(self, "_no_results_lbl"):
                self._no_results_lbl.hide()
            return

        if hasattr(self, "_search_input"):
            self._search_input.setEnabled(True)

        for i, app_item in enumerate(apps):
            exe  = app_item.get("exe", "") if isinstance(app_item, dict) else app_item
            mode = app_item.get("mode", "ask_always") if isinstance(app_item, dict) else "ask_always"
            mc   = self.MODE_CFG.get(mode, self.MODE_CFG["ask_always"])

            ac = _Card(bg=_CARD2, border=_BORD, radius=14,
                       accent_color=mc[3], hoverable=True)
            acl = QVBoxLayout(ac)
            acl.setContentsMargins(16, 12, 12, 12); acl.setSpacing(8)

            top = QHBoxLayout(); top.setSpacing(12)
            top.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            app_path = app_item.get("path", "") if isinstance(app_item, dict) else ""
            pm = self._exe_icon_pixmap(app_path)
            icon = _AppIconBox(pm, mc[0], 40, mc[1], mc[2], 12)
            top.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

            info_l = QVBoxLayout(); info_l.setSpacing(2)
            display_name = exe[:-4] if exe.lower().endswith(".exe") else exe
            nl = QLabel(display_name)
            nl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            nl.setStyleSheet(f"color: {_FG}; background: transparent;")
            dl = QLabel(mc[5])
            dl.setFont(QFont("Segoe UI", 8))
            dl.setStyleSheet(f"color: {_MUTE}; background: transparent;")
            info_l.addWidget(nl); info_l.addWidget(dl)
            top.addLayout(info_l); top.addStretch()

            rm_btn = QPushButton("✕  Remove")
            rm_btn.setFixedHeight(30)
            rm_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            rm_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #200810; color: #fca5a5;
                    border: 1px solid #3d1020; border-radius: 8px;
                    padding: 0 12px; font-size: 8pt; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: #3d1020; color: white;
                    border-color: {_RED};
                }}""")
            rm_btn.clicked.connect(lambda _=False, idx=i: self._remove_app(idx))
            _glow(rm_btn, _RED, 0)

            def _rm_enter(ev, b=rm_btn):
                b.graphicsEffect().setBlurRadius(14)
                QPushButton.enterEvent(b, ev)

            def _rm_leave(ev, b=rm_btn):
                b.graphicsEffect().setBlurRadius(0)
                QPushButton.leaveEvent(b, ev)

            rm_btn.enterEvent = _rm_enter
            rm_btn.leaveEvent = _rm_leave
            top.addWidget(rm_btn)
            acl.addLayout(top)

            div2 = QFrame(); div2.setFrameShape(QFrame.Shape.HLine)
            div2.setStyleSheet(f"color: {_BORD};"); div2.setFixedHeight(1)
            acl.addWidget(div2)

            pills = QHBoxLayout(); pills.setSpacing(6)
            bg2 = QButtonGroup(self); bg2.setExclusive(True)
            for mk, (_, _, _, pc, pl_lbl, _) in self.MODE_CFG.items():
                pb = _PillBtn(pl_lbl, active=(mk == mode), color=pc)
                bg2.addButton(pb)
                pills.addWidget(pb)
                pb.clicked.connect(
                    lambda _=False, idx=i, mkey=mk, desc=dl:
                        self._set_mode(idx, mkey, desc))
            acl.addLayout(pills)

            self._app_cards.append({
                "card": ac,
                "exe": exe,
                "display_name": display_name,
                "mode": mode,
                "desc": mc[5],
            })

            self._cards_lay.addWidget(ac)

        self._filter_apps()

    # ── Actions ──────────────────────────────────────────────────────────

    def _add_app(self):
        with suppress_faulthandler():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select application to lock", "",
                "Applications (*.exe *.lnk);;Executables (*.exe);;Shortcuts (*.lnk);;All files (*.*)")
        if path:
            path = path.strip().strip('"').strip("'")
            if path.lower().endswith(".lnk"):
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortCut(path)
                    target = getattr(shortcut, "TargetPath", None) or getattr(shortcut, "Targetpath", "")
                    if target and os.path.isfile(target) and target.lower().endswith(".exe"):
                        path = target
                except Exception:
                    pass
            name = os.path.basename(path).lower()
            apps = self._cfg.get("locked_apps", [])
            existing = [(a.get("exe","") if isinstance(a, dict) else a)
                        for a in apps]
            if name not in existing:
                apps.append({"exe": name, "mode": "ask_always", "path": path})
                self._cfg["locked_apps"] = apps
                save_config(self._cfg)
                self._refresh_apps()

    def _exe_icon_pixmap(self, path, size=32):
        try:
            if path and os.path.isfile(path):
                if not hasattr(self, "_fs_icon_model"):
                    self._fs_icon_model = QFileSystemModel()
                    self._fs_icon_model.setRootPath("")
                model = self._fs_icon_model
                model.setRootPath(os.path.dirname(path))
                idx = model.index(path)
                icon = model.fileIcon(idx)
                if icon and not icon.isNull():
                    pm = icon.pixmap(size, size)
                    if pm and not pm.isNull():
                        return pm
        except Exception:
            pass
        return None

    def _remove_app(self, idx):
        apps = self._cfg.get("locked_apps", [])
        if idx < len(apps):
            apps.pop(idx)
            self._cfg["locked_apps"] = apps
            save_config(self._cfg)
            self._refresh_apps()

    def _set_mode(self, idx, mode_key, desc_lbl):
        apps = self._cfg.get("locked_apps", [])
        if idx < len(apps):
            if isinstance(apps[idx], dict):
                apps[idx]["mode"] = mode_key
            else:
                apps[idx] = {"exe": apps[idx], "mode": mode_key}
            self._cfg["locked_apps"] = apps
            save_config(self._cfg)
            mc = self.MODE_CFG.get(mode_key, self.MODE_CFG["ask_always"])
            desc_lbl.setText(mc[5])
            self._refresh_apps()
