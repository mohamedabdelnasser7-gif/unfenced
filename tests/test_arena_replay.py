"""The Arena replay of real lost chats (new, 2026-10-30), on fake models and on the replay set
built from the made-up chats (demo/make_arena_history.py): never a real chat, never a model call."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from arena import personas as pp, replay, run
from tests import fake_recipe
from tests.fake_model import BUY, clean_env, say
from tests.test_arena_personas import make_history
from tests.test_arena_run import Agent, Customer, card

ROOT = Path(__file__).resolve().parent.parent


def chat(i, worry, *turns, lab="lost"):
    return {"id": f"c{i:04d}", "label": lab, "why": "quiet after the price", "source": "whatsapp", "worry": worry,
            "turns": [dict(t, min=n) for n, t in enumerate(turns)]}


def cust(text=None, media=None):
    t = {"from": "customer"}
    if text is not None:
        t["text"] = text
    if media is not None:
        t["media"] = media
    return t


STORE = {"from": "store", "text": "16,500 EGP."}


class Records:
    """A customer model that records every message list it is given. Given BUY, it answers an order
    summary with a plain yes, as a buying customer does under the strict win rule."""
    def __init__(self, line):
        self.line, self.seen = line, []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.seen.append(messages)
        summary = "Confirm?" in (messages[-1].get("content") or "")
        return say("yes" if self.line == BUY and summary else self.line)


class Plan(unittest.TestCase):
    def test_opening_is_the_customer_words_before_the_store_reply(self):
        e = chat(1, "size", cust("Hi"), cust(media="<photo>"), cust("  size 44?  "), STORE, cust("ok"))
        self.assertEqual(replay.opening(e), "Hi\nsize 44?")
        self.assertEqual(replay.opening(chat(2, "size", STORE, cust("hi"))), "")
        self.assertEqual(replay.opening(chat(3, "size", cust(media="<voice>"), STORE)), "")

    def test_persona_by_worry_a_buyer_first(self):
        cards = [dict(card(1, "price", 0.9), unwinnable=True), card(2, "price", 0.2), card(3, "price", 0.5),
                 dict(card(4, "just browsing"), unwinnable=True)]
        self.assertEqual(replay.persona(chat(1, "price"), cards)[0]["id"], "persona-03")
        self.assertEqual(replay.persona(chat(1, "just browsing"), cards), (None, replay.WILL_NOT_BUY))
        self.assertEqual(replay.persona(chat(1, "trust"), cards), (None, replay.NO_CARD))
        self.assertEqual(replay.persona(chat(1, None), cards), (None, replay.NO_WORRY))

    def test_plan_plays_lost_chats_only_and_skips_never_guesses(self):
        cards = [card(1, "size"), dict(card(2, "just browsing"), unwinnable=True)]
        entries = [chat(1, "size", cust("size 44?"), STORE),
                   chat(2, "size", cust("I'll take it"), STORE, lab="won"),
                   chat(3, "size", STORE, cust("hello")),
                   chat(4, "just browsing", cust("hi"), STORE),
                   chat(5, None, cust("hi"), STORE),
                   chat(6, "trust", cust("hi"), STORE)]
        ready, skipped = replay.plan(entries, cards)
        self.assertEqual([(e["id"], c["id"], first) for e, c, first in ready], [("c0001", "persona-01", "size 44?")])
        self.assertEqual(skipped, {replay.NO_OPENING: 1, replay.WILL_NOT_BUY: 1, replay.NO_WORRY: 1, replay.NO_CARD: 1})
        unlabelled = {k: v for k, v in chat(8, "size", cust("hi"), STORE).items() if k != "label"}
        self.assertEqual(replay.plan([chat(7, "size", cust("size 44?"), STORE, lab="unclear"), unlabelled], cards),
                         ([], {}))  # review round 1, finding 10: only a chat labelled lost is played, never a guess
        many = [chat(i, "size", cust(f"line {i}"), STORE) for i in range(1, 21)]
        self.assertEqual([e["id"] for e, _, _ in replay.plan(many, cards, most=4)[0]],
                         ["c0001", "c0006", "c0011", "c0016"])

    def test_load_refuses_the_repo_and_bad_lines(self):
        with self.assertRaises(replay.Refused):
            replay.load(ROOT / "demo" / "personas" / "summary.json")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "replay.jsonl"
            p.write_text(json.dumps(chat(1, "size", cust("hi"), STORE)) + "\n\n", encoding="utf-8")
            self.assertEqual([e["id"] for e in replay.load(p)], ["c0001"])
            p.write_text("{\n", encoding="utf-8")
            with self.assertRaises(replay.Refused):
                replay.load(p)
            p.write_text(json.dumps({"id": "c1"}) + "\n", encoding="utf-8")
            with self.assertRaises(replay.Refused):
                replay.load(p)


class Play(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def arena(self, customer, cap=300, learn=None):
        self.calls = run.Calls(self.dir / run.CALLS_FILE, cap, day="2026-10-30")
        self.agent = Agent()
        return run.Arena([card(1, "size"), card(2, "size")], agent_model=self.agent, customer_model=customer,
                         calls=self.calls, state=self.dir, learn=learn, now=lambda: 1_790_000_000.0)

    def test_the_agent_answers_the_real_opening_and_the_persona_goes_on(self):
        customer = Records(BUY)
        planned = [(chat(7, "size", cust("Hi"), cust("size 44 in Elite?"), STORE), card(1, "size"), "Hi\nsize 44 in Elite?")]
        out = self.arena(customer).replay(planned, {replay.NO_CARD: 2})
        self.assertEqual((out["played"], out["won"], out["lost"], out["skipped"], out["stopped"]),
                         (1, 1, [], {replay.NO_CARD: 2}, None))
        self.assertEqual([m["content"] for m in customer.seen[0][2:4]],
                         ["Hi\nsize 44 in Elite?", "The Mercurial Vapor 17 Elite is 16,500 EGP."])  # it goes on from the real opening
        saved = [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(m["replay"], m["won"], m["turns"][0]["customer"]) for m in saved],
                         [("c0007", True, "Hi\nsize 44 in Elite?")])
        self.assertTrue(saved[0]["id"].endswith("-replay-c0007"))
        self.assertEqual(self.calls.count, 6 + 2)  # price, stage, draft, summary, confirm, placed; buy and yes

    def test_a_lost_replay_quotes_the_turn_and_becomes_a_case(self):
        cases = []
        planned = [(chat(i, "size", cust(f"hi {i}"), STORE), card(1, "size"), f"hi {i}") for i in (1, 2)]
        out = self.arena(Records("[leave]"), learn=lambda m, j, mid: cases.append(mid) or mid).replay(planned)
        self.assertEqual((out["played"], out["won"]), (2, 0))
        self.assertEqual(out["lost"][0]["chat"], "c0001")
        self.assertEqual(out["lost"][0]["quote"]["text"], "The Mercurial Vapor 17 Elite is 16,500 EGP.")
        self.assertEqual(len(cases), 2)
        self.assertEqual(out["cases"], cases)

    def test_a_model_error_stops_the_replay_and_is_no_loss(self):
        """Review round 1, note 13: the customer's model not answering voids that replay, never a loss."""
        from kit.model import ModelError

        class Breaks:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                raise ModelError("the route is busy")

        cases = []
        planned = [(chat(i, "size", cust(f"hi {i}"), STORE), card(1, "size"), f"hi {i}") for i in (1, 2)]
        a = self.arena(Breaks(), learn=lambda m, j, mid: cases.append(mid) or mid)
        out = a.replay(planned)
        self.assertEqual((out["played"], out["lost"], out["stopped"], out["error"]),
                         (0, [], run.MODEL_ERROR, "the route is busy"))
        self.assertEqual(cases, [])
        self.assertFalse((self.dir / run.MATCHES_FILE).exists())
        rep = dict(a._report([], run.PASSED), replay=out)
        self.assertIn("; stopped by a model error: the route is busy", run.text(rep))

    def test_the_cap_stops_the_replay(self):
        planned = [(chat(i, "size", cust(f"hi {i}"), STORE), card(1, "size"), f"hi {i}") for i in (1, 2, 3)]
        out = self.arena(Records("[leave]"), cap=3).replay(planned)
        self.assertEqual((out["played"], out["stopped"]), (1, run.CAP))
        self.assertEqual(self.calls.count, 3)


