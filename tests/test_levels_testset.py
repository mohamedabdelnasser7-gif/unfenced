"""The test set is kept (DECISIONS item 85, arena/practice.py fixed_test): test-set.json keeps the first
run's test customers, a customer with a training match on record is never a test customer, across top
ups (6 to 20 to 30), a raised or lowered level and a short supply (the writer writes more), and a
test-set.json that cannot be read stops the run before any model call. The three agents of
tests/three_agents.json, so it holds for any agent kind. Fake models only."""
import json
import os
from unittest import mock

from arena import madeup, practice, run
from kit import seal, turn
from tests.test_customers_shape import Base, Writer


def recorded_play(log, won=False):
    """Practice.play with no model that saves each match in the agent's matches file as the real one
    does (its id, the card id, the person and whether it was a test match, sealed by Practice.save), so
    the training on record is real."""
    def play(self, card, match_id, *, opening=None, lessons=None, replay=None, training=False):
        log.append((match_id, card["id"]))
        m = {"id": match_id, "card": card["id"], "won": won, "persona": card, practice.TEST_KEY: not training}
        self.save(m)
        return m, {"won": won, "why": "fake", "quote": ""}
    return play


class Kept(Base):
    def practise(self, name, customers=None, gate_size=None, *, rounds=2, quick=False, writer=None):
        log = []
        with mock.patch.object(practice.Practice, "play", recorded_play(log)):
            rep = practice.practise(self.folders[name], agent_model=None, customer_model=writer or Writer(),
                                    judge_model=None, rounds=rounds, customers=customers, gate_size=gate_size,
                                    quick=quick)
        return rep

    def trained(self, name):
        """Card ids with a match on record that is not a test match."""
        lines = (self.folders[name] / run.MATCHES_FILE).read_text(encoding="utf-8").splitlines()
        return {m["card"] for m in map(json.loads, lines) if not m["id"].rsplit("-", 1)[-1].startswith("g")}

    def test_quick_then_medium_then_high_never_tests_a_customer_that_trained(self):
        for name in self.folders:
            with self.subTest(name=name):
                self.practise(name, quick=True)  # the 6 of the old shape, one of them trains
                medium = self.practise(name, 20, 10)
                self.assertFalse(set(medium["held_out_cards"]) & self.trained(name))
                high = self.practise(name, 30, 20)
                self.assertEqual(len(high["held_out_cards"]), 20)
                self.assertFalse(set(high["held_out_cards"]) & self.trained(name))
                self.assertLessEqual(set(medium["held_out_cards"]), set(high["held_out_cards"]))  # the same people
                again = self.practise(name, 30, 20)
                self.assertEqual(again["held_out_cards"], high["held_out_cards"])
                self.assertFalse(set(again["held_out_cards"]) & self.trained(name))

    def test_lowering_keeps_the_spare_test_customers_out_of_training(self):
        name = "support_calm_helper"
        high = self.practise(name, 30, 20)
        medium = self.practise(name, 20, 10)
        self.assertLessEqual(set(medium["held_out_cards"]), set(high["held_out_cards"]))
        self.assertFalse(set(high["held_out_cards"]) & self.trained(name))  # the 10 left out sat out
        back = self.practise(name, 30, 20)
        self.assertEqual(back["held_out_cards"], high["held_out_cards"])

    def test_too_few_that_never_trained_has_the_writer_write_more(self):
        name = "lead_trial_booker"
        self.practise(name, 20, 10)
        folder = self.folders[name]
        (folder / practice.TEST_FILE).unlink()
        cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((folder / madeup.FOLDER).glob("*.json"))]
        with open(folder / run.MATCHES_FILE, "a", encoding="utf-8") as f:  # every one of the 20 has trained
            for c in cards:
                f.write(json.dumps({"id": f"old-r1-t{c['id'][-2:]}", "card": c["id"], "persona": c}) + "\n")
        writer = Writer()
        rep = self.practise(name, 20, 10, writer=writer)
        self.assertTrue(writer.asks)  # the writer wrote more people
        self.assertEqual(len(rep["held_out_cards"]), 10)
        self.assertFalse(set(rep["held_out_cards"]) & {c["id"] for c in cards})
        self.assertFalse(set(rep["held_out_cards"]) & self.trained(name))

    def test_a_saved_test_customer_that_trained_is_replaced(self):
        name = "coffee_caption_writer"
        first = self.practise(name, 20, 10)
        gone = first["held_out_cards"][0]
        folder = self.folders[name]
        card = json.loads((folder / madeup.FOLDER / f"{gone}.json").read_text(encoding="utf-8"))
        with open(folder / run.MATCHES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "x-r1-t01", "card": gone, "persona": card}) + "\n")
        second = self.practise(name, 20, 10)
        self.assertNotIn(gone, second["held_out_cards"])
        self.assertEqual(len(set(first["held_out_cards"]) & set(second["held_out_cards"])), 9)
        saved = [e["id"] for e in json.loads((folder / practice.TEST_FILE).read_text(encoding="utf-8"))["test"]]
        self.assertNotIn(gone, saved)

    def test_a_test_file_that_cannot_be_read_stops_before_any_model_call(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        for text in ("not json", '{"test": "persona-01"}', '{"test": [{"id": 3}]}', "[]",
                     '{"test": [{"id": "persona-01"}]}'):  # no from_card
            with self.subTest(text=text):
                (folder / practice.TEST_FILE).write_text(text, encoding="utf-8")
                writer = Writer()
                with self.assertRaises(run.Refused) as got:
                    self.practise(name, 20, 10, writer=writer)
                self.assertIn("cannot be read", str(got.exception))
                self.assertEqual(writer.asks, [])
        (folder / practice.TEST_FILE).unlink()
        os.symlink(folder / "card.json", folder / practice.TEST_FILE)
        with self.assertRaises(run.Refused):
            self.practise(name, 20, 10)


class TrainedOnRecord(Base):
    """trained reads who trained from a field each match carries, and fails closed (red team levels r2
    item 2): a link, a line that cannot be read, or a matches file deleted beside test-set.json stops
    the run before any model call; a line without the field counts as training."""
    def setUp(self):
        super().setUp()
        self.dir = self.root / "one"
        self.dir.mkdir()

    def lines(self, *rows):
        """Each row sealed with the folder's key as Practice.save seals it, the roster beside them as
        Practice.save keeps it; a str row as it is."""
        practice.keep_trained(self.dir)
        (self.dir / run.MATCHES_FILE).write_text("".join(
            (r if isinstance(r, str) else json.dumps(seal.sign(dict(r), self.dir))) + "\n" for r in rows),
            encoding="utf-8")

    def test_a_test_match_is_one_its_line_says_is(self):
        self.lines({"id": "a-r1-g01", "card": "persona-01", "persona": {"from_card": "F"}, practice.TEST_KEY: True},
                   {"id": "a-r1-t01", "card": "persona-02", "persona": {"from_card": "F"}, practice.TEST_KEY: False},
                   {"id": "a-r1-g02", "card": "persona-03", "persona": {"from_card": "F"}},  # an old line
                   {"id": "a-r1-t02", "card": "persona-04", "persona": {"from_card": "F"}, practice.TEST_KEY: True},
                   {"id": "a-r1-g03", "card": "persona-05", "persona": {"from_card": "F"}, practice.TEST_KEY: "yes"},
                   "   ")
        self.assertEqual(practice.trained(self.dir), {("persona-02", "F"), ("persona-03", "F"), ("persona-04", "F"),
                                                       ("persona-05", "F")})

    def test_a_line_that_cannot_be_read_stops_it(self):
        good_line = {"id": "a-r1-t01", "card": "persona-01", practice.TEST_KEY: False}
        for bad in ('{"id": "a-r1-t02", "card"', "[1]", json.dumps({"id": "a-r1-t03", "card": 3}),
                    json.dumps({"id": "a-r1-t04"})):
            with self.subTest(bad=bad):
                self.lines(good_line, bad)
                with self.assertRaises(run.Refused) as got:
                    practice.trained(self.dir)
                self.assertIn("cannot be read", str(got.exception))

    def test_a_link_or_a_folder_is_refused(self):
        real = self.root / "elsewhere.jsonl"
        real.write_text(json.dumps({"id": "a-r1-t01", "card": "persona-01"}) + "\n", encoding="utf-8")
        os.symlink(real, self.dir / run.MATCHES_FILE)
        with self.assertRaises(run.Refused):
            practice.trained(self.dir)
        (self.dir / run.MATCHES_FILE).unlink()
        (self.dir / run.MATCHES_FILE).mkdir()
        with self.assertRaises(run.Refused):
            practice.trained(self.dir)

    def test_a_matches_file_deleted_beside_the_test_set_stops_it(self):
        self.assertEqual(practice.trained(self.dir), set())  # a first run: neither file
        practice.write_test(self.dir, [("persona-01", "F")])
        self.assertTrue((self.dir / run.MATCHES_FILE).is_file())  # made with the test set
        self.assertEqual(practice.trained(self.dir), set())
        (self.dir / run.MATCHES_FILE).unlink()
        with self.assertRaises(run.Refused) as got:
            practice.trained(self.dir)
        self.assertIn("gone", str(got.exception))


class FailClosedRun(Base):
    practise = Kept.practise

    def test_a_bad_line_or_a_deleted_matches_file_stops_the_run_before_any_model_call(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        self.practise(name, 20, 10)
        path = folder / run.MATCHES_FILE
        before = path.read_text(encoding="utf-8")
        for text in (before + "not json\n", None):
            with self.subTest(deleted=text is None):
                if text is None:
                    path.unlink()
                else:
                    path.write_text(text, encoding="utf-8")
                writer = Writer()
                with self.assertRaises(run.Refused):
                    self.practise(name, 20, 10, writer=writer)
                self.assertEqual(writer.asks, [])

    def test_an_old_test_line_without_the_field_counts_as_training(self):
        name = "coffee_caption_writer"
        first = self.practise(name, 20, 10)
        folder = self.folders[name]
        gone = first["held_out_cards"][0]
        card = json.loads((folder / madeup.FOLDER / f"{gone}.json").read_text(encoding="utf-8"))
        with open(folder / run.MATCHES_FILE, "a", encoding="utf-8") as f:  # a training match given a test id
            f.write(json.dumps({"id": "x-r1-g01", "card": gone, "persona": card}) + "\n")
        second = self.practise(name, 20, 10)
        self.assertNotIn(gone, second["held_out_cards"])


class FixedTest(Base):
    def cards(self, kinds):
        return [{"id": f"persona-{i:02d}", "kind": k, "from_card": "F", "unwinnable": k == "never"}
                for i, k in enumerate(kinds, 1)]

    def test_saved_first_then_new_and_short_when_too_few(self):
        cards = self.cards(["easy"] * 5 + ["never"])
        held, spare, short = practice.fixed_test(cards, 2, [("persona-04", "F")], set())
        self.assertIn("persona-04", held)
        self.assertEqual((len(held), spare, short), (2, [], 0))
        done = {("persona-01", "F"), ("persona-02", "F"), ("persona-03", "F")}
        self.assertEqual(practice.fixed_test(cards, 3, [], done), (None, [], 2))  # 1 more easy at 5 in 6
        self.assertEqual(practice.fixed_test(self.cards(["easy"] * 5), 5, [], set()), (None, [], 1))  # none to practise
        other = practice.fixed_test(cards, 1, [("persona-04", "G")], set())[0]  # another card's person
        self.assertEqual(other, practice.test_set(cards, 1))

    def test_the_kinds_follow_the_shapes_mix_never_the_saved_file(self):
        self.assertEqual(practice.shape_mix(20), {"easy": 7, "unsure": 7, "hard": 3})
        cards = self.cards(["easy"] * 10 + ["unsure"] * 10 + ["hard"] * 5 + ["never"] * 5)
        edited = [(c["id"], "F") for c in cards if c["kind"] in ("easy", "unsure")]  # 10 easy, 10 unsure, 0 hard
        held, spare, short = practice.fixed_test(cards, 20, edited, set(), practice.shape_mix(30))
        kinds = {c["id"]: c["kind"] for c in cards}
        got = [kinds[i] for i in held]
        self.assertEqual((got.count("easy"), got.count("unsure"), got.count("hard"), short), (8, 8, 4, 0))
        self.assertEqual(len(spare), 4)  # the saved ones past their kind's share sit out, never train
        self.assertFalse(set(spare) & set(held))
        fits = [(i, "F") for i in held]
        self.assertEqual(practice.fixed_test(cards, 20, fits, set(), practice.shape_mix(30))[0], held)  # kept
        low = practice.fixed_test(cards, 10, fits, set(), practice.shape_mix(20))[0]  # lowered: a subset, 4/4/2
        self.assertLessEqual(set(low), set(held))
        self.assertEqual(sorted(kinds[i] for i in low).count("hard"), 2)

    def test_a_kind_short_of_its_share_asks_the_writer_for_enough(self):
        cards = self.cards(["easy"] * 10 + ["unsure"] * 10 + ["hard"] * 5 + ["never"] * 5)
        done = {(c["id"], "F") for c in cards if c["kind"] == "hard"}  # every hard one trained
        held, spare, short = practice.fixed_test(cards, 20, [], done, practice.shape_mix(30))
        self.assertEqual((held, spare), (None, []))
        self.assertEqual(short, 24)  # 4 more hard at 5 in 30


class HandEditedKinds(Base):
    practise = Kept.practise

    def test_a_hand_edited_test_set_of_other_kinds_is_rebuilt(self):
        for name in self.folders:
            with self.subTest(name=name):
                folder = self.folders[name]
                practice.keep_trained(folder)  # the roster a first run leaves before it writes customers
                cards, _ = madeup.for_agent(folder, name, turn.load(folder).card, Writer(), count=30)
                practice.write_test(folder, [(c["id"], c["from_card"]) for c in cards
                                             if c["kind"] in ("easy", "unsure")])  # 10/10/0, none trained
                rep = self.practise(name, 30, 20)
                kinds = {c["id"]: c["kind"] for c in cards}
                got = [kinds[i] for i in rep["held_out_cards"]]
                self.assertEqual((got.count("easy"), got.count("unsure"), got.count("hard")), (8, 8, 4))


class Gaps(Base):
    """The cases review levels r2 item 4 found untested."""
    practise = Kept.practise

    def test_a_matches_file_that_cannot_be_read_stops_the_run_before_any_model_call(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        self.practise(name, 20, 10)
        path = folder / run.MATCHES_FILE
        before = path.read_bytes()
        for what in ("no read permission", "not utf-8"):
            with self.subTest(what=what):
                if what == "not utf-8":
                    path.write_bytes(before + b'{"id": "x-r1-t01", "card": "\xff"}\n')
                else:
                    os.chmod(path, 0)
                    self.addCleanup(os.chmod, path, 0o644)
                writer = Writer()
                with self.assertRaises(run.Refused) as got:
                    self.practise(name, 20, 10, writer=writer)
                self.assertIn("saved matches cannot be read", str(got.exception))
                self.assertEqual(writer.asks, [])
                os.chmod(path, 0o644)

    def test_read_test_refuses_a_dangling_link_a_big_file_and_a_bad_from_card(self):
        d = self.root / "one"
        d.mkdir()
        practice.keep_trained(d)  # the roster an earlier run left
        path = d / practice.TEST_FILE
        os.symlink(d / "gone.json", path)  # points nowhere
        with self.assertRaises(run.Refused):
            practice.read_test(d)
        path.unlink()
        pad = "x" * practice.MAX_TEST_FILE
        path.write_text(json.dumps({"test": [{"id": "persona-01", "from_card": "F"}], "pad": pad}), encoding="utf-8")
        with self.assertRaises(run.Refused):
            practice.read_test(d)  # whole JSON, but over the size cap
        for bad in (3, ["F"], {"f": 1}, True):
            with self.subTest(from_card=bad):
                path.write_text(json.dumps({"test": [{"id": "persona-01", "from_card": bad}]}), encoding="utf-8")
                with self.assertRaises(run.Refused):
                    practice.read_test(d)
        practice.write_test(d, [("persona-01", None)])
        self.assertEqual(practice.read_test(d), [("persona-01", None)])

    def test_a_training_match_whose_person_names_no_card_rules_out_the_id_whatever_its_card(self):
        d = self.root / "one"
        d.mkdir()
        (d / run.MATCHES_FILE).write_text(
            json.dumps({"id": "a-r1-t01", "card": "persona-01", "persona": {"id": "persona-01"},
                        practice.TEST_KEY: False}) + "\n" +
            json.dumps({"id": "a-r1-t02", "card": "persona-02", "persona": "not a person",
                        practice.TEST_KEY: False}) + "\n", encoding="utf-8")
        done = practice.trained(d)
        cards = FixedTest.cards(None, ["easy"] * 6 + ["never"])
        held = practice.fixed_test(cards, 4, [("persona-01", "F"), ("persona-02", "F")], done)[0]
        self.assertEqual(len(held), 4)
        self.assertFalse({"persona-01", "persona-02"} & set(held))

    def test_a_card_grown_from_real_chats_is_never_held_by_fixed_test(self):
        cards = FixedTest.cards(None, ["easy"] * 4 + ["never"])
        cards.append({"id": "grown-01", "kind": "easy", "from_card": "F", "unwinnable": False})
        held, spare, short = practice.fixed_test(cards, 3, [("grown-01", "F")], set())
        self.assertNotIn("grown-01", held + spare)
        self.assertEqual((len(held), short), (3, 0))
        held, _, short = practice.fixed_test(cards, 5, [("grown-01", "F")], set())  # only 4 are not grown
        self.assertIsNone(held)
        self.assertGreater(short, 0)

