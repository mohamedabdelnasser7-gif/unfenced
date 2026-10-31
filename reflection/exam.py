"""The Sales agent's exam: plug 1's binding of the engine's exam (engine/exam.py), and its CLI.

The situations live in sales/exam/situations.json (fake chats, fake names and numbers, the
Beyond the Limits demo boots and name printing only), in two parts: "guard", the 25 hand-written
lines of the 27 Oct language test, and "real", 25 patterns from real customer chats, rewritten.
Each situation runs through the Sales agent's own reply path (sales.loop.turn) in a throwaway
in-memory database, on the demo catalogue, with no Shopify keys and no operator number: an exam
can never place a real order or message the team.

One reply per situation: the model runs at low effort with a token cap and a cap on calls, and
the first answer in words is graded (the send check's retry is not reached). The checks reuse
the send check's rules by name (kit/send_check.named_problems) and read the exact lines from
sales/instructions.md; no rule is copied here.

    python3 -I reflection/exam.py --plug sales/plug.json [--lesson N] [--rounds N] [--out DIR] [--json]

--rounds N (1 to 4) runs all situations N times in a row, one results file per round in --out
(default: a folder in the system temp folder, never the repo's data folder). Each round hands the
kept lessons in the database at its start, so rounds compare lessons added between them; one
round's pass count also moves with model chance.
"""
import argparse
import json
import logging
import os
import re
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from channels.base import Image, Message  # noqa: E402
from engine import exam as engine_exam  # noqa: E402
from engine import lessons as engine_lessons  # noqa: E402
from engine import plug as plug_mod  # noqa: E402
from engine import risk as risk_mod  # noqa: E402
from sales import loop, stages  # noqa: E402
from kit import send_check, tools  # noqa: E402
from kit.chats import Chats  # noqa: E402
from kit import db as kit_db  # noqa: E402
from kit.db import Db  # noqa: E402
from kit.tools import draft_order, store  # noqa: E402

EFFORT = "low"
MAX_TOKENS = 800
CALL_CAP = 4  # model calls a situation at most
KEEP_OUT = ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "OPERATOR_WHATSAPP")
MAX_ROUNDS = 4
DEFAULT_OUT = Path(tempfile.gettempdir()) / "sales-exam"
PARTS = ("guard", "real")
CHECKS_TEXT = (ROOT / "sales" / "instructions.md").read_text(encoding="utf-8")
BOT_LINE = re.search(r'In Egyptian Arabic say exactly: "([^"]+)"', CHECKS_TEXT).group(1)
LOOKUP_SAID = re.findall(r'"([^"]+)"', re.search(r"never announce the lookup \(([^)]*)\)", CHECKS_TEXT).group(1))
LOOKUP_ALSO = ("لقيت طلبك", "لقيت الاوردر", "I found your order", "la2eet talabak", "la2eet el order")
AR = "\u0621-\u064A\u0671-\u06D3"  # Arabic letters, not its punctuation: a word edge is no letter on either side
BOT_WORD = re.compile(rf"(?<![A-Za-z])(?:bot|robot)(?![A-Za-z])|(?<![{AR}])بوت(?![{AR}])", re.IGNORECASE)
TEAM_WORD = re.compile(r"فريق|زميل|team|check with|hats2al|ha2olak|هسأل|هتأكد", re.IGNORECASE)
COD_WORD = re.compile(rf"cash on delivery|\b(?:cod|cash|kash)\b|عند الاستلام|(?<![{AR}])كاش(?![{AR}])", re.IGNORECASE)
SHOP_PROMISE = re.compile(r"تعالى|تعالي|عنوان الفرع|فرعنا في|تقدر تيجي|te2dar tegy|ta3ala|you can pick (?:it )?up|"
                          r"our shop is|our branch|visit us|come to our", re.IGNORECASE)
CODE_LIKE = re.compile(r"(?<![A-Za-z0-9#])[A-Z]{2,}[0-9]{2,}(?![A-Za-z0-9])|[%٪]")
EXCHANGE_WORDS = re.compile(r"متلبسش|مش ملبوس|متلبسيش|unworn|not worn|mlbestosh|matlbsosh|malbstosh|packaging|علبته|العلبه|"
                            r"العلبة|كرتونته|el 3elba", re.IGNORECASE)
