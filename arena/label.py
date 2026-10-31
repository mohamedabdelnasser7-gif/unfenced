"""Labels for the Arena replay (new, 2026-10-30): each chat won, lost or unclear, from the chat
itself, by the rules below, in code (DECISIONS item 21). No order record is joined: that
would need names or phones. Every text is read normalized (arena/clean.py normalize).

price    a store message gives a price: an amount with a currency (1450 جنيه, EGP 900), a price
         word with a number after it (السعر 1450, shipping 60; not a time such as الشحن بياخد 48
         ساعة or shipping takes 2 days) or an order summary.
won      after a store price line, the customer sends an address (arena/clean.py gives_address;
         a message with a question mark or a question word such as فين, بتوصلوا or can you
         counts only when it has an address number, as in عمارة 12), or the customer confirms
         the order (اكدلي, اطلبيه, هاخده, akkedly, I'll take it), not in a question, with no
         "no" in the three words before it and no "if" after it (هاخده لو نزل السعر), or the
         store writes that the order is placed (تم تسجيل الطلب, your order is confirmed; a price
         in that line counts) with no "once" or "if" after it in the same sentence.
lost     not won; a store price line was given; the store answered the customer's last message
         (text or media) and then the customer wrote nothing for QUIET_HOURS, counted up to the
         newest message of the whole import, as an export has no "now" of its own.
unclear  anything else, skipped and never guessed: no customer message; no store reply at all;
         a won sign before any price and none after it; a cancel or a voice note from the
         customer after the won sign; the customer's last message is a voice note, which could
         hold an address or a yes we cannot read; the customer's last message got no answer;
         the chat is still open (the store's last answer came within QUIET_HOURS of the newest
         message); or the customer went quiet with no price given.
"""
import re

from kit import send_check
from reflection import history as hist
from arena import clean

WON, LOST, UNCLEAR = "won", "lost", "unclear"
QUIET_HOURS = 48

# why, for the counts
ADDRESS = "address sent"
CONFIRMED = "order confirmed by the customer"
STORE_CONFIRMED = "order confirmed by the store"
QUIET = "quiet after the price"
NO_CUSTOMER = "no customer message"
NO_REPLY = "no store reply"
UNANSWERED = "last customer message not answered"
OPEN = "still open"
VOICE = "last customer message is a voice note"
CANCELLED = "cancelled after the won sign"
VOICE_AFTER = "voice note after the won sign"
EARLY = "won sign before any price"
NO_PRICE = "quiet with no price given"

L, R = send_check.LETTER_BEFORE, send_check.NO_LETTER_AFTER
CONFIRM = re.compile(L + r"(?:"
                     r"[اأ]كد(?:ي|ه|يه|ها|يها|وه|وها)?(?:لي|لى|ولي)?"
                     r"|[اإ]طلب(?:ي|و)?(?:ه|ها|هم)(?:ولي|لي|لى)?"
                     r"|[اإ]بعت(?:ي|و)?(?:ه|ها|هم)(?:ولي|لي|الي|ولى)"
                     r"|هاخد(?:ه|ها|هم)|هاخد\s+(?:ده|دي|دا)|اتفقنا|تم\s+الاتفاق"
                     r"|2?akk?ed(?:ly|li|o|ha|eh|y)?|otlob(?:o|ha|oly|holy)|eb3at(?:o|ha)(?:ly|li)"
                     r"|ha5do|ha5odha|hakhdo|hakhodha"
                     r"|i'?ll\s+take\s+(?:it|them|one)|i\s+will\s+take\s+(?:it|them|one)"
                     r"|place\s+(?:the|my)\s+order|confirm(?:ed)?(?=\s*(?:$|[.!]|(?:it|the\s+order|my\s+order"
                     r"|order|please|pls)" + R + r"))"
                     r")" + R, re.IGNORECASE)
NO_BEFORE = frozenset({"مش", "مو", "لا", "لأ", "ما", "بلاش", "not", "dont", "don't", "no", "won't", "wont", "msh",
                       "mesh", "mish", "la2", "bala"})
