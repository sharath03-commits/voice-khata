"""Replies in the shopkeeper's language.

Each message has: en, hi (romanised, shown on screen), hs (Devanagari, spoken
by Hindi TTS so it sounds natural) and kn (Kannada, shown and spoken).
Amount placeholders receive paise and are formatted per language.
"""
from __future__ import annotations

import re

M = {
    "saved_credit": {
        "en": "Added ₹{amt} credit for {name}. {bal}",
        "hi": "{name} ka ₹{amt} udhaar likha. {bal}",
        "hs": "{name} का {amt} रुपये उधार लिखा। {bal}",
        "kn": "{name} ಖಾತೆಗೆ ₹{amt} ಉದ್ರಿ ಬರೆದಿದೆ. {bal}"},
    "saved_payment": {
        "en": "Received ₹{amt} from {name}. {bal}",
        "hi": "{name} se ₹{amt} jama kiya. {bal}",
        "hs": "{name} से {amt} रुपये जमा किए। {bal}",
        "kn": "{name} ಅವರಿಂದ ₹{amt} ಜಮಾ ಆಗಿದೆ. {bal}"},
    "corrected": {
        "en": "Changed to ₹{amt} {kind} for {name}. {bal}",
        "hi": "Theek kiya: {name} ka ₹{amt} {kind}. {bal}",
        "hs": "ठीक किया: {name} का {amt} रुपये {kind}। {bal}",
        "kn": "ಸರಿಪಡಿಸಲಾಗಿದೆ: {name} ₹{amt} {kind}. {bal}"},
    "undone": {
        "en": "Removed ₹{amt} {kind} for {name}. {bal}",
        "hi": "{name} ka ₹{amt} {kind} hata diya. {bal}",
        "hs": "{name} का {amt} रुपये {kind} हटा दिया। {bal}",
        "kn": "{name} ಅವರ ₹{amt} {kind} ತೆಗೆದುಹಾಕಲಾಗಿದೆ. {bal}"},
    "balance": {"en": "{name}: {bal}", "hi": "{name}: {bal}", "hs": "{name}: {bal}", "kn": "{name}: {bal}"},
    "ask_customer": {
        "en": "Which customer?", "hi": "Kis customer ka?",
        "hs": "किस ग्राहक का?", "kn": "ಯಾವ ಗ್ರಾಹಕರು?"},
    "ask_which": {
        "en": "Which one: {opts}?", "hi": "Kaun sa: {opts}?",
        "hs": "कौन सा: {opts}?", "kn": "ಯಾರು: {opts}?"},
    "ask_amount": {
        "en": "How much for {name}?", "hi": "{name} ka kitna?",
        "hs": "{name} का कितना?", "kn": "{name} ಎಷ್ಟು?"},
    "ask_amount_pick": {
        "en": "Which amount: {opts}?", "hi": "Kitna: {opts}?",
        "hs": "कितना: {opts}?", "kn": "ಎಷ್ಟು: {opts}?"},
    "ask_type": {
        "en": "₹{amt} for {name}: credit or payment?",
        "hi": "{name} ka ₹{amt}: udhaar ya jama?",
        "hs": "{name} का {amt} रुपये: उधार या जमा?",
        "kn": "{name} ₹{amt}: ಉದ್ರಿ ಅಥವಾ ಜಮಾ?"},
    "confirm": {
        "en": "Save ₹{amt} {kind} for {name}?",
        "hi": "{name} ka ₹{amt} {kind} likhun?",
        "hs": "{name} का {amt} रुपये {kind} लिखूँ?",
        "kn": "{name} ಖಾತೆಗೆ ₹{amt} {kind} ಬರೆಯಲೇ?"},
    "confirm_new": {
        "en": "{name} is a new customer. Add and save ₹{amt} {kind}?",
        "hi": "{name} naya customer hai. Jodkar ₹{amt} {kind} likhun?",
        "hs": "{name} नया ग्राहक है। जोड़कर {amt} रुपये {kind} लिखूँ?",
        "kn": "{name} ಹೊಸ ಗ್ರಾಹಕರು. ಸೇರಿಸಿ ₹{amt} {kind} ಬರೆಯಲೇ?"},
    "confirm_fuzzy": {
        "en": "Did you mean {name}? Save ₹{amt} {kind}?",
        "hi": "{name} na? ₹{amt} {kind} likhun?",
        "hs": "{name} ना? {amt} रुपये {kind} लिखूँ?",
        "kn": "{name} ಅಲ್ವಾ? ₹{amt} {kind} ಬರೆಯಲೇ?"},
    "confirm_overpay": {
        "en": "{name} owes only ₹{due}. Save ₹{amt} payment anyway?",
        "hi": "{name} ka baaki sirf ₹{due} hai. Phir bhi ₹{amt} jama likhun?",
        "hs": "{name} का बाकी सिर्फ {due} रुपये है। फिर भी {amt} रुपये जमा लिखूँ?",
        "kn": "{name} ಬಾಕಿ ₹{due} ಮಾತ್ರ. ಆದರೂ ₹{amt} ಜಮಾ ಬರೆಯಲೇ?"},
    "confirm_duplicate": {
        "en": "Same entry was saved a moment ago. Save ₹{amt} {kind} for {name} again?",
        "hi": "Yahi entry abhi likhi thi. {name} ka ₹{amt} {kind} phir se likhun?",
        "hs": "यही एंट्री अभी लिखी थी। {name} का {amt} रुपये {kind} फिर से लिखूँ?",
        "kn": "ಇದೇ ಎಂಟ್ರಿ ಈಗಷ್ಟೇ ಬರೆದಿದೆ. {name} ₹{amt} {kind} ಮತ್ತೆ ಬರೆಯಲೇ?"},
    "cancelled": {
        "en": "Okay, nothing saved.", "hi": "Theek hai, kuch nahi likha.",
        "hs": "ठीक है, कुछ नहीं लिखा।", "kn": "ಸರಿ, ಏನೂ ಬರೆದಿಲ್ಲ."},
    "nothing_pending": {
        "en": "Nothing is waiting for a yes or no.", "hi": "Abhi haan ya na ke liye kuch nahi hai.",
        "hs": "अभी हाँ या ना के लिए कुछ नहीं है।", "kn": "ಹೌದು ಅಥವಾ ಇಲ್ಲ ಹೇಳಲು ಏನೂ ಬಾಕಿ ಇಲ್ಲ."},
    "no_recent": {
        "en": "No recent entry to change.", "hi": "Badalne ke liye koi haal ki entry nahi.",
        "hs": "बदलने के लिए कोई हाल की एंट्री नहीं।", "kn": "ಬದಲಾಯಿಸಲು ಇತ್ತೀಚಿನ ಎಂಟ್ರಿ ಇಲ್ಲ."},
    "unknown_customer": {
        "en": "No customer named {name}.", "hi": "{name} naam ka koi customer nahi.",
        "hs": "{name} नाम का कोई ग्राहक नहीं।", "kn": "{name} ಹೆಸರಿನ ಗ್ರಾಹಕರು ಇಲ್ಲ."},
    "not_understood": {
        "en": "Didn't catch that. Try: Ramesh 340 credit.",
        "hi": "Samjha nahi. Aise boliye: Ramesh ka 340 udhaar.",
        "hs": "समझा नहीं। ऐसे बोलिए: रमेश का 340 उधार।",
        "kn": "ಅರ್ಥ ಆಗಲಿಲ್ಲ. ಹೀಗೆ ಹೇಳಿ: ರಮೇಶ್ 340 ಉದ್ರಿ."},
    "report_today": {
        "en": "Today: ₹{c} credit in {nc} entries, ₹{p} received in {np}. Total outstanding ₹{t}.",
        "hi": "Aaj: ₹{c} udhaar ({nc} entry), ₹{p} jama ({np} entry). Kul baaki ₹{t}.",
        "hs": "आज: {c} रुपये उधार, {nc} एंट्री। {p} रुपये जमा, {np} एंट्री। कुल बाकी {t} रुपये।",
        "kn": "ಇವತ್ತು: ₹{c} ಉದ್ರಿ ({nc}), ₹{p} ಜಮಾ ({np}). ಒಟ್ಟು ಬಾಕಿ ₹{t}."},
    "report_all": {
        "en": "Total outstanding ₹{t} from {n} customers. Highest: {top}.",
        "hi": "Kul baaki ₹{t}, {n} customer. Sabse zyada: {top}.",
        "hs": "कुल बाकी {t} रुपये, {n} ग्राहक। सबसे ज़्यादा: {top}।",
        "kn": "ಒಟ್ಟು ಬಾಕಿ ₹{t}, {n} ಗ್ರಾಹಕರು. ಹೆಚ್ಚು: {top}."},
    "report_clear": {
        "en": "Nobody owes anything right now.", "hi": "Abhi kisi ka baaki nahi hai.",
        "hs": "अभी किसी का बाकी नहीं है।", "kn": "ಈಗ ಯಾರದೂ ಬಾಕಿ ಇಲ್ಲ."},
}

