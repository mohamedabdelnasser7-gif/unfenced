"""Fact checks on every Sales agent reply in an Arena match (new, 2026-10-30), in code, against
the store's own data (kit/tools/store.py catalogue and delivery, demo/governorates.json):

price     every amount in the reply (kit/send_check.py prices_in) is a price of a product the
          reply names, a delivery fee, one price plus one fee, or an amount a tool gave this
          turn (a draft order's total). With no product named, any store price counts. A tier
          the reply names (Elite, Pro; else one the customer's line names) narrows the prices to
          that tier's, and in a clause that names one tier its amounts must be that tier's prices:
          the Pro price given for an Elite boot is a wrong price.
size      a size number after a size word (مقاس 43, size 43, EU 43) fits a size of a product
          the reply names, or of any product when it names none.
stock     a reply that says a named product (and size, when it gives one) is available while
          the store has it out fails; so does one that says it is out while the store has it.
delivery  an amount in a sentence about delivery is a delivery fee (the named governorate's
          zone fee when the reply names one); a count of days there sits inside the zones' days
          (the named zone's when it names one).
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
from decimal import Decimal
from pathlib import Path

from arena import clean, label
from kit import send_check, tools
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
AVAILABLE = re.compile(r"(?<!\w)(?:متاح[ةه]?|متوفر[ةه]?|موجود[ةه]?|available|in\s+stock|mawgood|motaa7|metwafar)(?!\w)",
                       re.IGNORECASE)
DELIVERY = re.compile(r"(?<!\w)(?:شحن|الشحن|توصيل|التوصيل|delivery|shipping|tawseel|sha7n|courier)(?!\w)", re.IGNORECASE)
DAYS = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:(?:-|to|او|أو|ل|الى|إلى|و|or)\s*(\d{1,2})\s*)?"
                  r"(?:(?:working|business)\s+)?(?:days?|يوم|أيام|ايام|yom|youm|ayam)(?!\w)", re.IGNORECASE)
TWO_DAYS = re.compile(r"(?<!\w)(?:يومين|yomein|youmein)(?!\w)", re.IGNORECASE)
SENTENCE = re.compile(r"[^.!?؟\n]+")
# a clause for the tier rule: cut at an end mark, a new line, ؛ ; ، or a comma that is not inside
# a number (16,500 stays whole); a decimal point does not end it
TIER_CLAUSE = re.compile(r"(?:[^.!?؟\n,،;؛]|(?<=\d)[.,](?=\d))+")


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


def check(reply, customer_text="", tool_results=(), orders=()):
    items = store.catalogue()
    sizes = store.size_strings()
    zones = store.delivery().get("zones", [])
    fees = {send_check.amount(z["fee"]) for z in zones if "fee" in z}
    all_tiers = store.tiers()
    named = products_named(reply, items) or products_named(customer_text, items)
    said = tiers_named(reply, all_tiers) or tiers_named(customer_text, all_tiers)
    pool = named or items
    prices = {send_check.amount(v["price"]) for i in pool for v in _of_tiers(i.get("variants", []), said)
              if "price" in v}
    from_tools = set()
    for name, res in tool_results:
        if name in tools.AMOUNT_TOOLS:
            from_tools |= send_check.amounts_in(res)
    allowed = set(prices) | fees | {p + f for p in prices for f in fees if p is not None and f is not None}
    allowed |= from_tools
    failed, wrong = [], set()
    for a in send_check.prices_in(reply, sizes, orders):
        if Decimal(str(a)) not in {Decimal(str(x)) for x in allowed if x is not None}:
            wrong.add(Decimal(str(a)))
            failed.append({"check": "price", "why": f"{a} is not a store price, fee or tool amount"})

    for clause in TIER_CLAUSE.findall(reply):
        here = tiers_named(clause, all_tiers)
        if len(here) != 1:
            continue
        mine = products_named(clause, items) or pool
        ok = {send_check.amount(v["price"]) for i in mine for v in _of_tiers(i.get("variants", []), here)
              if "price" in v and v.get("tier")}
        ok |= fees | {p + f for p in ok for f in fees if p is not None and f is not None} | from_tools
        for a in send_check.prices_in(clause, sizes, orders):
            d = Decimal(str(a))
            if d not in wrong and d not in {Decimal(str(x)) for x in ok if x is not None}:
                wrong.add(d)
                failed.append({"check": "price", "why": f"{a} is not the {next(iter(here))} price of {_names(mine)}"})

    for m in SIZE_NUMBER.finditer(reply):
        n = int(m.group(1))
        if not any(_variant_for(i, number=n) for i in pool):
            failed.append({"check": "size", "why": f"size {n} is not a size of {_names(named)}"})

    for sentence in SENTENCE.findall(reply):
        says_out = bool(OUT.search(sentence))
        says_in = not says_out and bool(AVAILABLE.search(sentence))
        if not (says_out or says_in):
            continue
        here = products_named(sentence, items) or named
        nums = [int(m.group(1)) for m in SIZE_NUMBER.finditer(sentence)]
        letters = SIZE_LETTER.findall(sentence)
        level = tiers_named(sentence, all_tiers) or said
        for item in here:
            variants = [v for v in (_variant_for(item, number=n, tiers=level) for n in nums) if v]
            variants += [v for v in (_variant_for(item, letter=x, tiers=level) for x in letters) if v]
            if not variants and not nums and not letters:
                variants = _of_tiers(item.get("variants", []), level)
                if says_in and variants and all(v.get("stock") == "out" for v in variants):
                    failed.append({"check": "stock", "why": f"{item['title']} is out, the reply says available"})
                continue
            for v in variants:
                if says_in and v.get("stock") == "out":
                    failed.append({"check": "stock", "why": f"{item['title']} {_label(v)} is out, "
                                                            f"the reply says available"})
                if says_out and v.get("stock") not in (None, "out"):
                    failed.append({"check": "stock", "why": f"{item['title']} {_label(v)} is in stock, "
                                                            f"the reply says out"})

    zone = _governorate_zone(reply) or _governorate_zone(customer_text)
    mine = [z for z in zones if z.get("area") == zone] or zones
    for sentence in SENTENCE.findall(reply):
        if not DELIVERY.search(sentence):
            continue
        zone_fees = {send_check.amount(z["fee"]) for z in mine if "fee" in z}
        for a in send_check.prices_in(sentence, sizes, orders):
            if a in prices or a in zone_fees or any(a == x for x in allowed if x not in fees):
                continue
            failed.append({"check": "delivery", "why": f"{a} is not the delivery fee for {zone or 'any zone'}"})
        low = min(z["days_min"] for z in mine)
        high = max(z["days_max"] for z in mine)
        spans = [(int(m.group(1)), int(m.group(2) or m.group(1))) for m in DAYS.finditer(sentence)]
        spans += [(2, 2)] * len(TWO_DAYS.findall(sentence))
        for a, b in spans:
            if a < low or b > high:
                failed.append({"check": "delivery", "why": f"{a} to {b} days is outside {low} to {high} days"
                                                           f" for {zone or 'any zone'}"})

    if claims_order(reply) and not placed(tool_results):
        failed.append({"check": "order", "why": "the reply says the order is placed, but no tool placed one"})
    return failed


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


def _names(items):
    return ", ".join(i["title"] for i in items) if items else "any product"
