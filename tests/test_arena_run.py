"""Arena loop, gate, cap, trust file and lost matches to Reflection (new, 2026-10-30), on fake models."""
import contextlib
import fnmatch
import io
import json
import os
import random
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import learn, match as match_mod, paths, run
from engine.log import Log, is_history
from engine.study import BAD, settle
from kit.db import Db
from reflection import PLUG
from tests.fake_model import BUY, Seller, clean_env, say

REPO = Path(run.__file__).resolve().parent.parent
HISTORY = REPO / "demo" / "history"
TEXT = {".py", ".md", ".json", ".jsonl", ".txt", ".html", ".toml", ".cfg", ".yml", ".yaml", ""}
STAND_IN = 4  # the stand-in count of matches a test or an example level uses


def card(i, worry, weight=0.5):
    return {"id": f"persona-{i:02d}", "worry": worry, "unwinnable": False, "want": ["boots"],
            "buy_trigger": ["a clear answer"], "patience": {"median": 1, "most": 1}, "examples": [],
            "style": {"language": {"english": 1.0}, "length": {"short": 1.0}, "opening": {"price": 1.0}},
            "arena_weight": weight}


class Agent(Seller):
    """Always gives the right price, and places the order on a buying line and a yes (fake_model.Seller)."""


class Customer:
    """Buys when its worry is in buyers (BUY, then yes to the summary), else leaves after its first line."""
    def __init__(self, buyers=("size",)):
        self.buyers, self.calls = set(buyers), 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls += 1
        worry = messages[0]["content"].split("Your worry is ")[1].split(".")[0]
        if len(messages) == 2:
            return say("How much is the Mercurial Vapor 17 Elite?")
        if worry not in self.buyers:
            return say("[leave]")
        return say("yes" if "Confirm?" in (messages[-1]["content"] or "") else BUY)


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def arena(self, cards, customer, **kw):
        kw.setdefault("calls", run.Calls(self.dir / "calls.json", kw.pop("cap", 300), day="2026-10-30"))
        return run.Arena(cards, agent_model=Agent(), customer_model=customer, state=self.dir,
                         trust={"matches": 4, "wins": 3, "zero_failed_checks": True}, now=lambda: 1_790_000_000.0, **kw)


