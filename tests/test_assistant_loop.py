"""The assistant's loop on a simulated day (new, 2026-10-31)."""
import json
import unittest

from assistant import PLUG, arena, loop, simday
from assistant.desk import Desk
from assistant.modes import Modes
from engine.lessons import Lessons
from engine.log import Log
from kit.db import Db
from kit.model import ModelError
from tests.assistant_fakes import Helper, Silent
from tests.fake_model import FakeModel, say, tool_call


class Day(unittest.TestCase):
    def test_a_good_assistant_wins_the_day_and_the_model_never_sees_hidden(self):
        day = simday.build_day(1)
        model = Helper()
        desk, _, judged = arena.play_day(day, model=model)
        self.assertTrue(judged["won"], judged["failed"])
        sent_to_model = json.dumps([c["messages"] for c in model.calls])
        self.assertNotIn("hidden", sent_to_model)
        self.assertNotIn("urgent\": true", sent_to_model)
        self.assertTrue(desk.sent)
        for c in model.calls:
            names = [t["function"]["name"] for t in c["tools"] or []]
            self.assertNotIn("send", names)

    def test_every_send_follows_a_yes_from_the_user(self):
        desk, _, _ = arena.play_day(simday.build_day(2), model=Helper())
        for row in desk.sent:
            yes = [y for y in desk.yeses if y["draft"] == row["draft"]]
            self.assertTrue(yes and yes[0]["seq"] < row["seq"] and yes[0]["by"] == "user")
        self.assertEqual(len(desk.sent), len([a for a in desk.answers if a["kind"] in ("used", "edited") and "draft" in a["made"]]))

    def test_long_drafts_in_rushed_are_corrected_and_never_sent(self):
        day = simday.build_day(4)
        desk, _, judged = arena.play_day(day, model=Helper(long_drafts=True))
        rushed = [d for d in desk.drafts.values() if simday.mode_at(day, d["at"]) == "rushed"]
        self.assertTrue(rushed)
        self.assertTrue(all(d["state"] == "draft" for d in rushed if simday.find_item(day, d["item"])["hidden"]["reply"]))
        self.assertIn("corrected", [a["kind"] for a in desk.answers])
        self.assertFalse(judged["checks"]["mode"])

    def test_the_mode_is_shown_to_the_model_with_each_item(self):
        model = Helper()
        arena.play_day(simday.build_day(5), model=model)
        modes = [c["messages"][0]["content"].split("Current mode: ")[1].split(" ")[0] for c in model.calls]
        self.assertIn("rushed", modes)
        self.assertIn("off", modes)

    def test_a_model_that_does_not_answer_raises(self):
        with self.assertRaises(ModelError):
            arena.play_day(simday.build_day(1), model=Silent())

    def test_the_users_style_and_lessons_reach_the_prompt(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        log = Log(db, PLUG)
        lessons = Lessons(log.db, PLUG)
        lid = lessons.add("In rushed mode keep drafts to two lines.", ["rushed"], "seed", yes_by="user",
                          skip_exam=True)
        lessons.keep(lid)
        events = [{"type": "user_says", "at": "10:00", "text": "slammed today"},
                  {"type": "item", "at": "10:05", "id": "i1", "kind": "email", "from": "maya@northwind.test",
                   "subject": "Deck", "body": "Which one?"}]
        d = Desk(items=[events[1]], calendar=[], rules={}, user_address="u@demo.test", date="2026-11-02", log=log,
                 case="day:2026-11-02")
        model = FakeModel(say("Quiet morning."), say("ok"))

        class User:
            name = "user"

            def on_brief(self, text, mode):
                return "used", None

        loop.run_day(events, model=model, desk=d, modes=Modes(), user=User(), lessons=lessons,
                     style={"median_words": 12, "greeting": "Hi", "sign_off": "Thanks, Nadia"})
        system = model.calls[1]["messages"][0]["content"]
        self.assertIn("Current mode: rushed", system)
        self.assertIn("In rushed mode keep drafts to two lines.", system)
        self.assertIn("opens with 'Hi'", system)
        self.assertIn(lid, d.lessons)

    def test_tool_steps_are_capped(self):
        many = [tool_call("sort", {"item": "i1", "bucket": "later", "tell": False})] * (loop.MAX_TOOL_STEPS + 2)
        model = FakeModel(say("brief"), *many)
        events = [{"type": "item", "at": "10:05", "id": "i1", "kind": "email", "from": "a@x.test", "subject": "s",
                   "body": "b"}]
        d = Desk(items=events, calendar=[], rules={}, user_address="u@demo.test", date="2026-11-02")

        class User:
            name = "user"

            def on_brief(self, text, mode):
                return "used", None

        loop.run_day(events, model=model, desk=d, modes=Modes(), user=User())
        self.assertEqual(len(d.calls), loop.MAX_TOOL_STEPS)

    def test_view_drops_hidden(self):
        self.assertEqual(loop.view({"id": "i1", "body": "b", "hidden": {"urgent": True}, "x": 1}), {"id": "i1", "body": "b"})


if __name__ == "__main__":
    unittest.main()
