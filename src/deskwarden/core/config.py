"""
DeskWarden - core/config.py

"""

import os
import json
import threading

from .paths import CONFIG_PATH
from .logging_utils import dlog

# ═════════════════════════════════════════════════════════════════════════
# Config cache 
# ═════════════════════════════════════════════════════════════════════════

_config_cache_lock = threading.Lock()
_config_cache = {"mtime": None, "data": None}


# ═════════════════════════════════════════════════════════════════════════
# Migration + deep copy
# ═════════════════════════════════════════════════════════════════════════

def _migrate_config(c: dict) -> dict:
    default = {"password_hash": "", "locked_apps": [], "autostart": True,
               "auto_update": True, "last_update_check": "",
               "update_skip_version": "", "update_skip_until": ""}
    for k, v in default.items():
        c.setdefault(k, v)
    migrated = []
    for item in c.get("locked_apps", []):
        if isinstance(item, str):
            migrated.append({"exe": item.lower(), "mode": "ask_always"})
        elif isinstance(item, dict):
            item.setdefault("mode", "ask_always")
            item["exe"] = item.get("exe", "").lower()
            migrated.append(item)
    c["locked_apps"] = migrated
    return c


def _deep_copy_config(c: dict) -> dict:
    return {
        "password_hash": c.get("password_hash", ""),
        "locked_apps": [dict(item) for item in c.get("locked_apps", [])],
        "autostart": c.get("autostart", True),
        "auto_update": c.get("auto_update", True),
        "last_update_check": c.get("last_update_check", ""),
        **{k: v for k, v in c.items() if k not in (
            "password_hash", "locked_apps", "autostart",
            "auto_update", "last_update_check")},
    }


# ═════════════════════════════════════════════════════════════════════════
# load_config / save_config
# ═════════════════════════════════════════════════════════════════════════

def load_config():
    default = {"password_hash": "", "locked_apps": [], "autostart": True,
               "auto_update": True, "last_update_check": "",
               "update_skip_version": "", "update_skip_until": ""}

    if os.path.exists(CONFIG_PATH):
        try:
            disk_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            disk_mtime = None

        with _config_cache_lock:
            if (disk_mtime is not None
                    and _config_cache["data"] is not None
                    and _config_cache["mtime"] == disk_mtime):
                return _deep_copy_config(_config_cache["data"])

        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                c = json.load(f)
            c = _migrate_config(c)
            with _config_cache_lock:
                _config_cache["mtime"] = disk_mtime
                _config_cache["data"] = c
            return _deep_copy_config(c)
        except Exception as e:
            dlog("ERROR", f"load_config: failed to read config.json: {e} — using defaults")

    try:
        save_config(default)
    
        from .process_utils import set_autostart
        set_autostart(True)
    except Exception:
        pass
    dlog("INFO", "load_config: config.json not found, creating default config")
    return default


def save_config(cfg):
    tmp_path = CONFIG_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
        try:
            new_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            new_mtime = None
        with _config_cache_lock:
            _config_cache["mtime"] = new_mtime
            _config_cache["data"] = _migrate_config(_deep_copy_config(cfg))
    except Exception as e:
        dlog("ERROR", f"save_config: failed to write config.json: {e}")
