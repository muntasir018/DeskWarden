"""
DeskWarden - ui/control_panel_ui/settings_io.py
"""

import json

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QLabel, QPushButton
from PyQt6.QtCore import Qt

from ...core.config import load_config, save_config
from ...core.security import load_security_log, _save_security_log
from ...core.process_utils import set_autostart

from .theme import _RED, _GREEN, _MUTE, _FG, _CARD, _CARD2, _BORD, _ACC3


class _SettingsIOMixin:

    # ── Export ───────────────────────────────────────────────────────────

    def _export_settings(self):
        import datetime as _dt
        default_name = f"deskwarden_backup_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _f = QFileDialog.getSaveFileName(
            self, "Export DeskWarden Settings", default_name,
            "DeskWarden Backup (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            data = {
                "app": "DeskWarden",
                "export_version": 1,
                "exported_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "config": load_config(),
                "security_log": load_security_log(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            self._backup_status.setText(f"✓ Exported to {path}")
        except Exception as e:
            self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._backup_status.setText(f"✗ Export failed: {e}")

    # ── Import ───────────────────────────────────────────────────────────

    def _import_settings(self):
        path, _f = QFileDialog.getOpenFileName(
            self, "Import DeskWarden Settings", "",
            "DeskWarden Backup (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = data.get("config")
            if not isinstance(cfg, dict) or "locked_apps" not in cfg:
                raise ValueError("Not a valid DeskWarden backup file.")


            if cfg.get("password_hash"):
                box = QMessageBox(self)

                box.setWindowFlags(
                    box.windowFlags() | Qt.WindowType.FramelessWindowHint)
                box.setWindowTitle("Password-Protected Backup")
                box.setIcon(QMessageBox.Icon.Warning)
                box.setText(
                    f"<b style='font-size:11pt; color:{_RED};'>Password-Protected Backup</b>"
                    "<br><br>This backup file has a password set."
                )
                box.setInformativeText(
                    "Importing it will replace your current DeskWarden "
                    "password with the one saved in this backup.\n\n"
                    "Make sure you know that password before continuing — "
                    "otherwise you could lock yourself out of your apps."
                )
                yes_btn = box.addButton("Import Anyway", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.setDefaultButton(yes_btn)
                box.setStyleSheet(f"""
                    QMessageBox {{
                        background: {_CARD}; border: 1px solid {_BORD};
                        border-radius: 12px;
                    }}
                    QLabel {{ color: {_FG}; background: transparent; }}
                    QPushButton {{
                        background: {_CARD2}; color: {_FG};
                        border: 1px solid {_BORD}; border-radius: 8px;
                        padding: 6px 14px; min-width: 90px;
                    }}
                    QPushButton:hover {{ background: #1f1c34; border-color: {_ACC3}; }}
                """)

                for icon_name in ("qt_msgboxex_icon_label", "qt_msgbox_icon_label"):
                    icon_lbl = box.findChild(QLabel, icon_name)
                    if icon_lbl is not None:
                        icon_lbl.setStyleSheet(
                            f"background: {_CARD};"
                            "border-top-left-radius: 12px;"
                            "border-bottom-left-radius: 12px;"
                        )
                box.adjustSize()
                parent_geo = self.geometry()
                parent_center = self.mapToGlobal(parent_geo.center() - parent_geo.topLeft())
                box.move(
                    parent_center.x() - box.width() // 2,
                    parent_center.y() - box.height() // 2,
                )
                box.exec()
                if box.clickedButton() is not yes_btn:
                    self._backup_status.setStyleSheet(f"color: {_MUTE}; background: transparent;")
                    self._backup_status.setText("Import cancelled.")
                    return

            save_config(cfg)
            if "security_log" in data and isinstance(data["security_log"], list):
                _save_security_log(data["security_log"])

            self._cfg = load_config()

            # Refresh Locked Apps list
            self._refresh_apps()

            # Refresh Password badge / form state
            has_pw = bool(self._cfg.get("password_hash"))
            self._pw_badge.setText("✓ Set" if has_pw else "✗ Not set")
            self._pw_badge.setStyleSheet(f"""
                color: white; background: {_GREEN if has_pw else _RED};
                border-radius: 10px; padding: 2px 10px;""")
            self._reset_pw_form()

            # Refresh autostart checkbox + registry entry
            self._auto_cb.setChecked(self._cfg.get("autostart", False))
            set_autostart(self._cfg.get("autostart", False))

            # Refresh Security Log list
            self._refresh_log()

            self._backup_status.setStyleSheet(f"color: {_GREEN}; background: transparent;")
            self._backup_status.setText("✓ Settings imported successfully.")
        except Exception as e:
            self._backup_status.setStyleSheet(f"color: {_RED}; background: transparent;")
            self._backup_status.setText(f"✗ Import failed: {e}")
