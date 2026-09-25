"""
DeskWarden - core/sound_utils.py

Provides non-blocking audio feedback for unlock and wrong attempt events.
Uses native Windows winsound async playback.
"""

import os
import threading
from .paths import asset_path
from .config import load_config
from .logging_utils import log_crash

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False


def _play_wav_async(filename: str):
    if not _HAS_WINSOUND:
        return
    try:
        cfg = load_config()
        if not cfg.get("sound_enabled", True):
            return
        
        sound_path = asset_path(os.path.join("sounds", filename))
        if not os.path.isfile(sound_path):
            sound_path = asset_path(filename)
            
        if os.path.isfile(sound_path):
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        log_crash(f"sound_utils._play_wav_async({filename})", e)


def play_unlock_sound():
    """Play subtle cyber bloom sound on successful authentication / unlock."""
    threading.Thread(target=_play_wav_async, args=("unlock.wav",), daemon=True).start()


def play_error_sound():
    """Play subtle cyber denied pulse on incorrect password attempt."""
    threading.Thread(target=_play_wav_async, args=("error.wav",), daemon=True).start()


def play_block_sound():
    """Play soft bump sound when a permanently blocked application notice appears."""
    threading.Thread(target=_play_wav_async, args=("block.wav",), daemon=True).start()
