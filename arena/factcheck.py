"""Fact checks on every Sales agent reply in an Arena match (new, 2026-10-30), in code, against
the store's own data (kit/tools/store.py catalogue and delivery, demo/governorates.json):

price     every amount in the reply (kit/send_check.py prices_in) is a price of a product the
          reply names, a delivery fee, one price plus one fee, or an amount a tool gave this
          turn (a draft order's total). With no product named, any store price counts. A tier
          the reply names (Elite, Pro; else one the customer's line names) narrows the prices to
          that tier's, and in a clause that names one tier its amounts must be that tier's prices:
          the Pro price given for an Elite boot is a wrong price. An extra (store.extras: the name
          printing) goes on any product, so a price plus an extra, with or without one fee, counts
          whatever product the reply names (2026-10-31). The extra's own price counts only in a
          clause that names the extra (extras_named: its title, type and description words, with
          their Arabic and Franco spellings), or in a clause that names no product and no tier
          when the reply names the extra elsewhere (or, naming nothing, the customer's line does)
          and its sentence names no boot and no tier: "The Vapor 17 Elite is 400 EGP" fails,
          "الطباعة 400 جنيه" passes (2026-10-31). A clause that names a boot or a tier and the
          extra holds the extra's price only beside a sum, or when the boot comes first with no
          joining word between ("For the Vapor 17 Elite the printing is 400 EGP" passes, "The
          Vapor 17 Elite with printing is 400 EGP" fails) or with the boot's own price before
          the extra and the extra's amount right after it, past the rest of the extra's title and
          an own price word (سعرها, its price) ("The Vapor 17 Elite is 16,500 EGP with printing 400
          EGP" passes), or when the extra comes first as the
          clause's subject ("Printing on the Vapor 17 Elite is 400 EGP" passes, "With printing the
          Vapor 17 Elite is 400 EGP" fails) (_extra_not_held; red team gatefb rounds 1 and 2,
          review gatefb round 2). An add-on word right beside the amount (more, extra, plus, on
          top, زيادة; a whole word, and after the amount only at the clause end or before a
          currency word, for, on, to, if, with, and, each, عشان, لو or و) keeps the price of the
          extra its clause names, else of one its sentence names; in a clause with a boot or a
          tier only an extra named before the amount: "If you add printing to the Elite, it's 400
          EGP more" passes (DECISIONS item 52); "The Elite is 400 EGP more, and printing is
          available too", "400 EGP more or so" and "The Vapor 17 Elite is 400 EGP extra. We can
          also print your name." fail (review gatefb rounds 1 and 2). Hidden format characters
          are dropped from the reply first. An extra named only
          in another sentence, or only in the customer's line, never makes an add-on amount. For
          this rule a colon, a bracket and a spaced dash cut a clause too, and a
          clause that names no product and no tier takes those of the clauses before it in its
          sentence (red team round 2). A model number in a product's title (the 17 in Vapor 17,
          the 50 in F50) is never an amount, unless a currency or thousands word follows it.
size      a size number after a size word (مقاس 43, size 43, EU 43) fits a size of a product
          the reply names, or of any product when it names none.
stock     a reply that says a named product (and size, when it gives one) is available while
          the store has it out fails; so does one that says it is out while the store has it.
          A clause that says a product (or a size of it) is in stock, in Arabic, Franco or English,
          fails when the store gives no stock data for it (Arena run 20261104T143545, cause 7: an
          untracked variant has no stock field, kit/tools/store.py). Left out: an extra, a question,
          a clause about delivery or payment, and an unsure clause ("I cannot confirm stock",
          "مش متأكد", "mesh met2aked"), so the honest answer passes. "Available for pre-order"
          ("متاح للحجز") claims no stock (decision 108): "size 43 is out of stock, you can pre-order
          it with 20% down" passes when 43 is out.
delivery  an amount in a sentence about delivery is a delivery fee (the named governorate's
          zone fee when the reply names one); a count of days there sits inside the zones' days
          (the named zone's when it names one), or within the store's pre-order days in a sentence
          that talks about a pre-order (decision 108). A count of days an exchange or return word governs
          (exchange_days) is the exchange window, not a delivery time. Every fee is the zone's fee
          after the store's delivery offer (kit/offers.py delivery_fee, 2026-11-04): under free
          delivery it is 0, so the zone's old fee is no fact and fails.
order     a reply that says the order is placed or confirmed (claims_order below) passes only
          when a tool placed an order this turn (draft_order created): in a match the agent is
          the store, so its own claim is never a sale.

check(reply, customer_text, tool_results, orders) returns the failed checks as
[{"check", "why"}]; an empty list is a pass. Products are named by the words of their title
after the store name, all of them or all but the first (the maker: "Mercurial Vapor" names "Nike
Mercurial Vapor 17"), in the reply or, when the reply names none, in the customer's line. Tiers
are named by their word from the store data ("Elite"), the same way.
"""
import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from arena import clean, label
from kit import offers, send_check, tools
from kit.tools import draft_order, store

ROOT = Path(__file__).resolve().parent.parent
GOVERNORATES = ROOT / "demo" / "governorates.json"
STORE_NAME = "beyond the limits"
CHECKS = ("price", "size", "stock", "delivery", "order")

