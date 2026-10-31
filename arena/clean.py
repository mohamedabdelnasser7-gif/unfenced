"""Cleaning for the Arena (new, 2026-10-30): a chat's text with names, numbers and places
taken out, in code, before any model sees it and before anything is written.

It wraps reflection/history.py's Masker (reviewed code for untrusted text) and never changes
it. One message goes through these steps, in this order:
 1. normalize: NFKC (full width and styled digits as 0 to 9, odd spaces as spaces), invisible
    format characters out (zero width, direction marks, BOM, word joiner), every combining mark
    out (Arabic short vowels, the grapheme joiner, variation selectors, the keycap sign), spacing
    marks, private use and unassigned code points out, blanks that are letters or symbols out
    (Hangul fillers, Braille blank), look-alike colons and equals signs as : and =, tatweel
    out, Eastern Arabic and Persian digits as 0 to 9. The letters stay as typed.
 2. Emails, also written "x at y dot com", "x(at)y.com" or "x@ y.com" -> [email]; x@y with no dot
    (a payment ID such as name@instapay) or a bare x@ -> [user]; links (http, hxxp, www, a bare domain, any
    host.tld/path) -> [link]; @usernames in any script, the chat's own Instagram username and a
    handle after insta, snap, tiktok and the like -> [user].
 3. A message that gives an address becomes [address] as a whole (gives_address below).
 4. Phones in every Egyptian format, the groups split by spaces, dashes, dots, commas,
    underscores, stars, slashes or و -> [phone]; a number of 4 or more digits after an account
    cue (رقم الحساب, الحساب البنكي, IBAN, account no, rakam el 7esab) -> [number], even with a
    currency or a letter after it (الحساب 1450 جنيه alone is the bill and stays); any other run
    of 7 or more digits with up to 12 signs of any kind (or و, ثم, بعدين, then) between each two
    -> [number], except a sum of up to 11 digits that is not shaped like a phone and has a
    currency right after it (1450 + 90 = 1540 جنيه) or = and + × or * in it (1450 + 60 = 1510);
    a lone run of 5 or 6 digits with no money word before or after it (a zip code, a tracking
    number) -> [number].
 5. Handles with no @: a word with an underscore, letters then 2 or more digits (yasmine1990),
    a dotted handle (yassin.marzouk.99, karim.fz99) and a list first name with digits (KARIM10)
    -> [user].
 6. Order numbers: # then letters or digits, a number of 3 or more digits after an order word
    with up to 8 words between and any signs (الاوردر اللي عملته من يومين 1045, my order (from
    yesterday) 1045, الاوردر بتاعي، 1045), or before one (1045، ده رقم الاوردر) -> [order]; an
    amount stays (الطلب 850 جنيه).
 7. Names: up to 3 words after a name cue (اسمي, الاسم or اسم with : - / | = .. ، or an emoji,
    باسم, المستلم, my name is, name - X, Name X at a line's start, be esm, besm), up to two new
    lines after it,
    stopping at a word that is never a name; any sender's full name from the whole import
    (hamza and ta marbuta forms as one, Arabic typed for a Latin display name and back); the
    history Masker with the chat's own sender names; each of their words in any of its forms,
    joined to و ف ب ل يا, or two of them typed as one; عبد ال... and abd el... names.
 8. Governorates, cities, districts, malls and big streets -> [place]; a short message of a
    [place] and at most 4 other words, none a common word, no digit and no question -> [address]
    (عباس العقاد مدينة نصر). Zamalek and Smouha are left out: they are football clubs too.
 9. A word after يا that is not a form of address, the word after a title (استاذ, مدام,
    كابتن, Mr, ostaz) with or without يا (ياعم too), a list or capitalised name after hi, thx,
    انا, I'm, معاك, a relation word (لابني, لماما, my son), a name-like word after a lone ل, after
    a ل joined to it behind a delivery verb (ابعتها لزوزو) or after deliver to, ship it to, send
    it to (lower case too, a colon or a new line between); every common first name in
    arena/words.py wherever it stands; then up to 2 name-like words after any [name].
Prices and sizes stay (السعر 850 جنيه, مقاس 43): they are what the personas are about.

ChatCleaner.texts cleans a whole chat: after the store asks the name (اسمك ايه, ممكن الاسم,
اسم المستلم؟, مين معايا, Name?), every customer message up to the store's next one that moves on
is [name] (لحظة, then the name, are both [name]); a short store line with no question (تمام,
a thumbs up, ok, an export's media or deleted message line) does not move on. After the store asks
for the address, or after a customer message that cleaned to [address] or [place], every
customer message up to the store's next one is [address]. When the store asks both at once,
the first answer is [name] and the rest [address].
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from kit import send_check
from reflection import history as hist
from arena import words as W
from arena.words import fold

ROOT = Path(__file__).resolve().parent.parent
GOVERNORATES = ROOT / "demo" / "governorates.json"

KINDS = ("name", "phone", "order", "number", "email", "link", "user", "place", "address")
PLACEHOLDER = re.compile(r"\[(?:" + "|".join(KINDS) + r")\]")
RUN = re.compile(r"\[(" + "|".join(KINDS) + r")\](?:[ \t]+\[\1\])+")
LETTER_BEFORE, NO_LETTER_AFTER = send_check.LETTER_BEFORE, send_check.NO_LETTER_AFTER
QUESTION = re.compile(r"[?؟]")
ARABIC = send_check.ARABIC

# ---- 1. normalize

MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")

# format characters (zero width, direction marks), every combining mark left after NFKC (the
# grapheme joiner U+034F, variation selectors, the keycap sign), spacing marks, private use and
# unassigned code points: none is an Arabic or Latin letter
DROPPED = frozenset({"Cf", "Mn", "Me", "Mc", "Co", "Cn"})
# send_check's look-alike colons and equals signs; the blanks it reads as a gap (Hangul fillers,
# Braille blank) are dropped here like a zero width space, so a name split by one stays whole
# (accepted: a Braille blank between two words glues them, hi⠀Karim; reading it as a space
# splits a name instead; neither is typed by people)
LOOKALIKES = {**send_check.LOOKALIKES, **dict.fromkeys((0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800))}


def normalize(text):
    """The text as every rule reads it (step 1 above)."""
    text = unicodedata.normalize("NFKC", str(text or "")).translate(LOOKALIKES)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in DROPPED)
    return MARKS.sub("", text).translate(send_check.EASTERN_DIGITS)


def is_stop(word):
    """True for a word that is never a name, also with و, ف, ب, ل or ال before it."""
    f = fold(word)
    if f in W.STOP:
        return True
    for p in ("وال", "فال", "بال", "لل", "ال", "و", "ف", "ب", "ل"):
        if f.startswith(p) and len(f) - len(p) >= 2 and f[len(p):] in W.STOP:
            return True
    return False


VERB_START = re.compile(r"^[بهح][يتنا]")
VERB_ENDS = ("تلي", "تلك", "ولي", "يلي", "لكم", "ليه", "تني", "وني", "يني", "وا")


def verb_shaped(f):
    """An Arabic word shaped like a verb: بيقول, هتوصل, حنبعت, قالتلي, ابعتوا."""
    return bool(len(f) >= 4 and VERB_START.match(f)) or (len(f) >= 4 and f.endswith(VERB_ENDS))


def is_listed(word, weak=False):
    """A first name, or a word-like name that is no stop word (a weak cue takes fewer)."""
    f = fold(word)
    if f in W.FIRST:
        return True
    return f in W.CUE and not is_stop(word) and not (weak and f in W.NOT_WEAK)


def arabic_name_like(word):
    f = fold(word)
    return bool(ARABIC.search(word)) and len(f) >= 3 and not f.startswith("ال") and not is_stop(word) \
        and not verb_shaped(f)


def latin_capital(word):
    f = fold(word)
    return word[:1].isupper() and word.isascii() and word.isalpha() and len(word) >= 2 and not is_stop(word) \
        and f not in LATIN_FORMS and f not in W.TITLES


# ---- 2. emails, links, users

OBF_EMAIL = re.compile(r"(?<![\w.+\-])[\w.+\-]+(?:\s+dot\s+[\w+\-]+)*\s*(?:\(at\)|\[at\]|\s+at\s+)\s*[\w\-]+"
                       r"(?:\s*(?:\.|\(dot\)|\[dot\]|\s+dot\s+)\s*[\w\-]+)*?"
                       r"\s*(?:\.|\(dot\)|\[dot\]|\s+dot\s+)\s*(?:com|net|org|eg|io|me|co|info|edu|gov)(?!\w)",
                       re.IGNORECASE)
# a full stop after it ends the sentence, not the ID (pay to zorvex@instapay.)
AT_USER = re.compile(r"(?<![\w.+\-@])[\w.+\-]*\w@\w+(?![\w@]|\.\w)")
TLDS = (r"(?:com|net|org|eg|me|ly|io|co|app|link|shop|store|info|biz|gl|gd|to|tv|xyz|site|online|page|ee|ai|dev"
        r"|sa|uk|ae|ca|de|fr|es|tk|gg|cc|ws|fm|kw|qa|om|bh|jo|lb|tn|iq|tr|ru|cn|jp|nl|ch|se|pl|pt|gr|ie|nz|au"
        r"|za|ng|ke|live|art|blog|club|tech|news|space|website|bio|pro|top)")
LINK = re.compile(r"(?<![\w@])(?:h[tx]{2}ps?://|www\.)[^\s<>\"']+"
                  r"|(?<![\w@.\-])(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}/[^\s<>\"']*"
                  r"|(?<![\w@.\-])(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+" + TLDS
                  + r"(?![a-z0-9\-])(?:/[^\s<>\"']*)?", re.IGNORECASE)
# an email with a space next to the @ (zorvex@ gmail.com, zorvex @ gmail . com), and a word with
# a bare @ after it, the rest of an email typed apart (zorvex@, zorvex@.)
SPACED_EMAIL = re.compile(r"(?<![\w.+\-@])[\w.+\-]*\w(?:[ \t]+@[ \t]*|[ \t]*@[ \t]+)(?:[\w\-]+[ \t]*\.[ \t]*)+"
                          + TLDS + r"(?![\w\-])", re.IGNORECASE)
TRAILING_AT = re.compile(r"(?<![\w.+\-@])[\w.+\-]*\w@(?![\w@]|\.\w)")
# whatever is left with a word glued to an @ (zorvex@@instapay, an x@y.z the email rule refuses)
LEFTOVER_AT = re.compile(r"(?<![\w.+\-@])[\w.+\-]*\w@+[\w.+\-@]*")
USER = re.compile(r"(?<![\w@.])@\w(?:[\w.]{0,28}\w)?")
HANDLE = r"(?=[A-Za-z0-9_.]*[A-Za-z])[A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?"
HANDLE_CUE = re.compile(r"(?<!\w)(?:insta(?:gram)?|ig|snap(?:chat)?|tik[ \t]?tok|telegram|fb|facebook|twitter"
                        r"|[اإ]نستا|[اإ]نستجرام|[اإ]نستغرام|سناب(?:[ \t]?شات)?|تيك[ \t]?توك|فيس(?:بوك)?|تليجرام)"
                        r"(?P<mid>(?:[ \t]+(?:is|account|handle|id|username|user|حسابي|بتاعي|اكونت|هو))*"
                        r"(?:[ \t]*[:：][ \t]*|[ \t]+))(?P<h>" + HANDLE + r")(?![\w@])", re.IGNORECASE)
NOT_A_HANDLE = frozenset({"page", "story", "stories", "post", "posts", "reel", "reels", "live", "dm", "link", "account",
                          "profile", "ad", "ads", "too", "also", "only"})


def _handle(m):
    h = fold(m.group("h"))
    if h in W.STOP or h in NOT_A_HANDLE or h in LATIN_FORMS:
        return m.group(0)
    return m.group(0)[:m.start("h") - m.start()] + "[user]"


# ---- 3. addresses

STREET = (
    r"(?:و|ف|ب|ل)?(?:ال)?(?:شارع|طريق|كمبوند|برج|عمار[ةه]|عمارات|فيلا|بلوك|مربع|مجاور[ةه]|حي|منطق[ةه]|مساكن"
    r"|عزب[ةه]|قري[ةه]|نجع|حار[ةه]|عطف[ةه]|ميدان|محور|شق[ةه])",
    r"(?:el[\s\-]?)?(?:share3|sharee3|sharia|shar3|tare2|tari2|compound|kombound|borg|3emara|3amara|emara|villa"
    r"|block|mogawra|manta2a|mante2a|masaken|3ezba|ezba|2arya|karya|7ara|hara|midan|meydan|sha2a|7ay|hay)",
    r"street|road|avenue|compound|tower|building|bldg|villa|block|district|square|lane|apartment",
)
# words after a street word that make it a question or a plain phrase, not a street's name
NOT_A_NAME = (r"(?:[اإأ]يه|[اأ]ي|كام|فين|ده|دي|دا|اللي|الي|هو|هي|بتاع|which|what|where|is|no|name|eh|eih|fen|kam"
              r"|da|di|el\s?eh)")
STREET_NAMED = re.compile(r"(?<!\w)(?:" + "|".join(STREET) + r")(?!\w)[ \t]+(?!" + NOT_A_NAME + r"(?!\w))"
                          r"[^\W\d_]{2,}", re.IGNORECASE)
NEAR = (r"(?:جنب|جمب|بجوار|بجانب|قدام|[اأ]مام|خلف|ورا|وراء|قصاد|قريب\s+من|فوق|تحت|عند|بعد|ganb|gamb|odam|2odam"
        r"|oddam|wara|2osad|osad|near|next\s+to|behind|opposite|in\s+front\s+of|beside|across\s+from)")
MARK_AR = (r"(?:ال)?(?:مسجد|جامع|كنيس[ةه]|مدرس[ةه]|صيدلي[ةه]|بنك|محط[ةه]|مترو|ماركت|سوبر\s*ماركت|كوبري|مستشف[يى]"
           r"|نادي|مول|قسم|بنزين[ةه]|مخبز|فرن|كافيه|قهو[ةه]|بواب[ةه]|مدخل|مطعم|محل|سنترال|جامع[ةه]|كلي[ةه]|موقف"
           r"|كشك|مكتب[ةه]|فندق|مركز|سنتر|كارفور|سبينس|هايبر)")
MARK_LA = (r"(?:(?:el|the)\s?)?(?:masged|masgid|masjid|gam3|game3|kenisa|madrasa|madrsa|saydaleya|sydalya|pharmacy"
           r"|bank|ma7atet|ma7ata|station|metro|market|supermarket|kobry|bridge|mostashfa|hospital|nady|club|mall"
           r"|mosque|church|school|cafe|bakery|restaurant|shop|university|hotel|center|centre|kiosk|carrefour"
           r"|spinneys|hyper)")
LANDMARK = re.compile(LETTER_BEFORE + NEAR + r"\s+(?:" + MARK_AR + "|" + MARK_LA + r")" + NO_LETTER_AFTER,
                      re.IGNORECASE)
LABEL = re.compile(LETTER_BEFORE + r"(?:(?:و|ف|ب|ل)?(?:ال)?عنوان(?:ي|ى|ه|ها|ك|كم)?(?:\s+(?:ال)?(?:شحن|توصيل|استلام))?"
                   r"|(?:el\s?)?3[ae]nwan(?:y|i|ak|ek|o)?|(?:(?:delivery|shipping)\s+)?address|location"
                   r"|(?:ال)?لوكيشن)" + NO_LETTER_AFTER + r"\s*[:：]\s*\S", re.IGNORECASE)
MY_ADDRESS = re.compile(LETTER_BEFORE + r"(?:عنواني|عنوانى|3[ae]nwany|3[ae]nwani|my\s+address(?:\s+is)?)"
                        + NO_LETTER_AFTER + r"\s*[:：]?\s*[^\W_]+\s+[^\W_]+", re.IGNORECASE)
ORDINAL_AR = r"(?:ال)?(?:[اأ]ول|[اأ]رضي|[اأ]خير|تاني|ثاني|تالت|ثالث|رابع|خامس|سادس|سابع|تامن|ثامن|تاسع|عاشر)"
ORDINAL_LA = (r"(?:el\s?)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|ground|last|top|awel|tany"
              r"|talet|rabe3|khames|sades|sabe3|tamen|tase3|3asher|ardy|ardi)")
FLOOR = re.compile(LETTER_BEFORE + r"(?:(?:(?:و|ف|ب)?(?:ال)?(?:دور|طابق)\s+" + ORDINAL_AR + r")"
                   r"|(?:(?:el\s?)?(?:dor|floor)\s+" + ORDINAL_LA + r")"
                   r"|(?:(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|ground|top|\d+(?:st|nd|rd|th))"
                   r"\s+floor))" + NO_LETTER_AFTER, re.IGNORECASE)
COORDS = re.compile(r"(?<![\d.])-?\d{1,3}\.\d{3,}\s*[,،؛;]?\s*-?\d{1,3}\.\d{3,}(?![\d.])"
                    r"|\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*\d{1,2}(?:\.\d+)?\s*[\"″]?\s*[NSEW]"
                    r"|(?<![\w+])[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}(?!\w)", re.IGNORECASE)


def gives_address(text):
    """True when the text gives an address: a number after or before an address word (history's
    own check: عمارة 12, 12 شارع), a street or building word with a name after it (شارع
    التحرير, share3 el nasr, street Salah, 7ay el ...), a landmark (جنب صيدلية, فوق بنك, next
    to the mosque), an address label with text after it (العنوان: ..., عنوان الشحن: ...,
    location: ..., عنواني ...), a floor (الدور الخامس, third floor) or map coordinates
    (with , ، ؛ or a space, degrees, or a plus code)."""
    text = normalize(text)
    return bool(hist.gives_address(text) or LABEL.search(text) or MY_ADDRESS.search(text) or FLOOR.search(text)
                or STREET_NAMED.search(text) or LANDMARK.search(text) or COORDS.search(text))


# ---- 4. numbers

_SEP = r"(?:[ \t\-_.,،*/‐-―−]|[ \t]*و[ \t]*)"
PHONE_WIDE = re.compile(  # kit/send_check.py PHONE with more signs between the groups
    r"(?<![\w+])(?:(?:\+|00)[ \t]?20" + _SEP + r"?|20|0)1[0125](?:" + _SEP + r"?\d){8}(?!\d)"
    r"|(?<![\w+])(?:\+|00)[ \t]?20(?:" + _SEP + r"?\d){8,10}(?!\d)"
    r"|(?<![\w+.,])0(?:2(?:" + _SEP + r"?\d){8}|3(?:" + _SEP + r"?\d){7}|[4-9]\d(?:" + _SEP + r"?\d){7})(?!\d)"
    r"|(?<![\w+])\+[ \t]?[1-9](?:" + _SEP + r"?\d){7,14}(?!\d)")
LETTER_O_PHONE = re.compile(r"(?<![\w+])[0oO][1lI][0125oO](?:[ \t\-.]?[0-9oO]){8}(?!\w)")
# Any run of up to 12 signs between the digits, of any kind (; : ؛ | = ~ + ' and the rest, a new
# line too), or و, ثم, بعدين, then with up to 3 signs each side: never a list of signs, so a new
# sign cannot split a phone past it.
SPREAD_NUMBER = re.compile(r"(?<!\d)\+?\(?\d(?:(?:[\W_]{0,12}|[\W_]{0,3}(?:و[ \t]*بعدين|و|ثم|بعدين|then)[\W_]{0,3})"
                           r"\d){6,}\)?(?!\d)", re.IGNORECASE)
SUM_SIGN = re.compile(r"[+×*]")
PHONE_SHAPE = re.compile(r"(?:(?:00)?20|0)?1[0125]\d{8}|0\d{8,9}|00\d{7,15}")
BARE5 = re.compile(r"(?<![\w.,])\d{5,6}(?!\w|[.,]\d)")
MONEY_NEXT = re.compile(r"\s*" + send_check.CURRENCY + r"(?!\w)", re.IGNORECASE)
CUE_BEFORE = re.compile(LETTER_BEFORE + r"(?:" + "|".join(send_check.PRICE_WORDS) + r"|بـ|ب|b|be|bi|for)"
                        + NO_LETTER_AFTER + r"[ \t]*[:=]?[ \t]*$", re.IGNORECASE)
# حساب is a price word (الحساب 1450 جنيه is the bill), so an account number needs its own cue:
# رقم الحساب, the bank account, IBAN, account no, rakam el 7esab. A number after one is never an amount.
ACCOUNT_WORDS = (r"(?:و|ف|ب)?رقم\s+(?:ال)?(?:حساب|[اأ]كونت|محفظ[ةه]|كارت|بطاق[ةه]|فيزا)(?:ي|ى|ك|ه|ها|نا)?"
                 r"|(?:و|ف|ب)?(?:ال)?حساب(?:ي|ى|ك|ه|نا)?\s+(?:ال)?بنك(?:ي|ى)|(?:و|ف|ب)?(?:ال)?[اأآإ]يبان"
                 r"|(?:bank\s+)?(?:account|acct|acc|a/c)(?:\s*(?:number|no\.?|num|nr|#))?|ac\s*(?:number|no\.?|num|nr|#)"
                 r"|iban|(?:rakam|ra2am|rqm|rkm)\s+(?:el\s?)?[7h][ea]?sab\w*")
# possessive (*+), so the two runs of signs around the filler never split one run: linear time.
# The words end at a word end, or the run eats the start of a name it cannot give back (هيثم)
ACCOUNT_MID = r"(?:\s*(?:(?:number|no\.?|num|nr|is|هو|هي)(?![^\W\d_])|:|：|#|=|-|\())*+"
# the number may have a letter right after it (1234567جنيه): the greedy run already took every digit
ACCOUNT_NUMBER = re.compile(LETTER_BEFORE + r"(?:" + ACCOUNT_WORDS + r")" + NO_LETTER_AFTER + ACCOUNT_MID
                            + r"(?:\s+[^\W\d_]+){0,3}?" + ACCOUNT_MID
                            + r"\s*(?P<n>(?:[A-Za-z]{2}[ \t]?)?\d(?:(?:[\W_]{0,5}|[ \t]*و[ \t]*)\d){3,})",
                            re.IGNORECASE)


def _letter_o(m):
    return "[phone]" if sum(ch.isdigit() for ch in m.group(0)) >= 5 else m.group(0)


def _spread(m):
    """[number], except a sum with a currency right after it (1450 + 90 = 1540 جنيه) or with = and
    + × or * in it (1450 + 60 = 1510, 2*1450=2900): up to 11 digits, not shaped like a phone
    (1 and 0 1 2 or 5 then 8 digits, 0 and 9 or 10 digits, 20 or 00 first, or a +)."""
    run = m.group(0)
    digits = re.sub(r"\D", "", run)
    if run.startswith("+") or len(digits) > 11 or PHONE_SHAPE.fullmatch(digits):
        return "[number]"
    if MONEY_NEXT.match(m.string, m.end()) or "=" in run and SUM_SIGN.search(run):
        return run
    return "[number]"


def _price_before(text, start):
    return bool(CUE_BEFORE.search(text, max(0, start - 40), start))


def _bare5(m):
    if MONEY_NEXT.match(m.string, m.end()) or _price_before(m.string, m.start()):
        return m.group(0)  # an amount: السعر 12500, 12500 جنيه
    return "[number]"


# ---- 5. handles with no @

UNDERSCORE = re.compile(r"(?<![\w.@])(?=\w*[^\W\d_])\w+(?:_\w*)+")
LETTER_DIGITS = re.compile(r"(?<![\w.@])(?P<w>[A-Za-z][A-Za-z_]{2,})\d{2,}(?!\w)")
DOTTED = re.compile(r"(?<![\w.@])(?=[\w.]*[^\W\d_])\w+(?:\.\w+){2,}(?![\w.]*\w)"
                    r"|(?<![\w.@])[^\W\d_]{3}\w*\.\w*\d\w*(?!\.?\w)")  # {3} not {3,}: linear on a long word
NAME_DIGITS = re.compile(r"(?<![\w.@])(?P<w>[A-Za-z]{2,15})\d{1,4}(?!\w)")
CURRENCY_WORD = re.compile(send_check.CURRENCY, re.IGNORECASE)


def _letter_digits(m):
    w = m.group("w")
    if is_stop(w) or CURRENCY_WORD.fullmatch(w) or send_check.PRICE_WORD.fullmatch(w):
        return m.group(0)  # size42, EGP1450
    return "[user]"


def _name_digits(m):
    return "[user]" if is_listed(m.group("w")) else m.group(0)


# ---- 6. orders

HASH_ORDER = re.compile(r"#\s*(?:[A-Za-z]{1,5}[-_]?)?\d{1,12}(?!\w)")
ORDER_WORDS = (r"(?:orders?|ordr|(?:el\s?)?order|talab|el\s?talab|tracking|shipment|awb"
               r"|(?:و|ف|ب|ل)?(?:ال)?(?:[اأ]وردر(?:ي|ك)?|طلب(?:ي|ك|ية|يه)?|شحن[ةه]|بوليص[ةه]))")
# signs between an order word and its number: , ، - / " ( ) and the like (الاوردر بتاعي، 1045)
ORDER_MID = r"(?:\s*(?:number|no\.?|num|nr|رقم(?:ه|ها)?|برقم|rakam|ra2am|is|[:#(),،\-/\"'“”]))*+"
# up to 8 filler words, a word or 1 or 2 digits before a time word (الاوردر بتاعي من 3 ايام 1045),
# with spaces or signs between them (my order (from yesterday) 1045)
ORDER_WORD = r"(?:[^\W\d_]+|\d{1,2}(?=\s+(?:يوم|يومين|[اأ]يام|[اأ]سبوع|ساع[ةه]|days?|weeks?|hours?)\b))"
ORDER_FILL = ORDER_WORD + r"(?:[\s,،\-\"'“”()]+" + ORDER_WORD + r"){0,7}?"
ORDER_NUMBER = re.compile(LETTER_BEFORE + ORDER_WORDS + NO_LETTER_AFTER + ORDER_MID
                          + r"(?:\s*(?P<fill>" + ORDER_FILL + r")" + ORDER_MID + r")?"
                          + r"\s*(?P<n>(?:[A-Za-z]{1,5}-?)?\d{3,12})(?!\w|[.,]\d)", re.IGNORECASE)
ORDER_BEFORE = re.compile(r"(?<![\w.,])(?P<n>\d{3,12})(?!\w|[.,]\d)[,،:\-]?(?P<fill>(?:\s+[^\W\d_]+){0,3}?)\s+"
                          + ORDER_WORDS + NO_LETTER_AFTER, re.IGNORECASE)
SIZE_WORD = re.compile(r"(?:size|sizes|eu|ma2as|(?:ب|ال|بال)?مقاس(?:ه|ها|ك|ات)?)", re.IGNORECASE)
WEAK_PRICE = frozenset({"ب", "b", "be", "bi", "for", "at", "only", "just", "بس"})


def _money_word(w):
    return bool(send_check.PRICE_WORD.fullmatch(w) or SIZE_WORD.fullmatch(w) or fold(w) in WEAK_PRICE)


def _order(m):
    if hist.MONEY_AFTER.match(m.string, m.end()) or any(map(_money_word, re.findall(r"\w+", m.group("fill") or ""))):
        return m.group(0)  # an amount after an order word: الطلب 850 جنيه
    return m.group(0)[:m.start("n") - m.start()] + "[order]"


def _order_before(m):
    if hist.MONEY_AFTER.match(m.string, m.end("n")) or any(map(_money_word, m.group("fill").split())) \
            or _price_before(m.string, m.start("n")):
        return m.group(0)
    return "[order]" + m.group(0)[m.end("n") - m.start():]


# ---- 7. names

# الاسم: X, الاسم - X, الاسم/ X, name | X, الاسم = X, الاسم .. X, الاسم ، X, الاسم: (person emoji) X
CUE_SEP = r"(?:[:：\-/|=،‐-―−]|\.{2,3}|" + send_check.EMOJI.pattern + r")"
CUE_WORDS = (r"[اإ]سم(?:[يى]|ه|ها)|ال[اإ]سم|[اإ]سم\s+(?:المستلم|العميل|صاحب\s+(?:ال)?(?:طلب|[اأ]وردر))|(?:ال)?مستلم"
             r"|[اإ]سم(?=[ \t]*" + CUE_SEP + r")"
             r"|ب[اإ]سم|my\s+name\s+is|my\s+name's|(?:his|her)\s+name\s+is|(?:full\s+)?name(?=[ \t]*" + CUE_SEP + r")"
             r"|full\s+name|recipient(?:\s+name)?(?=[ \t]*" + CUE_SEP + r")|recipient\s+is|esm[yi]|ism[yi]|esmo"
             r"|esmaha|el\s?esm|b(?:e|i)?\s?esm(?!\s+(?:allah|alla|el\s?lah)(?!\w))|esm\s+el\s?mostalem"
             # at a line's start with no sign: Name Zorvex (a capital after name), recipient zorvex
             r"|(?<![^\n])[ \t]*(?:(?:full\s+)?name(?=[ \t]+(?-i:[A-Z]))|recipient(?=[ \t]+\w))")
NAME_CUE = re.compile(r"(?<!\w)(?P<cue>" + CUE_WORDS + r")(?:[ \t]+(?:بالكامل|كامل|الكامل|ثلاثي|التلاتي|الثلاثي"
                      r"|رباعي|kamel|full))?(?P<sep>(?:[ \t]*" + CUE_SEP + r"){0,3}[ \t]*(?:\n[ \t]*){0,2})"
                      r"(?P<rest>[^\W\d_]+(?:[ \t]+[^\W\d_]+){0,2})", re.IGNORECASE)


def _cue_word(w):
    """A word taken as a name after a strong cue (اسمي, باسم, my name is)."""
    if is_listed(w):
        return True
    f = fold(w)
    return len(f) >= 2 and not is_stop(w) and not verb_shaped(f) and f not in LATIN_FORMS


def _name_cue(m):
    parts = re.split(r"([ \t]+)", m.group("rest"))
    take = 0
    for k, w in enumerate(parts[::2]):
        if not _cue_word(w):
            break
        take = k + 1
    if not take:
        return m.group(0)
    return m.group(0)[:m.start("rest") - m.start()] + "[name]" + "".join(parts[2 * take - 1:])


TOKEN = re.compile(r"\[\w+\]|\w+(?:['’]\w+)?")
JOINED = re.compile(r"(يا|و|ف|ب|ل)(\w{2,})$")
FRANCO_AR = re.compile(r"[2357-9][ء-ي]{2,}")  # a nickname with a Franco digit in Arabic letters: يا7ودة
COMPOUND = re.compile(r"(?<!\w)(?P<p>و|ف|ب|ل|يا)?عبد(?:\s*ال\w{2,}|\s+رب\w*)"
                      r"|(?<!\w)3?abd(?:[\s\-]?(?:el|al|ul|ol))?[\s\-]?[a-z]{3,}(?!\w)", re.IGNORECASE)
# Words never masked as a name, even when a sender's name holds them: function words, shop
# words, and our own placeholder words, so "[link]" never turns into "[[name]]".
COMMON = frozenset(fold(w) for w in (
    "the", "and", "for", "you", "our", "with", "from", "this", "that", "shop", "store", "official", "online", "team",
    "page", "sport", "sports", "egypt", "الله", "على", "الى", "إلى", "محل", "متجر", "ستور", *KINDS))

_SKEL_AR = {**dict.fromkeys("ب", "b"), **dict.fromkeys("تطث", "t"), **dict.fromkeys("جغ", "g"),
            **dict.fromkeys("خقك", "k"), **dict.fromkeys("دض", "d"), **dict.fromkeys("ذزظ", "z"),
            **dict.fromkeys("سص", "s"), "ش": "S", "ف": "f", "ل": "l", "م": "m", "ن": "n", "ر": "r"}
_SKEL_LA = (("sh", "S"), ("ch", "S"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"), ("ph", "f"), ("ck", "k"))
_SKEL_ONE = {**dict.fromkeys("aeiouywh2378", ""), "c": "k", "q": "k", "j": "g", "p": "b", "v": "f", "5": "k",
             "8": "g", "9": "k", "6": "t"}


def skeleton(word):
    """A word's consonants, the same for its Arabic and its Latin spelling: مرزوق and marzouk
    are both mrzk. Vowels, ع, ح, ه and the Franco 2 3 7 drop out; doubles count once."""
    if ARABIC.search(word):
        out = "".join(_SKEL_AR.get(ch, "") for ch in word)
    else:
        w = word.casefold()
        for a, b in _SKEL_LA:
            w = w.replace(a, b)
        out = "".join(_SKEL_ONE.get(ch, ch) if ch.isalnum() else "" for ch in w)
    return re.sub(r"(.)\1+", r"\1", out)


def _script(word):
    return "ar" if ARABIC.search(word) else "la"


def _franco(word):
    return bool(re.search(r"[A-Za-z]", word)) and bool(re.search(r"[235789]", word))


def _name_words(name):
    return [t for t in re.findall(r"\w+", normalize(name)) if not t.isdigit()]


class Display:
    """The chat's own sender names, word by word, in any of their forms: folded (أحمد and احمد
    as one), joined to و ف ب ل يا, two words typed as one (كريمفوزي), and Arabic typed for a
    Latin name or back (skeleton of 3 letters or more)."""

    def __init__(self, names=()):
        self.words, self.joined, self.skel = set(), set(), {}
        for name in names:
            toks = _name_words(name)
            keep = [t for t in toks if fold(t) not in COMMON]
            for t in keep:
                if len(t) >= 3 or len(toks) == 1 and len(t) >= 2:
                    self.words.add(fold(t))
                    s = skeleton(t)
                    if len(s) >= 3:
                        self.skel.setdefault(s, set()).add(_script(t))
            for a, b in zip(keep, keep[1:]):
                self.joined.add(fold(a + b))

    def hit(self, w):
        """The prefix kept before [name] ("" for none), or None when w is no sender word."""
        f = fold(w)
        if f in self.words or f in self.joined:
            return ""
        m = JOINED.match(f)
        if m and not m.group(2).startswith("ال") and m.group(2) in self.words:
            return w[:len(m.group(1))]
        s = skeleton(w) if len(w) >= 3 else ""
        if s in self.skel and (self.skel[s] - {_script(w)} or _franco(w)):
            return ""
        return None

    def __call__(self, text):
        if not (self.words or self.joined):
            return text
        out, last = [], 0
        for m in TOKEN.finditer(text):
            w = m.group(0)
            if w.startswith("["):
                continue
            p = self.hit(w)
            if p is not None:
                out += [text[last:m.start()], p + "[name]"]
                last = m.end()
        return "".join(out) + text[last:]


# ---- 8. places

CITIES = (
    "مدينة نصر", "مصر الجديدة", "المعادي", "المهندسين", "الدقي", "العجوزة", "الهرم", "فيصل", "إمبابة", "شبرا",
    "شبرا الخيمة", "حلوان", "المقطم", "عين شمس", "المطرية", "المرج", "النزهة", "التجمع", "التجمع الخامس",
    "القاهرة الجديدة", "الرحاب", "مدينتي", "الشروق", "العبور", "6 أكتوبر", "السادس من أكتوبر", "الشيخ زايد",
    "حدائق الأهرام", "العاشر من رمضان", "المنصورة", "طنطا", "المحلة", "المحلة الكبرى", "الزقازيق", "بنها",
    "شبين الكوم", "دمنهور", "كفر الدوار", "الغردقة", "شرم الشيخ", "العريش", "مرسى علم", "العلمين",
    "الساحل الشمالي", "سيدي جابر", "العجمي", "المنتزه", "محرم بك", "ميامي",
    "حدائق القبة", "ميت غمر", "بلبيس", "دسوق", "العاشر", "زهراء المعادي", "دجلة", "سيتي ستارز", "مول العرب",
    "مول مصر", "عباس العقاد", "مكرم عبيد", "التسعين الشمالي", "التسعين الجنوبي", "صلاح سالم", "المنيب",
    "السيدة زينب", "العباسية", "حلمية الزيتون", "حدائق المعادي", "دار السلام", "المعصرة", "طره", "بولاق",
    "بولاق الدكرور", "الوراق", "المنيل", "جاردن سيتي", "وسط البلد", "عابدين", "روض الفرج", "القطامية",
    "مصر القديمة", "شبرا مصر", "القناطر", "قليوب", "الخانكة", "مدينة بدر", "العاصمة الإدارية", "التجمع الأول",
    "التجمع الثالث", "النرجس", "اللوتس", "الأندلس", "الحوامدية", "البدرشين", "كرداسة", "أوسيم", "ناهيا",
    "حدائق أكتوبر", "أبو رواش", "دريم لاند", "سيدي بشر", "سان ستيفانو", "ستانلي", "لوران", "جليم", "رشدي",
    "كليوباترا", "سبورتنج", "الإبراهيمية", "الشاطبي", "المندرة", "العصافرة", "المعمورة", "أبو قير", "العامرية",
    "برج العرب", "الدخيلة", "المكس", "كرموز", "المنشية", "الأنفوشي", "فلمنج", "بولكلي", "زيزينيا", "محطة الرمل",
    "طلخا", "السنبلاوين", "المنزلة", "دكرنس", "شربين", "بلقاس", "منية النصر", "فاقوس", "أبو حماد",
    "منيا القمح", "ههيا", "ديرب نجم", "أبو كبير", "قويسنا", "منوف", "أشمون", "مدينة السادات", "الباجور",
    "كفر الزيات", "زفتى", "السنطة", "سمنود", "بسيون", "رشيد", "إدكو", "كوم حمادة", "إيتاي البارود",
    "وادي النطرون", "رأس البر", "فارسكور", "ملوي", "مغاغة", "بني مزار", "سمالوط", "أبو قرقاص", "ديروط",
    "منفلوط", "أبنوب", "طهطا", "جرجا", "أخميم", "البلينا", "نجع حمادي", "إسنا", "إدفو", "كوم أمبو",
    "nasr city", "madinet nasr", "heliopolis", "masr el gedida", "masr elgedida", "maadi", "el maadi",
    "mohandessin", "mohandeseen", "dokki", "agouza", "el haram", "faisal", "imbaba", "shubra", "shoubra", "helwan",
    "mokattam", "mo2attam", "ain shams", "3ein shams", "matareya", "nozha", "tagamo3", "el tagamo3", "tagamoa",
    "fifth settlement", "new cairo", "rehab", "el rehab", "madinaty", "shorouk", "el shorouk", "obour", "el obour",
    "6 october", "6th of october", "october city", "sheikh zayed", "el sheikh zayed", "zayed", "10th of ramadan",
    "mansoura", "el mansoura", "tanta", "mahalla", "el mahalla", "zagazig", "banha", "benha", "shebin",
    "damanhour", "hurghada", "ghardaqa", "el ghardaqa", "sharm", "sharm el sheikh", "arish", "el arish",
    "marsa alam", "alamein", "el alamein", "sahel", "north coast", "sidi gaber", "agami", "montaza", "miami",
    "ma3adi", "el ma3adi", "zahraa el maadi", "zahraa el ma3adi", "degla", "city stars", "mall of arabia",
    "mall of egypt", "cairo festival city", "festival city", "hadayek el kobba", "7adayek el kobba", "mit ghamr",
    "belbeis", "desouk", "el 3ashir", "abbas el akkad", "3abbas el 3akkad", "makram ebeid", "salah salem",
    "sidi bishr", "san stefano", "stanley", "gleem", "roushdy", "sporting", "garden city", "wust el balad",
    "abbassia", "manial", "el manial", "sayeda zeinab", "mounib", "katameya", "new capital", "beverly hills",
    "dreamland", "hadayek october", "zahraa",
)
_AR_PREFIX = r"(?:[وف]?(?:بال|لل|ال|ب|ل)?)"


def _arabic_place(s):
    stem = " ".join(s.split())
    stem = stem[2:] if stem.startswith("ال") else stem
    out = []
    for ch in stem:
        out.append("[اأإآ]" if ch in "اأإآ" else "[ةه]" if ch in "ةه" else "[يى]" if ch in "يى"
                   else r"\s+" if ch == " " else re.escape(ch))
    return _AR_PREFIX + "".join(out)


def _latin_place(s):
    return r"[\s\-]+".join(re.escape(w) for w in s.split())


@lru_cache(maxsize=1)
def places():
    """One pattern for every governorate spelling and every city above, longest first."""
    data = json.loads(GOVERNORATES.read_text(encoding="utf-8"))
    names = set(CITIES)
    for g in data["governorates"]:
        names |= {g["name"], g["name_ar"], *g["spellings"]}
    parts = []
    for s in sorted(names, key=lambda s: (-len(s), s)):
        parts.append(_arabic_place(s) if send_check.ARABIC.search(s) else _latin_place(s))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


def short_place(text):
    """True for a short message that is a place and a few words: عباس العقاد [place]."""
    if "[place]" not in text or QUESTION.search(text) or re.search(r"\d", text):
        return False
    rest = [w for w in TOKEN.findall(text) if not w.startswith("[")]
    return len(rest) <= 4 and not any(map(is_stop, rest))


# ---- 9. calls by name and listed names

LATIN_CALL = re.compile(r"(?<![\w.])(?P<cue>ya|hi|hey|hello|dear|thanks|thank\s+you|thx|thnx|thanx|tnx)[ \t]+"
                        r"(?P<w>(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{2,20})(?!\w)", re.IGNORECASE)
GREETINGS = frozenset({"hi", "hey", "hello", "dear", "thanks", "thank you", "thx", "thnx", "thanx", "tnx"})
LATIN_FORMS = frozenset({
    "fandem", "afandem", "fendem", "basha", "bashmohandes", "habibi", "habibti", "man", "bro", "sir", "madam",
    "madame", "gama3a", "gma3a", "gam3a", "kbeer", "kebir", "rayes", "captain", "kaptin", "ostaz", "ostaza",
    "doctor", "team", "all", "everyone", "guys", "there", "friend", "friends", "dear", "rab", "rabb", "reet",
    "salam", "gamil", "gamila", "sweet", "love", "boss", "chief", "king", "queen", "hader", "khabar", "sater",
    "satar", "alby", "albi", "baby", "prince", "shabab", "regala", "banat", "beh", "bey", "hanem", "mister",
    "engineer", "mohandes", "mohandesa", "hag", "hagga", "sit", "sitt", "set", "om", "abu", "abo", "lahwy",
    "lahwi", "salaam", "good", "so", "very", "again", "for", "you", "a", "lot", "much", "and",
})


def _latin_call(m):
    cue, word = " ".join(m.group("cue").casefold().split()), m.group("w")
    f = fold(word)
    if f in LATIN_FORMS or f in W.TITLES or is_stop(word) and not is_listed(word):
        return m.group(0)  # a form of address, or a title the title rule reads: Dear Mr Smith
    if cue in GREETINGS and not word[0].isupper() and not is_listed(word):
        return m.group(0)
    return m.group(0)[:m.start("w") - m.start()] + "[name]"


def _ya(m):
    return m.group(0)[:m.start(1) - m.start()] + "[name]" if hist._name_like(m.group(1)) else m.group(0)


# English titles that only ever come before a name: a lower case or Arabic word after them is a
# name too (dr zorvex, mr زوزو, dr zorvex's, mr zorvex2). coach, captain, doctor and eng still need
# a list or capital name (the coach said); miss is a verb too (don't miss our new collection).
HONORIFICS = frozenset("mr mrs ms mister dr madam madame".split())


def _after_title(title, w):
    f, t = fold(w), fold(title)
    if w.startswith("[") or f in LATIN_FORMS:
        return False
    if is_listed(w) or latin_capital(w):
        return True
    if ARABIC.search(t):  # after an Arabic title a name that is also a common word is a name: مدام منى
        return arabic_name_like(w) or (f in W.CUE and f != "ايه") or (
            bool(ARABIC.search(w)) and f.startswith("ال") and is_listed(w[2:]))
    if t in HONORIFICS:
        core = re.sub(r"(?:['’]s|\d{1,4})$", "", w)
        return latin_name_like(core) or arabic_name_like(core)
    return t not in W.LATIN_ENGLISH_TITLES and not is_stop(w) and w.isascii()


def latin_name_like(word):
    """A lower case Latin word that can be a name: 3 letters or more, no stop word, no form of
    address or title (deliver to zorvex; not deliver to me, the office)."""
    f = fold(word)
    return word.isascii() and word.isalpha() and len(word) >= 3 and not is_stop(word) \
        and f not in LATIN_FORMS and f not in W.TITLES


def _weak_ok(w):
    return is_listed(w, weak=True) or latin_capital(w)


def _relation_ok(w):
    return is_listed(w) or latin_capital(w) or arabic_name_like(w)


def _delivery_ok(w):  # deliver to zorvex, ship it to Zorvex
    return _relation_ok(w) or latin_name_like(w)


def _chained(w):
    """A word taken right after a [name]: listed, capitalised Latin or name-like Arabic."""
    return not w.startswith("[") and (is_listed(w) or latin_capital(w) or arabic_name_like(w))


def _cue_names(text):
    """Step 9 after يا and hi: titles, weak and relation cues, a lone ل, listed first names,
    then up to 2 name-like words after any [name]."""
    toks = [(m.start(), m.end(), m.group(0)) for m in TOKEN.finditer(text)]
    if not toks:
        return text
    n = len(toks)
    words = [t[2] for t in toks]
    folded = [fold(w) for w in words]
    gaps = [""] + [text[toks[i - 1][1]:toks[i][0]] for i in range(1, n)]
    spaced = [bool(re.fullmatch(r"[ \t]+", g)) for g in gaps]
    loose = [bool(re.fullmatch(r"[ \t]*[,،]?[ \t]+|\.[ \t]*", g)) for g in gaps]  # mr.zorvex too
    # after deliver to: a colon or a new line too (deliver to: zorvex, deliver to\nzorvex)
    deliv = [bool(re.fullmatch(r"[ \t]*[,،:：]?[ \t]*\n?[ \t]*|\.[ \t]*", g)) and g != "" for g in gaps]
    mask, prefix = set(), {}

    def take(j, ok, gap=spaced):
        if j < n and gap[j] and not words[j].startswith("[") and ok(words[j]):
            mask.add(j)
            return True
        return False

    for i, w in enumerate(words):
        f = folded[i]
        if w.startswith("["):
            continue
        if f in W.FIRST:
            mask.add(i)
            continue
        jm = JOINED.match(f)
        if jm and not jm.group(2).startswith("ال") and len(jm.group(2)) >= 3 and (
                jm.group(2) in W.FIRST or jm.group(1) == "يا" and (
                    jm.group(2) in W.CUE or FRANCO_AR.fullmatch(jm.group(2)))):
            mask.add(i)
            prefix[i] = w[:len(jm.group(1))]
            continue
        if jm and jm.group(1) == "ل" and i and spaced[i] and folded[i - 1] in W.DELIVERY_VERBS \
                and jm.group(2) not in W.NOT_WEAK and arabic_name_like(jm.group(2)):  # ابعتها لزوزو
            mask.add(i)
            prefix[i] = w[:1]
            continue
        if f in W.TITLES or f.startswith("يا") and f[2:] in W.TITLES:  # ياعم زوزو
            take(i + 1, lambda x, t=w: _after_title(t, x), loose)
        elif f in W.WEAK:
            take(i + 1, _weak_ok, loose)
        elif f in W.RELATION:
            take(i + 1, _relation_ok)
        elif f in W.DETACHED:  # ابعتها لـ زوزو
            take(i + 1, lambda x: _weak_ok(x) or arabic_name_like(x) or latin_name_like(x))
        for pair in W.WEAK_PAIRS + W.RELATION_PAIRS + W.DELIVERY_PAIRS:
            k = len(pair)
            if k > 1 and tuple(folded[i:i + k]) == pair and all(spaced[i + 1:i + k]):
                if pair in W.DELIVERY_PAIRS:
                    take(i + k, _delivery_ok, deliv)
                else:
                    take(i + k, _weak_ok if pair in W.WEAK_PAIRS else _relation_ok, loose)
    for i in range(n):  # the chain: up to 2 words after a [name], over spaces only
        if i in mask or words[i] == "[name]":
            for j in (i + 1, i + 2):
                if not take(j, _chained):
                    break
    if not mask:
        return text
    out, last = [], 0
    for i in sorted(mask):
        out += [text[last:toks[i][0]], prefix.get(i, "") + "[name]"]
        last = toks[i][1]
    return "".join(out) + text[last:]


def has_name(text):
    """True when a listed first name is still in the text (a gate for card examples)."""
    for w in TOKEN.findall(normalize(text)):
        f = fold(w)
        m = JOINED.match(f)
        if f in W.FIRST or m and not m.group(2).startswith("ال") and m.group(2) in W.FIRST:
            return True
    return False


# ---- the cleaner

ASKS_NAME = re.compile(r"(?<!\w)(?:[اإ]سم\s+حضرتك|[اإ]سمك|ال[اإ]سم\s*[؟?]|ال[اإ]سم\s+(?:[اإ]يه|ايه)|ابعت(?:لي|يلي)?\s+"
                       r"(?:ال)?[اإ]سم|باسم\s+(?:مين|حضرتك)|your\s+name|esmak|esmek|esm\s+7adretak|name\s+please"
                       r"|مين\s+معايا|[اأ]تشرف\s+بمين|[اأ]تشرف\s+باسم|who\s+(?:am\s+i|is\s+this|are\s+you)\b)",
                       re.IGNORECASE)
# a name word in a store line that asks: with a question mark, a request word (ممكن, لو سمحت,
# ابعت, محتاج, please) or a form word (بالكامل, الثلاثي, والعنوان, and address), or alone
NAME_WORD = re.compile(r"(?<!\w)(?:[وفب]?(?:ال)?[اإ]سم(?:ه|ها)?|[اأ]سامي|(?:full\s+)?names?|esm|el\s?esm)(?!\w)",
                       re.IGNORECASE)
NAME_ASK = re.compile(r"[?؟]|(?<!\w)(?:ممكن|لو\s*سمحت|ابعت\w*|اكتب\w*|محتاج\w*|[اأ]حتاج|عايز\w*|عاوز\w*|بالكامل|كامل"
                      r"|ثلاثي|الثلاثي|التلاتي|رباعي|الكريم|و?العنوان|please|pls|plz|send|need|and\s+address"
                      r"|momken|law\s+sama7t|ebaat\w*|eb3at\w*)(?!\w)", re.IGNORECASE)
# a short store line while the customer is still typing: it keeps the name window open
MARKER = re.compile(r"<[^<>\n]{1,200}>|(?:تم\s+)?حذف\s+هذه\s+الرسال[ةه]|لقد\s+حذفت\s+هذه\s+الرسال[ةه]")


def asks_name(plain):
    """True when a store line asks the customer's name (opens the name window)."""
    if ASKS_NAME.search(plain):
        return True
    return bool(NAME_WORD.search(plain)) and (bool(NAME_ASK.search(plain)) or len(TOKEN.findall(plain)) <= 2)


