"""Review and red team gatefb round 2 fixes (2026-10-31). Price: a clause with a boot or a tier
holds an add-on amount only for an extra named before it (review finding 1); a boot first holds the
extra's price unless a joining word sits between them (review finding 5); an extra first holds it
only as the clause's subject (red team item A); an add-on word counts only before an allowed word or
the clause end (review finding 2, red team item B). Fast notes: a name the customer gave at a start
counts (red team item C); ";" and ":" start no note sentence (review finding 3); a note is read with
a hidden character both ways (red team item E). Made-up text against the demo store data; no model,
no network."""
import unittest

from arena import factcheck
from engine import fast as engine_fast
from reflection import PLUG as SALES
from reflection import fast as sales_fast
from tests.fake_model import clean_env

AC = chr(0x60C)  # the Arabic comma
ZW = chr(0x200B)  # a zero width space, a hidden character


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


def note_guard(text, theirs=(), known=None):
    return engine_fast.guard(text, SALES, list(theirs), never=sales_fast.NEVER,
                             known=sales_fast.known() if known is None else known)


NAMED = "names a word from the source's own words: "


class AddOnInABootClause(unittest.TestCase):
    """Review finding 1: in a clause with a boot or a tier, an add-on amount keeps only the price of
    an extra named before it."""

    def setUp(self):
        clean_env(self)

    def test_the_extra_named_after_the_boots_add_on_amount_is_refused(self):
        for reply in ("The Elite is 400 EGP more, and printing is available too.",
                      "The Vapor 17 Elite is 400 EGP more and printing is included.",
                      "The Vapor 17 Elite is an extra 400 EGP, and we can print your name.",
                      "The Vapor 17 Elite is plus 400 EGP, and printing works too.",
                      "الـ Vapor 17 Elite بـ 400 جنيه زيادة" + AC + " والطباعة متاحة",
                      "The Vapor 17 Elite, 400 EGP more, with your name."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_an_extra_named_before_the_amount_still_counts(self):
        for reply in ("If you add printing to the Elite, it's 400 EGP more.",
                      "Sure, the Vapor 17 Elite can have your name on it, it's 400 EGP extra.",
                      "Adding your name to the Vapor 17 Elite is 400 EGP more.",
                      "For the Vapor 17 Elite, printing is 400 EGP more.",
                      "With printing the Vapor 17 Elite is 400 EGP more.",
                      "We print names, and the Vapor 17 Elite is 400 EGP more."):
            self.assertEqual(checks(reply), [], reply)

    def test_with_no_boot_the_extra_may_come_after(self):
        self.assertEqual(checks("It's 400 EGP more if you want printing."), [])


class BootFirst(unittest.TestCase):
    """Review finding 5 and red team item A: a boot before the extra holds the extra's price unless
    a joining word sits between them, or the extra's price stands before the extra."""

    def setUp(self):
        clean_env(self)

    def test_a_boot_first_with_no_joining_word_holds_the_extras_price(self):
        for reply in ("For the Vapor 17 Elite the printing is 400 EGP.", "Vapor 17 Elite printing is 400 EGP.",
                      "Vapor 17 Elite name printing costs 400 EGP."):
            self.assertEqual(checks(reply), [], reply)

    def test_and_joins_only_with_no_amount_between(self):
        self.assertEqual(checks("The Elite and printing is 400 EGP."), ["price"])
        self.assertEqual(checks("الـ Elite والطباعة بـ 400 جنيه"), ["price"])
        self.assertEqual(checks("الـ Elite بالطباعة 400 جنيه"), ["price"])
        self.assertEqual(checks("The Mercurial Vapor 17 Elite is 16,500 EGP and the name printing 400 EGP."), [])

    def test_a_joining_word_after_an_amount_still_joins(self):
        fee = next(str(int(float(z["fee"]))) for z in factcheck.store.delivery()["zones"] if "fee" in z)
        for reply in (f"The Vapor 17 Elite with {fee} EGP delivery and printing is 400 EGP.",
                      "The Vapor 17 Elite was 16,500 EGP and with printing is 400 EGP.",
                      "The Elite with printing is 400 EGP.", "Elite + printing = 400 EGP."):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_the_extras_price_beside_the_boot_before_the_extra_is_refused(self):
        self.assertEqual(checks("The Vapor 17 Elite is 400 EGP more than the printing."), ["price"])

    def test_a_boot_named_by_its_title_alone_counts(self):  # mutant fc12: boots ignored
        self.assertEqual(checks("The Phantom 6 with printing is 400 EGP."), ["price"])

    def test_an_extra_named_by_any_of_its_words_counts(self):  # mutant fc17: kind words only
        self.assertEqual(checks("The Phantom 6 with your name is 400 EGP."), ["price"])

    def test_a_sum_in_the_clause_holds_the_extras_price(self):
        self.assertEqual(checks("The Vapor 17 Elite with printing comes to 16,900 EGP from 16,500 and 400 EGP."), [])
        self.assertEqual(checks("The Vapor 17 Elite with printing is 16,500 + 400 = 16,900 EGP."), [])


class ExtraFirst(unittest.TestCase):
    """Red team item A: an extra named first holds its price only as the clause's subject."""

    def setUp(self):
        clean_env(self)

    def test_an_extra_that_is_not_the_subject_is_refused(self):
        for reply in ("With printing the Vapor 17 Elite is 400 EGP.",
                      "With your name printed the Vapor 17 Elite is 400 EGP.",
                      "Including printing the Vapor 17 Elite costs 400 EGP.",
                      "With printing included the Vapor 17 Elite is 400 EGP only!",
                      "Printed the Vapor 17 Elite is 400 EGP.",
                      "With the name printing the Vapor 17 Elite comes to 400 EGP.",
                      "بالطباعة الـ Vapor 17 Elite بـ 400 جنيه",
                      "مع الطباعة الـ Vapor 17 Elite هيبقى 400 جنيه بس",
                      "ma3 el tiba3a el Vapor 17 Elite b 400 EGP",
                      "With printing for the Elite the price is 400 EGP.",
                      "بالطباعة على الـ Elite بـ 400 جنيه"):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_the_extra_as_the_subject_passes(self):
        for reply in ("Printing on the Vapor 17 Elite is 400 EGP.",
                      "And the printing for the Elite is 400 EGP.",
                      "Printing is 400 EGP and the Vapor 17 Elite is 16,500 EGP.",
                      "الطباعة على الـ Vapor 17 Elite بـ 400 جنيه"):
            self.assertEqual(checks(reply), [], reply)


class AddOnAllowList(unittest.TestCase):
    """Review finding 2 and red team item B: an add-on word after the amount counts only where its
    clause ends or an allowed word follows."""

    def setUp(self):
        clean_env(self)

    def test_any_other_word_after_it_makes_it_no_add_on(self):
        for reply in ("If you add printing, the Vapor 17 Elite is 400 EGP more or so.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP more-or-less.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP more give or take.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP more ish.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP more at most.",
                      "If you add printing, the Vapor 17 Elite is 400 EGP extra quick.",
                      "The Elite is 400 EGP more costly than the Pro, and printing is available too.",
                      "The Vapor 17 Elite with printing is 400 EGP extra large.",
                      "لو ضفت الطباعة" + AC + " الـ Vapor 17 Elite هيبقى 400 جنيه زيادة على الـ Pro",
                      "لو ضفت الطباعة" + AC + " الـ Vapor 17 Elite هيبقى 400 جنيه زيادة تقريبا",
                      "لو ضفت الطباعة" + AC + " الـ Vapor 17 Elite هيبقى 400 جنيه زيادة شوية"):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_the_clause_end_and_each_allowed_word_keep_it(self):
        start = "The Vapor 17 Elite with printing is 400 EGP "
        for end in ("more.", "extra 🙂", "more EGP.", "more for the name.", "more on the order.", "more to add it.",
                    "more if you want it.", "extra with the name.", "more and worth it.", "more each."):
            self.assertEqual(checks(start + end), [], start + end)
        for reply in ("الـ Vapor 17 Elite مع الطباعة 400 جنيه زيادة عشان الاسم",
                      "الـ Vapor 17 Elite مع الطباعة 400 جنيه زيادة لو عايز",
                      "الـ Vapor 17 Elite مع الطباعة 400 جنيه زيادة وبس"):
            self.assertEqual(checks(reply), [], reply)

    def test_a_hidden_character_neither_joins_nor_hides_a_word(self):
        self.assertEqual(checks("If you add printing, the Vapor 17 Elite is 400 EGP more th" + ZW + "an fair."),
                         ["price"])
        self.assertEqual(checks("If you add printing, the Vapor 17 Elite is 400 EGP more" + ZW + "or less."), ["price"])
        self.assertEqual(checks("The Vapor 17 El" + ZW + "ite with printing is 400 EGP."), ["price"])


class NamesGivenAtAStart(unittest.TestCase):
    """Red team item C: a name the customer gave at a start (a one-word turn, or a turn-opening word
    followed by "here", a comma, a colon or the turn end) counts as written with a capital, unless
    the customer also wrote it in small letters."""

    def setUp(self):
        clean_env(self)

    def test_a_name_given_at_a_start_is_refused_at_a_notes_start(self):
        for cust in ("Ahmed", "AHMED", "\"Ahmed\"", "Ahmed here, size forty two please", "hi\nAhmed here, how much",
                     "hi! Ahmed here, how much?", "Hello. Ahmed from Giza. how much?", "salam; Ahmed here",
                     "Hi: Ahmed", "hi." + ZW + "Ahmed here", "\U0001F44B Ahmed here", "Ahmed here. Which size?",
                     "Karim speaking. size?", "Mona: do you have the Elite?", "Youssef. Price?"):
            name = next(w for w in ("Ahmed", "Karim", "Mona", "Youssef") if w.lower() in cust.lower())
            for text in (f"{name} wants the Elite; ask the size.", f"Ask the size first. {name} wants the Elite."):
                self.assertIn(NAMED + name.lower(), note_guard(text, ["what sizes do you have?", cust]),
                              (cust, text))

    def test_a_one_word_turn_counts_whatever_follows_it(self):
        self.assertIn(NAMED + "ahmed", note_guard("Ahmed wants the Elite.", ["Ahmed \U0001F44B"]))

    def test_a_hidden_character_inside_the_given_name_is_read_as_nothing_too(self):
        self.assertIn(NAMED + "ahmed", note_guard("Ahmed wants the Elite.", ["Ah" + ZW + "med here"]))

    def test_a_name_the_customer_also_wrote_in_small_letters_stays_exempt(self):
        self.assertEqual(note_guard("Ahmed wants the Elite.", ["Ahmed", "yes ahmed"]), [])
        self.assertEqual(note_guard("Ahmed wants the Elite; ask the size.", ["ahmed here"]), [])

    def test_a_word_opening_a_turn_before_other_words_still_does_not_count(self):
        self.assertEqual(note_guard("Recommend a tier, then mention delivery.", ["Recommend a light boot"]), [])
        self.assertEqual(note_guard("Look at what they asked before the price.", ["Look at the photos please"]), [])


class NoteSentenceEnds(unittest.TestCase):
    """Review finding 3: in a note ";" and ":" start no sentence; in the customer's words they still do."""

    def setUp(self):
        clean_env(self)

    def test_a_name_after_a_semicolon_or_colon_in_a_note_is_checked_past_the_start(self):
        for text in ("Ask the size first; Ahmed wants the Elite.", "Ask the size first: Ahmed wants the Elite."):
            self.assertIn(NAMED + "ahmed", note_guard(text, ["ahmed here"]), text)

    def test_a_word_after_a_semicolon_or_colon_in_the_customers_words_is_a_sentence_start(self):
        for cust in ("hi; Recommend a light boot", "hi: Recommend a light boot"):
            self.assertEqual(note_guard("Recommend a tier, then mention delivery.", [cust]), [], cust)


class HiddenCharactersInANote(unittest.TestCase):
    """Red team item E: a note is read with a hidden character as nothing and as a space."""

    def setUp(self):
        clean_env(self)

    def test_a_hidden_character_neither_fuses_nor_splits_a_name(self):
        self.assertIn(NAMED + "ahmed", note_guard("Ask" + ZW + "Ahmed about the size.", ["hi I am Ahmed"]))
        self.assertIn(NAMED + "ahmed", note_guard("Ask Ah" + ZW + "med about the size.", ["hi I am Ahmed"]))

    def test_any_space_between_a_places_words_keeps_it_whole(self):  # mutant ef12
        text = "Ask if Sheikh" + chr(0x1680) + "Zayed is close."
        self.assertEqual(engine_fast.guard(text, SALES, ["I am in Sheikh Zayed"], known=("Sheikh Zayed",)), [])


if __name__ == "__main__":
    unittest.main()
