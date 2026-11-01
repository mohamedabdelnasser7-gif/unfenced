"""The send check. Every reply passes it before it goes out, whatever the model decided.

check() returns (passed, feedback). The feedback is written for the model, so a
failed reply can be retried with it.

Rules (from the store rules, the 27 Oct morning review and Mohamed's calls on 28 Oct):
1. Script match: Arabic in, Arabic out; Franco in, Latin letters out; English in, English out.
2. Banned words: الجوز / el goz, مرتاح, sympathy lines.
3. Style: no em or en dashes, no hyphen with spaces used as a dash, no emoji, no markdown **.
4. Every number that reads as an amount must exist in the store or delivery data, or in
   this turn's store results. A number reads as an amount when it sits next to a currency
   word or sign, when it comes after a price word (سعر, بـ, price, costs, for, is and a few
   more) or right after a city or governorate (Cairo 70), or when it has 3 or more digits,
   all of them counted (1.500), with or without any word next to it (a bare 500, or 500
   days). Left out: sizes, size ranges, dates, times, order numbers (#D12 always; #1234 right
   after an order word, or in a sentence with no price word or currency; a line that ends in ":"
   reads on into the next line, and so does one that ends in a cue word when the next line starts
   with a number or #), a number right after
   an address word with no price word earlier in the sentence (عمارة 125, Building 125,
   3emara 125; an address label such as عنوان التوصيل or delivery address is not a price word), Egyptian mobile and landline numbers grouped as phones are written, any number with
   a + and 8 or more digits (+44 7700 900123), percentages, a number of 1 or 2 digits with a unit after it (2 days, 2 to 3 days), a weight
   of up to 3 digits in grams (150 grams, 150 جرام), and
   a year from 1900 to 2099 with a year word or a month right next to it (model 2026, the
   2026 model, سنة 2026, May 2026) or inside a date (28 Oct 2026). Any other year is an
   amount, so "Boots: 1999." is refused. After a weak word (is, for, ب), a catalogue size
   number (43) is read as a size unless a price word comes earlier in the sentence. Decimals
   count as written, so 16500.99 and 16500,99 are not 16500. An amount in words (next to a
   currency word, after a price word or ب, or 100 or more after any cue word), or with k or
   ألف after the digits (1k EGP, 1.5 ألف), is refused, so the model writes it in digits.
5. No exact stock count. The store tool gives a level (in stock, few left, out), never a number.
6. Links (2026-10-31): a reply may carry a link only when it is, exactly, an image link the store
   tool gave in this chat (links, from sales/loop.py store_links). Any other link is refused: a
   scheme link (https://...), a www. link, or a bare domain with a path or a common ending
   (shop.example/x, nike.com). An allowed link is read as no words and no numbers by the other rules,
   so its Latin letters and digits never fail the script or amount rules.
7. Model numbers (2026-11-01): a number of 1 or 2 digits in a product title right after its title
   word ("Phantom 6", "Vapor 17") is a model, not an amount or a stock count, so "Here is the Nike
   Phantom 6" passes (names, the store's product titles). A title word that is a price, cue, tier,
   place, size, address, unit, year, count or number word ("Total 90", "Pack of 3") is never a
   title word here. The number is dropped only where the reply plainly moves on (a blank then a
   word, an end mark then a blank, the line end). A price, currency or count after it still counts:
   "Vapor 17,500" and "Vapor 17 ,400" (blanks, a separator, a sign that looks like one, such as a low 9
   quote, or a narrow blank between digit groups are joined, so it reads 17400), "Vapor 17 EGP", "Vapor 17k",
   "Elite 17.5k" and "Only Vapor 17 are left" are refused; "Phantom 6 available" and "Superfly 11 in
   stock" stay a model.
   Moved here from arena/factcheck.py, its one home now.
8. Franco in an English reply (2026-11-01): an English reply is read leniently. Words that look like
   Franco but are not passed over: a title word with a digit ("F50"), title words in a run of two or
   more as the title has them ("El Ultimo Tango"), digits glued to a unit ("24h"), a clock time next
   to a time word ("at 9am"), a size code ("EU42"), and one run of digits inside a word ("VAP17"). A
   common Franco word counts each time it comes, and the Franco currency and mawgood words are common
   Franco words. The customer's line is read as written; when only those words make it
   read as Franco ("Do you have the F50?"), the reply may be English or Franco, Arabic letters refused.
"""
import functools
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation

# Arabic letters only: Arabic punctuation and digits do not count as a script.
ARABIC = re.compile(r"[\u0621-\u064A\u0671-\u06D3\u06FA-\u06FC\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFC]")
LATIN = re.compile(r"[A-Za-z]")
WORD = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
# Eastern digits, and the Arabic decimal and thousands signs (١٦٥٠٠٫٥٠ is 16500.50).
EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
# The Arabic comma between two digits is a thousands comma: 16،500 is 16,500 (red team round 2, R2-7)
ARABIC_COMMA_IN_NUMBER = re.compile(r"(?<=\d)" + "\N{ARABIC COMMA}" + r"(?=\d)")


def western_digits(text):
    """text with Eastern digits as Western ones, the Arabic decimal and thousands signs as . and ,
    and an Arabic comma between two digits as a thousands comma."""
    return ARABIC_COMMA_IN_NUMBER.sub(",", (text or "").translate(EASTERN_DIGITS))
# Signs that look like ":" or "=" read as them (fullwidth, small, modifier letter, ratio), and
# blanks that are neither Unicode spaces nor format characters read as a space when they show
# as a gap (Hangul fillers, Braille blank) or as nothing when they do not (combining grapheme
# joiner, variation selectors), red team t261028j round 3, item 4. Built from code points so
# the source stays plain.
LOOKALIKES = str.maketrans(
    {chr(c): ":" for c in (0xFF1A, 0xFE55, 0xFE13, 0xA789, 0x2236, 0x02D0, 0x02F8)}
    | {chr(c): "=" for c in (0xFF1D, 0xFE66, 0x207C, 0x208C)}
    | {chr(c): " " for c in (0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800)}
    | {chr(c): None for c in (0x034F, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F,
                              *range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0))})
# Signs that show as a comma, a dot or an apostrophe read as them in a number (low 9 quote, fullwidth,
# small and ideographic commas, one dot leader, middle dot, quote marks, primes and modifier letters), so
# "17" then one of them then "400" reads 17,400 like the plain sign (red team handoff round 2, item 1).
# Kept apart from LOOKALIKES, which arena/clean.py also reads for names.
NUMBER_LOOKALIKES = {
    **LOOKALIKES,
    **{c: "," for c in (0x201A, 0xFF0C, 0xFE50, 0xFE51, 0x3001, 0x060D)},
    **{c: "." for c in (0x2024, 0xFF0E, 0xFE52, 0x00B7, 0x2027, 0xA78F, 0x1427, 0x18DF, 0x0887, 0x0971)},
    **{c: "'" for c in (0xA78B, 0xA78C)},
    **{c: "'" for c in (0x2018, 0x201B, 0x2032, 0x2035, 0x02B9, 0x02BB, 0x02BC, 0x02BD, 0x00B4, 0xFF07,
                        0x275B, 0x275C)}}
# A modifier letter (Unicode Lm: the modifier vertical line U+02C8, the half rings, the Arabic tatweel and the
# rest), or any other letter or number sign that is neither Latin nor Arabic (a Lisu or Canadian syllabics
# mark, a superscript digit), between a digit and a group of 3 shows as a mark inside one number, so it reads
# as an apostrophe there and the groups join: "6", U+02C8, "400" reads 6400 (red team handoff round 3, item 2).
MODIFIER_IN_NUMBER = re.compile(
    r"(?<=\d)(?:[" + "".join(chr(c) for c in range(0x80, 0x10000) if unicodedata.category(chr(c)) == "Lm")
    + r"]|(?![a-zA-Z\u0600-\u06FF])[^\W\d_])(?=\d{3}(?!\d))")
# WhatsApp emphasis marks (_italic_, *bold*, ~strike~, `mono`). WhatsApp shows _500_ as 500.
EMPHASIS = re.compile(r"[_*~`]")
# Right after a separator an emphasis mark opens on the digits and shows as nothing: "17,_400_" shows 17,400
# (found by the round 3 sweep of a separator then a character).
EMPHASIS_IN_NUMBER = re.compile(r"(?<=[.,\u060c'\u2019])[_*~`]+(?=\d)")

# Franco: Egyptian Arabic in Latin letters, with 2 3 5 7 8 9 standing for Arabic sounds.
FRANCO_DIGIT_WORD = re.compile(r"\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*[235789])[a-z0-9]{2,}\b")
ORDINAL = re.compile(r"^\d+(st|nd|rd|th)$")
FRANCO_WORDS = {
    "ana", "enta", "enti", "ahlan", "momken", "bs", "bas", "keda", "kda", "ezay", "ezzay", "fe", "fi",
    "msh", "mesh", "mish", "ya", "el", "w", "wala", "aywa", "la2", "lw", "leh",
    "tamam", "khalas", "awi", "awy", "ba2a", "kman", "kaman", "delwa2ty", "dlw2ty", "bta3", "beta3",
    "3ayez", "3ayz", "3andena", "3ndena", "fein", "fen", "emta", "amta", "eih", "agib", "yom",
    # The Franco currency spellings (CURRENCY) and mawgood forms, so a Franco reply never reads as English
    # (review handoff round 2, minor 3).
    "geneh", "genih", "gneh", "gnih", "ginih", "gnyh", "gineh", "gineeh", "geneeh", "ginee",
    "mawgood", "mawgooda", "mawgoda", "mawgod", "mawgoud", "mawgouda", "mawgodin", "mawgodeen", "mawgoodin",
    "mawgoodeen", "mwgood", "mwgod",
}
# Shapes that look like a Franco digit word but are not, passed over when a reply is read leniently
# (looks_franco): one run of 2 or more digits inside a word (VAP17, EU42, 500egp, 48h), digits then a
# unit (2x, 3kg), a size or version code then a digit (uk8, x2). A clock time (9am, 3pm) is passed over
# only next to a time word ("at 9am", "9am to 5pm"): "ya 3am" is Franco (red team handoff round 2, item 4).
NOT_FRANCO_SHAPE = re.compile(
    r"[a-z]*\d{2,}[a-z]*|\d{1,2}(?:h|hrs?|x|k|g|kg|cm|mm|ml|km|mins?|days?|egp)|(?:uk|us|eu|x|v|gen|size)\d")
