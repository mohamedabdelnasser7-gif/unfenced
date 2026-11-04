"""The Arena gate follows the real customer mix (decision 101, losses part F), on made-up cards and fake models:
each card that can buy at its real share of chats, no card group past 3 of 10 gate matches (scaled), the rest to
the next most common, every gate match a new id and seed, never a training match's; trained cards may play the
gate; a card that will not buy never does; one card group that can buy still runs, its cap relaxed with a line."""
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from arena import grow, run
from tests.fake_model import clean_env
from tests.test_arena_run import Agent, Customer, card

NOW = 1_790_000_000.0


def made_up(i, worry, chats, weight=0.5, unwinnable=False):
    return dict(card(i, worry, weight), chats=chats, unwinnable=unwinnable)


def groups(plan):
    return Counter(grow.group(c) for c in plan)


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def arena(self, cards, matches=10, **kw):
        return run.Arena(cards, agent_model=Agent(), customer_model=Customer(buyers=()), state=self.dir,
                         calls=run.Calls(self.dir / "calls.json", 2000, day="2026-11-04"),
                         trust={"matches": matches, "wins": matches, "zero_failed_checks": True},
                         now=lambda: NOW, matches=1, rounds=1, **kw)

    def saved(self):
        return [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()]


class Mix(Base):
    def test_no_card_group_plays_more_than_3_of_10_and_the_rest_go_to_the_next_most_common(self):
        cards = [made_up(1, "price", 90), made_up(2, "size", 4), made_up(3, "fit", 3), made_up(4, "delivery", 2),
                 made_up(5, "colour", 1)]
        gate = run.real_mix(cards)
        most, line = run.gate_cap(gate, 10)
        self.assertEqual((most, line), (3, ""))
        for seed in range(20):
            plan = run.gate_plan(gate, 10, random.Random(seed), most)
            self.assertEqual(len(plan), 10)
            got = groups(plan)
            self.assertLessEqual(max(got.values()), 3, got)
            self.assertEqual(got["base:price"], 3)  # the most common, at the cap
            self.assertEqual(got["base:size"], 3)  # the next most common takes the most of the rest
        most20, _ = run.gate_cap(gate, 20)
        self.assertEqual(most20, 6)  # scaled: 6 of 20
        self.assertLessEqual(max(groups(run.gate_plan(gate, 20, random.Random(1), most20)).values()), 6)

    def test_shares_follow_the_chats_never_the_loss_raised_weight(self):
        # the rare card carries a huge training weight, as a loss-boosted card would: the gate reads its chats
        cards = [made_up(1, "price", 40, weight=0.01), made_up(2, "size", 30, weight=0.01),
                 made_up(3, "fit", 10, weight=0.01), made_up(4, "delivery", 10, weight=0.01),
                 made_up(5, "colour", 10, weight=0.01), made_up(6, "returns", 1, weight=99.0)]
        gate = run.real_mix(cards)
        self.assertAlmostEqual(sum(c["arena_weight"] for c in gate), 1.0)
        self.assertAlmostEqual(gate[0]["arena_weight"], 40 / 101)
        plan = run.gate_plan(gate, 10, random.Random(0), run.gate_cap(gate, 10)[0])
        got = groups(plan)
        self.assertEqual((got["base:price"], got["base:size"]), (3, 3))
        self.assertEqual(sorted((got["base:fit"], got["base:delivery"], got["base:colour"])), [1, 1, 2])
        self.assertEqual(got["base:returns"], 0)  # 1 of 101 chats: no gate match of 10

    def test_one_rare_held_card_no_longer_fills_the_gate(self):
        # the shape the owner saw: the held-out card was 10 of 300 chats and played about 98% of the gate
        base = [made_up(1, "price", 150), made_up(2, "size", 80), made_up(3, "fit", 40), made_up(4, "delivery", 20),
                made_up(5, "colour", 10)]
        pool = grow.Pool(self.dir / "owner", "sales")
        a = self.arena(base, pool=pool, held_out=None)
        self.assertEqual(sorted(c["id"] for c in a.gate_cards), [c["id"] for c in base])  # trained cards too
        plan = run.gate_plan(a.gate_cards, 10, random.Random(0), a.gate_most)
        self.assertLessEqual(groups(plan)["base:colour"], 1)
        self.assertLessEqual(max(groups(plan).values()), 3)

    def test_a_card_that_will_not_buy_and_a_grown_card_never_take_the_gate(self):
        cards = [made_up(1, "price", 50), made_up(2, "size", 50), made_up(3, "browsing", 500, unwinnable=True),
                 dict(made_up(4, "fit", 500), id="grown-fit")]
        self.assertEqual([c["id"] for c in run.real_mix(cards)], ["persona-01", "persona-02"])
        a = self.arena(cards)
        self.assertEqual(sorted(c["id"] for c in a.gate_cards), ["persona-01", "persona-02"])

    def test_a_fixed_test_set_plays_each_customer_once_with_the_cap_held(self):
        test_set = [made_up(i, w, 0) for i, w in enumerate(("price", "price", "price", "price", "size", "size", "fit",
                                                             "fit", "delivery", "colour", "colour", "returns"), 1)]
        gate = run.real_mix(test_set)  # made-up customers name no chats: they share alike
        most, line = run.gate_cap(gate, 10, once=True)
        self.assertEqual((most, line), (3, ""))
        for seed in range(10):
            plan = run.gate_plan(gate, 10, random.Random(seed), most, once=True)
            self.assertEqual(len({c["id"] for c in plan}), 10)
            self.assertLessEqual(max(groups(plan).values()), 3)


