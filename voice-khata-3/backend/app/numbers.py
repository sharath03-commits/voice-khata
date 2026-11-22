"""Spoken numbers in Kannada, Hindi and English (Indian system: hundred, thousand, lakh).

to_words(340, "kn") -> "ಮುನ್ನೂರ ನಲವತ್ತು"     (used by our own TTS: voices can't read digits)
WORD_VALUES["ಇಪ್ಪತ್ತೈದು"] -> 25                (used by the parser to read speech-to-text output)
"""
from __future__ import annotations

# ---------------------------------------------------------------- Hindi
HI_1_99 = (
    "एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह "
    "उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस "
    "तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस "
    "पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन "
    "अट्ठावन उनसठ साठ इकसठ बासठ तिरेसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर "
    "बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी अस्सी इक्यासी बयासी तिरासी "
    "चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानबे बानबे तिरानबे चौरानबे पंचानबे "
    "छियानबे सत्तानबे अट्ठानबे निन्यानबे"
).split()
assert len(HI_1_99) == 99

# Romanised Hindi 1-99 (how people type / how English ASR writes Hindi numbers)
HI_ROMAN_1_99 = (
    "ek do teen char paanch chhah saat aath nau das gyarah barah terah chaudah pandrah solah "
    "satrah atharah unnis bees ikkis bais teis chaubis pachchis chhabbis sattais atthais untis "
    "tees ikattis battis taintis chauntis paintis chhattis saintis adtis untalis chalis iktalis "
    "bayalis taintalis chavalis paintalis chhiyalis saintalis adtalis unchas pachas ikyavan baavan "
    "tirpan chauvan pachpan chhappan sattavan atthavan unsath saath iksath baasath tirsath chaunsath "
    "painsath chhiyasath sadsath adsath unhattar sattar ikhattar bahattar tihattar chauhattar "
    "pachhattar chhihattar sathattar athhattar unasi assi ikyasi bayasi tirasi chaurasi pachasi "
    "chhiyasi sattasi atthasi navasi nabbe ikyanbe baanbe tiranbe chauranbe pachanbe chhiyanbe "
    "sattanbe atthanbe ninyanbe"
).split()
assert len(HI_ROMAN_1_99) == 99

# ---------------------------------------------------------------- Kannada
KN_1_19 = ("ಒಂದು ಎರಡು ಮೂರು ನಾಲ್ಕು ಐದು ಆರು ಏಳು ಎಂಟು ಒಂಬತ್ತು ಹತ್ತು ಹನ್ನೊಂದು ಹನ್ನೆರಡು ಹದಿಮೂರು "
           "ಹದಿನಾಲ್ಕು ಹದಿನೈದು ಹದಿನಾರು ಹದಿನೇಳು ಹದಿನೆಂಟು ಹತ್ತೊಂಬತ್ತು").split()
KN_TENS = {20: "ಇಪ್ಪತ್ತು", 30: "ಮೂವತ್ತು", 40: "ನಲವತ್ತು", 50: "ಐವತ್ತು",
           60: "ಅರವತ್ತು", 70: "ಎಪ್ಪತ್ತು", 80: "ಎಂಬತ್ತು", 90: "ತೊಂಬತ್ತು"}
KN_HUNDREDS = {1: "ನೂರು", 2: "ಇನ್ನೂರು", 3: "ಮುನ್ನೂರು", 4: "ನಾನೂರು", 5: "ಐನೂರು",
               6: "ಆರುನೂರು", 7: "ಏಳುನೂರು", 8: "ಎಂಟುನೂರು", 9: "ಒಂಬೈನೂರು"}
_KN_VOWEL_SIGN = {"ಒ": "ೊ", "ಎ": "ೆ", "ಆ": "ಾ", "ಐ": "ೈ", "ಏ": "ೇ", "ಅ": ""}

KN_ROMAN_UNITS = "ondu eradu mooru naalku aidu aaru elu entu ombattu".split()
KN_ROMAN_TENS = {20: "ippattu", 30: "moovattu", 40: "nalavattu", 50: "aivattu",
                 60: "aravattu", 70: "eppattu", 80: "embattu", 90: "tombattu"}


def _kn_compound(tens_word: str, unit_word: str) -> str:
    stem = tens_word[:-1]  # ಇಪ್ಪತ್ತು -> ಇಪ್ಪತ್ತ
    if unit_word[0] in _KN_VOWEL_SIGN:
        return stem + _KN_VOWEL_SIGN[unit_word[0]] + unit_word[1:]
    return stem + unit_word


