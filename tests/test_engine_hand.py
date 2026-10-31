"""Step 4: the engine hands lessons to an agent's action. In the Sales agent loop a lesson
reaches the prompt only through hand() and the plug's slot, the send check still runs on
every reply after the model, and another agent's lesson never reaches the Sales agent. The
made-up waterer runs the same path with no engine change."""
import unittest
from unittest import mock

from channels.base import Message
from engine import lessons as engine_lessons
from engine import risk
from engine.lessons import Lessons as EngineLessons, in_share, slot
from engine.log import Log
from sales import loop
from kit import send_check
from kit.chats import Chats
from kit.db import Db
from kit.tools import store
from kit.tools.handoff import TAKING_OVER
from reflection import PLUG
from reflection.lessons import Lessons
from reflection.results import Results
from tests import plugs
from tests.fake_model import FakeModel, Outbox, call, clean_env, say
from tests.kept import kept_lesson

CUSTOMER = "201111111111"
OTHER = "201222222222"
OPERATOR = "201000000001"
ASK = "التوصيل بكام؟"
WRONG = "التوصيل بـ 500 جنيه."
CLEAN = "التوصيل حسب المحافظة، قولّي إنت منين؟"
LESSON_500 = "tell them delivery is 500"
TONE = "Greet them warmly before anything else."


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


