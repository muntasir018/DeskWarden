"""
DeskWarden - tests/conftest.py

    DeskWarden/
        src/
            deskwarden/...
            DeskWarden.py
        tests/              
            conftest.py
            test_security.py
            test_config.py
            test_main_window_smoke.py

চালানোর নিয়ম:
    pip install pytest
    pytest tests/ -v
"""

import os
import sys
import pathlib

import pytest

# ─────────────────────────────────────────────────────────────────────────
# Path setup
# ─────────────────────────────────────────────────────────────────────────
_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
_SRC_DIR = _PROJECT_ROOT / "src"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ─────────────────────────────────────────────────────────────────────────
# Isolated AppData
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path, monkeypatch):
    fake_appdata = tmp_path / "DeskWarden"
    fake_appdata.mkdir(parents=True, exist_ok=True)

    from deskwarden.core import paths as _paths
    monkeypatch.setattr(_paths, "APPDATA_DIR", str(fake_appdata), raising=False)
    monkeypatch.setattr(_paths, "CONFIG_PATH", str(fake_appdata / "config.json"), raising=False)
    monkeypatch.setattr(_paths, "SECURITY_LOG_PATH", str(fake_appdata / "security_log.json"), raising=False)
    monkeypatch.setattr(_paths, "DIAGNOSTIC_LOG_PATH", str(fake_appdata / "diagnostic_log.txt"), raising=False)
    monkeypatch.setattr(_paths, "CRASH_LOG_PATH", str(fake_appdata / "crash_log.txt"), raising=False)

    try:
        from deskwarden.core import config as _config
        monkeypatch.setattr(_config, "CONFIG_PATH", str(fake_appdata / "config.json"), raising=False)
        monkeypatch.setattr(_config, "_config_cache", {"mtime": None, "data": None}, raising=False)
    except Exception:
        pass

    try:
        from deskwarden.core import security as _security
        monkeypatch.setattr(_security, "SECURITY_LOG_PATH", str(fake_appdata / "security_log.json"), raising=False)
        monkeypatch.setattr(_security, "APPDATA_DIR", str(fake_appdata), raising=False)
        monkeypatch.setattr(_security, "_attempt_state", {}, raising=False)
    except Exception:
        pass

    yield fake_appdata


# ─────────────────────────────────────────────────────────────────────────
# Shared QApplication
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
