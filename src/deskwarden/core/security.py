"""
DeskWarden - core/security.py

"""

import os
import json
import time
import hashlib
import secrets
import threading
import datetime

from .paths import APPDATA_DIR, SECURITY_LOG_PATH

# ═════════════════════════════════════════════════════════════════════════
# Password & Recovery Key hashing
# ═════════════════════════════════════════════════════════════════════════

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def is_caps_lock_on() -> bool:
    """Return True if Windows Caps Lock is currently active."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 0x0001)
    except Exception:
        return False


_KEY_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def generate_recovery_key() -> str:
    """Generate a high-entropy 16-character recovery key grouped in 4-character blocks:
    e.g. DW-8F92-K4M1-99XP-3A7B"""
    chunks = ["".join(secrets.choice(_KEY_CHARSET) for _ in range(4)) for _ in range(4)]
    return "DW-" + "-".join(chunks)


def normalize_recovery_key(key: str) -> str:
    """Remove DW prefix, dashes, whitespace, and convert to uppercase."""
    if not key:
        return ""
    clean = key.strip().upper().replace("-", "").replace(" ", "").replace("_", "")
    if len(clean) > 16 and clean.startswith("DW"):
        clean = clean[2:]
    return clean


def hash_recovery_key(key: str) -> str:
    """Return SHA-256 hash of the normalized recovery key."""
    norm = normalize_recovery_key(key)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def verify_recovery_key(entered_key: str, stored_hash: str) -> bool:
    """True if normalized entered_key matches stored_hash."""
    if not stored_hash or not entered_key:
        return False
    return hash_recovery_key(entered_key) == stored_hash


# ═════════════════════════════════════════════════════════════════════════
# Email OTP (System 2)
# ═════════════════════════════════════════════════════════════════════════

RECOVERY_WORKER_URL = "https://deskwarden-update-proxy.mdmuntasir017.workers.dev/send-recovery-otp"

def generate_otp_code() -> str:
    """Generate a cryptographically random 6-digit numeric OTP."""
    return str(secrets.randbelow(900000) + 100000)


def mask_email(email: str) -> str:
    """Mask email for safe UI display: e.g. m***r@gmail.com"""
    if not email or "@" not in email:
        return email or ""
    parts = email.split("@", 1)
    name, domain = parts[0], parts[1]
    if len(name) <= 2:
        masked_name = name[0] + "*"
    else:
        masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
    return f"{masked_name}@{domain}"


# ═════════════════════════════════════════════════════════════════════════
# Daily OTP Rate Limiter
# ═════════════════════════════════════════════════════════════════════════

OTP_RATE_LIMIT_PATH = os.path.join(APPDATA_DIR, "otp_rate_limit.json")
_otp_rate_lock = threading.Lock()

DAILY_OTP_LIMITS = {
    "reset_password": 5,
    "import_verify": 5,
}
DEFAULT_DAILY_OTP_LIMIT = 5


def _load_otp_rate_data() -> dict:
    if os.path.exists(OTP_RATE_LIMIT_PATH):
        try:
            with open(OTP_RATE_LIMIT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_otp_rate_data(data: dict):
    tmp = OTP_RATE_LIMIT_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, OTP_RATE_LIMIT_PATH)
    except Exception:
        pass


def check_daily_otp_limit(purpose: str = "reset_password") -> tuple[bool, int, int]:
    """
    Check if the user is allowed to send an OTP today for the given purpose.
    Returns (allowed: bool, current_count: int, max_limit: int).
    Automatically resets count when a new calendar day arrives.
    """
    purpose = (purpose or "reset_password").strip()
    max_limit = DAILY_OTP_LIMITS.get(purpose, DEFAULT_DAILY_OTP_LIMIT)
    today_str = datetime.date.today().isoformat()

    with _otp_rate_lock:
        data = _load_otp_rate_data()
        entry = data.get(purpose, {})
        if entry.get("date") != today_str:
            current_count = 0
        else:
            current_count = int(entry.get("count", 0))

        allowed = current_count < max_limit
        return allowed, current_count, max_limit


def record_daily_otp_sent(purpose: str = "reset_password") -> int:
    """
    Increment and persist the daily OTP count for today.
    Returns the new count for today.
    """
    purpose = (purpose or "reset_password").strip()
    today_str = datetime.date.today().isoformat()

    with _otp_rate_lock:
        data = _load_otp_rate_data()
        entry = data.get(purpose, {})
        if entry.get("date") != today_str:
            new_count = 1
        else:
            new_count = int(entry.get("count", 0)) + 1

        data[purpose] = {
            "date": today_str,
            "count": new_count,
            "last_sent_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_otp_rate_data(data)
        return new_count


def send_recovery_otp_worker(email: str, otp: str, purpose: str = "reset_password", timeout: int = 10) -> tuple[bool, str]:
    """
    Send OTP to the user's recovery email via the Cloudflare Worker proxy.
    purpose: "reset_password" (default) or "import_verify"
    Returns (success: bool, message: str).
    Enforces daily limit per purpose.
    """
    import urllib.request
    import urllib.error

    if not email or "@" not in email:
        return False, "Invalid recovery email address."
    if not otp or len(otp) != 6 or not otp.isdigit():
        return False, "Invalid OTP code."

    # Check daily quota
    can_send, cur_count, max_lim = check_daily_otp_limit(purpose)
    if not can_send:
        return False, f"Daily limit reached ({cur_count}/{max_lim} codes sent today). Please try again tomorrow or use your Emergency Recovery Key."

    payload = json.dumps({
        "email": email.strip(),
        "otp": otp.strip(),
        "purpose": purpose.strip() if purpose else "reset_password",
    }).encode("utf-8")
    req = urllib.request.Request(
        RECOVERY_WORKER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DeskWarden-desktop/1.1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                new_c = record_daily_otp_sent(purpose)
                log_security_event("otp_sent", "Recovery", f"OTP dispatched to {mask_email(email)} (purpose={purpose}, count={new_c})")
                return True, "Verification code sent to your email!"
            return False, data.get("error", "Failed to send verification code.")
    except urllib.error.HTTPError as e:
        err_msg = "Server rejected request"
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            err_msg = err_data.get("error") or err_msg
        except Exception:
            pass
        return False, f"Email delivery failed ({e.code}): {err_msg}"
    except urllib.error.URLError as e:
        return False, f"Network error: Unable to reach server. Check your connection."
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════
# Constants
# ═════════════════════════════════════════════════════════════════════════

MAX_LOG_ENTRIES = 1000

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

def record_wrong_attempt(context: str, event_type: str = "wrong_password", note: str = "") -> dict:
    with _attempt_lock:
        st = _attempt_state.setdefault(context, {"count": 0, "until": 0.0})
        st["count"] += 1
        event_note = note if note else f"attempt #{st['count']}"
        log_security_event(event_type, context, event_note)
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
