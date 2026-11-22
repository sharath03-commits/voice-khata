# Voice Khata: quick start (Windows)

## Every time
1. Open the `backend` folder, right-click an empty area, **Open in Terminal**, and run:
   ```
   py -3.12 -m uvicorn app.main:app --port 8000
   ```
2. Open **Google Chrome** (not Edge) at `localhost:8000`.
3. First time on a computer: **Store → Test my setup**. It checks the microphone, listening, voices and server, and picks the fastest working settings.

## Using it
- **Tap the yellow mic** (or press Space) and say one sentence, e.g. “Ramesh ka 340 udhaar”, “ರಮೇಶ್ 200 ಕೊಟ್ಟರು”.
- **Hey Khata**: tap it once (green dot). Say “Hey Khata”, hear the chime, say the entry. Or in one breath: “Hey Khata, Lakshmi 500 jama”. After each reply it goes back to waiting for “Hey Khata”.
- The **language button** (ಕ / हि / En) must match the language you speak.
- If it asks something (new customer, credit or payment?), just answer; it is already listening.
- Tap the mic while it is speaking to interrupt and speak again.
- **Busy shop**: Store → tick “keep listening for the next entry” to speak entries back to back.

## Voice settings (Store page)
| Setting | Best on an ordinary laptop | Fully offline (needs a fast computer) |
|---|---|---|
| Listening | Chrome (fast) | Own, offline (Whisper) |
| Voice replies | Fast voice | Own, offline (MMS) |

Understanding is always done by **our own trained language model**, on this computer, in milliseconds.

## First-time install (already done on this laptop)
```
py install 3.12
py -3.12 -m pip install -r requirements.txt
```
Optional offline voice models: `py -3.12 ../scripts/setup_voice.py --lang hi kn`

## Moving from an older version
Copy `backend\.env` and `backend\voice_khata.db` from the old folder into the new `backend` folder. Downloaded models are reused automatically.

## If something doesn't work
Store → **Test my setup** tells you what failed and how to fix it. Most common: using Edge instead of Chrome, the microphone blocked (click the icon left of the address → Microphone → Allow), or the wrong language button.
