"""Store offers in the Arena (decision 105, job B): a card an offer covers wins as a sale, a card no offer
covers wins on a correct close (arena/close.py for Sales, arena/good.py close_case for an agent made here),
a made-up offer loses, the store team's old rate is a report line only, and Reflection, Try again and the
quick notes never take a correct close as a loss. Card matching is code (arena/offers.py), 0 model calls.
Fake models only, no network."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import close, gate, good, learn, learn_built, match as match_mod, offers, practice, run, verdict
from kit import offers as kit_offers, turn
from kit.db import Db
from tests.fake_model import BUY, Seller, call, clean_env, say
from tests.test_arena_run import card
from tests.test_customers_shape import Base as ShapeBase, Writer
from tests.test_try_again import Base as TryBase, Seen

COVERED = "installments please"            # valU's covers word "installment", with a plural s
CLOSE = "a firm delivery date"             # no offer of the store data covers it (decision 105: no time offer)
NOW = 1_790_000_000.0
CLOSE_REPLY = "I cannot promise an exact day. The nearest I can do is our usual delivery. Message me any time."
MADE_UP = "Just for you: 10% off today."


def offer_card(i, worry, trigger, chats=10, won=0):
    return dict(card(i, worry), buy_trigger=[trigger], chats=chats, won=won)


class Agent(Seller):
    """Sells as fake_model.Seller to a customer asking the price; to one asking when it arrives or for a deal it
    runs the store tool first and then closes honestly or makes up an offer."""

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        first = next((m.get("content") or "" for m in messages if m["role"] == "user"), "")
        last = messages[-1]
        if "arrive" in first or "deal" in first:
            self.calls.append({"messages": messages})
            if last["role"] == "tool":
                return say(CLOSE_REPLY if "arrive" in first else MADE_UP)
            if any(m["role"] == "tool" for m in messages):
                return say(CLOSE_REPLY if "arrive" in first else MADE_UP)
            return call("store", query="Mercurial")
        return super().chat(messages, tools, effort, max_tokens, whole)


class Shopper:
    """Asks by its worry; buys (BUY, then yes) when its line says an offer meets its need and its worry is a
    buyer; else leaves politely after the first answer."""

    def __init__(self, buyers=("price",)):
        self.buyers, self.calls = set(buyers), 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        system = messages[0]["content"]
        worry = system.split("Your worry is ")[1].split(".")[0]
        if len(messages) == 2:
            return say({"price": "How much is the Mercurial Vapor 17 Elite?", "date": "When does it arrive exactly?",
                        "deal": "Any deal for me?"}.get(worry, "How much is the Mercurial Vapor 17 Elite?"))
        if worry in self.buyers and "An offer like this meets your need" in system:
            return say("yes" if "Confirm?" in (messages[-1]["content"] or "") else BUY)
        return say("[leave]")


class CloseJudge:
    """The close judge's side: a correct close unless the chat holds a percent the store never gave."""

    def __init__(self, unreadable=0):
        self.asks, self.unreadable = [], unreadable

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.asks.append({"system": messages[0]["content"], "ask": json.loads(messages[1]["content"])})
        if self.unreadable:
            self.unreadable -= 1
            return say("not json")
        made_up = "%" in json.dumps(self.asks[-1]["ask"]["played"], ensure_ascii=False)
        return say(json.dumps({"made_up_offer": made_up, "nearest_option": True, "polite": True, "door_open": True,
                               "turn": 1, "why": "made up a percent" if made_up else "honest and kind"}))


class InOrder(run.Arena):
    """The Arena with its practice draw in deck order, so a test knows which card plays."""

    def pick(self, deck, r, k):
        return sorted(deck, key=lambda c: c["id"])[(k - 1) % len(deck)]


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.agent, self.shopper, self.judge = Agent(), Shopper(), CloseJudge()

    def arena(self, cards, cls=run.Arena, cap=1000, **kw):
        self.calls = run.Calls(self.dir / "calls.json", cap, day="2026-11-04")
        return cls(cards, agent_model=self.agent, customer_model=self.shopper, judge_model=self.judge,
                   calls=self.calls, state=self.dir, now=lambda: NOW, **kw)

    def saved(self):
        return [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]


