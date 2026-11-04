"""draft_order: places an order in two steps, so nothing is created without the customer's yes.

Step 1 (no confirm): checks the items against the store data and the governorate against
the delivery data, works out the subtotal, fee and total in code (never from the model),
saves a pending draft for the chat and returns a summary with a short code.

A printing line (a product whose type in the store data is Printing) carries the name to
print: the order's name unless the customer gives another as print_name (DECISIONS item 28).
print_name on any other line is refused. A product whose variants have tiers (Elite, Pro) needs the
tier as well as the size. Lines are keyed by product, tier, size and name to print,
so two names are two lines, and the name is part of the draft the customer confirms.

Step 2 (confirm set to that code) creates the order only when:
- this chat has a pending draft with that code, less than a day old,
- the model's own reply showing the draft's total went out after the summary (a fixed line does
  not count), the customer has written since, and every message they
  wrote after that reply is a plain yes: no question, no change, no photo (a voice note counts
  only in this turn, by its transcript), and
- the same details, worked out again from the data now, still match the pending draft.
Each summary writes an "order_drafted" row to the result log. The order goes to the store with
the chat id on it and cod_risk's level as a tag ("unknown" when the check could not run), and an
"order_created" row goes to the result log. The pending draft is used once, and a turn that
created an order makes no new summary, so a re-draft right after an order cannot become a
second order (review t261028j round 2, finding 1).

Offers (decision 105, kit/offers.py): payment is the customer's payment method, one of the store's.
The totals take the store's offers through offers.apply (one offer an order, the one that saves most,
delivery on top), and the draft keeps the payment, the discounts and the total. quote set to true works
out the totals for items and payment alone (a governorate adds the fee and days): no name or address,
nothing saved, so the agent can tell a customer what an order costs before they decide.

Money keys in results are price, fee, subtotal, discount and total only, so the send check reads them.
"""
import hmac
import json
import logging
import re
import time

from kit import offers, orders, send_check
from kit.tools import cod_risk, delivery, store, voice_note
from reflection.results import Results

log = logging.getLogger("kit.tools.draft_order")

MAX_LINES = 10
MAX_QUANTITY = 20
FIELDS = {"items", "name", "governorate", "address", "phone", "confirm", "payment", "quote"}
QUOTE_FIELDS = {"items", "governorate", "payment", "quote"}
REQUIRED = ("items", "name", "governorate", "address")
ITEM_FIELDS = {"product", "tier", "size", "quantity", "print_name"}
TEXT_LIMITS = (("name", 2, 80), ("governorate", 2, delivery.MAX_PLACE), ("address", 5, 300))
PRINTING = "printing"            # the store data's product type for the printing service, folded
PRINT_MIN, PRINT_MAX = 2, 30     # the name to print, in characters after spaces are folded

NAME = "draft_order"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Place an order in two steps. Step 1: call without confirm. It returns a summary with the subtotal, "
        "delivery fee and total from the store data, and a code. Show the summary and ask the customer to "
        "confirm. Step 2: only after the customer answers with a plain yes in a new message, call again with "
        "the same details and confirm set to the code. A question, or a yes with a change, means step 1 again. "
        "With quote set to true it only works out the totals, with the store's offers, for items and payment."),
    "parameters": {
        "type": "object",
        "properties": {
            "items": {"type": "array", "description": "What the customer is ordering.", "items": {
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "The product title exactly as the store tool gives it."},
                    "tier": {"type": "string", "description": "The tier as the store tool gives it, for example Elite. Leave out for a product with no tiers."},
                    "size": {"type": "string", "description": "The size as the store tool gives it. Leave out for a product with one size."},
                    "quantity": {"type": "integer", "minimum": 1, "maximum": MAX_QUANTITY},
                    "print_name": {"type": "string", "description": "Only on a product of type Printing: the name to print. Leave out to print the customer's name."},
                },
                "required": ["product", "quantity"],
                "additionalProperties": False,
            }},
            "name": {"type": "string", "description": "The customer's name for the delivery."},
            "governorate": {"type": "string", "description": "The governorate as the customer wrote it."},
            "address": {"type": "string", "description": "Area, street, building, floor and flat, as the customer wrote them."},
            "phone": {"type": "string", "description": "Only if the customer gives another number for the courier. Leave out to use this chat's WhatsApp number."},
            "confirm": {"type": "string", "description": "Step 2 only: the code from the summary."},
            "payment": {"type": "string", "description": "How the customer pays: one of the payment methods the store tool lists. Leave out when they have not said."},
            "quote": {"type": "boolean", "description": "true to work out the totals for items and payment only (a governorate adds the fee): no name or address needed, nothing is saved."},
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}}

