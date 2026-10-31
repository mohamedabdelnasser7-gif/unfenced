"""Task t261029d part 1: the risk check folds disguised letters before it matches. An accent,
a letter from another script that looks Latin, a wide form or a numeral sign cannot hide
a word on the risk list. Every text here is written with Unicode names, so no look alike
letter sits in this file as a raw character."""
import unittest

from engine import risk
from reflection import PLUG
from tests import plugs


def always_low(text, high_about, low_about):
    """A judge that says low to everything: what is still high was caught by the code check."""
    return risk.LOW


DISGUISED = [
    "Bring up the r\N{LATIN SMALL LETTER E WITH ACUTE}fund early.",          # one accented letter
    "Bring up the re\N{COMBINING ACUTE ACCENT}fund early.",                  # the accent as its own mark
    "Bring up the g\N{LATIN SMALL LETTER U WITH ACUTE}arantee early.",
    "Bring up the g\N{LATIN SMALL LETTER U WITH GRAVE}arant\N{LATIN SMALL LETTER E WITH ACUTE}e early.",
    "Bring up the r\N{CYRILLIC SMALL LETTER IE}fund early.",                 # a Cyrillic e
    "Bring up the R\N{CYRILLIC CAPITAL LETTER IE}FUND early.",
    "Bring up the \N{CYRILLIC SMALL LETTER ER}olicy early.",                 # a Cyrillic p
    "Bring up the pr\N{GREEK SMALL LETTER OMICRON}mise early.",              # a Greek o
    "Bring up the \N{GREEK SMALL LETTER RHO}romise early.",                  # a Greek p
    "Bring up the pol\N{LATIN SMALL LETTER DOTLESS I}cy early.",             # a dotless i
    "Bring up the \N{LATIN LETTER SMALL CAPITAL R}\N{LATIN LETTER SMALL CAPITAL E}"
    "\N{LATIN LETTER SMALL CAPITAL F}\N{LATIN LETTER SMALL CAPITAL U}\N{LATIN LETTER SMALL CAPITAL N}"
    "\N{LATIN LETTER SMALL CAPITAL D} early.",                               # small capitals
    "Bring up the ref\N{DEVANAGARI SIGN VISARGA}und early.",                 # a spacing mark inside the word
    "Say \N{ROMAN NUMERAL TWELVE} for both.",                                # a numeral sign
    "Say \N{SMALL ROMAN NUMERAL FOUR} for both.",
    "Say \N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT TWO} for both.",          # wide digits
]

STILL_CLEAR = [  # tone lessons with accents or other scripts find nothing on the code check
    "Greet them with a warm caf\N{LATIN SMALL LETTER E WITH ACUTE} style hello.",
    "Say \N{CYRILLIC SMALL LETTER ES}\N{CYRILLIC SMALL LETTER PE}\N{CYRILLIC SMALL LETTER A}"
    "\N{CYRILLIC SMALL LETTER ES}\N{CYRILLIC SMALL LETTER I}\N{CYRILLIC SMALL LETTER BE}"
    "\N{CYRILLIC SMALL LETTER O} at the end.",
    "رحب بيهم بلطف.",
]


class DisguisedLetters(unittest.TestCase):
    def test_a_disguised_risk_word_is_high_with_an_always_low_judge(self):
        for text in DISGUISED:
            with self.subTest(text=ascii(text)):
                self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)

    def test_the_reason_names_the_word_it_found(self):
        why = risk.classify("Bring up the r\N{CYRILLIC SMALL LETTER IE}fund early.", PLUG.risk, always_low)[1]
        self.assertIn("promise: refund", why)
        why = risk.classify("Say \N{ROMAN NUMERAL TWELVE} for both.", PLUG.risk, always_low)[1]
        self.assertIn("number: /[0-9]/", why)

    def test_tone_with_accents_or_other_scripts_stays_clear(self):
        for text in STILL_CLEAR:
            with self.subTest(text=ascii(text)):
                self.assertEqual(risk.code_check(text, PLUG.risk), [])

    def test_arabic_and_its_digits_still_read(self):
        for text in ("Say the boots are ٥٠٠ جنيه.", "Say ۵۰۰ for the pair.", "قول إن التَّوْصِيل سريع.",
                     "قول له هيوصل بكرة."):
            with self.subTest(text=text):
                self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)