class OneGroup(Base):
    def test_one_card_that_can_buy_still_runs_its_cap_relaxed_with_a_clear_line(self):
        cards = [made_up(1, "size", 10), made_up(2, "browsing", 290, unwinnable=True)]
        a = self.arena(cards)
        self.assertEqual(a.gate_most, 10)
        self.assertIn("only 1 card group can buy", a.gate_line)
        self.assertIn("relaxed", a.gate_line)
        rep = a.run()
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 10)
        self.assertEqual(rep["gate_mix"], {"cards": 1, "most": 10, "of": 10, "line": a.gate_line,
                                           "team_rate": rep["gate_mix"]["team_rate"]})  # decision 105's report line
        self.assertIn(a.gate_line, run.text(rep))

    def test_the_cap_holds_line_is_quiet(self):
        cards = [made_up(i, w, 10) for i, w in enumerate(("price", "size", "fit", "delivery"), 1)]
        rep = self.arena(cards).run()
        self.assertEqual(rep["gate_mix"]["line"], "")
        self.assertIn("at most 3 of 10 matches a card group", run.text(rep))
        self.assertNotIn("relaxed", run.text(rep))


class NewMatches(Base):
    def test_no_gate_match_is_a_training_match_or_one_saved_before(self):
        cards = [made_up(i, w, 10) for i, w in enumerate(("price", "size", "fit", "delivery"), 1)]
        first = self.arena(cards)
        taken = f"{first.run_id}-r1-g01"  # a match saved before under the id this run's first gate match would take
        (self.dir / run.MATCHES_FILE).write_text(json.dumps({"id": taken, "won": False}) + "\n", encoding="utf-8")
        first.run()
        self.arena(cards).run()  # a second run stamped the same second, in the same folder
        saved = self.saved()[1:]
        gate = [m for m in saved if "-g" in m["id"]]
        training = [m for m in saved if "-t" in m["id"]]
        self.assertEqual(len(gate), 20)
        ids = [m["id"] for m in gate]
        self.assertEqual(len(set(ids)), 20)
        self.assertNotIn(taken, ids)
        self.assertFalse(set(ids) & {m["id"] for m in training})
        self.assertFalse({m["seed"] for m in gate} & {m["seed"] for m in training})
        self.assertTrue(all(m["seed"] == m["id"] for m in gate))  # each gate match's seed is its new id
        self.assertTrue(all(run.re.fullmatch(r"\d{8}T\d{6}-r\d+-g\d+", i) for i in ids))  # still read as gate ids

    def test_a_lost_gate_match_names_its_match_for_train(self):
        # decision 104: Train studies the last run's lost matches, gate ones too; each lost line names its match
        rep = self.arena([made_up(1, "price", 10), made_up(2, "size", 10)], matches=4).run()
        lost = rep["rounds"][0]["gate"]["lost"]
        self.assertEqual(len(lost), 4)
        self.assertEqual({x["match"] for x in lost}, {m["id"] for m in self.saved() if "-g" in m["id"]})


if __name__ == "__main__":
    unittest.main()
