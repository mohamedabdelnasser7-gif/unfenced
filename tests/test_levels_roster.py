"""The sealed roster of every customer that ever trained (arena/practice.py keep_trained, trained.json; the
gap left after DECISIONS item 90): the seal is per line, so deleting a training line from
arena-matches.jsonl once hid that a customer trained. Each training match now adds its customer to a
roster sealed as test-set.json is, never shrunk, and trained is the union of the roster and the matches
file. A roster that does not hold its seal, or one gone while a sealed line or test-set.json is there,
stops the run before any model call with the same page note and Start a new test set, which counts
every old customer as trained in a new roster. An old folder with no roster has it built once from its
matches file. Fake models only."""
import json
import os

from arena import madeup, practice, run
from kit import seal
from kit.model import ModelError
from tests import test_levels_r3_minors as r3
from tests import test_levels_tab
from tests import test_levels_testset as testset  # the module, so its tests are not run twice
from tests.test_customers_shape import Base, Writer

NAME = "support_calm_helper"
OLD = "lead_trial_booker"


class Roster(Base):
    practise = testset.Kept.practise

    def setUp(self):
        super().setUp()
        self.folder = self.folders[NAME]
        self.first = self.practise(NAME, 20, 10)
        self.path = self.folder / run.MATCHES_FILE
        self.roster = self.folder / practice.ROSTER_FILE
        self.rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
        held = set(self.first["held_out_cards"])
        # a training customer that could reach the good result: the one an attacker would hide
        self.hidden = next(m["card"] for m in self.rows if m[practice.TEST_KEY] is False
                           and m["card"] not in held and not m["persona"].get("unwinnable"))
        self.from_card = next(m["persona"]["from_card"] for m in self.rows if m["card"] == self.hidden)

    def drop_lines(self):
        """The matches file with every line of the hidden customer deleted (the seal is per line)."""
        self.path.write_text("".join(json.dumps(m) + "\n" for m in self.rows if m["card"] != self.hidden),
                             encoding="utf-8")

    def items(self):
        return list(self.root.glob("arena-*-*.json"))  # the run items, never the call count

    def assert_refused(self):
        """The next run stops before any model call, naming the roster, and no item is written."""
        before, writer = self.items(), Writer()
        with self.assertRaises(practice.Unrecorded) as got:
            self.practise(NAME, 20, 10, writer=writer)
        self.assertEqual(got.exception.file, practice.ROSTER_FILE)
        self.assertEqual(writer.asks, [])  # before the writer, the first model call
        self.assertEqual(self.items(), before)
        self.assertEqual(practice.broken_record(self.folder), practice.ROSTER_FILE)

    def test_the_roster_holds_every_training_customer_and_no_test_customer(self):
        k = seal.key(practice.reports_of(self.folder))
        self.assertTrue(seal.holds(json.loads(self.roster.read_text(encoding="utf-8")), k))
        on_roster = practice._read_roster(self.folder)
        training = {(m["card"], m["persona"]["from_card"]) for m in self.rows if m[practice.TEST_KEY] is False}
        self.assertEqual(on_roster, training)
        self.assertFalse({c for c, _ in on_roster} & set(self.first["held_out_cards"]))

    def test_a_deleted_training_line_still_counts_as_trained(self):
        self.drop_lines()
        self.assertIn((self.hidden, self.from_card), practice.trained(self.folder))
        cards = [json.loads(p.read_text(encoding="utf-8"))
                 for p in sorted((self.folder / madeup.FOLDER).glob("*.json"))]
        done = practice.trained(self.folder)
        held = practice.fixed_test(cards, 10, [(self.hidden, self.from_card)], done, practice.shape_mix(20))[0]
        self.assertNotIn(self.hidden, held or [])
        again = self.practise(NAME, 20, 10)
        self.assertNotIn(self.hidden, again["held_out_cards"])
        self.assertIn((self.hidden, self.from_card), practice._read_roster(self.folder))  # never shrunk

    def test_an_edited_roster_stops_the_run_before_any_model_call(self):
        whole = self.roster.read_bytes()
        doc = json.loads(whole)
        shorter = dict(doc, trained=[e for e in doc["trained"] if e["card"] != self.hidden])  # old seal kept
        for how, body in (("the hidden customer removed, the old seal kept", json.dumps(shorter)),
                          ("a seal written by hand", json.dumps(dict(shorter, seal="0" * 64))),
                          ("no seal", json.dumps({"trained": shorter["trained"]})),
                          ("torn", whole.decode("utf-8")[:20]),
                          ("not a list", json.dumps(dict(doc, trained={"card": "persona-01"})))):
            with self.subTest(how=how):
                self.drop_lines()
                self.roster.write_text(body, encoding="utf-8")
                self.assert_refused()
                with self.assertRaises(practice.Unrecorded):
                    practice.trained(self.folder)
                self.roster.write_bytes(whole)
        self.roster.unlink()
        os.symlink(self.folder / "card.json", self.roster)
        self.assert_refused()

    def test_a_roster_copied_from_another_agent_beside_it_stops_the_run(self):
        other = self.folder.parent / "other_agent"
        other.mkdir()
        practice.keep_trained(other, [("persona-01", "F")])  # sealed with the same key, for its own folder
        self.drop_lines()
        self.roster.write_bytes((other / practice.ROSTER_FILE).read_bytes())
        k = seal.key(practice.reports_of(self.folder))
        self.assertTrue(seal.holds(json.loads(self.roster.read_text(encoding="utf-8")), k))  # only the name tells
        self.assert_refused()

    def test_a_deleted_roster_stops_the_run(self):
        self.roster.unlink()
        self.assert_refused()  # sealed lines and test-set.json there
        (self.folder / practice.TEST_FILE).unlink()
        self.assert_refused()  # sealed lines alone
        self.path.write_text("", encoding="utf-8")
        (self.folder / practice.TEST_FILE).write_text("{}", encoding="utf-8")
        with self.assertRaises(practice.Unrecorded) as got:  # test-set.json alone, no sealed line: still refused
            practice.trained(self.folder)
        self.assertEqual(got.exception.file, practice.ROSTER_FILE)

    def test_the_new_test_set_route_counts_every_old_customer_on_the_new_roster(self):
        self.drop_lines()
        doc = json.loads(self.roster.read_text(encoding="utf-8"))
        doc["trained"] = [e for e in doc["trained"] if e["card"] != self.hidden]
        self.roster.write_text(json.dumps(doc), encoding="utf-8")
        self.assert_refused()
        old = {p.stem for p in (self.folder / madeup.FOLDER).glob("persona-*.json")}
        aside = practice.new_test_set(self.folder)
        self.assertTrue(any(a.startswith("trained-before-") for a in aside))  # set aside, never deleted
        on_roster = practice._read_roster(self.folder)  # sealed again: it reads whole
        self.assertLessEqual(old | {self.hidden}, {c for c, _ in on_roster})
        self.assertIsNone(practice.broken_record(self.folder))
        again = self.practise(NAME, 20, 10)
        self.assertFalse(set(again["held_out_cards"]) & old)  # the new test set is new customers


