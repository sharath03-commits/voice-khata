"""Voice Khata API (FastAPI).

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import csv
import io
import json
import secrets
import hashlib
import os
import base64, hashlib, secrets, urllib.parse, urllib.request, urllib.error
from datetime import timedelta
from fastapi import Request
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

# Load backend/.env (Twilio keys, owner phone, ...) if python-dotenv is installed.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")   # backend/.env
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")   # project-root .env
except ImportError:
    pass

from .engine import Engine
from .ledger import Ledger

DB_PATH = os.getenv("VK_DB", str(Path(__file__).resolve().parents[1] / "voice_khata.db"))
FRONTEND = Path(os.getenv("VK_FRONTEND", Path(__file__).resolve().parents[2] / "frontend"))

app = FastAPI(title="Voice Khata", version="2.0.0",
              description="AI-powered multilingual voice ledger for kirana stores")
ledger = Ledger(DB_PATH)
engine = Engine(ledger)


@app.on_event("startup")
def _language_model_ready():
    """If the trained model is missing or was saved by another scikit-learn version,
    retrain it in the background (about a minute). Rules cover until it's ready."""
    import threading
    from .nlu import model as nlu
    if not nlu.available():
        def _train():
            from .nlu import train
            nlu._loaded["tried"] = False
            train.main(per_intent=1500, test_per_intent=150)
        threading.Thread(target=_train, daemon=True).start()
    try:
        from .speech import tts
        tts.prewarm("fast")
    except Exception:
        pass

@app.middleware("http")
async def owner_auth_guard(request: Request, call_next):
    if os.getenv("VK_REQUIRE_AUTH", "true").lower() == "true" and request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/auth/request-otp", "/api/auth/verify-otp"}:
        token = request.cookies.get("vk_session", "")
        row = ledger.db.execute("SELECT expires_at FROM owner_sessions WHERE token_hash=?", (_hash(token),)).fetchone() if token else None
        if not row or row["expires_at"] < ledger_now().isoformat():
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Owner login required"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------- integrations

def ledger_now():
    from .ledger import now
    return now()

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def _sms_destination(to: str) -> str:
    digits = "".join(ch for ch in (to or "") if ch.isdigit())
    if len(digits) == 10:
        return "+91" + digits
    if digits.startswith("91") and len(digits) == 12:
        return "+" + digits
    return "+" + digits if digits else to

def _twilio_send(to: str, body: str) -> tuple[bool, str, str]:
    to = _sms_destination(to)
    sid, token = os.getenv("TWILIO_ACCOUNT_SID", ""), os.getenv("TWILIO_AUTH_TOKEN", "")
    sender = os.getenv("TWILIO_FROM", "")
    if not (sid and token and sender):
        return False, "", "SMS provider is not configured (set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM)."
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": sender, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            result = json.loads(response.read().decode())
        return True, result.get("sid", ""), ""
    except Exception as exc:
        return False, "", str(exc)[:300]

def notify_transaction(txn: dict) -> None:
    customer = ledger.customer(int(txn["customer_id"]))
    if not customer or not customer.get("phone") or not customer.get("sms_opt_in"):
        return
    store = ledger.get_store()
    shop = store.get("store_name") or "Your store"
    amount = f"₹{txn['amount_paise'] / 100:,.2f}".rstrip("0").rstrip(".")
    balance = customer["balance_paise"]
    bal_text = f"₹{abs(balance) / 100:,.2f}".rstrip("0").rstrip(".")
    action = "credit added" if txn["kind"] == "credit" else "payment received"
    due = f"Outstanding balance: {bal_text}" if balance > 0 else (f"Advance balance: {bal_text}" if balance < 0 else "Your account is settled.")
    msg = f"{shop}: {action.title()} {amount} for {customer['name']}. {due} Thank you."
    ok, sid, error = _twilio_send(customer["phone"], msg)
    ledger.log_sms(customer["id"], customer["phone"], txn["id"], msg,
                   "sent" if ok else "failed", sid, error)

# ---------------------------------------------------------------- models
class Alternative(BaseModel):
    text: str
    confidence: Optional[float] = None