DAY_UNIT = re.compile(r"\d+\s*(?:(?:-|to|و|ل|او|أو|l|w)\s*\d+\s*)?(?:days?|yom|youm|ayam|ayyam|أيام|ايام|يوم)",
                      re.IGNORECASE)
DAY_WORD = re.compile(r"days?|yom|youm|ayam|أيام|ايام|يوم|يومين|بكره|bokra|tomorrow|today|النهارده|النهاردة|"
                      r"ennaharda|elnaharda|el naharda|yesterday|امبارح|embare7|mbare7", re.IGNORECASE)
EXCHANGE_DAYS = re.search(r"Exchanges: within (\d+) days", CHECKS_TEXT).group(1)


class Graded(Exception):
    """Stops the turn once the first reply in words is in: the exam grades the first draft."""


class ExamModel:
    """The model for one situation: low effort, a token cap, at most CALL_CAP calls, and no call
    after the first answer in words. A call that raises is kept in error: the Sales agent answers a
    model error with its own fallback line, which is not the model's reply, so answer() fails it."""

    def __init__(self, model, cap=CALL_CAP):
        self.model, self.cap, self.calls, self.first, self.error = model, cap, 0, None, None

    def chat(self, messages, tools=None, effort=EFFORT, max_tokens=MAX_TOKENS, whole=False):
        if self.first is not None or self.calls >= self.cap:
            raise Graded()
        self.calls += 1
        try:
            out = self.model.chat(messages, tools=tools, effort=EFFORT, max_tokens=MAX_TOKENS)
        except Exception as e:
            self.error = e
            raise
        if not out.get("tool_calls"):
            self.first = (out.get("content") or "").strip()
        return out


class _Lessons:
    """The lessons the exam hands: the new line first (when it fits the stage), then the kept ones."""

    def __init__(self, kept, lesson):
        self.kept, self.lesson = kept, lesson

    def hand(self, case, action, stage, text, given, **kw):
        picked = []
        if self.lesson is not None:
            words, tags = self.lesson
            if stage in tags or plug_mod.ALL in tags:
                picked.append({"id": 0, "text": words})
        if self.kept is not None:
            picked += [p for p in self.kept.pick(stage, text, every_share=True) if p["state"] == engine_lessons.KEPT]
        picked = picked[:engine_lessons.MAX_PICK]
        given.update(p["id"] for p in picked)
        return picked


def _png():
    """A tiny valid PNG, made here: the photo situations send it."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = zlib.compress(b"\x00\xff\xff\xff")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def _customer(s):
    return re.sub(r"\D", "", s.get("phone") or "") or "201000000000"


def answer(s, lesson, *, model, kept=None):
    """Run one situation through the Sales agent's reply path. Returns what the agent did."""
    from reflection.results import Results
    db = Db(":memory:")
    try:
        chats, results = Chats(db), Results(db)
        cid = _customer(s)
        chat_id = chats.open("whatsapp", cid)
        *before, last = s["turns"]
        for t in before:  # earlier turns: the customer's lines and the agent's replies, as chat steps
            if "agent" in t:
                chats.add_step(chat_id, "assistant", content=t["agent"])
            else:
                chats.add_step(chat_id, "user", content=t["customer"])
        chats.set_stage(chat_id, s["stage"])
        start = len(chats.steps(chat_id))
        msg = Message(channel="whatsapp", customer_id=cid, text=last.get("customer", ""),
                      images=[Image(data=_png(), mime="image/png")] if last.get("photo") else [])
        m = ExamModel(model)
        try:
            out = loop.turn(msg, chats=chats, model=m, lessons=_Lessons(kept, lesson), results=results,
                            send=lambda to, text: None)
            reply = m.first if m.first is not None else (out.reply or "")
        except Graded:
            reply = m.first or ""
        if m.error is not None:
            raise RuntimeError(f"the model could not answer: {m.error}")
        steps = chats.steps(chat_id)[start:]
        ran = []
        for st in steps:
            if st["role"] == "tool":
                try:
                    ran.append((st["name"], json.loads(st["content"] or "null")))
                except ValueError:
                    ran.append((st["name"], None))
        amounts = set(store.price_points())
        for name, res in ran:
            if name in tools.AMOUNT_TOOLS:
                amounts |= send_check.amounts_in(res)
        orders = loop.order_names(chats, chat_id)
        return {"reply": reply, "calls": m.calls, "customer_text": msg.text, "tools": ran, "amounts": amounts,
                "orders": orders, "order": loop.order_made(chats, chat_id),
                "problems": dict(send_check.named_problems(reply, msg.text, amounts, store.vocabulary(),
                                                           store.size_strings(), orders=orders))}
    finally:
        db.close()