class Loop(Base):
    def test_passes_on_held_out_wins_and_stops(self):
        cards = [card(1, "size"), card(2, "size"), card(3, "size")]
        rep = self.arena(cards, Customer(), matches=2, held_out=["persona-03"]).run()
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual(rep["held_out_cards"], ["persona-03"])
        self.assertEqual(len(rep["rounds"]), 1)
        self.assertEqual(rep["rounds"][0]["gate"], {"played": 4, "won": 4, "lost": []})
        self.assertEqual(len(run.past_wins(self.dir)), 6)

    def test_stuck_after_two_rounds_with_no_gain_writes_the_morning_item(self):
        cases = []
        cards = [card(1, "price"), card(2, "price")]
        a = self.arena(cards, Customer(), matches=2, held_out=["persona-02"],
                       learn=lambda m, j, mid: cases.append(m["card"]) or mid)
        rep = a.run()
        self.assertEqual(rep["stopped"], run.STUCK)
        self.assertEqual(len(rep["rounds"]), 3)
        self.assertEqual(cases, ["persona-01"] * 6)  # training losses only; held-out losses go nowhere
        item = json.loads((self.dir / rep["stuck"]["file"]).read_text(encoding="utf-8"))
        self.assertEqual(item["kind"], "arena_stuck")
        self.assertIn("0 of 4 gate matches won after 3 rounds", item["line"])
        self.assertEqual(item["lost"][0]["quote"]["text"], "The Mercurial Vapor 17 Elite is 16,500 EGP.")

    def test_between_runs_before_each_later_round(self):
        seen = []
        self.arena([card(1, "price"), card(2, "price")], Customer(), matches=1, held_out=["persona-02"],
                   between=seen.append).run()
        self.assertEqual(seen, [1, 2])

    def test_cap_stops_and_the_count_is_saved(self):
        rep = self.arena([card(1, "size"), card(2, "size")], Customer(), matches=5, cap=7).run()
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(rep["calls"]["used"], 7)
        again = run.Calls(self.dir / "calls.json", 7, day="2026-10-30")
        self.assertEqual(again.count, 7)
        with self.assertRaises(run.CapReached):
            again.take()
        self.assertEqual(run.Calls(self.dir / "calls.json", 7, day="2026-10-31").count, 0)

    def test_two_runs_across_cairo_midnight_share_one_cap(self):
        """Review round 2, finding 3: the day is read at each call, not once when the counter is built."""
        path = self.dir / "midnight.json"
        with mock.patch.object(run, "today", return_value="2026-10-30"):
            old = run.Calls(path, 5)
        with mock.patch.object(run, "today", return_value="2026-10-31"):
            new = run.Calls(path, 5)
            for _ in range(5):
                (old if _ % 2 else new).take()
            for c in (old, new):
                with self.assertRaises(run.CapReached):
                    c.take()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["calls"], 5)

    def test_a_model_error_stops_the_run_and_its_match_is_dropped(self):
        """Review round 1, note 13: a model that does not answer is no loss and no case; the run stops
        there as at the cap, and the report names the error."""
        from kit.model import ModelError

        class Breaks(Customer):
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                if "Your worry is fit" in messages[0]["content"]:
                    raise ModelError("the route is busy")
                return super().chat(messages, tools, effort, max_tokens, whole)

        cases = []
        rep = self.arena([card(1, "size"), card(2, "fit")], Breaks(), matches=2, held_out=["persona-02"],
                         learn=lambda m, j, mid: cases.append(mid) or mid).run()
        self.assertEqual((rep["stopped"], rep["error"]), (run.MODEL_ERROR, "the route is busy"))
        self.assertEqual((rep["rounds"][0]["training"]["played"], rep["rounds"][0]["gate"]),
                         (2, {"played": 0, "won": 0, "lost": []}))
        saved = (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(saved), 2)  # the two training wins; the void match is not kept
        self.assertIn("  stopped by a model error: the route is busy; that match was dropped, not counted as lost",
                      run.text(rep))

        class Silent:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                raise ModelError("no answer")

        rep = run.Arena([card(1, "price"), card(2, "price")], agent_model=Silent(), customer_model=Customer(),
                        calls=run.Calls(self.dir / "two.json", 300, day="2026-10-30"), state=self.dir / "two",
                        held_out=["persona-02"], learn=lambda m, j, mid: cases.append(mid) or mid,
                        now=lambda: 1_790_000_000.0).run()
        self.assertEqual((rep["stopped"], rep["error"], rep["rounds"][0]["training"]), (
            run.MODEL_ERROR, match_mod.AGENT_SILENT, {"played": 0, "won": 0, "cases": []}))
        self.assertEqual(cases, [])
        self.assertFalse((self.dir / "two" / run.MATCHES_FILE).exists())

    def test_the_gate_passes_at_the_level_wins_and_not_one_below(self):
        """Review round 1, finding 10: with a level of 3 wins in 4, 2 gate wins do not pass and 3 do."""

        class Schedule(Customer):
            """Buys in the matches whose numbers are given (counted by their first lines), else leaves."""
            def __init__(self, buys):
                super().__init__()
                self.buys, self.match = set(buys), 0

            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                if len(messages) == 2:
                    self.match += 1
                    return say("How much is the Mercurial Vapor 17 Elite?")
                if self.match not in self.buys:
                    return say("[leave]")
                return say("yes" if "Confirm?" in (messages[-1]["content"] or "") else BUY)

        cards = [card(1, "size"), card(2, "size")]
        for buys, gate_won, stopped in (({1, 2, 3}, 2, run.ROUNDS), ({1, 2, 3, 4}, 3, run.PASSED)):
            with self.subTest(buys=buys):
                rep = self.arena(cards, Schedule(buys), matches=1, rounds=1, held_out=["persona-02"],
                                 calls=run.Calls(self.dir / f"calls-{len(buys)}.json", 300, day="2026-10-30")).run()
                self.assertEqual((rep["rounds"][0]["gate"]["won"], rep["rounds"][0]["gate"]["played"]), (gate_won, 4))
                self.assertEqual(rep["stopped"], stopped)

    def test_a_count_file_that_cannot_be_read_counts_as_the_cap(self):
        """Review round 1, note 16: a count file that is there but unreadable or of the wrong shape
        never starts the day at 0; it counts as the cap reached and says why, and it is left as it is."""
        path, day = self.dir / run.CALLS_FILE, "2026-10-30"
        bad = ["{", "[]", json.dumps({"calls": 3}), json.dumps({"day": day, "calls": "3"}),
               json.dumps({"day": day, "calls": -1}), json.dumps({"day": day, "calls": True}),
               json.dumps({"day": day, "calls": 2.5})]
        for text in bad:
            path.write_text(text, encoding="utf-8")
            c = run.Calls(path, 5, day=day)
            self.assertTrue(c.problem, text)
            self.assertEqual(c.count, 5)
            with self.assertRaises(run.CapReached) as caught:
                c.take()
            self.assertIn(f"{run.CALLS_FILE} ", str(caught.exception))
            self.assertIn("counts as the cap reached until it is fixed or removed", str(caught.exception))
            self.assertEqual((c.reached, c.taken, path.read_text(encoding="utf-8")), (True, 0, text))
        path.unlink()
        path.mkdir()
        self.assertEqual(run.Calls(path, 5, day=day).problem, f"the call count file {run.CALLS_FILE} cannot be opened")
        path.rmdir()
        for text, count in ((None, 0), (json.dumps({"day": "2026-10-29", "calls": 9}), 0),
                            (json.dumps({"day": day, "calls": 2}), 2)):
            if text is not None:
                path.write_text(text, encoding="utf-8")
            c = run.Calls(path, 5, day=day)
            self.assertEqual((c.problem, c.count), (None, count))
            c.take()
            self.assertEqual(run.Calls(path, 5, day=day).count, count + 1)
        state = self.dir / "state"
        state.mkdir()
        (state / run.CALLS_FILE).write_text("{", encoding="utf-8")
        agent = Agent()
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = run.main(["--matches", "1", "--rounds", "1", "--state", str(state)], agent_model=agent,
                            customer_model=Customer())
        self.assertEqual((code, agent.calls), (1, []))
        self.assertIn(f"stopped, {run.CAP}.", printed.getvalue())
        self.assertIn(f"  the call count file {run.CALLS_FILE} is not a count the Arena wrote; it counts as the cap "
                      "reached until it is fixed or removed", printed.getvalue())


