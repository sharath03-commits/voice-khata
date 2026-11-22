"""Voice Khata's spoken replies.

Two engines, chosen per request from the app's settings (no .env editing):

  fast  Google voice through gTTS. Needs internet, replies in ~0.5 s on any laptop.
  own   Meta MMS voices (VITS) running on this server, fully offline:
          Kannada facebook/mms-tts-kan, Hindi facebook/mms-tts-hin, English facebook/mms-tts-eng
        Natural, but slow on old laptops.

If the chosen engine fails or is too slow, the other one is tried, and if both
fail the app falls back to the phone/browser voice. Finished audio is cached on
disk, so phrases like "हाँ, बोलिए" play instantly after the first time.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import os
import re
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..numbers import to_words
from ..parser import to_latin
from ..translit import to_script
from .audio import to_wav

MODEL_IDS = {"kn": os.getenv("VK_TTS_KN", "facebook/mms-tts-kan"),
             "hi": os.getenv("VK_TTS_HI", "facebook/mms-tts-hin"),
             "en": os.getenv("VK_TTS_EN", "facebook/mms-tts-eng")}
RUPEE = {"kn": "ರೂಪಾಯಿ", "hi": "रुपये", "en": "rupees"}
CACHE_DIR = Path(os.getenv("VK_VOICE_CACHE", Path(__file__).resolve().parents[2] / "voice_cache"))
TIME_LIMIT = float(os.getenv("VK_TTS_TIME_LIMIT", "8"))      # seconds before giving up on an engine
# phrases spoken often: generated in the background at start-up so they are instant
COMMON = {"hi": ["हाँ, बोलिए"], "kn": ["ಹೇಳಿ"], "en": ["Yes, tell me"]}

_models: dict = {}
_errors: dict = {}
_lock = threading.Lock()
_mem: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
_pool = cf.ThreadPoolExecutor(max_workers=2)


# ------------------------------------------------------------------ text prep (own voice)
def prepare_text(text: str, lang: str) -> str:
    """Make a reply speakable by an MMS voice: no digits, no English letters in kn/hi."""
    s = text

    def money(m):
        n = int(float(m.group(1).replace(",", "")))
        return f"{to_words(n, lang)} {RUPEE[lang]}"
    s = re.sub(r"₹\s?([\d,]+(?:\.\d+)?)", money, s)
    s = re.sub(r"(?<![\w.])([\d,]+)(?:\.\d+)?(?![\w.])", lambda m: to_words(int(m.group(1).replace(",", "")), lang), s)
    s = re.sub(rf"({re.escape(RUPEE[lang])})(\s+{re.escape(RUPEE[lang])})+", r"\1", s)
    if lang in ("kn", "hi"):
        s = to_script(s, lang)
    else:
        s = re.sub(r"[\u0900-\u097F\u0C80-\u0CFF]+", lambda m: to_latin(m.group(0)), s)
    s = s.replace("।", ".").replace(":", ",")
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ engines
def own_libraries_ok():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True, ""
    except Exception as exc:
        return False, f"Own voice libraries not installed ({exc.__class__.__name__})"


def fast_ok():
    try:
        import gtts  # noqa: F401
        return True, ""
    except Exception:
        return False, "gTTS not installed (pip install gTTS)"


def _load(lang: str):
    if lang in _models:
        return _models[lang]
    ok, why = own_libraries_ok()
    if not ok:
        raise RuntimeError(why)
    from transformers import AutoTokenizer, VitsModel
    mid = MODEL_IDS[lang]
    try:
        tok = AutoTokenizer.from_pretrained(mid)
        model = VitsModel.from_pretrained(mid)
        model.eval()
    except Exception as exc:
        _errors[lang] = str(exc)[:300]
        raise
    _models[lang] = (tok, model)
    _errors.pop(lang, None)
    return _models[lang]


def _own(text: str, lang: str) -> tuple[bytes, str]:
    import torch
    spoken = prepare_text(text, lang)
    with _lock:
        tok, model = _load(lang)
        src = spoken
        if getattr(tok, "is_uroman", False):
            try:
                import uroman as ur
                src = ur.Uroman().romanize_string(spoken)
            except Exception:
                src = to_latin(spoken)
        inputs = tok(src, return_tensors="pt")
        with torch.no_grad():
            wav = model(**inputs).waveform[0].cpu().numpy().astype(np.float32)
        rate = model.config.sampling_rate
    pad = np.zeros(int(rate * 0.12), dtype=np.float32)
    return to_wav(np.concatenate([pad, wav, pad]), rate), "audio/wav"


def _fast(text: str, lang: str) -> tuple[bytes, str]:
    import io
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang=lang, tld="co.in" if lang == "en" else "com", timeout=TIME_LIMIT).write_to_fp(buf)
    data = buf.getvalue()
    if len(data) < 500:
        raise RuntimeError("empty audio from fast voice")
    return data, "audio/mpeg"


ENGINES = {"fast": _fast, "own": _own}


# ------------------------------------------------------------------ cache
def _key(engine: str, lang: str, text: str) -> str:
    return hashlib.sha1(f"{engine}|{lang}|{text}".encode()).hexdigest()


def _cache_get(k: str):
    if k in _mem:
        _mem.move_to_end(k)
        return _mem[k]
    for ext, mime in ((".mp3", "audio/mpeg"), (".wav", "audio/wav")):
        f = CACHE_DIR / (k + ext)
        if f.exists():
            out = (f.read_bytes(), mime)
            _mem[k] = out
            return out
    return None


def _cache_put(k: str, out: tuple[bytes, str]):
    _mem[k] = out
    if len(_mem) > 300:
        _mem.popitem(last=False)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / (k + (".mp3" if out[1] == "audio/mpeg" else ".wav"))).write_bytes(out[0])
    except OSError:
        pass


# ------------------------------------------------------------------ public
def speak(text: str, lang: str, engine: str = "fast") -> tuple[bytes, str, str]:
    """-> (audio, mime, engine_used). Tries the chosen engine, then the other, each with a time limit."""
    lang = lang if lang in MODEL_IDS else "en"
    text = (text or "").strip()[:600]
    if not text:
        raise RuntimeError("nothing to say")
    order = [engine, "own" if engine == "fast" else "fast"] if engine in ENGINES else ["fast", "own"]
    errors = []
    for eng in order:
        k = _key(eng, lang, text)
        hit = _cache_get(k)
        if hit:
            return hit[0], hit[1], eng
        if eng == "own" and not own_libraries_ok()[0]:
            errors.append("own: not installed"); continue
        if eng == "fast" and not fast_ok()[0]:
            errors.append("fast: not installed"); continue
        fut = _pool.submit(ENGINES[eng], text, lang)
        try:
            # the own voice loads its model the first time; allow longer once
            limit = TIME_LIMIT * (6 if eng == "own" and lang not in _models else 1)
            out = fut.result(timeout=limit)
        except cf.TimeoutError:
            errors.append(f"{eng}: slower than {TIME_LIMIT:.0f}s")
            continue
        except Exception as exc:
            errors.append(f"{eng}: {exc}"[:160])
            continue
        _cache_put(k, out)
        return out[0], out[1], eng
    raise RuntimeError("; ".join(errors) or "no voice available")


def prewarm(engine: str = "fast"):
    """Generate the common phrases in the background so they play instantly."""
    def run():
        for lang, phrases in COMMON.items():
            for p in phrases:
                try:
                    speak(p, lang, engine)
                except Exception:
                    pass
    threading.Thread(target=run, daemon=True).start()


def status() -> dict:
    own_ok, own_why = own_libraries_ok()
    f_ok, f_why = fast_ok()
    return {"fast": {"available": f_ok, "message": f_why},
            "own": {"available": own_ok, "message": own_why,
                    "models": {k: {"id": v, "loaded": k in _models, "error": _errors.get(k)} for k, v in MODEL_IDS.items()}},
            # kept for older screens
            "libraries": own_ok or f_ok}


def warmup(langs=("hi", "kn", "en")) -> dict:
    out = {}
    for l in langs:
        try:
            with _lock:
                _load(l)
            out[l] = "ready"
        except Exception as exc:
            out[l] = f"failed: {exc}"[:200]
    return out


# backwards compatible name used by setup_voice.py
def synthesize(text: str, lang: str) -> bytes:
    return _own(text, lang)[0]