SUMMARY_NEXT = (
    "Show this summary to the customer in their language and script: items (with the name to print on a "
    "printing line), subtotal, any discount with its offer, delivery fee, total, name, address, phone and delivery days. Ask them to confirm. Never show the code. When they answer with a "
    "plain yes in a new message, call draft_order again with the same details and confirm set to the code. A "
    "question, or a yes with a change, needs a new summary: call draft_order again without confirm.")
QUOTE_NEXT = ("These are the totals for these items with the store's offers; nothing is saved. Give the customer "
              "the amounts as they are here. To order, ask for the name, governorate and address and call draft_order "
              "without quote.")
CREATED_NEXT = "Tell the customer the order is received, with its number, the total and the delivery days."
NOT_SAVED = "The store did not take the order. Say the order did not go through and ask them to try again later."
ORDER_MADE_NOW = ("Order {order} was created in this turn, so no new summary is made. Tell the customer the "
                  "order is received, with its number, the total and the delivery days. For another order, "
                  "wait until the customer asks for one in a new message.")
NO_PENDING = "No order summary is waiting for this chat. Call draft_order without confirm first."
SHOW_FIRST = ("The customer has not answered the summary yet: no reply showing its total went out. Show "
              "the summary first, with the total in digits, and wait for their yes in a new message.")
HEAR_FIRST = "The customer answered with a voice note. Call voice_note to hear it first."
NOT_A_YES = ("The customer's answer to the summary is not a plain yes, so the order was not placed. Answer what "
             "they asked, call draft_order without confirm (with any change they asked for), show the new "
             "summary and ask them to confirm.")

# A plain yes: every word is a yes word or a polite word next to it, and at least one is a yes word.
# Anything else (بس, لا, no, a size, a digit, a question) means the customer may want a change.
YES_WORDS = (
    "ايوه ايوا اه نعم تمام التمام ماشي اوك اوكي موافق اكد اكده اكدها اكدلي حاضر اكيد تم صح يلا "
    "aywa aiwa ah tamam tmam tmm mashy mashi ok okay k mwafe2 akked 2aked akd akid yalla sa7 "
    "yes yeah yep yup sure confirm confirmed correct ahead")
OK_WORDS = (
    "يا باشا حبيبي شكرا ميرسي كده كدا خلاص الاوردر الطلب ده دا لو سمحت من فضلك حضرتك "
    "ya basha pasha shokran merci kda keda khalas el order da please pls plz thanks thank you thx "
    "the it go do now fine good great perfect و w and")
SIGNS = {"\U0001F44D": " ok ", "\U0001F44C": " ok ", "\u2705": " ok ", "\U0001F44E": " no ", "\u274C": " no "}
REPEATS = re.compile(r"(.)\1+")
WORDS = re.compile(r"[^\W_]+")


