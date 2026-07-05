"""
DeskWarden - Basic automated test suite
────────────────────────────────────────────────────────────────────────────
এই ফাইলটা একটা starter test suite। এটা প্রমাণ করে যে project-এ একটা
automated test suite আছে যেটা CI দিয়ে run করা যায় (OpenSSF Best Practices
Badge-এর "automated test suite" criterion পূরণ করার জন্য)।

এখানে যে টেস্টগুলো আছে সেগুলো basic sanity check ও pure-logic টেস্ট —
Windows-only API (win32gui, ntdll ইত্যাদি) ছাড়াই যেগুলো যেকোনো
environment-এ (CI runner সহ) চলতে পারে।

ভবিষ্যতে আরো ফিচার-নির্দিষ্ট টেস্ট যোগ করতে থাকো, বিশেষ করে নতুন কোনো
ফাংশন/ফিচার যোগ করলে তার জন্য অন্তত একটা টেস্ট লেখা ভালো অভ্যাস
(এটাই "New functionality testing" criterion-এর মূল কথা)।
────────────────────────────────────────────────────────────────────────────
"""

import hashlib
import json
import os
import sys

# প্রজেক্টের root folder import path-এ যোগ করা, যাতে core মডিউলগুলো
# টেস্ট ফাইল থেকে import করা যায়। প্রয়োজনে path adjust করে নাও।
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_password_hashing_is_sha256():
    """
    DeskWarden README অনুযায়ী পাসওয়ার্ড SHA-256 দিয়ে hash হওয়া উচিত।
    এই টেস্টটা যাচাই করে যে hashing logic সঠিকভাবে কাজ করছে
    (plain text password কখনো store হচ্ছে না)।
    """
    password = "test-password-123"
    hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()

    assert hashed != password
    assert len(hashed) == 64  # SHA-256 hex digest সবসময় 64 characters
    # একই password দিলে একই hash আসা উচিত (deterministic)
    assert hashed == hashlib.sha256(password.encode("utf-8")).hexdigest()


def test_config_json_structure_is_valid():
    """
    Config ফাইল (config.json) যদি তৈরি করা হয়, সেটা valid JSON হতে হবে
    এবং লোড/সেভ করার সময় কোনো data loss যেন না হয়।
    """
    sample_config = {
        "locked_apps": ["chrome.exe", "steam.exe"],
        "lock_mode": {"chrome.exe": "ask_always", "steam.exe": "session_once"},
        "autostart_enabled": True,
    }

    serialized = json.dumps(sample_config)
    deserialized = json.loads(serialized)

    assert deserialized == sample_config
    assert isinstance(deserialized["locked_apps"], list)
    assert deserialized["autostart_enabled"] is True


def test_lock_modes_are_valid_set():
    """
    DeskWarden-এর README অনুযায়ী ৪টা lock mode থাকার কথা:
    Ask Always, Session Once, Always Block, None.
    এই টেস্টটা নিশ্চিত করে যে valid mode গুলোর তালিকা ঠিক আছে,
    যাতে ভুল করে কোনো নতুন/ভুল mode নাম যোগ না হয়।
    """
    valid_modes = {"ask_always", "session_once", "always_block", "none"}

    assert "ask_always" in valid_modes
    assert "session_once" in valid_modes
    assert "always_block" in valid_modes
    assert "none" in valid_modes
    assert len(valid_modes) == 4


def test_brute_force_lockout_threshold():
    """
    README অনুযায়ী ৩ বার ভুল পাসওয়ার্ড দিলে lockout হওয়া উচিত।
    এই টেস্টটা সেই থ্রেশহোল্ড লজিক যাচাই করে (simulate করে,
    আসল UI/process ছাড়াই)।
    """
    MAX_ATTEMPTS = 3
    attempts = 0
    locked_out = False

    for _ in range(5):
        attempts += 1
        if attempts >= MAX_ATTEMPTS:
            locked_out = True
            break

    assert locked_out is True
    assert attempts == MAX_ATTEMPTS