def is_ack(plain):
    """A short store line that moves nothing on: 3 words or fewer and no question (تمام, a thumbs up,
    ok, منتظرك), or an export's media or deleted message line in any language (<...>)."""
    s = plain.strip()
    if MARKER.fullmatch(s) or hist.SYSTEM.match(s) or hist.media_kind(s):
        return True
    return len(TOKEN.findall(s)) <= 3 and not QUESTION.search(s)
ASKS_ADDRESS = re.compile(r"(?<!\w)(?:(?:ابعت|ابعتي|ابعتلي|ابعتيلي|اكتب|اكتبي|اكتبلي|محتاج|محتاجين|عايزين|ممكن)"
                          r"(?:\s+\S+){0,2}?\s+(?:و|ف)?(?:ال)?(?:عنوان|لوكيشن)|عنوانك|عنوان\s+حضرتك"
                          r"|your\s+(?:full\s+)?address|send\s+(?:me\s+|us\s+)?(?:your|the)\s+(?:location|address)"
                          r"|3[ae]nwanak|3[ae]nwanek|el\s?3[ae]nwan)", re.IGNORECASE)


class Cleaner:
    """Built once for an import from every sender's display name: a full name (two words or
    more) is masked wherever it is typed, in any chat. Each chat then gets its own
    ChatCleaner (cleaner.chat) with its own senders' names and Instagram username."""

    def __init__(self, names=()):
        self.full, self.skel = set(), {}
        for name in names:
            toks = _name_words(name)
            if not 2 <= len(toks) <= 6:
                continue
            self.full.add(tuple(map(fold, toks)))
            sk = tuple(map(skeleton, toks))
            if all(len(s) >= 2 for s in sk) and len("".join(sk)) >= 5:
                self.skel.setdefault(sk, set()).add(_script(toks[0]))
        self.longest = max(map(len, self.full), default=0)

    def chat(self, names=(), usernames=()):
        return ChatCleaner(self, names, usernames)

    def _full_hit(self, words):
        """(how many words, joined prefix) for a full name at the start of words, or (0, "")."""
        for n in range(min(self.longest, len(words)), 1, -1):
            got = words[:n]
            if any(w.startswith("[") for w in got):
                continue
            key = tuple(map(fold, got))
            if key in self.full:
                return n, ""
            m = JOINED.match(key[0])  # typed joined to يا, و, ف, ب or ل: لسلمى تجربة
            if m and (m.group(2), *key[1:]) in self.full:
                return n, got[0][:len(m.group(1))]
            sk = tuple(map(skeleton, got))
            scripts = self.skel.get(sk)
            if scripts and (scripts - {_script(got[0])} or _franco(got[0])):
                return n, ""
        return 0, ""

    def full_names(self, text):
        if not self.full:
            return text
        toks = [(m.start(), m.end(), m.group(0)) for m in TOKEN.finditer(text)]
        words = [t[2] for t in toks]
        out, last, i = [], 0, 0
        while i < len(toks):
            hit, joined = self._full_hit(words[i:])
            if hit:
                out += [text[last:toks[i][0]], joined + "[name]"]
                last, i = toks[i + hit - 1][1], i + hit
            else:
                i += 1
        return "".join(out) + text[last:]