class UtteranceIn(BaseModel):
    alternatives: list[Alternative] = Field(default_factory=list)
    text: Optional[str] = None          # convenience for typed input / curl
    lang_hint: Optional[Literal["en", "hi", "kn"]] = None
    choice: Optional[dict] = None        # tapped option: {"type": "customer", "id": 3}
    confirm: Optional[bool] = None       # tapped Yes / No


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    tag: str = Field(default="", max_length=40)
    phone: str = Field(default="", max_length=20)
    sms_opt_in: bool = False


class CustomerPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    tag: Optional[str] = Field(default=None, max_length=40)
    phone: Optional[str] = Field(default=None, max_length=20)
    sms_opt_in: Optional[bool] = None


class ManualEntry(BaseModel):
    kind: Literal["credit", "payment"]
    amount: float = Field(gt=0, le=10_000_000)  # rupees


class OTPRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=16)

class OTPVerify(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    code: str = Field(min_length=4, max_length=8)

class StoreIn(BaseModel):
    store_name: str = Field(min_length=1, max_length=100)
    owner_name: str = Field(default="", max_length=80)
    phone: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=240)

class LangIn(BaseModel):
    lang: Optional[Literal["en", "hi", "kn"]] = None


# ---------------------------------------------------------------- voice
def run_engine(alts, lang_hint=None, choice=None, confirm=None, background: Optional[BackgroundTasks] = None):
    """Engine + SMS. SMS goes out in the background so the spoken reply is never delayed."""
    before = ledger.db.execute("SELECT COALESCE(MAX(id),0) FROM transactions").fetchone()[0]
    result = engine.handle(alts, lang_hint, choice=choice, confirm=confirm)
    if result.get("status") == "saved":
        row = ledger.db.execute("SELECT id FROM transactions WHERE id>? ORDER BY id DESC LIMIT 1", (before,)).fetchone()
        if row:
            txn = ledger.transaction(row[0])
            if background is not None:
                background.add_task(notify_transaction, txn)
            else:
                notify_transaction(txn)
    return result


@app.post("/api/utterance")
def utterance(body: UtteranceIn, background: BackgroundTasks):
    alts = [a.model_dump() for a in body.alternatives]
    if body.text:
        alts.insert(0, {"text": body.text, "confidence": None})
    return run_engine(alts, body.lang_hint, body.choice, body.confirm, background)


# ---------------------------------------------------------------- own voice assistant
@app.post("/api/voice/command")
async def voice_command(request: Request, background: BackgroundTasks, lang: Literal["en", "hi", "kn"] = "hi"):
    """Raw 16 kHz 16-bit mono PCM from the app -> our speech-to-text -> language model -> ledger."""
    from .speech import audio as au, stt, wake
    pcm = await request.body()
    if len(pcm) < 3200:
        raise HTTPException(400, "Audio too short")
    try:
        heard = await run_in_threadpool(stt.transcribe, au.pcm16_to_float(pcm), lang)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    alts = [{"text": wake.strip_wake(a["text"]), "confidence": a["confidence"]} for a in heard["alternatives"]]
    alts = [a for a in alts if a["text"].strip()]
    if not alts:
        from .messages import render
        return {"status": "error", "message_key": "not_understood", "heard": heard,
                "options": [], **render("not_understood", lang)}
    result = run_engine(alts, lang, background=background)
    result["heard"] = heard
    return result


@app.post("/api/voice/wake")
async def voice_wake(request: Request):
    """Short clip -> is it 'Hey Khata'? Also returns any command said in the same breath."""
    from .speech import audio as au, stt, wake
    pcm = await request.body()
    try:
        heard = await run_in_threadpool(stt.transcribe, au.pcm16_to_float(pcm), "en", True)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    found = wake.find(heard["text"])
    return {**found, "heard": heard["text"], "seconds": heard["seconds"]}


@app.get("/api/voice/tts")
async def voice_tts(text: str, lang: Literal["en", "hi", "kn"] = "hi",
                    engine: Literal["fast", "own"] = "fast"):
    """Spoken reply. engine=fast (Google voice, quick) or own (MMS voice on this server)."""
    from .speech import tts
    try:
        audio, mime, used = await run_in_threadpool(tts.speak, text, lang, engine)
    except Exception as exc:
        raise HTTPException(503, f"Voice unavailable: {exc}"[:300])
    return Response(audio, media_type=mime,
                    headers={"Cache-Control": "private, max-age=86400", "X-Voice-Engine": used})