IF_AFTER = re.compile(r"\s*(?:[,،]\s*)?(?:(?:بس|bas)\s+)?(?:لو|law|lw|if)" + R, re.IGNORECASE)
STORE_PLACED = re.compile(L + r"(?:تم\s+(?:تسجيل|تأكيد|تاكيد)\s+(?:ال)?(?:طلب|[اأ]وردر)|(?:ال)?(?:طلب|[اأ]وردر)(?:ك|كم)?"
                          r"\s+(?:اتسجل|اتأكد|اتاكد|تم\s+تسجيله|تم\s+تأكيده)|اتسجل\s+(?:ال)?(?:طلب|[اأ]وردر)"
                          r"|(?:your\s+)?order\s+(?:is|has\s+been|was)\s+(?:confirmed|placed)|order\s+confirmed"
                          r"|el\s?order\s+(?:et|it)sagel|et2aked\s+el\s?order)" + R, re.IGNORECASE)
LATER_IF = re.compile(L + r"(?:once|(?:when|after)\s+(?:you|u|we|i|the)|as\s+soon\s+as|if|لما|بمجرد|[اأ]ول\s+ما|بعد\s+ما"
                      r"|لو)" + R, re.IGNORECASE)
CANCEL = re.compile(L + r"(?:[اأإ]لغ(?:ي|ى|يه|يها|يلي|وه|وا)|[اإ]لغاء|cancel(?:led|ed)?|el[g8]i|elghi|el8eeh"
                    r"|مش\s+(?:عايز|عاوز|عايزة|عاوزة)(?:ه|ها|هم)|msh\s+3ayz(?:o|ha)|mesh\s+3ayz(?:o|ha)"
                    r"|(?:لا|لأ|خلاص)(?:\s+خلاص)?\s+مش\s+(?:عايز|عاوز|عايزة|عاوزة|عايزه|عاوزه)"
                    r"|(?:la2|la|khalas|5alas)(?:\s+(?:khalas|5alas))?\s+(?:msh|mesh|mish)\s+3a[yw]e?z"
                    r"|don'?t\s+want\s+it)" + R, re.IGNORECASE)
ASK_WORDS = re.compile(L + r"(?:فين|بتوصلوا|توصلوا|ينفع|[اإ]زاي|[اإ]يه|كام|بكام|[اإ]مت[يى]|عندكم|do\s+you|can\s+you"
                       r"|is\s+it)" + R, re.IGNORECASE)
# a time after the number is a delivery time, not a price: الشحن بياخد 48 ساعة, shipping takes 48 hours,
# also as a range (24 ل 48 ساعة, 48-72 hours, 48 to 72 hours) or a clock time (10 am, 10 الصبح, 10:30).
# يوم with a day name or a date after it is a day, so the number before it stays a price (السعر 850 يوم
# الخميس), and a number after يوم or الساعة is a date or a clock time (الشحن يوم 30/10).
DAY_NAME = (r"(?:ال)?(?:سبت|[اأ]حد|[اإ]?[تث]نين|[اإ]ثنين|[تث]لا[تث]اء?|[تث]لات|[اأ]ربع(?:اء)?|خميس|جمع[ةه]|جاي"
            r"|saturday|sunday|monday|tuesday|wednesday|thursday|friday)")
TIME_WORD = (r"(?:ساع[ةه]|ساعات|ساعتين|يوم(?!\s+(?:" + DAY_NAME + r"|\d))|يومين|[اأ]يام|[اأ]سبوع|[اأ]سبوعين"
             r"|[اأ]سابيع|دقيق[ةه]|دقايق|دقائق|س|sa3a|sa3at|yom|youm|ayam|hours?|hrs?|h|days?|weeks?|wks?|minutes?"
             r"|mins?)" + R)