def _without_common(name):
    return " ".join(w for w in re.findall(r"\w+", hist.name_key(normalize(name))) if fold(w) not in COMMON)


class ChatCleaner:
    """Cleans the messages of one chat (the steps in the module notes)."""

    def __init__(self, parent, names=(), usernames=()):
        self.parent = parent
        self.masker = hist.Masker([n for n in map(_without_common, names) if n])
        self.display = Display(names)
        users = sorted({normalize(u) for u in usernames if isinstance(u, str) and len(u) >= 3}, key=len, reverse=True)
        self.users = re.compile(r"(?<![\w.])@?(?:" + "|".join(map(re.escape, users)) + r")(?![\w])",
                                re.IGNORECASE) if users else None

    def __call__(self, text):
        if not isinstance(text, str) or not text:
            return ""
        text = normalize(text)
        if "@" in text:
            text = hist.EMAIL.sub("[email]", text)
            text = SPACED_EMAIL.sub("[email]", text)
        text = OBF_EMAIL.sub("[email]", text)
        text = AT_USER.sub("[user]", text)
        text = TRAILING_AT.sub("[user]", text)
        text = LEFTOVER_AT.sub("[user]", text)
        text = LINK.sub("[link]", text)
        text = USER.sub("[user]", text)
        if self.users is not None:
            text = self.users.sub("[user]", text)
        text = HANDLE_CUE.sub(_handle, text)
        if gives_address(text):
            return "[address]"
        text = PHONE_WIDE.sub("[phone]", text)
        text = LETTER_O_PHONE.sub(_letter_o, text)
        text = ACCOUNT_NUMBER.sub(lambda m: m.group(0)[:m.start("n") - m.start()] + "[number]", text)
        text = SPREAD_NUMBER.sub(_spread, text)
        text = BARE5.sub(_bare5, text)
        text = UNDERSCORE.sub("[user]", text)
        text = LETTER_DIGITS.sub(_letter_digits, text)
        text = DOTTED.sub("[user]", text)
        text = NAME_DIGITS.sub(_name_digits, text)
        text = HASH_ORDER.sub("[order]", text)
        text = ORDER_NUMBER.sub(_order, text)
        text = ORDER_BEFORE.sub(_order_before, text)
        text = NAME_CUE.sub(_name_cue, text)
        text = self.parent.full_names(text)
        text = self.masker(text)
        text = self.display(text)
        text = COMPOUND.sub(lambda m: (m.group("p") or "") + "[name]", text)
        text = places().sub("[place]", text)
        if short_place(text):
            return "[address]"
        text = hist.YA.sub(_ya, text)
        text = LATIN_CALL.sub(_latin_call, text)
        text = _cue_names(text)
        return RUN.sub(r"[\1]", text)

    def texts(self, messages):
        """The cleaned text of each message of one chat ("" for none), with the chat-level rules
        in the module notes: the answer to the name question, and the address window."""
        out, ask_name, window = [], False, False
        for m in messages:
            if not m.text:
                out.append("")
                continue
            if m.team:
                plain = normalize(m.text)
                asks, address = asks_name(plain), bool(ASKS_ADDRESS.search(plain))
                if ask_name and not asks and not address and is_ack(plain):
                    pass  # تمام while the customer is still typing the name: the window stays open
                else:
                    ask_name, window = asks, address
                out.append(self(m.text))
            elif window:  # the store asked name and address at once: the first answer is the name
                out.append("[name]" if ask_name else "[address]")
                ask_name = False
            elif ask_name:  # open up to the store's next message: لحظة, then the name
                out.append("[name]")
            else:
                got = self(m.text)
                window = got in ("[address]", "[place]")
                out.append(got)
        return out


def clean(text, names=(), usernames=()):
    """One text cleaned, with these sender names and usernames (an import builds one Cleaner)."""
    return Cleaner(names).chat(names, usernames)(text)