@app.get("/api/voice/check")
async def voice_check():
    """Self-check for the Store page: is each part working, and how fast?"""
    import time
    from .nlu import model as nlu
    from .parser import parse
    from .speech import stt, tts
    out = {}
    t0 = time.time()
    r = parse("Ramesh ka 340 udhaar")
    out["language_model"] = {"ok": nlu.available() and r.amount == 34000 and r.kind == "credit",
                             "ms": round((time.time() - t0) * 1000)}
    for eng in ("fast", "own"):
        t0 = time.time()
        try:
            _, _, used = await run_in_threadpool(tts.speak, "ಸರಿ", "kn", eng)
            out[f"voice_{eng}"] = {"ok": used == eng, "seconds": round(time.time() - t0, 2), "used": used}
        except Exception as exc:
            out[f"voice_{eng}"] = {"ok": False, "error": str(exc)[:200]}
    s = stt.status()
    out["own_listening"] = {"ok": bool(s["libraries"]), "message": s["message"]}
    return out


@app.get("/api/voice/status")
def voice_status():
    from .nlu import model as nlu
    from .speech import stt, tts
    return {"speech_to_text": stt.status(), "text_to_speech": tts.status(),
            "language_model": {"loaded": nlu.available(), **nlu.metrics()}}


@app.post("/api/voice/warmup")
async def voice_warmup(body: LangIn = LangIn()):
    """Load the voice models into memory so the first command is fast."""
    from .speech import stt, tts
    langs = (body.lang,) if body.lang else ("hi", "kn", "en")
    s = await run_in_threadpool(stt.warmup, langs)
    t = await run_in_threadpool(tts.warmup, langs)
    return {"speech_to_text": s, "text_to_speech": t}


@app.post("/api/nlu/understand")
def nlu_understand(body: UtteranceIn):
    """Debug/demo: show exactly what the language model understood, without saving anything."""
    from .nlu import model as nlu
    from .parser import parse, tokenize
    text = body.text or (body.alternatives[0].text if body.alternatives else "")
    r = parse(text, body.lang_hint)
    pred = nlu.predict(tokenize(text)) or {}
    return {"text": text, "tokens": tokenize(text), "tags": pred.get("tags"), "intent_probabilities": pred.get("probs"),
            "result": {"intent": r.intent, "kind": r.kind, "amount_paise": r.amount, "name": r.name,
                       "language": r.lang, "by": r.source, "model_confidence": r.model_conf}}


@app.post("/api/undo")
def undo(body: LangIn = LangIn()):
    return engine.undo(body.lang)


@app.post("/api/pending/cancel")
def cancel(_: LangIn = LangIn()):
    return engine.cancel()


@app.get("/api/state")
def state():
    return engine.state()


# ---------------------------------------------------------------- ledger
@app.get("/api/customers")
def customers():
    return ledger.list_customers()


@app.post("/api/customers", status_code=201)
def add_customer(body: CustomerIn):
    return ledger.add_customer(body.name, body.tag, body.phone, body.sms_opt_in)


@app.patch("/api/customers/{cid}")
def edit_customer(cid: int, body: CustomerPatch):
    c = ledger.update_customer(cid, body.name, body.tag, body.phone, body.sms_opt_in)
    if not c:
        raise HTTPException(404, "Customer not found")
    return c


@app.get("/api/customers/{cid}")
def customer(cid: int):
    c = ledger.customer(cid)
    if not c:
        raise HTTPException(404, "Customer not found")
    return {**c, "transactions": ledger.transactions_for(cid)}


@app.post("/api/customers/{cid}/entries", status_code=201)
def manual_entry(cid: int, body: ManualEntry, background: BackgroundTasks):
    if not ledger.customer(cid):
        raise HTTPException(404, "Customer not found")
    txn = ledger.add_transaction(cid, body.kind, round(body.amount * 100), source="manual")
    background.add_task(notify_transaction, txn)
    return {"transaction": txn, "balance_paise": ledger.balance(cid)}


@app.post("/api/transactions/{tid}/void")
def void(tid: int):
    t = ledger.transaction(tid)
    if not t:
        raise HTTPException(404, "Entry not found")
    ledger.void(tid, "removed in app")
    return {"ok": True, "balance_paise": ledger.balance(t["customer_id"])}


