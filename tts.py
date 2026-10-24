"""
tts.py — natural neural voices for the radio (Microsoft Edge neural voices via the edge-tts package; no key needed).
Persian: fa-IR-DilaraNeural (soft female voice).  English: en-US-EmmaMultilingualNeural.
Audio is cached in memory, so each news item is synthesised once.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from collections import OrderedDict

VOICE_FA = os.environ.get("TTS_VOICE_FA", "fa-IR-DilaraNeural")
VOICE_EN = os.environ.get("TTS_VOICE_EN", "en-US-EmmaMultilingualNeural")
RATE = os.environ.get("TTS_RATE", "-8%")      # a little slower = calmer
PITCH = os.environ.get("TTS_PITCH", "-2Hz")   # a touch lower = warmer

_cache: "OrderedDict[str, bytes]" = OrderedDict()
_lock = threading.Lock()
MAX_ITEMS = 300


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False


async def _synth(text: str, voice: str) -> bytes:
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    out = bytearray()
    async for chunk in com.stream():
        if chunk.get("type") == "audio":
            out.extend(chunk["data"])
    if not out:
        raise RuntimeError("empty audio")
    return bytes(out)


def speak(text: str, lang: str = "fa") -> bytes:
    voice = VOICE_FA if lang == "fa" else VOICE_EN
    key = hashlib.sha256(f"{voice}|{RATE}|{PITCH}|{text}".encode()).hexdigest()
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    audio = asyncio.run(_synth(text[:2500], voice))
    with _lock:
        _cache[key] = audio
        while len(_cache) > MAX_ITEMS:
            _cache.popitem(last=False)
    return audio
