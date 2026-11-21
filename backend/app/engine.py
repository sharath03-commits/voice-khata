"""Voice Khata dialogue engine.

SPEAK -> UNDERSTAND -> VALIDATE -> RECORD -> RESPOND

Every utterance is parsed, turned into a draft entry and validated. A draft is
saved only when the customer, amount and credit/payment are all certain;
otherwise the engine asks one short question and keeps the draft pending.
It never guesses.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from .ledger import Ledger
from .messages import render
from .parser import ParseResult, parse, phonetic_key

LARGE_AMOUNT = int(float(os.getenv("VK_CONFIRM_ABOVE", "5000")) * 100)  # paise
AUTO_SAVE_CONF = float(os.getenv("VK_AUTO_SAVE_CONFIDENCE", "0.75"))
MIN_STT_CONF = float(os.getenv("VK_MIN_STT_CONFIDENCE", "0.55"))


class Engine:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.pending: Optional[dict] = None
        self.lock = threading.RLock()
        self.last_lang = "en"

    # ------------------------------------------------------------------ API
    def handle(self, alternatives: list[dict], lang_hint: Optional[str] = None,
               choice: Optional[dict] = None, confirm: Optional[bool] = None) -> dict:
        """alternatives: [{'text': str, 'confidence': float|None}, ...] best first."""
        with self.lock:
            if confirm is not None or choice:
                return self._button(choice, confirm)
            alts = [a for a in alternatives if a.get("text", "").strip()]
            if not alts:
                return self._reply("not_understood", self.last_lang, status="error")
            r, conf = self._best(alts, lang_hint)
            self.last_lang = r.lang
            if self.pending:
                return self._continue(r, conf)
            return self._fresh(r, conf)

    def state(self) -> dict:
        return {"pending": self._public_pending()}

    def cancel(self) -> dict:
        with self.lock:
            had = self.pending is not None
            lang = self.pending["lang"] if self.pending else self.last_lang
            self.pending = None
            return self._reply("cancelled" if had else "nothing_pending", lang, status="answer")

    def undo(self, lang: Optional[str] = None) -> dict:
        with self.lock:
            lang = lang or self.last_lang
            self.pending = None
            last = self.ledger.last_transaction(within_minutes=30)
            if not last:
                return self._reply("no_recent", lang, status="answer")
            self.ledger.void(last["id"], "undo")
            bal = self.ledger.balance(last["customer_id"])
            return self._reply("undone", lang, status="undone", amt=last["amount_paise"],
                               kind=last["kind"], name=last["customer_name"], bal=bal,
                               extra={"transaction": last, "customer_id": last["customer_id"]})

    # ------------------------------------------------------------ choosing
    def _best(self, alts, lang_hint):
        scored = []
        for i, a in enumerate(alts[:5]):
            r = parse(a["text"], lang_hint)
            # prefer earlier alternatives slightly; STT already ranked them
            scored.append((r.quality - i * 0.1, i, r, a.get("confidence")))
        scored.sort(key=lambda x: (-x[0], x[1]))
        _, _, r, conf = scored[0]
        conf = conf if isinstance(conf, (int, float)) and conf > 0 else None
        return r, conf

    # ------------------------------------------------------------ no pending
    def _fresh(self, r: ParseResult, conf) -> dict:
        lang = r.lang
        if r.intent == "undo":
            return self.undo(lang)
        if r.intent == "correction":
            return self._correct_last(r)
        if r.intent in ("yes", "no"):
            return self._reply("nothing_pending", lang, status="answer")
        if r.intent == "report_today":
            rep = self.ledger.today_report()
            return self._reply("report_today", lang, status="answer",
                               c=rep["credit_paise"], nc=rep["credit_count"],
                               p=rep["payment_paise"], np=rep["payment_count"],
                               t=rep["outstanding_paise"], extra={"report": rep})
        if r.intent == "report_all":
            return self._report_all(lang)
        if r.intent in ("balance", "name_only"):
            if not r.name:
                return self._report_all(lang)
            matches, _ = self.ledger.find_customers(r.name)
            if not matches:
                return self._reply("unknown_customer", lang, status="answer", name=r.name)
            if len(matches) > 1:
                return self._reply("ask_which", lang, status="answer",
                                   opts=[f"{m['label']} ₹{m['balance_paise'] // 100}" for m in matches])
            c = matches[0]
            return self._reply("balance", lang, status="answer", name=c["label"],
                               bal=c["balance_paise"], extra={"customer_id": c["id"]})
        if r.intent == "transaction":
            self.pending = self._draft(r, conf)
            return self._advance()
        return self._reply("not_understood", lang, status="error")

    def _report_all(self, lang):
        o = self.ledger.outstanding()
        if not o["owing_count"]:
            return self._reply("report_clear", lang, status="answer")
        return self._reply("report_all", lang, status="answer", t=o["outstanding_paise"],
                           n=o["owing_count"], top=[(t["name"], t["balance_paise"]) for t in o["top"]],
                           extra={"report": o})

    def _correct_last(self, r: ParseResult) -> dict:
        new_amount = r.amount
        if not new_amount:
            return self._reply("ask_amount_pick", r.lang, status="answer", opts=r.amount_options)
        last = self.ledger.last_transaction(within_minutes=15)
        if not last:
            return self._reply("no_recent", r.lang, status="answer")
        self.ledger.void(last["id"], "corrected")
        txn = self.ledger.add_transaction(last["customer_id"], last["kind"], new_amount,
                                          transcript=r.text, lang=r.lang, source="voice-correction",
                                          replaces_id=last["id"])
        bal = self.ledger.balance(last["customer_id"])
        return self._reply("corrected", r.lang, status="saved", amt=new_amount, kind=last["kind"],
                           name=last["customer_name"], bal=bal,
                           extra={"transaction": txn, "customer_id": last["customer_id"]})

    # ------------------------------------------------------------ drafts
    def _draft(self, r: ParseResult, conf) -> dict:
        d = {"lang": r.lang, "transcript": r.text, "stt_conf": conf,
             "name": r.name, "customer": None, "candidates": [], "is_new": False, "fuzzy": False,
             "amount": r.amount, "amount_options": r.amount_options,
             "kind": r.kind, "kind_conf": r.kind_conf, "confirmed": False, "asking": None}
        if r.name:
            self._resolve_name(d, r.name)
        return d

    def _resolve_name(self, d: dict, name: str) -> None:
        matches, fuzzy = self.ledger.find_customers(name)
        d["name"] = name
        d["candidates"], d["customer"], d["is_new"], d["fuzzy"] = [], None, False, False
        if not matches:
            d["is_new"] = True
        elif len(matches) == 1:
            d["customer"], d["fuzzy"] = matches[0], fuzzy
        else:
            d["candidates"] = matches

    def _advance(self) -> dict:
        """Ask the next missing thing, ask for confirmation, or save."""
        d = self.pending
        lang = d["lang"]
        name = d["customer"]["label"] if d["customer"] else d["name"]

        if not d["name"] and not d["customer"]:
            return self._ask(d, "customer", "ask_customer")
        if d["candidates"]:
            return self._ask(d, "which", "ask_which", opts=[c["label"] for c in d["candidates"]],
                             options=[{"type": "customer", "id": c["id"], "label": c["label"]}
                                      for c in d["candidates"]])
        if not d["amount"]:
            if d["amount_options"]:
                return self._ask(d, "amount_pick", "ask_amount_pick", opts=d["amount_options"],
                                 options=[{"type": "amount", "value": a, "label": f"₹{a // 100}"}
                                          for a in d["amount_options"]])
            return self._ask(d, "amount", "ask_amount", name=name)
        if not d["kind"]:
            return self._ask(d, "type", "ask_type", amt=d["amount"], name=name,
                             options=[{"type": "kind", "value": "credit", "label": "Udhaar / credit"},
                                      {"type": "kind", "value": "payment", "label": "Jama / payment"}])

        if not d["confirmed"]:
            kw = {"amt": d["amount"], "kind": d["kind"], "name": name}
            yes_no = [{"type": "confirm", "value": True, "label": "Yes, save"},
                      {"type": "confirm", "value": False, "label": "No"}]
            if d["is_new"]:
                return self._ask(d, "confirm", "confirm_new", options=yes_no, **kw)
            cust = d["customer"]
            if self.ledger.recent_duplicate(cust["id"], d["kind"], d["amount"]):
                return self._ask(d, "confirm", "confirm_duplicate", options=yes_no, **kw)
            bal = self.ledger.balance(cust["id"])
            if d["kind"] == "payment" and d["amount"] > max(bal, 0):
                return self._ask(d, "confirm", "confirm_overpay", options=yes_no,
                                 name=name, amt=d["amount"], due=max(bal, 0))
            if d["fuzzy"]:
                return self._ask(d, "confirm", "confirm_fuzzy", options=yes_no, **kw)
            unsure = (d["kind_conf"] < AUTO_SAVE_CONF
                      or (d["stt_conf"] is not None and d["stt_conf"] < MIN_STT_CONF)
                      or d["amount"] >= LARGE_AMOUNT)
            if unsure:
                return self._ask(d, "confirm", "confirm", options=yes_no, **kw)
        return self._commit()

    def _ask(self, d, slot, key, options=None, **kw) -> dict:
        d["asking"] = slot
        return self._reply(key, d["lang"], status="ask", extra={"asking": slot, "options": options or []}, **kw)

    def _commit(self) -> dict:
        d, self.pending = self.pending, None
        cust = d["customer"]
        if d["is_new"] or not cust:
            cust = self.ledger.add_customer(d["name"])
        txn = self.ledger.add_transaction(cust["id"], d["kind"], d["amount"], transcript=d["transcript"],
                                          lang=d["lang"], confidence=d["stt_conf"])
        bal = self.ledger.balance(cust["id"])
        return self._reply(f"saved_{d['kind']}", d["lang"], status="saved", amt=d["amount"],
                           name=cust["label"], bal=bal,
                           extra={"transaction": txn, "customer_id": cust["id"], "new_customer": d["is_new"]})

    # ------------------------------------------------------------ pending
    def _continue(self, r: ParseResult, conf) -> dict:
        d = self.pending
        if r.intent not in ("yes", "no") or r.lang != "en":
            d["lang"] = r.lang

        if r.intent == "undo":
            return self.cancel()
        # A complete new command for a different customer replaces the draft.
        if r.intent == "transaction" and r.name and r.amount and r.kind:
            if not d["customer"] or phonetic_key(r.name) != d["customer"]["key"]:
                if phonetic_key(r.name) != phonetic_key(d["name"] or ""):
                    self.pending = self._draft(r, conf)
                    return self._advance()
        if r.intent in ("balance", "report_today", "report_all"):
            saved, self.pending = self.pending, None
            out = self._fresh(r, conf)
            self.pending = saved
            out["pending"] = self._public_pending()
            return out

        asking = d["asking"]
        if r.intent == "yes" or (r.yes and not r.amount and not r.name
                                 and r.kind in (None, d["kind"])):
            if asking == "confirm":
                d["confirmed"] = True
            return self._advance()
        if r.intent == "no" or (asking == "confirm" and r.no and not r.amount and not r.kind):
            return self.cancel()

        filled = False
        if asking == "which" and d["candidates"]:
            pick = self._pick_candidate(d["candidates"], r)
            if pick:
                d["customer"], d["candidates"], d["fuzzy"] = pick, [], False
                filled = True
        elif r.name and asking in ("customer", "confirm") or (r.name and not d["customer"] and not d["is_new"]):
            self._resolve_name(d, r.name)
            d["confirmed"] = False
            filled = True

        if r.amount:
            if d["amount_options"] and not d["amount"]:
                d["amount"] = min(d["amount_options"], key=lambda a: abs(a - r.amount))
                if r.amount in d["amount_options"]:
                    d["amount"] = r.amount
            else:
                d["amount"] = r.amount
            d["amount_options"] = []
            d["confirmed"] = d["confirmed"] and asking != "confirm"
            filled = True
        elif r.amount_options and asking in ("amount", "amount_pick"):
            d["amount_options"] = r.amount_options
            filled = True
        if r.kind:
            d["kind"], d["kind_conf"] = r.kind, 1.0  # explicit answer to our question
            filled = True
        if not filled:
            # Didn't understand the answer: ask the same question again.
            return self._advance()
        if asking == "confirm" and r.no and r.amount:
            # "Nahi, 430" while confirming: corrected amount, everything else was confirmed.
            d["confirmed"] = True
        return self._advance()

    def _pick_candidate(self, cands, r: ParseResult):
        if r.ordinal is not None and r.ordinal < len(cands):
            return cands[r.ordinal]
        words = [phonetic_key(t) for t in r.tokens if len(t) > 1]
        best, best_score = None, 0
        for c in cands:
            hay = phonetic_key(c["name"]) + " " + " ".join(phonetic_key(w) for w in c["tag"].split())
            score = sum(1 for w in words if w and w in hay)
            if score > best_score:
                best, best_score = c, score
        return best

    def _button(self, choice, confirm) -> dict:
        d = self.pending
        if not d:
            return self._reply("nothing_pending", self.last_lang, status="answer")
        if confirm is True:
            d["confirmed"] = True
            return self._advance()
        if confirm is False:
            return self.cancel()
        t = choice.get("type")
        if t == "customer":
            c = self.ledger.customer(int(choice["id"]))
            if c:
                d["customer"], d["candidates"], d["is_new"], d["fuzzy"] = c, [], False, False
        elif t == "amount":
            d["amount"], d["amount_options"] = int(choice["value"]), []
        elif t == "kind" and choice.get("value") in ("credit", "payment"):
            d["kind"], d["kind_conf"] = choice["value"], 1.0
        return self._advance()

    # ------------------------------------------------------------ output
    def _public_pending(self) -> Optional[dict]:
        d = self.pending
        if not d:
            return None
        return {"name": d["customer"]["label"] if d["customer"] else d["name"],
                "customer_id": d["customer"]["id"] if d["customer"] else None,
                "is_new": d["is_new"], "amount_paise": d["amount"], "kind": d["kind"],
                "asking": d["asking"], "transcript": d["transcript"]}

    def _reply(self, key, lang, status, extra=None, **kw) -> dict:
        out = {"status": status, "message_key": key, "lang": lang, **render(key, lang, **kw)}
        out.update(extra or {})
        out["pending"] = self._public_pending()
        return out