class TheNormalForm(unittest.TestCase):
    def test_marks_go_and_look_alikes_read_as_latin(self):
        self.assertEqual(risk.normalize("r\N{LATIN SMALL LETTER E WITH ACUTE}fund"), "refund")
        self.assertEqual(risk.normalize("g\N{LATIN SMALL LETTER U WITH ACUTE}arantee"), "guarantee")
        self.assertEqual(risk.normalize("r\N{CYRILLIC SMALL LETTER IE}fund"), "refund")
        self.assertEqual(risk.normalize("\N{CYRILLIC CAPITAL LETTER ER}\N{CYRILLIC CAPITAL LETTER A}Y"), "pay")

    def test_a_capital_and_its_small_letter_can_look_like_different_latin_letters(self):
        """Greek capital eta looks like H and its small letter like n; capital nu is N, small nu is v."""
        self.assertEqual(risk.normalize("\N{GREEK CAPITAL LETTER ETA}"), "h")
        self.assertEqual(risk.normalize("\N{GREEK SMALL LETTER ETA}"), "n")
        self.assertEqual(risk.normalize("\N{GREEK CAPITAL LETTER NU}"), "n")
        self.assertEqual(risk.normalize("\N{GREEK SMALL LETTER NU}"), "v")

    def test_a_capital_left_out_of_the_table_reads_through_its_small_letter(self):
        self.assertEqual(risk.normalize("\N{GREEK CAPITAL LETTER YOT}am"), "jam")

    def test_numeral_signs_read_as_their_digits(self):
        self.assertEqual(risk.normalize("\N{ROMAN NUMERAL TWELVE}"), "12")
        self.assertEqual(risk.normalize("\N{SMALL ROMAN NUMERAL ONE}"), "1")
        self.assertEqual(risk.normalize("\N{ROMAN NUMERAL ONE THOUSAND C D}"), "1000")
        self.assertEqual(risk.normalize("\N{FULLWIDTH DIGIT FIVE}\N{FULLWIDTH DIGIT ZERO}"), "50")

    def test_every_dash_reads_as_one(self):
        for dash in ("\N{HYPHEN}", "\N{EN DASH}", "\N{EM DASH}", "\N{MINUS SIGN}", "\N{FIGURE DASH}"):
            with self.subTest(dash=ascii(dash)):
                self.assertEqual(risk.normalize("1" + dash + "2"), "1-2")


class BothSidesFold(unittest.TestCase):
    """The plug's own words fold the same way, so a word written with a look alike still matches."""

    def test_a_plug_word_with_a_look_alike_matches_plain_text(self):
        bed = plugs.changed(plugs.WATERER, risk={
            "high": {"about": "High risk: chemicals.",
                     "words": {"chemicals": ["p\N{CYRILLIC SMALL LETTER O}ison", "bl\N{LATIN SMALL LETTER E WITH ACUTE}ach"]}},
            "low": {"about": "Low risk: the round."}})
        p = plugs.load(bed, self)
        for text in ("Use the poison.", "Use the bleach.", "Use the p\N{GREEK SMALL LETTER OMICRON}ison."):
            with self.subTest(text=ascii(text)):
                self.assertEqual(risk.classify(text, p.risk, always_low)[0], risk.HIGH)
        self.assertEqual(risk.classify("Visit the shady beds first.", p.risk, always_low)[0], risk.LOW)


# Words only, no pattern: the waterer's own [0-9] pattern would catch a numeral sign read as
# a digit, and these tests are about the words.
WORDS_ONLY = plugs.changed(plugs.WATERER, risk={
    "high": {"about": "High risk: chemicals and money.",
             "words": {"chemicals": ["poison", "pesticide", "bleach"],
                       "money": ["توصيل", "كوبون", "مصاريف"]}},
    "low": {"about": "Low risk: which bed to visit first."}})


