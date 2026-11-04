"""Engine fix A (2026-11-03): the Sales plug's high list is narrow. A lesson is high when it states an
amount, offers a discount or anything free, makes a promise, changes how customers pay, changes store
policy or keeps data beyond the order. Asking for the order details, naming a tool, and bringing up the
price, delivery or stock with no amount, date or promise are low on the judge's clear low. A bare number
of three or more digits, or a written hundred or thousand, still counts as an amount. The fast note
guard is not narrowed: it reads the old wide list as before."""
import unittest

from engine import fast as engine_fast
from engine import risk
from engine.lessons import Lessons
from engine.plug import Risk
from kit.db import Db
from reflection import PLUG
from reflection import fast as sales_fast


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


NOW_LOW = [  # each was high on the wide list, each is a lesson a store wants the agent to learn
    "When model and size are known, ask for name, governorate, address and phone together in plain text",
    "When price is objected to, ask for their budget, then present only a tier that fits",
    "Ask one question at a time, starting with the size.",
    "Before giving the total, call the delivery tool for the customer's governorate.",
    "When a customer asks when it will arrive, check the delivery tool and give the window it returns.",
    "If a size is out of stock, offer the nearest size that the store tool lists.",
    "Confirm payment is cash on delivery only when the customer asks how to pay.",
    "Mention the delivery fee once, after the customer picks a tier.",
    "When the customer hesitates on price, compare two tiers side by side with what each adds.",
    "Use draft_order only after the customer says a plain yes to the summary.",
    "If they ask how many days delivery takes, call delivery and repeat what it says.",
    "Ask for the customer's phone number last, after the address.",
]
STILL_HIGH = [  # (lesson, the group that must mark it)
    ("Offer a 10% discount when price is objected to.", "discount"),
    ("Tell them the boots cost 1500 EGP.", "amount"),
    ("Tell them the price is two thousand pounds.", "amount"),
    ("Promise delivery tomorrow.", "promise"),
    ("Say the order will arrive within 2 days.", "promise"),
    ("Ask for an InstaPay transfer before shipping.", "payment"),
    ("Ask for a deposit before confirming the order.", "payment"),
    ("Tell customers they can return or exchange any pair.", "policy"),
    ("Give free delivery on a second pair.", "discount"),
    ("Save the customer's phone to the marketing list for offers.", "personal_data"),
    ("Ask for their Instagram account so we can follow up.", "personal_data"),
    ("Guarantee the size will fit.", "promise"),
    ("Tell them every size is always in stock.", "policy"),
    ("Lower the price when they push back.", "discount"),
]
BARE_AMOUNTS = ["Say 1450 for the pair.", "Say ١٤٥٠ for the pair.", "Tell them it is two thousand.",
                "Say it is five hundred.", "قول ميتين."]
BARE_SMALL = ["Ask about the 2 colours first.", "Show them three styles."]


class NarrowList(unittest.TestCase):
    def test_the_twelve_lessons_are_low_on_a_clear_low(self):
        for text in NOW_LOW:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])
                self.assertEqual(risk.classify(text, PLUG.risk, always_low), (risk.LOW, ["judge: low"]))

    def test_the_twelve_still_wait_with_the_stub_judge(self):
        for text in NOW_LOW:
            with self.subTest(text=text):
                self.assertEqual(risk.classify(text, PLUG.risk)[0], risk.HIGH)

    def test_the_fourteen_stay_high_on_the_code_check_alone(self):
        for text, group in STILL_HIGH:
            with self.subTest(text=text):
                level, why = risk.classify(text, PLUG.risk, always_low)
                self.assertEqual(level, risk.HIGH)
                self.assertIn(group, [line.partition(": ")[0] for line in why])

    def test_a_bare_number_of_three_digits_or_a_written_hundred_is_an_amount(self):
        for text in BARE_AMOUNTS:
            with self.subTest(text=text):
                self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)
        for text in BARE_SMALL:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])

    def test_a_tool_name_is_a_mark_only_when_asked(self):
        text = "Use draft_order only after the customer says a plain yes to the summary."
        self.assertIn("tool: draft_order", risk.code_check(text, PLUG.risk))
        self.assertIn("tool: draft_order", risk.code_check(text, PLUG.risk, tools=True))
        self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])
        self.assertNotIn("tool: draft_order", risk.classify(text, PLUG.risk)[1])


