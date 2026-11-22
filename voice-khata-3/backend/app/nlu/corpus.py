"""Training data for the Voice Khata language model.

Generates labelled shop sentences in Kannada, Hindi and English (native script,
romanised and code-mixed). Every sentence gets:
  * an intent: credit, payment, amount_only, balance, report_today, report_all,
               correction, undo, yes, no
  * a tag per word: B-/I-NAME (customer), B-/I-AMT (money), B-/I-QTY (quantity), O

Names, amounts, items and phrasings are drawn at random, then noise is added the
way real speech-to-text output looks (fillers, honorifics, spelling variants).
Training and test sets use DIFFERENT names and the test set includes sentence
patterns the model never saw, so the score measures real generalisation.
"""
from __future__ import annotations

import random
import re

from ..numbers import HI_ROMAN_1_99, KN_ROMAN_TENS, KN_ROMAN_UNITS, to_words
from ..parser import tokenize
from ..translit import to_devanagari, to_kannada

INTENTS = ["credit", "payment", "amount_only", "balance", "report_today", "report_all",
           "correction", "undo", "yes", "no"]

TRAIN_NAMES = """Ramesh Suresh Lakshmi Anil Sunil Mahesh Ganesh Prakash Ravi Raju Mohan Kiran Anand
Vijay Ajay Sanjay Deepak Ashok Naveen Praveen Santosh Manju Manjunath Basavaraj Shivu Shivakumar
Nagaraj Venkatesh Srinivas Gopal Krishna Hari Mani Babu Murali Sudha Geetha Seetha Kavitha Savitha
Shobha Rekha Usha Asha Lata Pooja Priya Divya Sowmya Shilpa Anitha Sunitha Vanitha Bhagya Shanthi
Yamuna Ganga Kamala Vimala Sarala Parvathi Radha Meena Neela Ramya Rashmi Nandini Chandru Puttaswamy
Siddappa Basappa Mallesh Lokesh Dinesh Rajesh Umesh Naresh Harish Girish Satish Jagadish Shankar
Rahul Rohit Amit Sumit Vikas Akash Arjun Karthik Varun Tarun Nikhil Abhishek Shreyas Pavan Chetan
Imran Salim Rafiq Farhan Ayesha Fathima Joseph Thomas Mary David Kumar Gowda Reddy Shetty""".split()
TEST_NAMES = """Bhyrav Pramod Shanthamma Kempegowda Hanumanth Yallappa Nethra Spoorthi Tejas Darshan
Bhavya Chaitra Madhu Keerthi Sahana Raghu Veeresh Mallikarjun Siddharth Jyothi Gangamma Thimmaiah
Prashanth Vinay Akshay Sneha Anusha Pallavi Yashas Sharath""".split()
SURNAMES = ["Kumar", "Gowda", "Reddy", "Shetty", "Rao", "Naik", "Patil", "Hegde", "Singh", "Sharma"]

ITEMS = {"lat": ["sugar", "chini", "rice", "chawal", "akki", "doodh", "milk", "haalu", "oil", "tel",
                 "dal", "atta", "soap", "biscuit", "bread", "tea", "salt", "ghee", "maida", "rava"],
         "dev": ["चीनी", "चावल", "दूध", "तेल", "दाल", "आटा", "साबुन", "चाय", "नमक", "घी"],
         "kn": ["ಸಕ್ಕರೆ", "ಅಕ್ಕಿ", "ಹಾಲು", "ಎಣ್ಣೆ", "ಬೇಳೆ", "ಹಿಟ್ಟು", "ಸೋಪು", "ಟೀ", "ಉಪ್ಪು", "ತುಪ್ಪ"]}
QTY_UNITS = {"lat": ["kilo", "kg", "litre", "packet", "dozen", "piece"],
             "dev": ["किलो", "लीटर", "पैकेट", "दर्जन"],
             "kn": ["ಕೆಜಿ", "ಕಿಲೋ", "ಲೀಟರ್", "ಪ್ಯಾಕೆಟ್"]}

