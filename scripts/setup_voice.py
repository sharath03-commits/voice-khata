"""Install and test the Voice Khata own voice assistant on this laptop.

    cd backend
    python ../scripts/setup_voice.py              # Kannada + Hindi + English
    python ../scripts/setup_voice.py --lang kn    # only Kannada (smaller download)

What it does:
 1. installs PyTorch (CPU build, ~200 MB) and the speech libraries
 2. downloads the speech models once (about 1-2.5 GB total, needs internet once)
 3. self-test: our voice SPEAKS a sentence, our recogniser LISTENS to it, our
    language model UNDERSTANDS it -> prints what the ledger would record.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


def pip(*args):
    print("  pip install", " ".join(args))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *args])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="*", default=["kn", "hi", "en"], choices=["kn", "hi", "en"])
    ap.add_argument("--skip-install", action="store_true")
    a = ap.parse_args()

    if not a.skip_install:
        print("1/3 Installing voice libraries")
        try:
            import torch  # noqa: F401
            print("  PyTorch already installed")
        except ImportError:
            pip("torch", "--index-url", "https://download.pytorch.org/whl/cpu")
        pip("-r", str(BACKEND / "requirements-voice.txt"))

    from app.speech import stt, tts
    from app.speech.audio import SAMPLE_RATE
    print("2/3 Downloading and loading models (first time only, please wait)")
    t0 = time.time()
    print("  speech-to-text:", stt.warmup(tuple(a.lang)))
    print("  voice:", tts.warmup(tuple(a.lang)))
    print(f"  done in {time.time() - t0:.0f}s")

    print("3/3 Self-test: speak -> listen -> understand")
    import io, wave
    import numpy as np
    from app.parser import parse
    samples = {"kn": "ರಮೇಶ್ ಮುನ್ನೂರ ನಲವತ್ತು ರೂಪಾಯಿ ಉದ್ರಿ", "hi": "रमेश का तीन सौ चालीस रुपये उधार",
               "en": "Ramesh three hundred forty rupees credit"}
    for lang in a.lang:
        try:
            wav = tts.synthesize(samples[lang], lang)
            with wave.open(io.BytesIO(wav)) as w:
                rate, pcm = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
            audio = pcm.astype(np.float32) / 32768
            if rate != SAMPLE_RATE:   # simple resample to 16 kHz
                idx = np.linspace(0, len(audio) - 1, int(len(audio) * SAMPLE_RATE / rate))
                audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
            heard = stt.transcribe(audio, lang)
            r = parse(heard["text"], lang)
            amt = f"₹{r.amount / 100:.0f}" if r.amount else "-"
            print(f"  [{lang}] said: {samples[lang]}\n       heard: {heard['text']}  ({heard['seconds']}s)\n"
                  f"       understood: {r.intent}, {r.kind}, {r.name}, {amt}  (by {r.source})")
        except Exception as exc:
            print(f"  [{lang}] self-test failed: {exc}")
    print("\nVoice assistant ready. Start the app and open Store -> Voice assistant to see its status.")


if __name__ == "__main__":
    main()