class Parts(Base):
    def test_split_and_draw(self):
        cards = [card(1, "a", 0.0), card(2, "b", 1.0), card(3, "c", 0.2)]
        train, held = run.split(cards, ["persona-03"])
        self.assertEqual([c["id"] for c in train], ["persona-01", "persona-02"])
        rng = random.Random(1)
        self.assertEqual({run.draw(train, rng)["id"] for _ in range(50)}, {"persona-02"})
        train, held = run.split(cards, seed=4)
        self.assertEqual(len(held), 1)
        with self.assertRaises(run.Refused):
            run.split(cards, ["persona-09"])

    def test_a_deep_saved_match_is_skipped_by_past_wins(self):
        # review wireall r2 item 7: the parser's RecursionError is made here for one marker line
        deep, loads = "[[[deep]]]", json.loads
        won = json.dumps({"won": True, "turns": [{"who": "customer", "text": "hi"}]})

        def parse(text, *a, **k):
            if text == deep:
                raise RecursionError("maximum recursion depth exceeded")
            return loads(text, *a, **k)
        (self.dir / run.MATCHES_FILE).write_text(deep + "\n" + won + "\n", encoding="utf-8")
        with mock.patch("json.loads", side_effect=parse):
            self.assertEqual(run.past_wins(self.dir), [loads(won)])

    def test_trust_file(self):
        p = self.dir / "trust.json"
        p.write_text(json.dumps({"sales": {"matches": 4, "wins": 3}}), encoding="utf-8")  # stand-in numbers
        self.assertEqual(run.load_trust(p), {"matches": 4, "wins": 3, "zero_failed_checks": True})
        self.assertEqual(run.load_trust(None), run.PUBLIC_TRUST)
        with self.assertRaises(run.Refused):
            run.load_trust(Path(run.__file__))
        for level in ({"matches": True, "wins": True}, {"matches": 4, "wins": True}, [4, 3], "4 of 3",
                      {"matches": 4, "wins": 0}):  # a level of no wins would pass every gate
            p.write_text(json.dumps({"sales": level}), encoding="utf-8")  # review round 1, note 15
            with self.assertRaises(run.Refused, msg=level):
                run.load_trust(p)

    def test_no_real_trust_level_in_the_repo(self):
        """Trust levels stay out of the public repo (DECISIONS item 17): a level written in any file
        here is the placeholder (every match won), the public Sales level of 7 of 10 (DECISIONS item 63)
        or uses the stand-in count of STAND_IN matches."""
        PUBLIC = (10, 7)  # the one level the README names (DECISIONS item 63)
        self.assertEqual((run.PUBLIC_TRUST["matches"], run.PUBLIC_TRUST["wins"]), PUBLIC)
        found = []
        level = re.compile(r"""["']matches["']\s*:\s*(\d+)\s*,\s*["']wins["']\s*:\s*(\d+)""")
        seen = 0
        for folder, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in (".git", "data", "__pycache__")
                       and Path(folder, d) != REPO / "arena" / "real"]  # tests never read arena/real/
            for name in files:
                path = Path(folder) / name
                if path.suffix not in TEXT or name == ".git":
                    continue
                seen += 1
                for m, w in level.findall(path.read_text(encoding="utf-8", errors="replace")):
                    if int(m) != int(w) and int(m) != STAND_IN and (int(m), int(w)) != PUBLIC:
                        found.append(f"{path.relative_to(REPO)}: {m} matches, {w} wins")
        self.assertGreater(seen, 100)
        self.assertEqual(found, [])

    def test_cli_on_the_demo_cards(self):
        out = self.dir / "state"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = run.main(["--matches", "1", "--rounds", "1", "--state", str(out), "--json"],
                            agent_model=Agent(), customer_model=Customer(buyers=()))
        self.assertEqual(code, 1)
        rep = json.loads(printed.getvalue())
        self.assertEqual(rep["stopped"], run.ROUNDS)
        self.assertEqual(rep["calls"]["cap"], 1000)  # the default a day, raised from 300 (DECISIONS item 33)
        self.assertTrue((out / run.CALLS_FILE).is_file())

    def test_cli_keeps_the_arena_files_next_to_the_database(self):
        folder = self.dir / "agent"
        folder.mkdir()
        db = folder / "ascent.db"
        Db(str(db)).close()
        with contextlib.redirect_stdout(io.StringIO()):
            code = run.main(["--matches", "1", "--rounds", "1", "--db", str(db), "--json"], agent_model=Agent(),
                            customer_model=Customer(buyers={c["worry"] for c in run.load_cards(run.DEMO_CARDS)}))
        self.assertEqual(code, 0)
        names = sorted(p.name for p in folder.iterdir() if p.name.startswith("arena-"))
        items = [n for n in names if n.startswith("arena-sales-")]  # a pass writes its Morning item too
        self.assertEqual(len(items), 1)
        self.assertIs(json.loads((folder / items[0]).read_text(encoding="utf-8"))["quick"], False)
        self.assertEqual([n for n in names if n not in items],
                         [run.CALLS_FILE, "arena-calls.lock", run.MATCHES_FILE, run.seal.KEY_FILE])
        ignored = (REPO / ".gitignore").read_text(encoding="utf-8").split()
        for name in names + [run.CALLS_FILE + ".tmp", run.seal.KEY_FILE + ".1.ab"]:  # temp files a crash could leave
            self.assertTrue(any(fnmatch.fnmatchcase(name, pat) for pat in ignored), name)
        self.assertTrue(run.past_wins(run.state_dir(db)))
        for argv in ([], ["--db", str(db), "--state", str(self.dir)]):  # neither, or both
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(run.main(["--matches", "1"] + argv, agent_model=Agent(), customer_model=Customer()), 2)
            self.assertIn("Not run:", err.getvalue())

    def test_a_quick_run_marks_its_item_quick(self):
        """Review simplify round 1, finding 1: the page never unlocks Connect on a quick run's item."""
        folder = self.dir / "quick"
        folder.mkdir()
        db = folder / "ascent.db"
        Db(str(db)).close()
        with contextlib.redirect_stdout(io.StringIO()):
            run.main(["--quick", "--db", str(db), "--json"], agent_model=Agent(),
                     customer_model=Customer(buyers={c["worry"] for c in run.load_cards(run.DEMO_CARDS)}))
        items = [p for p in folder.iterdir() if p.name.startswith("arena-sales-")]
        self.assertEqual(len(items), 1)
        for p in items:
            self.assertIs(json.loads(p.read_text(encoding="utf-8")).get("quick"), True)

    def test_cli_hands_the_agent_its_kept_lessons(self):
        """Review round 1, finding 7: with --db the agent plays with its kept lessons, as the exam
        hands them, so the go-live gate does not test the bare seed."""
        from reflection.lessons import Lessons as SalesLessons
        from tests.kept import kept_lesson
        lesson = "Say the price and the delivery fee together."
        db = self.dir / "ascent.db"
        d = Db(str(db))
        kept_lesson(SalesLessons(d), lesson, ["all"])
        d.close()

        class Seen(Agent):
            def __init__(self):
                super().__init__()
                self.systems = []

            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                self.systems.append(messages[0]["content"])
                return super().chat(messages, tools, effort, max_tokens, whole)

        agent = Seen()
        with contextlib.redirect_stdout(io.StringIO()):
            run.main(["--matches", "1", "--rounds", "1", "--db", str(db), "--json"], agent_model=agent,
                     customer_model=Customer(buyers={c["worry"] for c in run.load_cards(run.DEMO_CARDS)}))
        self.assertTrue(agent.systems)
        self.assertTrue(all(lesson in s for s in agent.systems), agent.systems[0])

    def test_each_match_keeps_its_customer_prompt_fingerprint_and_file(self):
        """Review round 1, finding 6: each saved match names the customer prompt it was played with
        (its fingerprint and the file it came from, never the prompt itself), so the eval gate can
        rerun it with the same prompt."""
        prompt = "A customer prompt for this test. Your worry is $worry."
        cards = [card(1, "size"), card(2, "fit")]
        self.arena(cards, Customer(), prompt=prompt, prompt_file=self.dir / "p.txt", held_out=["persona-02"],
                   matches=1, rounds=1).run()
        self.arena(cards, Customer(), held_out=["persona-02"], matches=1, rounds=1).run()
        saved = [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(saved), 10)  # each run: one training match, then the four of the gate
        self.assertEqual([(m["prompt_sha"], m["prompt_file"]) for m in saved],
                         [(match_mod.prompt_sha(prompt), str(self.dir / "p.txt"))] * 5 + [(match_mod.GENERIC_SHA, None)] * 5)
        self.assertTrue(all(prompt not in json.dumps(m) for m in saved))
        by_id = {c["id"]: c for c in cards}  # the gate reruns a win against the card it was played with
        # the gate's copy carries its real share of chats as its weight (decision 101); the card is the same
        bare = lambda c: {k: v for k, v in c.items() if k != "arena_weight"}  # noqa: E731
        self.assertEqual([bare(m["persona"]) for m in saved], [bare(by_id[m["card"]]) for m in saved])

    def test_cli_refuses_a_database_that_is_not_there(self):
        """Review round 1, finding 10: --db names the agent's database; a path with no file is
        refused, and no empty database is made there."""
        missing = self.dir / "agent" / "ascent.db"
        missing.parent.mkdir()
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = run.main(["--matches", "1", "--db", str(missing)], agent_model=Agent(), customer_model=Customer())
        self.assertEqual(code, 2)
        self.assertIn(f"Not run: no database at {missing}", err.getvalue())
        self.assertFalse(missing.exists())

    def test_refuses_arena_files_inside_the_repo_but_not_under_data(self):
        root = Path(run.__file__).resolve().parent.parent
        state = root / "arena" / "state-probe"
        for given in (state, Path(str(state).swapcase())):  # a Mac opens the folder under any case
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = run.main(["--matches", "1", "--state", str(given)], agent_model=Agent(), customer_model=Customer())
            self.assertEqual(code, 2)
            self.assertIn("inside the repo", err.getvalue())
        self.assertFalse(state.exists())
        self.assertFalse(paths.inside_repo(self.dir))
        self.assertTrue(paths.within(root / "data" / "agent", paths.DATA))
        self.assertTrue(paths.inside_repo(str(root / "x.json").swapcase()))
        self.assertFalse(paths.within(root / "data-old", paths.DATA))


