"""
DeskWarden - core/security.py

"""

import os
import json
import time
import hashlib
import threading
import datetime

from .paths import APPDATA_DIR, SECURITY_LOG_PATH

# ═════════════════════════════════════════════════════════════════════════
# Password hashing
# ═════════════════════════════════════════════════════════════════════════

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

MAX_LOG_ENTRIES = 200

PENALTY_THRES = 3
PENALTY_BASE  = 30
PENALTY_MAX   = 300

UNLOCK_GRACE_SECONDS = 15
MIN_GRACE_LIVENESS_DELAY = 2.0

_attempt_state: dict = {}
_attempt_lock = threading.Lock()


# ═════════════════════════════════════════════════════════════════════════
# Security event log (security_log.json)
# ═════════════════════════════════════════════════════════════════════════

def load_security_log():
    if os.path.exists(SECURITY_LOG_PATH):
        try:
            return json.load(open(SECURITY_LOG_PATH, encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_security_log(entries):
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        json.dump(entries[-MAX_LOG_ENTRIES:],
                  open(SECURITY_LOG_PATH, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
    except Exception:
        pass


def log_security_event(event_type: str, context: str, extra: str = ""):
    entry = {
        "time":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type":  event_type,
        "where": context,
        "note":  extra,
    }
    entries = load_security_log()
    entries.append(entry)
    _save_security_log(entries)


# ═════════════════════════════════════════════════════════════════════════
# Wrong-attempt tracking / progressive lockout
# ═════════════════════════════════════════════════════════════════════════

def record_wrong_attempt(context: str) -> dict:
    with _attempt_lock:
        st = _attempt_state.setdefault(context, {"count": 0, "until": 0.0})
        st["count"] += 1
        log_security_event("wrong_password", context, f"attempt #{st['count']}")
        if st["count"] >= PENALTY_THRES:
            excess  = st["count"] - PENALTY_THRES
            penalty = min(PENALTY_BASE * (2 ** excess), PENALTY_MAX)
            st["until"] = time.time() + penalty
            log_security_event("lockout_start", context,
                               f"{int(penalty)}s lockout after {st['count']} wrong attempts")
        locked = time.time() < st["until"]
        wait   = max(0, int(st["until"] - time.time()))
        return {"count": st["count"], "until": st["until"], "locked": locked, "wait": wait}


def reset_attempt_state(context: str):
    with _attempt_lock:
        _attempt_state.pop(context, None)


def check_locked_out(context: str):
    with _attempt_lock:
        st = _attempt_state.get(context, {"until": 0.0})
        remaining = max(0, int(st["until"] - time.time()))
        return remaining > 0, remaining
