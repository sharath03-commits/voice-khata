"""Romanised Indian names -> Devanagari / Kannada.

Used by our own text-to-speech (the Kannada and Hindi voices can only read their
own script) and to generate native-script training data for the language model.

    to_devanagari("Ramesh")  -> "रमेश"
    to_kannada("Lakshmi")    -> "ಲಕ್ಷ್ಮಿ"
"""
from __future__ import annotations

import re

# longest patterns first
_CONS = [
    ("ksh", "क्ष"), ("chh", "छ"), ("shr", "श्र"), ("gy", "ज्ञ"),
    ("kh", "ख"), ("gh", "घ"), ("ch", "च"), ("jh", "झ"), ("th", "त"), ("dh", "ध"),
    ("ph", "फ"), ("bh", "भ"), ("sh", "श"),
    ("k", "क"), ("g", "ग"), ("c", "क"), ("j", "ज"), ("t", "त"), ("d", "द"), ("n", "न"),
    ("p", "प"), ("b", "ब"), ("m", "म"), ("y", "य"), ("r", "र"), ("l", "ल"), ("v", "व"),
    ("w", "व"), ("s", "स"), ("h", "ह"), ("f", "फ"), ("z", "ज"), ("q", "क"), ("x", "क्स"),
]
_VOW = [  # (latin, independent, sign)
    ("aa", "आ", "ा"), ("ai", "ऐ", "ै"), ("au", "औ", "ौ"), ("ee", "ई", "ी"), ("ii", "ई", "ी"),
    ("oo", "ऊ", "ू"), ("uu", "ऊ", "ू"), ("ou", "औ", "ौ"),
    ("a", "अ", ""), ("e", "ए", "े"), ("i", "इ", "ि"), ("o", "ओ", "ो"), ("u", "उ", "ु"), ("y", "ई", "ी"),
]
_VIRAMA = "्"


def _match(word: str, i: int, table):
    for item in table:
        if word.startswith(item[0], i):
            return item
    return None


# common name endings that are spoken with a long "aa" (Manjunath, Basavaraj, Prasad)
_LONG_A_ENDINGS = ("nath", "raj", "ram", "kant", "kanth", "prasad", "lal", "das", "bai", "rao", "swamy")


def _word_to_dev(word: str, final_virama: bool) -> str:
    w = word.lower()
    for end in _LONG_A_ENDINGS:
        if w.endswith(end) and len(w) > len(end):
            w = w[: -len(end)] + end.replace("a", "aa", 1)
            break
    # "Bhyrav" -> bhairav: a y between consonants is the vowel "ai"
    w = re.sub(r"(?<=[bcdfghjklmnpqrstvwxz])y(?=[bcdfghjklmnpqrstvwxz])", "ai", w)
    out, i, prev_cons = [], 0, False
    while i < len(w):
        if not w[i].isalpha():
            out.append(w[i]); i += 1; prev_cons = False; continue
        # 'y' acts as a vowel only after a consonant at the end (Shreya keeps y as consonant)
        v = _match(w, i, _VOW)
        if v and not (v[0] == "y" and (not prev_cons or i + 1 < len(w))):
            out.append(v[2] if prev_cons else v[1])
            i += len(v[0]); prev_cons = False; continue
        c = _match(w, i, _CONS)
        if c:
            if prev_cons:
                out.append(_VIRAMA)
            out.append(c[1]); i += len(c[0]); prev_cons = True; continue
        i += 1
    if prev_cons and final_virama:
        out.append(_VIRAMA)
    s = "".join(out)
    # a word-final short 'a' is written long in names: "Seema" -> सीमा, "Ganga" -> गंगा
    if w.endswith("a") and not w.endswith("aa") and len(w) > 2:
        s = s + "ा" if not s.endswith("ा") else s
    for a, b in (("न्ग", "ंग"), ("न्क", "ंक"), ("म्ब", "ंब"), ("न्ज", "ंज"), ("न्द", "ंद"), ("न्त", "ंत")):
        s = s.replace(a, b)
    return s


def to_devanagari(text: str) -> str:
    return re.sub(r"[A-Za-z]+", lambda m: _word_to_dev(m.group(0), final_virama=False), text)


def _dev_to_kannada(s: str) -> str:
    return "".join(chr(ord(c) + 0x380) if 0x0900 <= ord(c) <= 0x097F else c for c in s)


def to_kannada(text: str) -> str:
    # Kannada writes the final consonant with a virama: ರಮೇಶ್
    return re.sub(r"[A-Za-z]+", lambda m: _dev_to_kannada(_word_to_dev(m.group(0), final_virama=True)), text)


def to_script(text: str, lang: str) -> str:
    if lang == "hi":
        return to_devanagari(text)
    if lang == "kn":
        return to_kannada(text)
    return text
