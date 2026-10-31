"""Writes demo/crowd.jsonl: a crowd of simulated customer chats for the demo, most in Egyptian
Arabic, some in Franco and English, from templates, the demo catalogue and the demo delivery
file (read through kit/tools/store, so the products, sizes, prices and stock are the demo
store's own: Beyond the Limits football boots and name printing, two stickers, one on each shoe).

    python3 -I demo/make_crowd.py [--out FILE] [--count N] [--seed N]

Every chat is labelled "simulated": true. Names end in "تجربة" or start with "Demo"; phones run
+20 100 000 0500 upward, past the exam's numbers. The same count and seed always write the same
bytes (tests/test_crowd.py compares a fresh run with demo/crowd.jsonl).

One line a chat: {"id", "simulated", "channel", "name", "phone", "language", "kind", "stage",
"product", "turns"}. turns take the exam's form (sales/exam/situations.json): the customer's
lines and the team's replies in order, the last one the customer's, so a chat runs through the
Sales agent's reply path the way an exam situation does (reflection/exam.answer). The score
(sim/score.py) does not read it; it reads its own scenarios.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.tools import store  # noqa: E402

OUT = Path(__file__).resolve().parent / "crowd.jsonl"
COUNT = 300
SEED = 30
FIRST_PHONE = 500
WEIGHT = {"ar": 4, "fr": 1, "en": 1}  # most chats in Egyptian Arabic
NAMES_AR = ["كريم", "منى", "سلمى", "عمر", "ياسمين", "حسن", "نور", "مريم", "يوسف", "هالة", "طارق", "دينا"]
NAMES_EN = ["Hany", "Nour", "Omar", "Laila", "Ziad", "Farida"]
# (kind, stage, languages): what the customer asks; the templates below give the words
KINDS = [("price", "asking", "ar fr en"), ("size", "asking", "ar fr en"), ("stock", "asking", "ar fr"),
         ("delivery", "asking", "ar fr en"), ("order", "ordering", "ar fr"), ("chase", "my_order", "ar fr en"),
         ("exchange", "my_order", "ar en"), ("bot", "asking", "ar fr en"), ("complaint", "with_person", "ar"),
         ("pay", "asking", "ar en"), ("printing", "asking", "ar fr en")]
BOOTS_ONLY = {"size", "stock", "exchange", "order"}   # kinds about a pair of boots, never the printing alone
ASK = {
    "price": {"ar": ["{p} بكام؟", "لو سمحت سعر {p} كام؟", "عايز أعرف {p} بكام"],
              "fr": ["{p} b kam?", "law sama7t {p} se3ro kam?"], "en": ["What is the price of {p}?", "Price of {p}?"]},
    "size": {"ar": ["فيه {p} مقاس {s}؟", "عايز {p} مقاس {s}، متاح؟"], "fr": ["fe {p} size {s}?"],
             "en": ["Do you have {p} in size {s}?"]},
    "stock": {"ar": ["لسه فيه {p}؟", "عندكم {p} دلوقتي؟"], "fr": ["lessa fe {p}?"]},
    "delivery": {"ar": ["الشحن ل{g} بياخد كام يوم؟", "التوصيل ل{g} امتى؟"], "fr": ["el sha7n l {g} kam yom?"],
                 "en": ["How long is delivery to {g}?"]},
    "order": {"ar": ["تمام اكد الطلب", "ايوه تمام كده"], "fr": ["tamam akked el order", "aywa tamam"]},
    "chase": {"ar": ["فين الاوردر بتاعي؟", "طلبي اتأخر، فيه أخبار؟"], "fr": ["el order bta3y fen?"],
              "en": ["Where is my order?", "My order is late, any news?"]},
    "exchange": {"ar": ["المقاس طلع صغير، ينفع أبدله؟", "عايز أرجع {p}"],
                 "en": ["Can I exchange {p}? The size is too small."]},
    "bot": {"ar": ["انت بوت؟", "انا بكلم حد ولا بوت؟"], "fr": ["enta bot?"], "en": ["Am I talking to a bot?"]},
    "complaint": {"ar": ["طلبت {p} والطلب وصل غلط ومحدش بيرد", "المندوب اتكلم معايا وحش جدا"]},
    "pay": {"ar": ["ينفع الدفع عند الاستلام؟", "الدفع ازاي؟"], "en": ["Can I pay cash on delivery?"]},
    "printing": {"ar": ["ينفع تكتبوا اسمي على الجزمة؟", "عايز اسم ابني مكتوب على الجزمة، بكام؟"],
                 "fr": ["momken tektebo esmy 3al gazma?"], "en": ["Can you print my name on the boots?"]},
}
GOVS = {"ar": ["القاهرة", "الجيزة", "الإسكندرية", "المنصورة", "أسيوط"],
        "fr": ["el qahera", "giza", "alex", "mansoura"], "en": ["Cairo", "Giza", "Alexandria", "Mansoura"]}


def products():
    """The demo store's items as the crowd names them: one entry a boot and tier (the title without
    the maker's word, then the tier: "the Mercurial Vapor 17 Elite"), the name in each language,
    sizes, price. The printing is one entry with no sizes."""
    out = []
    for item in store._from_demo(store.DEMO_CATALOGUE):
        title = item["title"]
        variants = item["variants"]
        if item.get("type") == "Printing":
            out.append({"title": title, "name": {"ar": "طباعة الاسم", "fr": "teba3et el esm", "en": "the name printing"},
                        "sizes": [], "in_stock": [], "price": variants[0]["price"]})
            continue
        model = title.split(" ", 1)[1] if " " in title else title
        for tier in dict.fromkeys(v.get("tier") for v in variants):
            rows = [v for v in variants if v.get("tier") == tier]
            name = f"{model} {tier}" if tier else model
            sizes = list(dict.fromkeys(v["size"] for v in rows if v.get("size")))
            out.append({"title": title, "name": {"ar": f"الـ {name}", "fr": f"el {name}", "en": f"the {name}"},
                        "sizes": sizes,
                        "in_stock": [z for z in sizes
                                     if any(v.get("size") == z and v.get("stock") != "out" for v in rows)],
                        "price": rows[0]["price"]})
    return out


def team_reply(p, lang):
    """The team's earlier reply in a chat: the product's price, and its sizes not sold out, from
    the demo data. The printing has no sizes: its reply says it is two stickers, one on each shoe."""
    if not p["sizes"]:
        what = {"ar": "استيكرين، واحد على كل فردة", "fr": "2 sticker, wa7ed 3ala kol farda",
                "en": "two stickers, one on each shoe"}[lang]
    else:
        what = {"ar": "المقاسات " + " و ".join(p["in_stock"]), "fr": "el sizes " + ", ".join(p["in_stock"]),
                "en": "sizes " + ", ".join(p["in_stock"])}[lang]
    if lang == "ar":
        return f"{p['name']['ar']} بـ {p['price']} جنيه، {what}."
    if lang == "fr":
        return f"{p['name']['fr']} b {p['price']} geneh, {what}."
    verb = "are" if p["sizes"] else "is"
    return f"{p['name']['en'][0].upper()}{p['name']['en'][1:]} {verb} {p['price']} EGP, {what}."


def chat(n, rng, items):
    kind, stage, langs = KINDS[rng.randrange(len(KINDS))]
    langs = langs.split()
    lang = rng.choices(langs, weights=[WEIGHT[x] for x in langs])[0]
    if kind == "printing":
        pool = [i for i in items if not i["sizes"]]
    elif kind in BOOTS_ONLY:
        pool = [i for i in items if len(i["sizes"]) > 1]
    else:
        pool = items
    p = pool[rng.randrange(len(pool))]
    s = rng.choice(p["sizes"]) if p["sizes"] else ""
    template, g = rng.choice(ASK[kind][lang]), rng.choice(GOVS[lang])
    if lang == "ar" and g.startswith("ال"):
        g = g[1:]  # after ل: ل plus القاهرة is written للقاهرة
    words = template.format(p=p["name"][lang], s=s, g=g)
    turns = []
    if kind in ("order", "exchange", "complaint") or rng.random() < 0.3:  # an earlier exchange before the last line
        opener = {"ar": f"عايز {p['name']['ar']}", "fr": f"3ayez {p['name']['fr']}", "en": f"I want {p['name']['en']}"}
        turns += [{"customer": opener[lang]}, {"agent": team_reply(p, lang)}]
    turns.append({"customer": words})
    phone = FIRST_PHONE + n
    name = (f"Demo {rng.choice(NAMES_EN)}" if lang == "en" else f"{rng.choice(NAMES_AR)} تجربة")
    return {"id": f"crowd-{n + 1:03d}", "simulated": True, "channel": rng.choice(["whatsapp", "instagram"]),
            "name": name, "phone": f"+20 100 000 {phone:04d}", "language": {"ar": "arabic", "fr": "franco",
                                                                           "en": "english"}[lang],
            "kind": kind, "stage": stage, "product": p["title"], "turns": turns}


def crowd(count=COUNT, seed=SEED):
    """The crowd's chats as dicts, the same for the same count and seed."""
    if not 1 <= count <= 1000 - FIRST_PHONE:
        raise ValueError(f"count is 1 to {1000 - FIRST_PHONE}: the phones stay +20 100 000 0xxx")
    rng = random.Random(seed)
    items = products()
    return [chat(n, rng, items) for n in range(count)]


def write(out=OUT, count=COUNT, seed=SEED):
    out = Path(out)
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in crowd(count, seed)), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write the demo's crowd of simulated chats.")
    ap.add_argument("--out", default=str(OUT), help="the file to write (default demo/crowd.jsonl)")
    ap.add_argument("--count", type=int, default=COUNT, help=f"how many chats (default {COUNT})")
    ap.add_argument("--seed", type=int, default=SEED, help=f"the seed (default {SEED})")
    a = ap.parse_args()
    print(f"written: {write(a.out, a.count, a.seed)}")