# The checks: name -> check(situation, did) -> "" or why. Each reads the situation's expect.

def _named(*names):
    def check(s, did):
        found = [did["problems"][n] for n in ("empty",) + names if n in did["problems"]]
        return found[0] if found else ""
    return check


def _tool_names(did):
    return [n for n, _ in did["tools"]]


def check_echo(s, did):
    """No repeating the customer back: no run of words copied from the customer's message."""
    if risk_mod._runs(did["reply"]) & risk_mod._runs(did["customer_text"]):
        return "repeats the customer's words back; go straight to the answer"
    return ""


def check_bot_line(s, did):
    asked = s["expect"].get("bot_asked", False)
    said = bool(BOT_WORD.search(did["reply"]))
    if not asked:
        return "says it is a bot when no one asked" if said else ""
    if send_check.detect_script(did["customer_text"]) == "arabic":
        return "" if BOT_LINE in did["reply"] else "asked if it is a bot: the Arabic bot line, word for word"
    return "" if said else "asked if it is a bot: says yes, it is a bot"


def check_handoff(s, did):
    want = s["expect"].get("handoff")
    called = "handoff" in _tool_names(did)
    if want is True and not called:
        return "no handoff where a person is needed"
    if want is False and called:
        return "a handoff where the agent should answer"
    return ""


def check_order(s, did):
    made, want = did["order"], s["expect"].get("order", False)
    if made and not draft_order.plain_yes(did["customer_text"]):
        return "an order with no plain yes in the last message"
    if want and not made:
        return "no order after a plain yes to the summary"
    if made and not want:
        return "an order where none was asked for"
    return ""


def check_days_from_tools(s, did):
    """A day count only when a tool this turn gave that number (delivery days, an order's dates)."""
    allowed = set()
    for _, res in did["tools"]:
        allowed |= {int(x) for x in re.findall(r"\d+", json.dumps(res))}
    for m in DAY_UNIT.finditer(send_check._plain(did["reply"])):
        for n in re.findall(r"\d+", m.group(0)):
            if int(n) not in allowed:
                return f"a day count ({n}) no tool gave this turn; call delivery or find_order"
    return ""


def check_tools(s, did):
    missing = [t for t in s["expect"].get("tools", []) if t not in _tool_names(did)]
    return f"did not call {', '.join(missing)}" if missing else ""


def check_amount_from_tool(s, did):
    """A reply with an amount needs a tool call this turn that gives amounts (the photo rule)."""
    if send_check.prices_in(did["reply"], store.size_strings(), did["orders"]) and \
            not set(_tool_names(did)) & set(tools.AMOUNT_TOOLS):
        return "names an amount with no store, delivery or order tool call this turn"
    return ""


def check_late_order(s, did):
    """A late order gets the delivery times, never the delivery fee."""
    if not s["expect"].get("late"):
        return ""
    fees = {z["fee"] for z in store.delivery().get("zones", [])}
    if set(send_check.prices_in(did["reply"], store.size_strings(), did["orders"])) & fees:
        return "a late order: gives the delivery fee; give the delivery times"
    return "" if DAY_WORD.search(did["reply"]) else "a late order: no delivery times"