class Cli(unittest.TestCase):
    """The replay set built from the made-up chats, the way the demo builds it."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        make_history(tmp / "hist")
        cls.out = tmp / "personas"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = pp.main(["--source", str(tmp / "hist"), "--out", str(cls.out), "--scripted", "--recipe",
                            str(fake_recipe.write(tmp))])
        assert code == 0
        cls.entries = replay.load(cls.out / "replay.jsonl")
        cls.cards = run.load_cards(cls.out / "cards")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def main(self, *args, customer=None):
        o, e = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            code = run.main(["--cards", str(self.out / "cards"), "--matches", "1", "--rounds", "1",
                             "--state", str(self.dir), *args], agent_model=Agent(),
                            customer_model=customer or Customer(buyers={c["worry"] for c in self.cards}))
        return code, o.getvalue(), e.getvalue()

    def test_replays_the_demo_lost_chats_after_the_gate(self):
        ready, skipped = replay.plan(self.entries, self.cards, 4)
        self.assertEqual(len(ready), 4)
        code, out, err = self.main("--replay", str(self.out / "replay.jsonl"), "--replay-max", "4", "--json")
        self.assertEqual(code, 0, err)
        rp = json.loads(out)["replay"]
        self.assertEqual((rp["played"], rp["won"], rp["skipped"]), (4, 2, skipped))
        # the two Arabic openings get the fake agent's English line, and the real Sales agent loop hands
        # them to a person: judged by the same verdict as every match
        self.assertEqual([(x["chat"], x["why"]) for x in rp["lost"]], [("c0006", "the chat went to a person"),
                                                                       ("c0013", "the chat went to a person")])
        self.assertEqual([e["id"] for e, _, first in ready if any("\u0600" <= ch <= "\u06ff" for ch in first)],
                         ["c0006", "c0013"])  # the two Arabic openings in the plan
        saved = [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        replays = [m for m in saved if "replay" in m]
        self.assertEqual([(m["replay"], m["card"], m["turns"][0]["customer"]) for m in replays],
                         [(e["id"], c["id"], first) for e, c, first in ready])
        for e, _, first in ready:
            self.assertEqual(e["label"], "lost")
            self.assertTrue(first)
        self.assertEqual(json.loads(out)["calls"]["used"],
                         json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"])
        code, out, _ = self.main("--replay", str(self.out / "replay.jsonl"), "--replay-max", "1")
        self.assertIn("replay of real lost chats: 1 of 1 won, 0 cases to Reflection; skipped: its card will not buy 3", out)

    def test_the_cleaned_set_is_taken_end_to_end_and_a_second_one_in_the_repo_is_not(self):
        """Review round 1, finding 6: REAL_REPLAY pointed at a made-up file in the repo, through a link
        outside it, so only the same file by device and inode is taken, never one by its name."""
        from unittest import mock
        crowd = ROOT / "demo" / "crowd.jsonl"
        link = self.dir / "cleaned.jsonl"
        link.symlink_to(crowd)
        with mock.patch.object(replay, "REAL_REPLAY", link):
            self.assertEqual(len(replay.load(crowd)), sum(1 for x in crowd.read_text(encoding="utf-8").splitlines()
                                                           if x.strip()))
            code, out, err = self.main("--replay", str(crowd), "--json")
            self.assertNotIn("inside the repo", err)
            self.assertEqual(code, 0, err)
            self.assertIn("replay", json.loads(out))
            with self.assertRaises(replay.Refused):
                replay.load(ROOT / "demo" / "personas" / "summary.json")
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-replay-") as d:
            second = Path(d) / "replay.jsonl"  # the same name, in the repo, not the cleaned set
            second.write_bytes((self.out / "replay.jsonl").read_bytes())
            for patched in (None, link):
                with self.subTest(real_replay=patched), \
                        mock.patch.object(replay, "REAL_REPLAY", patched or replay.REAL_REPLAY):
                    with self.assertRaises(replay.Refused):
                        replay.load(second)
                    code, _, err = self.main("--replay", str(second))
                    self.assertEqual(code, 2)
                    self.assertIn("inside the repo", err)

    def test_no_replay_before_the_gate_passes(self):
        code, out, _ = self.main("--replay", str(self.out / "replay.jsonl"), customer=Customer(buyers=()))
        self.assertEqual(code, 1)
        self.assertIn("replay not run: the persona gate has not passed", out)
        saved = (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8")
        self.assertNotIn('"replay"', saved)

    def test_the_cleaned_set_is_the_one_repo_file_taken(self):
        self.assertEqual(replay.REAL_REPLAY, ROOT / "arena" / "real" / "replay.jsonl")
        self.assertTrue(replay._is_real_replay(replay.REAL_REPLAY.resolve()))  # a stat, never a read
        self.assertFalse(replay._is_real_replay((ROOT / "demo" / "crowd.jsonl").resolve()))
        self.assertFalse(replay._is_real_replay((ROOT / "arena" / "real" / "summary.json").resolve()))

    def test_refuses_a_replay_set_in_the_repo_before_any_call(self):
        for given in (ROOT / "demo" / "crowd.jsonl", Path(str(ROOT / "demo" / "crowd.jsonl").swapcase())):
            code, _, err = self.main("--replay", str(given))
            self.assertEqual(code, 2)
            self.assertIn("inside the repo", err)
        self.assertFalse((self.dir / run.CALLS_FILE).exists())
        big = self.dir / "big.jsonl"
        with open(big, "wb") as f:
            f.truncate(replay.MAX_BYTES + 1)
        deep = self.dir / "deep.jsonl"
        deep.write_text("[" * 200000 + "]" * 200000 + "\n", encoding="utf-8")
        for path, said in ((big, "over"), (deep, "not JSON"), (self.dir, "not a regular file")):
            code, _, err = self.main("--replay", str(path))
            self.assertEqual(code, 2)
            self.assertIn(said, err)
        code, _, err = self.main("--replay", str(self.out / "replay.jsonl"), "--replay-max", "0")
        self.assertEqual(code, 2)

    def test_the_repo_check_ignores_the_unicode_form(self):
        from arena import paths
        decomposed, composed = self.dir / "café", self.dir / "café" / "state"
        self.assertTrue(paths.within(composed, decomposed))
        self.assertTrue(paths.within(self.dir / "café" / "state", self.dir / "café"))

    def test_a_second_name_for_the_repo_folder_is_inside(self):
        """Review round 2, finding 4: /System/Volumes/Data/<repo> on macOS is the same folder by another name."""
        from arena import paths
        firm = Path("/System/Volumes/Data" + str(ROOT))
        if not firm.is_dir():
            self.skipTest("no /System/Volumes/Data name on this machine")
        for p in (firm / "recipe.json", firm / "demo" / "crowd.jsonl", firm / "new-folder" / "state"):
            self.assertTrue(paths.inside_repo(p), p)
        self.assertFalse(paths.inside_repo(self.dir / "state"))


if __name__ == "__main__":
    unittest.main()
