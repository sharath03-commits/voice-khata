"""Our own speech-to-text: Whisper models running on the Voice Khata server.

Default models (change with environment variables):
  Kannada  VK_STT_KN  = vasista22/whisper-kannada-small   (Whisper fine-tuned on Kannada speech, IIT Madras)
  Hindi    VK_STT_HI  = vasista22/whisper-hindi-small     (Whisper fine-tuned on Hindi speech, IIT Madras)
  English  VK_STT_EN  = openai/whisper-base
  Wake     VK_STT_WAKE= openai/whisper-tiny               (small + fast, only listens for "Hey Khata")

Models download once (from Hugging Face) on first use and then run offline on CPU.
"""
from __future__ import annotations

import math
import os
import threading
import time

import numpy as np

from .audio import SAMPLE_RATE, prepare

MODEL_IDS = {
    "kn": os.getenv("VK_STT_KN", "vasista22/whisper-kannada-small"),
    "hi": os.getenv("VK_STT_HI", "vasista22/whisper-hindi-small"),
    "en": os.getenv("VK_STT_EN", "openai/whisper-base"),
    "wake": os.getenv("VK_STT_WAKE", "openai/whisper-tiny"),
}
FALLBACK_ID = os.getenv("VK_STT_FALLBACK", "openai/whisper-small")
LANG_NAME = {"kn": "kannada", "hi": "hindi", "en": "english"}

_models: dict = {}
_errors: dict = {}
_locks = {k: threading.Lock() for k in MODEL_IDS}


def libraries_ok() -> tuple[bool, str]:
    if all(str(v).strip().lower() == "off" for v in MODEL_IDS.values()):
        return False, "Own speech recogniser is switched off in .env (browser listening is used)"
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True, ""
    except Exception as exc:
        return False, f"Voice libraries not installed ({exc.__class__.__name__}). Run scripts/setup_voice.py"


def _load(slot: str):
    if slot in _models:
        return _models[slot]
    ok, why = libraries_ok()
    if not ok:
        raise RuntimeError(why)
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
    last = None
    for mid in (MODEL_IDS[slot], FALLBACK_ID if slot != "wake" else MODEL_IDS["wake"]):
        try:
            proc = WhisperProcessor.from_pretrained(mid)
            model = WhisperForConditionalGeneration.from_pretrained(mid)
            model.eval()
            _models[slot] = (proc, model, mid)
            _errors.pop(slot, None)
            return _models[slot]
        except Exception as exc:  # try the general multilingual model next
            last = exc
    _errors[slot] = str(last)[:300]
    raise RuntimeError(f"Could not load speech model for {slot}: {last}")


def _generate(proc, model, feats, lang: str, beams: int, prompt: str = ""):
    import torch
    base = dict(max_new_tokens=96, num_beams=beams, num_return_sequences=beams,
                return_dict_in_generate=True, output_scores=True)
    if prompt:
        try:
            base["prompt_ids"] = torch.tensor(proc.get_prompt_ids(prompt))
        except Exception:
            pass
    attempts = []
    if lang in LANG_NAME:
        attempts.append(dict(language=lang, task="transcribe"))
        attempts.append(dict(forced_decoder_ids=proc.get_decoder_prompt_ids(language=LANG_NAME[lang], task="transcribe")))
    attempts.append({})
    last = None
    for extra in attempts:
        for use_prompt in (True, False):
            kw = dict(base, **extra)
            if not use_prompt:
                kw.pop("prompt_ids", None)
            try:
                with torch.no_grad():
                    return model.generate(feats, **kw), kw
            except Exception as exc:
                last = exc
    raise last


def transcribe(audio: np.ndarray, lang: str = "hi", wake: bool = False, hint: str = "") -> dict:
    """audio: float32 mono 16 kHz. Returns {text, alternatives:[{text, confidence}], model, seconds}."""
    slot = "wake" if wake else (lang if lang in ("kn", "hi", "en") else "hi")
    t0 = time.time()
    audio = prepare(audio)
    if audio.size < SAMPLE_RATE * 0.25:
        return {"text": "", "alternatives": [], "model": None, "seconds": 0.0}
    with _locks[slot]:
        proc, model, mid = _load(slot)
        feats = proc(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_features
        beams = 1 if wake else 3
        out, kw = _generate(proc, model, feats, "" if wake else lang, beams, "" if wake else hint)
    texts = proc.batch_decode(out.sequences, skip_special_tokens=True)
    if "prompt_ids" in kw and hint:
        texts = [t.replace(hint, "").strip() for t in texts]
    if getattr(out, "sequences_scores", None) is not None:
        confs = [math.exp(float(s)) for s in out.sequences_scores]
    else:
        try:
            ts = model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)
            confs = [math.exp(float(ts[0].mean()))]
        except Exception:
            confs = [None] * len(texts)
    alts, seen = [], set()
    for t, c in zip(texts, confs):
        t = t.strip()
        if t and t not in seen:
            seen.add(t); alts.append({"text": t, "confidence": round(c, 3) if c is not None else None})
    return {"text": alts[0]["text"] if alts else "", "alternatives": alts, "model": mid,
            "seconds": round(time.time() - t0, 2)}


def status() -> dict:
    ok, why = libraries_ok()
    return {"libraries": ok, "message": why,
            "models": {k: {"id": v, "loaded": k in _models, "error": _errors.get(k)} for k, v in MODEL_IDS.items()}}


def warmup(langs=("hi", "kn", "en"), wake: bool = True) -> dict:
    done = {}
    for slot in list(langs) + (["wake"] if wake else []):
        try:
            with _locks[slot]:
                _load(slot)
            done[slot] = "ready"
        except Exception as exc:
            done[slot] = f"failed: {exc}"[:200]
    return done