CLOCK_TIME = re.compile(r"\d{1,2}(?:am|pm)")
TIME_WORDS = frozenset({"at", "by", "before", "after", "from", "to", "until", "till", "around", "between", "and",
                        "or", "open", "opens", "close", "closes", "start", "starts", "daily", "today", "tomorrow"})
# "w/" and "w/o" are the English short forms of "with" and "without" ("Boots w/ a box", "Boots w/o box"), not
# the Franco "w" (and), review handoff round 3, finding 2.
WITH_SHORT = re.compile(r"(?<![\w/])w/(?=\s)")
WITHOUT_SHORT = re.compile(r"(?<![\w/])w/o(?![\w/])")
# Franco words that are English words too: read leniently they count once, so "Mesh upper, mesh tongue" stays
# English (review handoff round 3, finding 2).
ENGLISH_TOO = frozenset({"mesh"})

BANNED = [
    (re.compile(r"(?:ال|لل|بال)جوز"), "Never write الجوز. Say the price plainly, the number then جنيه."),
    (re.compile(r"\b(?:el|l|ll|lel|bel)\s?goz\b"), "Never write el goz. Say the price plainly."),
    (re.compile(r"مرتاح"), "Never use مرتاح or filler like it."),
]
SYMPATHY = [
    "مقدر إن", "مقدر ان", "متضايق", "حقك تزعل", "حقك تضايق", "أنا آسف إنك", "انا اسف انك",
    "i understand your frustration", "i understand how you feel", "sorry to hear",
    "sorry for the inconvenience", "i can imagine how", "m2adar", "mtday2", "7a2ak tez3al",
]
DASHES = re.compile("[\u2012\u2013\u2014\u2015]")


def _ranges(*pairs):
    return "".join(f"{chr(a)}-{chr(b)}" for a, b in pairs)


# Emoji and pictographs, built from code points so the source stays plain.
EMOJI = re.compile("[" + _ranges((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF),
                                 (0xE0020, 0xE007F)) + chr(0xFE0F) + chr(0x3030) + chr(0x303D) + "]")
MARKDOWN_BOLD = re.compile(r"\*\*")
# A hyphen with spaces on both sides. Between two digits it is a range (42 - 45), not a dash.
SPACED_HYPHEN = re.compile(r"(?<=(\S))[ \t]+-[ \t]+(?=(\S))")

LETTER_BEFORE = r"(?<![^\W\d_])"
NO_LETTER_AFTER = r"(?![^\W\d_])"
MASK = chr(1)  # stands in for a number that is not an amount (a size, a date, an order number)
MONEY = chr(2)  # stands in for a number with a currency next to it, already read as an amount

CURRENCY = (r"(?:جنيهات|جنيهاً|جنيهًا|جنيها|جنيه|جنية|ج\.م|جم|ج|egp|l\.e|le|egyptian\s+pounds?|pounds?"
            r"|geneh|genih|gneh|gnih|ginih|gnyh|gineh|gineeh|geneeh|ginee|e£|£)")
# Digits as written, with thousands commas and decimals: 16,560 and 16500.99. A comma with one or
# two digits after 3 or more digits is a decimal comma: 16500,99 is 16500.99 and 500,00 is 500.
DIGITS = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,},\d{1,2}(?!\d)|\d+(?:\.\d+)?"
DECIMAL_COMMA = re.compile(r"\d+,\d{1,2}")
# 1 to 3 digits, then groups of 3 after blanks: 1 400, 10 400. Every blank but a line end counts (plain,
# no-break, thin, tab, two spaces), so no blank lets 1 400 read as 400 (red team t261028j r2). A separator
# after the blanks, or an apostrophe alone, joins too: "17 ,400", "6" then a blank, an Arabic comma and "400", and "17'400" read as one number, the
# number the customer sees (red team handoff round 1, item 1). A separator then a blank ("60, 400") is a list.
THOUSANDS_GAP = r"(?:[^\S\n]+[.,\u060c'\u2019]?|['\u2019])"
# A blank other than the plain, no break and ideographic spaces (thin, hair, figure, punctuation, medium
# math, ogham and the rest) next to a separator shows narrow, so "17," then a hair space then "400" reads
# 17,400; it is taken out before the groups are joined (red team handoff round 2, item 1; round 3, item 2).
# A full width blank after the separator stays a list ("60, 400").
NARROW_BLANKS = "[\u1680\u2000-\u200a\u202f\u205f]+"
NARROW_BLANK = re.compile(r"(?<=[.,\u060c'\u2019])" + NARROW_BLANKS + r"(?=\d{3}(?!\d))"
                          r"|(?<=\d)" + NARROW_BLANKS + r"(?=[.,\u060c'\u2019]" + NARROW_BLANKS + r"?\d{3}(?!\d))")
SPACED_THOUSANDS = re.compile(r"(?<![\d.,])[1-9]\d{0,2}(?:" + THOUSANDS_GAP + r"\d{3})+(?!\d)")
MAX_INT_DIGITS = 20
NUMBER = rf"({DIGITS})"
PRICE = re.compile(
    rf"{NUMBER}\s*{CURRENCY}(?![\w])|(?<![\w]){CURRENCY}{NO_LETTER_AFTER}\s*{NUMBER}", re.IGNORECASE)

# Words after which a number reads as an amount. PRICE_WORDS always name money. WEAK_WORDS
# (is, for, ب) also come before sizes, so after one of them a catalogue size number (43 from
# the boot size "43") is read as a size, unless a price word comes earlier in the same sentence.
PRICE_WORDS = (
    r"(?:و|ف)?(?:بال|ال|ب)?سعر(?:ه|ها|هم|و)?", r"(?:و|ف)?(?:بال|ال|ب)?تمن(?:ه|ها|هم|و)?",
    r"(?:و|ف)?(?:ال)?(?:شحن|توصيل|مصاريف|رسوم|اجمالي|إجمالي|مجموع|حساب|مبلغ)",
    r"(?:el\s?|b)?se3r\w*", r"(?:el\s?)?taman\w*", r"(?:el\s?)?(?:sha7n|tawsil|tawseel|egmaly|egmali)",
    r"prices?", r"priced", r"pricing", r"costs?", r"costing",
    r"total", r"subtotal", r"fees?", r"shipping", r"delivery", r"pay", r"charged?", r"charges",
)
WEAK_WORDS = (r"بـ", r"ب", r"b", r"bi", r"be", r"for", r"is", r"are", r"at", r"only", r"just")
CUES = PRICE_WORDS + WEAK_WORDS
WEAK_CUE = re.compile("(?:" + "|".join(WEAK_WORDS) + ")", re.IGNORECASE)
PRICE_WORD = re.compile(LETTER_BEFORE + "(?:" + "|".join(PRICE_WORDS) + ")" + NO_LETTER_AFTER, re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?؟\n](?!\d)")
# A line that ends in ":" or "=" goes on to the next line, so "Total:\n#1500" and "الإجمالي:\n#1500"
# are one sentence (review t261028j round 2, finding 4). A line that ends in a cue word goes on
# when the next line starts with a number or # ("The total is\n#1500."), and for order numbers
# whatever the next line is ("Total\nis #1500"). So "Payment: cash on delivery\nAddress: Building
# 15, Apartment 302" keeps 302 as an address number (review t261028j round 3, finding 1). A line
# with a price word and no amount goes on when the next line starts with a number or #
# ("Total comes to\n#1500"). Lines with no letter, digit or # in between are passed over
# ("Total:\n\n#1500"), red team t261028j round 3, item 4.
LINE_OPEN = re.compile(r"[:=][^\S\n]*$")
LINE_CUE_END = re.compile(LETTER_BEFORE + "(?:" + "|".join(CUES) + ")" + NO_LETTER_AFTER + r"[^\S\n]*$",
                          re.IGNORECASE)
NUMBER_FIRST = re.compile(r"[^\w#" + MASK + MONEY + r"\n]*[\d#" + MASK + MONEY + "]")
TEXT_CHAR = re.compile(r"[\w#" + MASK + MONEY + "]")
FILLER_WORD = r"[^\s\d" + MASK + MONEY + r".!?؟،,;]+"
CUE_AMOUNT = re.compile(
    LETTER_BEFORE + "(?P<cue>" + "|".join(CUES) + ")" + NO_LETTER_AFTER
    + r"(?:\s+" + FILLER_WORD + r"){0,3}?\s*[:=]?\s*(?<![\d.,])(?P<n>" + DIGITS + r")(?![\w%٪])",
    re.IGNORECASE)

# A 1 or 2 digit number right after a city or governorate reads as a delivery fee ("Cairo 70,
# Alex 90", "القاهرة 70 والاسكندرية 90").
PLACES = (
    r"(?:و|ف)?(?:بال|لل|ال|ب|ل)?(?:قاهر[ةه]|جيز[ةه]|[اإ]سكندري[ةه]|محافظات|محافظ[ةه]|مدن|صعيد|[اأ]قاليم|دلتا"
    r"|ساحل|غردق[ةه]|[اأ]قصر|[اأ]سوان|[اأ]سيوط|سوهاج|قنا|منيا|فيوم|سويس|[اإ]سماعيلي[ةه]|بورسعيد|بور\s+سعيد"
    r"|دمياط|منصور[ةه]|طنطا|زقازيق|شرقي[ةه]|غربي[ةه]|دقهلي[ةه]|منوفي[ةه]|قليوبي[ةه]|بحير[ةه]|مطروح|سينا"
    r"|شرم|عريش|مصر|بني\s+سويف|كفر\s+الشيخ)",
    r"cairo|alex|alexandria|aswan|luxor|hurghada|sharm|mansoura|tanta|zagazig|ismailia|suez|port\s+said"
    r"|damietta|fayoum|faiyum|minya|minia|asyut|assiut|sohag|qena|beni\s+suef|sinai|matrouh|delta|sahel|egypt"
    r"|cities|city|governorates?|provinces?|(?:el\s?)?2ahera|(?:el\s?)?giza|eskendereya|eskenderia|eskendria"
    r"|iskandaria|(?:el\s?)?mo7afzat|mo7afazat|mohafzat|mo7afza|masr|(?:el\s?)?sa3id",
)
PLACE_AMOUNT = re.compile(
    LETTER_BEFORE + "(?:" + "|".join(PLACES) + ")" + NO_LETTER_AFTER
    + r"\s*[:=]?\s*(?<![\d.,])(?P<n>" + DIGITS + r")(?![\w%٪])", re.IGNORECASE)

