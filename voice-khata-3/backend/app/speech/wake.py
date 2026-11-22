"""'Hey Khata' wake word.

The app listens on the phone's microphone and cuts speech into short clips with
its own voice-activity detector. Each short clip is transcribed here by the small
Whisper model and checked for the wake phrase in any script:
    hey khata · he khata · हे खाता · ಹೇ ಖಾತಾ · ಏ ಖಾತೆ ...
If the shopkeeper said the command in the same breath ("Hey Khata, Ramesh ka 340
udhaar"), the rest of the sentence is returned too.
"""
from __future__ import annotations

import re

from ..parser import to_latin

_WAKE_RE = re.compile(
    r"\b(?:h?e+y?|h?a+y?|hai|hi|ae|ay|oye?|ok|okay)\s*,?\s*"
    r"(?:kh?a+t+h?(?:a+|e+|i+)|kh?a+th|cata|katta|cutter|kutta|carter|khatha|kata)\b")


def _latin(text: str) -> str:
    s = to_latin(text.lower())
    s = re.sub(r"[^a-z\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find(text: str) -> dict:
    """-> {wake: bool, command: str}  (command = whatever followed the wake phrase)."""
    lat = _latin(text)
    m = _WAKE_RE.search(lat)
    if not m and re.fullmatch(r"kh?a+th?(?:a+|e+)", lat):   # just "Khata" on its own
        return {"wake": True, "command": ""}
    if not m:
        return {"wake": False, "command": ""}
    # the wake word must open the sentence (within the first 3 words), not be buried in chatter
    if len(lat[: m.start()].split()) > 2:
        return {"wake": False, "command": ""}
    rest_words = lat[m.end():].split()
    # map back: drop the same number of leading words from the original text
    orig_words = re.sub(r"[,.!?।]", " ", text).split()
    lead = len(lat[: m.end()].split())
    command = " ".join(orig_words[lead:]) if rest_words else ""
    return {"wake": True, "command": command.strip()}


def strip_wake(text: str) -> str:
    r = find(text)
    return r["command"] if r["wake"] else text
