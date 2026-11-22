"""Tests for the own voice assistant: numbers, transliteration, trained language
model, wake word, speech preparation and the voice API (with a stand-in recogniser)."""
import numpy as np
import pytest

from app.numbers import WORD_VALUES, to_words
from app.parser import parse, phonetic_key
from app.speech import wake
from app.speech.tts import prepare_text
from app.translit import to_devanagari, to_kannada


@pytest.mark.parametrize("n,kn,hi,en", [
    (25, "ಇಪ್ಪತ್ತೈದು", "पच्चीस", "twenty five"),
    (340, "ಮುನ್ನೂರ ನಲವತ್ತು", "तीन सौ चालीस", "three hundred forty"),
    (1250, "ಸಾವಿರದ ಇನ್ನೂರ ಐವತ್ತು", "एक हज़ार दो सौ पचास", "one thousand two hundred fifty"),
    (2500, "ಎರಡು ಸಾವಿರದ ಐನೂರು", "दो हज़ार पाँच सौ", "two thousand five hundred"),
])
def test_number_words(n, kn, hi, en):
    assert (to_words(n, "kn"), to_words(n, "hi"), to_words(n, "en")) == (kn, hi, en)


def test_every_spoken_number_reads_back():
    for n in [7, 19, 25, 34, 68, 99, 140, 345, 999, 1250, 2500, 12345]:
        for lang in ("kn", "hi", "en"):
            r = parse(f"Ramesh {to_words(n, lang)} udhaar")
            assert r.amount == n * 100, (n, lang, to_words(n, lang), r.amount)
    assert WORD_VALUES["ಇಪ್ಪತ್ತೈದು"] == 25 and WORD_VALUES["निन्यानबे"] == 99


def test_transliteration_matches_customer_keys():
    for name in ["Ramesh", "Lakshmi", "Suresh", "Priya", "Govind"]:
        assert phonetic_key(name) == phonetic_key(to_devanagari(name)) == phonetic_key(to_kannada(name))


@pytest.mark.parametrize("text,kind,amount,name", [
    ("ಸುರೇಶ್ ಕಡೆಯಿಂದ ಮುನ್ನೂರು ಬಂದಿದೆ", "payment", 30000, "ಸುರೇಶ್"),
    ("priya ne teen sau rupaye lauta diye", "payment", 30000, "Priya"),
    ("ಭವ್ಯ ಮೇಲೆ ಐನೂರು ಉದ್ರಿ", "credit", 50000, "ಭವ್ಯ"),
    ("tejas 2 litre oil 240 udhaar likh lo", "credit", 24000, "Tejas"),
    ("मोहन ने पाँच सौ लौटा दिए", "payment", 50000, "मोहन"),
    ("Kavya took two kilo sugar worth 180", "credit", 18000, "Kavya"),
])
def test_language_model_understands_new_phrasings(text, kind, amount, name):
    r = parse(text)
    assert r.source == "model"
    assert (r.kind, r.amount, r.name) == (kind, amount, name)


def test_language_model_metrics_recorded():
    from app.nlu import model
    m = model.metrics()
    assert model.available()
    assert m["intent_accuracy_new_names_known_phrasing"] > 0.97
    assert m["slot_f1"] > 0.93


@pytest.mark.parametrize("text,is_wake,command", [
    ("Hey Khata", True, ""), ("हे खाता", True, ""), ("ಹೇ ಖಾತಾ", True, ""),
    ("hey khata ramesh ka 340 udhaar", True, "ramesh ka 340 udhaar"),
    ("Ramesh ka khata dikhao", False, ""), ("Thank you.", False, ""),
])
def test_wake_phrase(text, is_wake, command):
    r = wake.find(text)
    assert r["wake"] is is_wake and r["command"] == command


def test_tts_text_is_speakable():
    s = prepare_text("Ramesh ಖಾತೆಗೆ ₹340 ಉದ್ರಿ ಬರೆದಿದೆ. ಬಾಕಿ ₹1,250.", "kn")
    assert "ರಮೇಶ್" in s and "ಮುನ್ನೂರ ನಲವತ್ತು ರೂಪಾಯಿ" in s and not any(c.isdigit() for c in s)
    s = prepare_text("Ramesh का 340 रुपये उधार लिखा। बाकी 140 रुपये।", "hi")
    assert "रमेश" in s and "तीन सौ चालीस रुपये" in s and "रुपये रुपये" not in s


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("VK_REQUIRE_AUTH", "false")
    import importlib
    import app.main as m
    importlib.reload(m)
    from fastapi.testclient import TestClient
    return m, TestClient(m.app)