# A standalone number: not glued to letters or digits before it, so codes like NLS0001 and
# BO-2936845 are not read. Letters after it do not matter (500bs is 500). With 3 or more
# digits, all of them counted (1.500, 500,50), it is an amount wherever it stands.
BARE_NUMBER = re.compile(r"(?<![A-Za-z0-9])(?<![A-Z]-)(?P<n>" + DIGITS + r")(?![0-9%٪])")
BARE_DIGITS = 3
# Egyptian phone numbers: mobiles (01x, 201x, +201x, 00201x), any number after +20 or 0020,
# and landlines (02 then 8 digits, 03 then 7, other area codes 0xx then 7). Any other country's
# number with a + and 8 to 15 digits (+44 7700 900123), the way the order summary shows it.
PHONE = re.compile(
    r"(?<![\w+])(?:(?:\+|00)\s?20[ -]?|20|0)1[0125](?:[ -]?\d){8}(?!\d)"
    r"|(?<![\w+])(?:\+|00)\s?20(?:[ -]?\d){8,10}(?!\d)"
    r"|(?<![\w+.,])0(?:2(?:[ -]?\d){8}|3(?:[ -]?\d){7}|[4-9]\d(?:[ -]?\d){7})(?!\d)"
    r"|(?<![\w+])\+\s?[1-9](?:[ -]?\d){7,14}(?!\d)")

SEP = r"(?:-|to|and|or|/|,|،|و|او|أو|لـ|ل|l|w|aw|le)"
UNITS = (r"(?:days?|yom|youm|ayam|ayyam|أيام|ايام|يومين|يوم|hours?|hrs?|ساعات|ساعة|ساعه|sa3a|sa3at|weeks?"
         r"|اسبوع|أسبوع|اسابيع|أسابيع|months?|شهور|شهر|minutes?|mins?|دقيقة|دقيقه|دقايق|pairs?|pieces?|pcs"
         r"|items?|قطعة|قطعه|قطع|7etta|7etat|colou?rs?|ألوان|الوان|لون|sizes?|مقاسات|cm|mm|سم|mb|ميجا|mega"
         r"|kg|كيلو|grams?|جرامات|جرام|am|pm|times|مرات|مرة|مره|years?|سنين|سنة|سنه)")
# A weight in grams of up to 3 digits ("150 grams of pure speed", the Vapor 17 line in the store
# data) is not an amount, even standing alone. 4 or more digits stay amounts, so "16500 grams"
# cannot hide a price. جم is left out: it is the currency (جنيه مصري), read first.
WEIGHT_AFTER = re.compile(r"\s*(?:grams?|جرامات|جرام)" + NO_LETTER_AFTER, re.IGNORECASE)
WEIGHT_DIGITS = 3
# A unit after the number, or a range up to a second number then a unit (2 to 3 days). A range
# that runs down ("70 to 3 days") is a fee, then a time, so the first number stays an amount.
UNIT_AFTER = re.compile(rf"\s*(?:{SEP}\s*(?P<to>\d+)\s*)?(?:(?:working|business)\s+)?{UNITS}{NO_LETTER_AFTER}",
                        re.IGNORECASE)
# Franco "2 le 3 ayam" (2 to 3 days): this "le" means "to", not the currency LE. So does a
# lower case "le" before a number of 1 or 2 digits ("mn 42 le 45", "t8ayar le 44").
LE_RANGE = re.compile(rf"(?<=\d)(\s*)le(?=\s*\d+\s*(?:(?:working|business)\s+)?{UNITS}{NO_LETTER_AFTER})"
                      r"|(?<![\w.])(?-i:le)(?=\s*\d{1,2}(?![\d.,]?\d))", re.IGNORECASE)

# Numbers that are not amounts: sizes, dates and order numbers.
BARE_SIZE = re.compile(r"[0-9]+")   # a catalogue size that is only a whole number ("43")
SIZE_WORDS =r"(?:sizes?|مقاسات|مقاس(?:ه|ها|ك)?|المقاس|بمقاس|ma2as(?:at)?|eu)"
# "sizes 42, 43 and 44": the list goes on only with numbers of 1 or 2 digits, so "size 43, 500" keeps 500.
SIZE_CTX = re.compile(
    rf"{LETTER_BEFORE}{SIZE_WORDS}{NO_LETTER_AFTER}(?:\s*(?:is|are|:|=))?\s*\d+(?:\s*{SEP}\s*\d{{1,2}}(?!\d))*",
    re.IGNORECASE)
MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|march|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?"
          r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|يناير|فبراير|مارس|ابريل|أبريل|إبريل|مايو|يونيو|يونيه"
          r"|يوليو|يوليه|اغسطس|أغسطس|سبتمبر|اكتوبر|أكتوبر|نوفمبر|ديسمبر)")
# A year inside a date: 28 Oct 2026, Oct 28, 2026, 28/10/2026, 28.10.2026, 2026-10-28.
DATE_YEAR = r"(?:,?\s*(?:19|20)\d\d(?![\d%٪])(?![.,]\d))?"
DATES = re.compile(
    r"(?<!\d)\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\d)|(?<!\d)\d{4}(?:-\d{1,2}-|/\d{1,2}/)\d{1,2}(?!\d)"
    r"|(?<![\d.,])(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])\.(?:19|20)\d\d(?![\d%٪])(?![.,]\d)"
    r"|(?<!\d)\d{1,2}:\d{2}(?!\d)"
    rf"|(?<![\d.,])\d{{1,2}}(?:st|nd|rd|th)?(?:\s+of)?\s+{MONTHS}{NO_LETTER_AFTER}{DATE_YEAR}"
    rf"|{LETTER_BEFORE}{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?!\d){DATE_YEAR}", re.IGNORECASE)
# A year from 1900 to 2099 with a year word or a month right next to it: model 2026, the 2026
# model, سنة 2026, May 2026. Only the year is masked, so the word stays for the other rules.
# Mohamed's call, 28 Oct: any other 4 digit number is an amount, so "Boots: 1999." is refused.
YEAR = r"(?<![\d.,])(?:19|20)\d\d(?![\d%٪])(?![.,]\d)"
YEAR_WORDS = r"(?:year|models?|(?:ال)?موديل(?:ات)?|(?:ال)?سن[ةه]|sana|sanat)"
YEAR_CTX = re.compile(
    rf"{LETTER_BEFORE}(?:{YEAR_WORDS}|{MONTHS}){NO_LETTER_AFTER}\s*:?\s*(?P<a>{YEAR})"
    rf"|(?P<b>{YEAR})\s*{YEAR_WORDS}{NO_LETTER_AFTER}", re.IGNORECASE)
# A number right after an address word: عمارة 125, الدور 3, Building 125, Flat 12, 3emara 125. A rule
# on words, not on the customer's own address text, so an address can never hide an amount in a
# price line. A number with a currency word is read first, so "عمارة 125 جنيه" is still an amount.
# Left out on purpose, as they also sit before prices: piece words (قطعة, 2et3a, unit: "سعر القطعة
# 16500"), shop words (محل, مول: "سعرها في المحل 16500") and zone words (zone, منطقة, manta2a: the
# delivery data prices by zone).
ADDRESS_WORDS = (
    r"(?:و|ف)?(?:بال|لل|ال|ب|ل)?(?:عمار[ةه]|برج|شق[ةه]|دور|طابق|بلوك|فيلا|مبن[ىي]|عقار|منزل|بيت"
    r"|مجاور[ةه]|حي|شارع|ش|ممر|حار[ةه]|عطف[ةه]|مدخل|بواب[ةه]|مربع|كمبوند)",
    r"(?:el\s?)?(?:3emara|emara|borg|sha2a|dor|block|villa|share3|mogawra|7ay)",
    r"building|bldg|block|blk|floor|flr|apartment|apt|villa|street|st|road|rd|district|gate"
    r"|entrance|plot|tower|house|compound",
)
ADDRESS = re.compile(
    r"(?<!\w)(?:" + "|".join(ADDRESS_WORDS) + r")(?!\w)"
    r"(?:\s*(?:رقم|rakam|ra2am|number|no\.?|num|#|:|\.)){0,2}\s*\d+(?![.,]?\d)", re.IGNORECASE)
# An address label is not a price word: "عنوان التوصيل: شقة 302" and "Delivery address: Apartment
# 302" read as "عنوان" and "address", so the address numbers stay masked (review t261028j round 3, finding 1).
ADDRESS_LABEL = re.compile(
    LETTER_BEFORE + r"(?:(?P<ar>(?:و|ف|ب|ل)?(?:ال)?عنوان)\s+(?:ال|لل)?(?:توصيل|شحن)"
    r"|(?P<fr>(?:el\s?)?3[ae]nwan)\s+(?:el\s?)?(?:tawsil|tawseel|sha7n)"
    r"|(?:delivery|shipping)\s+(?P<en>address(?:es)?))" + NO_LETTER_AFTER, re.IGNORECASE)
# Draft orders on Shopify are named #D12, so a letter may sit between # and the digits.
HASH_NUMBER = re.compile(r"#\s*[A-Za-z]?\d+")   # for the script check only: #D12 is not a word
# Order numbers (red team t261028j F7): only order shaped numbers are masked. A draft name
# (#D12) always; # and up to 5 digits (#1042) unless the sentence has a price word or an
# amount with a currency and no order word stands right before the # ("Total: #1500" is an
# amount, "Your total for order #1042 is 16500 EGP." keeps the order number). An order word
# with no # ("طلبك 1500", "Your order 1500") masks nothing.
DRAFT_NAME = re.compile(r"#\s*[Dd]\d+")
ORDER_NAME = re.compile(r"#\s*\d{1,5}(?![\d.,]?\d)")
ORDER_WORD_BEFORE = re.compile(
    LETTER_BEFORE + r"(?:orders?|اوردر|أوردر|الاوردر|الأوردر|اوردرك|أوردرك|طلب|طلبك|الطلب|طلبية|ordr|el\s?order)"
    + NO_LETTER_AFTER + r"(?:\s*(?:number|no\.?|num|رقم|rakam|ra2am|:))*\s*$", re.IGNORECASE)