BAL = {
    "en": ("Balance ₹{b}.", "Account settled.", "Advance ₹{b}."),
    "hi": ("Baaki ₹{b}.", "Hisaab barabar.", "Advance ₹{b}."),
    "hs": ("बाकी {b} रुपये।", "हिसाब बराबर।", "एडवांस {b} रुपये।"),
    "kn": ("ಬಾಕಿ ₹{b}.", "ಲೆಕ್ಕ ಚುಕ್ತಾ.", "ಮುಂಗಡ ₹{b}."),
}
KIND = {"en": {"credit": "credit", "payment": "payment"},
        "hi": {"credit": "udhaar", "payment": "jama"},
        "hs": {"credit": "उधार", "payment": "जमा"},
        "kn": {"credit": "ಉದ್ರಿ", "payment": "ಜಮಾ"}}
OR = {"en": " or ", "hi": " ya ", "hs": " या ", "kn": " ಅಥವಾ "}
CURRENCY_WORD = {"en": "rupees", "kn": "ರೂಪಾಯಿ"}
TTS_LANG = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN"}
AMOUNT_KEYS = {"amt", "due", "c", "p", "t"}


def inr(paise: int, grouped: bool = True) -> str:
    """Indian digit grouping: 125000 paise -> '1,250'."""
    neg = paise < 0
    paise = abs(int(paise))
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    if grouped and len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    if p:
        s += f".{p:02d}"
    return ("-" if neg else "") + s