SIZE_NUMBER = re.compile(r"(?<!\w)(?:sizes?|مقاس(?:ات)?|المقاس|بمقاس|ma2as|eu)\s*[:#]?\s*(\d{2})(?!\d)", re.IGNORECASE)
CLAIM_SENTENCE = re.compile(r"(?:[^.!?؟\n]|(?<=\d)\.(?=\d))+[.!?؟]*")  # a decimal point does not end it
CLAIM_CLAUSE = re.compile(r"[,،;:]")
ORDER_CLAIM = re.compile(
    label.L + r"(?:تم\s+(?:ال)?(?:طلب|[اأ]وردر)"
    r"|تم\s+(?:تسجيل|تأكيد|تاكيد|عمل|حجز)\s+(?:ال)?(?:طلب(?:ية)?|[اأ]وردر|حجز)(?:ك|كم)?"
    r"|(?:ال)?(?:طلب(?:ية)?|[اأ]وردر)(?:ك|كم)?(?:\s+بتاع(?:ك|كم|كي))?\s+(?:اتسجل|اتأكد|اتاكد|اتعمل|اتحجز"
    r"|تم\s+(?:تسجيله|تأكيده|تاكيده))"
    r"|(?:اتسجل|اتأكد|اتاكد|اتعمل)\s+(?:ال)?(?:طلب|[اأ]وردر)"
    r"|(?:سجلت|[اأ]كدت|عملت)(?:لك|لك[يى])?\s+(?:ال)?(?:طلب|[اأ]وردر)"
    r"|طلبك\s+(?:في|ف)\s+الطريق"
    r"|(?:order|purchase|booking)(?:\s*#\s*\d+)?(?:'s|\s+is|\s+has\s+been|\s+was|\s+got)?\s+(?:now\s+|successfully\s+)?"
    r"(?:confirmed|placed|booked|registered|submitted|created)"
    r"|(?:order|purchase)(?:'s|\s+is)\s+(?:all\s+set|on\s+(?:its|the)\s+way)|order\s*:\s*confirmed"
    r"|(?:placed|confirmed|booked|registered|submitted|created)\s+(?:your|the|ur)\s+order"
    r"|(?:placed|created|booked|made)\s+(?:an|a|the)\s+order\s+for\s+you|(?:received|got)\s+your\s+order"
    r"|el\s?order\s+(?:et|it)sagel|et2aked\s+el\s?order|(?:el\s?)?order(?:-?ak)?\s+(?:et|it)(?:sagel|2aked)"
    r"|talabak\s+(?:et|it)(?:sagel|2aked)|tm\s+ta2keed\s+el\s?order|3amaltlak\s+el\s?order)" + label.R, re.IGNORECASE)
# a condition anywhere before the claim in its sentence: "If you reply yes, your order is confirmed"
CLAIM_LEAD = re.compile(
    label.L + r"(?:if|once|unless|as\s+soon\s+as|when|after|before|until|reply|say\s+yes|just\s+say|to\s+get"
    r"|لو|لما|بمجرد|[اأ]ول\s+ما|بعد\s+ما|قبل\s+ما|عشان|علشان|law|lw|lama)" + label.R, re.IGNORECASE)
# a negation, a may-be or a then before the claim in its own clause: "I can have your order placed"
CLAIM_NEAR = re.compile(
    label.L + r"(?:not|\w+n't|never|yet|can|could|will|would|should|shall|may|might|then"
    r"|مش|لسه|لسة|لم|ممكن|هل)" + label.R, re.IGNORECASE)
# a condition right after the claim: "Your order is confirmed once you reply", "... right after"
CLAIM_AFTER = re.compile(
    r"\s*(?:only|then|after|once|when|if|until|unless|as\s+soon|right\s+after|before"
    r"|بعد|لما|لو|بمجرد|[اأ]ول\s+ما|قبل)" + label.R, re.IGNORECASE)
CLAIM_QUESTION = re.compile(
    r"^\s*(?:is|are|was|were|do|does|did|can|could|shall|should|will|would|may|هل|ممكن|تحب|تحبي)" + label.R,
    re.IGNORECASE)
SIZE_LETTER = re.compile(r"(?<![\w])(XS|S|M|L|XL)(?![\w])")
EU_RANGE = re.compile(r"(\d{2})\s*-\s*(\d{2})")
EU_ONE = re.compile(r"(?:EU\s*)?(\d{2})", re.IGNORECASE)
OUT = re.compile(r"(?<!\w)(?:خلص(?:ت|ان)?|نفذ(?:ت)?|مش\s+(?:متاح|متوفر|موجود)[ةه]?|غير\s+متوفر[ةه]?|out\s+of\s+stock|sold\s+out|"
                 r"not\s+available|unavailable|msh\s+(?:mawgood|motaa7|metwafar)|5ls|khalas)(?!\w)", re.IGNORECASE)
AVAILABLE = re.compile(r"(?<!\w)(?:متاح[ةه]?|متوفر[ةه]?|موجود[ةه]?|available|in[\s-]+stock|mawgood|motaa7|metwafar|"
                       r"mawgou?da?|mawgooda|motaa7a|metwaff?a?r[ae]?|motawaff?era?|(?:fel|fe|fl|f\s+el)\s+(?:stock|makhzan)|"
                       r"(?:في|فى)\s+(?:المخزن|الستوك|المخزون))(?!\w)",
                       re.IGNORECASE)
# A clause that does not claim stock: unsure, or about delivery or payment (cash on delivery is available).
UNSURE = re.compile(r"(?<!\w)(?:can(?:no|')?t\s+(?:confirm|promise|say|check)|unable\s+to\s+confirm|not\s+sure|"
                    r"no\s+stock\s+(?:data|info)|مش\s+متأكد[ةه]?|مقدرش\s+[اأ]?[اأ]كد|مش\s+هقدر\s+[اأ]?[اأ]كد|"
                    r"مش\s+عارف|mesh\s+met2aked[ae]?|msh\s+met2aked[ae]?|ma2darsh\s+a2aked|mesh\s+3aref)(?!\w)",
                    re.IGNORECASE)
PAYMENT = re.compile(r"(?<!\w)(?:cash|payment|pay|cod|الدفع|كاش|دفع|الكاش|kash|el\s+daf3|daf3)(?!\w)", re.IGNORECASE)
DELIVERY = re.compile(r"(?<!\w)(?:شحن|الشحن|توصيل|التوصيل|delivery|shipping|tawseel|sha7n|courier)(?!\w)", re.IGNORECASE)
DAYS = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:(?:-|to|او|أو|ل|الى|إلى|و|or)\s*(\d{1,2})\s*)?"
                  r"(?:(?:working|business)\s+)?(?:days?|يوم|أيام|ايام|yom|youm|ayam)(?!\w)", re.IGNORECASE)
# An available word followed by a pre-order ("available for pre-order", "متاح للحجز") claims no stock (decision 108).
AS_PREORDER = re.compile(r"\s*(?:(?:for|to|as|on|by)\s+)?(?:an?\s+)?(?:pre[\s-]?order)|\s*(?:لل|بال|ك)?حجز|"
                         r"\s*(?:لل|بال)?طلب\s+(?:ال)?مسبق", re.IGNORECASE)
