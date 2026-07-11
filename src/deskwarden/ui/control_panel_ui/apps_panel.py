"""
DeskWarden - ui/control_panel_ui/apps_panel.py
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QButtonGroup, QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor, QFileSystemModel

from ...core.config import load_config, save_config

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
        hl = QLabel("PROTECTED APPS")
        hl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        hl.setStyleSheet(f"color: #b794f6; background: transparent;")
        hdr.addWidget(hl); hdr.addStretch()
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

        self._apps_container_lay = cl
        self._apps_card = card

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

        pl.addWidget(card)
        cl.addWidget(add_btn)

        self._scroll_lay.addWidget(panel)
        self._section_widgets["apps"] = panel
        self._refresh_apps()

    # ── Refresh ──────────────────────────────────────────────────────────

    def _refresh_apps(self):
        self._cfg = load_config()
        apps = self._cfg.get("locked_apps", [])
        self._count_badge.setText(f"{len(apps)} app(s)")
        while self._apps_container_lay.count() > 3:
            item = self._apps_container_lay.takeAt(2)
            if item and item.widget():
                item.widget().deleteLater()

        if not apps:
            empty = QLabel("No apps locked yet. Click '＋ Add App' below.")
            empty.setFont(QFont("Segoe UI", 9))
            empty.setStyleSheet(f"color: {_MUTE}; background: transparent; padding: 10px 0;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._apps_container_lay.insertWidget(
                self._apps_container_lay.count() - 1, empty)
            return

        for i, app_item in enumerate(apps):
            exe  = app_item.get("exe", "") if isinstance(app_item, dict) else app_item
            mode = app_item.get("mode", "ask_always") if isinstance(app_item, dict) else "ask_always"
            mc   = self.MODE_CFG.get(mode, self.MODE_CFG["ask_always"])

            ac = _Card(bg=_CARD2, border=_BORD, radius=14,
                       accent_color=mc[3], hoverable=True)
            acl = QVBoxLayout(ac)
            acl.setContentsMargins(16, 12, 12, 12); acl.setSpacing(8)

            top = QHBoxLayout(); top.setSpacing(12)
            app_path = app_item.get("path", "") if isinstance(app_item, dict) else ""
            pm = self._exe_icon_pixmap(app_path)
            icon = _AppIconBox(pm, mc[0], 40, mc[1], mc[2], 12)
            top.addWidget(icon)

            info_l = QVBoxLayout(); info_l.setSpacing(2)
            nl = QLabel(exe)
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

            self._apps_container_lay.insertWidget(
                self._apps_container_lay.count() - 1, ac)

    # ── Actions ──────────────────────────────────────────────────────────

    def _add_app(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select .exe to lock", "",
            "Executable (*.exe);;All files (*.*)")
        if path:
            name = os.path.basename(path).lower()
            apps = self._cfg.get("locked_apps", [])
            existing = [(a.get("exe","") if isinstance(a, dict) else a)
                        for a in apps]
            if name not in existing:
                apps.append({"exe": name, "mode": "ask_always", "path": path})
                self._cfg["locked_apps"] = apps
                save_config(self._cfg)
                self._refresh_apps()

    def _exe_icon_pixmap(self, path, size=28):
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