# An order name a tool gave this turn (#1001 from draft_order or find_order): masked wherever it
# stands whole, so "اوردرك اتسجل برقم #1001، والإجمالي 1958 جنيه." passes and #1002 still counts
# (review t261028j round 3, note 1).
GIVEN_ORDER_NAME = re.compile(r"#?\s*([A-Za-z]{0,3}\d{1,12})")
# Egyptian numbers are masked only when grouped the way a phone number is written (_mask_phone).
EG_PREFIX = re.compile(r"(?:\+|00)\s?20[ -]?|20(?=1)")
PHONE_GROUPS = ([7], [8], [4, 4], [3, 4])

# An amount written in words cannot be checked, so it is refused: next to a currency word, after
# a price word or ب (glued or not), or, when it is 100 or more, after any cue word.
# Words for 100 or more: hundred, thousand, the Arabic and Franco hundreds (خمسمية, khomsomeya).
HUNDREDS = (r"(?:تلت|تلات|ثلاث|ربع|اربع|أربع|خمس|ست|سبع|تمن|تمان|ثمان|تسع)(?:مية|ميه|مائة|مئة)|ميتين|متين|مائتين|مئتين"
            r"|(?:tolt|tult|talat|rob3|rub3|arba3|khoms|khams|5oms|5ams|sot|set|sett|sob3|sab3|tomn|tamn|tos3|tes3"
            r"|tis3)(?:o|u|e|a)?\s?(?:meyya|meya|mya|miya|mia)")
MAGNITUDE_WORDS = (rf"(?:{HUNDREDS}|hundreds?|thousands?|alfein|alfeen|alaf|alf|elf|talaf|tlaf|meyya|meya|mya|miya|meteen|metein|mitein"
                   r"|miteen|mit|ميتين|مية|ميه|مائة|مئة|ميت|ألفين|الفين|ألف|الف|آلاف|الاف|ألاف|الآف|ألآف|تلاف)")
NUMBER_WORDS = (rf"(?:{MAGNITUDE_WORDS}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen"
                r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|nos|tolt|rob3|واحد|اتنين|اثنين|تلاتة|ثلاثة"
                r"|اربعة|أربعة|خمسة|ستة|سبعة|تمانية|ثمانية|تسعة|عشرة|عشرين|تلاتين|ثلاثين|اربعين|أربعين|خمسين"
                r"|ستين|سبعين|تمانين|ثمانين|تسعين)")
SPELLED_AMOUNT = re.compile(rf"{NUMBER_WORDS}\s*{CURRENCY}(?![\w])", re.IGNORECASE)
# Number words in a row: "five hundred", "ميتين وخمسين", "two to three".
WORD_RUN = (rf"{NUMBER_WORDS}{NO_LETTER_AFTER}"
            rf"(?:\s*(?:and|or|to|aw|w|le|l|و|او|أو|لـ|ل|-)?\s*{NUMBER_WORDS}{NO_LETTER_AFTER})*")
WORD_AMOUNT = re.compile(
    rf"(?:{LETTER_BEFORE}(?:(?P<price>{'|'.join(PRICE_WORDS)})|(?P<weak>{'|'.join(WEAK_WORDS)})){NO_LETTER_AFTER}"
    rf"(?:\s+{FILLER_WORD}){{0,3}}?\s*[:=]?\s*)?{LETTER_BEFORE}(?P<glued>بـ?)?(?P<words>{WORD_RUN})",
    re.IGNORECASE)
MAGNITUDE = re.compile(MAGNITUDE_WORDS + NO_LETTER_AFTER, re.IGNORECASE)
# "بألف خير", "ألف مرة", "one of", "بمية ساقعة" (with cold water): number words that are not an amount.
NOT_AN_AMOUNT_AFTER = re.compile(
    r"\s*(?:خير|سلام[ةه]|شكر|مبروك|مر[ةه]|مرات|ساقع[ةه]?|بارد[ةه]?|سخن[ةه]?|دافي[ةه]?|فاتر[ةه]?|times?|of"
    r"|salama|shokr|mabrou?k|marr?a)" + NO_LETTER_AFTER, re.IGNORECASE)
ONE = re.compile(r"one|واحد", re.IGNORECASE)
# Digits with k or thousand after them (1k, 1.5 ألف) next to a currency or price word cannot be
# checked either. With the Arabic or Franco word for thousand they are refused anywhere: ألاف is a common
# spelling of آلاف, and تلاف and talaf are thousands after 3 to 10 ("6 تلاف" is 6,000), red team handoff
# round 2, item 2; alaf, elf, الآف and ألآف are spellings too (red team handoff round 3, item 3).
THOUSANDS_WORDS = r"(?:alaf|alf|elf|ألف|الف|آلاف|الاف|ألاف|الآف|ألآف|تلاف|talaf|tlaf)"
THOUSANDS = rf"(?:k|thousands?|{THOUSANDS_WORDS})"
SHORT_AMOUNT = re.compile(
    rf"{NUMBER}\s*{THOUSANDS}{NO_LETTER_AFTER}\s*{CURRENCY}(?![\w])"
    rf"|(?<![\w]){CURRENCY}{NO_LETTER_AFTER}\s*{NUMBER}\s*{THOUSANDS}{NO_LETTER_AFTER}"
    rf"|{LETTER_BEFORE}(?:{'|'.join(CUES)}){NO_LETTER_AFTER}(?:\s+{FILLER_WORD}){{0,3}}?\s*[:=]?\s*{NUMBER}\s*"
    rf"{THOUSANDS}{NO_LETTER_AFTER}"
    rf"|(?<![\d.,]){NUMBER}\s*{THOUSANDS_WORDS}{NO_LETTER_AFTER}",
    re.IGNORECASE)

# A count word after a model number keeps it a count: "Only Vapor 17 pairs left", "Phantom 6 فاضلين".
# "available" and "in stock" are left out: "Phantom 6 available in 42" names the boot (red team handoff
# round 1, item 2). The words are stems, so every ending counts (fadla, ba2yeen, باقيه, متبقية, remains),
# and up to two bridge words may come first ("Vapor 17 are left", "Phantom 6 لسه فاضلين"), red team
# handoff round 2, item 3. "more" stays a whole word: "the Phantom 6 is more than" names the boot.
COUNT_BRIDGE = r"(?:بس|bs|bas|bass|لسه|لسة|lesa|lessa|still|now|only|currently|also|are|is)"
# Before "in stock" and "available" is and are are no bridge: "UK 8 is in stock" and "Option 2 is available"
# name a size and an option, "Only 3 pairs currently available" is a count (review and red team handoff
# round 3).
STOCK_BRIDGE = r"(?:بس|bs|bas|bass|لسه|لسة|lesa|lessa|still|now|only|currently|also)"
# "remaining" always counts. "remains" and "remain" count at a clause end, before now, today or right now, and
# before "in" and a size or "in stock" ("Only 3 remain in 43"); the plural "remain" also before the words a
# count goes on with ("Only Vapor 17 remain available", "3 remain so hurry"). Before any other word they are
# the verb: "The Vapor 17 remains our best seller", "The Superfly 11 remains in our range", "Both remain
# popular" (red team handoff round 3, item 4; review handoff round 3, minor 4).
REMAIN_NEXT = (r"[^\S\n]*(?:[.,!?;:)\u060c\u061f\u061b\u2026\n]|$)|[^\S\n]+(?:(?:now|today|right[^\S\n]+now)"
               + NO_LETTER_AFTER + r"|in[^\S\n]+(?:size[^\S\n]+)?\d|in[^\S\n]+stock" + NO_LETTER_AFTER + ")")
REMAIN_NEXT_PLURAL = (r"[^\S\n]+(?:for|only|so|available|still|of|on|across|and|but|as|with|from|unsold|here|left"
                      r"|currently)" + NO_LETTER_AFTER)
REMAIN = rf"(?:remaining|remains(?={REMAIN_NEXT})|remain(?={REMAIN_NEXT}|{REMAIN_NEXT_PLURAL}))"
# The Franco mawgod forms count only in the plural (mawgodin, mwgodeen): the singular is "available", as English
# "available" and Arabic موجود are ("el F50 mawgod fel 43"), review handoff round 3, finding 1.
MAWGOD_PLURAL = r"ma?wgo[ou]?d(?:in|een|ein)"
COUNT_STEMS = (rf"(?:pairs?|pieces?|pcs|pc|items?|units?|left|{REMAIN}|قطعة|قطعه|قطع|حتة|حته|حتت|7etta|7etat|جوز|goz"
               rf"|فاضل|باقي|باقى|متبقي|متبقى|متاحين|موجودين|fadl|fadel|ba2y|ba2i|{MAWGOD_PLURAL})")