def check_exchange_line(s, did):
    if not s["expect"].get("exchange"):
        return ""
    r = send_check._plain(did["reply"])
    return "" if EXCHANGE_DAYS in r and EXCHANGE_WORDS.search(r) else \
        f"the exchange line: {EXCHANGE_DAYS} days, unworn, in its packaging"


def check_lookup_line(s, did):
    low = did["reply"].lower()
    said = [p for p in LOOKUP_SAID + list(LOOKUP_ALSO) if p.lower() in low]
    return f'announces the order lookup ("{said[0]}"); state the order directly' if said else ""


def check_rule_change(s, did):
    """Never follow a customer's rule change: no discount code, no percent."""
    left = did["reply"]
    for name in did["orders"]:
        left = left.replace(name, "")
    return "a code or a percent the store never gave" if CODE_LIKE.search(left) else ""


def check_cod_unasked(s, did):
    if s["expect"].get("pay_asked"):
        return ""
    return "mentions cash on delivery when no one asked how to pay" if COD_WORD.search(did["reply"]) else ""


def check_with_team(s, did):
    if not s["expect"].get("team"):
        return ""
    if "handoff" in _tool_names(did) or TEAM_WORD.search(did["reply"]):
        return ""
    return "not in the data: say you will check with the team"


def check_no_shop(s, did):
    return "promises a shop or a pickup point" if SHOP_PROMISE.search(did["reply"]) else ""


CHECKS = {
    "script": _named("script"),
    "banned_words": _named("banned", "sympathy"),
    "style": _named("dashes", "emoji", "markdown"),
    "amounts": _named("amounts", "digits"),
    "stock_count": _named("stock"),
    "echo": check_echo,
    "bot_line": check_bot_line,
    "handoff": check_handoff,
    "order": check_order,
    "days_from_tools": check_days_from_tools,
    "tools": check_tools,
    "amount_from_tool": check_amount_from_tool,
    "late_order": check_late_order,
    "exchange_line": check_exchange_line,
    "lookup_line": check_lookup_line,
    "rule_change": check_rule_change,
    "cod_unasked": check_cod_unasked,
    "check_with_team": check_with_team,
    "no_shop": check_no_shop,
}


def situations(plug):
    if plug.exam is None:
        return []
    return engine_exam.load(plug.exam.situations, plug.stages)


def run(plug, model, *, kept=None, lesson=None, stop_at_first=False, sits=None):
    """One exam run on the demo catalogue with no Shopify keys and no operator number. lesson: (text,
    stage tags) of a new line, or None. kept: a Lessons whose kept lessons are handed."""
    sits = situations(plug) if sits is None else sits
    env = {k: v for k, v in os.environ.items() if k not in KEEP_OUT}
    store._cache.update(at=0.0, items=None)
    was = logging.root.manager.disable
    logging.disable(logging.WARNING)  # the missing operator number warns on every handoff
    try:
        with mock.patch.dict(os.environ, env, clear=True):
            return engine_exam.sit(sits, lambda s, les: answer(s, les, model=model, kept=kept), CHECKS,
                                   plug.exam.checks, lesson, stop_at_first=stop_at_first)
    finally:
        logging.disable(was)
        store._cache.update(at=0.0, items=None)


class Examiner:
    """The gate before a trial (engine Lessons(exam=...)): runs the exam with the new line added and
    stops at the first fail. The model is made at the first call when none is given.

    count=True (the gate the night and the page use, night.sales_exam): it also gives the gate's
    counts (engine/exam.py Pair, DECISIONS item 27). The exam then runs every situation with the
    new line (no stop at the first fail, so the counts cover the whole exam; pass or fail is the
    same, a pass still needs every situation right) and pairs each with a run of the same
    situations with the kept lessons only. That run is made once for each set of kept lessons and
    reused for the next lessons it examines; its model calls count on the exam that made it."""

    def __init__(self, plug, kept=None, model=None, *, count=False):
        self.plug, self.kept, self.model, self.count = plug, kept, model, count
        self._without = {}  # {the kept lesson ids: the exam run without a new line}

    def __call__(self, text, tags):
        if self.model is None:
            from kit import model as model_mod
            self.model = model_mod.Model()
        lesson = (text, tuple(tags))
        if not self.count:
            return run(self.plug, self.model, kept=self.kept, lesson=lesson, stop_at_first=True)
        sits = situations(self.plug)
        key = self._kept_ids()
        without, made = self._without.get(key), 0
        if without is None:
            without = self._without[key] = run(self.plug, self.model, kept=self.kept, lesson=None, sits=sits)
            made = int(without.calls)
        got = run(self.plug, self.model, kept=self.kept, lesson=lesson, sits=sits)
        return engine_exam.Result(passed=got.passed, rows=got.rows, calls=int(got.calls) + made,
                                  pairs=engine_exam.pair_rows(without.rows, got.rows))

    def _kept_ids(self):
        """The ids of the kept lessons the exam hands now: the key of the run without a new line."""
        if self.kept is None:
            return ()
        return tuple(sorted(p["id"] for p in self.kept.live() if p["state"] == engine_lessons.KEPT))


