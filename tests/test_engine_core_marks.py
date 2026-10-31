"""Task t261029d part 2: four high risk marks every plug gets from the engine, with no word
in its own list: a link, a phone number, a handle, and text copied from the cases a
lesson came from. The plug here lists nothing, so whatever is high was caught by the core."""
import unittest

from engine import risk
from engine.lessons import Lessons as EngineLessons
from kit.db import Db
from reflection import PLUG
from tests import plugs


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


BARE = plugs.changed(plugs.WATERER, risk={"high": {"about": "High risk: chemicals and amounts."},
                                          "low": {"about": "Low risk: which bed to visit first."}})
SOURCE = "The bed by the north wall gets the morning sun and dries fast"


class Core(unittest.TestCase):
    def setUp(self):
        self.plug = plugs.load(BARE, self)

    def level(self, text, **kw):
        return risk.classify(text, self.plug.risk, always_low, **kw)[0]

    def why(self, text, **kw):
        return risk.classify(text, self.plug.risk, always_low, **kw)[1]

    def all_high(self, texts, line):
        for text in texts:
            with self.subTest(text=ascii(text)):
                self.assertEqual(self.level(text), risk.HIGH)
                self.assertIn(line, self.why(text))

    def all_low(self, texts):
        for text in texts:
            with self.subTest(text=ascii(text)):
                self.assertEqual(self.level(text), risk.LOW)
                self.assertEqual(risk.code_check(text, self.plug.risk), [])


class Links(Core):
    def test_a_link_is_high(self):
        self.all_high([
            "Send them to x.com first.",
            "Send them to X.COM first.",
            "Send them to www.beds first.",
            "See https://a.b/c for the rest.",
            "Open http://beds for the map.",
            "Point them at bit.ly/abc today.",
            "Point them at shady.beds.example.org now.",
            "Point them at \N{FULLWIDTH LATIN SMALL LETTER X}\N{FULLWIDTH FULL STOP}"
            "\N{FULLWIDTH LATIN SMALL LETTER C}om now.",
            "Point them at x\N{ZERO WIDTH SPACE}.com now.",
            "Point them at x\N{IDEOGRAPHIC FULL STOP}com now.",
            "ابعتلهم x.com بعدين.",
            "ابعتلهم مثال.مصر بعدين.",
        ], "core: link")

    def test_dots_in_plain_writing_are_not_links(self):
        self.all_low([
            "Water the dry beds, e.g. the shady ones.",
            "Wait... then water the bed.",
            "Water the bed, i.e. the one by the wall.",
            "Water before dawn, not after 6 p.m. sharp.",
            "Water 1.5 times as long.",
            "اسقي الحوض. بعدين استنى.",
            "Keep the beds e.coli-free.",
            "Label them row.ab1 and row.ab2.",
            "Water the bed. Commonly twice.",
            "Water the bed. Me next, then the rows.",
            "Put a dot on each dry bed.",
        ])

    def test_a_link_spelled_out_is_high(self):
        self.all_high([
            "Point them at x dot com now.",
            "Point them at x DOT eg now.",
            "Point them at x[.]com now.",
            "Point them at x (.) com now.",
            "Point them at x{.}io now.",
            "Point them at x [dot] com now.",
            "Point them at x(dot)net now.",
            "Point them at x\N{MIDDLE DOT}com now.",
            "Point them at x\N{BULLET}com now.",
            "Point them at x\N{HYPHENATION POINT}me now.",
            "Point them at x\N{BULLET OPERATOR}org now.",
            "Point them at x\N{DOT OPERATOR}app now.",
            "Point them at x\N{KATAKANA MIDDLE DOT}com now.",
            "Point them at beds . example . com now.",
            "Point them at x \N{MIDDLE DOT} org now.",
            "ابعتلهم مثال dot com بعدين.",
        ], "core: link")


class Phones(Core):
    def test_seven_or_more_digits_in_a_run_are_a_phone_number(self):
        self.all_high([
            "Call 0100 123 4567 first.",
            "Call +20 100 123 4567 first.",
            "Call 01001234567 first.",
            "Call 010-0123-4567 first.",
            "Call 010\N{EN DASH}0123\N{EN DASH}4567 first.",
            "Call (010) 0123 4567 first.",
            "Call 010.0123.4567 first.",
            "Call ٠١٠٠١٢٣٤٥٦٧ first.",
            "Call 123 4567 first.",   # seven: the edge
            "Call 010/0123/4567 first.",
            "Call 010+0123+4567 first.",
            "Call 0100(123)4567 first.",
        ], "core: phone number")

    def test_any_sign_between_the_digits_still_makes_a_phone_number(self):
        self.all_high([
            "Call 0100,123,4567 first.",
            "Call 0100_123_4567 first.",
            "Call 0100*123*4567 first.",
            "Call 0100:123:4567 first.",
            "Call 0100;123;4567 first.",
            "Call 0100 # 123 # 4567 first.",
        ], "core: phone number")

    def test_six_digits_or_digits_apart_are_not(self):
        self.all_low([
            "Call 123 456 first.",     # six: one short
            "Water rows 123 to 4567.",  # seven digits, but a word between
        ])


