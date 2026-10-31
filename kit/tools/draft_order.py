"""draft_order: places an order in two steps, so nothing is created without the customer's yes.

Step 1 (no confirm): checks the items against the store data and the governorate against
the delivery data, works out the subtotal, fee and total in code (never from the model),
saves a pending draft for the chat and returns a summary with a short code.

A printing line (a product whose type in the store data is Printing) carries the name to
print: the order's name unless the customer gives another as print_name (DECISIONS item 28).
print_name on any other line is refused. Lines are keyed by product, size and name to print,
so two names are two lines, and the name is part of the draft the customer confirms.

Step 2 (confirm set to that code) creates the order only when:
- this chat has a pending draft with that code, less than a day old,
- the model's own reply showing the draft's total went out after the summary (a fixed line or a
  team member's reply does not count), the customer has written since, and every message they
  wrote after that reply is a plain yes: no question, no change, no photo (a voice note counts
  only in this turn, by its transcript), and
- the same details, worked out again from the data now, still match the pending draft.
Each summary writes an "order_drafted" row to the result log. The order goes to the store with
the chat id on it and cod_risk's level as a tag ("unknown" when the check could not run), and an
"order_created" row goes to the result log. The pending draft is used once, and a turn that
created an order makes no new summary, so a re-draft right after an order cannot become a
second order (review t261028j round 2, finding 1).

Money keys in results are price, fee, subtotal and total only, so the send check reads them.
"""
import hmac
import json
import logging
import re
import time
from decimal import Decimal

from kit import orders, send_check
from kit.tools import cod_risk, delivery, store, voice_note
from reflection.results import Results

log = logging.getLogger("kit.tools.draft_order")

MAX_LINES = 10
MAX_QUANTITY = 20
FIELDS = {"items", "name", "governorate", "address", "phone", "confirm"}
REQUIRED = ("items", "name", "governorate", "address")
ITEM_FIELDS = {"product", "size", "quantity", "print_name"}
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
        "the same details and confirm set to the code. A question, or a yes with a change, means step 1 again."),
    "parameters": {
        "type": "object",
        "properties": {
            "items": {"type": "array", "description": "What the customer is ordering.", "items": {
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "The product title exactly as the store tool gives it."},
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
        },
        "required": list(REQUIRED),
        "additionalProperties": False,
    },
}}

SUMMARY_NEXT = (
    "Show this summary to the customer in their language and script: items (with the name to print on a "
    "printing line), subtotal, delivery fee, total, name, address, phone and delivery days. Ask them to confirm. Never show the code. When they answer with a "
    "plain yes in a new message, call draft_order again with the same details and confirm set to the code. A "
    "question, or a yes with a change, needs a new summary: call draft_order again without confirm.")