class MoreDisguises(unittest.TestCase):
    """Review t261029i: disguises the first fold missed."""

    def setUp(self):
        self.plug = plugs.load(WORDS_ONLY, self)

    def all_high(self, texts, line):
        for text in texts:
            with self.subTest(text=ascii(text)):
                level, why = risk.classify(text, self.plug.risk, always_low)
                self.assertEqual(level, risk.HIGH)
                self.assertIn(line, why)

    def test_a_numeral_sign_inside_a_word_reads_as_its_letter(self):
        self.all_high(["Add po\N{SMALL ROMAN NUMERAL ONE}son to the bed."], "chemicals: poison")
        self.all_high(["Use b\N{SMALL ROMAN NUMERAL FIFTY}each weekly."], "chemicals: bleach")
        self.all_high(["Spray pesti\N{SMALL ROMAN NUMERAL ONE HUNDRED}ide."], "chemicals: pesticide")

    def test_the_letter_form_and_the_digit_form(self):
        self.assertEqual(risk.normalize("\N{ROMAN NUMERAL TWELVE}"), "12")
        self.assertEqual(risk.normalize("\N{ROMAN NUMERAL TWELVE}", letters=True), "xii")
        self.assertEqual(risk.normalize("b\N{SMALL ROMAN NUMERAL FIFTY}each", letters=True), "bleach")

    def test_lisu_cherokee_and_rarer_look_alikes(self):
        self.all_high(["Add \N{LISU LETTER PA}OISON to the bed.",
                       "Add po\N{LATIN SMALL LETTER IOTA}son to the bed."], "chemicals: poison")
        self.all_high(["Use b\N{CHEROKEE LETTER TLE}EACH weekly.",
                       "Use b\N{LISU LETTER LA}EACH weekly."], "chemicals: bleach")
        self.all_high(["Spray pesti\N{CHEROKEE LETTER TLI}ide.",
                       "Spray pesti\N{CHEROKEE SMALL LETTER TLI}ide.",
                       "Spray pesti\N{GREEK LUNATE SIGMA SYMBOL}ide."], "chemicals: pesticide")

    def test_the_table_is_read_before_nfkd_and_after_case_is_folded(self):
        # NFKD turns a lunate sigma into a final sigma, so the table must be read first.
        self.assertEqual(risk.normalize("\N{GREEK LUNATE SIGMA SYMBOL}"), "c")
        # A small Cherokee letter folds to its capital; the capital's Latin letter comes out small.
        self.assertEqual(risk.normalize("\N{CHEROKEE SMALL LETTER A}"), "d")
        self.assertEqual(risk.normalize("\N{CHEROKEE LETTER TLI}"), "c")

    def test_a_blank_letter_inside_a_word_hides_nothing(self):
        for blank in ("\N{HANGUL FILLER}", "\N{HALFWIDTH HANGUL FILLER}", "\N{HANGUL CHOSEONG FILLER}",
                      "\N{HANGUL JUNGSEONG FILLER}", "\N{BRAILLE PATTERN BLANK}"):
            self.all_high([f"Add poi{blank}son to the bed."], "chemicals: poison")

    def test_persian_keyboard_letters_read_as_arabic(self):
        self.all_high(["توص\N{ARABIC LETTER FARSI YEH}ل مجاني"], "money: توصيل")
        self.all_high(["\N{ARABIC LETTER KEHEH}وبون"], "money: كوبون")
        self.all_high(["مصار\N{ARABIC LETTER FARSI YEH}ف"], "money: مصاريف")
        for heh in ("\N{ARABIC LETTER HEH GOAL}", "\N{ARABIC LETTER HEH DOACHASHMEE}", "\N{ARABIC LETTER AE}",
                    "\N{ARABIC LETTER HEH WITH YEH ABOVE}"):
            with self.subTest(heh=ascii(heh)):
                self.assertEqual(risk.normalize(heh), "ه")


if __name__ == "__main__":
    unittest.main()
