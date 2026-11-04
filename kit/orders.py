"""The order book the order tools share: pending drafts, orders and order history.

Pending drafts: one per chat, saved when draft_order makes a summary, taken when the
customer confirms. Orders go to Shopify as draft orders (draftOrderCreate) when
SHOPIFY_STORE and SHOPIFY_TOKEN are set, else to the demo_orders table in the SQLite file.
Every order carries its chat id, so a later delivery result links back to the chat, and a
tag with the WhatsApp number that placed it, so that number can find it. A printing line's
name to print is saved with the items on the demo store and sent to Shopify on that line as
the custom attribute "Name to print".

History for find_order and cod_risk: on the demo store, demo/orders.json (made-up
customers) plus demo_orders; on Shopify, the store's orders and draft orders for a phone.
Orders are only ever found by phone, matched exactly in code, never by an order number.

Money is kept as Decimal strings and given out as numbers by amount().
"""
import json
import re
import secrets
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from kit import env, net
from kit.send_check import EASTERN_DIGITS
from kit.tools import store

ROOT = Path(__file__).resolve().parent.parent
DEMO_ORDERS = ROOT / "demo" / "orders.json"
DRAFT_SECONDS = 24 * 3600   # a summary older than this needs a fresh one
CODE_LETTERS = "BCDFGHJKLMNPQRSTVWXZ"  # letters only, so a code is never read as an amount
CODE_LENGTH = 5
FIRST_ORDER_NUMBER = 1001
MAX_FOUND = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS order_drafts (
  chat_id TEXT PRIMARY KEY REFERENCES chats (id),
  code TEXT NOT NULL,
  draft TEXT NOT NULL,
  after_step INTEGER NOT NULL,
  at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_orders (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  chat_id TEXT NOT NULL REFERENCES chats (id),
  whatsapp TEXT NOT NULL,
  phone TEXT NOT NULL,
  customer TEXT NOT NULL,
  governorate TEXT NOT NULL,
  address TEXT NOT NULL,
  items TEXT NOT NULL,
  subtotal TEXT NOT NULL,
  fee TEXT NOT NULL,
  total TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'received',
  cod_risk TEXT NOT NULL,
  risk_reasons TEXT NOT NULL,
  tags TEXT NOT NULL,
  placed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS demo_orders_whatsapp ON demo_orders (whatsapp);
CREATE INDEX IF NOT EXISTS demo_orders_phone ON demo_orders (phone);
"""

# Columns added after the table was first made (decision 105): read by ALTER TABLE when missing.
ORDER_COLUMNS = (("payment", "TEXT NOT NULL DEFAULT ''"), ("discount", "TEXT NOT NULL DEFAULT '0'"),
                 ("discounts", "TEXT NOT NULL DEFAULT '[]'"))

# Statuses as the model reads them.
FINISHED = ("delivered", "refused")


class StoreError(Exception):
    """The store did not take the order. The message never carries a key."""


# phones and money

def phone_key(raw):
    """A phone number as digits with the country code, or "" if it does not look like one.

    01012345678, +20 10 1234 5678, 00201012345678 and 201012345678 are the same number.
    """
    d = re.sub(r"\D", "", str(raw or "").translate(EASTERN_DIGITS))
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 11 and d.startswith("01"):
        d = "20" + d[1:]
    elif len(d) == 10 and d.startswith("1"):
        d = "20" + d
    return d if 10 <= len(d) <= 15 else ""


def local_phone(key):
    """An Egyptian number the way Egyptians write it (01012345678); any other number with a +."""
    if len(key) == 12 and key.startswith("20") and key[2] != "0":
        return "0" + key[2:]
    return "+" + key if key else ""


def money(x):
    """A Decimal from a price in the data ("16500", "16500.00", 60). Raises ValueError otherwise."""
    if isinstance(x, bool):
        raise ValueError("not an amount")
    try:
        d = Decimal(str(x).strip())
    except InvalidOperation:
        raise ValueError("not an amount") from None
    if not d.is_finite() or d < 0:
        raise ValueError("not an amount")
    return d


def amount(d):
    """A Decimal amount as the number a result gives out: 16500, or 16500.5."""
    d = money(d)
    return int(d) if d == d.to_integral_value() else float(d.quantize(Decimal("0.01")))


def new_code():
    return "".join(secrets.choice(CODE_LETTERS) for _ in range(CODE_LENGTH))


def on_shopify():
    return bool(env.get("SHOPIFY_STORE") and env.get("SHOPIFY_TOKEN"))


class Book:
    def __init__(self, db):
        self.db = db
        self.db.script(SCHEMA)
        with self.db.tx() as c:  # a demo_orders table made before offers
            have = {r[1] for r in c.execute("PRAGMA table_info(demo_orders)")}
            for name, decl in ORDER_COLUMNS:
                if name not in have:
                    c.execute(f"ALTER TABLE demo_orders ADD COLUMN {name} {decl}")

    # pending drafts

    def save_draft(self, chat_id, code, draft, after_step):
        """Keep the summary the customer is asked to confirm. A new summary replaces the old one."""
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO order_drafts VALUES (?, ?, ?, ?, ?)",
                      (chat_id, code, json.dumps(draft, ensure_ascii=False, sort_keys=True), after_step, time.time()))

    def pending(self, chat_id):
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM order_drafts WHERE chat_id = ?", (chat_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["draft"] = json.loads(d["draft"])
        return d

    def take(self, chat_id, code):
        """Remove the pending draft with this code. True only for the one caller that removed it."""
        with self.db.tx() as c:
            return c.execute("DELETE FROM order_drafts WHERE chat_id = ? AND code = ?", (chat_id, code)).rowcount == 1

    def drop_draft(self, chat_id):
        with self.db.tx() as c:
            c.execute("DELETE FROM order_drafts WHERE chat_id = ?", (chat_id,))

    # orders

    def create(self, draft, chat_id, risk):
        """Save the order in the store. Returns {"order": its number, "store": "shopify" or "demo"}."""
        tags = ["whatsapp", "sales-agent", f"cod-risk-{risk['level']}"]
        if draft["whatsapp"]:
            tags.append(whatsapp_tag(draft["whatsapp"]))
        if draft.get("payment"):
            tags.append(f"payment-{draft['payment']}")
        if on_shopify():
            return _shopify_create(draft, chat_id, tags)
        with self.db.tx() as c:
            n = c.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM demo_orders").fetchone()[0]
            name = f"#{FIRST_ORDER_NUMBER - 1 + n}"
            c.execute(
                "INSERT INTO demo_orders (id, name, chat_id, whatsapp, phone, customer, governorate, address, items, "
                "subtotal, fee, total, status, cod_risk, risk_reasons, tags, placed_at, payment, discount, discounts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?, ?, ?, ?, ?, ?)",
                (n, name, chat_id, draft["whatsapp"], draft["phone"], draft["name"], draft["governorate"],
                 draft["address"], json.dumps(draft["items"], ensure_ascii=False), draft["subtotal"], draft["fee"],
                 draft["total"], risk["level"], json.dumps(risk["reasons"], ensure_ascii=False), json.dumps(tags),
                 time.time(), draft.get("payment") or "", str(discount_of(draft)),
                 json.dumps(draft.get("discounts") or [], ensure_ascii=False)))
        return {"order": name, "store": "demo"}

    def demo_order(self, name):
        """One demo_orders row as a dict (for the team and for tests)."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM demo_orders WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def for_phones(self, phones):
        """Orders whose WhatsApp or delivery phone is exactly one of these numbers, newest first."""
        keys = {k for k in (phone_key(p) for p in phones) if k}
        if not keys:
            return []
        if on_shopify():
            found = {}
            for k in sorted(keys):
                for o in _shopify_orders(k):
                    found[o["order"]] = o
            out = list(found.values())
        else:
            out = [o for o in self._demo_history() if o["phone"] in keys or o["whatsapp"] in keys]
        return sorted(out, key=lambda o: o["placed_at"], reverse=True)

    def area_counts(self, governorate):
        """(refused, finished) cash on delivery orders to a governorate, from the demo history.

        The live store has no refusal record yet (courier results are not connected), so (0, 0) there.
        """
        if on_shopify():
            return 0, 0
        done = [o for o in self._demo_history() if o["governorate"] == governorate and o["status"] in FINISHED]
        return sum(o["status"] == "refused" for o in done), len(done)

    def _demo_history(self):
        out = []
        for o in json.loads(DEMO_ORDERS.read_text(encoding="utf-8"))["orders"]:
            out.append({"order": o["name"], "status": o["status"], "placed_at": _when(o["placed"]),
                        "governorate": o["governorate"], "items": _plain_items(o["items"]),
                        "total": str(money(o["total"])),
                        "phone": phone_key(o["phone"]), "whatsapp": phone_key(o["whatsapp"])})
        with self.db.tx() as c:
            rows = c.execute("SELECT * FROM demo_orders").fetchall()
        for r in rows:
            out.append({"order": r["name"], "status": r["status"], "placed_at": r["placed_at"],
                        "governorate": r["governorate"], "items": _plain_items(json.loads(r["items"])),
                        "total": r["total"], "phone": r["phone"], "whatsapp": r["whatsapp"]})
        return out


def _plain_items(items):
    """Product, tier, size and quantity only."""
    return [{k: i[k] for k in ("product", "tier", "size", "quantity") if i.get(k) not in (None, "")} for i in items]


def _when(day):
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def placed_day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


# Shopify. Never run against a live store from tests: every test stubs the request.

def _graphql(query, variables):
    shop = env.get("SHOPIFY_STORE").removeprefix("https://").split("/")[0]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", shop):
        raise StoreError("SHOPIFY_STORE must look like name.myshopify.com")
    version = env.get("SHOPIFY_API_VERSION", store.SHOPIFY_DEFAULT_VERSION)
    url = f"https://{shop}/admin/api/{version}/graphql.json"
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-Shopify-Access-Token": env.get("SHOPIFY_TOKEN"), "Content-Type": "application/json"})
    with net.open_once(req, timeout=20) as r:   # no redirect: the token never follows one
        out = json.loads(r.read().decode("utf-8"))
    if out.get("errors"):
        raise StoreError("Shopify answered with errors")
    return out["data"]




# Checked against shopify.dev, Admin GraphQL 2026-10, on 28 Oct 2026: draftOrderCreate and
# DraftOrderInput (shippingLine.priceWithCurrency, since price is deprecated; countryCode, since
# country and province are deprecated), productVariants with sku:, orders and draftOrders with
# tag: and customer_id:, customers with phone:. Neither orders nor draftOrders has a phone filter.
# Scopes: write_draft_orders, read_draft_orders, read_orders (last 60 days unless read_all_orders
# is granted), read_customers, read_products.
DRAFT_ORDER_CREATE = """
mutation draftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder { id name totalPriceSet { shopMoney { amount currencyCode } } }
    userErrors { field message }
  }
}"""

VARIANT_BY_SKU = """
query VariantBySku($q: String!) {
  productVariants(first: 5, query: $q) { nodes { id sku } }
}"""

SKU = re.compile(r"[A-Za-z0-9._-]{1,64}")
# Not checked against live docs today: DraftOrderLineItemInput.customAttributes takes a list of
# {key, value} (AttributeInput). Check it on shopify.dev before the first live printing order.
PRINT_NAME_KEY = "Name to print"


def whatsapp_tag(key):
    """The tag every agent-made order carries, so the WhatsApp number that placed it can find it."""
    return f"wa-{key}"


def _variant_id(sku):
    if not sku or not SKU.fullmatch(sku):
        raise StoreError("a line has no usable sku")
    nodes = _graphql(VARIANT_BY_SKU, {"q": f"sku:{sku}"})["productVariants"]["nodes"]
    ids = [n["id"] for n in nodes if n.get("sku") == sku]
    if len(ids) != 1:
        raise StoreError("the sku does not name exactly one variant")
    return ids[0]


def discount_of(draft):
    """The draft's discounts added up, a Decimal (0 when it has none)."""
    return sum((money(d["discount"]) for d in draft.get("discounts") or []), Decimal(0))


def draft_order_input(draft, chat_id, tags, variant_ids):
    """The DraftOrderInput for one confirmed draft. Risk reasons stay off the note, which a customer may see.
    The offers' discount goes on as the order's appliedDiscount, a fixed amount (not checked against live
    docs, 2026-11-04)."""
    if not draft.get("currency"):
        raise StoreError("the store data has no currency")
    out = _draft_input(draft, chat_id, tags, variant_ids)
    off = discount_of(draft)
    if off > 0:
        out["appliedDiscount"] = {"valueType": "FIXED_AMOUNT", "value": float(off), "amountWithCurrency": {
            "amount": str(off), "currencyCode": draft["currency"]},
            "title": ", ".join(d["what"] for d in draft["discounts"])[:255]}
    return out


def _draft_input(draft, chat_id, tags, variant_ids):
    return {
        "lineItems": [_line_input(i, variant_ids) for i in draft["items"]],
        "shippingLine": {"title": f"Delivery, {draft['area']}",
                         "priceWithCurrency": {"amount": draft["fee"], "currencyCode": draft["currency"]}},
        "shippingAddress": {"address1": draft["address"], "city": draft["governorate"], "countryCode": "EG",
                            "phone": "+" + draft["phone"], "firstName": draft["name"]},
        "phone": "+" + (draft["whatsapp"] or draft["phone"]),
        "note": "Placed on WhatsApp by the Sales agent.",
        "tags": tags,
        "customAttributes": [{"key": "chat_id", "value": chat_id}],
    }


def _line_input(line, variant_ids):
    """One DraftOrderLineItemInput. A printing line carries its name to print as a custom attribute."""
    out = {"variantId": variant_ids[line["sku"]], "quantity": line["quantity"]}
    if line.get("print_name"):
        out["customAttributes"] = [{"key": PRINT_NAME_KEY, "value": line["print_name"]}]
    return out


def _shopify_create(draft, chat_id, tags):
    ids = {sku: _variant_id(sku) for sku in dict.fromkeys(i["sku"] for i in draft["items"])}  # one lookup a sku
    data = _graphql(DRAFT_ORDER_CREATE, {"input": draft_order_input(draft, chat_id, tags, ids)})["draftOrderCreate"]
    if data.get("userErrors") or not data.get("draftOrder"):
        raise StoreError("Shopify refused the draft order")
    made = data["draftOrder"]
    out = {"order": made["name"], "store": "shopify"}
    store_total = ((made.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")
    if store_total is not None and money(store_total) != money(draft["total"]):
        out["store_total_differs"] = True  # taxes or a price change in the store; the team checks it
    return out


ORDER_FIELDS = """
      name createdAt cancelledAt displayFulfillmentStatus phone tags
      shippingAddress { phone city }
      customer { defaultPhoneNumber { phoneNumber } }
      totalPriceSet { shopMoney { amount } }
      lineItems(first: 20) { nodes { title variantTitle quantity } }"""

FIND_BY_PHONE = """
query FindByPhone($tag: String!, $customer: String!) {
  orders(first: 10, query: $tag, reverse: true) { nodes {%s } }
  draftOrders(first: 10, query: $tag, reverse: true) {
    nodes {
      name createdAt status phone tags
      shippingAddress { phone city }
      totalPriceSet { shopMoney { amount } }
      lineItems(first: 20) { nodes { title variantTitle quantity } }
    }
  }
  customers(first: 5, query: $customer) { nodes { id defaultPhoneNumber { phoneNumber } } }
}""" % ORDER_FIELDS

ORDERS_BY_CUSTOMER = """
query OrdersByCustomer($q: String!) {
  orders(first: 10, query: $q, reverse: true) { nodes {%s } }
}""" % ORDER_FIELDS

FULFILLMENT = {"FULFILLED": "shipped", "PARTIALLY_FULFILLED": "partly shipped", "ON_HOLD": "on hold",
               "REQUEST_DECLINED": "on hold"}


def _shopify_orders(key):
    """Orders and open draft orders for one phone. The searches only narrow; the match is exact, here.

    Agent-made orders carry the WhatsApp tag. Other orders come through the store customer with
    exactly this phone. Every order kept must carry the tag or this exact phone.
    """
    data = _graphql(FIND_BY_PHONE, {"tag": f"tag:{whatsapp_tag(key)}", "customer": f"phone:+{key}"})
    orders = list(data["orders"]["nodes"])
    for cust in data["customers"]["nodes"]:
        if phone_key((cust.get("defaultPhoneNumber") or {}).get("phoneNumber")) != key:
            continue
        cid = str(cust.get("id", "")).rsplit("/", 1)[-1]
        if cid.isdigit():
            orders += _graphql(ORDERS_BY_CUSTOMER, {"q": f"customer_id:{cid}"})["orders"]["nodes"]
    out = {}
    for o in orders:
        if _belongs(o, key):
            status = "cancelled" if o.get("cancelledAt") else FULFILLMENT.get(o.get("displayFulfillmentStatus"), "confirmed")
            out[o["name"]] = _shopify_order(o, status)
    for o in data["draftOrders"]["nodes"]:
        if o.get("status") != "COMPLETED" and _belongs(o, key):  # a completed draft shows as its order
            out[o["name"]] = _shopify_order(o, "received")
    return list(out.values())


def _belongs(o, key):
    phones = {o.get("phone"), (o.get("shippingAddress") or {}).get("phone"),
              ((o.get("customer") or {}).get("defaultPhoneNumber") or {}).get("phoneNumber")}
    return whatsapp_tag(key) in (o.get("tags") or []) or key in {phone_key(p) for p in phones}


def _shopify_order(o, status):
    total = ((o.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")
    items = [{"product": li.get("title"), "size": li.get("variantTitle"), "quantity": li.get("quantity")}
             for li in (o.get("lineItems") or {}).get("nodes", [])]
    created = datetime.fromisoformat(o["createdAt"].replace("Z", "+00:00")).timestamp()
    return {"order": o["name"], "status": status, "placed_at": created,
            "governorate": (o.get("shippingAddress") or {}).get("city") or "",
            "items": [{k: v for k, v in i.items() if v not in (None, "")} for i in items],
            "total": str(money(total)) if total is not None else None, "phone": "", "whatsapp": ""}
