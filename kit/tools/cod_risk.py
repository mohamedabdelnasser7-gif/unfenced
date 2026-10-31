"""cod_risk: how risky a cash on delivery order looks, for the team only.

Reads the chat's pending order summary (from draft_order) and the order history, and
gives a level (low, medium or high) with plain reasons:
- past refusals by this phone (the WhatsApp number or the delivery phone),
- a first order with a high total,
- the governorate's refusal rate, once there are enough finished orders there.

The level goes on the order as a tag, and the level and reasons into the result log when
the order is created; the customer never sees them. The model reads only the next step
(HIGH_NEXT or OTHER_NEXT), never the level or the reasons: the courier phone comes from the
customer's text, so the reasons could tell one customer about another number's past orders
(red team t261028j F4). It sets no policy: when the level is high, the agent only
confirms the address and delivery day clearly. The thresholds below are demo values.

On the live store the refusal history needs courier results, which are not connected
yet, so there only the first order check runs.
"""
from decimal import Decimal

from kit import orders

HIGH_TOTAL = Decimal(25000)  # a first order at or above this total counts as high: above any one pair
AREA_MIN_ORDERS = 5          # finished orders needed before a governorate's rate counts
AREA_RATE = Decimal("0.3")   # refused share of finished orders that counts as many

NAME = "cod_risk"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "For the team only: how risky this cash on delivery order looks (low, medium or high), from past "
        "orders. Call it after draft_order makes the summary. Never tell the customer about it."),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}}

HIGH_NEXT = ("Never mention this check to the customer. Before they confirm, repeat the address and the "
             "delivery days clearly and ask them to check both.")
OTHER_NEXT = "Never mention this check to the customer. Nothing changes in how you confirm."


def check(args, ctx):
    if args:
        return False, "cod_risk takes no arguments. It reads the order summary from draft_order."
    return True, ""


def run(args, ctx):
    book = orders.Book(ctx.chats.db)
    pending = book.pending(ctx.chat_id)
    if pending is None:
        return {"ok": False, "feedback": "There is no order summary yet. Call draft_order without confirm first."}
    risk = assess(book, pending["draft"])
    return {"ok": True, "next": HIGH_NEXT if risk["level"] == "high" else OTHER_NEXT}


def assess(book, draft):
    """{"level": low, medium or high, "reasons": [plain lines]} for one order draft."""
    past = book.for_phones({draft["phone"], draft["whatsapp"]})
    refused = sum(o["status"] == "refused" for o in past)
    delivered = sum(o["status"] == "delivered" for o in past)
    points, reasons = 0, []
    if refused:
        points += 2 if refused >= 2 else 1
        reasons.append(f"Refused {refused} earlier cash on delivery order{'s' if refused > 1 else ''}.")
    if not past and orders.money(draft["total"]) >= HIGH_TOTAL:
        points += 1
        reasons.append("First order from this number, and the total is high.")
    area_refused, area_done = book.area_counts(draft["governorate"])
    if area_done >= AREA_MIN_ORDERS and Decimal(area_refused) >= AREA_RATE * area_done:
        points += 1
        reasons.append(f"Many cash on delivery orders to {draft['governorate']} were refused "
                       f"({area_refused} of {area_done} finished orders).")
    level = "high" if points >= 2 else "medium" if points == 1 else "low"
    if not reasons:
        reasons.append(f"{delivered} earlier orders delivered, none refused." if delivered
                       else "No warning signs in past orders.")
    return {"level": level, "reasons": reasons}