# ------------------------------------------------------------------ templates
# style: lat-hi (romanised Hindi), lat-kn, en, dev (Hindi), kn (Kannada), mix
# {N} name   {NGE} Kannada name+ಗೆ  {NGEL} romanised name+ge  {A} amount  {Q} quantity  {I} item
T = {
"credit": {
 "lat-hi": ["{N} ka {A} udhaar", "{N} ka {A} udhaar likho", "{N} ke khate mein {A} likh do", "{N} ko {A} ka saamaan udhaar diya", "{N} ne {A} ka maal liya", "{N} {A} udhaar", "{A} {N} ka udhaar", "{N} ka {A} rupaye baaki", "{N} ke naam {A} likh do", "{N} ne {Q} {I} liya {A} udhaar", "{N} ka {A} khate mein daal do", "{N} ji ka {A} udhaar likhna", "{N} bhai {A} udhaar", "{N} ko {A} udhaar de diya", "{N} ke {A} baaki hai", "{N} {A} ka saamaan le gaya", "{N} ke hisaab mein {A} jod do", "udhaar {N} {A}", "{N} ka {A} rupaye ka udhaar chadha do", "{N} ka {A} likh lo", "{N} ke upar {A} udhaar", "{N} ka {A} baad mein dega", "{N} {A} ka udhaar le gaya", "{N} ne udhaar pe {A} ka liya", "{N} {Q} {I} le gaya {A} likh lo"],
 "dev":    ["{N} का {A} उधार", "{N} का {A} रुपये उधार लिखो", "{N} के खाते में {A} लिख दो", "{N} ने {A} का सामान लिया", "{N} को {A} का सामान उधार दिया", "{N} के नाम {A} लिखो", "{N} का {A} बाकी", "{N} {A} उधार", "{N} ने {Q} {I} लिया {A} रुपये उधार", "{N} जी का {A} उधार लिख दीजिए", "{N} का {A} रुपये खाते में डालो", "उधार {N} {A}", "{N} {A} का सामान ले गए", "{N} के ऊपर {A} उधार", "{N} {A} बाद में देंगे", "{N} ने उधार पर {A} का लिया", "{N} के हिसाब में {A} जोड़ दो"],
 "kn":     ["{NGE} {A} ಉದ್ರಿ", "{N} {A} ಉದ್ರಿ", "{N} ಅವರ ಖಾತೆಗೆ {A} ಬರೆಯಿರಿ", "{NGE} {A} ಸಾಲ ಕೊಟ್ಟೆ", "{N} {A} ರೂಪಾಯಿ ಸಾಮಾನು ತಗೊಂಡ್ರು", "{N} ಅವರಿಗೆ {A} ಉದ್ರಿ ಹಾಕಿ", "{N} ಖಾತೆಗೆ {A} ಹಾಕಿ", "{N} {A} ಬಾಕಿ", "{N} {Q} {I} ತಗೊಂಡ್ರು {A} ಉದ್ರಿ", "{NGE} {A} ರೂಪಾಯಿ ಉದ್ರಿ ಬರೀರಿ", "{N} ಅಣ್ಣ {A} ಉದ್ರಿ", "{N} {A} ರೂಪಾಯಿ ಸಾಲ", "{N} ಲೆಕ್ಕಕ್ಕೆ {A} ಸೇರಿಸಿ", "{N} {A} ನಂತರ ಕೊಡ್ತಾರೆ", "{N} ಮೇಲೆ {A} ಉದ್ರಿ", "{N} {A} ಉದ್ರಿ ತಗೊಂಡ್ರು", "{NGE} {A} ಬರೆದುಕೊಳ್ಳಿ", "{N} {A} ರೂಪಾಯಿ ಸಾಮಾನು ತೆಗೆದುಕೊಂಡು ಹೋದರು"],
 "lat-kn": ["{NGEL} {A} udri", "{N} {A} udri", "{N} avara khatege {A} bariri", "{N} {A} saala", "{N} {A} rupayi samanu tagondru", "{N} {A} udri tagondru", "{N} mele {A} udri", "{N} {A} amele kodtare", "{N} {A} udri haaki"],
 "en":     ["{N} {A} credit", "add {A} credit for {N}", "{N} owes {A}", "{N} took goods worth {A}", "put {A} on {N} account", "{N} bought {Q} {I} for {A} on credit", "give {N} {A} credit", "{A} credit to {N}", "write {A} in {N} khata", "{N} has to pay {A}", "{N} {A} pending", "add {A} to {N} account", "{N} will pay {A} later", "note {A} for {N}", "{N} {A} on credit", "{N} credit {A}", "{N} took {Q} {I} worth {A}"],
 "mix":    ["{N} ka {A} credit add karo", "{N} ko {A} credit", "{NGE} {A} credit ಹಾಕಿ",
            "{N} {A} udhaar ಬರೀರಿ", "{N} ka {A} ಉದ್ರಿ", "{N} ka {A} credit likho", "{N} {A} ರೂಪಾಯಿ credit"],
},
"payment": {
 "lat-hi": ["{N} ne {A} diya", "{N} ne {A} diye", "{N} ne {A} jama kiya", "{N} se {A} mile", "{N} ka {A} jama", "{N} {A} jama", "{N} ne {A} wapas kiye", "{N} ne {A} chuka diya", "{A} {N} ne diya", "{N} ne {A} rupaye de diye", "{N} se {A} aaya", "{N} ka {A} payment aaya", "{N} ne {A} online bheja", "{N} ne {A} gpay kiya", "{N} {A} de gaya", "{N} ne {A} lauta diye", "{N} se {A} mil gaye", "{N} {A} de ke gaya", "{N} ka {A} aa gaya", "{N} se {A} wasool hua"],
 "dev":    ["{N} ने {A} दिए", "{N} ने {A} रुपये दिए", "{N} से {A} जमा", "{N} का {A} जमा करो", "{N} ने {A} वापस किए", "{N} ने {A} चुकाए", "{N} से {A} मिले", "{N} ने {A} दे दिए", "{N} ने {A} रुपये जमा कराए", "{N} ने {A} लौटा दिए", "{N} से {A} मिल गए", "{N} के {A} आ गए", "{N} {A} देकर गए", "{N} से {A} वसूल हुए"],
 "kn":     ["{N} {A} ಕೊಟ್ಟರು", "{N} {A} ಕೊಟ್ರು", "{N} {A} ಕೊಟ್ಟಿದ್ದಾರೆ", "{N} ಅವರಿಂದ {A} ಬಂತು", "{N} {A} ಜಮಾ", "{N} {A} ವಾಪಸ್ ಕೊಟ್ರು", "{N} {A} ಕಟ್ಟಿದ್ರು", "{N} {A} ರೂಪಾಯಿ ಕೊಟ್ಟು ಹೋದ್ರು", "{N} {A} ಪಾವತಿ ಮಾಡಿದರು", "{N} {A} ಫೋನ್ ಪೇ ಮಾಡಿದ್ರು", "{N} ಅವರು {A} ರೂಪಾಯಿ ಕೊಟ್ಟಿದ್ದಾರೆ", "{N} ಅವರಿಂದ {A} ಬಂದಿದೆ", "{N} {A} ಕೊಟ್ಟು ಹೋದರು", "{N} ಕಡೆಯಿಂದ {A} ಬಂತು", "{N} {A} ವಾಪಸ್ ಮಾಡಿದ್ರು", "{N} ಕಡೆಯಿಂದ {A} ಬಂದಿದೆ"],
 "lat-kn": ["{N} {A} kottru", "{N} {A} kottidare", "{N} {A} jama", "{N} {A} kattidru", "{N} kadeyinda {A} bantu", "{N} {A} kottu hodru", "{N} inda {A} bandide", "{N} {A} vapas kottru", "{N} avarinda {A} bantu"],
 "en":     ["{N} paid {A}", "received {A} from {N}", "{N} gave {A}", "{N} returned {A}", "{A} received from {N}", "{N} settled {A}", "got {A} from {N}", "{N} sent {A} on upi", "{N} payment {A}", "{N} cleared {A}", "{N} gave back {A}", "{N} paid back {A}", "{A} came from {N}", "{N} cleared {A} today", "{N} deposited {A}"],
 "mix":    ["{N} ne {A} payment kiya", "{N} {A} paid ಮಾಡಿದ್ರು", "{N} ka {A} received",
            "{N} {A} payment ಬಂತು", "{N} ne {A} upi kiya"],
},
"amount_only": {
 "lat-hi": ["{N} {A}", "{A} {N}", "{N} ka {A}", "{N} {A} rs", "{N} ji {A}", "{N} ke {A}", "{N} {A} rupaye"],
 "dev":    ["{N} {A}", "{N} का {A}", "{N} {A} रुपये"],
 "kn":     ["{N} {A}", "{N} {A} ರೂಪಾಯಿ", "{N} ಅವರು {A}", "{N} {A} ರೂ", "{A} {N}"],
 "en":     ["{N} {A}", "{N} {A} rupees", "{N} {A} rs", "{A} rupees {N}", "{A} for {N}"],
},
"balance": {
 "lat-hi": ["{N} ka baaki kitna hai", "{N} ka hisaab batao", "{N} ka kitna baaki", "{N} ka balance", "{N} ko kitna dena hai", "{N} kitna dena hai", "{N} ka khata dikhao", "{N} ka kitna hua", "{N} ka total kitna", "{N} ka kya hisaab hai", "{N} pe kitna hai"],
 "dev":    ["{N} का कितना बाकी है", "{N} का हिसाब बताओ", "{N} को कितना देना है", "{N} का बैलेंस",
            "{N} पर कितना बाकी है"],
 "kn":     ["{N} ಬಾಕಿ ಎಷ್ಟು", "{N} ಎಷ್ಟು ಕೊಡಬೇಕು", "{N} ಲೆಕ್ಕ ಹೇಳಿ", "{N} ಅವರದು ಎಷ್ಟು ಬಾಕಿ ಇದೆ", "{N} ಖಾತೆ ಎಷ್ಟಿದೆ", "{N} ಲೆಕ್ಕ ಎಷ್ಟಾಯ್ತು", "{N} ಎಷ್ಟು ಬಾಕಿ ಕೊಡಬೇಕು", "{N} ಖಾತೆ ತೋರಿಸಿ", "{N} ಅವರ ಬಾಕಿ ಹೇಳಿ"],
 "lat-kn": ["{N} eshtu baaki", "{N} baaki eshtu ide", "{N} lekka eshtu", "{N} khate eshtu ide", "{N} avaradu eshtu baaki", "{N} lekka heli"],
 "en":     ["how much does {N} owe", "{N} balance", "what is {N} balance", "check {N} account", "show {N} khata", "{N} pending amount", "how much is {N} due", "{N} total due", "tell me {N} balance"],
},
"report_today": {
 "lat-hi": ["aaj ka hisaab", "aaj kitna udhaar gaya", "aaj ka total batao", "aaj kitna jama hua", "aaj ki report", "aaj ka total kitna", "aaj kitna kamaya", "aaj ka collection", "aaj ka pura hisaab", "aaj ka khata batao"],
 "dev":    ["आज का हिसाब", "आज कितना जमा हुआ", "आज कितना उधार गया", "आज की रिपोर्ट बताओ"],
 "kn":     ["ಇವತ್ತಿನ ಲೆಕ್ಕ", "ಇಂದು ಎಷ್ಟು ಉದ್ರಿ ಆಯ್ತು", "ಇವತ್ತು ಎಷ್ಟು ಜಮಾ ಆಯ್ತು", "ಇವತ್ತಿನ ಒಟ್ಟು", "ಇಂದಿನ ಜಮಾ ಎಷ್ಟು", "ಇವತ್ತು ಎಷ್ಟು ಕಲೆಕ್ಷನ್", "ಇಂದಿನ ವರದಿ", "ಇಂದಿನ ಲೆಕ್ಕ ಹೇಳಿ"],
 "lat-kn": ["ivattina lekka", "indina lekka", "ivattu eshtu udri", "ivattina total", "ivattu eshtu jama aaytu"],
 "en":     ["today's total", "today's report", "how much credit today", "what happened today", "today collection", "today", "what is today's collection", "summary of today", "show today summary"],
},
"report_all": {
 "lat-hi": ["sabka baaki kitna", "kul baaki kitna hai", "sab customers ka hisaab", "kaun sabse zyada baaki", "total baaki batao", "sab ka total baaki", "kul kitna lena hai", "sabka hisaab batao", "sab ka kitna baaki hai", "sab logon ka baaki", "sab ka udhaar kitna hai"],
 "dev":    ["सबका कितना बाकी है", "कुल बाकी बताओ", "सब ग्राहकों का हिसाब", "सबका कुल हिसाब", "कुल कितना लेना है", "सब लोगों का बाकी", "सबसे ज़्यादा बाकी किसका है"],
 "kn":     ["ಎಲ್ಲರ ಬಾಕಿ ಎಷ್ಟು", "ಒಟ್ಟು ಬಾಕಿ ಎಷ್ಟು", "ಎಲ್ಲಾ ಗ್ರಾಹಕರ ಲೆಕ್ಕ", "ಎಲ್ಲರ ಒಟ್ಟು ಲೆಕ್ಕ", "ಒಟ್ಟು ಎಷ್ಟು ಬರಬೇಕು", "ಎಲ್ಲರದು ಎಷ್ಟು ಬಾಕಿ", "ಯಾರದು ಹೆಚ್ಚು ಬಾಕಿ"],
 "lat-kn": ["ellara baaki eshtu", "ottu baaki eshtu"],
 "en":     ["total outstanding", "who owes the most", "how much do all customers owe", "show all balances", "all customers total", "everyone's balance", "how much is pending overall", "total pending amount"],
},
"correction": {
 "lat-hi": ["nahi {A}", "nahi nahi {A}", "galat hai {A} karo", "nahi {A} tha", "{A} kar do galat tha", "sorry {A}", "nahi woh {A} hai", "galat {A}", "{A} likho galat hai", "nahi bhai {A}"],
 "dev":    ["नहीं {A}", "गलत {A} करो", "नहीं नहीं {A}", "नहीं {A} था"],
 "kn":     ["ಇಲ್ಲ {A}", "ಅಲ್ಲ {A}", "ತಪ್ಪು {A} ಮಾಡಿ", "ಇಲ್ಲ ಇಲ್ಲ {A}", "ತಪ್ಪಾಯ್ತು {A}", "ಇಲ್ಲ ಅದು {A}", "{A} ಮಾಡಿ ತಪ್ಪಾಗಿದೆ", "ಅಲ್ಲ {A} ರೂಪಾಯಿ"],
 "lat-kn": ["illa {A}", "tappu {A}", "illa adu {A}", "alla {A}"],
 "en":     ["no {A}", "no make it {A}", "change it to {A}", "correct it to {A}", "sorry {A}", "not that {A}", "make it {A}", "it should be {A}", "wrong it is {A}"],
},
"undo": {
 "lat-hi": ["undo", "cancel karo", "last wala hatao", "pichhla entry hata do", "galti se hua hatao", "last entry cancel", "abhi wala hatao", "delete karo", "woh hatao"],
 "dev":    ["रद्द करो", "पिछली एंट्री हटाओ", "वो हटा दो", "आखिरी वाला हटाओ"],
 "kn":     ["ಕೊನೆಯದು ತೆಗೆದುಹಾಕಿ", "ರದ್ದು ಮಾಡಿ", "ಅದನ್ನು ತೆಗೆಯಿರಿ", "ಅದನ್ನು ರದ್ದು ಮಾಡಿ", "ಕೊನೆಯದು ಡಿಲೀಟ್", "ಕೊನೆಯ ಎಂಟ್ರಿ ಡಿಲೀಟ್ ಮಾಡಿ"],
 "en":     ["delete the last entry", "remove that", "cancel it", "undo that", "undo last", "take that back", "cancel the last one", "remove last entry"],
},
"yes": {
 "lat-hi": ["haan", "haan ji", "haan likho", "theek hai", "sahi hai", "haan sahi", "ji haan", "haan bilkul", "haan theek", "ji", "sahi likho", "haan save karo"],
 "dev":    ["हाँ", "हाँ लिखो", "ठीक है", "सही है", "हाँ बिल्कुल", "जी हाँ", "सही लिखो", "हाँ जी"],
 "kn":     ["ಹೌದು", "ಸರಿ", "ಹೂಂ ಬರೀರಿ", "ಹೌದು ಸರಿ", "ಹೌದು ಬರೀರಿ", "ಸರಿ ಬರೆಯಿರಿ", "ಹೂಂ", "ಹೌದು ಬರೆಯಿರಿ"],
 "lat-kn": ["haudu", "sari", "hoon", "sari bariri", "haudu sari", "kone entry tegi", "radd maadi", "adu delete maadi", "haudu bariri"],
 "en":     ["yes", "ok", "yes save it", "correct", "yeah", "okay go ahead", "sure", "fine", "yes correct", "that's right", "go ahead", "right"],
},
"no": {
 "lat-hi": ["nahi", "nahi rehne do", "mat likho", "nahi galat hai", "nahi chahiye", "mat karo", "nahi ji", "rehne do"],
 "dev":    ["नहीं", "मत लिखो", "रहने दो", "नहीं चाहिए", "मत करो", "नहीं जी", "नहीं गलत है"],
 "kn":     ["ಇಲ್ಲ", "ಬೇಡ", "ಬರೀಬೇಡಿ", "ಬೇಡ ಬಿಡಿ", "ಇಲ್ಲ ಬೇಡ ಬಿಡಿ", "ಬರೆಯಬೇಡಿ", "ಇಲ್ಲ ಬೇಡ"],
 "lat-kn": ["illa", "beda", "beda bidi", "illa beda", "bareyabedi", "bareebedi"],
 "en":     ["no", "don't save", "leave it", "no thanks", "no don't", "cancel no", "not needed", "nope"],
},
}