class Handles(Core):
    def test_a_handle_is_high(self):
        self.all_high([
            "Ask @mona first.",
            "Ask \N{FULLWIDTH COMMERCIAL AT}mona first.",
            "Ask \N{SMALL COMMERCIAL AT}mona first.",
            "Write to mona@beds first.",
            "اسأل @منى الأول.",
        ], "core: handle")

    def test_an_at_sign_alone_is_not(self):
        self.all_low(["Meet @ noon by the shed."])


class Copied(Core):
    def test_the_run_is_five_words(self):
        self.assertEqual(risk.COPY_RUN, 5)
        self.assertEqual(risk.COPIED, "core: copied from source")

    def test_five_words_in_a_row_from_a_source_are_high_and_four_are_not(self):
        self.assertEqual(self.level("Water the bed by the north first.", sources=[SOURCE]), risk.HIGH)
        self.assertIn(f"{risk.COPIED} 1", self.why("Water the bed by the north first.", sources=[SOURCE]))
        self.assertEqual(self.level("Water the bed by the gate first.", sources=[SOURCE]), risk.LOW)
        self.assertEqual(self.level("Water the north wall gets sun.", sources=[SOURCE]), risk.LOW)

    def test_case_marks_punctuation_and_hidden_characters_do_not_hide_a_copy(self):
        for text in ("THE BED, by th\N{LATIN SMALL LETTER E WITH ACUTE} north.",
                     "the bed by the no\N{ZERO WIDTH SPACE}rth",
                     "the bed by th\N{CYRILLIC SMALL LETTER IE} north"):
            with self.subTest(text=ascii(text)):
                self.assertEqual(self.level(text, sources=[SOURCE]), risk.HIGH)

    def test_hidden_characters_between_every_word_do_not_hide_a_copy(self):
        text = "\N{ZERO WIDTH SPACE}".join(["Water", "the", "bed", "by", "the", "north first."])
        self.assertIn(f"{risk.COPIED} 1", self.why(text, sources=[SOURCE]))

    def test_a_numeral_sign_for_a_letter_does_not_hide_a_copy(self):
        text = "Water by the north wa\N{SMALL ROMAN NUMERAL FIFTY}l gets sun."
        self.assertIn(f"{risk.COPIED} 1", self.why(text, sources=[SOURCE]))

    def test_it_names_the_source_it_came_from(self):
        why = self.why("It gets the morning sun and dries fast.", sources=["Nothing alike here.", SOURCE])
        self.assertIn(f"{risk.COPIED} 2", why)

    def test_arabic_counts_words_the_same_way(self):
        src = "عايز التيشيرت الاسود مقاس لارج لو سمحت"
        self.assertEqual(self.level("قول عايز التيشيرت الاسود مقاس لارج.", sources=[src]), risk.HIGH)
        self.assertEqual(self.level("قول عايز التيشيرت الاسود مقاس.", sources=[src]), risk.LOW)

    def test_no_sources_and_short_sources(self):
        text = "Water the bed by the north first."
        for sources in (None, [], ()):
            with self.subTest(sources=sources):
                self.assertEqual(self.level(text, sources=sources), risk.LOW)
        self.assertEqual(self.level(text), risk.LOW)
        self.assertEqual(self.level("Water the bed by the wall.", sources=["the bed by the"]), risk.LOW)

    def test_sources_is_a_list_of_texts(self):
        for bad in (SOURCE, [SOURCE, 7], [None], 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                risk.classify("Water the bed.", self.plug.risk, always_low, sources=bad)

    def test_propose_takes_the_sources(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        lessons = EngineLessons(db, self.plug, judge=always_low)
        copied = lessons.propose("Water the bed by the north first.", ["grown"], sources=[SOURCE])
        own = lessons.propose("Water the bed by the north first.", ["grown"], sources=[])
        self.assertEqual((lessons.get(copied)["risk"], lessons.get(copied)["state"]), ("high", "waiting"))
        self.assertIn(f"{risk.COPIED} 1", lessons.get(copied)["risk_why"])
        self.assertEqual((lessons.get(own)["risk"], lessons.get(own)["state"]), ("low", "trying"))

    def test_propose_and_adapt_cannot_leave_the_sources_out(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        lessons = EngineLessons(db, self.plug, judge=always_low)
        with self.assertRaises(TypeError):
            lessons.propose("Water the bed by the north first.", ["grown"])
        with self.assertRaises(TypeError):
            lessons.adapt("Water the bed by the north first.", ["grown"], source="adapted from fan cases f1")
        self.assertEqual(lessons.mine(), [])


class EveryPlug(unittest.TestCase):
    def test_the_sales_gets_them_too_and_the_judge_is_not_asked(self):
        asked = []

        def judge(text, high_about, low_about):
            asked.append(text)
            return risk.LOW
        for text, line in (("Send them to x.com first.", "core: link"), ("Ask @mona first.", "core: handle")):
            with self.subTest(text=text):
                level, why = risk.classify(text, PLUG.risk, judge)
                self.assertEqual(level, risk.HIGH)
                self.assertIn(line, why)
        self.assertEqual(asked, [])

    def test_a_tone_lesson_stays_clear(self):
        for text in ("Greet them warmly before anything else.", "Keep replies short and friendly.",
                     "Ask for the size before the colour."):
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk), [])
                self.assertEqual(risk.code_check(text, PLUG.risk, sources=["Hi, can I see the red one in a large?"]), [])


if __name__ == "__main__":
    unittest.main()