class CardMatching(unittest.TestCase):
    def test_cover_reads_any_trigger_against_the_covers_words_in_code(self):
        data = kit_offers.demo()
        got = offers.cover({"buy_trigger": ["a firm delivery date", COVERED]}, data)
        self.assertIn("Pay in installments through valU", got["covered_by"])
        self.assertFalse(got["close"])
        self.assertEqual(offers.cover({"buy_trigger": [CLOSE]}, data), {"covered_by": [], "close": True})
        arabic = offers.cover({"buy_trigger": ["بالتقسيط"]}, data)  # the joined letter and the article fold away
        self.assertIn("Pay in installments through valU", arabic["covered_by"])
        never = offers.cover({"buy_trigger": [CLOSE], "unwinnable": True}, data)
        self.assertFalse(never["close"])  # told it never buys: no close card, it plays as before
        self.assertEqual(offers.cover({"buy_trigger": [CLOSE]}, None), {"covered_by": [], "close": False})

    def test_the_offer_line_reaches_the_customer_prompt_and_the_match(self):
        import random
        covered = offers.mark([offer_card(1, "price", COVERED)], kit_offers.demo())[0]
        shut = offers.mark([offer_card(2, "date", CLOSE)], kit_offers.demo())[0]
        text, _ = match_mod.fill(match_mod.GENERIC_PROMPT, covered, random.Random(1))
        self.assertIn("An offer like this meets your need: Pay in installments through valU", text)
        text, _ = match_mod.fill(match_mod.GENERIC_PROMPT, shut, random.Random(1))
        self.assertIn(match_mod.OFFER_LINES[1], text)
        old = match_mod.PAST_GENERIC_PROMPTS[0]  # the prompt before the line is still known by its fingerprint
        self.assertIn(match_mod.prompt_sha(old), match_mod.KNOWN_PROMPTS)
        self.assertNotIn("$offer", match_mod.fill(old, shut, random.Random(1))[0])
        self.assertTrue(match_mod.match_of(shut, 1, [], "left", False, "x")["close"])
        self.assertFalse(match_mod.match_of(covered, 1, [], "left", False, "x")["close"])

    def test_no_store_tool_is_no_correct_close_and_takes_no_model_call(self):
        judge = CloseJudge()
        turns = [{"n": 1, "customer": "when?", "replies": [CLOSE_REPLY], "tools": [], "failed": []}]
        got = close.judge({"turns": turns, "ended": "left", "close": True}, offer_card(1, "date", CLOSE),
                          kit_offers.demo(), judge)
        self.assertEqual((got["won"], got["why"], judge.asks), (False, f"{close.NOT_CLOSED}: {close.NO_STORE}", []))
        turns[0]["tools"] = ["store"]
        got = close.judge({"turns": turns, "ended": "left", "close": True}, offer_card(1, "date", CLOSE),
                          kit_offers.demo(), judge)
        self.assertEqual((got["won"], got.get("close"), len(judge.asks)), (True, True, 1))

    def test_the_verdict_asks_for_the_close_judge_only_on_a_close_card_with_no_sale(self):
        turns = [{"n": 1, "customer": "hi", "replies": ["hello"], "failed": [], "order": False}]
        self.assertTrue(verdict.judge({"turns": turns, "ended": "left", "close": True})["needs_close"])
        self.assertNotIn("needs_close", verdict.judge({"turns": turns, "ended": "left"}))
        self.assertNotIn("needs_close", verdict.judge({"turns": turns, "ended": "no_safe_reply", "close": True}))
        failed = [dict(turns[0], failed=[{"check": "amounts", "why": "a made-up price"}])]
        self.assertNotIn("needs_close", verdict.judge({"turns": failed, "ended": "left", "close": True}))