def check(args, ctx):
    extra = set(args) - FIELDS
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}."
    if "quote" in args and args["quote"] is not True:
        return False, "quote must be true, or left out to place an order."
    if "payment" in args:
        methods = offers.payment_methods(offers.current())
        if not isinstance(args["payment"], str) or _key(args["payment"]) not in methods:
            listed = ", ".join(methods) or "none"
            return False, f"payment must be one of the payment methods the store lists: {listed}."
    if args.get("quote"):
        extra = set(args) - QUOTE_FIELDS
        if extra:
            return False, f"A quote takes items, payment and governorate only, not {', '.join(sorted(extra))}."
        return _check_items(args, ("governorate",) if "governorate" in args else ())
    missing = [k for k in REQUIRED if k not in args]
    if missing:
        return False, f"Missing: {', '.join(missing)}. Ask the customer for them first."
    ok, problem = _check_items(args, [k for k, _, _ in TEXT_LIMITS])
    if not ok:
        return ok, problem
    if "phone" in args and (not isinstance(args["phone"], str) or not orders.phone_key(args["phone"])):
        return False, "phone must be a phone number, or left out to use this chat's WhatsApp number."
    if "confirm" in args and (not isinstance(args["confirm"], str) or not 0 < len(args["confirm"].strip()) <= 12):
        return False, "confirm must be the code from the summary."
    return True, ""


def _check_items(args, texts):
    """The items and the text fields named in texts, checked."""
    items = args.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_LINES:
        return False, f"items must be a list of 1 to {MAX_LINES} lines."
    for it in items:
        if not isinstance(it, dict) or set(it) - ITEM_FIELDS or "product" not in it or "quantity" not in it:
            return False, ("Each item takes product and quantity, tier and size when the product has them, and "
                           "print_name on a printing line. Nothing else.")
        if not isinstance(it["product"], str) or not 0 < len(it["product"].strip()) <= 120:
            return False, "product must be the title from the store tool."
        if "size" in it and (not isinstance(it["size"], str) or len(it["size"]) > 60):
            return False, "size must be the size text from the store tool."
        if "tier" in it and (not isinstance(it["tier"], str) or len(it["tier"]) > 60):
            return False, "tier must be the tier text from the store tool."
        if "print_name" in it and (not isinstance(it["print_name"], str)
                                   or not PRINT_MIN <= len(_text(it["print_name"])) <= PRINT_MAX):
            return False, f"print_name must be the name to print, {PRINT_MIN} to {PRINT_MAX} characters."
        q = it["quantity"]
        if isinstance(q, bool) or not isinstance(q, int) or not 1 <= q <= MAX_QUANTITY:
            return False, f"quantity must be a whole number from 1 to {MAX_QUANTITY}. Say that is the most for one order."
    for key, lo, hi in TEXT_LIMITS:
        if key not in texts:
            continue
        v = args[key]
        if not isinstance(v, str) or not lo <= len(_text(v)) <= hi:
            return False, f"{key} must be text, {lo} to {hi} characters."
    return True, ""


def run(args, ctx):
    if args.get("quote"):
        return quote(args)
    book = orders.Book(ctx.chats.db)
    if "confirm" in args:
        return _confirm(book, args, ctx)
    steps = ctx.chats.steps(ctx.chat_id)
    made = created(steps)
    if made:
        return _refuse(ORDER_MADE_NOW.format(order=made["order"]))
    draft, problem = build(args, ctx)
    if problem:
        return {"ok": False, "feedback": problem}
    code = orders.new_code()
    book.save_draft(ctx.chat_id, code, draft, steps[-1]["n"] if steps else 0)
    _log(ctx, "order_drafted", {"total": orders.amount(draft["total"])})
    return {"ok": True, "step": "summary", "code": code, **shown(draft), "next": SUMMARY_NEXT}