def kn_1_99(n: int) -> str:
    if n < 20:
        return KN_1_19[n - 1]
    t, u = divmod(n, 10)
    return KN_TENS[t * 10] if u == 0 else _kn_compound(KN_TENS[t * 10], KN_1_19[u - 1])


def _kn_join(word: str) -> str:
    """ನೂರು -> ನೂರ, used before a following number (ಮುನ್ನೂರ ನಲವತ್ತು)."""
    return word[:-1] if word.endswith("ು") else word


# ---------------------------------------------------------------- English
EN_1_19 = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
           "fifteen sixteen seventeen eighteen nineteen").split()
EN_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
           60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}


def _en_1_99(n: int) -> str:
    if n < 20:
        return EN_1_19[n - 1]
    t, u = divmod(n, 10)
    return EN_TENS[t * 10] + ("" if u == 0 else " " + EN_1_19[u - 1])


# ---------------------------------------------------------------- to words
def to_words(n: int, lang: str) -> str:
    """Whole rupees to words (Indian grouping). 0 -> zero word."""
    n = int(n)
    if n == 0:
        return {"hi": "शून्य", "kn": "ಸೊನ್ನೆ"}.get(lang, "zero")
    if lang == "hi":
        return _hi(n)
    if lang == "kn":
        return _kn(n)
    return _en(n)


def _split(n: int):
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1000)
    hundred, rest = divmod(n, 100)
    return crore, lakh, thousand, hundred, rest


def _hi(n: int) -> str:
    crore, lakh, thousand, hundred, rest = _split(n)
    out = []
    if crore:
        out += [_hi(crore), "करोड़"]
    if lakh:
        out += [HI_1_99[lakh - 1], "लाख"]
    if thousand:
        out += [HI_1_99[thousand - 1], "हज़ार"]
    if hundred:
        out += [HI_1_99[hundred - 1], "सौ"]
    if rest:
        out.append(HI_1_99[rest - 1])
    return " ".join(out)


def _en(n: int) -> str:
    crore, lakh, thousand, hundred, rest = _split(n)
    out = []
    if crore:
        out += [_en(crore), "crore"]
    if lakh:
        out += [_en_1_99(lakh), "lakh"]
    if thousand:
        out += [_en_1_99(thousand), "thousand"]
    if hundred:
        out += [EN_1_19[hundred - 1], "hundred"]
    if rest:
        out.append(_en_1_99(rest))
    return " ".join(out)


def _kn(n: int) -> str:
    crore, lakh, thousand, hundred, rest = _split(n)
    parts = []  # (word, is_scale)
    if crore:
        parts.append(_kn(crore) + " ಕೋಟಿ")
    if lakh:
        parts.append((kn_1_99(lakh) + " " if lakh > 1 else "ಒಂದು ") + "ಲಕ್ಷ")
    if thousand:
        parts.append(("" if thousand == 1 else kn_1_99(thousand) + " ") + "ಸಾವಿರ")
    if hundred:
        parts.append(KN_HUNDREDS[hundred])
    if rest:
        parts.append(kn_1_99(rest))
    # every part except the last takes its joining form
    joined = []
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        if not last:
            if p.endswith("ಸಾವಿರ") or p.endswith("ಲಕ್ಷ") or p.endswith("ಕೋಟಿ"):
                p = p + "ದ"           # ಸಾವಿರದ, ಲಕ್ಷದ, ಕೋಟಿದ
            else:
                p = _kn_join(p)        # ಮುನ್ನೂರ
        joined.append(p)
    return " ".join(joined)


# ---------------------------------------------------------------- reverse lexicon
def _build_word_values() -> dict:
    """Every single-word number form we can generate -> its value (used by the parser)."""
    v: dict[str, float] = {}
    for i in range(1, 100):
        v[HI_1_99[i - 1]] = i
        v[HI_ROMAN_1_99[i - 1]] = i
        v[kn_1_99(i)] = i
        if i < 20:
            v[EN_1_19[i - 1]] = i
    for t, w in KN_TENS.items():
        v[w] = t
        v[_kn_join(w)] = t
    for t, w in KN_ROMAN_TENS.items():
        v[w] = t
    for i, w in enumerate(KN_ROMAN_UNITS, 1):
        v[w] = i
    for h, w in KN_HUNDREDS.items():
        v[w] = h * 100
        v[_kn_join(w)] = h * 100
    for t, w in EN_TENS.items():
        v[w] = t
    v["पांच"] = 5; v["छः"] = 6; v["छे"] = 6; v["तैंतीस"] = 33
    # "do" and "दो" are also the verb "give", so they stay weak in the parser
    v.pop("do", None); v.pop("दो", None)
    return v


WORD_VALUES = _build_word_values()