FILLERS = {"lat": ["achha", "suniye", "haan", "ok", "sir", "boss", "dekho"],
           "dev": ["अच्छा", "सुनिए", "देखो"], "kn": ["ಅಣ್ಣ", "ಸರ್", "ನೋಡಿ", "ಹಾ"], "en": ["ok", "so", "please"]}
HONORIFICS = {"lat": ["ji", "bhai", "anna", "akka", "sir", "madam", "avru"],
              "dev": ["जी", "भाई", "दीदी"], "kn": ["ಅವರು", "ಅಣ್ಣ", "ಅಕ್ಕ", "ಸರ್"]}
SPELLING = {"udhaar": ["udhar", "udaar", "udhaar", "udhari", "udhaara"], "jama": ["jamaa", "jama"],
            "diya": ["dia", "diya", "diye"], "hisaab": ["hisab", "hisaab"], "baaki": ["baki", "baaki", "baqi"],
            "kitna": ["kitnaa", "kitna"], "rupaye": ["rupay", "rupaye", "rupees", "rs"], "nahi": ["nahin", "nai", "nahi"],
            "haan": ["han", "haan", "ha"], "khate": ["khaate", "khate"], "udri": ["udhri", "udri"]}


def _script(style):
    return {"dev": "dev", "kn": "kn"}.get(style, "lat")


