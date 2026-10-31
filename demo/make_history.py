"""Writes the fake history in demo/history: WhatsApp exports, one Instagram download, a Shopify
orders export, a deliveries file in our own format, and the demo humanizer's pairs. The store
is Beyond the Limits: the latest drop of Nike and adidas football boots, each in tiers with
their own prices, and name printing with UV DTF (400 EGP, two stickers, one on each shoe).

    python3 -I demo/make_history.py [--out DIR]

Every name, phone, address and order is made up. Phones are +20 100 000 0xxx, names end in
"تجربة" or start with "Demo", the names given for printing too. The same run always writes the
same bytes, so the numbers in the docs and tests can be checked again (tests/test_importer.py
compares a fresh run with the files in demo/history). These files feed the importer
(reflection/importer.py) and its tests; they are not part of the demo flow.

The plan: 22 chats, 18 on WhatsApp (Android and iOS lines) and 4 on Instagram. Each asks
about a pair of boots; in chats 4, 9 and 16 a parent asks about boots for their son. In
4 chats the customer adds the name printing to the order: with their own name (11 and 21)
or a name they give, their child's (4 and 16). In 10 of them the team asks for a landmark
near the address; 8 of those 10 end delivered. In the other 12, 3 end delivered. Chat 3's
order comes 5 days after its last message, chat 7 never shows a phone, chat 20 types none,
so their orders, if any, join no chat; chat 5 has two orders. Under the Sales plug an order
decides a case and a delivery never does, so there every landmark chat ends good and 7 of
the other 12 do.
"""
import argparse
import csv
import datetime
import json
import random
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent / "history"
CAIRO = ZoneInfo("Africa/Cairo")
BASE = datetime.datetime(2026, 7, 5, 10, 0, tzinfo=CAIRO)
TEAM = "Beyond the Limits"
LANDMARK = {0, 2, 4, 6, 8, 10, 12, 14, 16, 18}
OUTCOME = {0: "delivered", 1: "delivered", 2: "delivered", 3: "late", 4: "delivered", 5: "two", 6: "refused",
           7: "delivered", 8: "delivered", 9: "refused", 10: "delivered", 11: "delivered", 12: "delivered",
           13: None, 14: "returned", 15: "returned", 16: "delivered", 17: None, 18: "delivered", 19: "refused",
           20: None, 21: "delivered"}
NAMED = {7: "منى تجربة", 11: "كريم تجربة"}           # WhatsApp chats whose sender is a name, not a number
IG_NAMES = {18: "سلمى تجربة", 19: "Demo Hany", 20: "Demo Nour", 21: "ياسمين تجربة"}

BOOTS = [  # (title, how the customer writes it, {tier: price in EGP}) from demo/catalogue.json
    ("Nike Mercurial Vapor 17", "Vapor 17", {"Elite": 16500, "Pro": 11000, "Academy": 7500}),
    ("Nike Phantom 6", "Phantom 6", {"Elite": 16500, "Pro": 11000, "Academy": 7500}),
    ("Nike Tiempo Maestro", "Tiempo Maestro", {"Elite": 15500, "Pro": 11000, "Academy": 7500}),
    ("Nike Mercurial Superfly 11", "Superfly 11", {"Elite": 20000, "Pro": 13500, "Academy": 9500}),
    ("Adidas F50 Messi El Ultimo Tango", "F50 Messi", {"Elite": 19500, "Pro": 11000, "League": 7500}),
]
FOR_A_SON = {4, 9, 16}                                # a parent buying boots for their son
WRITES_AS_A_WOMAN = {4, 7, 9, 16, 18, 21}
OWN_NAME = {11, 21}                                   # adds the printing with their own name
GIVEN_NAME = {4: "آدم تجربة", 16: "علي تجربة"}        # adds the printing with a name they give

ASK = ["السلام عليكم، الـ {c} لسه متاحة؟", "مساء الخير، عندكم الـ {c}؟", "لو سمحت الـ {c} بكام؟"]
SON_ASK = ["السلام عليكم، عايزة جزمة كورة لابني، الـ {c} متاحة؟", "مساء الخير، الـ {c} ينفع لابني؟",
           "لو سمحت الـ {c} بكام؟ عايزاها لابني"]
