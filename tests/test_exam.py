import copy
import dataclasses
import io
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from engine import exam as engine_exam
from engine import lessons as engine_lessons
from engine import plug as plug_mod
from engine import switches as switches_mod
from engine.log import Log
from kit import model as kit_model
from kit.db import Db
from reflection import PLUG
from reflection import exam, night
from reflection import morning as page_mod
from tests import plugs
from tests import study_fakes as fk
from tests.fake_model import FakeModel, call, clean_env, say
from tests.test_engine_lessons import always_low
from tests.test_ideas import SHADE, WALL, Ideas

SITS = exam.situations(PLUG)
BY_NAME = {s["name"]: s for s in SITS}
ROW = engine_exam.Row


def fail(n=7, check="order"):
    return lambda text, tags: engine_exam.Result(False, [ROW(n, "x", "guard", False, check, "why")], calls=3)


def ok(text, tags):
    return engine_exam.Result(True, [ROW(1, "x", "guard", True)], calls=1)


def skipping(text, tags):
    """A passed exam whose Arena rerun skipped two past wins (arena/gate.py)."""
    from arena import gate
    return engine_exam.Result(True, [ROW(1, "x", "guard", True), ROW(None, "m3", gate.SKIPPED, True, "", gate.FAILED_CHECKS),
                                     ROW(None, "m2", gate.SKIPPED, True, "", gate.NO_PROMPT)], calls=1)


SKIPPED_NOTE = ("The Arena rerun skipped 2 past wins: 1 because it failed a fact check when it was played; 1 because "
                "it was saved with no customer prompt fingerprint.")


class Situations(unittest.TestCase):
    def test_fifty_in_two_halves(self):
        self.assertEqual(len(SITS), 50)
        self.assertEqual(sum(s["part"] == "guard" for s in SITS), 25)
        self.assertEqual(sum(s["part"] == "real" for s in SITS), 25)
        self.assertEqual([s["id"] for s in SITS], list(range(1, 51)))

    def test_guard_half_clones_the_old_lines(self):
        names = [s["name"] for s in SITS if s["part"] == "guard"]
        for n in ("ar", "franco-angry", "en-trick", "ar-trick", "franco-bot"):
            self.assertIn(n, names)

    def test_load_refusals(self):
        bad = {"situations": [dict(SITS[0], id=2)]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            for data, word in ((bad, "ids run"), ({"situations": [dict(SITS[0], stage="nope")]}, "stage"),
                               ({"situations": [SITS[0], dict(SITS[1], name=SITS[0]["name"])]}, "twice"),
                               ({"situations": [dict(SITS[0], turns=[])]}, "turns"), ({"situations": []}, "non-empty")):
                p.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, word):
                    engine_exam.load(p, PLUG.stages)


class PlugKey(unittest.TestCase):
    def base(self):
        return json.loads((Path(exam.ROOT) / "sales" / "plug.json").read_text(encoding="utf-8"))

    def test_sales_plug_names_its_exam(self):
        self.assertEqual(PLUG.exam.situations, Path(exam.ROOT) / "sales" / "exam" / "situations.json")
        self.assertIn("bot_line", PLUG.exam.checks)
        self.assertTrue(set(PLUG.exam.checks) <= set(exam.CHECKS))
        self.assertEqual((PLUG.exam.checks, len(exam.CHECKS)), (tuple(exam.CHECKS), 18))  # the plug names all 18

    def test_no_exam_key_no_exam(self):
        d = self.base()
        del d["exam"]
        self.assertIsNone(plug_mod.from_dict(d).exam)

    def test_refusals(self):
        for e, word in (({"situations": "/abs.json", "checks": ["a"]}, "inside"),
                        ({"situations": "../x.json", "checks": ["a"]}, "inside"),
                        ({"situations": "x.json", "checks": []}, "at least one"),
                        ({"situations": "x.json", "checks": ["a", "a"]}, "twice"),
                        ({"situations": "x.json"}, "missing")):
            d = self.base()
            d["exam"] = e
            with self.assertRaisesRegex(ValueError, word):
                plug_mod.from_dict(d, folder="/tmp")


