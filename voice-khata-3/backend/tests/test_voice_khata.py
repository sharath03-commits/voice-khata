import pytest

from app.engine import Engine
from app.ledger import Ledger
from app.parser import parse, phonetic_key


@pytest.fixture
def eng(tmp_path):
    return Engine(Ledger(str(tmp_path / "t.db")))


def say(eng, text, lang=None, conf=0.9):
    return eng.handle([{"text": text, "confidence": conf}], lang)


def seed(eng, *names):
    return [eng.ledger.add_customer(n) for n in names]


# ------------------------------------------------------------------ parser
@pytest.mark.parametrize("text,kind,amount,name", [
    ("Ramesh ka 340 udhaar", "credit", 34000, "Ramesh"),
    ("Ramesh ne 200 diya", "payment", 20000, "Ramesh"),
    ("Lakshmi 1,250 credit", "credit", 125000, "Lakshmi"),
    ("Received 200 from Govind", "payment", 20000, "Govind"),
    ("Suresh do sau pachas jama", "payment", 25000, "Suresh"),
    ("saade teen sau Ramesh ka udhaar", "credit", 35000, "Ramesh"),
    ("dedh hazaar udhaar Lakshmi", "credit", 150000, "Lakshmi"),
    ("Lakshmi 2 kilo sugar 90 rupaye udhaar", "credit", 9000, "Lakshmi"),
    ("Ramesh 2k udhaar", "credit", 200000, "Ramesh"),
    ("ರಮೇಶ್‌ಗೆ 340 ಉದ್ರಿ", "credit", 34000, "ರಮೇಶ್"),
    ("ರಮೇಶ್ 200 ಕೊಟ್ಟರು", "payment", 20000, "ರಮೇಶ್"),
    ("ಸುರೇಶ್ ಎರಡು ಸಾವಿರದ ಐನೂರು ಉದ್ರಿ", "credit", 250000, "ಸುರೇಶ್"),
    ("रमेश का ३४० उधार", "credit", 34000, "रमेश"),
    ("₹75 jama Suresh", "payment", 7500, "Suresh"),
])
def test_parse_transactions(text, kind, amount, name):
    r = parse(text)
    assert r.intent == "transaction"
    assert (r.kind, r.amount, r.name) == (kind, amount, name)


def test_cross_script_names_match():
    assert phonetic_key("Ramesh") == phonetic_key("रमेश") == phonetic_key("ರಮೇಶ್")
    assert phonetic_key("Lakshmi") == phonetic_key("ಲಕ್ಷ್ಮಿ") == phonetic_key("लक्ष्मी")


def test_parse_queries_and_commands():
    assert parse("रमेश का कितना बाकी है").intent == "balance"
    assert parse("ರಮೇಶ್ ಬಾಕಿ ಎಷ್ಟು").intent == "balance"
    assert parse("aaj ka hisaab").intent == "report_today"
    assert parse("sabka baaki kitna").intent == "report_all"
    assert parse("Nahi, 430").intent == "correction"
    assert parse("undo").intent == "undo"
    assert parse("haan").intent == "yes"


def test_two_amounts_are_ambiguous():
    r = parse("Ramesh 340 200")
    assert r.amount is None and r.amount_options == [34000, 20000]