PRICE = "الـ {c} ب {price} جنيه والشحن 60 جنيه للقاهرة والجيزة و85 جنيه لباقي المحافظات"
SIZES = "المقاسات من 39 لحد 46"
PRINT_ASK = "ينفع تكتبوا اسم على الجزمة؟"
PRINT = "أيوه، بنطبع الاسم بالـ UV DTF ب 400 جنيه زيادة، استيكرين، واحد على كل فردة. الاسم اللي هيتكتب إيه؟"
PRINT_OK = "تمام، هنضيف الطباعة على الطلب"
LAND = "ممكن أقرب علامة مميزة للعنوان؟ عشان المندوب يوصل بسهولة"
ADDRESS_ASK = "ممكن حضرتك تبعتلنا العنوان بالتفصيل ورقم الموبايل؟"
CONFIRM = "تمام يا فندم، تم تسجيل الطلب وهيوصلك خلال 3 أيام"
THANKS = "شكرا لذوق حضرتك، نورتنا"
STORE_PHONE = "لأي استفسار كلمنا على 01000000999"
PAIRS = [
    (LAND, "ممكن حضرتك تقولنا أقرب علامة مميزة جنب العنوان؟ كده المندوب هيوصل أسرع."),
    (PRICE.format(c="Vapor 17 Elite", price=16500),
     "الـ Vapor 17 Elite بـ 16,500 جنيه، والشحن 60 جنيه في القاهرة والجيزة و85 جنيه في باقي المحافظات."),
    (SIZES, "المقاسات من 39 لـ 46. حضرتك مقاسك كام؟"),
    (PRINT, "أيوه، نقدر نطبع الاسم بالـ UV DTF بـ 400 جنيه زيادة، استيكرين، واحد على كل فردة. الاسم اللي نطبعه إيه؟"),
    (THANKS, "شكرا لحضرتك، ونتمنى الجزمة تعجبك."),
]
PRINTING = ("Beyond the Limits Name Printing", 400, 1)


def local(i):
    return f"0100000{i + 1:04d}"


def spaced(i):
    return f"+20 100 000 {i + 1:04d}"


def size(i):
    """The size chat i asks for: 39 to 41 for a son, the others 40 to 44."""
    return 39 + i % 3 if i in FOR_A_SON else 40 + i % 5


def pick(i, shift=0):
    """Chat i's boot: (title, how the customer writes it with the tier, tier, price). Elite or Pro by
    turns, the cheapest tier for a son; shift moves to the next boot in the list."""
    title, said, prices = BOOTS[(i + shift) % len(BOOTS)]
    tiers = list(prices)
    tier = tiers[-1] if i in FOR_A_SON else tiers[i % 2]
    return title, f"{said} {tier}", tier, prices[tier]


def boots(i, shift=0):
    """Chat i's boots as an order line: (Shopify line item name, price, quantity)."""
    title, _, tier, price = pick(i, shift)
    return (f"{title} - {tier} / {size(i)}", price, 1)