class Buyer:
    """Buys after the price (BUY, then yes to the summary) unless its system prompt says it will not buy."""
    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if len(messages) == 2:
            return say("How much is the Mercurial Vapor 17 Elite?")
        if "will not buy" in messages[0]["content"]:
            return say("[leave]")
        return say("yes" if "Confirm?" in (messages[-1]["content"] or "") else BUY)


class HeldOut(Base):
    """Review round 1, finding 9: the gate never plays a card that will not buy, and the held-out
    cards are spread over worries."""

    def test_a_perfect_agent_passes_the_public_level_in_round_one_on_every_seed(self):
        cards = run.load_cards(run.DEMO_CARDS)
        self.assertTrue(any(c["unwinnable"] for c in cards))  # the demo cards hold unwinnable ones
        for seed in range(10):
            with self.subTest(seed=seed):
                state = self.dir / f"seed-{seed}"
                rep = run.Arena(cards, agent_model=Agent(), customer_model=Buyer(), state=state,
                                calls=run.Calls(state / "calls.json", 300, day="2026-10-30"),
                                trust=dict(run.PUBLIC_TRUST), matches=1, rounds=1, seed=seed,
                                now=lambda: 1_790_000_000.0).run()
                self.assertEqual(rep["stopped"], run.PASSED, rep["rounds"][0]["gate"])
                self.assertEqual(rep["item"]["kind"], "arena_rounds")  # the pass is saved, so Connect unlocks
                train, held = run.split(cards, seed=seed)
                self.assertFalse(any(c["unwinnable"] for c in held))
                self.assertEqual(len({c["worry"] for c in held}), len(held))  # one card a worry

    def test_the_held_out_share_spreads_over_worries_then_comes_round_again(self):
        cards = [card(1, "size"), card(2, "size"), card(3, "size"), card(4, "price"), card(5, "price"),
                 dict(card(6, "trust"), unwinnable=True)]
        for seed in range(10):
            train, held = run.split(cards, share=0.5, seed=seed)
            self.assertEqual(len(held), 3)
            self.assertEqual({c["worry"] for c in held}, {"size", "price"})  # both worries before a second card
            self.assertNotIn("persona-06", [c["id"] for c in held])

    def test_refused_when_no_held_out_card_can_buy(self):
        never = [dict(card(1, "price"), unwinnable=True), dict(card(2, "browsing"), unwinnable=True)]
        with self.assertRaises(run.Refused):
            run.split(never)
        mixed = [card(1, "size"), dict(card(2, "price"), unwinnable=True)]
        with self.assertRaises(run.Refused):
            run.split(mixed, ["persona-02"])
        train, held = run.split(mixed)
        self.assertEqual([c["id"] for c in held], ["persona-01"])
        a = self.arena(mixed + [card(3, "size")], Buyer(), held_out=["persona-01", "persona-02"])
        self.assertEqual([c["id"] for c in a.gate_cards], ["persona-01"])


