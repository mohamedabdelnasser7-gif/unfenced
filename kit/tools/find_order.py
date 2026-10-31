"""find_order: the customer's own orders, found by the WhatsApp number they write from.

Never by an order number alone. The number comes from the chat, never from the model, and
an order comes back only when its phone or WhatsApp tag matches that number exactly. An
order number the customer names only picks among those orders. The status comes from the
store: Shopify, or the demo order book.
"""
import re

from kit import orders
from kit.tools import delivery

NAME = "find_order"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Find this customer's own orders and their status, by the WhatsApp number they are writing from. "
        "Never ask for an order number first; call this."),
    "parameters": {
        "type": "object",
        "properties": {"order": {
            "type": "string",
            "description": "Only if the customer named an order number: it picks that one from their own orders."}},
        "additionalProperties": False,
    },
}}

OPEN = ("received", "confirmed", "shipped", "partly shipped", "on hold")
NONE_FOUND = ("No orders under this WhatsApp number. Ask whether they ordered from another number; if so, "
              "call handoff so the team can check. Never look an order up by its number.")
NOT_THEIRS = ("None of the orders on this WhatsApp number has that order number. These are the orders on this "
              "number. If the order was placed from another number, call handoff so the team can check.")


def check(args, ctx):
    extra = set(args) - {"order"}
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}. Only order is allowed."
    o = args.get("order", "")
    if not isinstance(o, str) or len(o) > 20:
        return False, "order must be a short order number, or left out."
    return True, ""


def run(args, ctx):
    chat = ctx.chats.get(ctx.chat_id)
    key = orders.phone_key(chat["customer_id"]) if chat["channel"] == "whatsapp" else ""
    if not key:
        return {"ok": False, "feedback": "This chat has no WhatsApp number to find orders by. Call handoff."}
    found = orders.Book(ctx.chats.db).for_phones({key})
    if not found:
        return {"ok": True, "orders": [], "note": NONE_FOUND}
    want = re.sub(r"\D", "", args.get("order") or "")
    if want:
        picked = [o for o in found if re.sub(r"\D", "", o["order"]) == want]
        if not picked:
            return {"ok": True, "orders": [shown(o) for o in found[:orders.MAX_FOUND]], "note": NOT_THEIRS}
        found = picked
    return {"ok": True, "orders": [shown(o) for o in found[:orders.MAX_FOUND]]}


def shown(o):
    """One order as the model reads it: number, status, day placed, items, total, and delivery days while open."""
    out = {"order": o["order"], "status": o["status"], "placed": orders.placed_day(o["placed_at"]), "items": o["items"]}
    if o.get("total") is not None:
        out["total"] = orders.amount(o["total"])
    if o["status"] in OPEN and o.get("governorate"):
        q = delivery.quote(o["governorate"])
        if q["ok"]:
            out["days_min"], out["days_max"] = q["days_min"], q["days_max"]
    return out
