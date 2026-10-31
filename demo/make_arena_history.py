"""Writes a made-up chat export for the Arena personas (new, 2026-10-30): WhatsApp exports
(Android and iOS lines) and an Instagram download (JSON, its text written as mojibake), for
the store Beyond the Limits. For tests and the demo cards in demo/personas.

    python3 -I demo/make_arena_history.py --out DIR

--out is needed and must be outside this repo: reflection/history.py reads nothing in the repo
but demo/history, and demo/history is the importer's own fake history (tests/test_importer.py
compares it byte for byte), so this one never goes there.

Every name, phone, address and order is made up. Phones are +20 100 000 1xxx; names end in
"تجربة" or start with "Demo". The same run always writes the same bytes.

The plan: 33 chats, one every 3 days, so only the last is still open when the import ends.
  won (12)      after the store gives a price, the customer confirms (أكدلي, هاخدهم, اطلبيها,
                akkedly, I'll take it) or sends an address; one has a voice note before the
                address, one types a name and a phone before it; two add the name printing
                (the customer's name printed with UV DTF, 400 EGP for two stickers, one on each shoe), one in Arabic
                and one in English
  lost (16)     the customer goes quiet after the store's answer with a price in the chat:
                size 2, price 4 (one with no budget), cash on delivery 2, trust 2, delivery 2,
                just browsing 3, other 1 (offered the name printing, then quiet)
  unclear (5)   a cancel after the yes, a last question not answered, a voice note last, no
                store reply, and the last chat, still open
"""
import argparse
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I, as arena/personas.py is
    sys.path.insert(0, str(ROOT))

from reflection import history as hist  # noqa: E402

CAIRO = ZoneInfo("Africa/Cairo")
BASE = datetime.datetime(2026, 8, 2, 11, 0, tzinfo=CAIRO)
TEAM = "Beyond the Limits"
VOICE, PHOTO = "<voice>", "<photo>"

HELLO = "أهلا بيك في Beyond the Limits، تحت أمرك"
PRICE = "الـ Phantom 6 Elite ب 16500 جنيه والشحن 60 جنيه"
SIZES = "متاح من مقاس 39 لحد 46"
ADDRESS_ASK = "ابعتلي العنوان بالتفصيل ورقم الموبايل"
PLACED = "تمام، تم تسجيل الطلب وهيوصلك خلال 3 أيام"
COD = "الدفع عند الاستلام متاح لكل المحافظات"
ORIGINAL = "كل منتجاتنا أصلية ومعاها ضمان"
DELIVERY = "التوصيل من 2 ل 4 أيام عمل"
EN_PRICE = "The Phantom 6 Elite is 16500 EGP, shipping is 60 EGP"
EN_PLACED = "Done, your order is confirmed"
PRINTING = "أيوة، بنطبع اسمك بالـ UV DTF ب 400 جنيه، استيكرين، واحد على كل فردة"
EN_PRINTING = "Yes, we print your name with UV DTF for 400 EGP, two stickers, one on each shoe. The Vapor 17 Elite is 16500 EGP"


def phone(n):
    return f"+20 100 000 {1000 + n:04d}"


