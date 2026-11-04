"""As many practice customers as the shape needs, and a fixed test set (DECISIONS item 85), on fake models
only: arena/madeup.py for_agent count (batches, the mix, no two the same person, top up, the cap) and
arena/practice.py practise customers and gate_size (exactly gate_size test customers, the same ids run to
run, each once a round, never studied, "never" cards only practise). The three agents of
tests/three_agents.json, so it holds for any agent kind."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import madeup, practice, run
from kit import turn
from tests.fake_model import clean_env, say
from tests.test_any_agent_r2 import THREE, old_folder

SHAPES = {20: (7, 7, 3, 3), 30: (10, 10, 5, 5)}  # easy, unsure, hard, never


def person(n, why=True):
    out = {"want": [f"want number {n}"], "worry": f"worry {n}", "settles_it": [f"settled {n}"],
           "language": "english", "length": "short", "opening": f"topic {n}", "examples": [f"line {n}"]}
    if why:
        out["why_not"] = "it cannot happen today"
    return out


class Writer:
    """The customer writer's side: a different person for every slot asked, unless same says otherwise
    (same(call number, slot number) -> the person number to repeat, or None)."""

    def __init__(self, same=None):
        self.asks, self.systems, self.n, self.same = [], [], 0, same

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.systems.append(messages[0]["content"])
        ask = json.loads(messages[1]["content"])
        self.asks.append(ask)
        slots = ask.get("kinds") or ask.get("people")
        people = []
        for i, _ in enumerate(slots):
            again = self.same(len(self.asks), i) if self.same else None
            if again is None:
                self.n += 1
            people.append(person(self.n if again is None else again))
        return say(json.dumps({"customers": people}))


def counts(cards):
    return tuple(sum(c["kind"] == k for c in cards) for k in ("easy", "unsure", "hard", "never"))


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()
        self.folders = {name: old_folder(self.root, name) for name in THREE}

    def files(self, name):
        folder = self.folders[name] / madeup.FOLDER
        return {p.name: p.read_bytes() for p in sorted(folder.glob("persona-*.json"))}

    def write(self, name, model, count=None, **kw):
        return madeup.for_agent(self.folders[name], name, THREE[name]["card"], model, count=count, **kw)


class Shapes(Base):
    def test_counts_and_mix_for_each_shape_and_agent(self):
        for name in THREE:
            for count, mix in SHAPES.items():
                with self.subTest(name=name, count=count):
                    model = Writer()
                    folder = self.root / f"{name}-{count}"
                    cards, written = madeup.for_agent(folder, name, THREE[name]["card"], model, count=count)
                    self.assertTrue(written)
                    self.assertEqual((len(cards), counts(cards)), (count, mix))
                    self.assertEqual([c["id"] for c in cards], [f"persona-{i:02d}" for i in range(1, count + 1)])
                    self.assertEqual([len(a["kinds"]) for a in model.asks], [10] * (count // 10))
                    for a in model.asks:  # every batch holds the mix, never only one kind
                        self.assertTrue({"easy", "unsure", "hard"} <= set(a["kinds"]), a["kinds"])
                    self.assertEqual(len({madeup.person(c) for c in cards}), count)
                    self.assertTrue(all(c["unwinnable"] == (c["kind"] == "never") for c in cards))
                    case = isinstance(THREE[name]["card"].get("case"), dict)
                    self.assertEqual(model.systems[0].endswith(madeup.CASE_PART), case)

    def test_the_mix_shares(self):
        self.assertEqual(madeup.mix(6), {"easy": 2, "unsure": 2, "hard": 1, "never": 1})
        self.assertEqual(madeup.kinds_for(6), list(madeup.KINDS))
        self.assertEqual(madeup.mix(20), {"easy": 7, "unsure": 7, "hard": 3, "never": 3})
        self.assertEqual(madeup.mix(30), {"easy": 10, "unsure": 10, "hard": 5, "never": 5})
        self.assertEqual(madeup.mix(2), {"easy": 1, "unsure": 1, "hard": 0, "never": 0})
        for bad in (1, 0, 100, True, 2.5, "20"):
            with self.assertRaises(ValueError):
                madeup.check_count(bad)

    def test_later_batches_are_told_the_people_already_written(self):
        model = Writer()
        cards, _ = self.write("support_calm_helper", model, 30)
        self.assertNotIn("already", model.asks[0])
        self.assertFalse(model.systems[0].startswith(madeup.SYSTEM + madeup.ALREADY_PART))
        self.assertEqual([len(a.get("already", [])) for a in model.asks], [0, 10, 20])
        self.assertTrue(model.systems[1].startswith(madeup.SYSTEM + madeup.ALREADY_PART))
        self.assertEqual(model.asks[2]["already"][0], {"want": cards[0]["want"], "opening": "topic 1"})

    def test_a_blend_takes_the_real_cards_in_turn(self):
        real = [madeup.behaviour({"unwinnable": i == 2, "patience": {"median": 2, "most": 2},
                                  "style": {"length": {"short": 1}, "language": {"english": 1}, "voice_notes": 0,
                                            "opening": {"greeting": 0.5}}, "worry": "price"}, f"persona-{i:02d}")
                for i in (1, 2, 3)]
        model = Writer()
        cards, _ = self.write("lead_trial_booker", model, 20, profiles=real)
        self.assertEqual(len(cards), 20)
        self.assertEqual([c["behaviour_from"][0] for c in cards[:4]], ["persona-01", "persona-02", "persona-03", "persona-01"])
        self.assertEqual([len(a["people"]) for a in model.asks], [10, 10])
        self.assertEqual(len({madeup.person(c) for c in cards}), 20)


class SamePerson(Base):
    def test_a_repeat_is_asked_once_more_and_kept_when_new(self):
        # the second batch's first person repeats person 3 of the first batch
        model = Writer(same=lambda call, i: 3 if (call, i) == (2, 0) else None)
        cards, _ = self.write("coffee_caption_writer", model, 20)
        self.assertEqual(len(model.asks), 3)
        self.assertEqual(len(model.asks[2]["kinds"]), 1)
        self.assertEqual(len(model.asks[2]["already"]), 19)
        self.assertEqual((len(cards), counts(cards)), (20, SHAPES[20]))
        self.assertEqual(len({madeup.person(c) for c in cards}), 20)

    def test_a_repeat_within_one_batch_is_caught(self):
        model = Writer(same=lambda call, i: 1 if (call, i) == (1, 1) else None)
        cards, _ = self.write("coffee_caption_writer", model, 20)
        self.assertEqual([len(a["kinds"]) for a in model.asks], [10, 1, 10])
        self.assertEqual(len({madeup.person(c) for c in cards}), 20)

    def test_a_second_repeat_is_dropped(self):
        model = Writer(same=lambda call, i: 3 if (call, i) in ((2, 0), (3, 0)) else None)
        cards, _ = self.write("coffee_caption_writer", model, 20)
        self.assertEqual(len(model.asks), 3)
        self.assertEqual(len(cards), 19)
        self.assertEqual(len({madeup.person(c) for c in cards}), 19)
        self.assertEqual(self.files("coffee_caption_writer").keys(), {f"persona-{i:02d}.json" for i in range(1, 20)})

    def test_the_same_person_in_other_words_is_still_the_same(self):
        a = {"want": ["Want number 1 "], "style": {"opening": {"Topic  1": 1.0, "greeting": 0.2}}}
        b = {"want": ["want   number 1"], "style": {"opening": {"topic 1": 1.0}}}
        self.assertEqual(madeup.person(a), madeup.person(b))
        self.assertNotEqual(madeup.person(a), madeup.person({**b, "want": ["want number 2"]}))
        self.assertNotEqual(madeup.person(a), madeup.person({**b, "style": {"opening": {"topic 2": 1.0}}}))


class TopUp(Base):
    def test_an_old_folder_of_six_is_topped_up_and_its_files_stay(self):
        name = "support_calm_helper"
        old, written = self.write(name, Writer())
        self.assertTrue(written)
        before = self.files(name)
        self.assertEqual(len(before), 6)
        stamps = {p.name: p.stat().st_mtime_ns for p in (self.folders[name] / madeup.FOLDER).glob("persona-*.json")}
        model = Writer()
        model.n = 100
        cards, written = self.write(name, model, 20)
        self.assertTrue(written)
        self.assertEqual((len(cards), counts(cards)), (20, SHAPES[20]))
        self.assertEqual(cards[:6], old)
        after = self.files(name)
        self.assertEqual({k: after[k] for k in before}, before)
        for p in (self.folders[name] / madeup.FOLDER).glob("persona-0[1-6].json"):
            self.assertEqual(p.stat().st_mtime_ns, stamps[p.name])
        self.assertEqual(len(after), 20)
        self.assertEqual([len(a["kinds"]) for a in model.asks], [10, 4])
        self.assertEqual(len(model.asks[0]["already"]), 6)
        # the fingerprint stays card.json's, so a third read writes nothing
        again, written = self.write(name, Writer(), 20)
        self.assertEqual((again, written), (cards, False))
        changed = dict(THREE[name]["card"], good="Something else.")
        _, written = madeup.for_agent(self.folders[name], name, changed, Writer(), count=20)
        self.assertTrue(written)

    def test_a_folder_with_more_gives_the_mix_of_count(self):
        name = "lead_trial_booker"
        self.write(name, Writer(), 30)
        model = Writer()
        cards, written = self.write(name, model, 20)
        self.assertEqual((written, len(model.asks), len(cards), counts(cards)), (False, 0, 20, SHAPES[20]))


class Cap(Base):
    def calls(self, cap):
        return run.Calls(self.root / run.CALLS_FILE, cap)

    def test_every_batch_call_counts_on_the_cap(self):
        calls, model = self.calls(50), Writer()
        self.write("coffee_caption_writer", calls.model(model), 30)
        self.assertEqual((calls.taken, len(model.asks)), (3, 3))
        self.assertEqual(json.loads((self.root / run.CALLS_FILE).read_text())["calls"], 3)

    def test_a_rewrite_call_counts_too(self):
        calls = self.calls(50)
        self.write("coffee_caption_writer", calls.model(Writer(same=lambda c, i: 1 if (c, i) == (2, 0) else None)), 20)
        self.assertEqual(calls.taken, 3)

    def test_the_cap_mid_write_saves_what_was_written_and_says_so(self):
        name = "coffee_caption_writer"
        calls = self.calls(2)
        with self.assertRaises(run.CapReached) as got:
            self.write(name, calls.model(Writer()), 30)
        self.assertIn("20 of 30 practice customers were written and saved", str(got.exception))
        self.assertIn("the cap of 2 model calls", str(got.exception))
        saved = self.files(name)
        self.assertEqual(len(saved), 20)
        model = Writer()
        model.n = 100
        cards, written = self.write(name, model, 30)
        self.assertEqual((written, len(cards), counts(cards), len(model.asks)), (True, 30, SHAPES[30], 1))
        self.assertEqual({k: v for k, v in self.files(name).items() if k in saved}, saved)

    def test_the_cap_before_any_customer_saves_nothing(self):
        name = "coffee_caption_writer"
        calls = self.calls(1)
        calls.take()
        with self.assertRaises(run.CapReached) as got:
            self.write(name, calls.model(Writer()), 20)
        self.assertIn("0 of 20 practice customers were written and none saved", str(got.exception))
        self.assertFalse((self.folders[name] / madeup.FOLDER).exists())


class OldShape(Base):
    def test_no_count_is_one_call_of_kinds_and_no_repeat_check(self):
        for name in THREE:
            with self.subTest(name=name):
                model = Writer(same=lambda call, i: 1)  # every person the same, as an old fake model answers
                cards, written = self.write(name, model)
                self.assertTrue(written)
                self.assertEqual(model.asks, [{"agent_card": madeup.asked_card(THREE[name]["card"]),
                                               "kinds": list(madeup.KINDS)}])
                self.assertEqual(model.systems, [madeup.system_for(madeup.SYSTEM, THREE[name]["card"])])
                self.assertEqual([c["kind"] for c in cards], list(madeup.KINDS))
                self.assertEqual([c["share"] for c in cards], [round(1 / 6, 3)] * 6)

    def test_practise_on_the_old_gate_with_no_shape_keeps_the_split_and_the_draw(self):
        # the old gate (a trust file or --gate) keeps the old shape; with neither, the level sets it (test_levels_e2e)
        name = "coffee_caption_writer"
        got = {}
        real = madeup.for_agent

        def spy(*a, **kw):
            got["count"] = kw.get("count", "missing")
            return real(*a, **kw)
        seen = []
        with mock.patch.object(madeup, "for_agent", spy), \
                mock.patch.object(run, "draw", lambda cards, rng: seen.append(len(cards)) or cards[0]), \
                mock.patch.object(practice.Practice, "play", fake_play([])):
            rep = practice.practise(self.folders[name], agent_model=None, customer_model=Writer(), judge_model=None,
                                    matches=3, gate=practice.GATE)
        self.assertIsNone(got["count"])
        cards = madeup.read(self.folders[name] / madeup.FOLDER, name, turn.load(self.folders[name]).card)
        train, held = run.split(cards)
        self.assertEqual((rep["training_cards"], rep["held_out_cards"]),
                         ([c["id"] for c in train], [c["id"] for c in held]))
        self.assertEqual(len(seen), 3)  # every training match drawn by arena/run.py draw; the gate by its plan (101)


def fake_play(log, won=False):
    """Practice.play with no model: logs (match id, card id) and returns a lost (or won) match."""
    def play(self, card, match_id, *, opening=None, lessons=None, replay=None, training=False):
        log.append((match_id, card["id"]))
        return {"id": match_id, "card": card["id"]}, {"won": won, "why": "fake", "quote": ""}
    return play


class Gate(Base):
    def practise(self, name, customers, gate_size, *, rounds=2, matches=10, trust=None, learn=None):
        log = []
        with mock.patch.object(practice.Practice, "play", fake_play(log)):
            rep = practice.practise(self.folders[name], agent_model=None, customer_model=Writer(), judge_model=None,
                                    matches=matches, rounds=rounds, customers=customers, gate_size=gate_size,
                                    trust=trust, learn=learn)
        cards = {c["id"]: c for c in madeup.read(self.folders[name] / madeup.FOLDER, name, turn.load(self.folders[name]).card) or []}
        return rep, log, cards

    def trust(self, matches):
        path = self.root / "trust.json"
        path.write_text(json.dumps({name: {"matches": matches, "wins": matches} for name in THREE}))
        return str(path)

    def by_round(self, log, part):
        out = {}
        for mid, cid in log:
            r, k = mid.rsplit("-", 2)[-2:]
            if k.startswith(part):
                out.setdefault(r, []).append(cid)
        return out

    def test_both_shapes_for_every_agent(self):
        for name in THREE:
            for customers, gate_size in ((20, 10), (30, 20)):
                with self.subTest(name=name, customers=customers):
                    self.fresh(name)
                    studied = []
                    rep, log, cards = self.practise(name, customers, gate_size, trust=self.trust(gate_size),
                                                    learn=lambda m, judged, mid: studied.append(m["card"]))
                    test = set(rep["held_out_cards"])
                    practice_ids = set(rep["training_cards"])
                    self.assertEqual((len(cards), len(test), len(practice_ids)), (customers, gate_size, 10))
                    self.assertFalse(test & practice_ids)
                    self.assertTrue(all(not cards[i]["unwinnable"] for i in test))
                    self.assertTrue({i for i, c in cards.items() if c["unwinnable"]} <= practice_ids)
                    gates, training = self.by_round(log, "g"), self.by_round(log, "t")
                    self.assertEqual(sorted(gates), ["r1"])  # round 2 plays practice only (decision 113)
                    self.assertEqual(sorted(training), ["r1", "r2"])
                    for r, ids in gates.items():  # each test customer exactly once a round
                        self.assertEqual(sorted(ids), sorted(test), r)
                    for r, ids in training.items():  # the 10 practice customers, each once
                        self.assertEqual(sorted(ids), sorted(practice_ids), r)
                    self.assertTrue(studied)
                    self.assertFalse(set(studied) & test)  # a test customer is never studied

    def fresh(self, name):
        """The agent's folder with no practice customers and no Arena files, for the next shape."""
        shutil.rmtree(self.folders[name] / madeup.FOLDER, ignore_errors=True)
        for p in self.folders[name].glob("arena-*"):
            p.unlink()
        (self.folders[name] / practice.TEST_FILE).unlink(missing_ok=True)  # its test set went with its matches

    def test_no_repeat_within_a_gate_round_when_fewer_matches_than_test_customers(self):
        rep, log, _ = self.practise("support_calm_helper", 30, 20, rounds=3)  # the public level: 10 matches
        for r, ids in self.by_round(log, "g").items():
            self.assertEqual(len(ids), rep["trust"]["matches"])
            self.assertEqual(len(set(ids)), len(ids), r)
            self.assertTrue(set(ids) <= set(rep["held_out_cards"]))

    def test_training_past_the_practice_customers_plays_each_once_first(self):
        rep, log, _ = self.practise("lead_trial_booker", 20, 10, rounds=1, matches=15)
        ids = self.by_round(log, "t")["r1"]
        self.assertEqual(len(ids), 15)
        self.assertEqual(sorted(ids[:10]), sorted(rep["training_cards"]))

    def test_the_same_test_ids_across_runs(self):
        name = "lead_trial_booker"
        first, _, _ = self.practise(name, 30, 20)
        second, _, _ = self.practise(name, 30, 20)
        self.assertEqual(first["held_out_cards"], second["held_out_cards"])
        other = self.root / "elsewhere"
        cards, _ = madeup.for_agent(other, name, turn.load(self.folders[name]).card, Writer(), count=30)
        self.assertEqual(practice.test_set(cards, 20), first["held_out_cards"])
        changed = [dict(c, from_card="another card") for c in cards]
        self.assertNotEqual(practice.test_set(changed, 20), first["held_out_cards"])

    def test_the_test_set_takes_each_kind_in_its_share(self):
        cards, _ = madeup.for_agent(self.root / "x", "coffee_caption_writer", THREE["coffee_caption_writer"]["card"],
                                    Writer(), count=30)
        kinds = {c["id"]: c["kind"] for c in cards}
        got = [kinds[i] for i in practice.test_set(cards, 20)]
        self.assertEqual((got.count("easy"), got.count("unsure"), got.count("hard"), got.count("never")), (8, 8, 4, 0))

    def test_practise_counts_the_writer_calls_on_the_run_cap(self):
        rep, _, _ = self.practise("support_calm_helper", 30, 20, rounds=1)  # matches are faked: no model call
        self.assertEqual(rep["calls"]["used"], 3)
        with self.assertRaises(run.CapReached) as got:
            practice.practise(self.folders["coffee_caption_writer"], agent_model=None, customer_model=Writer(),
                              judge_model=None, cap=4, customers=20, gate_size=10)  # 3 used today
        self.assertIn("10 of 20 practice customers were written and saved", str(got.exception))

    def test_a_card_grown_from_real_chats_is_never_a_test_customer(self):
        cards = [{"id": f"grown-{i:02d}", "kind": "easy", "unwinnable": False} for i in range(1, 9)]
        cards += [{"id": f"persona-{i:02d}", "kind": "easy", "unwinnable": False} for i in range(1, 5)]
        got = practice.test_set(cards, 3)
        self.assertEqual(len(got), 3)
        self.assertFalse([i for i in got if i.startswith(run.GROWN)])
        with self.assertRaises(run.Refused):
            practice.test_set(cards, 5)  # only 4 that are not grown

    def test_a_test_set_of_every_customer_is_refused(self):
        cards = [{"id": f"persona-{i:02d}", "kind": "easy", "unwinnable": False} for i in range(1, 6)]
        self.assertEqual(len(practice.test_set(cards, 4)), 4)
        with self.assertRaises(run.Refused) as got:
            practice.test_set(cards, 5)
        self.assertIn("leave at least one to practise on", str(got.exception))

    def test_too_few_or_too_many_test_customers_are_refused(self):
        cards, _ = madeup.for_agent(self.root / "y", "coffee_caption_writer", THREE["coffee_caption_writer"]["card"],
                                    Writer(), count=20)
        with self.assertRaises(run.Refused):
            practice.test_set(cards, 18)  # 17 can reach the good result
        for bad in (0, True, 2.0):
            with self.assertRaises(run.Refused):
                practice.test_set(cards, bad)
        with self.assertRaises(run.Refused) as got:
            self.practise("coffee_caption_writer", 20, 10, trust=self.trust(12))
        self.assertIn("each test customer plays once a round", str(got.exception))


if __name__ == "__main__":
    unittest.main()