class OldFolder(Base):
    practise = testset.Kept.practise

    def test_an_old_folder_has_its_roster_built_once_from_its_matches(self):
        folder = self.folders[OLD]
        old = ["persona-01", "persona-02", "persona-03"]
        (folder / run.MATCHES_FILE).write_text("".join(  # lines from before the seal and the roster
            json.dumps({"id": f"old-r1-t{n:02d}", "card": c, "persona": {"id": c}}) + "\n"
            for n, c in enumerate(old, 1)), encoding="utf-8")
        self.assertFalse((folder / practice.ROSTER_FILE).exists())
        self.assertEqual({c for c, _ in practice.trained(folder)}, set(old))  # read with no roster
        rep = self.practise(OLD, 20, 10)
        self.assertFalse(set(rep["held_out_cards"]) & set(old))
        on_roster = practice._read_roster(folder)
        self.assertLessEqual({(c, practice._ANY) for c in old}, on_roster)  # any card: the id counts
        (folder / run.MATCHES_FILE).write_text("", encoding="utf-8")  # every line deleted later
        self.assertLessEqual({(c, practice._ANY) for c in old}, practice.trained(folder))
        again = self.practise(OLD, 20, 10)
        self.assertFalse(set(again["held_out_cards"]) & set(old))


    def test_the_roster_is_built_before_any_model_call(self):
        folder = self.folders[OLD]
        (folder / run.MATCHES_FILE).write_text(json.dumps({"id": "old-r1-t01", "card": "persona-01"}) + "\n",
                                               encoding="utf-8")

        class Down:
            asks = []

            def chat(self, *a, **kw):
                raise ModelError("the writer did not answer")
        with self.assertRaises(ModelError):
            self.practise(OLD, 20, 10, writer=Down())
        self.assertEqual(practice._read_roster(folder), {("persona-01", practice._ANY)})


class Page(test_levels_tab.Tab):
    """The roster's refusal on the Arena tab: the same note and Start a new test set."""
    run_page = r3.Record.run_page
    old_customers = r3.Record.old_customers
    check_way_on = r3.Record.check_way_on

    def test_an_edited_roster_offers_the_way_on(self):
        self.run_page()
        roster = self.folder / practice.ROSTER_FILE
        doc = json.loads(roster.read_text(encoding="utf-8"))
        doc["trained"] = doc["trained"][1:]
        roster.write_text(json.dumps(doc), encoding="utf-8")
        self.run_page()
        self.check_way_on(practice.ROSTER_FILE)
        self.assertTrue(list(self.folder.glob("trained-before-*.json")))

    def test_a_deleted_roster_offers_the_way_on(self):
        self.run_page()
        (self.folder / practice.ROSTER_FILE).unlink()
        self.run_page()
        self.check_way_on(practice.ROSTER_FILE)
