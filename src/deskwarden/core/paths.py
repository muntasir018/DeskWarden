"""
DeskWarden - core/paths.py

"""

import os
import sys

# ═════════════════════════════════════════════════════════════════════════
# Frozen (EXE) / dev (script) mode
# ═════════════════════════════════════════════════════════════════════════


IS_FROZEN: bool = getattr(sys, "frozen", False)


# ═════════════════════════════════════════════════════════════════════════
# Project root / base directory
# ═════════════════════════════════════════════════════════════════════════

def _compute_project_root() -> str:

    if IS_FROZEN:
        return os.path.dirname(sys.executable)

    this_file = os.path.abspath(__file__)
    
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(this_file)))
    )


PROJECT_ROOT: str = _compute_project_root()


# ═════════════════════════════════════════════════════════════════════════
# Bundled resources (assets/icon.png)
# ═════════════════════════════════════════════════════════════════════════

def resource_path(*parts: str) -> str:

    if IS_FROZEN:
   
        base = getattr(sys, "_MEIPASS", PROJECT_ROOT)
    else:
        base = PROJECT_ROOT
    return os.path.join(base, *parts)


def asset_path(filename: str) -> str:
    
    return resource_path("assets", filename)


# ═════════════════════════════════════════════════════════════════════════
# App data — %APPDATA%\DeskWarden  (config, logs)
# ═════════════════════════════════════════════════════════════════════════

APPDATA_DIR: str = os.path.join(os.environ.get("APPDATA", "."), "DeskWarden")
os.makedirs(APPDATA_DIR, exist_ok=True)

CONFIG_PATH: str         = os.path.join(APPDATA_DIR, "config.json")
SECURITY_LOG_PATH: str   = os.path.join(APPDATA_DIR, "security_log.json")
DIAGNOSTIC_LOG_PATH: str = os.path.join(APPDATA_DIR, "diagnostic_log.txt")
CRASH_LOG_PATH: str      = os.path.join(APPDATA_DIR, "crash_log.txt")


# ═════════════════════════════════════════════════════════════════════════
# relaunch করা
# (elevated service → user-session GUI, Control Panel subprocess spawn )
# ═════════════════════════════════════════════════════════════════════════

def _find_pythonw() -> str:

    base = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "python.exe"):
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def get_own_executable() -> str:

    if IS_FROZEN:
        return sys.executable
    return _find_pythonw()


def build_relaunch_args(*extra_args: str) -> list:

    exe = get_own_executable()
    if IS_FROZEN:
        return [exe, *extra_args]
    script = os.path.join(PROJECT_ROOT, "src", "DeskWarden.py")
    return [exe, script, *extra_args]


def build_relaunch_cmdline(*extra_args: str) -> str:

    parts = build_relaunch_args(*extra_args)
    quote_count = 1 if IS_FROZEN else 2  
    quoted_part = " ".join(f'"{p}"' for p in parts[:quote_count])
    remainder = " ".join(parts[quote_count:])
    return f"{quoted_part} {remainder}".strip()
