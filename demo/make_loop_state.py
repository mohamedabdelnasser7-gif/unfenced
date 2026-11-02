"""Writes a demo state folder for the loop judges see (DECISIONS items 78 and 79): one made-up owner
running two Sales style agents of one kind (siblings) and one support agent, a database with a few
made-up live style chats, already cleaned, and one lesson the first agent kept.

    python3 -I demo/make_loop_state.py [--state FOLDER]

FOLDER defaults to data/demo-loop, which git ignores; it must sit outside the repo or under data/,
and it must not hold a database yet. What it writes, in the layout Quick start's Build uses
(reflection/quickstart.py):
  agents/owner.json            {"owner": "demo"}: the owner the three plugs name
  agents/boots_seller/         a Sales style agent, kind sales, with one kept lesson
  agents/bags_seller/          a second agent of kind sales: a sibling of boots_seller
  agents/returns_helper/       a support agent, kind support
  ascent.db                    the chats, their log rows (engine/log.py) and the kept lesson

Every chat is made up: no real customer text, the names are "Demo" names and the numbers run from
0100 000 0700 upward. Each chat is in the log of the agent that answered it, so a night grows the
practice customers of that agent's kind into the owner's pool (arena/grow.py): the Sales style
chats are labelled from the chat (quiet after the price is lost), the support chats by the agent's
own deciding result (unresolved is lost). Then, with a key in .env, the commands it prints run one
night each: boots_seller's grows the sales pool shared with bags_seller, and bags_seller's night
reads boots_seller's kept lesson first, fit checks and adapts it, and holds it for a yes, as it has
no exam to put it on trial through (engine/study.py step 6). Nothing here calls a model.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arena import paths  # noqa: E402
from arena import recipe as recipe_mod  # noqa: E402
from engine import plug as plug_mod  # noqa: E402
from engine.lessons import Lessons  # noqa: E402
from engine.log import Log  # noqa: E402
from kit.chats import Chats  # noqa: E402
from kit.db import Db  # noqa: E402

STATE = paths.DATA / "demo-loop"
OWNER = "demo"
H = 3600.0
TRIAL = {"fast": {"share": 0.5, "days": 7}, "careful": {"share": 0.2, "days": 14}}
KEPT = "Give the delivery fee with the price, so the customer sees the whole total at once."

SALES_CASE = {"input": "a customer's first message on WhatsApp", "starts": "person",
              "output": "replies and, after a plain yes, an order", "ends": "an order is taken or the chat closes"}
SUPPORT_CASE = {"input": "a customer's message about a return or an exchange", "starts": "person",
                "output": "a reply that settles it and a tag", "ends": "it is resolved or tagged"}

# (folder, kind, what it does, good, bad, decides good, decides bad)
AGENTS = (
    ("boots_seller", "sales", "Answers a made-up shoe store's customers and takes orders after a plain yes.",
     "The customer orders after a plain yes.", "The chat closes with no order.", "order_taken", "chat_closed"),
    ("bags_seller", "sales", "Answers a made-up bag store's customers and takes orders after a plain yes.",
     "The customer orders after a plain yes.", "The chat closes with no order.", "order_taken", "chat_closed"),
    ("returns_helper", "support", "Answers a made-up shoe store's customers about returns and exchanges.",
     "The return or exchange is settled.", "The customer leaves with it unsettled.", "resolved", "unresolved"),
)

# Made-up chats: (chat id, agent, deciding result or None, [(role, text, hours before now)])
CHATS = (
    ("demo-c1", "boots_seller", "chat_closed", [
        ("user", "بكام الجزمة السودا مقاس 43؟ انا Demo Karim", 90),
        ("assistant", "الجزمة السودا ب 1450 جنيه، والمقاس 43 متاح", 89.9)]),
    ("demo-c2", "boots_seller", "chat_closed", [
        ("user", "Hi, how much is the white runner in size 41?", 84),
        ("assistant", "The white runner is 1,300 EGP, and size 41 is in stock.", 83.9),
        ("user", "And delivery to Giza?", 83.8),
        ("assistant", "Delivery to Giza is 60 EGP and takes two to three days.", 83.7)]),
    ("demo-c3", "boots_seller", "chat_closed", [
        ("user", "عندكم جزمة كورة مقاس 40؟", 78),
        ("assistant", "ايوه متاحة ب 1650 جنيه", 77.9),
        ("user", "غالية شوية، فيه خصم؟", 77.8),
        ("assistant", "السعر ثابت للأسف، بس الشحن عندنا سريع", 77.7)]),
    ("demo-c4", "boots_seller", "order_taken", [
        ("user", "السلام عليكم", 72), ("assistant", "اهلا بيك، تحب تشوف ايه؟", 71.9),
        ("user", "عايز جزمة جري رمادي", 71.8), ("assistant", "متاحة ب 1350 جنيه", 71.7),
        ("user", "فيه مقاس 44؟", 71.6), ("assistant", "ايوه 44 متاح", 71.5),
        ("user", "والشحن لاسكندرية؟", 71.4), ("assistant", "الشحن 70 جنيه وبياخد يومين", 71.3),
        ("user", "تمام، ينفع الدفع عند الاستلام؟", 71.2), ("assistant", "ايوه الدفع عند الاستلام", 71.1),
        ("user", "خلاص اكدلي", 71.0), ("assistant", "تم تسجيل الطلب", 70.9)]),
    ("demo-c5", "boots_seller", "order_taken", [
        ("user", "عايز الجزمة البيضا مقاس 42", 66), ("assistant", "السعر 1450 جنيه والشحن 60", 65.9),
        ("user", "تمام اكدلي", 65.8), ("assistant", "تم تسجيل الطلب", 65.7)]),
    ("demo-c6", "returns_helper", "unresolved", [
        ("user", "I want to return the trainers I got last week, they are too small.", 80),
        ("assistant", "Sorry about that. Is the box still with you?", 79.9),
        ("user", "No, I threw it away.", 79.8),
        ("assistant", "A return needs the box, so I tagged it for the team to look at.", 79.7)]),
    ("demo-c7", "returns_helper", "unresolved", [
        ("user", "عايز ابدل الجزمة بمقاس اكبر", 74),
        ("assistant", "المقاس الاكبر خلص للأسف من نفس اللون", 73.9),
        ("user", "طيب مش عايزها خالص", 73.8),
        ("assistant", "تمام، علمتها للفريق يراجعها", 73.7)]),
    ("demo-c8", "returns_helper", "resolved", [
        ("user", "Can I swap size 42 for 43?", 70),
        ("assistant", "Yes, size 43 is in stock. The courier swaps it at your door.", 69.9),
        ("user", "Great, thanks.", 69.8),
        ("assistant", "Done, the swap is booked.", 69.7)]),
)


def plug_for(agent, kind, does, good, bad):
    return {"agent": agent, "kind": kind, "owner": OWNER, "about": does,
            "case": "One WhatsApp chat with one customer; the case id is the chat id.", "fields": ["retail"],
            "stages": ["chat"], "actions": {"reply": "One answer to a customer message."},
            "results": {"replied": {"speed": "fast", "after": "reply"},
                        good: {"speed": "fast"}, bad: {"speed": "fast"}},
            "causes": {}, "source": {"about": "The customer in the chat.", "known_by": "case"},
            "harm": {"results": [bad]}, "decides": {"good": good, "bad": [bad]},
            "risk": {"high": {"about": "Prices, promises and personal data.", "tools": []},
                     "low": {"about": "Tone and word choice."}},
            "trial": TRIAL, "slot": "Lessons from past chats:"}


def card_for(agent, kind, does, good_line, bad_line, at):
    return {"agent": agent, "name": agent.replace("_", " ").capitalize(), "does": does, "good": good_line,
            "bad": bad_line, "case": SUPPORT_CASE if kind == "support" else SALES_CASE,
            "never": ["Never promises a delivery date the tools did not give."], "needs": [], "tools": [],
            "kind": kind, "level": "careful", "at": at}


def check_state(state):
    state = Path(state).expanduser().resolve()
    if paths.inside_repo(state) and not paths.within(state, paths.DATA):
        raise SystemExit("Not written: the state folder sits inside the repo outside data/.")
    if (state / "ascent.db").exists() or (state / "agents").exists():
        raise SystemExit(f"Not written: {state} has a demo state already. Remove it or name another --state.")
    return state


def write(state, now=None):
    """The demo state in state; returns {agent: plug}."""
    now = time.time() if now is None else float(now)
    agents = state / "agents"
    agents.mkdir(parents=True)
    (agents / "owner.json").write_text(json.dumps({"owner": OWNER}) + "\n", encoding="utf-8")
    plugs = {}
    for agent, kind, does, good_line, bad_line, good, bad in AGENTS:
        folder = agents / agent
        folder.mkdir()
        (folder / "plug.json").write_text(json.dumps(plug_for(agent, kind, does, good, bad), indent=1) + "\n",
                                          encoding="utf-8")
        (folder / "instructions.md").write_text(f"{does} Plain, short and warm. Facts come from the tools only.\n",
                                                encoding="utf-8")
        (folder / "card.json").write_text(json.dumps(card_for(agent, kind, does, good_line, bad_line, now),
                                                     ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        plugs[agent] = plug_mod.load(folder / "plug.json")
    db = Db(str(state / "ascent.db"))
    try:
        Chats(db)
        logs = {a: Log(db, p) for a, p in plugs.items()}
        with db.tx() as c:
            for k, (cid, agent, _, steps) in enumerate(CHATS):
                times = [now - s[2] * H for s in steps]
                c.execute("INSERT INTO chats (id, channel, customer_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                          (cid, "whatsapp", f"2010000{700 + k:05d}", min(times), max(times)))
                for n, (role, text, h) in enumerate(steps, 1):
                    c.execute("INSERT INTO steps (chat_id, n, role, content, at) VALUES (?, ?, ?, ?, ?)",
                              (cid, n, role, text, now - h * H))
        for cid, agent, ended, steps in CHATS:
            for role, _, h in steps:
                if role == "assistant":
                    logs[agent].act(cid, "reply", result="replied", stage="chat", at=now - h * H)
            logs[agent].result(cid, ended, stage="chat", at=now - steps[-1][2] * H + 1)
        boots = Lessons(db, plugs["boots_seller"])
        lesson = boots.add(KEPT, ["chat"], yes_by=OWNER, now=now - 30 * 24 * H)
        if not boots.keep(lesson):
            raise SystemExit("Not written in full: the kept lesson waits behind a trial.")
    finally:
        db.close()
    return plugs


def commands(state):
    db = state / "ascent.db"
    return [f'python3 -m reflection.night --plug "{state / "agents" / a / "plug.json"}" --db "{db}" '
            f'--recipe "{recipe_mod.EXAMPLE}"' for a in ("boots_seller", "returns_helper", "bags_seller")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", default=str(STATE), help="the demo state folder (default: data/demo-loop)")
    args = ap.parse_args(argv)
    state = check_state(args.state)
    write(state)
    print(f"Wrote the demo state in {state}: owner {OWNER}, agents boots_seller and bags_seller (kind sales, "
          f"siblings) and returns_helper (kind support), {len(CHATS)} made-up chats and one kept lesson.")
    print("With a key in .env, one night each, in this order:")
    for line in commands(state):
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