TWO_DAYS = re.compile(r"(?<!\w)(?:يومين|yomein|youmein)(?!\w)", re.IGNORECASE)
# an exchange, return or swap word: a count of days it governs is the exchange window, not a delivery time
# ("ممكن تبدل المقاس خلال 14 يوم", Arena run 2026-10-31)
EXCHANGE = re.compile(
    r"(?<!\w)(?:(?:[وف]?(?:بال|لل|ال|ب|ل)?(?:تبديل|استبدال|ترجيع|استرجاع|مرتجع)"
    r"|[وف]?(?:هت|ت|ي|ن|ا|أ)?(?:تبدل|ترجع)|[وف]?(?:هت|ت|ي|ن|ا|أ)(?:بدل|رجع))\w*"  # not a bare بدل (instead of)
    r"|exchang\w*|returns?|returned|returning|swap\w*|refund\w*"
    r"|t[ae]?ba?d[ae]?l\w*|ta?bdee?l\w*|[ei]?st[ae]?bdal\w*|t[ae]?r[gj](?:a|ee?|i)?3\w*)(?!\w)", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?؟\n]+")
# a clause for the tier rule: cut at an end mark, a new line, ؛ ; ، or a comma that is not inside
# a number (16,500 stays whole); a decimal point does not end it
TIER_CLAUSE = re.compile(r"(?:[^.!?؟\n,،;؛]|(?<=\d)[.,](?=\d))+")
# For the extra price rule: a sentence (a decimal point does not end it), and its clauses, cut as
# above and at a colon too ("The Vapor 17 Elite with printing: 400 EGP"), but not at one inside a
# time or a number (10:30)
PRICE_SENTENCE = re.compile(r"(?:[^.!?؟\n]|(?<=\d)\.(?=\d))+")
EXTRA_CLAUSE = re.compile(r"(?:[^.!?؟\n,،;؛:]|(?<=\d)[.,:](?=\d))+")
# A bracket or a spaced dash sets an aside apart like a comma does, for the extra price rule only: "The
# Vapor 17 Elite (with printing) is 400 EGP" (review round 3, item 4). The marks become ";", which
# EXTRA_CLAUSE cuts at and which never sits inside a number.
ASIDE = re.compile(r"[()\[\]]|(?<=\s)[-\u2013\u2014](?=\s)")
# An add-on word right beside an amount in its clause, with at most a currency word between (DECISIONS
# item 52): "400 EGP more", "400 extra", "400 on top", "400 جنيه زيادة", "plus 400", "+ 400", "an extra
# 400", "زيادة 400". Such an amount is said to go on top of something, so an extra's price there is the extra's.
ADDON_WORDS = r"more|extra|on\s+top|زيادة|زياده"
# An add-on word after the amount counts only where its clause ends or one of these words follows: a
# currency word, for, on, to, if, with, and, each, عشان, لو, or و. So "400 EGP more or so", "more-or-less",
# "more costly", "extra large" and "زيادة على الـ Pro" are no add-on: a list of the words that make it
# none can never be whole (review gatefb round 2, finding 2; red team gatefb round 2, item B).
ADDON_AFTER = (r"(?=[^\w\n]*$|[^\S\n]+(?:(?:" + send_check.CURRENCY + r"|for|on|to|if|with|and|each|عشان|لو)"
               + send_check.NO_LETTER_AFTER + r"|و))")
ADDON = re.compile(
    send_check.LETTER_BEFORE + r"(?:(?:plus|(?:an\s+)?extra|زيادة|زياده)[^\S\n]+|\+[^\S\n]*)(" + send_check.DIGITS + r")(?![\d.,]\d)"
    r"|(?<![\d.,])(" + send_check.DIGITS + r")[^\S\n]*(?:" + send_check.CURRENCY + r")?[^\S\n]*(?:" + ADDON_WORDS + ")"
    + send_check.NO_LETTER_AFTER + ADDON_AFTER, re.IGNORECASE)
# For a clause that names a boot or a tier and an extra: a word that joins the extra to the boot before
# it, so the clause's amount is the boot's with the extra on it ("The Vapor 17 Elite with printing is
# 400 EGP"), and "and", which joins them only with no amount between: "The Elite and printing is 400
# EGP" joins, "The Elite is 16,500 EGP and the name printing 400 EGP" gives each its own price. With
# none of these the boot only says which boot: "For the Vapor 17 Elite the printing is 400 EGP" (review
# gatefb round 2, finding 5). An extra written with the Arabic ب (with) or و (and) joins the same way.
JOIN = re.compile(r"(?<![^\W_])(?:with|w/|plus|including|incl|ma3|m3|مع)(?![^\W_])|\+", re.IGNORECASE)
AND = re.compile(r"(?<![^\W_])(?:and|w|و)(?![^\W_])|&", re.IGNORECASE)
# The words an extra's clause may open with before the extra and still have it as the clause's subject
# ("The printing", "Your name"), and the words that put it beside the boot after it, before any amount
# ("Printing on the Elite", "الطباعة على الـ Elite"). "With printing the Vapor 17 Elite is 400 EGP" opens
# with neither and does not hold the extra's price (red team gatefb round 2, item A).
SUBJECT_LEAD = re.compile(r"(?:(?:and|also|so|but|then|the|a|an|your|our|its|his|her|their|my|this|el|al|ال\w*)\W+)*",
                          re.IGNORECASE)
TOWARD = re.compile(r"(?<![^\W_])(?:on|onto|for|to|of|in|في|على|عل|ع|لل\w*|لـ)(?![^\W_])", re.IGNORECASE)
# Arabic and Franco spellings of an English word stem. Used only for a stem an extra's own title,
# type or description carries (extra_words), so an extra with none of these stems gets none of them.
STEM_FORMS = {
    "print": r"[وف]?(?:بال|لل|ال|ب|ل)?طباع[ةه]?|[وف]?[هب]?[نتياأ]{0,2}طبع\w*|[وف]?(?:بال|ال)?مطبوع\w*"
             r"|\w{0,3}t[ie]?ba3\w*",
    "name": r"[وف]?(?:بال|لل|ال|ب|ل)?[اإأ]سم(?:ك|كم|كي|ي|ه|ها|نا|ين)?|[ie]sm(?:ak|ek|ik|y|i|o|ena|ko)?",
    "sticker": r"[وف]?(?:بال|لل|ال|ب|ل)?[اإ]?ستيكر\w*|e?sti(?:c?k|ck)er\w*",
}
EXTRA_DESCRIPTION_LETTERS = 5   # a description word this long or longer names its extra ("stickers", not "with")


def _words(text):
    return set(re.findall(r"[a-z]+", (text or "").casefold()))


def products_named(text, items):
    """The catalogue items whose title words (after the store name) all show in text, or all but
    the first word (the maker, often left out: "Mercurial Vapor" for "Nike Mercurial Vapor 17")."""
    have = _words(text)
    out = []
    for item in items:
        title = re.findall(r"[a-z]+", (item.get("title") or "").casefold().replace(STORE_NAME, ""))
        need, rest = set(title), set(title[1:])
        if (need and need <= have) or (rest and rest <= have):
            out.append(item)
    # a title whose words all sit inside a longer named title ("Phantom" inside "Phantom Club")
    # gives way to the longer one; keep the longest titles only
    return [i for i in out if not any(o is not i and _words(i["title"]) < _words(o["title"]) for o in out)]