def script(i, rng):
    """[(minutes after the start, team?, text)] for chat i; text may hold a newline or a media mark."""
    first = NAMED.get(i, IG_NAMES.get(i, "")).split(" ")[0]
    greet = f"أهلا يا {first}، تحت أمرك" if first and first != "Demo" else "أهلا بحضرتك يا فندم، تحت أمرك"
    want = "عايزة" if i in WRITES_AS_A_WOMAN else "عايز"
    _, said, _, amount = pick(i)
    ask = rng.choice(SON_ASK if i in FOR_A_SON else ASK).format(c=said)
    price, sizes = PRICE.format(c=said, price=amount), SIZES
    wants = f"{want} مقاس {size(i)}" + (" لابني" if i in FOR_A_SON else "")
    lines = [(0, False, ask), (3, True, greet), (5, True, price), (9, False, wants),
             (12, True, sizes), (15, False, "<media>")]
    if i in OWN_NAME or i in GIVEN_NAME:
        name = f"اكتبوا اسمي {first}" if i in OWN_NAME else f"اكتبوا اسم ابني {GIVEN_NAME[i]}"
        lines += [(16, False, PRINT_ASK), (17, True, PRINT), (18, False, name), (19, True, PRINT_OK)]
    lines += [(20, True, ADDRESS_ASK), (31, False, "العنوان: 12 شارع التجربة\nمدينة نصر، القاهرة")]
    if i in (11, 18, 21):
        lines.append((33, False, f"ورقمي {local(i)}"))
    if i in LANDMARK:
        lines += [(36, True, LAND), (44, False, rng.choice(["جنب صيدلية النور", "قدام مدرسة التجربة"]))]
    if i == 19:
        lines.append((47, False, f"عملت اوردر #{1001 + i} من الموقع، ممكن تأكدوه؟"))
    if OUTCOME[i] is not None:
        lines += [(50, False, "تمام، أكدوا الطلب"), (52, True, CONFIRM)]
    lines += [(55, True, STORE_PHONE), (60, False, "تمام شكرا"), (62, True, THANKS)]
    return lines


def start(i, rng):
    return BASE + datetime.timedelta(days=3.5 * i, minutes=rng.randrange(0, 120))