class T6ArenaScore(Base):
    def cards(self):
        return [offer_card(1, "browse", COVERED, chats=40, won=4),  # trains; it leaves, no sale
                offer_card(2, "price", COVERED, chats=10, won=3),
                offer_card(3, "date", CLOSE, chats=30, won=1),
                offer_card(4, "deal", CLOSE, chats=20, won=0)]

    def test_a_sale_a_correct_close_and_a_made_up_offer(self):
        a = self.arena(self.cards(), matches=1, rounds=1, held_out=["persona-02", "persona-03", "persona-04"],
                       trust={"matches": 3, "wins": 3, "zero_failed_checks": True})
        a.quick = True  # its item is saved whatever the gate says (a level here is all wins, test_arena_run)
        self.assertEqual(sorted(c["id"] for c in a.gate_cards), ["persona-02", "persona-03", "persona-04"])
        rep = a.run()
        by = {m["card"]: m for m in self.saved() if "-g" in m["id"]}
        self.assertEqual(sorted(by), ["persona-02", "persona-03", "persona-04"])  # each once at this size
        self.assertEqual((by["persona-02"]["won"], by["persona-02"]["why"], by["persona-02"]["close_win"]),
                         (True, verdict.WON_ORDER, False))
        self.assertEqual((by["persona-03"]["won"], by["persona-03"]["close_win"]), (True, True))
        self.assertTrue(by["persona-03"]["why"].startswith(close.WON))
        self.assertFalse(by["persona-04"]["won"])
        self.assertIn(close.MADE_UP, by["persona-04"]["why"])
        self.assertEqual((rep["sales"], rep["closes"]), (1, 1))
        self.assertEqual((rep["stopped"], rep["trust"]["wins"]), (run.ROUNDS, 3))  # 2 wins: the bar stays the level's
        self.assertEqual(rep["gate_mix"]["team_rate"], {"won": 4, "chats": 60})
        line = "The store team's real rate on these customers: 4 of 60 chats. Report only; the bar stays 3 of 3."
        self.assertIn(line, run.text(rep))
        self.assertIn("sales 1, correct closes 1", run.text(rep))
        self.assertEqual((rep["item"]["team_line"], rep["item"]["needs"]), (line, 3))
        self.assertEqual(rep["item"]["team_rate"], {"won": 4, "chats": 60})
        self.assertEqual((rep["item"]["sales"], rep["item"]["closes"]), (1, 1))
        # the close judge read the store tool's offers (no names or covers) and is counted on the cap
        self.assertEqual(len(self.judge.asks), 2)
        self.assertEqual(self.judge.asks[0]["ask"]["offers"], kit_offers.for_tool(kit_offers.demo()))
        self.assertNotIn("covers", json.dumps(self.judge.asks[0]["ask"]))
        self.assertEqual(self.calls.count, len(self.agent.calls) + self.shopper.calls + len(self.judge.asks))

    def test_the_close_judge_call_stops_at_the_cap(self):
        shut = [offer_card(1, "date", CLOSE), offer_card(2, "date", CLOSE)]
        a = self.arena(shut, matches=1, rounds=1, held_out=["persona-02"], trust={"matches": 1, "wins": 1})
        first = a.play(a.train[0], "m1", training=True)
        self.assertEqual(len(self.judge.asks), 1)
        played = self.calls.count
        self.assertEqual(played, len(self.agent.calls) + self.shopper.calls + 1)
        tight = self.arena(shut, cap=played * 2 - 1, matches=1, rounds=1, held_out=["persona-02"],
                           trust={"matches": 1, "wins": 1})
        tight.calls.count = played  # what is left is the match without its close judge
        tight.calls.path.write_text(json.dumps({"day": "2026-11-04", "calls": played, "cap": played * 2 - 1}),
                                    encoding="utf-8")
        self.assertTrue(first[1]["close"])
        self.assertIsNone(tight.play(tight.train[0], "m2", training=True))
        self.assertEqual(tight.halt, run.CAP)
        self.assertEqual(len(self.judge.asks), 1)  # the judge was never reached past the cap
        self.assertEqual(len([m for m in self.saved() if m["id"] == "m2"]), 0)  # dropped, never a loss

    def test_an_unreadable_close_judge_twice_is_unjudged_and_no_judge_keeps_the_loss(self):
        shut = [offer_card(1, "date", CLOSE), offer_card(2, "date", CLOSE)]
        self.judge = CloseJudge(unreadable=2)
        a = self.arena(shut, matches=1, rounds=1, held_out=["persona-02"], trust={"matches": 1, "wins": 1})
        self.assertIs(a.play(a.train[0], "m1", training=True), run.UNJUDGED)
        self.assertEqual(len(self.judge.asks), 2)
        self.judge = None
        b = self.arena(shut, matches=1, rounds=1, held_out=["persona-02"], trust={"matches": 1, "wins": 1})
        m, judged = b.play(b.train[0], "m2", training=True)
        self.assertEqual((judged["won"], judged["why"], m["close_win"]), (False, verdict.LEFT, False))


