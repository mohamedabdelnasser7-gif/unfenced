"""Modes and setup (new, 2026-10-31): the mode is picked, shown and corrected; the setup reply is
the model's own words from two intents, checked through a fake model, never by exact text."""
import json
import unittest

from assistant import PLUG, setup
from assistant.desk import Desk
from assistant.modes import Modes
from engine.log import Log
from kit.db import Db
from tests.fake_model import FakeModel, say


class Picker(unittest.TestCase):
    def test_the_users_word_wins_and_holds_until_working_hours_end(self):
        m = Modes()
        self.assertEqual(m.pick({"time": "10:00"}, said="slammed today, keep it short"), "rushed")
        self.assertEqual(m.shown(), {"mode": "rushed", "why": "the user said so", "by": "user"})
        self.assertEqual(m.pick({"time": "11:00", "focus_block": True}), "rushed")  # signals do not override the user
        self.assertEqual(m.pick({"time": "18:30"}), "off")  # working hours ended

    def test_signals_pick_a_mode_when_the_user_said_nothing(self):
        m = Modes({"work_start": "08:00", "work_end": "17:00", "short_reply_words": 6})
        self.assertEqual(m.pick({"time": "07:30"}), "off")
        self.assertEqual(m.pick({"time": "09:00", "focus_block": True}), "focused")
        self.assertEqual(m.pick({"time": "10:00", "reply_words": 4, "reply_minutes": 1}), "rushed")
        self.assertEqual(m.shown()["why"], "short, fast replies")
        self.assertEqual(m.pick({"time": "10:30", "reply_words": 30, "reply_minutes": 40}), "rushed")  # no new sign
        self.assertEqual(m.pick({"time": "11:00", "in_meeting": True}), "focused")

    def test_words_match_whole_words_only(self):
        m = Modes()
        self.assertIsNone(m.from_words("I took an offer"))
        self.assertEqual(m.from_words("Signing off now"), "off")
        self.assertEqual(m.from_words("heads down for an hour"), "focused")

    def test_a_correction_goes_to_the_log_and_an_unknown_mode_is_noted(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        log = Log(db, PLUG)
        d = Desk(items=[], calendar=[], rules={}, user_address="u@demo.test", date="2026-11-02", log=log,
                 case="day:2026-11-02")
        m = Modes()
        m.pick({"time": "10:00"})
        self.assertEqual(m.correct("rushed", desk=d), "rushed")
        self.assertEqual(d.mode, "rushed")
        self.assertEqual(m.correct("travel", desk=d, said="travelling", date="2026-11-02"), "rushed")
        self.assertEqual(m.unfit[-1]["named"], "travel")
        rows = log.case("day:2026-11-02")
        self.assertEqual([r["result"] for r in rows], ["corrected", "corrected"])
        self.assertEqual(rows[0]["detail"]["made"], {"mode": "focused"})

    def test_words_that_fit_no_mode_are_noted(self):
        m = Modes()
        m.pick({"time": "09:30"}, said="at the airport now, travelling all day", at="09:30", date="2026-11-02")
        self.assertEqual(m.current, "focused")
        self.assertEqual(m.unfit[0]["said"], "at the airport now, travelling all day")

    def test_an_added_mode_is_picked_by_its_words(self):
        m = Modes(added=[{"name": "travel", "words": ["travelling", "airport"]}])
        self.assertEqual(m.pick({"time": "09:30"}, said="at the airport"), "travel")
        self.assertIn("travel", m.names)


def answer(reply, carries):
    return say(json.dumps({"reply": reply, "carries": carries}))


class Setup(unittest.TestCase):
    ASK = "I want to build a personal assistant to organize my email and my day"

    def test_the_trigger(self):
        self.assertTrue(setup.wants(self.ASK))
        self.assertTrue(setup.wants("can you be my personal assistant?"))
        self.assertTrue(setup.wants("an assistant for my calendar"))
        self.assertFalse(setup.wants("what is the weather"))
        self.assertFalse(setup.wants(""))

    def test_any_wording_that_carries_both_intents_passes(self):
        for reply, learn, offer in [
            ("Happy to help! Tell me a bit about your work and your days. Want to connect your email? Most of a "
             "working day passes through it, but you can skip it and add it later.",
             "Tell me a bit about your work and your days.", "Want to connect your email?"),
            ("Sounds good. What does a normal day look like for you? If you like, link your inbox, since most work "
             "runs through it; it's optional.", "What does a normal day look like for you?",
             "If you like, link your inbox, since most work runs through it; it's optional."),
        ]:
            model = FakeModel(answer(reply, {"learn_about_user": learn, "offer_email": offer}))
            out = setup.reply(self.ASK, model=model)
            self.assertEqual(out["reply"], reply)
            self.assertEqual(out["intents"], ["learn_about_user", "offer_email"])
            sent = model.calls[0]["messages"][0]["content"]
            self.assertIn("learn_about_user", sent)
            self.assertIn("offer_email", sent)
            self.assertIn("most of a working day", sent)

    def test_a_reply_missing_an_intent_is_retried_then_refused(self):
        bad = answer("Tell me about you.", {"learn_about_user": "Tell me about you."})
        good = answer("Tell me about you. Connecting email helps, most of a day is there, and it is up to you.",
                      {"learn_about_user": "Tell me about you.",
                       "offer_email": "Connecting email helps, most of a day is there, and it is up to you."})
        model = FakeModel(bad, good)
        self.assertIn("Connecting email", setup.reply(self.ASK, model=model)["reply"])
        self.assertIn("no sentence carries offer_email", model.calls[1]["messages"][-1]["content"])
        with self.assertRaises(setup.SetupError):
            setup.reply(self.ASK, model=FakeModel(bad, bad))

    def test_a_quote_not_in_the_reply_or_a_must_fails(self):
        self.assertEqual(setup.check({"reply": "Hi there.", "carries": {"learn_about_user": "Who are you?"}},
                                     ["learn_about_user"]), "the sentence for learn_about_user is not in the reply")
        must = {"reply": "Tell me more. You must connect your email first.",
                "carries": {"learn_about_user": "Tell me more.", "offer_email": "You must connect your email first."}}
        self.assertIn("must", setup.check(must, ["learn_about_user", "offer_email"]))
        self.assertEqual(setup.check(None, ["learn_about_user"]), "no reply")
        with self.assertRaises(setup.SetupError):
            setup.reply(self.ASK, model=FakeModel(say("not json"), say("```\n{}\n```")))

    def test_with_email_connected_only_the_learn_intent_is_needed(self):
        model = FakeModel(answer("Email is connected. Tell me how your week runs.",
                                 {"learn_about_user": "Tell me how your week runs."}))
        self.assertEqual(setup.reply(self.ASK, model=model, has_email=True)["intents"], ["learn_about_user"])

    def test_start_without_email_uses_the_defaults_and_with_a_picture_its_modes(self):
        s = setup.start("I run a studio")
        self.assertEqual((s["email"], s["modes"].work_start, s["about"]), (False, "09:00", "I run a studio"))
        pic = {"starting_modes": {"work_start": "08:00", "work_end": "17:00", "short_reply_words": 5},
               "style": {"greeting": "Hi"}}
        s2 = setup.connect(setup.start("x", added=[{"name": "travel", "words": ["airport"]}]), pic)
        self.assertEqual((s2["email"], s2["modes"].work_end, s2["style"]["greeting"]), (True, "17:00", "Hi"))
        self.assertIn("travel", s2["modes"].names)


if __name__ == "__main__":
    unittest.main()