def whatsapp(i, rng, out):
    t0 = start(i, rng)
    ios = i % 3 == 1
    who = NAMED.get(i) or (f"‪{spaced(i)}‬" if ios else spaced(i))
    name = NAMED.get(i) or spaced(i)
    lines = []
    if ios:
        lines.append(f"[{t0:%d/%m/%Y, %H:%M:%S}] {who}: ‎Messages and calls are end-to-end encrypted. "
                     "No one outside of this chat, not even WhatsApp, can read or listen to them.")
    else:
        lines.append(f"{t0:%d/%m/%Y, %H:%M} - Messages and calls are end-to-end encrypted. No one outside of this "
                     "chat, not even WhatsApp, can read or listen to them. Tap to learn more.")
    times = []
    for minutes, team, text in script(i, rng):
        t = t0 + datetime.timedelta(minutes=minutes, seconds=rng.randrange(0, 50))
        times.append((t, team))
        sender = TEAM if team else who
        if text == "<media>":
            text = "‎image omitted" if ios else "<Media omitted>"
        head = f"[{t:%d/%m/%Y, %H:%M:%S}] " if ios else f"{t:%d/%m/%Y, %H:%M} - "
        lines.append(f"{head}{sender}: {text}")
    sep = " - " if ios else " with "
    (out / "whatsapp" / f"WhatsApp Chat{sep}{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [t for t, team in times if not team]


def mojibake(s):
    return s.encode("utf-8").decode("latin-1")


def instagram(i, rng, out):
    t0 = start(i, rng)
    cust = IG_NAMES[i]
    msgs, times = [], []
    for minutes, team, text in script(i, rng):
        t = t0 + datetime.timedelta(minutes=minutes, seconds=rng.randrange(0, 50))
        m = {"sender_name": mojibake(TEAM if team else cust), "timestamp_ms": int(t.timestamp() * 1000)}
        if text == "<media>":
            m["photos"] = [{"uri": "your_instagram_activity/messages/photos/demo.jpg"}]
        else:
            m["content"] = mojibake(text)
        msgs.append(m)
        if not team:
            times.append(t)
    msgs.insert(3, {"sender_name": mojibake(cust), "timestamp_ms": msgs[2]["timestamp_ms"] + 1000,
                    "content": "Liked a message"})
    folder = f"demo_customer_{i}_{1000000000 + i}"
    doc = {"participants": [{"name": mojibake(cust)}, {"name": TEAM}], "messages": msgs[::-1],
           "title": mojibake(cust), "is_still_participant": True, "thread_path": f"inbox/{folder}"}
    where = out / "instagram" / "messages" / "inbox" / folder
    where.mkdir(parents=True, exist_ok=True)
    (where / "message_1.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return times


ORDER_COLUMNS = ["Name", "Financial Status", "Fulfillment Status", "Total", "Created at", "Lineitem quantity",
                 "Lineitem name", "Lineitem price", "Billing Name", "Billing Phone", "Shipping Name",
                 "Shipping Phone", "Phone", "Cancelled at"]


def order_rows(name, at, phone, form, items, rng, cancelled=False):
    phones = {"Phone": "", "Shipping Phone": "", "Billing Phone": ""}
    phones[("Phone", "Shipping Phone", "Phone", "Billing Phone")[form % 4]] = phone
    total = sum(p * q for _, p, q in items) + 60
    rows = []
    for n, (item, price, qty) in enumerate(items):
        row = dict.fromkeys(ORDER_COLUMNS, "")
        row.update({"Name": name, "Lineitem quantity": str(qty), "Lineitem name": item, "Lineitem price": f"{price}.00"})
        if n == 0:
            buyer = f"Demo Customer {name[1:]}"
            row.update({"Financial Status": "pending", "Fulfillment Status": "fulfilled", "Total": f"{total}.00",
                        "Created at": at.strftime("%Y-%m-%d %H:%M:%S %z"), "Billing Name": buyer,
                        "Shipping Name": buyer, "Cancelled at": "", **phones})
        rows.append(row)
    return rows


def write(out=OUT):
    rng = random.Random(29)
    out = Path(out)
    (out / "whatsapp").mkdir(parents=True, exist_ok=True)
    orders, deliveries = [], []
    for i in range(22):
        times = whatsapp(i, rng, out) if i < 18 else instagram(i, rng, out)
        result = OUTCOME[i]
        if result is None:
            continue
        last = max(times)
        forms = [local(i), "+20" + local(i)[1:], spaced(i), "0020" + local(i)[1:]]
        placed = [(f"#{1001 + i}", last + datetime.timedelta(hours=5 if result == "late" else 0, days=5 if result == "late" else 0,
                                                              minutes=rng.randrange(60, 1200)))]
        if i == 19:
            placed = [(f"#{1001 + i}", times[-3] - datetime.timedelta(minutes=30))]
        states = ["delivered" if result in ("late", "two") else result]
        lines = [[boots(i)] + ([PRINTING] if i in OWN_NAME or i in GIVEN_NAME else [])]
        if result == "two":  # a second pair, the next boot in the list, the day after
            placed.append(("#1030", last + datetime.timedelta(hours=26)))
            states.append("refused")
            lines.append([boots(i, 1)])
        for (name, at), state, picked in zip(placed, states, lines):
            orders += order_rows(name, at, forms[i % 4], i, picked, rng)
            day = (at + datetime.timedelta(days=2 + rng.randrange(4))).date()
            deliveries.append({"order": name, "state": state, "date": day.isoformat()})
    for n, (name, state) in enumerate((("#1040", "delivered"), ("#1041", "refused"))):
        at = BASE + datetime.timedelta(days=20 + 9 * n, hours=3)
        picked = [(f"{BOOTS[n][0]} - Pro / {(43, 41)[n]}", BOOTS[n][2]["Pro"], 1)]
        orders += order_rows(name, at, local(89 + n), n, picked, rng)
        deliveries.append({"order": name, "state": state, "date": (at + datetime.timedelta(days=3)).date().isoformat()})
    deliveries.append({"order": "#1999", "state": "delivered", "date": "2026-09-30"})
    deliveries.append({"order": "#1001", "state": "lost", "date": "2026-07-08"})
    with open(out / "orders.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ORDER_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(orders)
    with open(out / "deliveries.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order", "state", "date"], lineterminator="\n")
        w.writeheader()
        w.writerows(deliveries)
    pairs = {"about": "Demo pairs for the demo humanizer: a reply as the team wrote it, and the same reply in our "
                      "tone. Made up.", "pairs": [{"theirs": a, "ours": b} for a, b in PAIRS]}
    (out / "humanizer.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write the fake history files.")
    ap.add_argument("--out", default=str(OUT), help="the folder to write (default demo/history)")
    write(ap.parse_args().out)
