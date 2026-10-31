"""New modes per user (new, 2026-10-31): noted moments, a proposal tested in the Arena, one card,
and the user's yes, rename or drop; no answer changes nothing."""
import json
import tempfile
import unittest
from pathlib import Path

from assistant import arena, newmode, simday
from assistant.modes import Modes
from tests.assistant_fakes import Helper


def moments(*rows):
    return [{"said": s, "date": d} for s, d in rows]


TRAVEL = moments(("at the airport, travelling all day", "2026-11-02"), ("travelling again today", "2026-11-05"),
                 ("still travelling, short replies", "2026-11-09"), ("month end close", "2026-11-30"))


class Propose(unittest.TestCase):
    def test_moments_that_share_a_word_on_two_days_become_a_candidate(self):
        cands = newmode.propose(TRAVEL)
        self.assertEqual(cands[0]["name"], "travell")  # the user's own word, stemmed, never a preset
        self.assertEqual((cands[0]["moments"], cands[0]["days"]), (3, 3))
        self.assertIn("travelling", cands[0]["words"])
        self.assertEqual([c for c in cands if c["name"] == "month"], [])  # once is not enough

    def test_known_dropped_and_default_names_are_never_proposed(self):
        self.assertEqual(newmode.propose(TRAVEL, dropped=["travell"]), [])
        self.assertEqual(newmode.propose(TRAVEL, known=["travell"]), [])
        off = moments(("off sick", "2026-11-02"), ("off sick again", "2026-11-03"), ("off sick", "2026-11-04"))
        self.assertNotIn("off", [c["name"] for c in newmode.propose(off)])

    def test_one_day_is_not_enough(self):
        same = moments(*[("travelling", "2026-11-02")] * 5)
        self.assertEqual(newmode.propose(same), [])


class Night(unittest.TestCase):
    def play(self, day, added):
        """The real loop on a past day; an added mode makes the long-draft agent's words fit it."""
        _, _, judged = arena.play_day(day, model=self.model, added=added)
        return judged["won"]

    def test_the_arena_counts_fixed_and_broken_days(self):
        counts = newmode.arena_test({"name": "x", "words": ["x"]}, [1, 2, 3], lambda day, added: bool(added) or day == 3)
        self.assertEqual((counts["fixed"], counts["broken"], counts["passed"]), (2, 0, True))
        counts = newmode.arena_test({"name": "x", "words": ["x"]}, [1, 2], lambda day, added: (day == 1) != bool(added))
        self.assertEqual((counts["fixed"], counts["broken"], counts["passed"]), (1, 1, False))

    def test_a_mode_from_the_loop_reaches_the_moments_file(self):
        day = simday.build_day(4, own_mode="travel")
        _, modes, _ = arena.play_day(day, model=Helper())
        self.assertTrue(any("travelling" in m["said"] for m in modes.unfit))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(newmode.keep_moments(d, modes.unfit), len(modes.unfit))
            self.assertEqual(newmode.read_moments(d)[0]["said"], modes.unfit[0]["said"])

    def test_the_night_writes_one_card_and_none_while_it_waits(self):
        with tempfile.TemporaryDirectory() as d:
            newmode.keep_moments(d, TRAVEL)
            path = newmode.night(d, [1, 2], lambda day, added: bool(added), now=1_800_000_000)
            card = json.loads(path.read_text())
            self.assertEqual((card["kind"], card["name"], card["choices"]), ("mode_card", "travell", ["yes", "rename", "drop"]))
            self.assertEqual(card["arena"]["fixed"], 2)
            self.assertTrue(path.name.startswith("mode-assistant-"))
            self.assertNotIn("line", card)  # the words the user reads are written when shown, never fixed here
            self.assertIsNone(newmode.night(d, [1, 2], lambda day, added: bool(added), now=1_800_000_100))
            self.assertEqual(newmode.read_modes(d), {"added": [], "dropped": []})  # no answer, nothing changed

    def test_a_candidate_that_breaks_a_day_gets_no_card(self):
        with tempfile.TemporaryDirectory() as d:
            newmode.keep_moments(d, TRAVEL)
            self.assertIsNone(newmode.night(d, [1, 2], lambda day, added: (day == 1) != bool(added)))

    def test_yes_rename_and_drop(self):
        with tempfile.TemporaryDirectory() as d:
            cand = newmode.propose(TRAVEL)[0]
            counts = {"fixed": 1, "broken": 0}
            c1 = newmode.write_card(d, cand, counts, now=1)
            out = newmode.answer_card(c1, d, "rename", name="Travel", by="user")
            self.assertEqual(out["added"][0]["name"], "travel")
            with self.assertRaises(ValueError):
                newmode.answer_card(c1, d, "yes", by="user")  # answered already
            c2 = newmode.write_card(d, dict(cand, name="month"), counts, now=2)
            self.assertEqual(newmode.answer_card(c2, d, "drop", by="user")["dropped"], ["month"])
            c3 = newmode.write_card(d, dict(cand, name="travel"), counts, now=3)
            with self.assertRaises(ValueError):
                newmode.answer_card(c3, d, "yes", by="user")  # there is a travel mode already
            with self.assertRaises(ValueError):
                newmode.answer_card(c3, d, "rename", name="9 lives!", by="user")
            with self.assertRaises(ValueError):
                newmode.answer_card(c3, d, "maybe", by="user")
            modes = Modes(added=newmode.read_modes(d)["added"])
            self.assertEqual(modes.pick({"time": "10:00"}, said="travelling today"), "travel")

    def test_an_added_mode_fixes_an_own_mode_day_in_the_arena(self):
        day = simday.build_day(4, own_mode="travel")

        class ShortWhenTravel(Helper):
            def _draft(self, it):
                return super()._draft(it)

        self.model = Helper()
        added = [{"name": "travel", "words": ["travelling", "airport"]}]
        _, modes, judged = arena.play_day(day, model=self.model, added=added)
        self.assertEqual(modes.unfit, [])  # the words now fit a mode
        self.assertTrue(judged["won"])


if __name__ == "__main__":
    unittest.main()