def _pcm(seconds=1.5):
    return (np.sin(np.linspace(0, 400, int(16000 * seconds))) * 8000).astype("<i2").tobytes()


def test_voice_command_endpoint(client, monkeypatch):
    m, cl = client
    from app.speech import stt
    monkeypatch.setattr(stt, "transcribe", lambda audio, lang="hi", wake=False, hint="": {
        "text": "hey khata Ramesh ka 340 udhaar", "seconds": 0.1, "model": "stand-in",
        "alternatives": [{"text": "hey khata Ramesh ka 340 udhaar", "confidence": 0.9}]})
    cl.post("/api/customers", json={"name": "Ramesh"})
    r = cl.post("/api/voice/command?lang=hi", content=_pcm(), headers={"Content-Type": "application/octet-stream"}).json()
    assert r["status"] == "saved" and r["understanding"]["name"] == "Ramesh"
    assert cl.get("/api/customers").json()[0]["balance_paise"] == 34000


def test_voice_wake_endpoint(client, monkeypatch):
    m, cl = client
    from app.speech import stt
    monkeypatch.setattr(stt, "transcribe", lambda audio, lang="hi", wake=False, hint="": {
        "text": "Hey Khata.", "seconds": 0.1, "model": "stand-in", "alternatives": []})
    r = cl.post("/api/voice/wake", content=_pcm(0.8)).json()
    assert r["wake"] is True and r["command"] == ""


def test_voice_unavailable_is_reported_not_crashed(client, monkeypatch):
    m, cl = client
    from app.speech import stt
    def boom(*a, **k):
        raise RuntimeError("Voice libraries not installed")
    monkeypatch.setattr(stt, "transcribe", boom)
    r = cl.post("/api/voice/command?lang=kn", content=_pcm())
    assert r.status_code == 503
    assert cl.get("/api/voice/status").status_code == 200


def test_nlu_understand_endpoint(client):
    m, cl = client
    r = cl.post("/api/nlu/understand", json={"text": "ಸುರೇಶ್ ಕಡೆಯಿಂದ ಮುನ್ನೂರು ಬಂದಿದೆ"}).json()
    assert r["result"]["kind"] == "payment" and "B-NAME" in r["tags"]


def test_only_owner_number_can_log_in(client, monkeypatch):
    m, cl = client
    monkeypatch.setenv("VK_OWNER_PHONE", "9845000000")
    assert cl.post("/api/auth/request-otp", json={"phone": "9000000001"}).status_code == 403
    assert cl.post("/api/auth/request-otp", json={"phone": "9845000000"}).status_code == 200


def test_tts_engine_fallback_and_cache(tmp_path, monkeypatch):
    from app.speech import tts
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    tts._mem.clear()
    calls = []
    def broken(text, lang):
        calls.append("fast"); raise RuntimeError("no internet")
    def own(text, lang):
        calls.append("own"); return b"RIFF" + b"0" * 600, "audio/wav"
    monkeypatch.setitem(tts.ENGINES, "fast", broken)
    monkeypatch.setitem(tts.ENGINES, "own", own)
    monkeypatch.setattr(tts, "fast_ok", lambda: (True, ""))
    monkeypatch.setattr(tts, "own_libraries_ok", lambda: (True, ""))
    audio, mime, used = tts.speak("ಸರಿ", "kn", "fast")
    assert used == "own" and mime == "audio/wav" and calls == ["fast", "own"]
    tts._mem.clear()
    audio2, _, used2 = tts.speak("ಸರಿ", "kn", "fast")      # from disk cache, no engine call
    assert audio2 == audio and calls == ["fast", "own", "fast"]


def test_tts_slow_engine_is_abandoned(tmp_path, monkeypatch):
    import time
    from app.speech import tts
    monkeypatch.setattr(tts, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tts, "TIME_LIMIT", 0.3)
    tts._mem.clear()
    monkeypatch.setitem(tts.ENGINES, "fast", lambda t, l: (time.sleep(2), (b"x" * 600, "audio/mpeg"))[1])
    monkeypatch.setitem(tts.ENGINES, "own", lambda t, l: (b"y" * 600, "audio/wav"))
    monkeypatch.setattr(tts, "fast_ok", lambda: (True, ""))
    monkeypatch.setattr(tts, "own_libraries_ok", lambda: (True, ""))
    t0 = time.time()
    _, _, used = tts.speak("हाँ", "hi", "fast")
    assert used == "own" and time.time() - t0 < 1.5


def test_voice_check_endpoint(client):
    m, cl = client
    r = cl.get("/api/voice/check").json()
    assert r["language_model"]["ok"] is True
