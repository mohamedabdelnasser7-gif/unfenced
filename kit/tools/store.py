"""store: products, prices, tiers, sizes and stock.

Reads the Shopify Admin GraphQL API when SHOPIFY_STORE and SHOPIFY_TOKEN are set,
else demo/catalogue.json. Answers only with fields present in the data: a field the
data does not have is left out, never filled in. Each product option of a variant goes out under
its own lowercase name: a boot's variant has a tier ("Elite") and a size ("42").

Stock goes out as a level, never a count (Mohamed's call, 28 Oct): "in stock",
"few left" (under FEW_LEFT) or "out". A variant whose stock the store does not track
(inventoryItem tracked false) has no stock field at all.

Each product's image link goes out as "image" (2026-10-31): Shopify's featured media image
url live; in the demo store a stand-in link on an .example host (demo_images in
demo/catalogue.json, kept out of the seed mutation's variables), never a real brand's image.
Only an https link with no space in it goes out. The send check lets a reply carry a link only
when the store tool gave it in that chat (sales/loop.py store_links).
"""
import contextvars
import html
import json
import re
import time
import urllib.request
from pathlib import Path

from kit import env, net
from kit.send_check import amount

ROOT = Path(__file__).resolve().parents[2]
DEMO_CATALOGUE = ROOT / "demo" / "catalogue.json"
DEMO_DELIVERY = ROOT / "demo" / "delivery.json"
# Not checked against live docs today: set SHOPIFY_API_VERSION to the current one from shopify.dev.
SHOPIFY_DEFAULT_VERSION = "2026-10"
CACHE_SECONDS = 300
FEW_LEFT = 5

NAME = "store"
DEFINITION = {"type": "function", "function": {
    "name": NAME,
    "description": (
        "Look up the store's products: names, prices, tiers, sizes, stock level (in stock, few left or out) when the store tracks it, "
        "and each product's image link when it has one. "
        "Search in English words "
        "like 'phantom' or 'name printing'. Leave query empty to get every product."),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Short search words in English, or empty."}},
        "additionalProperties": False,
    },
}}

_cache = {"at": 0.0, "items": None}
# A Quick start agent's sample products (kit/sample.py store_items), set by kit/turn.py for one turn of an
# agent that has them. Read only when no Shopify keys are set: real keys always win.
SAMPLE = contextvars.ContextVar("store_sample", default=None)


def check(args, ctx):
    extra = set(args) - {"query"}
    if extra:
        return False, f"Unknown arguments: {', '.join(sorted(extra))}. Only query is allowed."
    q = args.get("query", "")
    if not isinstance(q, str) or len(q) > 100:
        return False, "query must be a short string, 100 characters at most."
    return True, ""


def run(args, ctx):
    items = catalogue()
    q = (args.get("query") or "").lower()
    words = [w for w in re.findall(r"\w+", q) if len(w) > 1]
    if not words:
        return {"ok": True, "items": items}
    hits = [i for i in items if all(w.rstrip("s") in _haystack(i) for w in words)]
    hits = hits or [i for i in items if any(w.rstrip("s") in _haystack(i) for w in words)]
    if not hits:
        return {"ok": True, "items": items, "note": "Nothing matched the search, so this is every product."}
    return {"ok": True, "items": hits}


def _haystack(item):
    return json.dumps(item, ensure_ascii=False).lower()


# data