CREATED_NEXT = "Tell the customer the order is received, with its number, the total and the delivery days."
NOT_SAVED = "The store did not take the order. Say you will check with the team, or call handoff."
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
    missing = [k for k in REQUIRED if k not in args]
    if missing:
        return False, f"Missing: {', '.join(missing)}. Ask the customer for them first."
    items = args["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_LINES:
        return False, f"items must be a list of 1 to {MAX_LINES} lines."
    for it in items:
        if not isinstance(it, dict) or set(it) - ITEM_FIELDS or "product" not in it or "quantity" not in it:
            return False, ("Each item takes product and quantity, size when the product has sizes, and print_name "
                           "on a printing line. Nothing else.")
        if not isinstance(it["product"], str) or not 0 < len(it["product"].strip()) <= 120:
            return False, "product must be the title from the store tool."
        if "size" in it and (not isinstance(it["size"], str) or len(it["size"]) > 60):
            return False, "size must be the size text from the store tool."
        if "print_name" in it and (not isinstance(it["print_name"], str)
                                   or not PRINT_MIN <= len(_text(it["print_name"])) <= PRINT_MAX):
            return False, f"print_name must be the name to print, {PRINT_MIN} to {PRINT_MAX} characters."
        q = it["quantity"]
        if isinstance(q, bool) or not isinstance(q, int) or not 1 <= q <= MAX_QUANTITY:
            return False, f"quantity must be a whole number from 1 to {MAX_QUANTITY}. For more, call handoff."
    for key, lo, hi in TEXT_LIMITS:
        v = args[key]
        if not isinstance(v, str) or not lo <= len(_text(v)) <= hi:
            return False, f"{key} must be text, {lo} to {hi} characters."
    if "phone" in args and (not isinstance(args["phone"], str) or not orders.phone_key(args["phone"])):
        return False, "phone must be a phone number, or left out to use this chat's WhatsApp number."
    if "confirm" in args and (not isinstance(args["confirm"], str) or not 0 < len(args["confirm"].strip()) <= 12):
        return False, "confirm must be the code from the summary."
    return True, ""


def run(args, ctx):
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
    return {"ok": True, "step": "created", "order": made["order"], "subtotal": orders.amount(draft["subtotal"]),
            "fee": orders.amount(draft["fee"]), "total": orders.amount(draft["total"]),
            "days_min": draft["days_min"], "days_max": draft["days_max"], "next": CREATED_NEXT}


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
    step `after` that shows the draft's total. Fixed lines (model down, limit, handoff) and a
    team member's replies never count. None when no such reply went out."""
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


def build(args, ctx):
    """The order from the arguments and the store and delivery data now: (draft, None) or (None, feedback)."""
    chat = ctx.chats.get(ctx.chat_id)
    whatsapp = orders.phone_key(chat["customer_id"]) if chat["channel"] == "whatsapp" else ""
    phone = orders.phone_key(args["phone"]) if args.get("phone") else whatsapp
    if not phone:
        return None, "Ask the customer for a phone number for the courier and pass it as phone."
    catalogue = store.catalogue()
    name = _text(args["name"])
    lines, currencies = {}, set()
    for it in args["items"]:
        item, v, problem = _variant(catalogue, it["product"], it.get("size"))
        if problem:
            return None, problem
        print_name, problem = _print_name(item, it, name)
        if problem:
            return None, problem
        key = (item["title"], v.get("size", ""), print_name)
        if key not in lines:
            lines[key] = {"product": item["title"], "size": v.get("size", ""), "sku": v.get("sku", ""),
                          "price": str(orders.money(v["price"])), "quantity": 0}
            if print_name:
                lines[key]["print_name"] = print_name
        line = lines[key]
        line["quantity"] += it["quantity"]
        if line["quantity"] > MAX_QUANTITY:
            return None, f"At most {MAX_QUANTITY} of one item. For more, call handoff."
        if v.get("currency"):
            currencies.add(v["currency"])
    if len(currencies) > 1:
        return None, "The items are priced in different currencies. Call handoff."
    quote = delivery.quote(args["governorate"])
    if not quote["ok"]:
        return None, quote["note"]
    items = sorted(lines.values(), key=lambda line: (line["product"], line["size"], line.get("print_name", "")))
    subtotal = sum((orders.money(line["price"]) * line["quantity"] for line in items), Decimal(0))
    fee = orders.money(quote["fee"])
    return {
        "items": items, "name": name, "address": _text(args["address"]),
        "phone": phone, "whatsapp": whatsapp,
        "governorate": quote["governorate"], "area": quote["area"],
        "days_min": quote["days_min"], "days_max": quote["days_max"],
        "subtotal": str(subtotal), "fee": str(fee), "total": str(subtotal + fee),
        "currency": currencies.pop() if currencies else None,
    }, None


def shown(draft):
    """The summary the model reads: amounts as numbers, no sku, the phone as Egyptians write it."""
    return {
        "items": [{"product": i["product"], **({"size": i["size"]} if i["size"] else {}),
                   **({"print_name": i["print_name"]} if i.get("print_name") else {}),
                   "quantity": i["quantity"], "price": orders.amount(i["price"])} for i in draft["items"]],
        "subtotal": orders.amount(draft["subtotal"]), "fee": orders.amount(draft["fee"]),
        "total": orders.amount(draft["total"]),
        "name": draft["name"], "phone": orders.local_phone(draft["phone"]),
        "governorate": draft["governorate"], "address": draft["address"],
        "days_min": draft["days_min"], "days_max": draft["days_max"],
    }


def _variant(catalogue, product, size):
    """(product, variant, None) for an exact title and size from the store data, else (None, None, feedback)."""
    item = next((i for i in catalogue if _fold(i.get("title")) == _fold(product)), None)
    if item is None:
        return None, None, "No product has that title. Call store and use the exact title it gives."
    variants = item.get("variants", [])
    sizes = ", ".join(v.get("size", "") for v in variants)
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
        return None, None, f"{item['title']} in {v.get('size', 'this size')} is out of stock. Tell the customer."
    if "price" not in v:
        return None, None, "This product has no price in the store data. Say you will check with the team."
    return item, v, None


def _print_name(item, it, name):
    """(the name to print, None) for a printing line, ("", None) for any other line, else (None, feedback).
    A printing line with no print_name prints the order's name."""
    if _fold(item.get("type")) != PRINTING:
        if "print_name" in it:
            return None, (f"print_name goes only on a printing line, not on {item['title']}. Put the name on "
                          "the printing line, or leave it out.")
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


def _text(s):
    return " ".join(str(s).split())