class LoopCase(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.lessons, self.results = Chats(self.db), Lessons(self.db), Results(self.db)
        self.out = Outbox()

    def turn(self, model, text, customer=CUSTOMER, lessons=None):
        msg = Message(channel="whatsapp", customer_id=customer, text=text)
        return loop.turn(msg, chats=self.chats, model=model, lessons=lessons or self.lessons, results=self.results,
                         send=self.out)

    def rows(self, chat_id):
        return [(r["action"], r["outcome"], r["lessons"]) for r in self.results.for_chat(chat_id)]

    @staticmethod
    def prompts(model):
        return [c["messages"][0]["content"] for c in model.calls]


class SalesTrial(unittest.TestCase):
    """Mohamed's calls: two trial levels the owner edits in setup (call 16), fast at 1 in 2 chats
    for 7 days and careful at 1 in 5 for 14, careful by default; and the slot line does not say
    the team checked lessons it did not check."""

    def test_the_sales_plug(self):
        self.assertEqual({n: (lv.share, lv.days) for n, lv in PLUG.levels.items()},
                         {"fast": (0.5, 7), "careful": (0.2, 14)})
        self.assertEqual(PLUG.slot, "Lessons from past chats:")
        self.assertNotIn("team", PLUG.slot)

    def test_a_low_risk_lesson_goes_live_on_about_1_in_5_chats(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        front = EngineLessons(db, PLUG, judge=always_low)
        lid = front.propose(TONE, ["all"], now=1_800_000_000.0, sources=[])
        les = front.get(lid)
        self.assertEqual((les["risk"], les["state"], les["share"]), ("low", "trying", 0.2))
        live = sum(in_share(f"chat-{i}", lid, les["share"]) for i in range(5000))
        self.assertTrue(900 < live < 1100, live)


class LessonsStillPassTheSendCheck(LoopCase):
    """A lesson the team said yes to cannot loosen the send check: a reply that follows it
    and names an amount the store never gave is still refused."""

    def setUp(self):
        super().setUp()
        amounts, vocab, sizes = store.price_points(), store.vocabulary(), store.size_strings()
        self.assertFalse(send_check.check(WRONG, ASK, amounts, vocab, sizes)[0])
        self.assertTrue(send_check.check(CLEAN, ASK, amounts, vocab, sizes)[0])  # the line it falls back to
        self.lid = self.lessons.propose(LESSON_500, ["all"], sources=[])
        self.assertEqual((self.lessons.get(self.lid)["risk"], self.lessons.get(self.lid)["state"]),
                         ("high", "waiting"))

    def test_a_waiting_lesson_is_not_in_the_prompt(self):
        model = FakeModel(say(CLEAN))
        r = self.turn(model, ASK, customer=OTHER)
        self.assertNotIn(LESSON_500, self.prompts(model)[0])
        self.assertEqual(self.rows(r.chat_id), [("reply", "replied", [])])

    def test_a_lesson_saying_delivery_is_500_is_still_refused(self):
        self.assertTrue(self.lessons.approve(self.lid, "mohamed", share=1))
        model = FakeModel(say(WRONG), say(CLEAN))
        r = self.turn(model, ASK)
        first, second = self.prompts(model)
        self.assertIn("Lessons from past chats:\n- " + LESSON_500, first)
        self.assertIn(LESSON_500, second)
        self.assertEqual(self.out.sent, [(CUSTOMER, CLEAN)])
        self.assertFalse([text for _, text in self.out.sent if "500" in text])
        self.assertIn("500", model.calls[1]["messages"][-1]["content"])  # the check's feedback names it
        self.assertEqual((r.outcome, r.reply), ("replied", CLEAN))
        self.assertEqual(self.rows(r.chat_id),
                         [("reply", "check_failed", [self.lid]), ("reply", "replied", [self.lid])])

    def test_three_500_replies_hand_off_and_none_goes_out(self):
        clean_env(self, OPERATOR_WHATSAPP=OPERATOR)
        self.assertTrue(self.lessons.approve(self.lid, "mohamed", share=1))
        model = FakeModel(say(WRONG), say(WRONG), say(WRONG), say("العميل بيسأل عن التوصيل."))
        r = self.turn(model, ASK)
        self.assertEqual(r.outcome, "handed_off")
        self.assertFalse([text for _, text in self.out.sent if "500" in text])
        self.assertEqual([text for to, text in self.out.sent if to == CUSTOMER], [TAKING_OVER["arabic"]])
        self.assertEqual(self.rows(r.chat_id), [("reply", "check_failed", [self.lid])] * 3
                         + [("hand_off", "handed_off", [self.lid])])
        self.assertTrue(all(LESSON_500 in p for p in self.prompts(model)[:3]))


class TheLoopAsksTheEngine(LoopCase):
    def test_each_model_step_calls_hand_with_the_chat_the_action_the_stage_and_one_set(self):
        asking = kept_lesson(self.lessons, "Say the price plainly, the number then جنيه.", ["asking"])
        ordering = kept_lesson(self.lessons, "Ask for the size before the colour.", ["ordering"])
        real = engine_lessons.Lessons.hand
        with mock.patch.object(engine_lessons.Lessons, "hand", autospec=True, side_effect=real) as spy:
            model = FakeModel(call("switch_stage", to="ordering"), say("تمام، تحب أي مقاس؟"))
            r = self.turn(model, "عايز اطلب جزمة")
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(spy.call_count, 2)
        (a, b) = spy.call_args_list
        self.assertEqual(a.args[:5], (self.lessons, r.chat_id, "reply", "asking", "عايز اطلب جزمة"))
        self.assertEqual(b.args[:5], (self.lessons, r.chat_id, "reply", "ordering", "عايز اطلب جزمة"))
        self.assertIs(a.args[5], b.args[5])  # one set for the whole turn
        self.assertEqual(a.args[5], {asking, ordering})
        first, second = self.prompts(model)
        self.assertIn("Say the price plainly", first)
        self.assertNotIn("Ask for the size", first)
        self.assertIn("Ask for the size", second)
        self.assertEqual(self.rows(r.chat_id), [("reply", "replied", [asking, ordering])])

    def test_another_agents_lesson_never_reaches_the_sales_prompt(self):
        waterer = EngineLessons(self.db, plugs.load(plugs.WATERER, self), judge=always_low)
        theirs = [kept_lesson(waterer, "Greet the bed warmly before watering.", ["all"], yes_by="grower"),
                  kept_lesson(waterer, "Water the seedlings first.", ["seedling"], yes_by="grower"),
                  waterer.propose("Visit the shady beds first.", ["all"], sources=[])]
        mine = kept_lesson(self.lessons, TONE, ["all"])
        for text, reply in (("أهلا", "أهلا بيك، تحب تسأل عن إيه؟"),
                            ("greet warmly before watering the beds", "Hi, what can I help you with?"),
                            ("Visit the shady beds first.", "Hi, what can I help you with?")):
            with self.subTest(text=text):
                model = FakeModel(say(reply))
                r = self.turn(model, text)
                prompt = self.prompts(model)[0]
                self.assertIn("Lessons from past chats:\n- " + TONE, prompt)
                for t in ("Greet the bed", "Water the seedlings", "shady beds"):
                    self.assertNotIn(t, prompt.split("Lessons from past chats:")[1])
                self.assertEqual(self.rows(r.chat_id)[-1][2], [mine])
        self.assertTrue(all(waterer.get(i)["state"] in ("kept", "trying") for i in theirs))


class ShareInTheLoop(LoopCase):
    def test_only_chats_in_the_share_get_a_lesson_on_trial(self):
        front = EngineLessons(self.db, PLUG, judge=always_low)
        lid = front.propose(TONE, ["all"], sources=[])
        self.assertEqual((front.get(lid)["state"], front.get(lid)["share"]), ("trying", 0.2))
        inside = outside = None
        for i in range(400):
            number = f"2015{i:08d}"
            chat_id = self.chats.open("whatsapp", number)
            if in_share(chat_id, lid, 0.2):
                inside = inside or number
            else:
                outside = outside or number
            if inside and outside:
                break
        self.assertTrue(inside and outside)
        for _ in range(2):  # the same chat gets the same answer every turn
            for number, given in ((inside, [lid]), (outside, [])):
                with self.subTest(number=number):
                    model = FakeModel(say("أهلا بيك، تحب تسأل عن إيه؟"))
                    r = self.turn(model, "أهلا", customer=number, lessons=front)
                    self.assertEqual(TONE in self.prompts(model)[0], bool(given))
                    self.assertEqual(self.rows(r.chat_id)[-1], ("reply", "replied", given))


class MadeUpAgentRun(unittest.TestCase):
    """The waterer: lessons handed per bed, written into its prompt, the action logged with
    them, and a slow result days later read back by bed."""

    def test_a_full_round(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        plug = plugs.load(plugs.WATERER, self)
        lessons, log = EngineLessons(db, plug, judge=always_low), Log(db, plug)
        kept = kept_lesson(lessons, "Water the seedlings first.", ["seedling"], yes_by="grower", now=0)
        grown_only = kept_lesson(lessons, "Check the soil before watering.", ["grown"], yes_by="grower", now=0)
        trial = lessons.propose("Visit the shady beds first.", ["all"], now=0, sources=[])
        waiting = lessons.propose("Use 2 cups of water.", ["seedling"], now=0, sources=[])  # a number: high, waits
        self.assertEqual([lessons.get(i)["state"] for i in (kept, trial, waiting)], ["kept", "trying", "waiting"])
        with self.assertRaises(ValueError):
            lessons.hand("bed-1", "reply", "seedling", "", set(), now=1)  # not its action
        beds = [f"bed-{i}" for i in range(40)]
        for i, bed in enumerate(beds):
            given = set()
            picked = lessons.hand(bed, "water", "seedling", "the shady beds", given, now=1)
            prompt = slot(plug, picked)
            self.assertTrue(prompt.startswith("Notes from past rounds:\n- "))
            self.assertEqual(given, {p["id"] for p in picked})
            log.act(bed, "water", lessons=given, result="soaked", stage="seedling", at=100 + i)
        for i, bed in enumerate(beds):
            if i % 3:
                log.result(bed, "grew", at=400_000 + i)
            else:
                log.result(bed, "wilted", cause="frost", at=300_000 + i)
        for bed in beds:
            act, later = log.case(bed)
            expected = sorted({kept} | ({trial} if in_share(bed, trial, 0.5) else set()))
            self.assertEqual((act["action"], act["result"], act["lessons"]), ("water", "soaked", expected))
            self.assertEqual((later["action"], later["lessons"]), (None, []))
        self.assertTrue(any(in_share(b, trial, 0.5) for b in beds) and not all(in_share(b, trial, 0.5) for b in beds))
        for i in range(40):
            self.assertNotIn(waiting, log.case(beds[i])[0]["lessons"])
            self.assertNotIn(grown_only, log.case(beds[i])[0]["lessons"])
        wilted = log.query(result="wilted", since=200_000)
        self.assertEqual([r["case_id"] for r in wilted], [b for i, b in enumerate(beds) if i % 3 == 0])
        self.assertEqual({r["cause"] for r in wilted}, {"frost"})
        by_case = {r["case_id"]: r["lessons"] for r in log.query(action="water")}
        with_trial = [r["case_id"] for r in wilted if trial in by_case[r["case_id"]]]
        self.assertEqual(with_trial, [r["case_id"] for r in wilted if in_share(r["case_id"], trial, 0.5)])
        self.assertEqual({r["agent"] for r in log.query()}, {"waterer"})


if __name__ == "__main__":
    unittest.main()
