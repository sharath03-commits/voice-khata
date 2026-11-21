# Voice Khata

AI-powered voice ledger for kirana stores. Team QuantumCrew, PS2.

A shopkeeper says *"Ramesh ka 340 udhaar"* and the ledger records ₹340 credit for Ramesh, then speaks back the new balance. It understands Kannada, Hindi and English (and mixes of them), and it never guesses: if the customer, amount or credit/payment is unclear, it asks one short question before saving anything.

## Run it

You need Python 3.10+ and Google Chrome (desktop or Android).

```bash
./run.sh            # macOS / Linux
run.bat             # Windows
```

Open http://localhost:8000, pick ಕನ್ನಡ / हिंदी / English, tap the mic, and speak.

To load demo customers first (from the `backend` folder): `python ../scripts/seed_demo.py`.

### Using it on an Android phone

Chrome only allows the microphone on `https://` or `localhost`. Two easy options:

1. **USB:** connect the phone, open `chrome://inspect` on the laptop, add port forwarding `8000 → localhost:8000`, then open `http://localhost:8000` on the phone.
2. **Tunnel:** run `ngrok http 8000` (or `cloudflared tunnel --url http://localhost:8000`) and open the https link on the phone.

### Run the tests

```bash
cd backend && python -m pytest -q      # 35 tests
```

## What it does (matches the deck)

| Deck feature | How it works here |
|---|---|
| Multilingual voice recognition | Chrome's streaming speech recognition in `kn-IN`, `hi-IN` or `en-IN`, up to 5 alternative transcripts sent to the server; the parser picks the one that makes the most sense. Names match across scripts: Ramesh, रमेश and ರಮೇಶ್ are the same customer. |
| Intelligent number recognition | Digits, Devanagari and Kannada numerals, `1,250`, `2k`, words (*do sau pachas*, *dedh hazaar*, *saade teen sau*, *ಎರಡು ಸಾವಿರದ ಐನೂರು*, *two thousand five hundred*). Quantities like *2 kilo* are ignored so they are never taken as money. |
| Smart credit & payment detection | Keyword and grammar scoring: *udhaar / ಉದ್ರಿ / credit* means credit; *jama / diya / ಕೊಟ್ಟರು / paid* means payment. *Ramesh **ne** 200 diya* (Ramesh gave) is payment; *Ramesh **ko** 200 diya* (shop gave) is treated as credit but confirmed first. |
| Voice corrections | *"Nahi, 430"* fixes the entry being confirmed or the last saved one. The old entry is kept, marked corrected, for an audit trail. *"Undo"* removes the last entry. |
| Duplicate customer names | Two Anils? It asks *"Anil (doodh wala) ya Anil (school teacher)?"*; answer by voice (*"doodh wala"*, *"pehla"*) or tap. |
| Voice reports | *"Ramesh ka baaki kitna"*, *"ರಮೇಶ್ ಬಾಕಿ ಎಷ್ಟು"*, *"aaj ka hisaab"*, *"sabka baaki kitna"*. |
| Validate before record | Saves straight away only when everything is certain. Otherwise asks to confirm when: new customer, unsure credit/payment, low speech confidence, amount ≥ ₹5,000, payment larger than what's owed, or the same entry repeated within 90 seconds. |
| Spoken reply | Replies in the language spoken. Hindi replies are shown romanised (as in the deck) and spoken in Devanagari so the voice sounds natural. |

Also included: hands-free mode (listens again after each reply), typed input fallback, manual entries, per-customer history showing what was heard, CSV export, light/dark mode, works on a phone screen.

## Architecture

```
Voice input (Chrome mic)
  → Speech-to-text (Web Speech API, kn-IN / hi-IN / en-IN, 5 alternatives)
  → POST /api/utterance
      parser.py   language + numbers + intent + credit/payment + customer name
      engine.py   validate → ask back (pending draft) or record
      ledger.py   SQLite, amounts in paise, entries voided never deleted
      messages.py reply text + TTS text in kn / hi / en
  → Text-to-speech reply (speechSynthesis) + ledger refresh
```

```
voice-khata/
├── backend/
│   ├── app/
│   │   ├── main.py       FastAPI routes, serves the frontend
│   │   ├── parser.py     multilingual NLP (no external AI service needed)
│   │   ├── engine.py     dialogue + validation state machine
│   │   ├── ledger.py     SQLite storage
│   │   └── messages.py   localised replies
│   ├── tests/            35 pytest tests
│   └── requirements.txt
├── frontend/index.html   single-page voice app
├── scripts/seed_demo.py
├── run.sh / run.bat
```