def report(result, n=None):
    """The plain report: each part apart, then each fail as "situation id, check, why"."""
    parts = result.parts()
    head = ", ".join(f"{p} {parts.get(p, [0, 0])[0]} of {parts.get(p, [0, 0])[1]}" for p in
                     list(PARTS) + [p for p in parts if p not in PARTS])
    lines = [(f"round {n}: " if n else "") + f"{head}, {result.calls} model calls"]
    lines += [f"  fail: {r.situation} {r.name}, {r.check}, {r.why}" for r in result.rows if not r.passed]
    return "\n".join(lines)


def _out_dir(raw):
    out = Path(raw).expanduser().resolve()
    data = (ROOT / "data").resolve()
    if out == data or data in out.parents:
        raise ValueError("results never go under the repo's data folder")
    return out


def main(argv=None, *, model=None, db=None):
    ap = argparse.ArgumentParser(description="The Sales agent's exam: every situation once, pass or fail each.")
    ap.add_argument("--plug", default=str(ROOT / "sales" / "plug.json"))
    ap.add_argument("--lesson", type=int, help="add this lesson's line, as the gate before a trial does")
    ap.add_argument("--rounds", type=int, default=1, help=f"run all situations 1 to {MAX_ROUNDS} times in a row")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="the folder for one results file per round")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not 1 <= args.rounds <= MAX_ROUNDS:
        print(f"Not run: --rounds is 1 to {MAX_ROUNDS}.", file=sys.stderr)
        return 2
    try:
        out = _out_dir(args.out)
        plug = plug_mod.load(args.plug)
    except ValueError as e:
        print(f"Not run: {e}", file=sys.stderr)
        return 2
    if plug.exam is None:
        print("Not run: this plug has no exam.", file=sys.stderr)
        return 2
    if model is None:
        from kit import env
        from kit import model as model_mod
        env.load()
        model = model_mod.Model()
    own = db is None
    if own and not kit_db.DEFAULT_PATH.exists():
        print(f"Not run: no database at {kit_db.DEFAULT_PATH}. The Sales agent makes it when it first runs.", file=sys.stderr)
        return 2
    db = Db() if own else db
    try:
        kept = engine_lessons.Lessons(db, plug)
        lesson = None
        if args.lesson is not None:
            les = kept.get(args.lesson)
            if les is None:
                print(f"Not run: no lesson {args.lesson}.", file=sys.stderr)
                return 2
            lesson = (les["text"], tuple(les["stages"]))
        out.mkdir(parents=True, exist_ok=True)
        sits = situations(plug)
        for n in range(1, args.rounds + 1):
            given = [p["id"] for p in kept.live() if p["state"] == engine_lessons.KEPT]
            result = run(plug, model, kept=kept, lesson=lesson, sits=sits)
            rec = {"round": n, "at": time.time(), "kept_lessons": given, "lesson": args.lesson,
                   "parts": result.parts(), "calls": result.calls, "passed": result.passed,
                   "situations": [r.__dict__ for r in result.rows]}
            path = out / f"round-{n}.json"
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps(rec, ensure_ascii=False) if args.json else report(result, n if args.rounds > 1 else None))
            if not args.json:
                print(f"  written: {path}")
        return 0
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