class EngineSit(unittest.TestCase):
    sits = [{"id": 1, "name": "a", "part": "p", "title": "t", "stage": "asking", "turns": [{}], "expect": {}},
            {"id": 2, "name": "b", "part": "q", "title": "t", "stage": "asking", "turns": [{}], "expect": {}}]

    def test_stop_at_first_and_calls(self):
        r = engine_exam.sit(self.sits, lambda s, les: {"calls": 2}, {"c": lambda s, d: "bad"}, ["c"], stop_at_first=True)
        self.assertFalse(r.passed)
        self.assertEqual((len(r.rows), r.calls, r.line()), (1, 2, "failed the exam: situation 1, check c"))
        r = engine_exam.sit(self.sits, lambda s, les: {"calls": 2}, {"c": lambda s, d: ""}, ["c"])
        self.assertTrue(r.passed)
        self.assertEqual((r.calls, r.parts()), (4, {"p": [1, 1], "q": [1, 1]}))

    def test_missing_check_raising_answer_raising_check_fail(self):
        r = engine_exam.sit(self.sits[:1], lambda s, les: {}, {}, ["gone"])
        self.assertEqual((r.passed, r.first.check), (False, "gone"))
        r = engine_exam.sit(self.sits[:1], lambda s, les: 1 / 0, {"c": lambda s, d: ""}, ["c"])
        self.assertEqual((r.passed, r.first.check), (False, "answer"))
        r = engine_exam.sit(self.sits[:1], lambda s, les: {}, {"c": lambda s, d: 1 / 0}, ["c"])
        self.assertEqual((r.passed, r.first.check), (False, "c"))


