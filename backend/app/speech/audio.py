"""Audio helpers: raw 16 kHz PCM from the app <-> numpy, WAV encoding, trimming."""
from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 16000


def pcm16_to_float(data: bytes) -> np.ndarray:
    """Little-endian 16-bit mono PCM (what the app sends) -> float32 in [-1, 1]."""
    if len(data) % 2:
        data = data[:-1]
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def prepare(audio: np.ndarray) -> np.ndarray:
    """Trim leading/trailing silence and normalise loudness (helps in a noisy shop)."""
    if audio.size == 0:
        return audio
    frame = 320  # 20 ms
    n = audio.size // frame
    if n > 4:
        rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
        thr = max(rms.min() * 3, rms.max() * 0.08, 0.004)
        voiced = np.where(rms > thr)[0]
        if voiced.size:
            a = max(0, (voiced[0] - 10) * frame)
            b = min(audio.size, (voiced[-1] + 15) * frame)
            audio = audio[a:b]
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if 0 < peak < 0.6:
        audio = audio * (0.6 / peak)
    return audio.astype(np.float32)


def to_wav(samples: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def duration(audio: np.ndarray) -> float:
    return audio.size / SAMPLE_RATE