def _stem(word):
    for end in ("ing", "ed", "s"):
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[:-len(end)]
    return word


def extra_words(extra, items):
    """The word stems that name an extra, from its own data: its title words after the store name
    and its type ("name", "print"), and its description's long words that no other product's title,
    type or description uses and that are no tier or delivery word ("sticker" from "two stickers")."""
    def text_words(item, fields):
        text = " ".join(str(item.get(f) or "") for f in fields).casefold()
        return re.findall(r"[a-z]+", text.replace(STORE_NAME, ""))
    others = set()
    for i in items:
        if i is not extra:
            others |= set(text_words(i, ("title", "type", "description")))
    tiers = {t.casefold() for t in store.tiers()}
    own = set(text_words(extra, ("title", "type")))
    own |= {w for w in text_words(extra, ("description",)) if len(w) >= EXTRA_DESCRIPTION_LETTERS
            and w not in others and w not in tiers and not DELIVERY.fullmatch(w)}
    return sorted({_stem(w) for w in own if len(w) >= 3})


def extras_named(text, extras, items, kind=False):
    """The extras whose words (extra_words, in English or with their STEM_FORMS spellings) show in text:
    "printing", "your name", "two stickers", "الطباعة", "اسمك", "استيكرين". With kind, only the words
    of the extra's type ("Printing": "printing", "الطباعة", not "your name", which an order asks for)."""
    return [e for e in extras if _extra_match(e, text, items, kind)]


def _extra_match(e, text, items, kind=False):
    """The first place text names the extra e (extras_named), or None."""
    stems = sorted({_stem(w) for w in re.findall(r"[a-z]+", str(e.get("type") or "").casefold())
                    if len(w) >= 3}) if kind else extra_words(e, items)
    forms = [re.escape(s) + r"[a-z]*" for s in stems] + [STEM_FORMS[s] for s in stems if s in STEM_FORMS]
    return re.search(r"(?<!\w)(?:" + "|".join(forms) + r")(?!\w)", text or "", re.IGNORECASE) if forms else None


def _names_boot(text, items, extras, all_tiers):
    return bool(tiers_named(text, all_tiers) or _boots(products_named(text, items), extras))


def _boot_end(text, items, extras, all_tiers):
    """Where text first has named a boot or a tier: the end of the word that completes it, or None."""
    for m in re.finditer(r"\w+", text):
        if _names_boot(text[:m.end()], items, extras, all_tiers):
            return m.end()
    return None


def _extra_not_held(clause, extras, items, all_tiers, sizes, orders):
    """True when a clause that names a boot or a tier and an extra does not hold the extra's own
    price. With the boot first: when an extra's price sits between them ("The Vapor 17 Elite is 400 EGP
    more and printing is included", review gatefb round 2, finding 1), when a joining word sits between
    them (JOIN, or AND with no amount between), or the extra is written with ب or و: "The Vapor 17 Elite
    with printing is 400 EGP",
    "The Elite and printing is 400 EGP", "The Vapor 17 Elite was 16,500 EGP and with printing is 400
    EGP" (red team gatefb round 1, item 1; round 2, item A); "For the Vapor 17 Elite the printing is
    400 EGP" holds it (review gatefb round 2, finding 5). With the extra first: unless it is the
    clause's subject, opening it (SUBJECT_LEAD) without ب or ل on it, with an amount or a word that
    puts it on the boot (TOWARD) before the boot: "Printing on the Vapor 17 Elite is 400 EGP" holds
    it, "With printing the Vapor 17 Elite is 400 EGP" and "Printed the Vapor 17 Elite is 400 EGP" do
    not. False when the clause names no extra or no boot."""
    found = [m for m in (_extra_match(e, clause, items) for e in extras) if m]
    if not found or not _names_boot(clause, items, extras, all_tiers):
        return False
    first = min(found, key=lambda m: m.start())
    word = re.sub(r"^[وف]", "", first.group(0))
    end = _boot_end(clause[:first.start()], items, extras, all_tiers)
    if end is not None:  # the boot first
        gap = clause[end:first.start()]
        mine = _dec(send_check.amount(v["price"]) for e in extras for v in e.get("variants", []) if "price" in v)
        if _dec(send_check.prices_in(gap, sizes, orders)) & mine:  # its price beside the boot, before the extra
            return True
        if _own_price_then_extra(gap, clause[first.end():], items, extras, sizes, orders):
            return False
        if re.fullmatch(r"[a-z]+ed|(?:ال)?مطبوع\w*", word, re.IGNORECASE):  # a participle: the boot printed
            return True
        return bool(JOIN.search(gap) or word.startswith("ب")
                    or ((AND.search(gap) or first.group(0).startswith("و"))
                        and not send_check.prices_in(gap, sizes, orders)))
    lead = clause[:first.start()]
    if SUBJECT_LEAD.fullmatch(lead.lstrip(" \t\"'“”‘’")) is None or word.startswith(("ب", "ل")):
        return True
    after = clause[first.end():]
    reach = after[:_boot_end(after, items, extras, all_tiers)]
    return not (TOWARD.search(reach) or send_check.prices_in(reach, sizes, orders))


def _own_price_then_extra(gap, after, items, extras, sizes, orders):
    """True when a boot price ends the gap or comes right before its first joining word, only
    SUBJECT_LEAD words follow that word, and an amount follows the extra at once: "The Vapor 17 Elite
    is 16,500 EGP with printing 400 EGP" and "الـ Vapor 17 Elite بـ 16,500 جنيه بالطباعة 400 جنيه" name
    each its own price. "The Vapor 17 Elite was 16,500 EGP and with printing 400 EGP", "The Vapor 17
    Elite is 16,500 EGP with printing is 400 EGP" and "The Vapor 17 Elite is 60 EGP with printing 400
    EGP" (a fee) do not (gatefb round 2 fix, call 8)."""
    join = JOIN.search(gap)
    before, between = (gap, "") if join is None else (gap[:join.start()], gap[join.end():])
    boots = _dec(send_check.amount(v["price"]) for i in items if i not in extras
                 for v in i.get("variants", []) if "price" in v)
    return bool(OWN_PRICE_END.search(before) and _dec(send_check.prices_in(before, sizes, orders)) & boots
                and SUBJECT_LEAD.fullmatch(_past_extra_name(between, extras, price_word=False).lstrip())
                and EXTRA_AMOUNT.match(_past_extra_name(after, extras)))