CLOCK = r"(?:[ap]\.?m\.?|الصبح|صباحا|صباحاً|بالليل|بليل|مساء|مساءا|مساءً|الضهر|العصر|المغرب)" + R
RANGE = r"\s*(?:-|\u2013|/|الى|إلى|ل|لـ|to|or|او|أو)\s*\d{1,3}"
TIME_AFTER = r"(?:(?:" + RANGE + r")?\s*" + TIME_WORD + r"|\s*" + CLOCK + r"|:\d{2}|/\d{1,2}(?!\d))"
PRICE_WORD_NUMBER = re.compile(send_check.PRICE_WORD.pattern + r"\s*[:=\-]?\s*"
                               r"(?:(?!(?:يوم|الساع[ةه])" + R + r")[^\W\d_]+\s+){0,2}\d{2,}"
                               r"(?!\d|" + TIME_AFTER + r")", re.IGNORECASE)
SUMMARY = re.compile(L + r"(?:ملخص\s+(?:ال)?(?:طلب|[اأ]وردر)|order\s+summary)" + R, re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?؟\n]")


def gave_price(text):
    """True when a store message gives a price (see price above)."""
    if not text:
        return False
    plain = clean.normalize(text)
    return bool(send_check.PRICE.search(plain) or PRICE_WORD_NUMBER.search(plain) or SUMMARY.search(plain))


def sends_address(text):
    """True when a customer's message gives an address; a question needs an address number."""
    if not text:
        return False
    plain = clean.normalize(text)
    asks = clean.QUESTION.search(plain) or ASK_WORDS.search(plain)
    return hist.gives_address(plain) or (not asks and clean.gives_address(plain))


def confirms(text):
    """True when a customer's message confirms the order: not a question, no "no" just before,
    no "if" just after."""
    if not text:
        return False
    plain = clean.normalize(text)
    if clean.QUESTION.search(plain):
        return False
    for m in CONFIRM.finditer(plain):
        before = re.findall(r"[\w']+", plain[:m.start()].casefold())[-3:]
        if not NO_BEFORE.intersection(before) and not IF_AFTER.match(plain, m.end()):
            return True
    return False


def store_placed(text):
    """True when a store's message says the order is placed or confirmed, with no question and
    no "once" or "if" after it in the same sentence."""
    if not text:
        return False
    plain = clean.normalize(text)
    if clean.QUESTION.search(plain):
        return False
    for m in STORE_PLACED.finditer(plain):
        rest = SENTENCE_END.split(plain[m.end():], 1)[0]
        if not LATER_IF.search(rest):
            return True
    return False


def cancels(text):
    return bool(text) and bool(CANCEL.search(clean.normalize(text)))


def label(chat, newest, quiet_hours=QUIET_HOURS):
    """(won, lost or unclear, why) for one reflection/history.py Chat. newest: the time of the
    newest message in the whole import."""
    msgs = chat.messages
    customer = [i for i, m in enumerate(msgs) if not m.team]
    if not customer:
        return UNCLEAR, NO_CUSTOMER
    if not any(m.team for m in msgs):
        return UNCLEAR, NO_REPLY
    priced, early = False, False
    for i, m in enumerate(msgs):
        why = None
        if m.team and gave_price(m.text):
            priced = True
        if not m.team and sends_address(m.text):
            why = ADDRESS
        elif not m.team and confirms(m.text):
            why = CONFIRMED
        elif m.team and store_placed(m.text):
            why = STORE_CONFIRMED
        if why is None:
            continue
        if not priced:
            early = True
            continue
        later = [x for x in msgs[i + 1:] if not x.team]
        if any(cancels(x.text) for x in later):
            return UNCLEAR, CANCELLED
        if any(x.media == "audio" for x in later):
            return UNCLEAR, VOICE_AFTER
        return WON, why
    if early:
        return UNCLEAR, EARLY
    last = customer[-1]
    if msgs[last].media == "audio":
        return UNCLEAR, VOICE
    answers = [m for m in msgs[last + 1:] if m.team and (m.text or m.media)]
    if not answers:
        return UNCLEAR, UNANSWERED
    if newest - answers[-1].at < quiet_hours * 3600:
        return UNCLEAR, OPEN
    if not priced:
        return UNCLEAR, NO_PRICE
    return LOST, QUIET