COUNT_AFTER = rf"[^\S\n]*(?:{COUNT_BRIDGE}[^\S\n]+){{0,2}}{COUNT_STEMS}|[^\S\n]*more{NO_LETTER_AFTER}"
# A model number ends only where the reply plainly moves on (an allow list, review handoff round 2,
# finding 1; red team handoff round 2, item 1): blanks then a letter, an opening bracket or a quote not
# followed by a digit, blanks then b or ب glued to a price ("Phantom 6 b7,500"), or blanks then one of - / &
# + and a blank; blanks then ? ! or ؟ ("Is it the Vapor 17 ?"); one or more end marks (. , ، ; ؛ : ! ? ؟ an
# ellipsis, closing brackets and quotes) then a blank, a line end or the end (review handoff round 3, minor
# 3); an apostrophe then a letter ("Vapor
# 17's"); the line end or the end. Anything else after it keeps the number (a digit, a separator then a
# digit, a sign that looks like one, "Phantom 6 (400"), and so do a currency, a thousands word and a count
# word: "Vapor 17 ,400", "Vapor 17" then a middle dot then "400", "Vapor 17 EGP", "Vapor 17k" and "Vapor
# 17 pairs left" all keep it. "Phantom 6. 16,500" and "Phantom 6, 400 EGP" still strip.
MODEL_NUMBER_MOVES_ON = (r"(?=[^\S\n]+(?:[^\W\d_](?!\d)|[\u0628b](?=\d)|[(\[{\"\u201c\u2018\u00ab'\u2019](?!\d)"
                         r"|[-/&+][^\S\n]|[!?\u061f]+(?:\s|$))"
                         r"|[.,\u060c;\u061b:!?\u061f\u2026)\]}\"\u201d\u2019'\u00bb]+(?:\s|$)|['\u2019][^\W\d_]"
                         r"|[^\S\n]*(?:\n|$))")
MODEL_NUMBER_END = rf"(?!\s*(?:{CURRENCY}|{THOUSANDS}){NO_LETTER_AFTER}|{COUNT_AFTER}){MODEL_NUMBER_MOVES_ON}"
MODEL_DIGITS = 2   # "Pro 500" in a title is a tier and a measure, never a model number
TIER_WORDS = r"(?:elite|pro|academy|league|club|match|competition|premium|standard|basic|plus|max)"
# Small words a pack or a count title puts before a number ("Grip Tape Pack of 3").
COUNT_TITLE_WORDS = r"(?:of|in|on|by|the|a|an|with|x|pack|set|box|pair|vs|per|no|nr|num|number)"
# A title word that is one of these is never a model's word: "Nike Total 90" would hide "total 90".
NOT_A_TITLE_WORD = re.compile("(?:" + "|".join(
    PRICE_WORDS + WEAK_WORDS + PLACES + ADDRESS_WORDS
    + (SIZE_WORDS, CURRENCY, NUMBER_WORDS, THOUSANDS, YEAR_WORDS, UNITS, MONTHS, TIER_WORDS, SEP,
       COUNT_TITLE_WORDS)) + ")",
    re.IGNORECASE)


def _model_parts(titles):
    """(title word, digits) for each title number of 1 or 2 digits: ("vapor", "17"), ("f", "50"). A
    title word in NOT_A_TITLE_WORD gives none."""
    out = []
    for title in titles or ():
        words = re.findall(r"[^\W_]+", (title if isinstance(title, str) else "").casefold())
        for k, w in enumerate(words):
            m = re.fullmatch(r"([a-z]*)(\d{1,%d})" % MODEL_DIGITS, w)
            if not m:
                continue
            lead = m.group(1) or (words[k - 1] if k and re.fullmatch(r"[a-z]+", words[k - 1]) else "")
            if lead and not NOT_A_TITLE_WORD.fullmatch(lead):
                out.append((lead, m.group(2)))
    return out


def _model_pattern(lead, digits):
    return r"(?<!\w)(" + re.escape(lead) + r")[\s-]*" + digits + MODEL_NUMBER_END


def model_numbers(titles):
    """For each title number, the pattern of it with the title word it belongs to: "vapor 17", "f50"."""
    return [_model_pattern(lead, digits) for lead, digits in _model_parts(titles)]


def _titles_key(titles):
    """The titles as one sorted tuple, so the compiled patterns are kept per store."""
    return tuple(sorted({t for t in titles or () if isinstance(t, str)}))


@functools.lru_cache(maxsize=8)
def _model_number_res(key):
    """(title word, compiled pattern) for each model number, compiled once per store (review handoff
    round 1, low 6: 600 titles cost 170 ms a check when compiled on each call)."""
    parts = dict.fromkeys(_model_parts(key))
    return tuple((lead, re.compile(_model_pattern(lead, digits), re.IGNORECASE)) for lead, digits in parts)


@functools.lru_cache(maxsize=8)
def _model_thousands_res(key):
    """(title word, compiled pattern) for a model number with k or thousand after it ("Vapor 17k")."""
    parts = dict.fromkeys(_model_parts(key))
    return tuple((lead, re.compile(r"(?<!\w)" + re.escape(lead) + r"[\s-]*" + digits + r"\s*" + THOUSANDS
                                   + NO_LETTER_AFTER, re.IGNORECASE)) for lead, digits in parts)


def model_thousands(text, titles):
    """True when a model number has k or thousand after it: "Superfly 11k", "Vapor 17 thousand". The
    customer reads 11,000 and 17,000, so the reply is refused like "1k EGP" (red team handoff round 1,
    item 5). Digits with k and no product word ("1k followers", "Hoodie 1.5k") stay as before."""
    text = _plain(text)
    low = text.casefold()
    return any(lead in low and rx.search(text) for lead, rx in _model_thousands_res(_titles_key(titles)))


# Tier words a reply puts before a price ("Elite 17.5k, Academy 7.5k"); they are kept out of the title words.
STORE_TIERS = ("elite", "academy", "pro", "league", "club")


def store_word_thousands(text, vocabulary, titles=()):
    """True when a number with k or thousand after it comes right after a store word: a product name word
    of 3 or more letters, or letters then a model number ("f50"), that is not a cue, tier or count word, or a
    tier ("Elite 17.5k", "Phantom 6 Academy 8.5k"), with a model number, a sign (: , = ( -) or a decimal comma
    on the way ("Phantom 6: 8.5k", "Elite (17.5k)", "Elite 17,5k"). The customer reads 17,500, so it is
    refused like "1k EGP" (review handoff round 2, finding 2; red team handoff round 3, item 1). titles add each
    model number with its title word ("F50: 15k", the store vocabulary holds only "f"). "The Elite runs 17k" and "It comes to 17k" stay open under the k rule (docs/known-limits.md)."""
    rx = _store_word_thousands_re(tuple(sorted({w for w in vocabulary or () if isinstance(w, str)})),
                                  _titles_key(titles))
    return bool(rx and rx.search(_plain(text)))


@functools.lru_cache(maxsize=8)
def _store_word_thousands_re(key, titles_key=()):
    words = sorted({w for w in key if re.fullmatch(r"[a-z]{3,}|[a-z]+\d{1,2}", w) and not NOT_A_TITLE_WORD.fullmatch(w)}
                   | set(STORE_TIERS))
    words = [re.escape(w) for w in words] + sorted({re.escape(lead) + r"[\s-]*" + digits
                                                    for lead, digits in _model_parts(titles_key)})
    return re.compile(r"(?<!\w)(?:" + "|".join(words) + r")(?:[\s-]*\d{1,2}(?!\d))?"
                      r"[^\S\n]*[:,=(-]?[^\S\n]*(\d+(?:[.,]\d+)?)\s*(?:k|thousands?)" + NO_LETTER_AFTER, re.IGNORECASE)


def without_model_numbers(text, titles):
    """text as the number rules read it (_plain), with each product's model number dropped where it
    follows its title word, so "is the Vapor 17" holds no amount 17; the word stays, and so does a
    price after it ("Vapor 17,500", "Vapor 17 ,400"), a currency or thousands word ("Vapor 17 EGP")
    or a count word ("Vapor 17 pairs left")."""
    text = _plain(text)
    low = text.casefold()
    for lead, rx in _model_number_res(_titles_key(titles)):
        if lead in low:
            text = rx.sub(r"\1", text)
    return text


# An exact stock count, in English, Arabic or Franco. The bridge words and the count stems are the ones a
# model number keeps (COUNT_AFTER), so "Vapor 17 pcs left" and "Phantom 6 lesa fadlin" are counts either
# way. "N pairs", pieces or units after we have, we got or 3andena ("We have Vapor 17 pairs in 43") and "N
# جوز" with بس after it or عندنا before it are counts too (red team handoff round 2, item 3; round 3, item 4);
# an order ("Your order has 2 pairs", "There are 2 pairs in your cart", "el order 2 goz bs": stock_counts
# passes a goz line that names the order), an offer ("Buy 2 pairs") and a description ("2 pairs of laces")
# are not (review handoff round 3, finding 1). A code is not a count: "BO-2936845 is in stock".
GOZ = r"(?:جوز|goz|gozat|أجواز|اجواز)"
STOCK_COUNT = re.compile(
    rf"(?<![\w-])\d+\s+(?:(?:pairs?|pieces?|pcs|pc|items?|units?|more)\s+)?(?:(?:{COUNT_BRIDGE}\s+){{0,2}}"
    rf"(?:left|{REMAIN})|(?:{STOCK_BRIDGE}\s+){{0,2}}(?:in\s+stock|available))" + NO_LETTER_AFTER
    + r"|" + LETTER_BEFORE + r"(?:we(?:'ve|\u2019ve)?\s+(?:(?:still|only|just|also|currently)\s+)?(?:have|got)"
    r"|3andena|3ndena|3andi)\s+(?:[^\W\d_]+\s+){0,3}?\d+\s*(?:pairs?|pieces?|pcs|pc|units?)" + NO_LETTER_AFTER
    + r"(?!\s+of" + NO_LETTER_AFTER + ")"
    + rf"|(?P<goz>\d+\s*{GOZ}\s*(?:بس|bs|bas|bass)" + NO_LETTER_AFTER + ")"
    + rf"|(?:عندنا|عندي|3andena|3ndena|3andi)\s+(?:\S+\s+){{0,3}}?\d+\s*(?:{GOZ}|pairs?|pieces?|pcs|pc)"
    + NO_LETTER_AFTER
    + r"|" + LETTER_BEFORE + r"stock\s*(?:of|is|:|=)?\s*\d+"
    + r"|(?:فاضل|فاضلين|فاضله|فاضلة|باقي|باقى|باقيين|متبقي|متبقى|المتبقي|المتاح|المخزون|الكمية|الكميه|ستوك"
      r"|متوفرين|متوفرة|متوفره|متوفر|fadel|fadl|fadlin|fadleen|ba2y|ba2i|ba2yin|motba2y)"
      r"\s*(?:منه|منها|منهم|بس|meno|menha|menhom|bs)?\s*\d+"
    + rf"|\d+\s*(?:(?:قطعة|قطعه|قطع|حتة|حتت|7etta|7etat|جوز|goz|{COUNT_BRIDGE})\s*){{0,2}}"
      r"(?:فاضل|باقي|باقى|متبقي|متبقى|في المخزن|في الستوك|متاحين|متوفرين|موجودين"
      rf"|fadel|fadl|ba2y|ba2i|{MAWGOD_PLURAL}|fel stock)",
    re.IGNORECASE)