# (name, where, [(minutes, "c" or "s", text)]); where: android, ios or ig. A name of None: the
# sender is the chat's phone number.
CHATS = [
    # ---- won
    ("علي تجربة", "android", [(0, "c", "السلام عليكم، الجزمة دي متاحة؟"), (4, "s", HELLO), (5, "s", PRICE),
                              (9, "c", "مقاس 43 متاح؟"), (12, "s", SIZES), (15, "c", "تمام أكدلي مقاس 43"),
                              (18, "s", PLACED)]),
    ("Demo Karim", "ios", [(0, "c", "Hi, are these boots true to size?"), (3, "s", "Hello, welcome to Beyond the Limits"),
                           (6, "c", "I usually wear 42, which size should I get?"),
                           (9, "s", "Take 42, they fit true to size. The pair is 16500 EGP"),
                           (12, "c", "Great, I'll take it"),
                           (14, "s", EN_PLACED)]),
    (None, "android", [(0, "c", "عايز الجزمة دي مقاس 41"), (3, "s", PRICE), (6, "c", VOICE), (9, "s", "المقاس 41 متاح"),
                       (14, "c", "العنوان: 12 شارع التجربة، مدينة نصر"), (17, "s", PLACED)]),
    ("منى تجربة", "ios", [(0, "c", "بكام الجزمة دي؟"), (2, "s", PRICE), (5, "c", "غالية شوية، مفيش خصم؟"),
                         (8, "s", "لو أخدت اتنين في خصم 10%"), (12, "c", "خلاص هاخدهم الاتنين"), (15, "s", PLACED)]),
    ("Demo Salma", "ig", [(0, "c", "How much is the Phantom 6 Elite?"), (3, "s", EN_PRICE),
                          (6, "c", "That's a bit expensive, any discount?"), (9, "s", "10% off if you take two pairs"),
                          (13, "c", "OK I'll take them, two pairs"), (15, "s", EN_PLACED)]),
    ("كريم تجربة", "android", [(0, "c", "ينفع الدفع عند الاستلام؟"), (3, "s", COD + "، والجزمة ب 16500 جنيه"),
                               (6, "c", "تمام كده، أكدلي الأوردر"), (9, "s", PLACED)]),
    ("Demo Youssef", "ios", [(0, "c", "Can I pay cash on delivery?"),
                             (3, "s", "Yes, cash on delivery is available everywhere, the boots are 16500 EGP"),
                             (7, "c", "My address is 7 Test Street, Nasr City"), (10, "s", EN_PLACED)]),
    ("سلمى تجربة", "ig", [(0, "c", "الجزمة دي أصلية ولا كوبي؟"), (3, "s", ORIGINAL),
                          (6, "c", "طيب لو طلعت مش أصلية أرجعها؟"), (9, "s", "أكيد، ترجعها خلال 14 يوم، والسعر 16500 جنيه"),
                          (12, "c", "تمام اطلبيها"), (14, "s", PLACED)]),
    ("Demo Hazem", "android", [(0, "c", "el gazma di mawgooda?"), (2, "s", "aywa mawgooda, b 16500 geneh"),
                               (5, "c", "emta hywsal law talabt el naharda?"), (8, "s", "men 2 l 4 ayam"),
                               (11, "c", "tamam akkedly"), (13, "s", "tamam, el order etsagel")]),
    ("Demo Tarek", "ios", [(0, "c", "عايز الـ Phantom 6 Elite مقاس 44"), (3, "s", PRICE),
                           (6, "c", f"تمام، اسمي طارق تجربة ورقمي 0100000{1009:04d}"), (9, "s", ADDRESS_ASK),
                           (14, "c", "عمارة 5 شارع التجربة، المعادي جنب صيدلية النور"), (17, "s", PLACED)]),
    # ---- lost
    (None, "android", [(0, "c", "الجزمة دي فيها مقاس 47؟"), (3, "s", "للأسف آخر مقاس عندنا 46"),
                       (6, "c", "طب مقاس 46 هيبقى ضيق عليا؟"),
                       (9, "s", "الموديل ده واسع شوية، 46 هيكون مناسب، وسعره 16500 جنيه")]),
    ("Demo Mostafa", "ig", [(0, "c", "el ma2as bta3 el gazma di mazboot?"), (3, "s", "aywa el ma2as mazboot"),
                            (6, "c", "ana 42.5, a5od 42 wala 43?"), (9, "s", "5od 43 a7san, w el se3r 16500 geneh")]),
    ("أحمد تجربة", "ios", [(0, "c", "بكام دي؟"), (2, "s", PRICE), (5, "c", "غالية أوي، في أرخص؟"),
                          (8, "s", "عندنا الـ Academy ب 7500 جنيه")]),
    ("Demo Sherif", "android", [(0, "c", "bkam el gazma di?"), (2, "s", "el gazma b 16500 geneh w el sha7n 60"),
                                (5, "c", "8aly awy, mafeesh discount?"), (8, "s", "el discount 3ala el 2 bas")]),
    ("Demo Laila", "ios", [(0, "c", "Hello, what's the price of the Phantom 6 Elite?"), (3, "s", EN_PRICE),
                           (6, "c", "Too expensive for me, is there a cheaper pair?"), (9, "s", "Our cheapest pair is the Academy at 7500 EGP")]),
    (None, "android", [(0, "c", "الجزمة دي بكام؟"), (2, "s", PRICE), (5, "c", "مفيش فلوس دلوقتي، السعر عالي عليا"),
                       (8, "s", "ممكن تقسطها على 3 شهور")]),
    ("Demo Rana", "ios", [(0, "c", "الدفع كاش عند الاستلام ولا لازم تحويل؟"), (3, "s", "الدفع مقدم بس للطلبات برا القاهرة"),
                          (6, "c", "أنا برا القاهرة ومش هحول قبل الاستلام"),
                          (9, "s", "للأسف الدفع مقدم في الحالة دي، والجزمة ب 16500 جنيه")]),
    ("هبة تجربة", "ig", [(0, "c", "ينفع cash on delivery؟"), (3, "s", "متاح الدفع عند الاستلام بزيادة 20 جنيه"),
                         (6, "c", "ليه زيادة على الدفع عند الاستلام؟"), (9, "s", "دي رسوم شركة الشحن")]),
    ("Demo Nader", "android", [(0, "c", "دي أصلي ولا تقليد؟"), (3, "s", ORIGINAL), (6, "c", "إيه اللي يضمنلي إنها أصلي؟"),
                               (9, "s", "تقدر تشوف ريفيوهات العملاء على الصفحة، والسعر 16500 جنيه")]),
    ("Demo Farah", "ios", [(0, "c", "Are these original or copy?"),
                           (3, "s", "All our boots are original with a warranty, this pair is 16500 EGP"),
                           (6, "c", "Can you send a photo of the box and the code?"), (9, "s", PHOTO), (10, "s", "Here it is")]),
    ("سارة تجربة", "android", [(0, "c", "لو طلبت النهاردة هيوصل امتى؟"), (3, "s", DELIVERY),
                               (6, "c", "محتاجها قبل الخميس، هتوصل؟"), (9, "s", "مقدرش أضمن قبل الخميس، والشحن 60 جنيه")]),
    ("Demo Adam", "ios", [(0, "c", "How long does delivery take to Alexandria?"),
                          (3, "s", "2 to 4 working days, shipping is 60 EGP"),
                          (6, "c", "I need them by Friday for a match, or email me at demo.adam@example.com"),
                          (9, "s", "We can't promise Friday, sorry")]),
    (None, "android", [(0, "c", "بكام الطقم ده؟"), (2, "s", "الطقم ب 1200 جنيه"), (5, "c", "تمام شكرا، أنا بس بتفرج دلوقتي"),
                       (8, "s", "تحت أمرك في أي وقت")]),
    ("Demo Mariam", "ig", [(0, "c", "Hi! just looking at the new collection"),
                           (3, "s", "Welcome, the new drop starts at 7500 EGP, tell me if you need help"),
                           (6, "c", "Sure, my friend @demo.friend sent me your page"), (9, "s", "Anytime")]),
    ("نور تجربة", "ig", [(0, "c", "عندكم جزم أطفال؟"), (3, "s", "مش عندنا مقاسات أطفال، أصغر مقاس 39، والـ Academy من 7500 جنيه"),
                         (6, "c", "حلو، بس بسأل بس دلوقتي"),
                         (9, "s", "تمام، نورتنا")]),
    ("Demo Hossam", "android", [(0, "c", "ممكن تطبعوا اسم على الجزمة؟"),
                                (3, "s", PRINTING + "، والجزمة ب 16500 جنيه"),
                                (6, "c", "حلو، شفت شغل زي ده على example.com/print، هفكر وأرجعلك"),
                                (9, "s", "تحت أمرك في أي وقت")]),
    # ---- unclear
    ("Demo Omar", "ios", [(0, "c", "دي أصلي؟"), (3, "s", ORIGINAL + "، والسعر 16500 جنيه"), (6, "c", "تمام اطلبهالي"),
                          (9, "s", PLACED),
                          (60, "c", "معلش ألغي الطلب رقم 1027"), (65, "s", "تم الإلغاء")]),
    ("رامي تجربة", "android", [(0, "c", "الشحن لأسوان بياخد كام يوم؟"), (3, "s", DELIVERY), (6, "c", "طب ممكن يوصل يوم السبت؟")]),
    ("Demo Ali", "ig", [(0, "c", "عايز جزمة مقاس 42"), (3, "s", PRICE), (6, "c", VOICE), (9, "s", "ثواني وأرد عليك")]),
    (None, "android", [(0, "c", "السلام عليكم"), (1, "c", "الجزمة دي متاحة مقاس 40؟")]),
    # ---- won, with the name printing (before the last chat, so it stays the only open one)
    ("مروان تجربة", "android", [(0, "c", "بتطبعوا أسامي على الجزم؟"), (3, "s", PRINTING + "، والجزمة ب 16500 جنيه"),
                                (6, "c", "حلو، عايز الـ Vapor 17 Elite مقاس 43 واكتبلي اسمي مروان"),
                                (9, "s", "الجزمة والطباعة 16900 جنيه والشحن 60 جنيه"), (12, "c", "تمام أكدلي"),
                                (15, "s", PLACED)]),
    ("Demo Hana", "ios", [(0, "c", "Hi, can you print a name on the boots?"), (3, "s", EN_PRINTING),
                          (6, "c", "Nice, the Vapor 17 Elite in 42 with my name on it"),
                          (9, "s", "The boots and the printing are 16900 EGP, shipping is 60 EGP"),
                          (12, "c", "Great, I'll take it"), (14, "s", EN_PLACED)]),
    ("Demo Nada", "ios", [(0, "c", "What sizes do you have for the Tiempo Maestro?"), (3, "s", "We have sizes 39 to 46"),
                          (6, "c", "Do they run small?"), (9, "s", "No, they fit true to size")]),
]