class MorningItem(Base):
    def test_the_stuck_item_is_on_the_morning_page(self):
        from reflection import morning
        from reflection.lessons import Lessons as SalesLessons
        db = Db(":memory:")
        self.addCleanup(db.close)
        SalesLessons(db)
        page = morning.Morning(db, [PLUG], reports=self.dir)
        self.assertEqual(page.view(1_790_000_000.0)["agents"], [])  # no item, no Arena part
        rep = self.arena([card(1, "price"), card(2, "price")], Customer(), matches=1, held_out=["persona-02"]).run()
        older = dict(json.loads((self.dir / rep["stuck"]["file"]).read_text(encoding="utf-8")),
                     at=1.0, run="old", line="old line")
        (self.dir / "arena-sales-old.json").write_text(json.dumps(older), encoding="utf-8")
        (self.dir / "arena-sales-bad.json").write_text("{", encoding="utf-8")
        (self.dir / "arena-sales-x.json").write_text(json.dumps(dict(older, kind="other", run="x")), encoding="utf-8")
        view = page.view(1_790_000_000.0)
        a = [x for x in view["agents"] if x["agent"] == run.AGENT][0]
        self.assertEqual(a["arena"]["file"], rep["stuck"]["file"])  # the newest one
        self.assertIn("0 of 4 gate matches won after 3 rounds", a["arena"]["line"])
        self.assertEqual(sorted(view["problems"]), ["A saved Arena item could not be read: arena-sales-bad.json",
                                                   "A saved Arena item could not be read: arena-sales-x.json"])
        html = morning.render(view, token=None)
        self.assertIn("<h3>The Arena</h3>", html)
        self.assertIn("0 of 4 gate matches won after 3 rounds", html)
        self.assertIn("Lost persona-02:", html)
        self.assertIn('(turn 1, agent: "The Mercurial Vapor 17 Elite is 16,500 EGP.")', html)
        self.assertNotIn("old line", html)
        (self.dir / "arena-sales-old.json").write_text(json.dumps(dict(older, line="<script>x</script>", at=2e9)),
                                                         encoding="utf-8")
        html = morning.render(page.view(1_790_000_000.0), token=None)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)
        self.assertNotIn("<script>x", html)
        lost = [{"card": "<b>c</b>", "why": "<b>w</b>", "quote": {"turn": 1, "who": "agent", "text": "<b>t</b>"}}]
        (self.dir / "arena-sales-old.json").write_text(json.dumps(dict(older, lost=lost, at=2e9)), encoding="utf-8")
        html = morning.render(page.view(1_790_000_000.0), token=None)  # review round 1, finding 10: each lost field
        self.assertIn("Lost &lt;b&gt;c&lt;/b&gt;: &lt;b&gt;w&lt;/b&gt; (turn 1, agent: \"&lt;b&gt;t&lt;/b&gt;\")", html)
        self.assertNotIn("<b>", html)


