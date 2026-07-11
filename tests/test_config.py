"""
DeskWarden - tests/test_config.py
"""

from deskwarden.core.config import load_config, save_config, _migrate_config


def test_load_config_creates_default_when_missing():
    cfg = load_config()
    assert cfg["password_hash"] == ""
    assert cfg["locked_apps"] == []
    assert cfg["autostart"] is True


def test_save_then_load_round_trip():
    cfg = load_config()
    cfg["password_hash"] = "abc123hash"
    cfg["locked_apps"] = [{"exe": "brave.exe", "mode": "ask_always"}]
    save_config(cfg)

    reloaded = load_config()
    assert reloaded["password_hash"] == "abc123hash"
    assert reloaded["locked_apps"] == [{"exe": "brave.exe", "mode": "ask_always"}]


def test_migrate_config_converts_old_string_list():
    old_style = {"locked_apps": ["Brave.exe", "steam.exe"]}
    migrated = _migrate_config(old_style)
    assert migrated["locked_apps"] == [
        {"exe": "brave.exe", "mode": "ask_always"},
        {"exe": "steam.exe", "mode": "ask_always"},
    ]


def test_migrate_config_preserves_existing_mode():
    cfg = {"locked_apps": [{"exe": "Auth.exe", "mode": "permanent_block"}]}
    migrated = _migrate_config(cfg)
    assert migrated["locked_apps"] == [{"exe": "auth.exe", "mode": "permanent_block"}]


def test_migrate_config_fills_missing_defaults():
    migrated = _migrate_config({})
    for key in ("password_hash", "locked_apps", "autostart",
                "auto_update", "last_update_check"):
        assert key in migrated