@app.get("/api/transactions/recent")
def recent(limit: int = 20):
    return ledger.recent(min(max(limit, 1), 100))


@app.get("/api/report/today")
def report_today():
    return ledger.today_report()


@app.get("/api/export.csv")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["entry_id", "date_time", "customer", "type", "amount_rupees", "status", "heard"])
    for c in ledger.list_customers():
        for t in reversed(ledger.transactions_for(c["id"], limit=100000)):
            w.writerow([t["id"], t["created_at"], c["label"], t["kind"], t["amount_paise"] / 100,
                        "removed" if t["voided_at"] else "active", t["transcript"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=voice_khata.csv"})


@app.post("/api/auth/request-otp")
def request_otp(body: OTPRequest):
    phone = "".join(ch for ch in body.phone if ch.isdigit())
    if len(phone) < 10:
        raise HTTPException(400, "Enter a valid mobile number")
    owner = "".join(ch for ch in (os.getenv("VK_OWNER_PHONE") or ledger.get_store().get("phone") or "") if ch.isdigit())
    if owner and phone[-10:] != owner[-10:]:
        raise HTTPException(403, "This number is not the store owner's number")
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (ledger_now() + timedelta(minutes=5)).isoformat()
    ledger.db.execute("INSERT OR REPLACE INTO otp_codes(phone,code_hash,expires_at,attempts,created_at) VALUES(?,?,?,?,?)",
                      (phone, _hash(code), expires, 0, ledger_now().isoformat()))
    ledger.db.commit()
    ok, _, error = _twilio_send(phone, f"Your Voice Khata login code is {code}. It expires in 5 minutes.")
    if not ok and os.getenv("VK_ALLOW_DEV_OTP", "true").lower() != "true":
        raise HTTPException(503, error)
    payload = {"ok": True, "message": "OTP sent" if ok else "Development OTP (configure Twilio for SMS)"}
    if not ok:
        payload["dev_otp"] = code
    return payload

@app.post("/api/auth/verify-otp")
def verify_otp(body: OTPVerify, response: Response):
    phone = "".join(ch for ch in body.phone if ch.isdigit())
    row = ledger.db.execute("SELECT * FROM otp_codes WHERE phone=?", (phone,)).fetchone()
    if not row or row["attempts"] >= 5 or row["expires_at"] < ledger_now().isoformat() or not secrets.compare_digest(row["code_hash"], _hash(body.code)):
        if row:
            ledger.db.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE phone=?", (phone,)); ledger.db.commit()
        raise HTTPException(400, "Invalid or expired OTP")
    ledger.db.execute("DELETE FROM otp_codes WHERE phone=?", (phone,))
    token = secrets.token_urlsafe(32)
    expires = (ledger_now() + timedelta(days=14)).isoformat()
    ledger.db.execute("INSERT INTO owner_sessions(token_hash,phone,expires_at,created_at) VALUES(?,?,?,?)",
                      (_hash(token), phone, expires, ledger_now().isoformat()))
    ledger.db.commit()
    response.set_cookie("vk_session", token, httponly=True, samesite="lax", secure=os.getenv("VK_COOKIE_SECURE", "false").lower()=="true", max_age=14*86400)
    return {"ok": True, "phone": phone}

@app.get("/api/auth/me")
def auth_me(request: Request):
    token = request.cookies.get("vk_session", "")
    row = ledger.db.execute("SELECT phone,expires_at FROM owner_sessions WHERE token_hash=?", (_hash(token),)).fetchone() if token else None
    return {"authenticated": bool(row and row["expires_at"] >= ledger_now().isoformat()), "phone": row["phone"] if row else ""}

@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    token = request.cookies.get("vk_session", "")
    if token:
        ledger.db.execute("DELETE FROM owner_sessions WHERE token_hash=?", (_hash(token),)); ledger.db.commit()
    response.delete_cookie("vk_session")
    return {"ok": True}

@app.get("/api/store")
def get_store():
    return ledger.get_store()

@app.put("/api/store")
def put_store(body: StoreIn):
    return ledger.save_store(body.store_name, body.owner_name, body.phone, body.address)

@app.get("/api/messages")
def messages():
    return ledger.list_sms()

@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- frontend
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")

    # Installable mobile app (PWA): the service worker must be served from the root.
    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(FRONTEND / "sw.js", media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json")
