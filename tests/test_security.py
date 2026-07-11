"""
DeskWarden - tests/test_security.py
"""

from deskwarden.core.security import (
    hash_pw,
    record_wrong_attempt,
    reset_attempt_state,
    check_locked_out,
    PENALTY_THRES,
)


def test_hash_pw_is_deterministic():
    assert hash_pw("mypassword123") == hash_pw("mypassword123")


def test_hash_pw_different_inputs_differ():
    assert hash_pw("password1") != hash_pw("password2")


def test_hash_pw_not_plaintext():
    pw = "supersecret"
    assert hash_pw(pw) != pw


def test_wrong_attempts_below_threshold_not_locked():
    context = "test_app_below_threshold"
    reset_attempt_state(context)
    for _ in range(PENALTY_THRES - 1):
        result = record_wrong_attempt(context)
    assert result["locked"] is False


def test_wrong_attempts_at_threshold_triggers_lockout():
    context = "test_app_at_threshold"
    reset_attempt_state(context)
    result = None
    for _ in range(PENALTY_THRES):
        result = record_wrong_attempt(context)
    assert result["locked"] is True
    assert result["wait"] > 0


def test_reset_attempt_state_clears_lockout():
    context = "test_app_reset"
    for _ in range(PENALTY_THRES):
        record_wrong_attempt(context)
    reset_attempt_state(context)
    locked, remaining = check_locked_out(context)
    assert locked is False
    assert remaining == 0


def test_check_locked_out_fresh_context_not_locked():
    locked, remaining = check_locked_out("never_seen_before_context")
    assert locked is False
    assert remaining == 0