# ------------------------------------------------------------------ dialogue
def test_deck_demo_flow(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh ka 340 udhaar.")
    assert out["status"] == "saved"
    assert out["text"] == "Ramesh ka ₹340 udhaar likha. Baaki ₹340."
    out = say(eng, "Ramesh ne 200 diya.")
    assert out["status"] == "saved"
    assert "Baaki ₹140" in out["text"]


def test_new_customer_needs_confirmation(eng):
    out = say(eng, "Suresh ka 180 udhaar")
    assert out["status"] == "ask" and out["message_key"] == "confirm_new"
    assert eng.ledger.list_customers() == []
    out = say(eng, "haan")
    assert out["status"] == "saved" and out["new_customer"] is True
    assert eng.ledger.list_customers()[0]["balance_paise"] == 18000


def test_voice_correction_while_confirming(eng):
    say(eng, "Suresh ka 340 udhaar")           # new customer -> asks
    out = say(eng, "Nahi, 430")
    assert out["status"] == "saved"
    assert eng.ledger.list_customers()[0]["balance_paise"] == 43000


def test_voice_correction_after_saving(eng):
    seed(eng, "Ramesh")
    say(eng, "Ramesh ka 340 udhaar")
    out = say(eng, "Nahi, 430")
    assert out["message_key"] == "corrected"
    c = eng.ledger.list_customers()[0]
    assert c["balance_paise"] == 43000
    txns = eng.ledger.transactions_for(c["id"])
    assert txns[1]["voided_at"] and txns[0]["replaces_id"] == txns[1]["id"]


def test_missing_amount_asks_back(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh ka udhaar")
    assert out["status"] == "ask" and out["asking"] == "amount"
    out = say(eng, "340")
    assert out["status"] == "saved"


def test_unclear_type_asks_back(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh 500")
    assert out["asking"] == "type"
    out = say(eng, "jama")
    assert out["status"] == "ask" and out["message_key"] == "confirm_overpay"
    out = say(eng, "haan")
    assert out["status"] == "saved"
    assert eng.ledger.list_customers()[0]["balance_paise"] == -50000


def test_two_amounts_asks_which(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh 340 200 udhaar")
    assert out["asking"] == "amount_pick"
    out = eng.handle([], choice={"type": "amount", "value": 34000})
    assert out["status"] == "saved"


def test_duplicate_names_resolved_by_voice(eng):
    seed(eng, "Ramesh Gowda", "Ramesh Kumar")
    out = say(eng, "Ramesh ka 100 udhaar")
    assert out["asking"] == "which"
    out = say(eng, "Kumar")
    assert out["status"] == "saved"
    assert "Ramesh Kumar" in out["text"]


def test_same_name_resolved_by_tag(eng):
    eng.ledger.add_customer("Ramesh", tag="doodh wala")
    eng.ledger.add_customer("Ramesh", tag="school")
    out = say(eng, "Ramesh ka 100 udhaar")
    assert out["asking"] == "which"
    out = say(eng, "doodh wala")
    assert out["status"] == "saved" and "doodh wala" in out["text"]


def test_low_stt_confidence_confirms(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh ka 340 udhaar", conf=0.3)
    assert out["status"] == "ask" and out["message_key"] == "confirm"
    assert say(eng, "no")["message_key"] == "cancelled"
    assert eng.ledger.list_customers()[0]["balance_paise"] == 0


def test_large_amount_confirms(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh ka 12000 udhaar")
    assert out["message_key"] == "confirm"


def test_duplicate_entry_confirms(eng):
    seed(eng, "Ramesh")
    say(eng, "Ramesh ka 340 udhaar")
    out = say(eng, "Ramesh ka 340 udhaar")
    assert out["message_key"] == "confirm_duplicate"


def test_cross_script_customer_reuse(eng):
    seed(eng, "Ramesh")
    out = say(eng, "ರಮೇಶ್‌ಗೆ 340 ಉದ್ರಿ")
    assert out["status"] == "saved" and out["lang"] == "kn"
    assert len(eng.ledger.list_customers()) == 1
    assert "ರೂಪಾಯಿ" in out["speak"]


def test_hindi_tts_is_devanagari(eng):
    seed(eng, "Ramesh")
    out = say(eng, "Ramesh ka 340 udhaar")
    assert out["tts_lang"] == "hi-IN" and "उधार" in out["speak"]


def test_balance_and_reports(eng):
    seed(eng, "Ramesh", "Lakshmi")
    say(eng, "Ramesh ka 340 udhaar")
    say(eng, "Lakshmi 1250 udhaar")
    say(eng, "Ramesh ne 200 diya")
    assert "₹140" in say(eng, "Ramesh ka baaki kitna")["text"]
    rep = say(eng, "aaj ka hisaab")
    assert rep["report"]["credit_paise"] == 159000 and rep["report"]["payment_paise"] == 20000
    allr = say(eng, "sabka baaki kitna")
    assert allr["report"]["outstanding_paise"] == 139000


def test_undo(eng):
    seed(eng, "Ramesh")
    say(eng, "Ramesh ka 340 udhaar")
    out = say(eng, "undo")
    assert out["status"] == "undone"
    assert eng.ledger.list_customers()[0]["balance_paise"] == 0


def test_alternatives_pick_best(eng):
    seed(eng, "Ramesh")
    out = eng.handle([{"text": "remesh car 340 udar", "confidence": 0.5},
                      {"text": "Ramesh ka 340 udhaar", "confidence": 0.7}])
    assert out["status"] == "saved"


def test_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("VK_REQUIRE_AUTH", "false")
    import importlib
    import app.main as m
    importlib.reload(m)
    from fastapi.testclient import TestClient
    cl = TestClient(m.app)
    assert cl.post("/api/customers", json={"name": "Ramesh"}).status_code == 201
    r = cl.post("/api/utterance", json={"text": "Ramesh ka 340 udhaar"}).json()
    assert r["status"] == "saved"
    assert cl.get("/api/customers").json()[0]["balance_paise"] == 34000
    assert cl.get("/api/report/today").json()["credit_paise"] == 34000
    assert "Ramesh" in cl.get("/api/export.csv").text
    assert cl.get("/").status_code == 200