def _confirm(book, args, ctx):
    pending = book.pending(ctx.chat_id)
    if pending is None:
        return _refuse(NO_PENDING)
    if not hmac.compare_digest(pending["code"].encode(), args["confirm"].strip().upper().encode()):
        return _refuse("That is not the code from the latest summary. Use the latest code, or make a new summary.")
    if time.time() - pending["at"] > orders.DRAFT_SECONDS:
        book.drop_draft(ctx.chat_id)
        return _refuse("The summary is more than a day old. Make a new summary and show it to the customer.")
    steps = ctx.chats.steps(ctx.chat_id)
    if summary_reply(steps, pending["after_step"], pending["draft"]["total"]) is None:
        return _refuse(SHOW_FIRST)
    answered = answers(steps, pending["after_step"], pending["draft"]["total"])
    if not answered:
        return _refuse("The customer has not answered the summary yet. Show it and wait for their yes in a new message.")
    problem = _not_a_yes(answered, ctx)
    if problem:
        return _refuse(problem)
    draft, problem = build(args, ctx)
    if problem:
        return _refuse(f"{problem} Then make a new summary.")
    if draft != pending["draft"]:
        return _refuse("This is not the order in the summary the customer saw. Call draft_order without confirm "
                       "to make a new summary and show it.")
    risk = _risk(book, draft)
    if not book.take(ctx.chat_id, pending["code"]):
        return _refuse(NO_PENDING)
    try:
        made = book.create(draft, ctx.chat_id, risk)
    except Exception:
        log.exception("the order was not created")
        book.save_draft(ctx.chat_id, pending["code"], pending["draft"], pending["after_step"])
        return {"ok": False, "feedback": NOT_SAVED}
    _record(ctx, made, draft, risk)
    out = {"ok": True, "step": "created", "order": made["order"], "subtotal": orders.amount(draft["subtotal"])}
    if draft.get("discounts"):
        out["discounts"] = _shown_discounts(draft)
    out.update({"fee": orders.amount(draft["fee"]), "total": orders.amount(draft["total"]),
                "days_min": draft["days_min"], "days_max": draft["days_max"], "next": CREATED_NEXT})
    return out


def _refuse(feedback):
    return {"ok": False, "feedback": feedback}


def _risk(book, draft):
    """cod_risk's level and reasons, run before the draft is taken. A lookup that fails never
    stops the order: it goes to the store tagged unknown (review t261028j finding 6)."""
    try:
        return cod_risk.assess(book, draft)
    except Exception:
        log.exception("the cod_risk check could not run; the order is tagged unknown")
        return {"level": "unknown", "reasons": ["The risk check could not run."]}


def created(steps):
    """The draft_order result that created an order in this turn (after the customer's last
    message in steps), or None. Never raises."""
    try:
        last_user = max((s["n"] for s in steps if s["role"] == "user"), default=0)
        for s in steps:
            if s["n"] > last_user and s["role"] == "tool" and s["name"] == NAME:
                out = json.loads(s["content"] or "null")
                if (isinstance(out, dict) and out.get("ok") is True and out.get("step") == "created"
                        and out.get("order") and out.get("total") is not None):
                    return out
    except Exception:
        log.exception("could not tell if this turn created an order")
    return None


def summary_reply(steps, after, total):
    """The step number of the summary the customer saw: the first reply the model wrote after
    step `after` that shows the draft's total. Fixed lines (model down, limit, order placed)
    and a person's reply in an imported chat never count. None when no such reply went out."""
    want = send_check.amount(str(total))
    for s in steps:
        if (s["n"] > after and s["role"] == "assistant" and not s["tool_calls"] and s["name"] is None
                and want in send_check.prices_in(s["content"] or "")):
            return s["n"]
    return None


def answers(steps, after, total):
    """The customer's messages after the summary reply (summary_reply), oldest first."""
    shown_at = summary_reply(steps, after, total)
    return [s for s in steps if s["role"] == "user" and s["n"] > shown_at] if shown_at is not None else []


def _yes_fold(text):
    """Lower case, Arabic letters folded and marks dropped, the thumbs up as ok, repeats as one letter."""
    text = delivery.AR_MARKS.sub("", str(text or "").lower().translate(delivery.AR_FOLD))
    for sign, word in SIGNS.items():
        text = text.replace(sign, word)
    return REPEATS.sub(r"\1", text)


