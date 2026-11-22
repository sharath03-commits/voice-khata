# Voice Khata 2.0

AI voice assistant for kirana stores. Team QuantumCrew, PS2.

The shopkeeper says *“Hey Khata, Ramesh ka 340 udhaar”* in Kannada, Hindi, English or a mix. Voice Khata hears it with **its own speech recogniser**, understands it with **its own trained language model**, writes it in the khata, and answers in **its own voice**. No browser speech services are needed.

## What's new in 2.0

| | 1.0 | 2.0 |
|---|---|---|
| Speech to text | Browser (Google) | Own server: Whisper models fine-tuned for Kannada and Hindi |
| Understanding | Keyword rules | Own trained language model (intent classifier + CRF tagger), rules only as a money safety check |
| Voice reply | Browser voice | Own server: Meta MMS voices for Kannada, Hindi, English |
| Hey Khata | Browser recogniser, unreliable | Own voice-activity detector + own wake-word recogniser |
| App | Web page | Installable mobile app (PWA), new signboard theme |
| Spoken numbers | A few words | Every number 1–99 plus hundreds, thousands, lakhs in all three languages |
| Security | Any phone could log in | Only the owner's number can log in |

## The voice system (version 3)

Built around what works on an ordinary shop laptop:

- **One microphone controller.** Only one listener exists at a time and it is fully stopped before the next starts; Chrome silently refuses overlapping listeners, which caused missed wake words before.
- **Hey Khata** restarts itself when Chrome ends a listening session, backs off on errors, never listens to its own replies, matches the wake phrase by sound in any script (हे खाता / हे कथा / ಹೇ ಖಾತಾ / ಏ ಕತಾ / hey kata), and accepts a command in the same breath.
- **Voice replies** use the engine chosen in the app (fast / own offline / browser), with a time limit and automatic fallback, so a slow engine can never freeze the conversation. Replies are cached on disk.
- **Test my setup** (Store page) checks browser, microphone, server, language model and every voice, and applies the fastest working settings.
- Every path is tested in a real browser with a simulated Chrome recogniser that reproduces Chrome's quirks (`tests` plus the UI test scripts).

See **QUICKSTART.md** for the shopkeeper's steps.

## Run it

```
run.bat            (Windows)
./run.sh           (Mac / Linux)
```

Open http://localhost:8000. If Twilio isn't set up, the login code is shown on screen (demo mode).

At this point the trained language model already works. Voice falls back to the phone's speech until step 2 is done.

## Install the own voice assistant (one time, needs internet once)

```
cd backend
python ../scripts/setup_voice.py
```

This installs PyTorch (CPU) and the speech libraries, downloads the models (about 1–2.5 GB), and runs a self-test where our voice speaks a sentence, our recogniser hears it, and the language model understands it. For a lighter install use `--lang kn` or `--lang hi`. A laptop with 8 GB RAM is recommended.

Then restart the app and open **Store → Voice assistant → Load voice models** before demoing, so the first command is fast.

## Install it on a phone as an app

The microphone and app install need https.
1. Run `ngrok http 8000` (or `cloudflared tunnel --url http://localhost:8000`).
2. Open the https link in Chrome on the phone, log in, then **⋮ → Add to Home screen / Install app**.

## Using it

- **Tap the yellow mic** and speak. It stops by itself when you pause.
- **Hey Khata**: turn it on and the app keeps listening. Say “Hey Khata”, wait for the chime, then speak. Or say it in one breath: “Hey Khata, Lakshmi 1250 jama”.
- If it needs something (new customer, unclear amount, credit or payment?), it asks and listens for your answer.
- Corrections: “Nahi, 430”. Remove: “undo”. Reports: “aaj ka hisaab”, “ರಮೇಶ್ ಬಾಕಿ ಎಷ್ಟು”, “sabka baaki kitna”.

## How the AI works