def _bal(lang: str, paise: int, grouped: bool) -> str:
    owes, settled, advance = BAL[lang]
    if paise > 0:
        return owes.format(b=inr(paise, grouped))
    if paise < 0:
        return advance.format(b=inr(-paise, grouped))
    return settled


def _fill(variant: str, key: str, kw: dict) -> str:
    spoken = variant == "hs"
    vals = {}
    for k, v in kw.items():
        if k in AMOUNT_KEYS:
            vals[k] = inr(v, grouped=not spoken)
        elif k == "bal":
            vals[k] = _bal(variant, v, grouped=not spoken)
        elif k == "kind":
            vals[k] = KIND[variant][v]
        elif k == "opts":
            vals[k] = OR[variant].join(
                ("₹" + inr(o) if variant != "hs" else inr(o, False) + " रुपये") if isinstance(o, int) else str(o)
                for o in v)
        elif k == "top":
            vals[k] = ", ".join(
                f"{n} ₹{inr(b)}" if variant != "hs" else f"{n} {inr(b, False)} रुपये" for n, b in v)
        else:
            vals[k] = v
    return M[key][variant].format(**vals)


def render(key: str, lang: str, **kw) -> dict:
    """Return {'text': shown on screen, 'speak': for TTS, 'tts_lang': BCP-47}."""
    lang = lang if lang in ("en", "hi", "kn") else "en"
    text = _fill(lang, key, kw)
    if lang == "hi":
        speak = _fill("hs", key, kw)
    else:
        word = CURRENCY_WORD[lang]
        speak = re.sub(r"₹([\d,]+(?:\.\d+)?)", lambda m: f"{m.group(1).replace(',', '')} {word}", text)
    return {"text": text, "speak": speak, "tts_lang": TTS_LANG[lang]}
