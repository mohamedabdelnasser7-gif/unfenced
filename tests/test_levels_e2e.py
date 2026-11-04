"""One practice run end to end at medium and at high (decisions 84 and 85, arena/practice.py practise with
study= and db=, no shape given): the level alone sets how many customers the writer makes, the fixed test
set, each test customer once a round, the round count (2 at every level, the second practice only, decision 113), the study between rounds and the call cap (the
day's UNFENCED_DAILY_CALLS setting, 3000 when not set; a high run keeps at least 1,500). The stock fixture and the three agents of tests/three_agents.json, so it holds for
any agent kind. A fake model only."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import levels, madeup, practice, run
from kit import turn
from kit.db import Db
from tests.fake_model import clean_env
from tests.test_any_agent_r2 import THREE, agent_folder
from tests.test_arena_practice import FIXTURE
from tests.test_arena_rounds import IDEA_HEAD, Exams
from tests.test_levels_study import FIRST, SECOND, Climb

SHAPE = {"medium": {"customers": 20, "test": 10, "rounds": 2, "cap": 3000, "scores": [0], "stopped": run.ROUNDS},
         "high": {"customers": 30, "test": 20, "rounds": 2, "cap": 3000, "scores": [0], "stopped": run.ROUNDS}}


class Logged(Climb):
    """Climb that writes each study into the run's log, between the matches the spy logs."""

    def __init__(self, instructions, ideas, log):
        super().__init__(instructions, ideas)
        self.log = log

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if messages[0]["content"].startswith(IDEA_HEAD):
            self.log.append(("study", None))
        return super().chat(messages, tools, effort, max_tokens, whole)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()

    def folders(self, level):
        """The stock fixture and each of the three agents, each under its own root, at level."""
        out = {}
        stock = self.root / f"stock-{level}" / "agents" / "stock_watch"
        shutil.copytree(FIXTURE, stock)
        out["stock_watch"] = stock
        for name in THREE:
            out[name] = agent_folder(self.root / f"{name}-{level}", name)
        for folder in out.values():
            levels.write(folder, level)
        return out

    def run_it(self, folder):
        """practise with only the models, the study and the database: (report, log of (match id, card id)
        and ("study", None) in the order they happened)."""
        log = []
        world = Logged((folder / "instructions.md").read_text(encoding="utf-8"), [[FIRST], [SECOND]], log)
        db = Db(str(folder.parent.parent / "ascent.db"))
        self.addCleanup(db.close)
        real = practice.Practice.play

        def spy(arena, card, match_id, **kw):
            log.append((match_id, card["id"]))
            return real(arena, card, match_id, **kw)
        study = {"study": world, "open": world, "exam": world, "examiner": Exams()}
        with mock.patch.object(practice.Practice, "play", spy):
            rep = practice.practise(folder, agent_model=world, customer_model=world, judge_model=world, study=study,
                                    db=db)
        return rep, log

    @staticmethod
    def rounds_of(log):
        """[{"t": [card ids], "g": [card ids]}] a round, and the index in log where each round starts."""
        out, starts = {}, {}
        for i, (mid, cid) in enumerate(log):
            if mid == "study":
                continue
            r, k = mid.rsplit("-", 2)[-2:]
            starts.setdefault(r, i)
            out.setdefault(r, {"t": [], "g": []})[k[0]].append(cid)
        order = sorted(out, key=lambda r: int(r[1:]))
        return [out[r] for r in order], [starts[r] for r in order]

    def check(self, level):
        want = SHAPE[level]
        for name, folder in self.folders(level).items():
            with self.subTest(level=level, agent=name):
                rep, log = self.run_it(folder)
                cards = madeup.read(folder / madeup.FOLDER, name, turn.load(folder).card)
                self.assertEqual(len(cards), want["customers"])  # every one a different person
                self.assertEqual(len({madeup.person(c) for c in cards}), want["customers"])
                test, train = set(rep["held_out_cards"]), set(rep["training_cards"])
                self.assertEqual((len(test), len(train)), (want["test"], want["customers"] - want["test"]))
                self.assertFalse(test & train)
                self.assertEqual(rep["held_out_cards"], practice.test_set(cards, want["test"]))  # the fixed set
                self.assertEqual((rep["trust"]["level"], rep["trust"]["matches"]), (level, want["test"]))
                played, starts = self.rounds_of(log)
                self.assertEqual((len(rep["rounds"]), len(played)), (want["rounds"], want["rounds"]))
                for r, one in enumerate(played, 1):
                    if r == want["rounds"]:  # the last round plays practice only, no gate (decision 113)
                        self.assertEqual(one["g"], [], f"round {r}: no gate")
                        self.assertTrue(rep["rounds"][r - 1].get("practice_only"))
                    else:
                        self.assertEqual(sorted(one["g"]), sorted(test), f"round {r}: each test customer once")
                    self.assertEqual(sorted(one["t"]), sorted(train), f"round {r}: each practice customer once")
                studies = [i for i, (mid, _) in enumerate(log) if mid == "study"]
                self.assertEqual(len(studies), want["rounds"] - 1)  # one study between each two rounds
                for i, at in enumerate(studies):
                    self.assertTrue(starts[i] < at < starts[i + 1], f"study {i + 1} sits between rounds")
                self.assertTrue(all(isinstance(r.get("reflection"), dict) for r in rep["rounds"][:-1]))
                self.assertEqual(rep["calls"]["cap"], want["cap"])
                self.assertLessEqual(rep["calls"]["used"], want["cap"])
                if name == "stock_watch":  # the fixture's fake agent climbs the same way every run
                    self.assertEqual(([r["gate"]["won"] for r in rep["rounds"] if not r.get("practice_only")],
                                      rep["stopped"]),
                                     (want["scores"], want["stopped"]))
        self.assertEqual(run.DEFAULT_CAP, 3000)  # the high floor is set per run, never by the default

    def test_medium_twenty_customers_ten_test_two_rounds_days_cap(self):
        self.check("medium")

    def test_high_thirty_customers_twenty_test_two_rounds_days_cap(self):
        self.check("high")


if __name__ == "__main__":
    unittest.main()