```
Phone mic ─► voice-activity detector (in the app, 16 kHz)
          ─► /api/voice/wake     whisper-tiny  → “Hey Khata”?
          ─► /api/voice/command  Whisper (Kannada / Hindi / English model) → 3 best transcripts
          ─► language model      intent + customer + amount + quantity
          ─► validation engine   asks back when unsure, never guesses
          ─► SQLite ledger       amounts in paise, nothing ever deleted
          ─► /api/voice/tts      MMS voice speaks the reply
```

### The language model (`backend/app/nlu/`)

Trained by us on our own generated corpus. Retrain any time with `python -m app.nlu.train` (about a minute).

- **Corpus** (`corpus.py`): about 450 sentence patterns across 10 intents, written in Kannada script, Devanagari, romanised Hindi, romanised Kannada, English and code-mixed speech. They are filled with 130+ names (also transliterated into Kannada and Devanagari), amounts as digits and as spoken words in all three languages, quantities and items. Speech-style noise is added: fillers, honorifics, dropped words and spelling variants. This produces 25,000 training sentences.
- **Intent classifier**: character 1–5-grams + word 1–2-grams → logistic regression. Character n-grams work across scripts and spellings, so it understands words like *ಕೊಟ್ಟಿದ್ದಾನೆ* or *udhaara* that it never saw exactly.
- **Slot tagger**: a Conditional Random Field that labels every word as customer name, money amount, quantity or other, using the word, its prefixes and suffixes, its script, and its neighbours.
- **Test set**: 30 names never seen in training, plus 40% of sentences in patterns held out from training.

| Measure | Score |
|---|---|
| Intent accuracy, new names, known sentence styles | **99.8%** |
| Intent accuracy, new names, sentence styles never seen | **76.7%** |
| Finding names / amounts / quantities (slot F1) | **97.0%** |
| Model size | about 1.2 MB, runs instantly on a laptop |

The original rules stay on as a **money safety check**. When the model and rules disagree about credit vs payment, or the model is unsure, Voice Khata asks instead of saving.

Try it live: `POST /api/nlu/understand {"text": "ಸುರೇಶ್ ಕಡೆಯಿಂದ ಮುನ್ನೂರು ಬಂದಿದೆ"}` shows the word-by-word tags and intent probabilities.

### Speech models (open models, running on our server)

| Job | Default model | Why |
|---|---|---|
| Kannada speech-to-text | `vasista22/whisper-kannada-small` | Whisper fine-tuned on Kannada speech (IIT Madras) |
| Hindi speech-to-text | `vasista22/whisper-hindi-small` | Whisper fine-tuned on Hindi speech (IIT Madras) |
| English speech-to-text | `openai/whisper-base` | Indian English |
| Wake word | `openai/whisper-tiny` | Small and fast for short clips |
| Voice | `facebook/mms-tts-kan / -hin / -eng` | Natural Kannada, Hindi and English voices |

Voices can't read digits or English letters in Kannada, so every reply is prepared first: ₹340 becomes *ಮುನ್ನೂರ ನಲವತ್ತು ರೂಪಾಯಿ* and Ramesh becomes ರಮೇಶ್ (`numbers.py`, `translit.py`). All model names can be changed in `.env`.

## Settings (`backend/.env`, copy from `.env.example`)

`VK_OWNER_PHONE` (only this number can log in), `VK_ALLOW_DEV_OTP` (show the code on screen in demo mode), Twilio keys for customer SMS, and model overrides.

## Tests

```
cd backend && python -m pytest -q        # 60 tests
```

They cover number words in three languages, transliteration, the trained model on new phrasings, the wake word, speech preparation, the voice API (with a stand-in recogniser), the dialogue engine, and owner-only login.

## Honest notes for judges

- **We trained the language model ourselves. The speech models are open-source models we run on our own server.** Training speech recognition from scratch needs thousands of hours of recorded speech. Fine-tuning Whisper on recordings from real kirana shops is our next step.
- Kannada speech recognition is the hardest part; the fine-tuned model is much better than plain Whisper. Noise is handled by the app's noise suppression, our voice-activity detector, 3-best transcripts, and confirmation when unsure.
- Wake word works while the app is open on screen; a phone stops background listening for battery and privacy reasons.
- Real customer SMS in India needs DLT registration; a Twilio trial only sends to verified numbers.