def _name(names, rng, script):
    n = rng.choice(names)
    if rng.random() < 0.12:
        n = f"{n} {rng.choice(SURNAMES)}"
    if script == "dev":
        return to_devanagari(n)
    if script == "kn":
        return to_kannada(n)
    return n


def _hi_roman_words(n: int) -> str:
    th, rest = divmod(n, 1000)
    h, r = divmod(rest, 100)
    out = []
    if th:
        out += [HI_ROMAN_1_99[th - 1] if th < 100 else str(th), "hazaar"]
    if h:
        out += [HI_ROMAN_1_99[h - 1], "sau"]
    if r:
        out.append(HI_ROMAN_1_99[r - 1])
    return " ".join(out)


def _amount(rng, style) -> str:
    r = rng.random()
    if r < 0.55:
        n = rng.choice([rng.randint(1, 99) * 10, rng.randint(1, 60) * 50, rng.randint(5, 999), rng.randint(1, 20) * 100,
                        rng.randint(10, 9999)])
    else:
        n = rng.choice([rng.randint(1, 99) * 5, rng.randint(1, 30) * 50, rng.randint(1, 15) * 100, rng.randint(11, 99),
                        rng.randint(1, 9) * 1000 + rng.randint(0, 9) * 100])
    use_words = rng.random() < 0.4
    if use_words:
        if style == "dev":
            return to_words(n, "hi")
        if style == "kn":
            return to_words(n, "kn")
        if style == "en":
            return to_words(n, "en")
        if style == "lat-hi" and n < 100000:
            special = {150: "dedh sau", 250: "dhai sau", 350: "saade teen sau", 1500: "dedh hazaar"}
            return special.get(n) or _hi_roman_words(n)
        if style == "lat-kn" and n < 100:
            t, u = divmod(n, 10)
            if t >= 2 and u == 0:
                return KN_ROMAN_TENS[t * 10]
            if n < 10:
                return KN_ROMAN_UNITS[n - 1]
    s = str(n)
    q = rng.random()
    if q < 0.15 and n >= 1000:
        s = f"{n:,}"
    elif q < 0.22 and n % 1000 == 0:
        s = f"{n // 1000}k"
    elif q < 0.3 and n < 1000:
        s = f"{n}.{rng.choice(['50', '00'])}" if rng.random() < 0.3 else s
    return s