def _past_extra_name(after, extras, price_word=True):
    """after with the rest of the extra's name (its own title words) and, with price_word, one word that
    gives the extra its own price (OWN_PRICE_WORD: سعرها, its price) taken off its start, so "مع طباعة
    Beyond the Limits Name Printing سعرها 400 جنيه" reads the 400 right after the extra and "with Beyond
    the Limits Name Printing 400 EGP" has only the extra's title past its joining word (Arena run
    20261104T120239, part D). Only these words: "with printing is 400 EGP" still joins the extra to the
    boot."""
    own = {w for e in extras for w in re.findall(r"[a-z]+", str(e.get("title") or "").casefold())}
    rest = after
    while True:
        m = re.match(r"[^\S\n]*([a-z]+)(?![^\W_])", rest, re.IGNORECASE)
        if not m or m.group(1).casefold() not in own:
            break
        rest = rest[m.end():]
    m = OWN_PRICE_WORD.match(rest) if price_word else None
    return rest[m.end():] if m else rest


# A price that ends the text, its currency word after it or none ("16,500 EGP "), and an amount right at
# the start of the text, its currency word before it or none (" 400 EGP"): the two sides of
# _own_price_then_extra.
OWN_PRICE_END = re.compile(r"\d(?:[^\S\n]*(?:" + send_check.CURRENCY + r")" + send_check.NO_LETTER_AFTER
                           + r")?[^\S\n]*$", re.IGNORECASE)
# A word that gives the extra named right before it its own price: "its price", "سعرها", "تمنه" (the ها or ه
# is the extra's, the boot's price already came before the joining word)
OWN_PRICE_WORD = re.compile(r"[^\S\n]*(?:its[^\S\n]+price(?:[^\S\n]+is)?|(?:سعر|تمن)(?:ها|ه))(?![^\W_])", re.IGNORECASE)
EXTRA_AMOUNT = re.compile(r"[^\S\n]*(?:(?:" + send_check.CURRENCY + r")" + send_check.NO_LETTER_AFTER
                          + r"[^\S\n]*)?(?:" + send_check.DIGITS + r")", re.IGNORECASE)


def model_numbers(items):
    """For each title number, the pattern of it with the title word it belongs to: "vapor 17", "f50"
    (kit/send_check.py model_numbers, from the items' titles)."""
    return send_check.model_numbers(i.get("title") for i in items)


MODEL_NUMBER_END = send_check.MODEL_NUMBER_END


def without_model_numbers(text, items):
    """text with each product's model number dropped where it follows its title word, so "is the
    Vapor 17" holds no amount 17 (kit/send_check.py without_model_numbers, from the items' titles)."""
    return send_check.without_model_numbers(text, [i.get("title") for i in items])