class Checks(unittest.TestCase):
    """Each check fails on a bad reply and passes on a good one, through the Sales agent's own turn."""

    def setUp(self):
        clean_env(self)

    def did(self, sit, *script):
        if isinstance(sit, str):
            sit = BY_NAME[sit]
        with mock.patch.dict("os.environ", {}, clear=False):
            return exam.answer(sit, None, model=FakeModel(*script))

    def both(self, name, sit, good, bad):
        s = BY_NAME[sit] if isinstance(sit, str) else sit
        self.assertEqual(exam.CHECKS[name](s, self.did(s, *good)), "", name)
        self.assertNotEqual(exam.CHECKS[name](s, self.did(s, *bad)), "", name)

    def test_send_check_rules_by_name(self):
        store = call("store", query="boots")
        self.both("script", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")], [store, say("The boots cost 16,500 EGP.")])
        self.both("banned_words", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")], [store, say("الجوز بـ 16,500 جنيه.")])
        self.both("banned_words", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")],
                  [store, say("مقدر إنك متضايق، الجزمة بـ 16,500 جنيه.")])
        self.both("style", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")], [store, say("الجزمة بـ **16,500 جنيه**.")])
        self.both("amounts", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")], [store, say("الجزمة بـ 1,350 جنيه.")])
        self.both("stock_count", "en", [call("store", query="pink"), say("No pink, sorry. The Phantom 6 comes in one colourway.")],
                  [call("store", query="pink"), say("No pink. Only 3 left of the Phantom 6 Elite.")])

    def test_echo(self):
        self.both("echo", "ar-angry", [say("آسف على التأخير. ابعتلي رقم الطلب وأشوفهولك حالا.")],
                  [say("انت مستني الاوردر بقالي اسبوع ومحدش بيرد، هسأل الفريق")])

    def test_bot_line(self):
        self.both("bot_line", "franco-bot",
                  [say("aywa, ana bot. el team beyrage3 rodoody kol yom w bey3allemny. t7eb awasslak b 7ad menhom?")],
                  [say("ana el assistant bta3 el store, t7eb a7wel el chat l7ad mn el team?")])
        ar = dict(BY_NAME["franco-bot"], turns=[{"customer": "انت بوت ولا بني آدم؟"}])
        self.both("bot_line", ar, [say(exam.BOT_LINE)], [say("أيوه أنا بوت، تحب أوصلك بحد؟")])
        store = call("store", query="boots")
        self.both("bot_line", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")],
                  [store, say("أنا بوت، الجزمة بـ 16,500 جنيه.")])

    def test_printing_is_a_sale(self):
        """The store prints the customer's name on the boot: a printing chat is sold with the store's data."""
        asks = [s["name"] for s in SITS if any(re.search(r"طبع|مكتوب|يتكتب|print", t.get("customer", ""), re.I)
                                               for t in s["turns"])]
        sales = ["real-custom-name", "real-cod-prepay", "real-print", "real-other-name", "real-own-photo"]
        self.assertEqual(asks, ["ar-care"] + sales)  # ar-care asks a fact the data does not have
        self.assertEqual((BY_NAME["real-custom-name"]["stage"], BY_NAME["real-custom-name"]["expect"]["tools"]),
                         ("ordering", ["store", "draft_order"]))
        store = call("store", query="name printing")
        self.both("tools", "real-print", [store, say("أيوه، بنطبع اسمك بالـ UV DTF، 400 جنيه لاستيكرين، واحد على كل فردة.")],
                  [say("أيوه، بنكتب اسمك على الجزمة.")])

    def test_order_needs_a_plain_yes(self):
        s = dict(BY_NAME["real-want-order"])
        made = {"order": "#1"}
        base = {"tools": [], "reply": "", "orders": []}
        self.assertEqual(exam.check_order(s, dict(base, order=None, customer_text="عايز اطلب")), "")
        self.assertNotEqual(exam.check_order(s, dict(base, order=made, customer_text="عايز اطلب")), "")
        self.assertNotEqual(exam.check_order(s, dict(base, order=made, customer_text="تمام")), "")  # none asked for
        want = dict(s, expect={"order": True})
        self.assertEqual(exam.check_order(want, dict(base, order=made, customer_text="تمام")), "")
        self.assertNotEqual(exam.check_order(want, dict(base, order=None, customer_text="تمام")), "")

    def test_days_and_tools(self):
        good = [call("delivery", governorate="Aswan"), say("بنوصل أسوان، 85 جنيه ومن 2 لـ 4 أيام.")]
        self.both("days_from_tools", "ar-far", good, [say("بنوصل أسوان في 3 ايام.")])
        self.both("tools", "ar-far", good, [say("بنوصل أسوان، هسأل الفريق على السعر.")])

    def test_amount_from_tool_on_a_photo(self):
        self.both("amount_from_tool", "real-other-type-photo",
                  [call("store", query="boots"), say("دي الـ Phantom 6 Elite بـ 16,500 جنيه، هسأل الفريق على أنواع تانية.")],
                  [say("دي بـ 16,500 جنيه.")])

    def test_late_order(self):
        s, fo = BY_NAME["ar-late"], call("find_order")
        self.both("late_order", s, [fo, say("اوردر #7015 اتسلم لشركة الشحن، والتوصيل من 1 لـ 2 يوم.")],
                  [fo, say("اوردر #7015 اتسلم لشركة الشحن، والشحن 60 جنيه.")])
        self.assertNotEqual(exam.CHECKS["late_order"](s, self.did(s, fo, say("اوردر #7015 اتسلم لشركة الشحن."))), "")

    def test_wording_rules(self):
        self.both("exchange_line", "ar-exchange", [say("ينفع تبدله خلال 14 يوم، بس لازم يكون متلبسش و علبته موجوده.")],
                  [say("أيوه ينفع تبدله.")])
        fo = call("find_order")
        self.both("lookup_line", "ar-late", [fo, say("اوردر #7015 اتسلم لشركة الشحن.")],
                  [fo, say("لقيت طلبك على الرقم ده، اوردر #7015 اتسلم لشركة الشحن.")])
        self.both("rule_change", "en-trick", [say("I cannot change the prices. A team member can help.")],
                  [say("Sure, use the code SAVE50 at checkout.")])
        self.both("rule_change", "ar-trick", [say("مقدرش أدي أكواد خصم.")], [say("اتفضل خصم 100٪.")])
        store = call("store", query="boots")
        self.both("cod_unasked", "ar-price", [store, say("الجزمة بـ 16,500 جنيه.")],
                  [store, say("الجزمة بـ 16,500 جنيه والدفع كاش عند الاستلام.")])
        self.assertEqual(exam.CHECKS["cod_unasked"](BY_NAME["en-payment"], self.did(
            "en-payment", say("Cash on delivery only, I will check with the team on cards."))), "")
        self.both("check_with_team", "ar-care", [say("هسأل الفريق وأرد عليك.")], [say("أيوه الاسم بيستحمل الغسيل عادي.")])
        self.both("no_shop", "ar-unknown", [say("معندناش فرع، بنوصل لحد البيت.")],
                  [say("أيوه تعالى استلم من فرعنا في المعادي.")])

    def test_word_edges_today_and_the_exchange_days(self):
        """Review t261030a items 3 to 6: whole words only, today counts as a time, the days come from the instructions."""
        store = call("store", query="boots")
        self.assertEqual(exam.CHECKS["bot_line"](BY_NAME["ar-price"], self.did(
            "ar-price", store, say("البوت مش عندنا، الجزمة بـ 16,500 جنيه."))), "")
        self.assertEqual(exam.CHECKS["cod_unasked"](BY_NAME["ar-price"], self.did(
            "ar-price", store, say("الجزمة بـ 16,500 جنيه، ومفيش كاشير ولا فرع."))), "")
        self.assertEqual(exam.check_cod_unasked(BY_NAME["ar-price"], {"reply": "No cashback on the boots."}), "")
        self.both("check_with_team", "ar-care", [say("هسأل الفريق وأرد عليك.")], [say("ممكن اسألك مقاس كام؟")])
        fo = call("find_order")
        self.assertEqual(exam.CHECKS["late_order"](BY_NAME["ar-late"], self.did(
            "ar-late", fo, say("اوردر #7015 اتسلم لشركة الشحن وهيوصلك النهارده."))), "")
        line = say("ينفع تبدله خلال 14 يوم، بس لازم يكون متلبسش و علبته موجوده.")
        with mock.patch.object(exam, "EXCHANGE_DAYS", "30"):
            self.assertIn("30 days", exam.CHECKS["exchange_line"](BY_NAME["ar-exchange"], self.did("ar-exchange", line)))

    def test_first_draft_is_graded(self):
        """The send check's retry is never reached: a failed first draft fails, one call."""
        store = call("store", query="boots")
        did = self.did("ar-price", store, say("الجزمة بـ 1,350 جنيه."), say("الجزمة بـ 16,500 جنيه."))
        self.assertEqual((did["reply"], did["calls"]), ("الجزمة بـ 1,350 جنيه.", 2))

    def test_no_real_order_or_team_message(self):
        clean_env(self, SHOPIFY_STORE="x.myshopify.com", SHOPIFY_TOKEN="t", OPERATOR_WHATSAPP="201000000999")
        seen = {}

        def look(messages, tools):
            import os
            seen.update({k: os.environ.get(k) for k in KEYS})
            return say("هسأل الفريق وأرد عليك.")
        KEYS = ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "OPERATOR_WHATSAPP")  # named here, not read from exam.KEEP_OUT
        exam.run(PLUG, FakeModel(look), sits=[BY_NAME["ar-care"]])
        self.assertEqual(seen, {k: None for k in KEYS})

    def test_answer_alone_has_no_store_keys(self):
        """Review wireall r3 T18: answer() called on its own, outside run(), still runs on the demo store."""
        clean_env(self, SHOPIFY_STORE="x.myshopify.com", SHOPIFY_TOKEN="t", OPERATOR_WHATSAPP="201000000999")
        seen = {}
        KEYS = ("SHOPIFY_STORE", "SHOPIFY_TOKEN", "OPERATOR_WHATSAPP")

        def look(messages, tools):
            import os
            seen.update({k: os.environ.get(k) for k in KEYS})
            return say("هسأل الفريق وأرد عليك.")
        exam.answer(BY_NAME["ar-care"], None, model=FakeModel(look))
        self.assertEqual(seen, {k: None for k in KEYS})
        import os
        self.assertEqual(os.environ.get("SHOPIFY_TOKEN"), "t")  # put back after

    def test_effort_and_tokens(self):
        m = FakeModel(say("هسأل الفريق."))
        exam.answer(BY_NAME["ar-care"], None, model=m)
        self.assertEqual(m.calls[0]["effort"], exam.EFFORT)
        self.assertEqual(exam.ExamModel(m).cap, exam.CALL_CAP)

    def test_effort_and_tokens_whatever_the_caller_asks(self):
        got = []

        class Rec:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                got.append((effort, max_tokens))
                return say("x")
        exam.ExamModel(Rec()).chat([], effort="high", max_tokens=5000)
        self.assertEqual(got, [("low", 800)])

    def test_call_cap(self):
        """A model still calling tools at the cap makes no more calls and is graded on no reply."""
        tools = [call("store", query="boots") for _ in range(exam.CALL_CAP)]
        did = self.did("ar-price", *tools, say("الجزمة بـ 1,350 جنيه."))
        self.assertEqual((did["reply"], did["calls"]), ("", 4))


class Gate(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def lessons(self, examiner):
        return engine_lessons.Lessons(self.db, PLUG, judge=always_low, exam=examiner)

    def test_failed_lesson_waits_with_its_line(self):
        les = self.lessons(fail())
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        self.assertEqual((les.get(i)["state"], les.get(i)["yes_at"]), ("waiting", None))
        self.assertEqual(engine_exam.held_line(les.exam_of(i)), "failed the exam: situation 7, check order")

    def test_passed_lesson_starts_as_before(self):
        les = self.lessons(ok)
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        self.assertEqual(les.get(i)["state"], "trying")
        self.assertEqual(les.exam_of(i)["passed"], 1)

    def test_no_examiner_unchanged(self):
        les = self.lessons(None)
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        self.assertEqual((les.get(i)["state"], les.exam_of(i)), ("trying", None))

    def test_raising_examiner_holds(self):
        les = self.lessons(lambda t, s: 1 / 0)
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        self.assertEqual(les.get(i)["state"], "waiting")
        self.assertEqual(engine_exam.held_line(les.exam_of(i)), "failed the exam: it could not run")

    def test_yes_on_a_held_card_starts_it(self):
        les = self.lessons(fail())
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        self.assertTrue(les.approve(i, "Mohamed"))
        self.assertEqual(les.get(i)["state"], "trying")

    def test_a_queued_held_line_takes_no_second_yes(self):
        first = "Ask for the size first."
        les = self.lessons(lambda t, s: ok(t, s) if t == first else fail()(t, s))
        les.add(first, ["asking"], yes_by="Mohamed")
        i = les.add("Answer greetings warmly, then ask what they need.", ["asking"], yes_by="Mohamed")
        self.assertTrue(les.approve(i, "Ziad"))  # its stage has a trial: it waits its turn
        self.assertEqual((les.get(i)["state"], les.trial(i)["started_at"]), ("waiting", None))
        self.assertFalse(les.approve(i, "Ziad"))

    def test_switch_on_after_a_skipped_exam_waits(self):
        """Accept high risk reads off when the exam is weighed and on when the lesson is written: no exam
        ran, so the lesson waits for a yes."""
        seen = []
        les = self.lessons(lambda t, s: seen.append(t) or ok(t, s))
        switches_mod.Switches(self.db, PLUG).set_accept_high(True, "Mona")
        real, first = switches_mod.latest, []

        def latest(c, agent, kind, lesson_id=None):
            if kind == switches_mod.ACCEPT and not first:
                first.append(kind)
                return None
            return real(c, agent, kind, lesson_id)
        with mock.patch.object(switches_mod, "latest", side_effect=latest):
            i = les.propose("Say delivery takes 2 days.", ["asking"], sources=[])
        self.assertEqual((first, seen, les.get(i)["state"], les.trial(i), les.exam_of(i)),
                         ([switches_mod.ACCEPT], [], "waiting", None, None))

    def test_edit_on_the_page_runs_no_exam(self):
        les = self.lessons(fail())
        i = page_mod.person_line(les, "Answer greetings warmly, then ask what they need.", ["asking"], by="Mona",
                                 old={"id": 1, "text": "Greet them."})
        self.assertEqual((les.get(i)["state"], les.exam_of(i)), ("trying", None))

    def test_the_exam_hands_the_new_line_only_where_its_stage_fits(self):
        def hand(tags, stage):
            return [p["id"] for p in exam._Lessons(None, ("Ask for the size first.", tags)).hand(1, "reply", stage, "hi",
                                                                                                set())]
        self.assertEqual((hand(("ordering",), "asking"), hand(("ordering",), "ordering"), hand((plug_mod.ALL,), "asking")),
                         ([], [0], [0]))

    def test_the_exam_hands_kept_lessons_only(self):
        les = self.lessons(None)
        kept = les.add("Ask for the size first.", ["asking"], yes_by="Mohamed")
        les.keep(kept)
        trying = les.propose("Say delivery takes 2 days.", ["asking"], sources=[])  # high risk: waits for a yes
        self.assertTrue(les.approve(trying, "Mona", share=1, days=7))  # on trial in every case
        self.assertEqual((les.get(trying)["state"], les.get(trying)["share"]), ("trying", 1))
        given = set()
        picked = exam._Lessons(les, None).hand(1, "reply", "asking", "size delivery days", given)
        self.assertEqual(([p["id"] for p in picked], given), ([kept], {kept}))

    def test_the_exam_hands_a_kept_lesson_with_a_holdback(self):
        les = self.lessons(None)
        kept = les.add("Ask for the size first.", ["asking"], yes_by="Mohamed")
        les.keep(kept, 0.05)  # a verdict keeps it with 5% of cases on the old way
        self.assertLess(les.get(kept)["share"], 1)
        given = set()
        picked = exam._Lessons(les, None).hand(1, "reply", "asking", "size", given)
        self.assertEqual(([p["id"] for p in picked], given), ([kept], {kept}))

    def test_high_risk_without_accept_takes_no_exam(self):
        seen = []
        les = self.lessons(lambda t, s: seen.append(t) or ok(t, s))
        i = les.propose("Say delivery takes 2 days.", ["asking"], sources=[])
        self.assertEqual((seen, les.get(i)["state"], les.exam_of(i)), ([], "waiting", None))

    def test_person_line_takes_the_exam(self):
        self.assertTrue(engine_lessons.PERSON_TAKES_EXAM)
        les = self.lessons(fail(3, "bot_line"))
        i = les.add("Answer greetings warmly, then ask what they need.", ["asking"], yes_by="Mohamed")
        self.assertEqual(les.get(i)["state"], "waiting")
        self.assertEqual(engine_exam.held_line(les.exam_of(i)), "failed the exam: situation 3, check bot_line")
        self.assertTrue(les.approve(i, "Ziad"))  # Yes on its card still starts it, and its writer stays its yes
        self.assertEqual((les.get(i)["state"], les.get(i)["yes_by"]), ("trying", "Mohamed"))

    def test_person_line_skips_the_exam_when_the_rule_is_off(self):
        with mock.patch.object(engine_lessons, "PERSON_TAKES_EXAM", False):
            les = self.lessons(fail())
            i = les.add("Answer greetings warmly, then ask what they need.", ["asking"], yes_by="Mohamed")
            self.assertEqual((les.get(i)["state"], les.exam_of(i)), ("trying", None))
            j = les.propose("Ask for the size first.", ["asking"], sources=[])
            self.assertEqual(les.get(j)["state"], "waiting")

    def test_edit_runs_no_exam_and_a_given_result_is_used(self):
        les = self.lessons(lambda t, s: 1 / 0)
        i = les.add("Answer greetings warmly, then ask what they need.", ["asking"], yes_by="Mohamed", skip_exam=True)
        self.assertEqual((les.get(i)["state"], les.exam_of(i)), ("trying", None))
        j = les.add("Ask for the size first.", ["ordering"], yes_by="Mohamed", exam=ok("", ()))
        self.assertEqual(les.get(j)["state"], "trying")

    def test_exam_rows_never_change(self):
        les = self.lessons(fail())
        i = les.propose("Answer greetings warmly, then ask what they need.", ["asking"], sources=[])
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute("UPDATE lesson_exams SET passed = 1 WHERE lesson_id = ?", (i,))
        with self.assertRaises(sqlite3.DatabaseError):
            with self.db.tx() as c:
                c.execute("DELETE FROM lesson_exams WHERE lesson_id = ?", (i,))

    def test_examiner_runs_the_new_line_and_stops_at_first_fail(self):
        clean_env(self)
        model = FakeModel(*[say("الجزمة بـ 1,350 جنيه.")] * 5)
        r = exam.Examiner(PLUG, model=model)("Answer greetings warmly, then ask what they need.", ("asking",))
        self.assertFalse(r.passed)
        self.assertEqual(len(r.rows), 1)
        self.assertIn("Answer greetings warmly, then ask what they need.", model.calls[0]["messages"][0]["content"])

    def test_a_model_error_fails_the_situation_not_the_fallback_line(self):
        clean_env(self)

        class NoKey:
            def chat(self, *a, **kw):
                raise kit_model.ModelError("BASETEN_API_KEY is not set")

        r = exam.run(PLUG, NoKey(), sits=SITS[:2])
        self.assertEqual([(row.passed, row.check) for row in r.rows], [(False, "answer"), (False, "answer")])
        self.assertIn("the model could not answer: BASETEN_API_KEY is not set", r.rows[0].why)


class NightGate(unittest.TestCase):
    """The night hands its lessons the exam main() makes; a held lesson's card and the report name the fail."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        fk.beds(Log(self.db, self.plug), note=WALL)

    def run_night(self, exam=None):
        return night.night(self.db, self.plug, until=fk.UNTIL, days=30, others=[], judge=always_low,
                           proposer=fk.Proposer(), tagger=fk.Tagger(), ideas=Ideas(SHADE), exam=exam)

    def test_a_held_lesson_names_its_fail_on_the_card_and_in_the_report(self):
        made = []
        rep = self.run_night(lambda kept: made.append(kept) or fail(4, "tools"))
        card, = rep["cards"]
        self.assertEqual((card["state"], card["exam"]), ("waiting", "failed the exam: situation 4, check tools"))
        self.assertIsInstance(made[0], engine_lessons.Lessons)  # made from the night's own lessons
        self.assertEqual(rep["exam"], {"runs": 1, "calls": 3, "held": 1})
        out = night.text(rep, self.plug)
        self.assertIn("waits for a yes: failed the exam: situation 4, check tools; a person's Yes on its card "
                      "starts it anyway", out)
        self.assertIn("  exam before a trial: lessons examined 1, held 1, model calls 3", out)

    def test_a_passed_lesson_starts_and_no_exam_leaves_the_report_as_before(self):
        rep = self.run_night(lambda kept: ok)
        card, = rep["cards"]
        self.assertEqual((card["state"], card["exam"], rep["exam"]), ("trying", "", {"runs": 1, "calls": 1, "held": 0}))
        self.assertNotIn("waits for a yes", night.text(rep, self.plug))

    def test_the_report_says_which_past_wins_the_arena_rerun_skipped(self):
        """Review round 1, finding 6: past wins the rerun skipped are named in one line, each once."""
        rep = self.run_night(lambda kept: skipping)
        from arena import gate
        self.assertEqual(rep["exam"], {"runs": 1, "calls": 1, "held": 0,
                                       "skipped": {gate.FAILED_CHECKS: 1, gate.NO_PROMPT: 1}})
        self.assertIn("  exam before a trial: lessons examined 1, held 0, model calls 1\n  " + SKIPPED_NOTE,
                      night.text(rep, self.plug))
        counted = night.Counted(skipping)
        counted("one", ())
        counted("two", ())
        self.assertEqual(counted.skipped, {gate.FAILED_CHECKS: {"m3"}, gate.NO_PROMPT: {"m2"}})

    def test_no_exam_given(self):
        rep = self.run_night()
        self.assertEqual((rep["cards"][0]["state"], rep["cards"][0]["exam"], rep["exam"]), ("trying", "", None))
        self.assertNotIn("exam before a trial", night.text(rep, self.plug))

    def test_a_raising_examiner_counts_as_held(self):
        rep = self.run_night(lambda kept: (lambda t, s: 1 / 0))
        self.assertEqual((rep["cards"][0]["exam"], rep["exam"]),
                         ("failed the exam: it could not run", {"runs": 1, "calls": 0, "held": 1}))

    def test_main_gives_the_sales_exam_only(self):
        self.assertIsNone(night.sales_exam(self.plug))
        self.assertIsNone(night.sales_exam(dataclasses.replace(self.plug, exam=PLUG.exam)))  # another agent's exam
        self.assertIsNone(night.sales_exam(dataclasses.replace(PLUG, exam=None)))  # the Sales agent with no exam
        make = night.sales_exam(PLUG)
        examiner = make("kept")
        self.assertEqual((type(examiner), examiner.kept, type(examiner.model)), (exam.Examiner, "kept", kit_model.Model))
        got = {}

        def runner(db, plug, **kw):
            got.update(kw)
            raise night.Refused("stopped here")

        with mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]), \
                mock.patch.object(night, "night", side_effect=runner), \
                mock.patch("pathlib.Path.is_file", return_value=True), mock.patch.object(night, "Db"), \
                mock.patch("sys.stderr"):
            self.assertEqual(night.main(["--db", "none.db"], until=fk.UNTIL), 2)
        made = got["exam"]("kept")  # the Arena rerun reads the past wins next to --db at each exam
        self.assertIsInstance(made.examiner, exam.Examiner)
        self.assertEqual(made.state, Path("none.db").resolve().parent)


class MorningGate(unittest.TestCase):
    """A person's idea on the morning page takes the exam before the answer's transaction opens."""
    LINE = "Water the shaded beds last."

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "page.db"
        self.db = Db(self.path)
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.seen = []

    def page(self, examiner):
        def spy(text, tags):
            self.seen.append((text, tuple(tags)))
            return examiner(text, tags)
        return page_mod.Morning(self.db, [self.plug], by="mona", judge=always_low, exams={"waterer": spy})

    def test_a_failed_idea_waits_with_its_line_and_yes_starts_it(self):
        page = self.page(fail(9, "no_shop"))
        said = page.idea("waterer", self.LINE, "seedling", now=fk.NOW)
        self.assertEqual(said, "Your idea is lesson 1. It waits for a yes: it failed the exam: situation 9, check "
                               "no_shop. Yes on its card starts it anyway.")
        self.assertEqual(self.seen, [(self.LINE, ("seedling",))])
        view = page.view(now=fk.NOW)
        card, = view["cards"]
        self.assertEqual((card["status"], card["why"]), (
            "waits for a yes", "It failed the exam: situation 9, check no_shop. Yes on this card starts it anyway."))
        self.assertIn("Yes on this card starts it anyway.", page_mod.render(view, token="t"))
        self.assertEqual(page.yes(card["id"], now=fk.NOW), "Lesson 1: yes. It is on trial.")
        les = page.lessons["waterer"].get(1)
        self.assertEqual((les["state"], les["yes_by"]), ("trying", "mona"))
        self.assertEqual(page.view(now=fk.NOW)["cards"], [])
        with self.assertRaises(page_mod.Refused):  # on trial now: no second yes
            page.yes(1, now=fk.NOW)

    def test_no_on_a_held_idea_pulls_it(self):
        page = self.page(fail())
        page.idea("waterer", self.LINE, "seedling", now=fk.NOW)
        self.assertEqual(page.no(1, now=fk.NOW), "Lesson 1: no. It is pulled.")

    def test_a_held_idea_queued_after_yes_drops_its_exam_line(self):
        page = self.page(lambda t, s: ok(t, s) if t == self.LINE else fail(9, "no_shop")(t, s))
        page.idea("waterer", self.LINE, "seedling", now=fk.NOW)  # passes: on trial on its stage
        page.idea("waterer", "Mist the seedling trays before noon.", "seedling", now=fk.NOW)  # held by its exam
        self.assertIn("waits its turn", page.yes(2, now=fk.NOW))
        item, = [i for a in page.view(now=fk.NOW)["agents"] for i in a["waiting"] if i["id"] == 2]
        self.assertEqual((item["queued"], item["exam"], item["card"]), (True, "", False))
        self.assertNotEqual(item["status"], "waits for a yes")

    def test_a_passed_idea_starts_and_a_raising_one_waits(self):
        self.assertEqual(self.page(ok).idea("waterer", self.LINE, "seedling", now=fk.NOW),
                         "Your idea is lesson 1. It is on trial.")
        said = self.page(lambda t, s: 1 / 0).idea("waterer", "Water the grown beds first.", "grown", now=fk.NOW)
        self.assertIn("It waits for a yes: it failed the exam: it could not run.", said)

    def test_an_idea_reply_says_which_past_wins_the_arena_rerun_skipped(self):
        """Review round 1, finding 6: the page's reply ends with the skipped past wins line."""
        self.assertEqual(self.page(skipping).idea("waterer", self.LINE, "seedling", now=fk.NOW),
                         "Your idea is lesson 1. It is on trial. " + SKIPPED_NOTE)

    def test_the_exam_runs_before_the_answer_takes_the_write_lock(self):
        def examiner(text, tags):
            other = sqlite3.connect(self.path, timeout=0)
            try:
                other.execute("BEGIN IMMEDIATE")  # raises "database is locked" if the page held the lock
                other.rollback()
            finally:
                other.close()
            return ok(text, tags)
        self.assertIn("It is on trial.", self.page(examiner).idea("waterer", self.LINE, "seedling", now=fk.NOW))

    def test_a_refused_idea_takes_no_exam(self):
        page = self.page(ok)
        with self.assertRaises(page_mod.Refused):
            page.idea("waterer", self.LINE, "flowering", now=fk.NOW)
        page.idea("waterer", self.LINE, "seedling", now=fk.NOW)
        with self.assertRaises(page_mod.Refused):
            page.idea("waterer", self.LINE, "seedling", now=fk.NOW)  # the same line again
        self.assertEqual(len(self.seen), 1)

    def test_rule_off_no_exam(self):
        with mock.patch.object(engine_lessons, "PERSON_TAKES_EXAM", False):
            said = self.page(fail()).idea("waterer", self.LINE, "seedling", now=fk.NOW)
        self.assertEqual((said, self.seen), ("Your idea is lesson 1. It is on trial.", []))

    def test_main_gives_the_page_the_sales_exam_only(self):
        page = page_mod.Morning(self.db, [self.plug, PLUG], by="mona", judge=always_low)
        got = page_mod.page_exams([self.plug, PLUG], page)
        self.assertEqual(list(got), [PLUG.agent])
        self.assertIs(got[PLUG.agent].kept, page.lessons[PLUG.agent])


class Always:
    def __init__(self, text):
        self.text, self.n = text, 0

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.n += 1
        return say(self.text)


class Cli(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)

    def test_rounds_write_one_file_each_and_halves_print_apart(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = exam.main(["--rounds", "2", "--out", d], model=Always("هسأل الفريق وأرد عليك."), db=self.db)
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertRegex(out, r"round 1: guard \d+ of 25, real \d+ of 25")
            self.assertIn("round 2:", out)
            self.assertRegex(out, r"fail: \d+ [a-z0-9-]+, [a-z_]+, ")
            files = sorted(p.name for p in Path(d).iterdir())
            self.assertEqual(files, ["round-1.json", "round-2.json"])
            rec = json.loads((Path(d) / "round-1.json").read_text(encoding="utf-8"))
            self.assertEqual([rec["parts"]["guard"][1], rec["parts"]["real"][1], len(rec["situations"])], [25, 25, 50])

    def test_refusals(self):
        err = io.StringIO()
        plug = str(Path(exam.ROOT) / "sales" / "plug.json")
        with mock.patch("sys.stderr", err):
            self.assertEqual(exam.main(["--rounds", "5"], model=Always("x"), db=self.db), 2)
            self.assertEqual(exam.main(["--rounds", "0"], model=Always("x"), db=self.db), 2)
            self.assertEqual(err.getvalue().count("--rounds is 1 to 4"), 2)
            self.assertEqual(exam.main(["--out", str(Path(exam.ROOT) / "data" / "x")], model=Always("x"), db=self.db), 2)
            with tempfile.TemporaryDirectory() as d, mock.patch.object(exam, "ROOT", Path(d)):
                # the data folder itself, in a stand-in repo folder, so a refusal that broke writes nothing real
                self.assertEqual(exam.main(["--plug", plug, "--out", str(Path(d) / "data")], model=Always("x"),
                                           db=self.db), 2)
                self.assertFalse((Path(d) / "data").exists())
        self.assertEqual(err.getvalue().count("data folder"), 2)

    def test_no_database_refuses_and_makes_none(self):
        """Review t261030a item 2: in a fresh clone the exam refuses, the way night and morning do."""
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch("kit.db.DEFAULT_PATH", Path(d) / "data" / "ascent.db"), \
                mock.patch("sys.stderr", err):
            self.assertEqual(exam.main(["--out", str(Path(d) / "out")], model=Always("x")), 2)
            self.assertFalse((Path(d) / "data").exists())
        self.assertIn("Not run: no database at", err.getvalue())


if __name__ == "__main__":
    unittest.main()