def _qty(rng, script) -> str:
    unit = rng.choice(QTY_UNITS[script])
    num = rng.choice(["1", "2", "3", "5", "half"] if script == "lat" else ["1", "2", "3", "5"])
    if script == "dev" and rng.random() < 0.4:
        num = rng.choice(["एक", "दो", "तीन"])
    if script == "kn" and rng.random() < 0.4:
        num = rng.choice(["ಒಂದು", "ಎರಡು", "ಮೂರು"])
    return f"{num} {unit}"


_PH = re.compile(r"\{(N|NGE|NGEL|A|Q|I)\}")


def render(template: str, style: str, names, rng):
    """Fill a template -> (tokens, tags)."""
    script = _script(style)
    name_script = script
    if style == "mix":
        name_script = "kn" if "{NGE}" in template else "lat"
    tokens, tags = [], []
    pos = 0
    for m in _PH.finditer(template):
        lit = template[pos:m.start()]
        for t in tokenize(lit):
            tokens.append(t); tags.append("O")
        ph = m.group(1)
        if ph in ("N", "NGE", "NGEL"):
            nm = _name(names, rng, "kn" if ph == "NGE" else name_script)
            if ph == "NGE":
                nm = nm.replace(" ", " ") + "ಗೆ"
            elif ph == "NGEL":
                nm = nm + "ge"
            label = "NAME"
            toks = tokenize(nm)
        elif ph == "A":
            toks, label = tokenize(_amount(rng, style)), "AMT"
        elif ph == "Q":
            toks, label = tokenize(_qty(rng, script)), "QTY"
        else:
            toks, label = tokenize(rng.choice(ITEMS[script])), "O"
        for i, t in enumerate(toks):
            tokens.append(t)
            tags.append("O" if label == "O" else ("B-" if i == 0 else "I-") + label)
        pos = m.end()
    for t in tokenize(template[pos:]):
        tokens.append(t); tags.append("O")
    return tokens, tags