class HistoryLessons(Base):
    """DECISIONS item 20: every agent starts from zero and earns its lessons in the Arena, so a
    --db holding a lesson sourced from history rows (a business's past, reflection/importer.py) is
    refused before any model call, with the lesson ids and why."""

    def setUp(self):
        super().setUp()
        import datetime
        import zoneinfo
        from reflection import importer as imp
        from reflection.lessons import Lessons as SalesLessons
        self.db = self.dir / "agent" / "ascent.db"
        now = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=zoneinfo.ZoneInfo("Africa/Cairo")).timestamp()
        imp.run(str(self.db), PLUG, whatsapp=HISTORY / "whatsapp", orders=HISTORY / "orders.csv",
                deliveries=HISTORY / "deliveries.csv", team=["Beyond the Limits"], now=now)
        self.d = Db(str(self.db))
        self.addCleanup(self.d.close)
        self.lessons = SalesLessons(self.d)
        with self.d.tx() as c:
            rows = c.execute("SELECT case_id, at FROM trace WHERE json_extract(detail, '$.history') = 1 "
                             "ORDER BY at").fetchall()
        self.assertGreater(len(rows), 50)
        self.case, self.at = rows[0]["case_id"], rows[0]["at"]
        learn.to_case(self.d, {"card": "persona-01", "worry": "price", "turns": [
            {"n": 1, "customer": "How much?", "replies": ["16,500 EGP."], "outcome": "replied", "failed": []}]},
            {"won": False, "why": "the customer left after this reply",
             "quote": {"turn": 1, "who": "agent", "text": "16,500 EGP."}}, "m1", now=now)

    def day(self, at):
        return time.strftime("%d %b %Y", time.gmtime(at))  # as engine/study.py writes a window

    def propose(self, source):
        n = len(self.lessons.mine()) + 1
        return self.lessons.propose(f"Say the delivery fee with the price, take {n}.", ["all"], source=source,
                                    sources=[])

    def cli(self):
        agent = Agent()
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = run.main(["--matches", "1", "--rounds", "1", "--db", str(self.db), "--json"], agent_model=agent,
                            customer_model=Customer(buyers={c["worry"] for c in run.load_cards(run.DEMO_CARDS)}))
        return code, err.getvalue(), agent.calls

    def test_imported_rows_and_arena_lessons_run(self):
        later = self.at + 400 * 86400  # a window that reads no imported row
        self.propose(f"night study of sales, cases from {self.day(later)} to {self.day(later + 2 * 86400)}: "
                     '"asks the size" helps; cases with it: arena-m1')
        self.propose("borrowed from marketing lesson 9")
        self.assertEqual(run.history_lessons(self.d), [])
        code, err, calls = self.cli()
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(calls)

    def test_a_lesson_naming_an_imported_case_is_refused(self):
        later = self.at + 400 * 86400
        lid = self.propose(f"night study of sales, cases from {self.day(later)} to {self.day(later + 86400)}: "
                           f'"asks the size" helps; cases with it: arena-m1, {self.case}')
        self.assertEqual(run.history_lessons(self.d), [lid])
        code, err, calls = self.cli()
        self.assertEqual((code, calls), (2, []))
        self.assertIn(f"Not run: the database at {self.db} holds 1 lesson sourced from history rows (lesson {lid}).",
                      err)
        self.assertIn("earns its lessons in the Arena (DECISIONS item 20)", err)
        self.assertFalse((self.db.parent / run.MATCHES_FILE).exists())

    def test_a_study_lesson_whose_window_read_imported_rows_is_refused_naming_none(self):
        """An idea names no case, and a pattern names only its first cases; the window it read says
        it all. A window that cannot be read counts as reading them."""
        idea = self.propose(f"night study of sales, cases from {self.day(self.at - 86400)} to {self.day(self.at)}: "
                            "an idea to try, with no past cases behind it")
        cut = self.propose("night study of sales, cases from last month: an idea to try")
        self.assertEqual(run.history_lessons(self.d), [idea, cut])
        code, err, _ = self.cli()
        self.assertEqual(code, 2)
        self.assertIn(f"holds 2 lessons sourced from history rows (lesson {idea}, {cut}).", err)

    def test_a_lesson_borrowed_from_one_carries_it(self):
        lid = self.propose(f"adapted fully from marketing cases {self.case}: the size first")
        with self.d.tx() as c:
            c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, source, source_lesson_id, "
                      "added_at) VALUES ('marketing', 'x', '[]', '[]', 'low', 'waiting', 'borrowed', ?, 1)", (lid,))
            other = c.execute("SELECT MAX(id) FROM lessons").fetchone()[0]
        self.assertEqual(run.history_lessons(self.d), [lid, other])

    def test_an_arena_case_is_not_a_history_row(self):
        self.propose("adapted fully from marketing cases arena-m1: the size first")
        self.assertEqual(run.history_lessons(self.d), [])
        empty = Db(":memory:")
        self.addCleanup(empty.close)
        self.assertEqual(run.history_lessons(empty), [])  # no tables yet


