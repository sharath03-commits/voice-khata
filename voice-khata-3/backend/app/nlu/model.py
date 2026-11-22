"""Voice Khata language model (our own, trained on our own corpus).

Two parts, both trained by `python -m app.nlu.train`:

1. Intent classifier: character n-grams (1-5) + word n-grams -> logistic regression.
   Character n-grams work across Kannada, Devanagari and Latin script and across
   spelling variants, so the model understands words it never saw exactly
   (ಕೊಟ್ಟಿದ್ದಾನೆ, udhaara, ...), not just a keyword list.

2. Slot tagger: a Conditional Random Field over the words of the sentence.
   It labels each word as customer NAME, money AMT, quantity QTY or other, using
   the word itself, its prefixes/suffixes, its script, its neighbours and the
   tags around it. That is how it finds names it has never heard before.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

MODEL_DIR = Path(__file__).resolve().parent / "model"
INTENT_FILE = MODEL_DIR / "intent.joblib"
CRF_FILE = MODEL_DIR / "slots.crfsuite"
META_FILE = MODEL_DIR / "metrics.json"

_lock = threading.Lock()
_loaded = {"intent": None, "crf": None, "tried": False}


# ------------------------------------------------------------------ features
def _script(t: str) -> str:
    if re.search(r"[\u0C80-\u0CFF]", t):
        return "kn"
    if re.search(r"[\u0900-\u097F]", t):
        return "dev"
    if re.fullmatch(r"[\d.]+", t):
        return "num"
    if t == "₹":
        return "cur"
    return "lat"


def _lex(t: str) -> dict:
    from ..parser import CURRENCY, MULTIPLIERS, MODIFIERS, QUANTITY, UNITS, WEAK_UNITS, _known
    return {"num_word": t in UNITS or t in WEAK_UNITS, "mult": t in MULTIPLIERS, "mod": t in MODIFIERS,
            "cur": t in CURRENCY, "qty": t in QUANTITY, "known": t in _known(),
            "digit": bool(re.fullmatch(r"[\d.]+", t))}


def token_features(toks: list[str], i: int) -> dict:
    t = toks[i]
    lx = _lex(t)
    f = {"bias": 1.0, "w": t, "p2": t[:2], "p3": t[:3], "s2": t[-2:], "s3": t[-3:], "s4": t[-4:],
         "script": _script(t), "len": str(min(len(t), 8)), "first": i == 0, "last": i == len(toks) - 1}
    f.update({k: v for k, v in lx.items()})
    for d in (-2, -1, 1, 2):
        j = i + d
        if 0 <= j < len(toks):
            u = toks[j]
            lu = _lex(u)
            f[f"{d}:w"] = u
            f[f"{d}:s3"] = u[-3:]
            f[f"{d}:script"] = _script(u)
            f[f"{d}:numlike"] = lu["digit"] or lu["num_word"] or lu["mult"]
            f[f"{d}:known"] = lu["known"]
            f[f"{d}:qty"] = lu["qty"]
        else:
            f[f"{d}:edge"] = True
    return f


def sent_features(toks):
    return [token_features(toks, i) for i in range(len(toks))]


def intent_text(toks: list[str]) -> str:
    # amounts don't change the intent; normalising digits helps generalise
    return " ".join("0" if re.fullmatch(r"[\d.]+", t) else t for t in toks)


# ------------------------------------------------------------------ training
def build_intent_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    feats = FeatureUnion([
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 5), min_df=2,
                                  max_features=80000, sublinear_tf=True)),
        ("words", TfidfVectorizer(analyzer="word", token_pattern=r"\S+", ngram_range=(1, 2),
                                  min_df=2, sublinear_tf=True)),
    ])
    return Pipeline([("feats", feats), ("clf", LogisticRegression(C=8.0, max_iter=2000))])


def train(train_data, log=print):
    import joblib
    import sklearn_crfsuite
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    log(f"Training intent classifier on {len(train_data)} sentences...")
    pipe = build_intent_pipeline()
    pipe.fit([intent_text(d["tokens"]) for d in train_data], [d["intent"] for d in train_data])
    joblib.dump(pipe, INTENT_FILE, compress=3)

    log("Training slot tagger (CRF)...")
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=0.05, c2=0.05, max_iterations=150,
                               all_possible_transitions=True, model_filename=str(CRF_FILE))
    crf.fit([sent_features(d["tokens"]) for d in train_data], [d["tags"] for d in train_data])
    with _lock:
        _loaded.update(intent=pipe, crf=crf, tried=True)
    return pipe, crf


def evaluate(test_data) -> dict:
    from sklearn.metrics import accuracy_score
    from sklearn_crfsuite import metrics as crf_metrics
    pipe, crf = _get()
    y_true = [d["intent"] for d in test_data]
    y_pred = list(pipe.predict([intent_text(d["tokens"]) for d in test_data]))
    tags_pred = crf.predict([sent_features(d["tokens"]) for d in test_data])
    labels = [l for l in crf.classes_ if l != "O"]

    def spans(tags, toks):
        out, cur = set(), None
        for i, (g, t) in enumerate(zip(tags, toks)):
            if g.startswith("B-"):
                if cur: out.add(cur)
                cur = (g[2:], i, i)
            elif g.startswith("I-") and cur and cur[0] == g[2:]:
                cur = (cur[0], cur[1], i)
            else:
                if cur: out.add(cur)
                cur = None
        if cur: out.add(cur)
        return out

    exact = sum(spans(p, d["tokens"]) == spans(d["tags"], d["tokens"]) for p, d in zip(tags_pred, test_data))
    per_style = {}
    for d, p in zip(test_data, y_pred):
        s = per_style.setdefault(d["style"], [0, 0]); s[1] += 1; s[0] += int(p == d["intent"])
    seen = [(a, b) for a, b, d in zip(y_true, y_pred, test_data) if not d.get("unseen_phrasing")]
    unseen = [(a, b) for a, b, d in zip(y_true, y_pred, test_data) if d.get("unseen_phrasing")]
    acc = lambda pairs: round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None
    return {
        "intent_accuracy": round(accuracy_score(y_true, y_pred), 4),
        "intent_accuracy_new_names_known_phrasing": acc(seen),
        "intent_accuracy_new_names_new_phrasing": acc(unseen),
        "slot_f1": round(crf_metrics.flat_f1_score([d["tags"] for d in test_data], tags_pred,
                                                   average="weighted", labels=labels), 4),
        "sentences_fully_correct_slots": round(exact / len(test_data), 4),
        "intent_accuracy_by_language_style": {k: round(a / b, 4) for k, (a, b) in sorted(per_style.items())},
        "test_sentences": len(test_data),
    }


# ------------------------------------------------------------------ inference
def _get():
    with _lock:
        if _loaded["intent"] is None and not _loaded["tried"]:
            _loaded["tried"] = True
            try:
                import joblib
                import sklearn_crfsuite
                _loaded["intent"] = joblib.load(INTENT_FILE)
                _loaded["crf"] = sklearn_crfsuite.CRF(model_filename=str(CRF_FILE))
            except Exception:
                _loaded["intent"] = _loaded["crf"] = None
        return _loaded["intent"], _loaded["crf"]


def available() -> bool:
    pipe, crf = _get()
    return pipe is not None and crf is not None


def predict(tokens: list[str]) -> Optional[dict]:
    """tokens from parser.tokenize -> {intent, confidence, probs, tags} or None if no model."""
    if not tokens:
        return None
    pipe, crf = _get()
    if pipe is None or crf is None:
        return None
    probs = pipe.predict_proba([intent_text(tokens)])[0]
    classes = list(pipe.classes_)
    best = int(probs.argmax())
    tags = crf.predict_single(sent_features(tokens))
    return {"intent": classes[best], "confidence": float(probs[best]),
            "probs": {c: round(float(p), 4) for c, p in zip(classes, probs)}, "tags": tags}


def metrics() -> dict:
    try:
        return json.loads(META_FILE.read_text())
    except Exception:
        return {}
