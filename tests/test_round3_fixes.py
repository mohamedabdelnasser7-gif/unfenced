"""Round 3 fixes (2026-10-31; DECISIONS item 52, review round 3 findings 2, 3 and 4). The price check
keeps an add-on's price when an add-on word sits right beside the amount, and a bracket or a spaced
dash sets an aside apart like a comma. The fast note name check lets the agent's own words through
(catalogue, places, the plug's own names) and checks a sentence's first word unless it opens a
note; "on us" and "final" are whole words on the note guard's side. A Gmail label line between two
delivery lines is the sender's. Made-up text on the demo catalogue only."""
import dataclasses
import email
import unittest

from arena import factcheck
from assistant import mbox
from engine import fast as engine_fast
from engine import risk
from kit.db import Db
from reflection import PLUG as SALES
from reflection import fast as sales_fast
from tests import plugs
from tests.fake_model import clean_env

AC = chr(0x60C)  # the Arabic comma


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class AddOnWords(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_an_add_on_word_beside_the_amount_keeps_the_extras_price(self):
        for reply in ("If you add printing to the Elite, it's 400 EGP more.",
                      "Sure, the Vapor 17 Elite can have your name on it, it's 400 EGP extra.",
                      "لو عايز اسمك على الـ Vapor 17 Elite" + AC + " هتبقى 400 جنيه زيادة",
                      "Vapor Elite with printing, plus 400 EGP.",
                      "Vapor Elite 16,500, an extra 400 for your name.",
                      "The Vapor 17 Elite with printing, 400 EGP on top.",
                      "الـ Vapor 17 Elite مع اسمك زيادة 400 جنيه",
                      "Vapor 17 Elite with name printing: 16,900 EGP (16,500 + 400)."):
            self.assertEqual(checks(reply), [], reply)

    def test_the_word_must_sit_beside_the_amount_and_the_extra_be_named(self):
        for reply in ("The Vapor 17 Elite is 400 EGP more.",                # no extra named anywhere
                      "Vapor Elite 16,500 plus 400",
                      "Vapor Elite 16,500; the printing is on top: 400",   # a colon between
                      "Vapor Elite with printing, 1400 EGP extra.",        # not the extra's price
                      "Vapor Elite with printing, 4000 more."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_round_2_refusals_still_hold(self):
        for reply in ("The Vapor 17 Elite, with printing, is 400 EGP.", "The Vapor 17 Elite with printing: 400 EGP.",
                      "Vapor Elite, 400 EGP, with your name.", "The Vapor 17 Elite is 400 EGP",
                      "The Vapor 17 Elite, printing included, is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)


class Asides(unittest.TestCase):
    """Review round 3, item 4: the guard lines no test caught on their own."""

    def setUp(self):
        clean_env(self)

    def test_a_bracket_or_a_spaced_dash_aside_is_cut_like_a_comma(self):
        for reply in ("The Vapor 17 Elite (with printing) is 400 EGP.",
                      "The Vapor 17 Elite [with printing] is 400 EGP.",
                      "The Vapor 17 Elite - with printing - is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)
        for reply in ("Phantom 6 Elite (with your name printed): 16,900 EGP", "Superfly 11 Elite (20,000 EGP).",
                      "Printing (400 EGP) goes on any boot."):
            self.assertEqual(checks(reply), [], reply)

    def test_an_extra_price_before_the_boot_in_its_sentence_fails(self):
        """The sentence names a boot after the price: the backdrop does not hold it (sentence_boot)."""
        for reply in ("It's 400 EGP, the Vapor 17 Elite with printing.",
                      "400 EGP, with printing, for the Vapor 17 Elite."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_a_boot_named_with_no_tier_counts_as_a_boot(self):
        for reply in ("The Mercurial Vapor, with printing, is 400 EGP.", "The Phantom, with your name, is 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_a_boot_price_in_a_clause_after_the_extra_alone_fails(self):
        """The clause takes the extra from the clause before it (inheritance)."""
        for reply in ("Printing, 16,500 EGP.", "The name printing, 16,500 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)


def note_guard(text, theirs=(), known=None):
    return engine_fast.guard(text, SALES, list(theirs), never=sales_fast.NEVER,
                             known=sales_fast.known() if known is None else known)


CUSTOMER = ("Hi, I am Ahmed from Cairo. Is the Nike Mercurial Vapor 17 Elite or the Pro better for me? "
            "I found you on WhatsApp, can I ask about the size?")


class NoteNames(unittest.TestCase):
    """Review round 3, finding 3: the name check refused the catalogue and place words."""

    def setUp(self):
        clean_env(self)

    def test_catalogue_and_place_words_the_customer_typed_pass(self):
        for text in ("Compare the Elite and Pro tiers before bringing up the price.",
                     "Mention how the Nike Vapor fits, then ask about size.",
                     "Ask if Cairo is where they want delivery, then mention the price."):
            self.assertEqual(note_guard(text, [CUSTOMER]), [], text)

    def test_a_word_the_plug_itself_writes_with_a_capital_passes(self):
        self.assertEqual(note_guard("Keep the chat on WhatsApp short and ask about size early.", [CUSTOMER], known=()),
                         [])

    def test_a_first_word_the_plug_itself_opens_with_passes_for_any_agent(self):
        """The waterer plug's action "Water the bed." makes water the agent's own verb."""
        plug = plugs.load(plugs.WATERER, self)
        self.assertEqual(engine_fast.guard("Water this bed once.", plug, ["please water it"]), [])
        self.assertTrue(engine_fast.guard("Mist this bed once.", plug, ["please mist it"]))

    def test_a_name_the_customer_gave_is_still_refused(self):
        for text in ("Ask Ahmed first about the size.", "Mr. Ahmed asked about the size; bring it up early."):
            self.assertIn("names a word from the source's own words: ahmed", note_guard(text, [CUSTOMER]), text)

    def test_a_first_word_name_in_the_customers_words_is_refused(self):
        text = "Ahmed wants the Elite; ask about the size early."
        self.assertIn("names a word from the source's own words: ahmed", note_guard(text, [CUSTOMER]))
        self.assertEqual(note_guard(text, ["Is the Vapor 17 Elite good?"]), [])  # not the customer's own word

    def test_a_note_may_open_with_a_verb_or_small_word_the_customer_typed(self):
        for text in ("Ask about the size before anything else.", "Then bring up delivery once they pick a tier."):
            self.assertEqual(note_guard(text, ["can I ask you what size then?"]), [], text)

    def test_the_sales_notes_read_the_catalogue_words(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        note = "Mention how the Vapor Elite fits before the price."
        fast = sales_fast.FastNotes(db, writer=lambda plug, view: note)
        self.assertEqual(fast._write({}, ["Is the Vapor good, or the Elite?"]), (note, None))

    def test_a_catalogue_that_cannot_answer_lets_no_word_through(self):
        db = Db(":memory:")
        self.addCleanup(db.close)

        def broken():
            raise OSError("the store is down")
        fast = engine_fast.FastNotes(db, SALES, writer=lambda plug, view: "Mention the Vapor first.",
                                     never=sales_fast.NEVER, known=broken)
        text, why = fast._write({}, ["Is the Vapor good?"])
        self.assertIsNone(text)
        self.assertIn("names a word from the source's own words: vapor", why)


class WholeNeverWords(unittest.TestCase):
    """Review round 3, finding 3: "on us" read inside "on using", "final" inside "finally"."""

    def test_on_us_and_final_inside_longer_words_pass(self):
        for text in ("Focus on using the size question first.", "Ask about the size, and finally bring up delivery."):
            self.assertEqual(note_guard(text, known=()), [], text)

    def test_on_us_and_final_as_words_are_still_refused(self):
        for text in ("Say the delivery is on us.", "Say the offer is final.", "Say these are the finals."):
            self.assertTrue(note_guard(text, known=()), text)

    def test_a_plug_word_on_the_whole_list_stays_whole(self):
        """A plug that lists "final" as a word does not bring its endings back."""
        never = sales_fast._never(dataclasses.replace(SALES.risk, words=SALES.risk.words + (("policy", "final"),)))
        text = "Ask about the size, and finally bring up delivery."
        self.assertEqual(engine_fast.guard(text, SALES, [], never=never), [])
        self.assertTrue(engine_fast.guard("Say the offer is final.", SALES, [], never=never))

    def test_the_lesson_risk_check_reads_its_words_as_before(self):
        """Root's call: engine/risk.py is shared with the lesson risk check and keeps its endings."""
        self.assertTrue(risk._word("on us").search("focus on using"))
        self.assertTrue(risk._word("final").search("finally"))


class LabelBetweenTraceLines(unittest.TestCase):
    """Review round 3, finding 4: a label line between two Received lines came inside an outside mail."""

    def test_a_label_line_between_two_received_lines_is_not_sent(self):
        raw = ("Received: from mx.evil.test by mx.demo.test\nX-Gmail-Labels: Sent\n"
               "Received: from fake.evil.test by fake.evil.test\nFrom: nadia@demo.test\n\nhi\n")
        self.assertFalse(mbox.is_sent(email.message_from_string(raw), "nadia@demo.test"))
        above = "X-Gmail-Labels: Sent\nReceived: by mx.demo.test\nFrom: nadia@demo.test\n\nhi\n"
        self.assertTrue(mbox.is_sent(email.message_from_string(above), "nadia@demo.test"))


if __name__ == "__main__":
    unittest.main()