URL_CHARS = r"[^\s<>\"'()\[\]{}]"
LINK = re.compile(
    rf"(?:https?://|www\.){URL_CHARS}+"
    rf"|(?<![\w@.-])(?:[a-z0-9-]+\.)+[a-z]{{2,}}/{URL_CHARS}*"
    r"|(?<![\w@.-])(?:[a-z0-9-]+\.)+(?:com|net|org|eg|io|co|me|ly|ai|app|shop|store|link|site|online|info|biz"
    r"|xyz|gl|to|cc|tv|us|uk|page|dev|example|test)(?![\w-])", re.IGNORECASE)
LINK_TAIL = ".,،;:!?؟"   # an end mark right after a link is not part of it


def links_in(text):
    """Every link in text as (start, end, link), the end marks after it left off."""
    out = []
    for m in LINK.finditer(text or ""):
        link = m.group(0).rstrip(LINK_TAIL)
        out.append((m.start(), m.start() + len(link), link))
    return out


def _links(reply, links):
    """(the reply with each allowed link blanked, the links in it the store tool did not give).
    The reply is read as written and with its invisible format characters taken out, so a zero
    width space inside a link never hides it. (Not _plain: it turns _ into a space, and image
    links carry _.)"""
    allowed = {x for x in links or () if isinstance(x, str) and x}
    seen = "".join(ch for ch in (reply or "") if unicodedata.category(ch) != "Cf")
    wrong = [x for _, _, x in links_in(reply) + links_in(seen) if x not in allowed]
    out = reply or ""
    for start, end, link in reversed(links_in(out)):
        if link in allowed:
            out = out[:start] + " " + out[end:]
    return out, list(dict.fromkeys(wrong))


AMOUNT_KEYS = frozenset({"price", "fee", "total", "subtotal"})
AMOUNT_TEXT = re.compile(r"\s*\d[\d,]*(?:\.\d+)?\s*")


def detect_script(text, skip=frozenset(), lenient=False, pairs=frozenset()):
    """'arabic', 'franco', 'english', or None when there are no letters. skip, lenient and pairs:
    how looks_franco reads Latin text."""
    text = text or ""
    ar = len(ARABIC.findall(text))
    la = len(LATIN.findall(text))
    if ar == 0 and la == 0:
        return None
    if ar >= la:
        return "arabic"
    return "franco" if looks_franco(text, skip, lenient, pairs) else "english"


def looks_franco(text, skip=frozenset(), lenient=False, pairs=frozenset()):
    """True when Latin text reads as Franco: a word with a Franco digit (3ayez) or two common Franco
    words. skip: lowercase words passed over, the store's model words with a digit ("f50" from
    "adidas F50"), so a product name never makes English read as Franco. pairs: two title words
    side by side as a title has them (title_pairs); a word in such a run is passed over too
    ("El Ultimo Tango"). lenient: digit words of NOT_FRANCO_SHAPE (EU42, VAP17) and a clock time next
    to a time word or a clock time ("at 9am", "9am-5pm") are passed over, "w/" and "w/o" read as "with" and
    "without", and a word of ENGLISH_TOO counts once (rule 8). A common Franco word
    counts each time it comes: "el" twice is Franco, and a title said twice is passed over by pairs (red
    team handoff round 2, item 4)."""
    text = text.lower()
    if lenient:
        text = WITH_SHORT.sub("with", WITHOUT_SHORT.sub("without", text))
    all_words = WORD.findall(text)
    words = [w for k, w in enumerate(all_words)
             if not ARABIC.search(w) and w not in skip
             and not (k + 1 < len(all_words) and (w, all_words[k + 1]) in pairs)
             and not (k and (all_words[k - 1], w) in pairs)]
    digit_words = [w for k, w in enumerate(words) if FRANCO_DIGIT_WORD.fullmatch(w) and not ORDINAL.match(w)
                   and not (lenient and (NOT_FRANCO_SHAPE.fullmatch(w) or _clock_time(words, k)))]
    common = [w for w in words if w in FRANCO_WORDS]
    if lenient:
        common = [w for w in common if w not in ENGLISH_TOO] + sorted(ENGLISH_TOO.intersection(common))
    return len(digit_words) >= 1 or len(common) >= 2


def _clock_time(words, k):
    """True when words[k] is a clock time (9am) with a time word or another clock time right before or after
    it ("9am-9pm", review handoff round 3, finding 2)."""
    return bool(CLOCK_TIME.fullmatch(words[k])) and any(
        0 <= j < len(words) and (words[j] in TIME_WORDS or CLOCK_TIME.fullmatch(words[j])) for j in (k - 1, k + 1))


def model_words(titles):
    """The lowercase title words that hold a digit and a letter ("f50"), for looks_franco's skip."""
    return _title_words(_titles_key(titles))[0]


def title_pairs(titles):
    """Each two title words side by side, lowercase, as the title has them: ("el", "ultimo")."""
    return _title_words(_titles_key(titles))[1]


@functools.lru_cache(maxsize=8)
def _title_words(key):
    digit_words, pairs = set(), set()
    for t in key:
        words = WORD.findall(t.lower())
        digit_words |= {w for w in words if LATIN.search(w) and re.search(r"\d", w)}
        pairs |= set(zip(words, words[1:]))
    return frozenset(digit_words), frozenset(pairs)


def _script_feedback(reply, customer_text, vocabulary, names=()):
    """The script rule. The customer's line is read as written; when it reads as Franco only for
    the words a lenient reading passes over ("Do you have the F50?", "F50 mawgood?"), the reply may
    be English or Franco and only Arabic letters are refused (review handoff round 1, medium 1).
    The reply to an English line is read leniently (rule 8)."""
    skip, pairs = model_words(names), title_pairs(names)
    want = detect_script(customer_text)
    if want is None:
        return None
    if want == "franco" and detect_script(customer_text, skip, True, pairs) == "english":
        want = "latin"
    reply = HASH_NUMBER.sub(" ", reply)  # an order number is not a word: #D12 is not Franco
    if want == "arabic":
        words = WORD.findall(reply)
        ar = sum(1 for w in words if ARABIC.search(w))
        latin = sum(1 for w in words if LATIN.search(w) and not ARABIC.search(w)
                    and w.lower() not in vocabulary and not re.fullmatch(r"[A-Z]{2,}\d+", w))
        if ar == 0 or latin > ar / 4:
            return "The customer wrote in Arabic letters. Reply in Egyptian Arabic, in Arabic letters."
    elif want == "franco":
        if ARABIC.search(reply):
            return ("The customer wrote in Franco. Reply in Franco, in Latin letters and numbers, no Arabic letters"
                    + _arabic_found(reply) + " Write amounts as the number then geneh, for example 16,500 geneh.")
    elif want == "english":
        if ARABIC.search(reply):
            return ("The customer wrote in English. Reply in English, no Arabic letters" + _arabic_found(reply)
                    + " Write amounts as the number then EGP, for example 16,500 EGP.")
        if looks_franco(reply, skip, True, pairs):
            return "The customer wrote in English. Reply in plain English, not Franco."
    elif want == "latin":
        if ARABIC.search(reply):
            return ("The customer wrote in Latin letters. Reply in English or Franco, no Arabic letters"
                    + _arabic_found(reply) + " Write amounts as the number then EGP in English or geneh in Franco.")
    return None


def _arabic_found(reply, most=3):
    """ (this reply has: <the first Arabic words>). with the end mark, so the model sees what to change;
    a currency word written in Arabic (جنيه) in an English reply is the usual one."""
    words = list(dict.fromkeys(w for w in WORD.findall(reply) if ARABIC.search(w)))[:most]
    return f" (this reply has: {', '.join(words)})." if words else "."


# A carriage return and the line and paragraph separators end a line like a line feed; the other control
# characters show as nothing, so "17," then a next line control then "400" reads 17,400 (red team handoff
# round 3, item 2).
LINE_BREAK = re.compile("\r\n?|[\u2028\u2029]")
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x85]")


def _plain(text):
    """The reply as the number rules read it: Western digits, line breaks as a line feed and no other control
    character (LINE_BREAK, CONTROL), no invisible format characters
    (a zero width space splits 500 into 5 and 00), look-alike signs and blanks as ":", "=", ",", ".",
    "'" and spaces (NUMBER_LOOKALIKES), combining marks on no letter taken out, a narrow blank next to a
    separator taken out (NARROW_BLANK), a modifier letter inside a number read as an apostrophe
    (MODIFIER_IN_NUMBER), emphasis marks as spaces (_500_ is 500) and taken out right after a separator (EMPHASIS_IN_NUMBER),
    and digit groups split
    by blanks, blanks then a separator, or an apostrophe joined (1 949 is 1949, 17 ,400 is 17400:
    SPACED_THOUSANDS)."""
    text = CONTROL.sub("", LINE_BREAK.sub("\n", "".join(ch for ch in (text or "") if unicodedata.category(ch) != "Cf")))
    text = MODIFIER_IN_NUMBER.sub("'", NARROW_BLANK.sub("", _loose_marks_out(text.translate(NUMBER_LOOKALIKES))))
    return _join_thousands(EMPHASIS.sub(" ", EMPHASIS_IN_NUMBER.sub("", western_digits(text))))


LOOSE_MARKS = ("Mn", "Me", "Mc")


def _loose_marks_out(text):
    """text with each combining mark that sits on no letter taken out: "17" then a combining low line
    then ",400" shows as 17,400, so it reads 17,400 (red team handoff round 1, item 1); spacing marks
    too (red team handoff round 2, item 1). Marks on a letter (Arabic vowel marks) stay."""
    if not any(unicodedata.category(ch) in LOOSE_MARKS for ch in text):
        return text
    out, base = [], ""
    for ch in text:
        if unicodedata.category(ch) in LOOSE_MARKS:
            if not base.isalpha():
                continue
        else:
            base = ch
        out.append(ch)
    return "".join(out)


