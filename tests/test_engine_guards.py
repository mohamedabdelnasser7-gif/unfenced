"""Guards in engine/ that the step tests did not reach, found by the mutant sweep of task
t261029a: each test here fails when its guard is taken out."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import plug, risk
from engine.lessons import Lessons as EngineLessons, in_share, slot
from engine.log import Log
from sales import loop, stages
from kit.db import Db
from reflection import PLUG
from tests import plugs
from tests.kept import kept_lesson


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


class PlugFile(unittest.TestCase):
    def bad(self, data, words):
        with self.assertRaises(ValueError) as cm:
            plug.from_dict(data)
        self.assertIn(words, str(cm.exception))

    def test_each_refusal_says_what_is_wrong(self):
        w = plugs.WATERER
        self.bad([], "one JSON object")
        self.bad("waterer", "one JSON object")
        for days in ([3], [1, 3, 9]):
            with self.subTest(days=days):
                self.bad(plugs.changed(w, results={"grew": {"speed": "slow", "shows_in_days": days}}),
                         "shows_in_days is [least, most]")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plug.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                plug.load(path)
            self.assertIn("not JSON", str(cm.exception))

    def test_trial_levels_days_and_keys(self):
        """Call 16: two levels, fast and careful, each {share, days}; unknown keys refused, share
        more than 0 and under 1, whole days from 1."""
        w = plugs.WATERER

        def both(**level):  # the waterer's two levels with one changed
            return plugs.changed(w, trial=dict(w["trial"], **level))

        for days in (0, -1, 1.5, True, "7", None):
            with self.subTest(days=days):
                self.bad(both(fast={"share": 0.5, "days": days}), "trial fast days")
        for share in (0, 1, -0.1, 1.5, "0.2", None):
            with self.subTest(share=share):
                self.bad(both(careful={"share": share, "days": 14}), "trial careful share")
        self.bad(both(careful={"share": 0.2, "days": 14, "start": 1}), "unknown key 'start'")
        self.bad(both(careful={"share": 0.2}), "missing 'days'")
        self.bad(both(careful={"days": 14}), "missing 'share'")
        self.bad(both(careful={}), "trial careful: an object")
        self.bad(both(slow={"share": 0.2, "days": 14}), "unknown key 'slow'")
        self.bad(plugs.changed(w, trial={"share": 0.5, "days": 7}), "fast and careful")
        self.bad(both(days=7), "fast and careful")
        self.bad(plugs.changed(w, low_per_night=3), "no nightly cap")

    def test_both_trial_levels_are_required_and_load_from_the_plug(self):
        """The plug is the only home of the two levels: the engine has no default for them."""
        w = plugs.WATERER
        both = {n: (lv.share, lv.days) for n, lv in plugs.load(w, self).levels.items()}
        self.assertEqual(both, {"fast": (0.8, 3), "careful": (0.5, 7)})
        hint = "the owner sets both trial levels here, fast and careful, each {share, days}"
        self.bad(plugs.changed(w, trial={"fast": {"share": 0.6, "days": 1}}), "trial: missing 'careful': " + hint)
        self.bad(plugs.changed(w, trial={"careful": {"share": 0.2, "days": 14}}), "trial: missing 'fast': " + hint)
        self.bad(plugs.changed(w, trial={"holdback": 0.1}), "trial: missing 'careful'")
        bare = dict(w)
        bare.pop("trial")
        self.bad(bare, "the plug: missing 'trial': " + hint)
        with self.assertRaises(ValueError):
            plugs.load(w, self).level("slow")
        root = Path(__file__).resolve().parent.parent
        for path in (root / "sales" / "plug.json", root / "marketing" / "plug.json"):
            with self.subTest(plug=path.parent.name):
                levels = plug.load(path).levels
                self.assertEqual({n: (lv.share, lv.days) for n, lv in levels.items()},
                                 {"fast": (0.5, 7), "careful": (0.2, 14)})

    def test_a_list_is_a_list(self):
        """A stage list written as one word would read as one stage per letter."""
        w = plugs.WATERER
        self.bad(plugs.changed(w, stages="seedling"), "a list")
        self.bad(plugs.changed(w, fields="gardening"), "a list")
        risk_list = copy.deepcopy(w["risk"])
        risk_list["high"]["tools"] = "sprayer"
        self.bad(plugs.changed(w, risk=risk_list), "a list")

    def test_actions_and_causes_cannot_be_changed_after_loading(self):
        p = plugs.load(plugs.WATERER, self)
        with self.assertRaises(TypeError):
            p.actions["dig"] = "Dig the bed."
        with self.assertRaises(TypeError):
            p.causes["hail"] = "Hail."
        self.assertNotIn("dig", PLUG.actions)


class LogGuards(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.log = Log(self.db, plugs.load(plugs.WATERER, self))

    def test_an_action_refuses_a_cause_its_plug_did_not_declare(self):
        with self.assertRaises(ValueError):
            self.log.act("bed-1", "water", result="soaked", cause="hail")
        self.assertEqual(self.log.query(), [])

    def test_the_database_refuses_a_cause_with_no_result(self):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute("INSERT INTO trace (agent, case_id, action, cause, at) "
                          "VALUES ('waterer', 'bed-1', 'water', 'frost', 1)")


class RiskForms(unittest.TestCase):
    """Each form a number or a risk word can take still reads as high on the code check alone."""

    def test_still_high(self):
        for text in ("Say ௰ EGP for the pair.",        # a number sign with no digit value, as an amount
                     "Say ፻ for both.",
                     "قول إن التوصيل بُكْرَة.",          # short vowels over a listed word
                     "Tell them the ｄｉｓｃｏｕｎｔ first.",  # wide letters
                     "Give them ﬁve pounds off.",        # a joined fi
                     "Say it comes on  time."):          # two spaces inside a listed phrase
            with self.subTest(text=text):
                self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)


class LessonTableGuards(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.lessons = EngineLessons(self.db, PLUG, judge=always_low)
        self.high = self.lessons.propose("Tell them delivery is 500.", ["asking"], sources=[])
        self.tone = self.lessons.propose("Greet them warmly.", ["all"], sources=[])

    def refused(self, sql, *args):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute(sql, args)

    def test_a_yes_has_both_its_name_and_its_time(self):
        self.refused("UPDATE lessons SET yes_by = 'mohamed' WHERE id = ?", self.high)
        self.refused("UPDATE lessons SET yes_at = 1 WHERE id = ?", self.tone)

    def test_share_risk_and_state_stay_in_their_ranges(self):
        for share in (0, 1.5, -1):
            with self.subTest(share=share):
                self.refused("UPDATE lessons SET share = ? WHERE id = ?", share, self.tone)
        self.refused("INSERT INTO lessons (agent, text, stages, fields, risk, state, added_at) "
                     "VALUES ('sales', 'Greet them.', ',all,', ',retail,', 'medium', 'waiting', 1)")
        self.refused("UPDATE lessons SET state = 'live' WHERE id = ?", self.tone)
        self.assertEqual((self.lessons.get(self.tone)["share"], self.lessons.get(self.tone)["state"]),
                         (PLUG.level("careful").share, "trying"))


class PickGuards(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.lessons = EngineLessons(self.db, PLUG, judge=always_low)

    def test_never_more_than_8_whatever_the_limit(self):
        for i in range(12):
            kept_lesson(self.lessons, f"Tone note {chr(97 + i)}.", ["all"], yes_by="team")
        self.assertEqual(len(self.lessons.pick("asking", "", limit=20)), 8)
        given = set()
        self.assertEqual(len(self.lessons.hand("chat-1", "reply", "asking", "", given, limit=20)), 8)
        self.assertEqual(len(given), 8)

    def test_no_case_gets_no_lesson_on_trial(self):
        self.assertFalse(any(in_share(None, i, 0.99) for i in range(1, 300)))
        lid = self.lessons.propose("Tell them delivery is 500.", ["all"], sources=[])
        self.assertTrue(self.lessons.approve(lid, "mohamed", share=0.99))
        self.assertEqual(self.lessons.pick("asking", "", case=None), [])
        self.assertEqual(self.lessons.pick("asking", "", case="chat-1")[0]["id"], lid)

    def test_no_lessons_means_no_slot_line(self):
        self.assertEqual(slot(PLUG, []), "")
        prompt = loop.system_prompt(stages.STAGES["asking"], [])["content"]
        self.assertNotIn(PLUG.slot, prompt)
        self.assertIn(PLUG.slot, loop.system_prompt(stages.STAGES["asking"], [{"text": "Greet them."}])["content"])


if __name__ == "__main__":
    unittest.main()
