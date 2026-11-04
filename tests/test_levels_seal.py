"""Each match line and test-set.json carry the run's seal (DECISIONS item 90, red team levels r3 items 1
and 2; arena/practice.py Practice.save, is_test, read_test, write_test): a line counts as a test match
only while its seal holds with the key beside the gate item (reports_of), so a training line relabelled
as a test match, a test line written by hand or a line given another line's seal still counts as
training; a test-set.json edited or written by hand is rebuilt from customers that never trained; old
lines and an old test-set.json with no seal count as training and are rebuilt. Fake models only."""
import json

from arena import madeup, practice, run
from kit import seal, turn
from tests.test_customers_shape import Base, Writer
from tests import test_levels_testset as testset  # the module, so its tests are not run twice

NAME = "support_calm_helper"


class Sealed(Base):
    practise = testset.Kept.practise

    def setUp(self):
        super().setUp()
        self.folder = self.folders[NAME]
        self.first = self.practise(NAME, 20, 10)
        self.path = self.folder / run.MATCHES_FILE
        self.rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines()]
        held = set(self.first["held_out_cards"])
        # a training customer that could reach the good result: the one an attacker would hide
        self.hidden = next(m["card"] for m in self.rows if m[practice.TEST_KEY] is False
                           and m["card"] not in held and not m["persona"].get("unwinnable"))
        self.from_card = next(m["persona"]["from_card"] for m in self.rows if m["card"] == self.hidden)

    def rewrite(self, change):
        """The matches file with each of the hidden customer's lines put through change(row)."""
        out = [change(dict(m)) if m["card"] == self.hidden else m for m in self.rows]
        self.path.write_text("".join(json.dumps(m) + "\n" for m in out), encoding="utf-8")

    def relabel(self, m):
        m["id"], m[practice.TEST_KEY] = m["id"].rsplit("-", 1)[0] + "-g99", True
        return m

    def assert_still_trained(self):
        done = practice.trained(self.folder)
        self.assertIn((self.hidden, self.from_card), done)
        cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.folder / madeup.FOLDER).glob("*.json"))]
        held = practice.fixed_test(cards, 10, [(self.hidden, self.from_card)], done, practice.shape_mix(20))[0]
        self.assertNotIn(self.hidden, held or [])

    def test_the_run_seals_every_line_and_a_real_test_line_holds(self):
        k = seal.key(practice.reports_of(self.folder))
        self.assertIsNotNone(k)
        self.assertTrue(all(seal.holds(m, k) for m in self.rows))
        tests = {m["card"] for m in self.rows if practice.is_test(m, k)}
        self.assertEqual(tests, set(self.first["held_out_cards"]))
        self.assertFalse(set(self.first["held_out_cards"]) & {c for c, _ in practice.trained(self.folder)})

    def test_a_training_line_relabelled_as_a_test_match_still_counts_as_training(self):
        self.rewrite(self.relabel)  # the old seal kept on the changed line
        self.assert_still_trained()

    def test_a_test_line_written_by_hand_counts_as_training(self):
        for mark in (None, "0" * 64, 7):
            with self.subTest(seal=mark):
                def by_hand(m):
                    m = self.relabel(m)
                    m.pop(seal.FIELD)
                    if mark is not None:
                        m[seal.FIELD] = mark
                    return m
                self.rewrite(by_hand)
                self.assert_still_trained()

    def test_a_seal_copied_from_a_real_test_line_does_not_hold(self):
        real = next(m for m in self.rows if m[practice.TEST_KEY] is True)

        def copied(m):
            m = self.relabel(m)
            m[seal.FIELD] = real[seal.FIELD]
            return m
        self.rewrite(copied)
        self.assert_still_trained()

    def test_a_key_that_is_gone_makes_every_line_training(self):
        (practice.reports_of(self.folder) / seal.KEY_FILE).unlink()
        done = {c for c, _ in practice.trained(self.folder)}
        self.assertLessEqual(set(self.first["held_out_cards"]), done)

    def test_an_old_line_with_the_field_and_no_seal_counts_as_training(self):
        def old(m):
            m = self.relabel(m)
            m.pop(seal.FIELD)
            return m
        self.rewrite(old)
        self.assert_still_trained()
        again = self.practise(NAME, 20, 10)  # the run goes on, old lines read as training
        self.assertNotIn(self.hidden, again["held_out_cards"])


class SealedTestSet(Base):
    practise = testset.Kept.practise

    def chosen(self, folder, cards):
        """8 easy, 8 unsure and 4 hard (the kinds the shape wants, so only the seal can refuse them), the
        last of each kind by test_set's order, never the ones a rebuild picks."""
        out = []
        for kind, n in practice.shape_mix(30).items():
            out += sorted((c for c in cards if c["kind"] == kind), key=practice._rank)[-n:]
        return sorted(c["id"] for c in out)

    def test_a_test_set_written_or_edited_by_hand_is_rebuilt_from_customers_that_never_trained(self):
        for how in ("hand written", "edited, the old seal kept", "old format"):
            with self.subTest(how=how):
                folder = self.folders[NAME]
                for p in (folder / practice.TEST_FILE, folder / run.MATCHES_FILE):
                    p.unlink(missing_ok=True)
                cards, _ = madeup.for_agent(folder, NAME, turn.load(folder).card, Writer(), count=30)
                by_id = {c["id"]: c for c in cards}
                want = self.chosen(folder, cards)
                rebuilt = practice.fixed_test(cards, 20, [], set(), practice.shape_mix(30))[0]
                self.assertNotEqual(want, rebuilt)
                body = {"test": [{"id": i, "from_card": by_id[i]["from_card"]} for i in want]}
                if how == "edited, the old seal kept":
                    practice.write_test(folder, [(i, by_id[i]["from_card"]) for i in rebuilt])
                    body[seal.FIELD] = json.loads((folder / practice.TEST_FILE).read_text(encoding="utf-8"))[seal.FIELD]
                elif how == "hand written":
                    body[seal.FIELD] = "f" * 64
                (folder / run.MATCHES_FILE).touch()
                (folder / practice.TEST_FILE).write_text(json.dumps(body), encoding="utf-8")
                self.assertEqual(practice.read_test(folder), [])
                rep = self.practise(NAME, 30, 20)
                self.assertEqual(rep["held_out_cards"], rebuilt)
                self.assertNotEqual(rep["held_out_cards"], want)
                self.assertEqual([i for i, _ in practice.read_test(folder)], rebuilt)  # sealed again by the run

    def test_the_run_keeps_its_own_sealed_test_set(self):
        first = self.practise(NAME, 20, 10)
        saved = practice.read_test(self.folders[NAME])
        self.assertEqual(sorted(i for i, _ in saved), first["held_out_cards"])
        self.assertEqual(self.practise(NAME, 20, 10)["held_out_cards"], first["held_out_cards"])


if __name__ == "__main__":
    import unittest
    unittest.main()