def start(i):
    return BASE + datetime.timedelta(days=3 * i, minutes=17 * (i % 5))


def whatsapp(i, name, ios, lines, out):
    t0 = start(i)
    num = phone(i)
    who = name or (f"\u202a{num}\u202c" if ios else num)
    rows = []
    if ios:
        rows.append(f"[{t0:%d/%m/%Y, %H:%M:%S}] {who}: \u200eMessages and calls are end-to-end encrypted. "
                    "No one outside of this chat, not even WhatsApp, can read or listen to them.")
    else:
        rows.append(f"{t0:%d/%m/%Y, %H:%M} - Messages and calls are end-to-end encrypted. No one outside of this "
                    "chat, not even WhatsApp, can read or listen to them. Tap to learn more.")
    for n, (minutes, side, text) in enumerate(lines):
        t = t0 + datetime.timedelta(minutes=minutes, seconds=7 * n)
        if text == VOICE:
            text = "\u200eaudio omitted" if ios else f"PTT-{t:%Y%m%d}-WA{n:04d}.opus (file attached)"
        elif text == PHOTO:
            text = "\u200eimage omitted" if ios else "<Media omitted>"
        head = f"[{t:%d/%m/%Y, %H:%M:%S}] " if ios else f"{t:%d/%m/%Y, %H:%M} - "
        rows.append(f"{head}{TEAM if side == 's' else who}: {text}")
    sep = " - " if ios else " with "
    (out / "whatsapp" / f"WhatsApp Chat{sep}{name or num}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def mojibake(s):
    return s.encode("utf-8").decode("latin-1")


def instagram(i, name, lines, out):
    t0 = start(i)
    msgs = []
    for n, (minutes, side, text) in enumerate(lines):
        t = t0 + datetime.timedelta(minutes=minutes, seconds=7 * n)
        m = {"sender_name": mojibake(TEAM if side == "s" else name), "timestamp_ms": int(t.timestamp() * 1000)}
        if text == VOICE:
            m["audio_files"] = [{"uri": "your_instagram_activity/messages/audio/demo.mp4"}]
        elif text == PHOTO:
            m["photos"] = [{"uri": "your_instagram_activity/messages/photos/demo.jpg"}]
        else:
            m["content"] = mojibake(text)
        msgs.append(m)
    msgs.insert(2, {"sender_name": mojibake(name), "timestamp_ms": msgs[1]["timestamp_ms"] + 1000,
                    "content": "Liked a message"})
    user = "democustomer" + str(i) if not name.startswith("Demo ") else "demo" + name[5:].lower()
    folder = f"{user}_{1000000000 + i}"
    doc = {"participants": [{"name": mojibake(name)}, {"name": TEAM}], "messages": msgs[::-1],
           "title": mojibake(name), "is_still_participant": True, "thread_path": f"inbox/{folder}"}
    where = out / "instagram" / "messages" / "inbox" / folder
    where.mkdir(parents=True, exist_ok=True)
    (where / "message_1.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def write(out):
    out = Path(out)
    (out / "whatsapp").mkdir(parents=True, exist_ok=True)
    for i, (name, where, lines) in enumerate(CHATS):
        if where == "ig":
            instagram(i, name, lines, out)
        else:
            whatsapp(i, name, where == "ios", lines, out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write the made-up chat export for the Arena personas.")
    ap.add_argument("--out", required=True, help="the folder to write, outside this repo")
    where = ap.parse_args().out
    if hist.within(where, hist.REPO):  # by device and inode: a change of case is still inside
        ap.error("--out must be outside this repo")
    write(where)