class BringBack(unittest.TestCase):
    def test_a_low_lesson_that_names_a_tool_comes_back_low(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        L = Lessons(db, PLUG, judge=always_low)
        lid = L.propose(NOW_LOW[9], ["ordering"], sources=[], now=1_800_000_000.0)
        self.assertEqual(L.get(lid)["risk"], risk.LOW)
        self.assertTrue(L.pull(lid, "the team asked"))
        back = L.bring_back(lid, "mohamed", now=1_800_000_100.0)
        self.assertEqual(L.get(back)["risk"], risk.LOW)


class NamedPatterns(unittest.TestCase):
    def risk_of(self, *patterns):
        return Risk(high_about="h", low_about="l", words=(), patterns=tuple(("g", p) for p in patterns), tools=())

    def test_a_named_pattern_is_saved_by_its_name(self):
        found = risk.code_check("Ask for size code zz42.", self.risk_of(r"(?#a size code)zz[0-9]{2}"))
        self.assertEqual(found, ["g: /a size code/"])

    def test_an_unnamed_or_empty_named_pattern_is_saved_as_itself(self):
        self.assertEqual(risk.code_check("Say 5.", self.risk_of(r"[0-9]")), ["g: /[0-9]/"])
        self.assertEqual(risk.code_check("Say 5.", self.risk_of(r"(?#)[0-9]")), ["g: /(?#)[0-9]/"])

    def test_the_plug_reasons_carry_no_expression(self):
        why = risk.classify("Tell them the boots cost 1500 EGP.", PLUG.risk)[1]
        self.assertTrue(why)
        for line in why:
            with self.subTest(line=line):
                self.assertNotIn("(?", line)
                self.assertNotIn("\\", line)


class NoteGuardUnchanged(unittest.TestCase):
    THEIRS = ["التوصيل بكام؟"]

    def test_the_note_guard_still_reads_the_old_words(self):
        words = {w.casefold() for _, w in sales_fast.NEVER.words}
        for w in ("name", "phone", "address", "stock", "cash", "offer", "one", "day",
                  "exchange", "available", "شحن", "يوصل"):
            with self.subTest(word=w):
                self.assertIn(w, words)

    def test_a_note_that_only_the_old_list_caught_is_still_refused(self):
        for text in ("Ask for their name before the size.", "Check stock before replying.",
                     "Say we take cash at the door.", "Mention the offer early.", "Say one pair is left in their size.",
                     "Explain how exchange works."):
            with self.subTest(text=text):
                self.assertTrue(engine_fast.guard(text, PLUG, self.THEIRS, never=sales_fast.NEVER))

    def test_the_note_guard_keeps_the_tools_and_the_old_low_line(self):
        self.assertEqual(sales_fast.NEVER.low_about,
                         "Low risk: tone, wording, the order of questions, when to ask for the size, greetings.")
        self.assertNotEqual(sales_fast.NEVER.low_about, PLUG.risk.low_about)
        self.assertEqual(set(sales_fast.NEVER.tools), {t for t in PLUG.risk.tools}
                         - {t for t in PLUG.risk.tools if t.casefold() in sales_fast.TOPIC_WORDS})
        self.assertTrue(engine_fast.guard("Call draft_order early.", PLUG, self.THEIRS, never=sales_fast.NEVER))

    def test_a_tone_note_still_passes(self):
        text = "Ask what they need it for before naming any item."
        self.assertEqual(engine_fast.guard(text, PLUG, self.THEIRS, never=sales_fast.NEVER), [])


if __name__ == "__main__":
    unittest.main()