class Notes:
    held = ()

    def __init__(self):
        self.after = []

    def after_loss(self, m, judged, mid):
        self.after.append(mid)
        return {"match": mid, "note": None, "answer": None, "why": "stand in"}

    def clear(self, r):
        return []

    def for_prompt(self, chat_id):
        return None


class T7NoCaseNoNote(Base):
    def test_a_correct_close_writes_no_case_and_no_quick_note(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        notes = Notes()
        cards = [offer_card(1, "date", CLOSE), offer_card(2, "deal", CLOSE), offer_card(3, "price", COVERED)]
        a = self.arena(cards, cls=InOrder, matches=2, rounds=1, held_out=["persona-03"], notes=notes,
                       learn=lambda m, j, mid: learn.to_case(db, m, j, mid, now=NOW),
                       trust={"matches": 1, "wins": 1, "zero_failed_checks": True})
        rep = a.run()
        ids = {m["card"]: m["id"] for m in self.saved() if "-t" in m["id"]}
        self.assertEqual(rep["rounds"][0]["training"]["cases"], [learn.case_id(ids["persona-02"])])
        self.assertEqual(notes.after, [ids["persona-02"]])  # the made-up offer only
        self.assertEqual(rep["rounds"][0]["closes"], 1)
        with self.assertRaises(ValueError):
            learn.to_case(db, {"turns": []}, {"won": False, "close": True}, "x")


def _odd_offers():
    return {"offers": [{"id": "odd", "kind": "choice", "what": "An option for odd people", "terms": "t", "when": "w",
                        "covers": [f"settled {n}" for n in range(1, 30, 2)]}]}


class T8T9Built(ShapeBase):
    """An agent made here (tests/three_agents.json), its own offers.json covering the odd customers only."""

    def go(self):
        name = next(iter(self.folders))
        folder = self.folders[name]
        kit_offers.write(folder, _odd_offers())
        asks = []

        def play(agent, persona, *, seed=0, **kw):
            turns = [{"n": 1, "customer": "hi", "replies": ["hello"], "tools": [], "actions": [], "failed": []}]
            return dict(match_mod.match_of(persona, seed, turns, "done", False, "x"), agent=agent.name)

        class Judge:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                ask = json.loads(messages[1]["content"])
                asks.append({"system": messages[0]["content"], "ask": ask})
                return say(json.dumps({"reached": "close_case" in ask, "broke_never": False, "turn": 1, "why": "x"}))

        with mock.patch.object(practice, "play", play):
            rep = practice.practise(folder, agent_model=None, customer_model=Writer(), judge_model=Judge(),
                                    rounds=1, matches=10, customers=20, gate_size=10)
        return name, folder, rep, asks

    def test_t8_the_judge_reads_close_case_and_a_close_win_is_no_loss(self):
        name, folder, rep, asks = self.go()
        closes = [a for a in asks if "close_case" in a["ask"]]
        self.assertTrue(closes)
        self.assertTrue(any("close_case" not in a["ask"] for a in asks))  # the covered ones are judged as before
        self.assertEqual(closes[0]["ask"]["close_case"]["offers"], kit_offers.for_tool(_odd_offers()))
        self.assertIn("correct close", closes[0]["system"])
        saved = [json.loads(x) for x in (folder / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        close_ids = {m["card"] for m in saved if m.get("close")}
        won = [m for m in saved if m.get("close_win")]
        self.assertTrue(won and all(m["won"] for m in won))
        item = json.loads((self.root / rep["item"]["file"]).read_text(encoding="utf-8"))
        self.assertTrue(item["lost"])  # covered customers that were not reached
        self.assertFalse({x["card"] for x in item["lost"]} & close_ids)
        db = Db(":memory:")
        self.addCleanup(db.close)
        agent = turn.load(folder)
        got = learn_built.from_folder(db, agent.plug, folder, until=NOW * 2)
        training = [m for m in saved if "-t" in m["id"] and m.get("agent") == agent.plug.agent]
        self.assertTrue(training)
        self.assertEqual(got["won"], 0)  # every practice win here was a close: written neither good nor bad
        self.assertEqual(got["lost"], sum(not m["won"] for m in training))
        with self.assertRaises(ValueError):
            learn_built.to_case(db, agent.plug, won[0], {"won": False, "close": True}, won[0]["id"])

    def test_t9_try_again_reads_only_the_lost_list_and_never_a_close(self):
        from arena import retry
        name, folder, rep, asks = self.go()
        item = json.loads((self.root / rep["item"]["file"]).read_text(encoding="utf-8"))
        saved = [json.loads(x) for x in (folder / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        close_ids = {m["card"] for m in saved if m.get("close")}
        cards = retry.lost_cards(item["lost"])  # what Morning.try_again plays for an agent made here
        self.assertTrue(cards)
        self.assertFalse(set(cards) & close_ids)
        self.assertFalse(any(m.get("close_win") for m in retry.saved_lost(folder, rep["run"], cards).values()))


class T9SalesTryAgain(TryBase):
    def test_try_again_never_replays_a_correct_close(self):
        cards = [offer_card(1, "price", COVERED), offer_card(2, "fit", COVERED), offer_card(3, "date", CLOSE)]
        judge = CloseJudge()
        a = run.Arena(cards, agent_model=Agent(), customer_model=Shopper(()), judge_model=judge, state=self.dir,
                      calls=run.Calls(self.dir / run.CALLS_FILE, 1000), held_out=["persona-02", "persona-03"],
                      trust={"matches": 4, "wins": 3, "zero_failed_checks": True}, matches=1, now=lambda: NOW,
                      rounds=4)  # the old shape: two gated rounds with no gain make it stuck (decision 113 plays 2 by default)
        rep = a.run()
        self.assertEqual(rep["stopped"], run.STUCK)
        self.assertTrue(judge.asks)  # the close card was played and closed right
        lost = {x["card"] for x in json.loads((self.dir / rep["stuck"]["file"]).read_text(encoding="utf-8"))["lost"]}
        self.assertEqual(lost, {"persona-02"})
        self.m.try_again("sales")
        self.assertTrue(self.seen)
        self.assertTrue(all("Your worry is fit" in s for s in self.seen))  # only the lost covered customer
        self.assertFalse(any(match_mod.OFFER_LINES[1] in s for s in self.seen))


class GateRerun(Base):
    def test_a_close_win_reruns_through_the_close_judge_or_is_skipped_without_one(self):
        from engine import exam as engine_exam
        cards = [offer_card(1, "date", CLOSE), offer_card(2, "date", CLOSE)]
        a = self.arena(cards, matches=1, rounds=1, held_out=["persona-02"], trust={"matches": 1, "wins": 1})
        m, judged = a.play(a.train[0], "20261104T000000-r1-t01", training=True)
        self.assertTrue(m["close_win"])
        win = run.past_wins(self.dir)
        self.assertEqual(len(win), 1)

        def exam(text, tags):
            return engine_exam.Result(passed=True, rows=[], calls=0, pairs=[], blocked=None)

        self.assertEqual(gate.pick(win, closes=False)[1][0][1], gate.NO_CLOSE_JUDGE)
        before = len(self.judge.asks)
        g = gate.Gate(exam, wins=win, agent_model=Agent(), customer_model=Shopper(), judge_model=self.judge,
                      calls=run.Calls(self.dir / "gate-calls.json", 300, day="2026-11-04"))
        r = g("a lesson", ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual(len(self.judge.asks), before + 1)  # the rerun was judged by the close judge
        bare = gate.Gate(exam, wins=win, agent_model=Agent(), customer_model=Shopper(),
                         calls=run.Calls(self.dir / "gate-calls2.json", 300, day="2026-11-04"))
        self.assertEqual([row.why for row in bare("a lesson", ("all",)).rows if row.part == gate.SKIPPED],
                         [gate.NO_CLOSE_JUDGE])


if __name__ == "__main__":
    unittest.main()