YES = frozenset(_yes_fold(w) for w in YES_WORDS.split())
OK = frozenset(_yes_fold(w) for w in OK_WORDS.split())
KNOWN = YES | OK
QUESTION_MARKS = ("?", "\u061f", "\uff1f")


def plain_yes(text):
    """True when the text is only a yes: "تمام، أكد", "ok", "yes please", "تماااام", a thumbs up. A question,
    or any word that is not a yes or a polite word (بس, لا, but, a size, a number), is not."""
    if any(q in text for q in QUESTION_MARKS):
        return False
    words = [w[1:] if w.startswith("و") and w[1:] in KNOWN else w for w in WORDS.findall(_yes_fold(text))]
    return bool(words) and all(w in KNOWN for w in words) and any(w in YES for w in words)


def _not_a_yes(answered, ctx):
    """None when every answer is a plain yes, else the feedback for the model."""
    for s in answered:
        kinds = {m.get("kind") for m in s.get("media") or []}
        text = s["content"] or ""
        if "image" in kinds:
            return NOT_A_YES
        if "audio" in kinds:
            if s is not answered[-1] or not getattr(ctx.message, "audio", None):
                return NOT_A_YES       # an earlier voice note cannot be heard again
            heard = ctx.cache.get(voice_note.NAME)
            if heard is None:
                return HEAR_FIRST
            if not heard.get("ok"):
                return NOT_A_YES
            text = f"{text} {heard['text']}"
        if not plain_yes(text):
            return NOT_A_YES
    return None


def quote(args):
    """The totals for items and payment with the store's offers, and the fee and days when a governorate is
    given. Nothing is saved and no name or address is needed."""
    items, kinds, currency, problem = _lines(args["items"], None)
    if problem:
        return _refuse(problem)
    fee, place = None, None
    if args.get("governorate"):
        place = delivery.quote(args["governorate"])
        if not place["ok"]:
            return _refuse(place["note"])
        fee = place["fee"]
    payment = _key(args["payment"]) if args.get("payment") else None
    got = offers.apply(_offer_lines(items, kinds), payment, offers.current(), fee=fee)
    out = {"ok": True, "step": "quote", "items": _shown_items(items), "subtotal": orders.amount(got["subtotal"])}
    if payment:
        out["payment"] = payment
    if got["discounts"]:
        out["discounts"] = [{"offer": d["offer"], "what": d["what"], "discount": orders.amount(d["discount"])}
                            for d in got["discounts"]]
    if place is not None:
        out.update({"fee": orders.amount(got["fee"]), "governorate": place["governorate"],
                    "days_min": place["days_min"], "days_max": place["days_max"]})
        if place.get("offer_id"):
            out["offer_id"] = place["offer_id"]   # the delivery offer that set the fee
    out.update({"total": orders.amount(got["total"]), "next": QUOTE_NEXT})
    return out


def build(args, ctx):
    """The order from the arguments and the store, delivery and offers data now: (draft, None) or (None,
    feedback)."""
    chat = ctx.chats.get(ctx.chat_id)
    whatsapp = orders.phone_key(chat["customer_id"]) if chat["channel"] == "whatsapp" else ""
    phone = orders.phone_key(args["phone"]) if args.get("phone") else whatsapp
    if not phone:
        return None, "Ask the customer for a phone number for the courier and pass it as phone."
    name = _text(args["name"])
    items, kinds, currency, problem = _lines(args["items"], name)
    if problem:
        return None, problem
    place = delivery.quote(args["governorate"])
    if not place["ok"]:
        return None, place["note"]
    payment = _key(args["payment"]) if args.get("payment") else None
    got = offers.apply(_offer_lines(items, kinds), payment, offers.current(), fee=place["fee"])
    draft = {
        "items": items, "name": name, "address": _text(args["address"]),
        "phone": phone, "whatsapp": whatsapp,
        "governorate": place["governorate"], "area": place["area"],
        "days_min": place["days_min"], "days_max": place["days_max"],
        "subtotal": str(got["subtotal"]), "fee": str(got["fee"]), "total": str(got["total"]),
        "currency": currency,
    }
    if payment:
        draft["payment"] = payment
    if place.get("offer_id"):
        draft["offer_id"] = place["offer_id"]  # the delivery offer that set the fee, kept with the order
    if got["discounts"]:
        draft["discounts"] = [{"offer": d["offer"], "what": d["what"], "discount": str(d["discount"])}
                              for d in got["discounts"]]
    return draft, None


