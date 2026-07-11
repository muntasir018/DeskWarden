"""
DeskWarden - ui/control_panel_ui/update_panel.py
"""

from PyQt6.QtWidgets import (
    QLabel, QPushButton, QHBoxLayout, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor

from ...core.config import load_config, save_config
from ...core.process_utils import set_autostart
from ...core.updater import (
    CURRENT_VERSION, check_for_update_async, friendly_error_message,
    skip_version_for_today, is_version_skipped, get_cached_update_snapshot,
)

from .theme import _GREEN, _RED, _MUTE
from .widgets import _Card
from .update_dialog import _UpdateCatalogDialog


class _UpdatePanelMixin:

    # ── Startup toggle ───────────────────────────────────────────────────

    def _toggle_auto(self):
        self._cfg["autostart"] = self._auto_cb.isChecked()
        save_config(self._cfg)
        set_autostart(self._cfg["autostart"])

    # ── Settings nav badge ───────────────────────────────────────────────

    def _refresh_settings_badge(self):
        """Show/hide the breathing red dot on the Settings nav item.
        Stays on until the user actually updates — independent of
        whether the catalog popup was skipped for today."""
        dot = getattr(self, "_settings_nav_dot", None)
        if dot is None:
            return
        try:
            has_update = get_cached_update_snapshot().get("update_available", False)
            if has_update:
                dot.show()
                dot.start_breathing()
            else:
                dot.stop_breathing()
                dot.hide()
        except Exception:
            pass

    # ── Update check ─────────────────────────────────────────────────────

    def _toggle_auto_update(self):
        self._cfg["auto_update"] = self._auto_update_cb.isChecked()
        save_config(self._cfg)

    def _check_update(self):
        self._update_btn.setEnabled(False)
        self._update_status.setStyleSheet(
            f"color: {_MUTE}; background: transparent;")
        self._update_status.setText("⏳ Checking for updates…")

        def _on_result(res):

            from PyQt6.QtCore import QMetaObject, Qt as _Qt

            self._update_result_pending = res
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._apply_update_result)

        check_for_update_async(callback=_on_result)

    def _apply_update_result(self):
        res = getattr(self, "_update_result_pending", None)
        self._update_btn.setEnabled(True)
        if res is None:
            return

        if not res.get("error") and hasattr(self, "_last_checked_lbl"):
            self._cfg = load_config()
            last_checked = self._cfg.get("last_update_check", "")
            txt = f"Last checked: {last_checked}" if last_checked else "Last checked: Never"
            self._last_checked_lbl.setText(txt)

        
        while self._update_status_layout.count():
            item = self._update_status_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if res.get("error"):
            lbl = QLabel(f"✗ {friendly_error_message(res['error'])}")
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {_RED}; background: transparent;")
            lbl.setWordWrap(True)
            self._update_status_layout.addWidget(lbl, 1)
            self._update_status = lbl

        elif res.get("update_available"):
            latest = res.get("latest", "?")
            pill = _Card(self._update_status_box, bg="#16231c",
                         border="#1f5c3a", radius=9)
            pl2 = QHBoxLayout(pill)
            pl2.setContentsMargins(10, 6, 10, 6); pl2.setSpacing(8)
            txt_lbl = QLabel(f"🎉  New version available — {latest}")
            txt_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Medium))
            txt_lbl.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            pl2.addWidget(txt_lbl, 1)
            view_btn = QPushButton("View details")
            view_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            view_btn.setFixedHeight(24)
            view_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            view_btn.setStyleSheet(f"""
                QPushButton {{ background: {_GREEN}; color: #08130c;
                    border: none; border-radius: 6px; padding: 0 10px; }}
                QPushButton:hover {{ background: #34d399; }}""")
            view_btn.clicked.connect(lambda: self._maybe_show_catalog(res, force=True))

            self._viewdetails_glow = QGraphicsDropShadowEffect()
            self._viewdetails_glow.setBlurRadius(0)
            self._viewdetails_glow.setColor(QColor(_GREEN))
            self._viewdetails_glow.setOffset(0, 0)
            view_btn.setGraphicsEffect(self._viewdetails_glow)

            def _viewdetails_enter(ev):
                self._viewdetails_glow.setBlurRadius(18)
                QPushButton.enterEvent(view_btn, ev)

            def _viewdetails_leave(ev):
                self._viewdetails_glow.setBlurRadius(0)
                QPushButton.leaveEvent(view_btn, ev)

            view_btn.enterEvent = _viewdetails_enter
            view_btn.leaveEvent = _viewdetails_leave

            pl2.addWidget(view_btn)
            self._update_status_layout.addWidget(pill, 1)
            self._update_status = txt_lbl

        else:
            latest = res.get("latest") or CURRENT_VERSION
            lbl = QLabel(f"✓ You are up to date  ({latest})")
            lbl.setFont(QFont("Segoe UI", 8))
            lbl.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            lbl.setWordWrap(True)
            self._update_status_layout.addWidget(lbl, 1)
            self._update_status = lbl

        self._refresh_settings_badge()
        self._maybe_show_catalog(res)

    # ── "What's new" catalog popup ───────────────────────────────────────

    def _maybe_show_catalog(self, res, force=False):
        
        if not res or not res.get("update_available"):
            return
        latest = res.get("latest", "?")
        if not force:
            already_shown = getattr(self, "_catalog_shown_this_session", False)
            if already_shown or is_version_skipped(latest):
                return
        self._catalog_shown_this_session = True

        def _skip_this_version():
            skip_version_for_today(latest)

        dlg = _UpdateCatalogDialog(
            version=latest,
            notes=res.get("notes", []),
            download_url=res.get("download_url", ""),
            release_url=res.get("url", ""),
            on_skip=_skip_this_version,
            parent=self,
        )
        self._update_catalog_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
