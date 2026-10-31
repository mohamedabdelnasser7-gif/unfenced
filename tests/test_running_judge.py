"""Task t261029s gap 1: the running Sales agent gives its lessons the Meta risk judge
(reflection/judge.py), not the engine's stub. It fails closed: when the judge cannot run (no
key, an error, an odd answer) a lesson counts as high and waits for a yes, as before. No test
touches the network or opens the repo's database."""
import itertools
import os
import unittest
import uuid
from unittest import mock

from channels import whatsapp as wa
from engine import lessons as engine_lessons
from engine import risk
from kit import model as kit_model
from kit.chats import Chats
from kit.db import Db
from kit.limits import Limits
from reflection import PLUG
from reflection.judge import Judge
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, clean_env, say
from tests.test_model_routes import env_with
from tests.test_whatsapp import payload, text_msg
from tests.kept import kept_lesson

TONE = "Greet them warmly before anything else."
TRIAL = "Ask which colour they like before anything else."


class Stop(Exception):
    pass


def lessons_main_builds(test):
    """The Lessons main() hands the App, with every key set and no server, no database file."""
    full = {**{n: "set" for n in wa.REQUIRED_ENV}, "OPERATOR_WHATSAPP": "201000000001"}
    db = Db(":memory:")
    test.addCleanup(db.close)
    with mock.patch.dict(os.environ, full, clear=True), mock.patch("kit.env.load", return_value=[]), \
            mock.patch("logging.basicConfig"), mock.patch("sales.loop.warn_size_prices"), \
            mock.patch("kit.db.Db", return_value=db), mock.patch.object(wa, "ThreadingHTTPServer") as server, \
            mock.patch.object(wa, "App", side_effect=Stop) as app:
        with test.assertRaises(Stop):
            wa.main()
    server.assert_not_called()
    return app.call_args.args[2]


class TheRunningPath(unittest.TestCase):
    def test_main_gives_the_lessons_the_meta_judge(self):
        lessons = lessons_main_builds(self)
        self.assertIsInstance(lessons, Lessons)
        self.assertIsInstance(lessons.judge, Judge)
        self.assertIsNot(lessons.judge, risk.no_judge)

    def test_that_judge_asks_muse_spark_open_through_kit_model(self):
        judge = lessons_main_builds(self).judge
        env_with(self, BASETEN_API_KEY="stand-in")
        self.assertIs(judge.model.route, kit_model.OPEN)


class FailsClosed(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def propose(self, judge):
        lessons = Lessons(self.db, judge=judge)
        return lessons.get(lessons.propose(TONE, ["all"], sources=[]))

    def test_a_plain_low_starts_a_trial(self):
        les = self.propose(Judge(FakeModel(say("low"))))
        self.assertEqual((les["risk"], les["state"]), (risk.LOW, "trying"))

    def test_no_key_counts_as_high_and_sends_nothing(self):
        env_with(self)  # no BASETEN_API_KEY
        with mock.patch("kit.net.open_once", side_effect=AssertionError("no call without a key")):
            les = self.propose(Judge())
        self.assertEqual((les["risk"], les["state"]), (risk.HIGH, "waiting"))

    def test_an_error_counts_as_high(self):
        def boom(messages, tools=None, **kw):
            raise kit_model.ModelError("Baseten answered 500 Internal Server Error")

        model = FakeModel()
        model.chat = boom
        les = self.propose(Judge(model))
        self.assertEqual((les["risk"], les["state"]), (risk.HIGH, "waiting"))

    def test_an_odd_answer_counts_as_high(self):
        les = self.propose(Judge(FakeModel(say("low, I think"))))
        self.assertEqual((les["risk"], les["state"]), (risk.HIGH, "waiting"))

    def test_the_code_check_still_comes_first(self):
        fake = FakeModel(say("low"))
        lessons = Lessons(self.db, judge=Judge(fake))
        les = lessons.get(lessons.propose("Promise a refund.", ["all"], sources=[]))
        self.assertEqual(les["risk"], risk.HIGH)
        self.assertEqual(fake.calls, [])

    def test_the_stub_stays_the_default(self):
        self.assertIs(Lessons(self.db).judge, risk.no_judge)
        self.assertEqual(PLUG.agent, Lessons(self.db).agent)


class Graph:
    """Stands in for the WhatsApp Graph client: keeps every (to, text) sent."""

    def __init__(self):
        self.sent = []

    def send(self, to, text):
        self.sent.append((to, text))
        return {"ok": True}


class EachReplyKeepsItsLessons(unittest.TestCase):
    """The App built as main() builds it, with the Meta judge: a reply's row keeps the id of
    every lesson the model was given, a team-kept lesson in every chat and a lesson on trial
    only in the chats its share takes (engine.lessons.in_share)."""

    CHATS = 40

    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        ids = itertools.count(1)
        p = mock.patch("kit.chats.uuid.uuid4", side_effect=lambda: uuid.UUID(int=next(ids)))  # fixed chat ids
        p.start()
        self.addCleanup(p.stop)

    def test_the_kept_lesson_always_and_the_trial_lesson_only_in_its_share(self):
        lessons = Lessons(self.db, judge=Judge(FakeModel(say("low"), say("low"))))  # add asks the judge too
        kept = kept_lesson(lessons, TONE, ["all"])
        trial = lessons.propose(TRIAL, ["all"], sources=[])
        les = lessons.get(trial)
        self.assertEqual((les["state"], les["share"]), ("trying", PLUG.level("careful").share))
        model = FakeModel(*[say("Ask me anything.")] * self.CHATS)
        results = Results(self.db)
        app = wa.App(Chats(self.db), model, lessons, results, Graph(), limits=Limits(self.db))
        for n in range(self.CHATS):
            app.accept(wa.parse(payload(text_msg(f"m{n}", "hello there, a question", frm=f"2011111111{n:02d}"))))
            self.assertEqual(app.work_one(app.q.get_nowait()).outcome, "replied")
        rows = results.query(result="replied")
        self.assertEqual(len(rows), self.CHATS)
        shares = []
        for row, call in zip(rows, model.calls):
            in_share = engine_lessons.in_share(row["case_id"], trial, les["share"])
            shares.append(in_share)
            self.assertEqual(row["lessons"], [kept, trial] if in_share else [kept])
            prompt = call["messages"][0]["content"]
            self.assertIn(TONE, prompt)
            self.assertEqual(TRIAL in prompt, in_share)  # the row names what the model was given
        self.assertIn(True, shares)
        self.assertIn(False, shares)


if __name__ == "__main__":
    unittest.main()