The parser is rule-based and runs offline on the server, so there is no API key, no per-request cost, and every decision is explainable. It is deliberately a separate module so it can later be swapped for or backed by an Indic NLP model.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/utterance` | `{"alternatives":[{"text","confidence"}], "lang_hint"}` or `{"text": "..."}`; tap answers use `{"confirm": true}` or `{"choice": {...}}` |
| POST | `/api/undo` | Remove the last entry (last 30 min) |
| POST | `/api/pending/cancel` | Drop the entry waiting for an answer |
| GET | `/api/customers` | All customers with balances |
| POST | `/api/customers` | Add `{name, tag, phone}` |
| GET / PATCH | `/api/customers/{id}` | History / edit name, note |
| POST | `/api/customers/{id}/entries` | Manual `{kind, amount}` (rupees) |
| POST | `/api/transactions/{id}/void` | Remove an entry |
| GET | `/api/report/today` | Today's credit, payments, total outstanding |
| GET | `/api/export.csv` | Full ledger download |

Interactive docs at http://localhost:8000/docs.

### Settings (environment variables)

`VK_CONFIRM_ABOVE` (rupees, default 5000), `VK_AUTO_SAVE_CONFIDENCE` (default 0.75), `VK_MIN_STT_CONFIDENCE` (default 0.55), `VK_DB` (database path).

## Demo script for judges (about 90 seconds)

1. Hindi selected. Say **"Ramesh ka 340 udhaar."** It says *Ramesh naya customer hai…* (new customer). Say **"haan"**. Saved, *Baaki ₹340*.
2. Say **"Ramesh ne 200 diya."** Saved, *Baaki ₹140* (slide 7 of the deck, live).
3. Say **"Lakshmi ka 1750 udhaar"**, then immediately **"Nahi, 1250."** Corrected; her history shows the old entry struck out.
4. Switch to ಕನ್ನಡ. Say **"ರಮೇಶ್ ಬಾಕಿ ಎಷ್ಟು"**. Kannada reply, same Ramesh.
5. With demo data loaded, say **"Anil ka 50 udhaar"**. It asks which Anil. Say **"doodh wala."**
6. Say **"aaj ka hisaab."**

## Limits to know

- Voice input needs Chrome (Android or desktop). Safari/Firefox can use typed input.
- Chrome's Kannada and Hindi speech recognition needs internet. The ledger itself is local.
- One shop per server; no login yet. Encryption at rest and multi-store accounts are the next steps listed on the deck's scalability slide.

## New owner login and customer SMS features

- Owner login uses a mobile OTP. In local development, when Twilio is not configured, the API returns a `dev_otp` value for testing. **Do not expose development OTP mode in production.** Set `VK_ALLOW_DEV_OTP=false` in production.
- Customer SMS notifications are triggered after a successful voice or manual credit/payment transaction when that customer has a phone number.
- SMS delivery uses Twilio Programmable Messaging. Configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM` on the server. For Indian numbers, 10-digit numbers are normalized to +91. Production Indian messaging may require DLT registration, approved sender IDs/templates, and provider compliance setup.
- `VK_REQUIRE_AUTH=true` (default) protects API routes with the owner session cookie. OTP request and verification routes remain public by design.
- `VK_COOKIE_SECURE=true` should be set when serving over HTTPS. Sessions expire after 14 days.
- SMS attempts and provider errors are visible in the SMS History page. A missing phone number means no message is attempted.
- The frontend now includes Dashboard, Voice Assistant, Customers, All Ledgers, SMS History, and Store Details pages. The original voice UI and parser remain in place.
- Customer SMS is sent only when a phone number is saved **and** the `Customer agreed to SMS` opt-in is enabled in that customer's details. Obtain and retain customer permission before enabling notifications.

### Environment setup for deployment

Copy `.env.example` to `.env` and load it through your process manager or deployment platform. Never commit real Twilio credentials. For local development without Twilio, leave `VK_ALLOW_DEV_OTP=true` (the default in code) so the OTP is shown in the response; for a deployed app, set it to `false` and configure Twilio first. Serve over HTTPS and set `VK_COOKIE_SECURE=true` in production.
