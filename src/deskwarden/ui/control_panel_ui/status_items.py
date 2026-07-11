"""
DeskWarden - ui/control_panel_ui/status_items.py

"""

import os
import datetime

import psutil

from ...core.security import load_security_log
from ...core.updater import CURRENT_VERSION, get_cached_update_snapshot
from .theme import _TEAL, _RED, _GREEN, _MUTE, _ACC2


def _sidebar_status_items():

    items = []
    try:
        proc = psutil.Process(os.getpid())
        cpu_pct = proc.cpu_percent(interval=None)
        mem_mb = proc.memory_info().rss / (1024 * 1024)
        items.append((f"CPU {cpu_pct:.0f}%  ·  RAM {mem_mb:.0f}MB", _TEAL))
    except Exception:
        pass
    try:
        entries = load_security_log()
        lbl_map = {"wrong_password": "Wrong password", "lockout_start": "Locked out",
                   "lockout_end": "Lockout ended", "success": "Unlocked"}
        color_map = {"wrong_password": "#f59e0b", "lockout_start": _RED,
                     "lockout_end": _GREEN, "success": _GREEN}

        _SKIP_WHERE = {"Control Panel", "Quit"}
        last = None
        for e in reversed(entries):
            if e.get("where") not in _SKIP_WHERE:
                last = e
                break
        if last:
            et = last.get("type", "")
            where = last.get("where", "")
            if where.startswith("App:"):
                where = where[4:]
            if where.lower().endswith(".exe"):
                where = where[:-4]
            txt = f"Last: {lbl_map.get(et, et or '—')} — {where}"
            items.append((txt[:46], color_map.get(et, _MUTE)))
        else:
            items.append(("No security events yet", _MUTE))
    except Exception:
        pass
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        entries = load_security_log()
        unlocks_today = sum(1 for e in entries
                             if e.get("type") == "success" and e.get("time", "").startswith(today))
        items.append((f"{unlocks_today} unlock{'s' if unlocks_today != 1 else ''} today", _GREEN))
    except Exception:
        pass
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        entries = load_security_log()
        failed_today = sum(1 for e in entries
                            if e.get("type") == "wrong_password" and e.get("time", "").startswith(today))
        items.append((f"{failed_today} failed attempt{'s' if failed_today != 1 else ''} today",
                      _RED if failed_today else _MUTE))
    except Exception:
        pass
    try:
        items.append((f"DeskWarden {CURRENT_VERSION}", _ACC2))
    except Exception:
        pass
    try:
        snap = get_cached_update_snapshot()
        if snap.get("update_available"):
            items.append((f"Update available: {snap.get('latest')}", "#fbbf24"))
    except Exception:
        pass
    if not items:
        items = [("Active · monitoring", _GREEN)]
    return items