def _governorate_zone(text):
    try:
        data = json.loads(GOVERNORATES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    low = " " + (text or "").casefold() + " "
    for g in data.get("governorates", []):
        for s in g.get("spellings", []):
            s = s.casefold()
            if re.search(r"(?<![\w])" + re.escape(s) + r"(?![\w])", low):
                return g.get("zone")
    return None


def _eu(size):
    """The size numbers a size string covers, as (least, most): "M (EU 42-45)" gives (42, 45), a bare
    "43" or "EU 43" gives (43, 43), anything else None."""
    m = EU_RANGE.search(size or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = EU_ONE.fullmatch((size or "").strip())
    return (int(m.group(1)), int(m.group(1))) if m else None


def tiers_named(text, tiers):
    """The tiers (from the store data) whose word shows in text: "Elite" in "the Elite is 16,500"."""
    low = (text or "").casefold()
    return {t for t in tiers if re.search(r"(?<![\w])" + re.escape(t.casefold()) + r"(?![\w])", low)}


def _of_tiers(variants, tiers):
    """The variants in one of tiers, and those with no tier (the printing); all of them when tiers is empty."""
    return [v for v in variants if not tiers or not v.get("tier") or v["tier"] in tiers]


def _variant_for(item, number=None, letter=None, tiers=()):
    for v in _of_tiers(item.get("variants", []), tiers):
        size = v.get("size") or ""
        if number is not None:
            r = _eu(size)
            if r and r[0] <= number <= r[1]:
                return v
        if letter is not None and re.match(re.escape(letter) + r"(?![\w])", size):
            return v
    return None


def _fee(zone):
    """A zone's delivery fee after the store's delivery offer (kit/offers.py delivery_fee, decision 105): under
    free delivery every zone's fee is 0, so a reply that quotes the zone's old fee fails; with no offers it
    is the zone's own fee."""
    return send_check.amount(offers.delivery_fee(offers.current(), zone["fee"]))


def check(reply, customer_text="", tool_results=(), orders=()):
    reply, customer_text = _visible(reply), _visible(customer_text)
    items = store.catalogue()
    sizes = store.size_strings()
    zones = store.delivery().get("zones", [])
    fees = {_fee(z) for z in zones if "fee" in z}
    all_tiers = store.tiers()
    said = tiers_named(reply, all_tiers) or tiers_named(customer_text, all_tiers)
    # an extra (the name printing) goes on any product, so a named boot never hides its price, and
    # naming only an extra names no product: the boot it goes on comes from the customer's line or
    # is any boot ("16,500 plus 400 printing is 16,900")
    extras = store.extras()
    named = _boots(products_named(reply, items), extras) or _boots(products_named(customer_text, items), extras)
    pool = (named + extras) if named else items
    prices = {send_check.amount(v["price"]) for i in pool for v in _of_tiers(i.get("variants", []), said)
              if "price" in v}
    extra_prices = {send_check.amount(v["price"]) for e in extras for v in e.get("variants", []) if "price" in v}
    extra_prices.discard(None)
    from_tools = set()
    for name, res in tool_results:
        if name in tools.AMOUNT_TOOLS:
            from_tools |= send_check.amounts_in(res)
    allowed = set(prices) | fees | {p + f for p in prices for f in fees if p is not None and f is not None}
    allowed |= _with_extras(prices, extra_prices, fees)
    allowed |= from_tools
    text = without_model_numbers(reply, items)   # the amounts are read from text, never a model number
    failed, wrong = [], set()
    for a in send_check.prices_in(text, sizes, orders):
        if Decimal(str(a)) not in {Decimal(str(x)) for x in allowed if x is not None}:
            wrong.add(Decimal(str(a)))
            failed.append({"check": "price", "why": f"{a} is not a store price, fee or tool amount"})

    # An extra's own price stands only beside the extra: in a clause that names it, or in a clause
    # that names no product and no tier when the reply names the extra elsewhere (the customer's
    # line when the reply names nothing). Any other reading of it (a store price, a fee, a sum, a
    # tool amount) still counts anywhere. A clause that names an extra and no product or tier holds
    # the extra's prices, fees, sums and tool amounts, and a boot price only beside one of those.
    base = {send_check.amount(v["price"]) for i in pool if i not in extras
            for v in _of_tiers(i.get("variants", []), said) if "price" in v}
    sums = _dec(_with_extras(prices, extra_prices, fees))
    other = _dec(base | fees | {p + f for p in base for f in fees if p is not None and f is not None}
                 | from_tools) | sums
    backdrop = extras_named(reply, extras, items)
    if not backdrop and not products_named(reply, items):
        backdrop = extras_named(customer_text, extras, items)
    for clause, start, boot, kinds, sentence_boot, sentence, before in _extra_clauses(text, items, extras,
                                                                                         all_tiers):
        here = extras_named(clause, extras, items)
        # the extra the clause names, else one its sentence names, keeps its price beside an add-on
        # word: "If you add printing to the Elite, it's 400 EGP more" (DECISIONS item 52). An extra
        # named only in another sentence, or only in the customer's line, never makes an add-on
        # amount (review gatefb round 1, finding 2; red team gatefb round 1, item 2). In a clause
        # with a boot or a tier (its own or the one before it) only an extra named before the amount
        # counts: "The Elite is 400 EGP more, and printing is available too" fails (review gatefb
        # round 2, finding 1).
        on_top = set()
        for d, at in _addon_hits(clause):
            gives = extras_named(sentence[:start + at], extras, items) if boot else \
                here or extras_named(sentence, extras, items)
            if d in _dec(send_check.amount(v["price"]) for e in gives for v in e.get("variants", []) if "price" in v):
                on_top.add(d)
        amounts = [Decimal(str(a)) for a in send_check.prices_in(clause, sizes, orders)]
        # the backdrop holds an extra's price only in a sentence that names no boot and no tier: "The
        # Vapor 17 Elite, with printing, is 400 EGP" fails (red team round 2, R2-1). A clause that
        # names a boot or a tier and the extra holds the extra's price only as _extra_not_held says,
        # or beside a sum or an add-on word: "The Vapor 17 Elite with printing is 400 EGP" fails,
        # "Printing on the Vapor 17 Elite is 400 EGP" passes (red team gatefb rounds 1 and 2).
        if _extra_not_held(clause, extras, items, all_tiers, sizes, orders) and not set(amounts) & sums:
            here = []
        # A sentence that names a boot or a tier only after the clause (in a later clause, "It costs 400
        # EGP, free with an Elite") reads a clause that names no product, no tier and no extra like a
        # sentence with no boot: the extra named before it in its sentence, else the one the sentence
        # before names (before). A boot or a tier before the clause keeps the clause to its own extra
        # (live Sales Arena run 2026-11-04: 3 of 4 losses in 20 matches were this false fail).
        if not sentence_boot:
            holds = here or backdrop
        elif here or boot or _names_boot(sentence[:start], items, extras, all_tiers):
            holds = here
        else:
            holds = extras_named(sentence[:start], extras, items) or before
        own = _dec(send_check.amount(v["price"]) for e in holds for v in e.get("variants", []) if "price" in v)
        if kinds and not boot:
            ok = own | sums | _dec(fees | from_tools) | {e + f for e in own for f in _dec(fees)}
            if any(d in ok and d not in _dec(fees | from_tools) for d in amounts):
                ok |= other
        else:
            ok = other | own | {d for d in amounts if d not in _dec(extra_prices)}
        for d in amounts:
            if d in wrong or d in ok or d in on_top:
                continue
            wrong.add(d)
            if d in _dec(extra_prices):
                why = f"{d} is the price of {_names(extras_of(extras, d))}, and its clause does not name it"
            else:
                why = f"{d} is not a price of {_names(kinds)}, a fee or a sum with it"
            failed.append({"check": "price", "why": why})

    for clause in TIER_CLAUSE.findall(text):
        here = tiers_named(clause, all_tiers)
        if len(here) != 1:
            continue
        mine = _boots(products_named(clause, items), extras) or pool   # the printing beside a boot names no price
        ok = {send_check.amount(v["price"]) for i in mine for v in _of_tiers(i.get("variants", []), here)
              if "price" in v and v.get("tier")}
        ok |= fees | {p + f for p in ok for f in fees if p is not None and f is not None} | from_tools \
            | extra_prices | _with_extras(ok, extra_prices, fees)
        for a in send_check.prices_in(clause, sizes, orders):
            d = Decimal(str(a))
            if d not in wrong and d not in {Decimal(str(x)) for x in ok if x is not None}:
                wrong.add(d)
                failed.append({"check": "price", "why": f"{a} is not the {next(iter(here))} price of {_names(mine)}"})

    for m in SIZE_NUMBER.finditer(reply):
        n = int(m.group(1))
        if not any(_variant_for(i, number=n) for i in pool):
            failed.append({"check": "size", "why": f"size {n} is not a size of {_names(named)}"})

    for m, context in _with_context(reply, items, named):
        if reply[m.end():m.end() + 1] not in ("?", "؟"):  # a question claims nothing
            failed += _no_stock_data(m.group(0), items, context, extras, all_tiers, said)
    for m, context in _with_context(reply, items, named):
        sentence = m.group(0)
        marks = _stock_marks(sentence)
        if not marks or reply[m.end():m.end() + 1] in ("?", "؟"):  # a question claims nothing
            continue
        here = products_named(sentence, items) or context
        level = tiers_named(sentence, all_tiers) or _tier_context(reply, m.start(), all_tiers) or said
        sized = [(s.start(1), "number", int(s.group(1))) for s in SIZE_NUMBER.finditer(sentence)]
        sized += [(s.start(1), "letter", s.group(1)) for s in SIZE_LETTER.finditer(sentence)]
        for item in here:
            if not sized:  # the product as a whole: out wins when the sentence says both
                says_out = any(k == "out" for _, _, k in marks)
                variants = _of_tiers(item.get("variants", []), level)
                if not says_out and variants and all(v.get("stock") == "out" for v in variants):
                    failed.append({"check": "stock", "why": f"{item['title']} is out, the reply says available"})
                continue
            for pos, how, size in sized:  # each size takes the stock word beside it (live run 20261104T170549)
                v = _variant_for(item, number=size, tiers=level) if how == "number" else \
                    _variant_for(item, letter=size, tiers=level)
                if not v:
                    continue
                says = _mark_for(sentence, pos, marks)
                if says == "in" and v.get("stock") == "out":
                    failed.append({"check": "stock", "why": f"{item['title']} {_label(v)} is out, "
                                                            f"the reply says available"})
                if says == "out" and v.get("stock") not in (None, "out"):
                    failed.append({"check": "stock", "why": f"{item['title']} {_label(v)} is in stock, "
                                                            f"the reply says out"})

    zone = _governorate_zone(reply) or _governorate_zone(customer_text)
    mine = [z for z in zones if z.get("area") == zone] or zones
    for sentence in SENTENCE.findall(reply):
        if not DELIVERY.search(sentence):
            continue
        zone_fees = {_fee(z) for z in mine if "fee" in z}
        for a in send_check.prices_in(without_model_numbers(sentence, items), sizes, orders):
            if a in prices or a in zone_fees or any(a == x for x in allowed if x not in fees):
                continue
            failed.append({"check": "delivery", "why": f"{a} is not the delivery fee for {zone or 'any zone'}"})
        low = min(z["days_min"] for z in mine)
        high = max(z["days_max"] for z in mine)
        rule = offers.preorder(offers.current())
        if rule and rule.get("days") and any(send_check._has_words(send_check._offer_tokens(sentence), w)
                                             for w in offers.preorder_words(offers.current())):
            high = max(high, rule["days"])   # a pre-order comes within the rule's days (decision 108)
        spans = [(int(m.group(1)), int(m.group(2) or m.group(1))) for m in DAYS.finditer(sentence)
                 if not exchange_days(sentence, m.start())]
        spans += [(2, 2)] * sum(1 for m in TWO_DAYS.finditer(sentence) if not exchange_days(sentence, m.start()))
        for a, b in spans:
            if a < low or b > high:
                failed.append({"check": "delivery", "why": f"{a} to {b} days is outside {low} to {high} days"
                                                           f" for {zone or 'any zone'}"})

    if claims_order(reply) and not placed(tool_results):
        failed.append({"check": "order", "why": "the reply says the order is placed, but no tool placed one"})
    return failed


# Still in stock: a few left, or "the available ones" (المتاح); a size beside it takes "in", never the out word of
# the next size.
FEW = re.compile(r"(?<!\w)(?:[وف]?ال(?:متاح|متوفر|موجود)[ةه]?|(?:only\s+)?(?:a\s+)?few\s+(?:are\s+|pairs\s+)?left|low\s+stock|last\s+(?:pair|one)s?|"
                 r"كمي[ةه]\s+قليل[ةه]|باقي\s+قليل|قرب\s+يخلص|fadel\s+2(?:o|a)l(?:a|e)yel)(?!\w)", re.IGNORECASE)
# where one clause of a sentence ends: ; ، ؛ or a comma that is not inside a number (16,500)
CLAUSE_CUT = re.compile(r"[;؛،]|(?<!\d),|,(?!\d)")


def _stock_marks(sentence):
    """The stock words of a sentence in order: (start, end, "out" or "in"). An available word inside an out
    word ("غير متوفر") is the out word only."""
    outs = [(m.start(), m.end(), "out") for m in OUT.finditer(sentence)]
    ins = [(m.start(), m.end(), "in") for rx in (AVAILABLE, FEW) for m in rx.finditer(sentence)
           if not any(a <= m.start() < b for a, b, _ in outs) and not AS_PREORDER.match(sentence, m.end())]
    return sorted(outs + ins)


def _mark_for(sentence, pos, marks):
    """The stock word a size at pos goes with: the nearest after it in its own clause, else the nearest before
    it in that clause, else the nearest after it in the sentence ("sizes 39, 40 in stock"), else before it
    ("المتاح مقاسات 40 و41")."""
    cuts = [m.start() for m in CLAUSE_CUT.finditer(sentence)]
    lo = max([c for c in cuts if c < pos], default=-1)
    hi = min([c for c in cuts if c > pos], default=len(sentence))
    after = [k for a, _, k in marks if a > pos]
    before = [k for a, _, k in marks if a < pos]
    mine_after = [k for a, _, k in marks if pos < a < hi]
    mine_before = [k for a, _, k in marks if lo < a < pos]
    for pick in (mine_after[:1], mine_before[-1:], after[:1], before[-1:]):
        if pick:
            return pick[0]
    return None


def _tier_context(reply, start, all_tiers):
    """The tiers the nearest sentence before start names, when the sentence at start names none ("The F50
    Pro in size 42 is in stock. Size 43 is in stock." is the Pro's 43)."""
    for m in reversed(list(SENTENCE.finditer(reply[:start]))):
        got = tiers_named(m.group(0), all_tiers)
        if got:
            return got
    return None


def _with_context(reply, items, named):
    """Each sentence of reply with the products it talks about when it names none: the ones the nearest
    sentence before it names (a size line under a product's heading, "Size 42 is out of stock", is about
    that product, Arena run 20261104T170549), else named. A sentence that names products keeps its own."""
    context = None
    for m in SENTENCE.finditer(reply):
        yield m, context or named
        own = products_named(m.group(0), items)
        if own:
            context = own


def _no_stock_data(sentence, items, named, extras, all_tiers, said):
    """The stock fails of one sentence for a clause that says a product is in stock (AVAILABLE, no OUT) while
    the store gives no stock field for it: for the variants of the sizes it names, or for any variant of the
    product's tiers when it names none. The product is the one the sentence names, else the reply's or the
    customer's (named). An unsure sentence and a clause about delivery or payment claim nothing; an
    extra (the printing) is a service, never stock. Nothing is ever filled in: no field is no data."""
    if UNSURE.search(sentence):
        return []
    claims = [c for c in CLAIM_CLAUSE.split(sentence)
              if any(not AS_PREORDER.match(c, m.end()) for m in AVAILABLE.finditer(c))
              and not OUT.search(c) and not DELIVERY.search(c) and not PAYMENT.search(c)]
    if not claims:
        return []
    here = _boots(products_named(sentence, items) or named, extras)
    nums = [int(m.group(1)) for m in SIZE_NUMBER.finditer(sentence)]
    letters = SIZE_LETTER.findall(sentence)
    level = tiers_named(sentence, all_tiers) or said
    out = []
    for item in here:
        variants = [v for v in (_variant_for(item, number=n, tiers=level) for n in nums) if v]
        variants += [v for v in (_variant_for(item, letter=x, tiers=level) for x in letters) if v]
        if not nums and not letters:
            variants = _of_tiers(item.get("variants", []), level)
            if variants and all(v.get("stock") is None for v in variants):
                out.append({"check": "stock", "why": f"the store gives no stock data for {item['title']}, "
                                                     "the reply says it is in stock"})
            continue
        for v in variants:
            if v.get("stock") is None:
                out.append({"check": "stock", "why": f"the store gives no stock data for {item['title']} "
                                                     f"{_label(v)}, the reply says it is in stock"})
    return out


def _extra_clauses(text, items, extras, all_tiers):
    """(clause, start, boot, kinds, sentence_boot, sentence) for each clause of text the extra price rule
    reads (EXTRA_CLAUSE, inside each PRICE_SENTENCE). start: where the clause starts in its sentence.
    boot: the tiers or boots the clause names; kinds:
    the extras it names by their type or title, never by "your name" alone (an order asks for it).
    A clause that names no product (boot or extra) and no tier takes the boots, tiers and kinds of
    the clauses before it in its sentence: in "Vapor Elite, 400 EGP, with your name" the 400 sits
    beside the boot (red team round 2, R2-1). A bracket or a spaced dash cuts a clause too (ASIDE).
    sentence_boot: the sentence names a boot or a tier. before: the extras the nearest sentence before
    it that names a product, a tier or an extra names, when that sentence names an extra and no boot
    and no tier, else none ("Printing is available. It costs 400 EGP, free with an Elite": the 400 is
    the printing's, live Sales Arena run 2026-11-04). A sentence that names nothing passes it on, as
    _with_context does for stock; one that names a boot or a tier ends it."""
    out = []
    before = []
    for sentence in PRICE_SENTENCE.findall(text):
        sentence_boot = bool(tiers_named(sentence, all_tiers) or _boots(products_named(sentence, items), extras))
        seen_boot, seen_kinds = [], []
        for found in EXTRA_CLAUSE.finditer(ASIDE.sub(";", sentence)):  # ASIDE keeps every place
            clause = found.group(0)
            named = products_named(clause, items)
            boot = list(tiers_named(clause, all_tiers)) or _boots(named, extras)
            kinds = extras_named(clause, extras, items, kind=True) or [i for i in named if i in extras]
            if boot or kinds or extras_named(clause, extras, items):
                seen_boot += boot
                seen_kinds += kinds
            else:
                boot, kinds = list(seen_boot), list(seen_kinds)
            out.append((clause, found.start(), boot, kinds, sentence_boot, sentence, before))
        if sentence_boot:
            before = []
        else:
            before = extras_named(sentence, extras, items) or before
    return out


def _addon_hits(clause):
    """(amount as a Decimal, where its add-on match starts) for each amount of a clause that an add-on
    word sits right beside (ADDON)."""
    out = []
    for m in ADDON.finditer(clause):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        try:
            out.append((Decimal(raw), m.start()))
        except ArithmeticError:
            continue
    return out


def _visible(text):
    """text without its hidden format characters (a zero width space and the like), so none splits
    or hides a word the price rules read (review gatefb round 2, finding 2)."""
    return "".join(ch for ch in str(text or "") if unicodedata.category(ch) != "Cf")


def _with_extras(prices, extra_prices, fees):
    """A price with one extra on it, with or without one delivery fee: the Elite boot with its name
    printing (16500 + 400), and that plus the fee."""
    out = set()
    for p in prices:
        for e in extra_prices:
            if p is None or p in extra_prices:
                continue
            out.add(p + e)
            out |= {p + e + f for f in fees if f is not None}
    return out


def exchange_days(sentence, pos):
    """True when the count of days at pos in sentence is an exchange or return window: the nearest
    delivery or exchange word before it is an exchange word, or, with none before it, the nearest after
    it is. "Delivery is 2 days and you can exchange within 14 days": 2 is delivery, 14 is not.
    "ممكن تبدل خلال 14 يوم من التوصيل": 14 is not. "التوصيل خلال 14 يوم": 14 is delivery."""
    words = [(m.start(), "exchange") for m in EXCHANGE.finditer(sentence)]
    words += [(m.start(), "delivery") for m in DELIVERY.finditer(sentence)]
    before = [w for w in words if w[0] < pos]
    if before:
        return max(before)[1] == "exchange"
    after = [w for w in words if w[0] > pos]
    return bool(after) and min(after)[1] == "exchange"


def claims_order(reply):
    """True when a sentence of the reply says the order is made and nothing scoped to that claim makes it
    conditional: no condition before it in its sentence, no negation, may-be or then before it in its own
    clause, no condition right after it, and the sentence is not a question that opens with a question word.
    Words in other clauses do not hide it ("Your order is confirmed, anything else?", review round 3)."""
    for m in CLAIM_SENTENCE.finditer(clean.normalize(reply or "")):
        s = m.group(0)
        if s.rstrip().endswith(("?", "؟")) and CLAIM_QUESTION.search(s):
            continue
        for c in ORDER_CLAIM.finditer(s):
            clause = CLAIM_CLAUSE.split(s[:c.start()])[-1]
            if CLAIM_LEAD.search(s[:c.start()]) or CLAIM_NEAR.search(clause) or CLAIM_AFTER.match(s, c.end()):
                continue
            return True
    return False


def placed(tool_results):
    """True when a draft_order result in tool_results created an order (kit/tools/draft_order.py created)."""
    for name, res in tool_results or ():
        if name == draft_order.NAME and isinstance(res, dict) and res.get("ok") is True and \
                res.get("step") == "created" and res.get("order"):
            return True
    return False


def _label(v):
    return " ".join(x for x in (v.get("tier"), v.get("size")) if x) or "(no size)"


def _boots(items, extras):
    """items without the extras: the products an extra goes on."""
    return [i for i in items if i not in extras]


def _dec(amounts):
    return {Decimal(str(x)) for x in amounts if x is not None}


def extras_of(extras, amount):
    """The extras with a variant at amount."""
    return [e for e in extras
            if any("price" in v and Decimal(str(v["price"])) == amount for v in e.get("variants", []))]


def _names(items):
    return ", ".join(i["title"] for i in items) if items else "any product"