class ToReflection(Base):
    def test_a_lost_match_is_a_case_the_study_reads_as_not_good(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        m = {"card": "persona-01", "worry": "price", "turns": [
            {"n": 1, "customer": "How much?", "replies": ["16,500 EGP."], "outcome": "replied", "failed": []},
            {"n": 2, "customer": "too much", "replies": ["It is our price."], "outcome": "replied", "failed": []}]}
        judged = {"won": False, "why": "the customer left after this reply",
                  "quote": {"turn": 2, "who": "agent", "text": "It is our price."}}
        now = 1_790_000_000.0
        case = learn.to_case(db, m, judged, "x1", now=now)
        rows = Log(db, PLUG).window(now - 14 * 86400, now)[case]
        self.assertEqual([r["result"] for r in rows], ["replied", "replied", "chat_closed"])  # no timer ends it (item 66)
        self.assertEqual(rows[1]["detail"]["quote"]["text"], "It is our price.")
        self.assertEqual(rows[0]["detail"]["customer"], "How much?")
        self.assertTrue(all(is_history(r) for r in rows))
        status, deciding, _, _ = settle(PLUG, rows, now)
        self.assertEqual((status, deciding), (BAD, "chat_closed"))
        with self.assertRaises(ValueError):
            learn.to_case(db, m, {"won": True}, "x2", now=now)


if __name__ == "__main__":
    unittest.main()