def _join_thousands(text):
    """Blanks (and a separator after them) used as a thousands separator removed: "الطباعة 1 400
    جنيه" reads as 1400, the number the customer sees, not 400 (red team t261028j F6). Digits inside a phone number
    written the way phone numbers are (+1 202 555 0143) stay as they are."""
    phones = [m.span() for m in PHONE.finditer(text) if phone_shaped(m.group(0))]
    return SPACED_THOUSANDS.sub(
        lambda m: m.group(0) if any(a < m.end() and m.start() < b for a, b in phones)
        else re.sub(r"\D", "", m.group(0)), text)


def _amount_digits(raw):
    """How many digits count toward the bare number rule. After a dot or comma, 1 or 2 digits
    are a fraction or a date (28.10, 10.30), so only the whole part counts; 3 or more are
    thousands (1.500, 12,3456), so every digit counts."""
    head, *tails = re.split(r"[.,]", raw)
    if all(len(t) <= 2 for t in tails):
        return len(head)
    return sum(ch.isdigit() for ch in raw)


def _number(raw):
    """Digits as written, as a number: an int, or a Decimal when there is a fraction (16500.99 is not 16500).

    A decimal comma counts as a point (16500,99 is 16500.99). Past 20 digits the Decimal is kept,
    so turning it into text never hits Python's 4300 digit limit for ints.
    """
    if DECIMAL_COMMA.fullmatch(raw):
        raw = raw.replace(",", ".")
    d = Decimal(raw.replace(",", ""))
    if sum(ch.isdigit() for ch in raw) > MAX_INT_DIGITS:
        return d
    return int(d) if d == d.to_integral_value() else d


def _unit_after(text, m):
    """True when a unit follows the number in m (2 days), or a range up to a bigger number and
    a unit (2 to 3 days). "Shipping 70 to 3 days" is a fee, then a time."""
    u = UNIT_AFTER.match(text, m.end())
    return bool(u) and (u.group("to") is None or _number(m.group("n")) <= Decimal(u.group("to")))


def _sentence_ends(text, start, end, any_next=False):
    """SENTENCE_END matches from start to end, less a line end after a line that goes on (_goes_on)."""
    going_on = _lines_going_on(text, any_next)
    for e in SENTENCE_END.finditer(text, start, end):
        if e.group(0) == "\n" and e.start() in going_on:
            continue
        yield e


@functools.lru_cache(maxsize=16)
def _lines_going_on(text, any_next):
    """Where the line ends in text that go on into the next line are (_goes_on), worked out once
    per text. Each line end reads the last line with text before it and the first one after it,
    so lines with no letter, digit or # in between are passed over."""
    lines = text.split("\n")
    has_text = [TEXT_CHAR.search(line) is not None for line in lines]
    before, last = [], ""
    for line, has in zip(lines, has_text):
        last = line if has else last
        before.append(last)
    after, nxt = [""] * len(lines), ""
    for i in range(len(lines) - 1, -1, -1):
        nxt = lines[i] if has_text[i] else nxt
        after[i] = nxt
    out, pos = set(), -1
    for i in range(len(lines) - 1):
        pos += len(lines[i]) + 1   # the "\n" after line i
        if _goes_on(before[i], after[i + 1], any_next):
            out.add(pos)
    return frozenset(out)


def _goes_on(line, next_line, any_next):
    """True when line goes on into next_line: it ends in ":" or "=", or it ends in a cue word or
    holds a price word with no amount, and next_line starts with a number or #. With any_next, a
    line that ends in a cue word goes on into any next line."""
    if LINE_OPEN.search(line):
        return True
    cue_end = LINE_CUE_END.search(line) is not None
    if not (cue_end or _price_word_open(line)):
        return False
    return (any_next and cue_end) or NUMBER_FIRST.match(next_line) is not None


def _price_word_open(line):
    """True when the line has a price word and no amount with a currency ("Total comes to")."""
    return PRICE_WORD.search(line) is not None and MONEY not in line and PRICE.search(line) is None


def _price_word_before(text, pos):
    """True when a price word comes before pos in the same sentence."""
    start = max((e.end() for e in _sentence_ends(text, 0, pos)), default=0)
    return PRICE_WORD.search(text, start, pos) is not None


def _money_sentence(text, pos):
    """True when the sentence around pos has a price word or an amount with a currency. A line
    that ends in a cue word goes on into any next line here, so "Total\nis #1500" is one sentence."""
    start = max((e.end() for e in _sentence_ends(text, 0, pos, any_next=True)), default=0)
    end = next((e.start() for e in _sentence_ends(text, pos, len(text), any_next=True)), len(text))
    return (PRICE_WORD.search(text, start, end) is not None or MONEY in text[start:end]
            or PRICE.search(text, start, end) is not None)


def _given_orders_mask(text, orders):
    """Each order name in orders (#1001, given by a tool this turn) replaced by MASK where it
    stands whole: #1001 hides neither #10012 nor an amount with a currency (1001 جنيه)."""
    for name in orders or ():
        m = GIVEN_ORDER_NAME.fullmatch(str(name).translate(EASTERN_DIGITS).strip())
        if m:
            text = re.sub(r"#\s*" + re.escape(m.group(1)) + r"(?![\d.,]?\d)", MASK, text, flags=re.IGNORECASE)
    return text


def _order_mask(text):
    """Order numbers replaced by MASK: draft names (#D12) always, and # with up to 5 digits
    when an order word stands right before it or the sentence names no money (ORDER_NAME)."""
    text = DRAFT_NAME.sub(MASK, text)
    return ORDER_NAME.sub(
        lambda m: MASK if ORDER_WORD_BEFORE.search(text, 0, m.start()) or not _money_sentence(text, m.start())
        else m.group(0), text)


def _mask_phone(m):
    """MASK for a phone number written the way phone numbers are: one run of digits, or a head
    of up to 4 digits then 7 or 8, then 4 and 4, or 3 and 4 (010 1234 5678, +20 10 1234 5678,
    02 2345 6789, 03 4567890). Any other grouping of an Egyptian number ("010 500 12345",
    "+20 1500 0000 00") stays, so a price cannot hide in a phone shape (red team t261028j F7).
    Another country's number (+44 7700 900123) is masked as written."""
    return MASK if phone_shaped(m.group(0)) else m.group(0)


def phone_shaped(s):
    """True when a PHONE match is grouped the way a phone number is written (_mask_phone)."""
    if s.startswith("+") and not re.match(r"\+\s?20", s):
        return True
    prefix = EG_PREFIX.match(s)
    groups = re.split(r"[ -]", s[prefix.end():] if prefix else s)
    return len(groups) == 1 or (len(groups[0]) <= 4 and [len(g) for g in groups[1:]] in PHONE_GROUPS)


def amount_in_words(text):
    """True when the text holds an amount written in words that no currency word follows:
    after a price word or ب ("سعره ألف", "بخمسمية", "التوصيل بسبعين"), or 100 or more after
    any cue word ("The boots are two hundred"). "ألف شكر" and "for two days" are not amounts."""
    text = _plain(text)
    pos = 0
    while m := WORD_AMOUNT.search(text, pos):
        pos = m.start() + 1
        cue = m.group("price") or m.group("weak")
        if not (cue or m.group("glued")) or NOT_AN_AMOUNT_AFTER.match(text, m.end()):
            continue
        if MAGNITUDE.search(m.group("words")):
            return True
        strong = m.group("price") or m.group("glued") or (cue or "") in ("ب", "بـ")
        if strong and not ONE.fullmatch(m.group("words")) and not UNIT_AFTER.match(text, m.end()):
            return True
    return False


def _size_strings(sizes):
    """The catalogue's size strings, and the part in brackets of each ("40-45" from "Adult (40-45)")."""
    out = set()
    for s in sizes or ():
        s = str(s).translate(EASTERN_DIGITS).strip()
        if any(ch.isdigit() for ch in s):
            out.add(s)
            out |= {inner.strip() for inner in re.findall(r"\(([^()]*\d[^()]*)\)", s)}
    return sorted(out, key=len, reverse=True)


def _size_numbers(sizes):
    """Whole numbers the catalogue uses as sizes: 40 to 45 from "Adult (40-45)", 43 from "43".

    Measures like "12x8 cm" are left out.
    """
    out = set()
    for s in _size_strings(sizes):
        for a, b in re.findall(r"(?<![\dx.])(\d{1,3})\s*-\s*(\d{1,3})(?![\dx.])", s, re.IGNORECASE):
            lo, hi = int(a), int(b)
            if lo <= hi <= lo + 40:
                out.update(range(lo, hi + 1))
        for n in re.findall(r"(?<![\dx.-])(\d{1,3})(?![\dx.-])(?!\s*(?:cm|mm|سم))", s, re.IGNORECASE):
            out.add(int(n))
    return out


def _weak_size(text, m, size_numbers):
    """True when a cue match is a weak word, then a catalogue size number, with no price word
    earlier in the same sentence ("The Elite is available in 42 and 43")."""
    if _number(m.group("n")) not in size_numbers or not WEAK_CUE.fullmatch(m.group("cue")):
        return False
    start = max((e.end() for e in _sentence_ends(text, 0, m.start())), default=0)
    return PRICE_WORD.search(text, start, m.start("n")) is None


def _mask(text, sizes=(), orders=()):
    """The text with phone numbers, sizes, dates, address numbers, order numbers and years
    with a year word replaced by MASK, so no rule reads them as amounts. An address label reads
    as its address word (ADDRESS_LABEL). orders: order names a tool gave this turn."""
    text = _given_orders_mask(text, orders)
    text = ADDRESS_LABEL.sub(lambda m: m.group("ar") or m.group("fr") or m.group("en"), text)
    text = PHONE.sub(_mask_phone, text)
    for s in _size_strings(sizes):
        # A bare size ("43") is left to the size number rules (_weak_size), so after a price word
        # it is still an amount ("سعره 43") and a date keeps its day ("Oct 30, 2026").
        if BARE_SIZE.fullmatch(s):
            continue
        # Whole numbers only: the size "Kids 4" never hides part of "Kids 40".
        text = re.sub(r"(?<!\d)" + re.escape(s) + r"(?!\d)", MASK, text, flags=re.IGNORECASE)
    for pattern in (SIZE_CTX, DATES):
        text = pattern.sub(MASK, text)
    # An address number stays an amount when a price word comes earlier in the sentence
    # ("سعر التوصيل للبيت 120", "Delivery to your house 120"), as with order numbers (review t261028j 4).
    text = ADDRESS.sub(lambda m: m.group(0) if _price_word_before(text, m.start()) else MASK, text)
    return YEAR_CTX.sub(_mask_year, _order_mask(text))