def _offer_lines(items, kinds):
    """The lines offers.apply reads: each item with its product's type from the store data."""
    return [{**i, **({"type": kinds[i["product"]]} if kinds.get(i["product"]) else {})} for i in items]


def _lines(raw_items, name):
    """(items, {product: type}, currency, None) from the arguments' items and the store data, or
    (None, None, None, feedback). name None: a quote, where a printing line needs no name to print."""
    catalogue = store.catalogue()
    lines, currencies, kinds = {}, set(), {}
    for it in raw_items:
        item, v, problem = _variant(catalogue, it["product"], it.get("size"), it.get("tier"))
        if problem:
            return None, None, None, problem
        print_name, problem = _print_name(item, it, name)
        if problem:
            return None, None, None, problem
        if item.get("type"):
            kinds[item["title"]] = item["type"]
        key = (item["title"], v.get("tier", ""), v.get("size", ""), print_name)
        if key not in lines:
            lines[key] = {"product": item["title"], **({"tier": v["tier"]} if v.get("tier") else {}),
                          "size": v.get("size", ""), "sku": v.get("sku", ""),
                          "price": str(orders.money(v["price"])), "quantity": 0}
            if print_name:
                lines[key]["print_name"] = print_name
        line = lines[key]
        line["quantity"] += it["quantity"]
        if line["quantity"] > MAX_QUANTITY:
            return None, None, None, f"At most {MAX_QUANTITY} of one item. Say that is the most for one order."
        if v.get("currency"):
            currencies.add(v["currency"])
    if len(currencies) > 1:
        return None, None, None, "The items are priced in different currencies. Order them one at a time."
    items = sorted(lines.values(), key=lambda line: (line["product"], line.get("tier", ""), line["size"],
                                                   line.get("print_name", "")))
    return items, kinds, (currencies.pop() if currencies else None), None


def _shown_items(items):
    return [{"product": i["product"], **({"tier": i["tier"]} if i.get("tier") else {}),
             **({"size": i["size"]} if i["size"] else {}),
             **({"print_name": i["print_name"]} if i.get("print_name") else {}),
             "quantity": i["quantity"], "price": orders.amount(i["price"])} for i in items]


def _shown_discounts(draft):
    return [{"offer": d["offer"], "what": d["what"], "discount": orders.amount(d["discount"])}
            for d in draft.get("discounts") or []]


def shown(draft):
    """The summary the model reads: amounts as numbers, no sku, the phone as Egyptians write it; the payment
    and each offer's discount when the draft has them."""
    out = {"items": _shown_items(draft["items"]), "subtotal": orders.amount(draft["subtotal"])}
    if draft.get("discounts"):
        out["discounts"] = _shown_discounts(draft)
    out.update({
        "fee": orders.amount(draft["fee"]), "total": orders.amount(draft["total"]),
        "name": draft["name"], "phone": orders.local_phone(draft["phone"]),
        "governorate": draft["governorate"], "address": draft["address"],
        "days_min": draft["days_min"], "days_max": draft["days_max"],
    })
    if draft.get("payment"):
        out["payment"] = draft["payment"]
    return out