def _noise(tokens, tags, style, rng):
    script = _script(style)
    fl = FILLERS["en" if style == "en" else script]
    # spelling variants of romanised words
    tokens = [rng.choice(SPELLING[t]) if t in SPELLING and rng.random() < 0.35 else t for t in tokens]
    # honorific after the name
    if "B-NAME" in tags and rng.random() < 0.15 and script in HONORIFICS:
        end = max(i for i, g in enumerate(tags) if g.endswith("NAME")) + 1
        tokens.insert(end, rng.choice(HONORIFICS[script])); tags.insert(end, "O")
    # filler at the start
    if rng.random() < 0.12:
        tokens.insert(0, rng.choice(fl)); tags.insert(0, "O")
    # dropped little words (speech-to-text often skips them)
    if rng.random() < 0.1:
        drop = [i for i, t in enumerate(tokens) if t in ("ka", "ne", "ko", "का", "ने", "ಅವರ", "ಅವರು") and tags[i] == "O"]
        if drop:
            i = rng.choice(drop); tokens.pop(i); tags.pop(i)
    return tokens, tags


def generate(n_per_intent: int, names, seed: int, hold_out: bool):
    """hold_out=False: every template except the last of each group (training).
       hold_out=True : all templates, including the unseen last ones (testing)."""
    rng = random.Random(seed)
    data = []
    for intent, groups in T.items():
        pool = []
        for style, temps in groups.items():
            use = temps if hold_out or len(temps) < 3 else temps[:-1]
            pool += [(style, t) for t in use]
        unseen = [(s, ts[-1]) for s, ts in groups.items() if len(ts) >= 3]
        for _ in range(n_per_intent):
            is_unseen = bool(hold_out and unseen and rng.random() < 0.4)
            if is_unseen:
                style, tmpl = rng.choice(unseen)
            else:
                style, tmpl = rng.choice([x for x in pool if not hold_out or x not in unseen] or pool)
            toks, tags = render(tmpl, style, names, rng)
            toks, tags = _noise(toks, tags, style, rng)
            if toks:
                data.append({"tokens": toks, "tags": tags, "intent": intent, "style": style,
                             "unseen_phrasing": is_unseen})
    rng.shuffle(data)
    return data


def held_out_templates():
    return {i: [ts[-1] for ts in g.values() if len(ts) >= 3] for i, g in T.items()}