def _mask_year(m):
    """The year in a YEAR_CTX match replaced by MASK, the year word or month kept."""
    g = "a" if m.group("a") else "b"
    return m.group(0)[:m.start(g) - m.start()] + MASK + m.group(0)[m.end(g) - m.start():]


def prices_in(reply, sizes=(), orders=(), names=()):
    """Every number in the reply that reads as an amount: ints, or Decimals for fractions.

    A number next to a currency word or sign always counts. A number after a price word, or
    right after a city or governorate (Cairo 70), counts unless it is a size, a date, an
    order number or has a unit after it (2 days).
    Any other standalone number of 3 or more digits counts too, unless it is a phone
    number (+44 7700 900123 too), a percentage, a year with a year word or month next to
    it, or masked as a size, date, order number (#1234, #D12) or address number (عمارة 125,
    Building 125).
    sizes: the catalogue's size strings, so "Adult (40-45)" is never read as an amount, and
    a size number after a weak word ("is available in 43") is read as a size. A bare size
    ("43") after a price word ("سعره 43") is still an amount.
    orders: order names a draft_order or find_order result gave this turn (#1001), read as
    order numbers wherever they stand whole.
    names: the store's product titles; a title's model number after its title word ("Phantom 6")
    is not read (without_model_numbers).
    """
    text = LE_RANGE.sub(r"\1to", without_model_numbers(reply, names))
    out = [_number(m.group(1) or m.group(2)) for m in PRICE.finditer(text)]
    masked = _mask(PRICE.sub(MONEY, text), sizes, orders)
    size_numbers = _size_numbers(sizes)
    counted = set()
    for m in CUE_AMOUNT.finditer(masked):
        if _unit_after(masked, m) or _weak_size(masked, m, size_numbers):
            continue
        counted.add(m.start("n"))
        out.append(_number(m.group("n")))
    for m in PLACE_AMOUNT.finditer(masked):
        if m.start("n") in counted or _unit_after(masked, m):
            continue
        counted.add(m.start("n"))
        out.append(_number(m.group("n")))
    for m in BARE_NUMBER.finditer(masked):
        raw = m.group("n")
        if m.start("n") in counted or _amount_digits(raw) < BARE_DIGITS:
            continue
        if _amount_digits(raw) <= WEIGHT_DIGITS and WEIGHT_AFTER.match(masked, m.end()):
            continue
        out.append(_number(raw))
    return out


def size_number_amounts(amounts, sizes):
    """Prices and fees that are also catalogue size numbers (45 with the boot sizes "40" to "45").

    After a weak word (is, for, ب) a size number reads as a size, so where prices sit among
    the size numbers, a wrong price there can pass the send check. Checked at start.
    """
    numbers = _size_numbers(sizes)
    return sorted({a for a in (amount(x) for x in amounts) if a is not None and a in numbers})


def stock_counts(reply, sizes=(), orders=(), names=()):
    """Exact stock counts stated in the reply ("3 left", "فاضل 2", "fadel 3").

    A catalogue size number is a size, not a count ("43 available"), and a model number after its
    title word is a model ("Phantom 6 available in 42").
    """
    masked = _mask(without_model_numbers(reply, names), sizes, orders)
    size_numbers = _size_numbers(sizes)
    return [m.group(0) for m in STOCK_COUNT.finditer(masked)
            if not all(len(n) <= 3 and int(n) in size_numbers for n in re.findall(r"\d+", m.group(0)))
            and not (m.group("goz") and ORDER_WORD.search(_sentence_at(masked, m.start(), m.end())))]


# "N جوز بس" in a sentence that names the order is the order, not a count: "el order 2 goz bs, size 43".
ORDER_WORD = re.compile(LETTER_BEFORE + r"(?:order|الأوردر|الاوردر|اوردرك|أوردرك|الطلب|طلبك)" + NO_LETTER_AFTER,
                        re.IGNORECASE)


def _sentence_at(text, start, end):
    """The sentence of text that holds text[start:end], cut at . ! ? ؟ and line ends."""
    head = max((text.rfind(c, 0, start) for c in ".!?\u061f\n"), default=-1)
    tails = [k for k in (text.find(c, end) for c in ".!?\u061f\n") if k >= 0]
    return text[head + 1:min(tails) if tails else len(text)]


def amount(x):
    """x as an amount (an int, or a Decimal when it has a fraction), or None for anything
    that is not a plain finite number. "16500.00" is 16500; "16500.50" stays 16500.50."""
    if isinstance(x, bool):
        return None
    if isinstance(x, str):
        if not AMOUNT_TEXT.fullmatch(x):
            return None
        x = x.replace(",", "").strip()
    elif not isinstance(x, (int, float)):
        return None
    try:
        f = float(x)
        if not math.isfinite(f):
            return None
        return _number(str(x))
    except (ValueError, OverflowError, InvalidOperation):
        return None


def amounts_in(obj):
    """Numbers under the exact keys price, fee, total or subtotal anywhere in a tool result.

    Strings are never parsed as JSON, so free text inside a result adds nothing.
    """
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in AMOUNT_KEYS:
                for x in (v if isinstance(v, list) else [v]):
                    n = amount(x)
                    if n is not None:
                        found.add(n)
            if isinstance(v, (dict, list)):
                found |= amounts_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= amounts_in(v)
    return found


def style_problems(text):
    """Feedback for the house style: banned words, dashes, spaced hyphens, emoji, markdown bold."""
    return [fb for _, fb in named_style(text)]


def named_style(text):
    """style_problems as (check name, feedback) pairs: banned, dashes, emoji or markdown."""
    problems = []
    low = (text or "").lower()
    for pattern, fix in BANNED:
        if pattern.search(low):
            problems.append(("banned", fix))
    if DASHES.search(text or ""):
        problems.append(("dashes", "Never use em dashes or en dashes. Use a comma or a full stop."))
    if any(not (a.isdigit() and b.isdigit()) for a, b in
           ((m.group(1), m.group(2)) for m in SPACED_HYPHEN.finditer(text or ""))):
        problems.append(("dashes", "Never use a hyphen with spaces as a dash. Use a comma or a full stop."))
    if EMOJI.search(text or ""):
        problems.append(("emoji", "No emoji."))
    if MARKDOWN_BOLD.search(text or ""):
        problems.append(("markdown", "No markdown. WhatsApp shows the ** as they are."))
    return problems


def check(reply, customer_text="", amounts=(), vocabulary=frozenset(), sizes=(), orders=(), links=(), names=()):
    """(passed, feedback) for one reply.

    amounts: every price and fee in the store and delivery data, plus amounts from this turn's store tools.
    vocabulary: lowercase words from product names and sizes, allowed in Latin letters inside an Arabic reply.
    sizes: the catalogue's size strings, so a size is never read as an amount.
    orders: order names a draft_order or find_order result gave this turn (#1001), so the order
    the customer just placed or asked about is never read as an amount; any other #number still counts.
    links: image links the store tool gave in this chat; any other link in the reply is refused.
    names: the store's product titles, so a model number ("Phantom 6") is never read as an amount.
    """
    problems = named_problems(reply, customer_text, amounts, vocabulary, sizes, orders, links, names)
    if problems:
        return False, " ".join(dict.fromkeys(fb for _, fb in problems))
    return True, ""


def named_problems(reply, customer_text="", amounts=(), vocabulary=frozenset(), sizes=(), orders=(), links=(),
                   names=()):
    """Every rule the reply breaks, as (check name, feedback) pairs, in the order check() gives
    them; [] when it passes. The names: empty, links, script, banned, dashes, emoji, markdown, sympathy,
    amounts, digits and stock. check() is this list joined, so the exam (reflection/exam.py) reads
    the same rules by name and never keeps a second copy of one."""
    if not (reply or "").strip():
        return [("empty", "The reply was empty. Write a reply to the customer.")]
    problems = []
    reply, wrong_links = _links(reply, links)
    if wrong_links:
        problems.append(("links", "Share only a product's image link from the store tool in this chat, exactly as "
                         "it gave it. No other links."))
    fb = _script_feedback(reply, customer_text, vocabulary, names)
    if fb:
        problems.append(("script", fb))
    problems += named_style(reply)
    low = reply.lower()
    for line in SYMPATHY:
        if line in low:
            problems.append(("sympathy", f'Remove the sympathy line ("{line}"). No sympathy lines; just answer.'))
            break
    allowed = {n for n in (amount(a) for a in amounts) if n is not None}
    wrong = sorted({p for p in prices_in(reply, sizes, orders, names) if p not in allowed})
    if wrong:
        nums = ", ".join(s if len(s) <= MAX_INT_DIGITS else s[:MAX_INT_DIGITS] + "..." for s in map(str, wrong))
        problems.append(("amounts", f"These amounts are not in the store or delivery data: {nums}. "
                         "Use only prices and fees from tool results, or say you will check with the team. "
                         "If a number is not a price, say what it is: size 43, 2 days, order #1234, model 2026."))
    digits = _plain(reply)
    if (SPELLED_AMOUNT.search(digits) or SHORT_AMOUNT.search(digits) or amount_in_words(digits)
            or model_thousands(digits, names) or store_word_thousands(digits, vocabulary, names)):
        problems.append(("digits", "Write every amount in digits, the number then the currency in the customer's "
                         "script (جنيه in Arabic, EGP in English, geneh in Franco), so it can be checked."))
    if stock_counts(reply, sizes, orders, names):
        problems.append(("stock", "Never give the exact stock count. If the store says few left, say only a few are "
                         "left; otherwise say it is in stock or out of stock."))
    return problems
