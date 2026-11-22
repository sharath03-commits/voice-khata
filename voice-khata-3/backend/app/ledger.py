"""SQLite ledger. Amounts are stored as integer paise; entries are never deleted,
only voided, so every correction leaves an audit trail."""
from __future__ import annotations

import difflib
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

from .parser import phonetic_key

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    key         TEXT NOT NULL,
    tag         TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    sms_opt_in  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_customers_key ON customers(key);
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    kind          TEXT NOT NULL CHECK (kind IN ('credit', 'payment')),
    amount_paise  INTEGER NOT NULL CHECK (amount_paise > 0),
    transcript    TEXT NOT NULL DEFAULT '',
    lang          TEXT NOT NULL DEFAULT '',
    confidence    REAL,
    source        TEXT NOT NULL DEFAULT 'voice',
    created_at    TEXT NOT NULL,
    voided_at     TEXT,
    void_reason   TEXT,
    replaces_id   INTEGER REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS ix_txn_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS ix_txn_created ON transactions(created_at);
CREATE TABLE IF NOT EXISTS store_profile (
 id INTEGER PRIMARY KEY CHECK(id=1), store_name TEXT NOT NULL DEFAULT '', owner_name TEXT NOT NULL DEFAULT '',
 phone TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS otp_codes (phone TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS owner_sessions (token_hash TEXT PRIMARY KEY, phone TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sms_logs (id INTEGER PRIMARY KEY, customer_id INTEGER, phone TEXT NOT NULL, transaction_id INTEGER, message TEXT NOT NULL, status TEXT NOT NULL, provider_sid TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
"""


def now() -> datetime:
    return datetime.now().astimezone()


class Ledger:
    def __init__(self, path: str = "voice_khata.db"):
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(customers)")}
        if "sms_opt_in" not in cols:
            self.db.execute("ALTER TABLE customers ADD COLUMN sms_opt_in INTEGER NOT NULL DEFAULT 0")
            self.db.commit()

    # ------------------------------------------------------------ customers
    def add_customer(self, name: str, tag: str = "", phone: str = "", sms_opt_in: bool = False) -> dict:
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO customers(name, key, tag, phone, sms_opt_in, created_at) VALUES (?,?,?,?,?,?)",
                (name.strip(), phonetic_key(name), tag.strip(), phone.strip(), int(sms_opt_in), now().isoformat()))
            self.db.commit()
            return self.customer(cur.lastrowid)

    def update_customer(self, cid: int, name: Optional[str] = None,
                        tag: Optional[str] = None, phone: Optional[str] = None,
                        sms_opt_in: Optional[bool] = None) -> Optional[dict]:
        c = self.customer(cid)
        if not c:
            return None
        name = c["name"] if name is None else name.strip()
        with self.lock:
            self.db.execute("UPDATE customers SET name=?, key=?, tag=?, phone=?, sms_opt_in=? WHERE id=?",
                            (name, phonetic_key(name), c["tag"] if tag is None else tag.strip(),
                             c["phone"] if phone is None else phone.strip(),
                             c.get("sms_opt_in", 0) if sms_opt_in is None else int(sms_opt_in), cid))
            self.db.commit()
        return self.customer(cid)

    def customer(self, cid: int) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        c = dict(row)
        c["balance_paise"] = self.balance(cid)
        c["label"] = f"{c['name']} ({c['tag']})" if c["tag"] else c["name"]
        return c

    def find_customers(self, spoken_name: str) -> tuple[list[dict], bool]:
        """Return (matches, fuzzy). Exact phonetic match first, then prefix
        ('Ramesh' -> 'Ramesh Gowda'), then close spelling."""
        key = phonetic_key(spoken_name)
        if not key:
            return [], False
        rows = [dict(r) for r in self.db.execute("SELECT id, key FROM customers")]
        exact = [r["id"] for r in rows if r["key"] == key]
        if exact:
            return [self.customer(i) for i in exact], False
        if len(key) >= 3:
            prefix = [r["id"] for r in rows if r["key"].startswith(key)]
            if prefix:
                return [self.customer(i) for i in prefix], len(prefix) == 1
        scored = sorted(((difflib.SequenceMatcher(None, key, r["key"]).ratio(), r["id"])
                         for r in rows), reverse=True)
        close = [i for s, i in scored if s >= 0.8]
        return [self.customer(i) for i in close[:4]], True

    def list_customers(self) -> list[dict]:
        rows = self.db.execute("""
            SELECT c.*,
                   COALESCE(SUM(CASE WHEN t.voided_at IS NULL AND t.kind='credit' THEN t.amount_paise END),0)
                 - COALESCE(SUM(CASE WHEN t.voided_at IS NULL AND t.kind='payment' THEN t.amount_paise END),0)
                   AS balance_paise,
                   MAX(t.created_at) AS last_activity
            FROM customers c LEFT JOIN transactions t ON t.customer_id = c.id
            GROUP BY c.id
            ORDER BY COALESCE(MAX(t.created_at), c.created_at) DESC""").fetchall()
        out = []
        for r in rows:
            c = dict(r)
            c["label"] = f"{c['name']} ({c['tag']})" if c["tag"] else c["name"]
            out.append(c)
        return out

    # ------------------------------------------------------------ entries
    def balance(self, cid: int) -> int:
        row = self.db.execute("""
            SELECT COALESCE(SUM(CASE kind WHEN 'credit' THEN amount_paise ELSE -amount_paise END),0)
            FROM transactions WHERE customer_id=? AND voided_at IS NULL""", (cid,)).fetchone()
        return int(row[0])

    def add_transaction(self, cid: int, kind: str, amount_paise: int, transcript: str = "",
                        lang: str = "", confidence: Optional[float] = None,
                        source: str = "voice", replaces_id: Optional[int] = None) -> dict:
        if kind not in ("credit", "payment") or amount_paise <= 0:
            raise ValueError("invalid transaction")
        with self.lock:
            cur = self.db.execute(
                """INSERT INTO transactions(customer_id, kind, amount_paise, transcript, lang,
                   confidence, source, created_at, replaces_id) VALUES (?,?,?,?,?,?,?,?,?)""",
                (cid, kind, amount_paise, transcript, lang, confidence, source,
                 now().isoformat(), replaces_id))
            self.db.commit()
            return self.transaction(cur.lastrowid)

    def transaction(self, tid: int) -> Optional[dict]:
        row = self.db.execute("""SELECT t.*, c.name AS customer_name FROM transactions t
                                 JOIN customers c ON c.id=t.customer_id WHERE t.id=?""", (tid,)).fetchone()
        return dict(row) if row else None

    def void(self, tid: int, reason: str) -> None:
        with self.lock:
            self.db.execute("UPDATE transactions SET voided_at=?, void_reason=? WHERE id=? AND voided_at IS NULL",
                            (now().isoformat(), reason, tid))
            self.db.commit()

    def last_transaction(self, within_minutes: int = 30) -> Optional[dict]:
        since = (now() - timedelta(minutes=within_minutes)).isoformat()
        row = self.db.execute("""SELECT id FROM transactions WHERE voided_at IS NULL AND created_at>=?
                                 ORDER BY id DESC LIMIT 1""", (since,)).fetchone()
        return self.transaction(row[0]) if row else None

    def recent_duplicate(self, cid: int, kind: str, amount: int, seconds: int = 90) -> bool:
        since = (now() - timedelta(seconds=seconds)).isoformat()
        row = self.db.execute("""SELECT 1 FROM transactions WHERE customer_id=? AND kind=? AND amount_paise=?
                                 AND voided_at IS NULL AND created_at>=?""",
                              (cid, kind, amount, since)).fetchone()
        return row is not None

    def transactions_for(self, cid: int, limit: int = 200) -> list[dict]:
        rows = self.db.execute("""SELECT * FROM transactions WHERE customer_id=?
                                  ORDER BY id DESC LIMIT ?""", (cid, limit)).fetchall()
        return [dict(r) for r in rows]

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("""SELECT t.*, c.name AS customer_name FROM transactions t
                                  JOIN customers c ON c.id=t.customer_id ORDER BY t.id DESC LIMIT ?""",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------- store / SMS
    def get_store(self) -> dict:
        row = self.db.execute("SELECT * FROM store_profile WHERE id=1").fetchone()
        return dict(row) if row else {"id": 1, "store_name": "", "owner_name": "", "phone": "", "address": ""}

    def save_store(self, store_name: str, owner_name: str, phone: str, address: str) -> dict:
        with self.lock:
            self.db.execute("INSERT INTO store_profile(id,store_name,owner_name,phone,address,updated_at) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET store_name=excluded.store_name,owner_name=excluded.owner_name,phone=excluded.phone,address=excluded.address,updated_at=excluded.updated_at", (store_name, owner_name, phone, address, now().isoformat()))
            self.db.commit()
        return self.get_store()

    def log_sms(self, customer_id, phone, transaction_id, message, status, provider_sid="", error="") -> dict:
        with self.lock:
            cur = self.db.execute("INSERT INTO sms_logs(customer_id,phone,transaction_id,message,status,provider_sid,error,created_at) VALUES(?,?,?,?,?,?,?,?)", (customer_id, phone, transaction_id, message, status, provider_sid, error, now().isoformat()))
            self.db.commit()
            return dict(self.db.execute("SELECT * FROM sms_logs WHERE id=?", (cur.lastrowid,)).fetchone())

    def list_sms(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sms_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    # ------------------------------------------------------------ reports
    def today_report(self) -> dict:
        start = now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = self.db.execute("""SELECT kind, COUNT(*) n, COALESCE(SUM(amount_paise),0) s FROM transactions
                                  WHERE voided_at IS NULL AND created_at>=? GROUP BY kind""", (start,)).fetchall()
        rep = {"credit_paise": 0, "credit_count": 0, "payment_paise": 0, "payment_count": 0}
        for r in rows:
            rep[f"{r['kind']}_paise"] = int(r["s"])
            rep[f"{r['kind']}_count"] = int(r["n"])
        rep.update(self.outstanding())
        return rep

    def outstanding(self) -> dict:
        owing = [c for c in self.list_customers() if c["balance_paise"] > 0]
        owing.sort(key=lambda c: c["balance_paise"], reverse=True)
        return {"outstanding_paise": sum(c["balance_paise"] for c in owing),
                "owing_count": len(owing),
                "top": [{"id": c["id"], "name": c["label"], "balance_paise": c["balance_paise"]}
                        for c in owing[:3]]}
