"""
DeskWarden - core/updater.py

"""

import json
import os
import threading
import urllib.request
import urllib.error

from .config import load_config, save_config
from .logging_utils import dlog


CURRENT_VERSION  = "v1.1.0"
GITHUB_API_URL   = "https://api.github.com/repos/muntasir018/DeskWarden/releases/latest"


WORKER_FALLBACK_URL = "https://deskwarden-update-proxy.mdmuntasir017.workers.dev/"


AUTO_CHECK_INTERVAL_HOURS = 24

# ═════════════════════════════════════════════════════════════════════════
# 🧪 TEST MODE — for trying out the toast/badge/red-dot/catalog flow
# without waiting for a real new GitHub release.
# ═════════════════════════════════════════════════════════════════════════
FAKE_UPDATE_TEST_MODE = False

def _fake_update_result() -> dict:
    
    fake_latest = "v9.9.9"   
    return {
        "update_available": True,
        "latest": fake_latest,
        "url": "https://github.com/muntasir018/DeskWarden/releases/latest",
        "download_url": "https://github.com/muntasir018/DeskWarden/releases/latest",
        "notes": [
            "This is a FAKE test update — for checking the notification flow only.",
            "Improved lock-screen animations",
            "Fixed a rare crash on Task Scheduler autostart",
            "General performance improvements",
        ],
        "error": None,
    }

_update_result   = {"checked": False, "latest": None, "url": None, "error": None}
_update_lock     = threading.Lock()

def _version_tuple(v: str, length: int = 4):
   
    clean = v.lstrip("vV").strip()
    try:
        parts = [int(x) for x in clean.split(".")]
    except Exception:
        return (0,) * length
    parts = parts[:length] + [0] * (length - len(parts))
    return tuple(parts)

def _fetch_release_json(url: str, timeout: int):

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DeskWarden-updater/1.0",
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def _extract_download_url(data: dict, html_url: str) -> str:
    
    try:
        assets = data.get("assets") or []
        for ext in (".exe", ".zip"):
            for a in assets:
                name = (a.get("name") or "").lower()
                url  = a.get("browser_download_url") or ""
                if name.endswith(ext) and url:
                    return url
        if assets:
            url = assets[0].get("browser_download_url") or ""
            if url:
                return url
    except Exception:
        pass
    return html_url


def _extract_notes(data: dict, max_lines: int = 6) -> list:
    
    body = (data.get("body") or "").strip()
    if not body:
        return []
    lines = []
    for raw in body.splitlines():
        line = raw.strip().lstrip("-*#").strip()
        if not line:
            continue
        if len(line) > 140:
            line = line[:137] + "..."
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def check_for_update(timeout: int = 8) -> dict:

    dlog("INFO", f"check_for_update: FAKE_UPDATE_TEST_MODE={FAKE_UPDATE_TEST_MODE} "
                 f"(running from: {os.path.abspath(__file__)})")

    if FAKE_UPDATE_TEST_MODE:
        result = _fake_update_result()
        with _update_lock:
            _update_result.update({"checked": True,
                                    "latest": result["latest"],
                                    "url":    result["url"],
                                    "download_url": result.get("download_url", ""),
                                    "notes":  result.get("notes", []),
                                    "error":  None})
        try:
            import datetime as _dt2
            _cfg_tmp = load_config()
            _cfg_tmp["last_update_check"] = _dt2.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_config(_cfg_tmp)
        except Exception:
            pass
        return result

    result = {"update_available": False, "latest": CURRENT_VERSION,
              "url": "", "download_url": "", "notes": [], "error": None}
    data = None
    last_err = None

    try:
        data = _fetch_release_json(GITHUB_API_URL, timeout)
    except Exception as e:
        last_err = e
        if WORKER_FALLBACK_URL:
            try:
                data = _fetch_release_json(WORKER_FALLBACK_URL, timeout)
                last_err = None
            except Exception as e2:
                last_err = e2

    if data is not None:
        latest   = data.get("tag_name", "").strip()
        html_url = data.get("html_url", "")

        result["latest"]       = latest
        result["url"]          = html_url
        result["download_url"] = _extract_download_url(data, html_url)
        result["notes"]        = _extract_notes(data)
        result["update_available"] = (
            bool(latest) and
            _version_tuple(latest) > _version_tuple(CURRENT_VERSION)
        )
    elif last_err is not None:
        if isinstance(last_err, urllib.error.URLError):
            result["error"] = f"Network error: {last_err.reason}"
        else:
            result["error"] = str(last_err)

    with _update_lock:
        _update_result.update({"checked": True,
                                "latest": result["latest"],
                                "url":    result["url"],
                                "download_url": result.get("download_url", ""),
                                "notes":  result.get("notes", []),
                                "error":  result["error"]})
    # Save last check time to config (only on success or "up to date")
    if not result.get("error"):
        try:
            import datetime as _dt2
            _cfg_tmp = load_config()
            _cfg_tmp["last_update_check"] = _dt2.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_config(_cfg_tmp)
        except Exception:
            pass
    return result

def check_for_update_async(callback=None):
 
    def _worker():
        res = check_for_update()
        if callback:
            try:
                callback(res)
            except Exception:
                pass
    t = threading.Thread(target=_worker, daemon=True, name="update-checker")
    t.start()
    return t

def _should_auto_check(cfg: dict) -> bool:
    if FAKE_UPDATE_TEST_MODE:
        return True  
 
    last = cfg.get("last_update_check", "")
    if not last:
        return True
    try:
        import datetime as _dt3
        last_dt = _dt3.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        elapsed = (_dt3.datetime.now() - last_dt).total_seconds()
        return elapsed >= AUTO_CHECK_INTERVAL_HOURS * 3600
    except Exception:
        return True

def check_for_update_auto_async(callback=None):

    cfg = load_config()
    if not _should_auto_check(cfg):
        return None
    return check_for_update_async(callback=callback)


def skip_version_for_today(version: str):
    
    import datetime as _dt4
    try:
        cfg = load_config()
        cfg["update_skip_version"] = version or ""
        cfg["update_skip_until"] = (
            _dt4.datetime.now() + _dt4.timedelta(hours=24)
        ).strftime("%Y-%m-%d %H:%M:%S")
        save_config(cfg)
    except Exception:
        pass


def is_version_skipped(version: str) -> bool:
    """True if this exact version was skipped and the 24h window hasn't
    passed yet."""
    if not version:
        return False
    import datetime as _dt5
    try:
        cfg = load_config()
        if cfg.get("update_skip_version") != version:
            return False
        until = cfg.get("update_skip_until", "")
        if not until:
            return False
        until_dt = _dt5.datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
        return _dt5.datetime.now() < until_dt
    except Exception:
        return False


def get_cached_update_snapshot() -> dict:
    
    with _update_lock:
        snap = dict(_update_result)
    latest = snap.get("latest")
    checked = snap.get("checked")
    snap["update_available"] = bool(
        checked and latest and
        _version_tuple(latest) > _version_tuple(CURRENT_VERSION)
    )
    return snap


def friendly_error_message(raw_error) -> str:

    if not raw_error:
        return ""
    low = str(raw_error).lower()

    if "rate limit" in low or " 403" in low or low.strip().endswith("403"):
        return "Update check limit reached — please try again in 24 hours"
    if "timed out" in low or "timeout" in low:
        return "Connection timed out — check your internet and try again"
    if any(x in low for x in (
            "getaddrinfo failed", "name or service not known",
            "network is unreachable", "no address associated")):
        return "No internet connection — please check your network"
    return "Could not check for updates — please try again later"

