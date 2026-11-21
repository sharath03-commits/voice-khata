"""
Voice Khata - multilingual utterance parser.

Turns one shop sentence (Kannada, Hindi, English, or a mix; Latin, Devanagari
or Kannada script) into a structured ParseResult:

    "Ramesh ka 340 udhaar"      -> transaction, credit, Ramesh, Rs 340
    "ರಮೇಶ್ 200 ಕೊಟ್ಟರು"          -> transaction, payment, ರಮೇಶ್, Rs 200
    "रमेश का कितना बाकी है"       -> balance query, रमेश
    "Nahi, 430"                 -> correction, Rs 430

Design rule: the parser never invents data. Anything missing or ambiguous is
reported as missing/ambiguous so the dialogue engine can ask back.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Script helpers
# --------------------------------------------------------------------------
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_DIGITS = str.maketrans("०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯", "01234567890123456789")

_V = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri",
      "ए": "e", "ऎ": "e", "ऐ": "ai", "ओ": "o", "ऒ": "o", "औ": "au"}
_M = {"ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri", "े": "e",
      "ॆ": "e", "ै": "ai", "ो": "o", "ॊ": "o", "ौ": "au"}
_C = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh",
      "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
      "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p",
      "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
      "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ऱ": "r",
      "ऴ": "l"}
_VIRAMA, _NUKTA = "्", "़"


def _kannada_to_devanagari(s: str) -> str:
    # The Kannada and Devanagari Unicode blocks share the ISCII layout,
    # so a fixed offset maps one onto the other.
    return "".join(chr(ord(c) - 0x380) if 0x0C80 <= ord(c) <= 0x0CFF else c for c in s)


def to_latin(s: str) -> str:
    """Rough romanisation of Devanagari/Kannada (good enough for name matching)."""
    s = _kannada_to_devanagari(s.translate(_ZERO_WIDTH)).replace(_NUKTA, "")
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c in _C:
            out.append(_C[c])
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt in _M:
                out.append(_M[nxt]); i += 2; continue
            if nxt == _VIRAMA:
                i += 2; continue
            out.append("a"); i += 1; continue
        if c in _V:
            out.append(_V[c])
        elif c in "ंँ":
            out.append("n")
        elif c == "ः":
            out.append("h")
        elif c in _M:
            out.append(_M[c])
        else:
            out.append(c)
        i += 1
    return "".join(out)


def phonetic_key(name: str) -> str:
    """Script-independent key: 'Ramesh', 'रमेश', 'ರಮೇಶ್' -> 'rames'."""
    s = re.sub(r"[^a-z]", "", to_latin(name.lower()))
    for a, b in (("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("f", "p"),
                 ("ee", "i"), ("oo", "u")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    s = re.sub(r"([kgcjtdpbsrl])h", r"\1", s)
    s = re.sub(r"(.)\1+", r"\1", s)
    if len(s) > 3:
        s = re.sub(r"[au]+$", "", s)
    return s


def detect_script_lang(text: str) -> Optional[str]:
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    return None


# --------------------------------------------------------------------------
# Lexicons
# --------------------------------------------------------------------------
UNITS = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    # Hindi (romanised)
    "ek": 1, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "chhah": 6, "cheh": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "gyarah": 11, "gyaarah": 11, "barah": 12, "baarah": 12, "terah": 13,
    "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17, "atharah": 18,
    "athaarah": 18, "unnis": 19, "unnees": 19, "bees": 20, "pachees": 25,
    "pachchis": 25, "pachis": 25, "tees": 30, "chalis": 40, "chaalis": 40,
    "chaalees": 40, "pachas": 50, "pachaas": 50, "sattar": 70, "assi": 80,
    "nabbe": 90,
    # Kannada (romanised)
    "ondu": 1, "eradu": 2, "mooru": 3, "muru": 3, "nalku": 4, "naalku": 4,
    "aidu": 5, "aaru": 6, "elu": 7, "yelu": 7, "entu": 8, "ombattu": 9,
    "hattu": 10, "ippattu": 20, "muvattu": 30, "moovattu": 30, "nalavattu": 40,
    "aivattu": 50, "aravattu": 60, "eppattu": 70, "embattu": 80, "tombattu": 90,
    "innooru": 200, "innuru": 200, "munnooru": 300, "munnuru": 300,
    "nannooru": 400, "naanooru": 400, "ainooru": 500, "ainuru": 500,
    "aarnooru": 600, "elnooru": 700, "entnooru": 800, "ombainooru": 900,
    # Devanagari
    "एक": 1, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13,
    "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18,
    "उन्नीस": 19, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50,
    "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
    # Kannada script
    "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6,
    "ಏಳು": 7, "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಇಪ್ಪತ್ತು": 20,
    "ಮೂವತ್ತು": 30, "ನಲವತ್ತು": 40, "ಐವತ್ತು": 50, "ಅರವತ್ತು": 60,
    "ಎಪ್ಪತ್ತು": 70, "ಎಂಬತ್ತು": 80, "ತೊಂಬತ್ತು": 90, "ಇನ್ನೂರು": 200,
    "ಮುನ್ನೂರು": 300, "ನಾನೂರು": 400, "ನಾನ್ನೂರು": 400, "ಐನೂರು": 500,
    "ಆರುನೂರು": 600, "ಏಳುನೂರು": 700, "ಎಂಟುನೂರು": 800, "ಒಂಬೈನೂರು": 900,
    # fractional numbers
    "dedh": 1.5, "derh": 1.5, "डेढ़": 1.5, "डेढ": 1.5,
    "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5, "ढाई": 2.5,
}
# Words that are numbers only when next to another number ("do sau" = 200,
# but "do" alone is usually the verb "give").
WEAK_UNITS = {"do": 2, "दो": 2}
MULTIPLIERS = {
    "hundred": 100, "sau": 100, "nooru": 100, "nuru": 100, "सौ": 100,
    "ನೂರು": 100, "ನೂರ": 100,
    "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000,
    "hajaar": 1000, "saavira": 1000, "savira": 1000, "saavirada": 1000,
    "हज़ार": 1000, "हजार": 1000, "ಸಾವಿರ": 1000, "ಸಾವಿರದ": 1000,
    "lakh": 100000, "lakhs": 100000, "lac": 100000, "laksha": 100000,
    "लाख": 100000, "ಲಕ್ಷ": 100000,
}
MODIFIERS = {"saade": 0.5, "sade": 0.5, "साढ़े": 0.5, "साढे": 0.5,
             "sava": 0.25, "savaa": 0.25, "सवा": 0.25,
             "paune": -0.25, "pone": -0.25, "पौने": -0.25}

CURRENCY = {"₹", "rs", "inr", "rupees", "rupee", "rupaye", "rupaiye", "rupay",
            "rupaya", "rupaayi", "rupayi", "rupai", "ru", "रुपये", "रुपए", "रुपया",
            "रु", "ರೂಪಾಯಿ", "ರೂ", "ರುಪಾಯಿ"}
QUANTITY = {"kg", "kgs", "kilo", "kilos", "gram", "grams", "gm", "gms", "litre",
            "liter", "litres", "liters", "ltr", "packet", "packets", "pack",
            "dozen", "darjan", "piece", "pieces", "pc", "pcs", "bottle", "bottles",
            "ಕೆಜಿ", "ಕಿಲೋ", "ಲೀಟರ್", "ಪ್ಯಾಕೆಟ್", "किलो", "लीटर", "पैकेट", "दर्जन"}

CREDIT_STRONG = {"udhaar", "udhar", "udhaari", "udhari", "udaar", "udhara",
                 "credit", "khata", "khate", "khaate", "likh", "likho", "likhdo",
                 "likhna", "owes", "owe", "due", "saala", "sala", "udri", "udhri",
                 "उधार", "उधारी", "लिखो", "लिख", "खाते", "खाता",
                 "ಸಾಲ", "ಉದ್ರಿ", "ಖಾತೆ", "ಖಾತೆಗೆ"}
CREDIT_WEAK = {"baaki", "baki", "बाकी", "ಬಾಕಿ", "pending"}
PAYMENT_STRONG = {"jama", "paid", "pay", "pays", "payment", "received", "receive",
                  "wapas", "vapas", "waapas", "vaapas", "returned", "chukaya",
                  "chukta", "settled", "kattidru", "kattidaru", "kattiddare",
                  "kattidare", "kattiddaare",
                  "जमा", "वापस", "चुकाया", "चुका", "ಜಮಾ", "ಪಾವತಿ", "ವಾಪಸ್"}
PAYMENT_PREFIX = ("ಕಟ್ಟಿದ", "ಕಟ್ಟಿದ್")
GIVE = {"diya", "diye", "dia", "de", "gave", "given", "kotta", "kottru",
        "kottaru", "kottidare", "kottiddare", "kottidru", "kottiddaare",
        "दिया", "दिए", "दिये"}
GIVE_PREFIX = ("ಕೊಟ್ಟ", "kott")
TAKE = {"liya", "liye", "lia", "took", "taken", "bought", "buys", "purchased",
        "लिया", "लिए", "लिये"}
TAKE_PREFIX = ("ತಗೊಂಡ", "ತೆಗೆದುಕೊಂಡ", "tagond", "tegedukond")
DATIVE = {"ko", "को", "to"}
SOURCE = {"se", "से", "from"}

QUERY = {"outstanding", "kitna", "kitne", "kitni", "how", "much", "balance", "total", "hisaab",
         "hisab", "eshtu", "estu", "yeshtu", "batao", "bataiye", "bolo", "helu",
         "heli", "report", "summary", "कितना", "कितने", "कितनी", "हिसाब", "बताओ",
         "ಎಷ್ಟು", "ಲೆಕ್ಕ", "ಹೇಳಿ", "ಹೇಳು", "lekka"}
TODAY = {"aaj", "today", "todays", "indu", "ivattu", "aj", "आज", "ಇಂದು", "ಇವತ್ತು"}
ALL = {"sab", "sabka", "sabhi", "all", "everyone", "everybody", "ellaru",
       "ellara", "सब", "सबका", "सभी", "ಎಲ್ಲ", "ಎಲ್ಲರ", "ಎಲ್ಲಾ", "ಎಲ್ಲರೂ"}
YES = {"haan", "ha", "han", "haa", "yes", "yeah", "yep", "ok", "okay", "sahi",
       "theek", "thik", "haudu", "howdu", "hu", "hoo", "sari", "correct", "right",
       "confirm", "save", "हाँ", "हां", "हा", "ठीक", "सही", "ಹೌದು", "ಸರಿ", "ಹೂಂ", "ಹೂ"}
NO = {"nahi", "nahin", "nai", "na", "no", "nope", "illa", "alla", "galat",
      "wrong", "नहीं", "नही", "ना", "गलत", "ಇಲ್ಲ", "ಅಲ್ಲ", "ಬೇಡ", "beda"}
UNDO = {"undo", "cancel", "hatao", "hata", "hatado", "delete", "remove", "radd",
        "mitao", "हटाओ", "हटा", "रद्द", "ರದ್ದು", "ತೆಗೆದುಹಾಕಿ"}
CHANGE = {"change", "correct", "badlo", "badal", "बदलो", "ಬದಲಾಯಿಸಿ", "ಬದಲಿಸಿ"}
ORDINAL = {"first": 0, "pehla": 0, "pahla": 0, "modala": 0, "modalane": 0,
           "पहला": 0, "ಮೊದಲ": 0, "ಮೊದಲನೇ": 0,
           "second": 1, "doosra": 1, "dusra": 1, "eradane": 1, "दूसरा": 1, "ಎರಡನೇ": 1,
           "third": 2, "teesra": 2, "tisra": 2, "muraneya": 2, "तीसरा": 2, "ಮೂರನೇ": 2}

STOP = {
    # English
    "the", "a", "an", "has", "have", "had", "is", "was", "of", "for", "on", "in",
    "me", "my", "his", "her", "their", "only", "and", "please", "add", "put",
    "mark", "entry", "now", "he", "she", "they", "just", "account", "it", "as",
    "with", "by", "i", "we", "you", "sir", "madam", "uncle", "aunty", "anna",
    "akka", "bhai", "ji", "saab", "sahab", "didi", "amma", "appa", "garu",
    "what", "is", "does", "today", "yesterday", "credit", "money", "amount",
    # Hindi (romanised)
    "ka", "ki", "ke", "ne", "hai", "he", "hain", "tha", "thi", "the", "aur",
    "bhi", "mein", "me", "main", "par", "pe", "wala", "wale", "wali", "mera",
    "mere", "unka", "uska", "abhi", "kal", "ab", "toh", "kar", "karo", "kardo",
    "kariye", "dena", "dedo", "dijiye", "rupaye", "paise", "saamaan", "saman",
    "samaan", "maal", "ka", "naam", "isko", "usko", "unko",
    # Kannada (romanised)
    "avru", "avaru", "avara", "avra", "avrige", "avarige", "inda", "ninda",
    "hakri", "haaki", "haku", "haaku", "bari", "bariri", "bareyiri", "barkoli",
    "maadi", "madi", "kodi", "swalpa", "nanna", "avana", "avala", "ide", "ittu",
    "saamanu", "samanu",
    # Devanagari
    "का", "की", "के", "ने", "है", "हैं", "था", "थी", "और", "भी", "में", "पर",
    "जी", "भाई", "अभी", "कर", "करो", "दे", "दो", "सामान", "माल", "नाम",
    # Kannada script
    "ಅವರು", "ಅವರ", "ಅವರಿಗೆ", "ಅವರಿಂದ", "ಹಾಕಿ", "ಹಾಕು", "ಬರೆಯಿರಿ", "ಬರಿ",
    "ಬರೀರಿ", "ಮಾಡಿ", "ಇದೆ", "ಕೊಡಿ", "ಸಾಮಾನು", "ಅಣ್ಣ", "ಅಕ್ಕ", "ಸರ್",
}
PRODUCTS = {
    "sugar", "chini", "cheeni", "rice", "chawal", "akki", "doodh", "milk",
    "haalu", "halu", "oil", "tel", "enne", "dal", "daal", "bele", "atta",
    "aata", "soap", "sabun", "biscuit", "biscuits", "bread", "egg", "eggs",
    "ande", "motte", "tea", "chai", "coffee", "salt", "namak", "uppu", "ghee",
    "tuppa", "flour", "maida", "rava", "sooji", "curd", "dahi", "mosaru",
    "चीनी", "चावल", "दूध", "तेल", "दाल", "आटा", "साबुन", "अंडे", "चाय", "नमक",
    "ಸಕ್ಕರೆ", "ಅಕ್ಕಿ", "ಹಾಲು", "ಎಣ್ಣೆ", "ಬೇಳೆ", "ಹಿಟ್ಟು", "ಸೋಪು", "ಮೊಟ್ಟೆ",
    "ಟೀ", "ಕಾಫಿ", "ಉಪ್ಪು", "ತುಪ್ಪ", "ಮೊಸರು",
}

HINDI_HINTS = {"ka", "ki", "ke", "ne", "ko", "se", "udhaar", "udhar", "diya",
               "diye", "kitna", "haan", "nahi", "nahin", "jama", "baaki", "aaj",
               "rupaye", "liya", "likho", "likh", "hisaab", "sau", "hazaar",
               "dedh", "dhai", "hai", "wapas", "batao"}
KANNADA_HINTS = {"kotta", "kottru", "kottaru", "eshtu", "saala", "udri", "haudu",
                 "illa", "avru", "avaru", "indu", "ivattu", "nooru", "saavira",
                 "ondu", "eradu", "kattidru", "lekka", "helu", "sari", "beda"}

_KN_SUFFIXES = (("ಅವರಿಗೆ", "dat"), ("ಅವರಿಂದ", "src"), ("ನಿಗೆ", "dat"),
                ("ನಿಂದ", "src"), ("ರಿಂದ", "src"), ("ಗೆ", "dat"), ("ಇಂದ", "src"))
_LATIN_SUFFIXES = (("avarige", "dat"), ("avrige", "dat"), ("avarinda", "src"),
                   ("avrinda", "src"), ("nige", "dat"), ("ge", "dat"))

_TOKEN_RE = re.compile(r"₹|[a-z0-9]+(?:\.[0-9]+)?|[\u0900-\u0963\u0966-\u097F]+|[\u0C80-\u0CFF]+")


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------
@dataclass
class ParseResult:
    text: str
    lang: str
    intent: str = "unknown"  # transaction | balance | report_today | report_all |
                             # correction | undo | yes | no | unknown
    kind: Optional[str] = None          # credit | payment
    kind_conf: float = 0.0
    amount: Optional[int] = None        # paise
    amount_options: list = field(default_factory=list)  # paise, when ambiguous
    name: Optional[str] = None
    ordinal: Optional[int] = None
    yes: bool = False
    no: bool = False
    tokens: list = field(default_factory=list)

    @property
    def quality(self) -> float:
        q = 0.0
        if self.intent != "unknown":
            q += 2
        if self.amount:
            q += 2
        if self.kind:
            q += 1 + self.kind_conf
        if self.name:
            q += 1
        if self.amount_options:
            q -= 1
        return q


# --------------------------------------------------------------------------
# Normalisation + tokenising
# --------------------------------------------------------------------------
def normalise(text: str) -> str:
    s = text.translate(_ZERO_WIDTH).translate(_DIGITS).lower()
    s = re.sub(r"(?<=\d),(?=\d)", "", s)                      # 1,250 -> 1250
    s = re.sub(r"/-", " ", s)                                 # 340/- -> 340
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s?k\b",
               lambda m: str(int(float(m.group(1)) * 1000)), s)  # 2k -> 2000
    s = re.sub(r"(\d)([^\d\s.,])", r"\1 \2", s)               # 340rs -> 340 rs
    s = re.sub(r"([^\d\s.,₹])(\d)", r"\1 \2", s)              # rs340 -> rs 340
    s = s.replace("₹", " ₹ ")
    return s


def tokenize(text: str) -> list[str]:
    return [t.rstrip(".") if not re.match(r"^\d+\.\d+$", t) else t
            for t in _TOKEN_RE.findall(normalise(text))]


def _strip_suffix(tok: str) -> tuple[str, Optional[str]]:
    if re.search(r"[\u0C80-\u0CFF]", tok):
        for suf, kind in _KN_SUFFIXES:
            if tok.endswith(suf) and len(tok) > len(suf) + 1:
                return tok[: -len(suf)], kind
        return tok, None
    if re.fullmatch(r"[a-z]+", tok) and len(tok) >= 5 and tok not in _known():
        for suf, kind in _LATIN_SUFFIXES:
            if tok.endswith(suf) and len(tok) - len(suf) >= 3:
                if suf == "ge" and tok[-3] not in "hstdkmbpvl":
                    continue  # keep names like "George"
                return tok[: -len(suf)], kind
    return tok, None


_KNOWN_CACHE: set = set()


def _known() -> set:
    """Every word the lexicons know - none of these can be a customer name."""
    if not _KNOWN_CACHE:
        _KNOWN_CACHE.update(
            STOP | PRODUCTS | CURRENCY | QUANTITY | CREDIT_STRONG | CREDIT_WEAK |
            PAYMENT_STRONG | GIVE | TAKE | DATIVE | SOURCE | QUERY | TODAY | ALL |
            YES | NO | UNDO | CHANGE | set(ORDINAL) | set(MULTIPLIERS) |
            set(MODIFIERS) | set(WEAK_UNITS) | set(UNITS))
    return _KNOWN_CACHE


def _has_prefix(tok: str, prefixes) -> bool:
    return any(tok.startswith(p) for p in prefixes)


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def _num(tok: str):
    if re.fullmatch(r"\d+(?:\.\d+)?", tok):
        return ("d", float(tok))
    if tok in UNITS:
        return ("u", float(UNITS[tok]))
    if tok in WEAK_UNITS:
        return ("w", float(WEAK_UNITS[tok]))
    if tok in MULTIPLIERS:
        return ("m", float(MULTIPLIERS[tok]))
    if tok in MODIFIERS:
        return ("f", MODIFIERS[tok])
    return None


def _spans(tokens: list[str]):
    """Group tokens into number spans: list of (start, end_exclusive, [(kind, v)])."""
    spans, cur, start = [], [], None
    for i, t in enumerate(tokens):
        n = _num(t)
        if n is None:
            if cur:
                spans.append((start, i, cur)); cur = []
            continue
        if cur:
            last_k, last_v = cur[-1]
            joinable = True
            if n[0] in ("d", "u", "w") and last_k in ("d", "u", "w"):
                # "twenty five" joins; "340 200" does not
                joinable = (last_k in ("u", "w") and last_v >= 20 and last_v % 10 == 0
                            and n[1] < 10 and n[0] != "d")
            elif n[0] in ("d", "u", "w") and last_k == "m":
                joinable = n[1] < last_v * (1000 if last_v >= 1000 else 1)
            elif n[0] == "f":
                joinable = last_k == "m"
            if not joinable:
                spans.append((start, i, cur)); cur = []
        if not cur:
            start = i
        cur.append(n)
    if cur:
        spans.append((start, len(tokens), cur))
    return spans


def _span_value(items) -> Optional[float]:
    kinds = [k for k, _ in items]
    if kinds == ["w"] or kinds == ["f"] or all(k == "f" for k in kinds):
        return None
    total, cur, mod = 0.0, 0.0, 0.0
    for k, v in items:
        if k in ("d", "u", "w"):
            cur += v + mod; mod = 0.0
        elif k == "f":
            mod = v
        elif k == "m":
            base = cur if cur else 1 + mod
            mod = 0.0
            if v >= 1000:
                total += base * v; cur = 0.0
            else:
                cur = base * v
    value = total + cur
    return value if value > 0 else None


def extract_amounts(tokens: list[str]):
    """Return (amount_paise | None, options_paise, used_token_indexes)."""
    found, used = [], set()
    for s, e, items in _spans(tokens):
        val = _span_value(items)
        if val is None:
            continue
        idx = set(range(s, e))
        nxt = tokens[e] if e < len(tokens) else ""
        prev = tokens[s - 1] if s > 0 else ""
        if nxt in QUANTITY:
            used |= idx | {e}
            continue  # "2 kilo" is a quantity, not money
        currency = nxt in CURRENCY or prev in CURRENCY
        found.append((round(val * 100), currency))
        used |= idx
    if not found:
        return None, [], used
    tagged = [a for a, c in found if c]
    if len(tagged) == 1:
        return tagged[0], [], used
    values = list(dict.fromkeys(a for a, _ in found))
    if len(values) == 1:
        return values[0], [], used
    return None, values, used


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------
def parse(text: str, lang_hint: Optional[str] = None) -> ParseResult:
    raw_tokens = tokenize(text)
    tokens, roles = [], {}
    for t in raw_tokens:
        base, role = _strip_suffix(t)
        if role:
            roles[len(tokens)] = role
        tokens.append(base)
    tset = set(tokens)

    # Language of the reply
    lang = detect_script_lang(text)
    if not lang:
        hi = len(tset & HINDI_HINTS)
        kn = len(tset & KANNADA_HINTS) + sum(1 for t in tokens if _has_prefix(t, ("kott",)))
        lang = "hi" if hi > kn and hi else "kn" if kn > hi and kn else (lang_hint or "en")
    r = ParseResult(text=text, lang=lang, tokens=tokens)

    amount, options, used = extract_amounts(tokens)
    r.amount, r.amount_options = amount, options

    # Credit / payment scoring
    dative = bool(tset & DATIVE) or "dat" in roles.values()
    source = bool(tset & SOURCE) or "src" in roles.values()
    credit = payment = 0.0
    keyword_idx = set()
    for i, t in enumerate(tokens):
        if t in CREDIT_STRONG:
            credit += 3; keyword_idx.add(i)
        elif t in CREDIT_WEAK:
            keyword_idx.add(i)
            if amount or options:
                credit += 2
        elif t in PAYMENT_STRONG or _has_prefix(t, PAYMENT_PREFIX):
            payment += 3; keyword_idx.add(i)
        elif t in GIVE or _has_prefix(t, GIVE_PREFIX):
            keyword_idx.add(i)
            # "Ramesh ko diya" / "Rameshge kotte" = shop gave goods -> credit (unsure)
            if dative:
                credit += 1.5
            else:
                payment += 2
        elif t in TAKE or _has_prefix(t, TAKE_PREFIX):
            keyword_idx.add(i)
            if source:
                payment += 1.5
            else:
                credit += 2
    if credit or payment:
        r.kind = "credit" if credit > payment else "payment" if payment > credit else None
        top, other = max(credit, payment), min(credit, payment)
        if r.kind is None:
            r.kind_conf = 0.0
        elif other == 0:
            r.kind_conf = 0.95 if top >= 3 else 0.8 if top >= 2 else 0.6
        else:
            r.kind_conf = 0.55

    r.yes = bool(tset & YES)
    r.no = bool(tset & NO)
    for t in tokens:
        if t in ORDINAL:
            r.ordinal = ORDINAL[t]; break

    # Customer name: first contiguous run of tokens that are nothing else
    reserved = _known()
    run: list[int] = []
    for i, t in enumerate(tokens):
        candidate = (i not in used and i not in keyword_idx and t not in reserved
                     and t != "₹" and not re.fullmatch(r"[\d.]+", t)
                     and not _has_prefix(t, GIVE_PREFIX + TAKE_PREFIX + PAYMENT_PREFIX)
                     and len(t) > 1)
        if candidate and (not run or run[-1] == i - 1) and len(run) < 3:
            run.append(i)
        elif run and not candidate:
            break
    if run:
        parts = [tokens[i] for i in run]
        r.name = " ".join(p.capitalize() if re.fullmatch(r"[a-z]+", p) else p for p in parts)

    # Intent
    first = tokens[0] if tokens else ""
    has_query = bool(tset & QUERY) or ("baaki" in tset or "बाकी" in tset or "ಬಾಕಿ" in tset)
    if tset & UNDO:
        r.intent = "undo"
    elif (first in NO or tset & CHANGE) and (amount or options) and not r.kind:
        r.intent = "correction"
    elif r.yes and not (amount or options) and not r.name and not r.kind:
        r.intent = "yes"
    elif r.no and not (amount or options) and not r.kind:
        r.intent = "no"
    elif has_query and not (amount or options):
        if tset & TODAY:
            r.intent = "report_today"
        elif tset & ALL or not r.name:
            r.intent = "report_all" if (tset & ALL or "total" in tset) else "balance"
        else:
            r.intent = "balance"
    elif amount or options or r.kind:
        r.intent = "transaction"
    elif r.name:
        r.intent = "name_only"
    return r