def _variant(catalogue, product, size, tier=None):
    """(product, variant, None) for an exact title, tier and size from the store data, else
    (None, None, feedback). A product whose variants have tiers needs the tier; one with no tiers
    refuses it."""
    item = next((i for i in catalogue if _fold(i.get("title")) == _fold(product)), None)
    if item is None:
        return None, None, "No product has that title. Call store and use the exact title it gives."
    variants = item.get("variants", [])
    tiers = list(dict.fromkeys(v["tier"] for v in variants if v.get("tier")))
    if tier is not None and tier.strip():
        if not tiers:
            return None, None, f"{item['title']} has no tiers. Leave tier out for it."
        variants = [v for v in variants if _fold(v.get("tier")) == _fold(tier)]
        if not variants:
            return None, None, f"{item['title']} comes in the tiers {', '.join(tiers)}. Ask the customer which one."
    elif len(tiers) > 1:
        return None, None, f"{item['title']} comes in the tiers {', '.join(tiers)}. Ask the customer which one."
    sizes = ", ".join(dict.fromkeys(v.get("size", "") for v in variants))
    if size is None or not size.strip():
        found = variants if len(variants) == 1 else []
    elif not any(v.get("size") for v in variants):
        return None, None, f"{item['title']} has no sizes. Leave size out for it."
    else:
        found = [v for v in variants if _fold(v.get("size")) == _fold(size)]
        found = found or [v for v in variants if _fold(v.get("size")).split(" (")[0] == _fold(size)]
    if len(found) != 1:
        return None, None, f"{item['title']} comes in: {sizes}. Ask the customer which one."
    v = found[0]
    if v.get("stock") == "out":
        what = " ".join(x for x in (v.get("tier"), v.get("size")) if x) or "this size"
        return None, None, f"{item['title']} in {what} is out of stock. Tell the customer."
    if "price" not in v:
        return None, None, "This product has no price in the store data."
    return item, v, None


def _print_name(item, it, name):
    """(the name to print, None) for a printing line, ("", None) for any other line, else (None, feedback).
    A printing line with no print_name prints the order's name."""
    if _fold(item.get("type")) != PRINTING:
        if "print_name" in it:
            return None, (f"print_name goes only on a printing line, not on {item['title']}. Put the name on "
                          "the printing line, or leave it out.")
        return "", None
    if name is None and "print_name" not in it:   # a quote: the name to print does not change the price
        return "", None
    wanted = _text(it["print_name"]) if "print_name" in it else name
    if not PRINT_MIN <= len(wanted) <= PRINT_MAX:
        return None, (f"The name to print must be {PRINT_MIN} to {PRINT_MAX} characters. Ask the customer which "
                      "name to print and pass it as print_name.")
    return wanted, None


def _record(ctx, made, draft, risk):
    """An "order_created" row in the result log, with the risk level, for the night study and the team."""
    detail = {"order": made["order"], "store": made["store"], "total": orders.amount(draft["total"]),
              "cod_risk": risk["level"], "reasons": risk["reasons"]}
    if made.get("store_total_differs"):
        detail["store_total_differs"] = True
    if isinstance(draft.get("area"), str):  # the delivery zone, for the morning page's delivery days fact (reflection/facts.py)
        detail["area"] = draft["area"]
    _log(ctx, "order_created", detail)


def _log(ctx, outcome, detail):
    """One row in the result log, with the ids of the lessons the turn handed before this call.
    A failure here is logged and never stops the order."""
    try:
        Results(ctx.chats.db).record(ctx.chat_id, outcome, stage=getattr(ctx.stage, "name", None),
                                     lessons=getattr(ctx, "lesson_ids", ()), detail=detail)
    except Exception:
        log.exception("the %s row was not written to the result log", outcome)


def _fold(s):
    return " ".join(str(s or "").lower().split())


def _key(s):
    return offers._key(str(s or ""))


def _text(s):
    return " ".join(str(s).split())
