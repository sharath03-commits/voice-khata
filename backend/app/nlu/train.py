"""Train the Voice Khata language model.

    cd backend
    python -m app.nlu.train            # ~2-4 minutes on a laptop

Writes app/nlu/model/ (intent.joblib, slots.crfsuite, metrics.json).
"""
from __future__ import annotations

import json
import time

from . import corpus, model


def main(per_intent: int = 2500, test_per_intent: int = 300):
    t0 = time.time()
    train = corpus.generate(per_intent, corpus.TRAIN_NAMES, seed=7, hold_out=False)
    test = corpus.generate(test_per_intent, corpus.TEST_NAMES, seed=99, hold_out=True)
    print(f"Generated {len(train)} training and {len(test)} test sentences "
          f"(test uses {len(corpus.TEST_NAMES)} names never seen in training and held-out phrasings).")
    model.train(train)
    m = model.evaluate(test)
    m.update({"train_sentences": len(train), "intents": corpus.INTENTS,
              "train_seconds": round(time.time() - t0, 1),
              "examples_unseen_phrasings": corpus.held_out_templates()["payment"][:3]})
    model.META_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in m.items() if k != "examples_unseen_phrasings"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