def catalogue(fresh=False):
    """Every product as a list of plain dicts, cached for a few minutes. With no Shopify keys, an agent's
    sample products (SAMPLE) when this turn has them."""
    real = bool(env.get("SHOPIFY_STORE") and env.get("SHOPIFY_TOKEN"))
    sample = None if real else SAMPLE.get()
    if sample is not None:
        return sample
    if not fresh and _cache["items"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["items"]
    if real:
        items = _from_shopify()
    else:
        items = _from_demo(DEMO_CATALOGUE)
    _cache.update(at=time.time(), items=items)
    return items


def stock_level(quantity):
    """The stock level the model may see: "in stock", "few left" or "out". Never the count."""
    if quantity <= 0:
        return "out"
    return "few left" if quantity < FEW_LEFT else "in stock"


def _tracked(variant):
    """False only when the store says it does not track the variant's stock (inventoryItem
    tracked false). Then no level is read: an untracked item has a quantity of 0, and reading
    it would tell the customer "out" for an item the store sells."""
    return (variant.get("inventoryItem") or {}).get("tracked") is not False


def _put(d, key, value):
    if value is not None and value != "" and value != []:
        d[key] = value


def _clean(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


IMAGE_LINK = re.compile(r"https://[^\s<>\"']+")


def _image(url):
    """The image link when it is a plain https link with no space or quote in it, else None."""
    return url if isinstance(url, str) and IMAGE_LINK.fullmatch(url) else None


def _from_demo(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    products = data.get("variables", data)
    images = data.get("demo_images") if isinstance(data.get("demo_images"), dict) else {}
    items = []
    for key in sorted(products, key=lambda k: int(re.sub(r"\D", "", k) or 0)):
        p = products[key]
        item = {}
        _put(item, "title", p.get("title"))
        _put(item, "type", p.get("productType"))
        _put(item, "description", _clean(p.get("descriptionHtml")) or None)
        _put(item, "image", _image(images.get(key)))
        variants = []
        for v in p.get("variants", []):
            var = {}
            for o in v.get("optionValues", []):
                _put(var, (o.get("optionName") or "size").strip().casefold(), o.get("name"))
            _put(var, "price", v.get("price"))
            _put(var, "sku", v.get("sku"))
            qty = [q["quantity"] for q in v.get("inventoryQuantities", []) if q.get("name") == "available"]
            if qty and _tracked(v):
                var["stock"] = stock_level(sum(qty))
            variants.append(var)
        _put(item, "variants", variants)
        items.append(item)
    return items


SHOPIFY_QUERY = """
query Products($cursor: String) {
  shop { currencyCode }
  products(first: 50, after: $cursor, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      title productType description
      featuredMedia { preview { image { url } } }
      variants(first: 50) {
        nodes { title price sku inventoryQuantity inventoryItem { tracked } selectedOptions { name value } }
      }
    }
  }
}"""


def _from_shopify():
    shop = env.get("SHOPIFY_STORE").removeprefix("https://").split("/")[0]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", shop):
        raise ValueError("SHOPIFY_STORE must look like name.myshopify.com")
    version = env.get("SHOPIFY_API_VERSION", SHOPIFY_DEFAULT_VERSION)
    url = f"https://{shop}/admin/api/{version}/graphql.json"
    items, cursor = [], None
    for _ in range(20):
        body = json.dumps({"query": SHOPIFY_QUERY, "variables": {"cursor": cursor}}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "X-Shopify-Access-Token": env.get("SHOPIFY_TOKEN"), "Content-Type": "application/json"})
        with net.open_once(req, timeout=20) as r:   # no redirect: the token never follows one
            out = json.loads(r.read().decode("utf-8"))
        if out.get("errors"):
            raise RuntimeError("Shopify answered with errors")
        data = out["data"]
        currency = (data.get("shop") or {}).get("currencyCode")
        for p in data["products"]["nodes"]:
            item = {}
            _put(item, "title", p.get("title"))
            _put(item, "type", p.get("productType"))
            _put(item, "description", p.get("description"))
            preview = ((p.get("featuredMedia") or {}).get("preview") or {}).get("image") or {}
            _put(item, "image", _image(preview.get("url")))
            variants = []
            for v in p["variants"]["nodes"]:
                var = {}
                options = [o for o in v.get("selectedOptions") or [] if o.get("name") != "Title"]
                for o in options:
                    _put(var, (o.get("name") or "size").strip().casefold(), o.get("value"))
                if not options and v.get("title") != "Default Title":
                    _put(var, "size", v.get("title"))
                _put(var, "price", v.get("price"))
                _put(var, "currency", currency)
                _put(var, "sku", v.get("sku"))
                if v.get("inventoryQuantity") is not None and _tracked(v):
                    var["stock"] = stock_level(v["inventoryQuantity"])
                variants.append(var)
            _put(item, "variants", variants)
            items.append(item)
        page = data["products"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    return items


def delivery():
    """Delivery fees and days. Demo data from the 27 Oct language test until the delivery tool lands."""
    return json.loads(DEMO_DELIVERY.read_text(encoding="utf-8"))


def price_points():
    """Every price and fee in the store and delivery data, for the send check.

    Kept as written: 16500.00 is 16500, and 16500.50 stays 16500.50, never cut to 16500.
    """
    values = [v["price"] for item in catalogue() for v in item.get("variants", []) if "price" in v]
    values += [zone["fee"] for zone in delivery().get("zones", []) if "fee" in zone]
    return {a for a in map(amount, values) if a is not None}


def vocabulary():
    """Lowercase words in product names, tiers and sizes, allowed in Latin letters in an Arabic reply."""
    words = set()
    for item in catalogue():
        words |= set(re.findall(r"[a-z]+", item.get("title", "").lower()))
        for v in item.get("variants", []):
            words |= set(re.findall(r"[a-z]+", (v.get("tier", "") + " " + v.get("size", "")).lower()))
    return frozenset(words)


def titles():
    """Every product title ("Nike Phantom 6"), so the send check reads a model number as a model."""
    return frozenset(i["title"] for i in catalogue() if isinstance(i.get("title"), str))


def size_strings():
    """Every size string in the catalogue ("43"), so the send check never reads a size as an amount."""
    return frozenset(v["size"] for item in catalogue() for v in item.get("variants", []) if v.get("size"))


def extras():
    """The products sold on top of any other product: every variant has neither a tier nor a size
    (the name printing, one price whatever boot it goes on). The Arena fact check counts their
    prices whatever product a reply names."""
    return [i for i in catalogue() if i.get("variants")
            and not any(v.get("tier") or v.get("size") for v in i["variants"])]


def tiers():
    """Every tier name in the catalogue ("Elite"), so a reply that names one is checked against its prices."""
    return frozenset(v["tier"] for item in catalogue() for v in item.get("variants", []) if v.get("tier"))
