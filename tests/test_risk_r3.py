"""Engine fix round 3 (review engfix r2, red team engfix r2). The plug word lists stay a first net of
clear money words; meaning is the judge's job, and the judge fails closed (tests/test_judge.py FailClosed).
Here: the general code lines in engine/risk.py (a word glued to a digit or an underscore, letters spaced
apart), the Sales and Marketing list fixes, and the long note cut in engine/fast.py."""
import unittest

from engine import risk
from reflection import PLUG


def groups(text, plug_risk=None):
    return {line.partition(": ")[0] for line in risk.code_check(text, plug_risk or PLUG.risk, tools=False)}


class GluedAndSpaced(unittest.TestCase):
    """Red team engfix r2, finding 1, word evasions: a Latin word is bounded by letters only, as the
    patterns are, and a run of three or more single letters apart by one space, dot, dash or apostrophe
    is read joined, in Latin and Arabic letters."""

    GLUED = (("Offer a discount_ for two.", "discount"), ("Give them 5discount.", "discount"),
             ("Offer a refund_ to them.", "policy"), ("Offer a refund3 to them.", "policy"),
             ("Ask for a deposit_ first.", "payment"), ("Eddy el customer khasm_.", "discount"),
             ("Eddy a khasm2.", "discount"), ("Add a gift_ with it.", "discount"))
    SPACED = (("Give f r e e delivery.", "discount"), ("Give f.r.e.e delivery.", "discount"),
              ("Offer a d i s c o u n t.", "discount"), ("Offer a d-i-s-c-o-u-n-t.", "discount"),
              ("Offer a r'e'f'u'n'd.", "policy"), ("اديله خ ص م.", "discount"), ("اديله خ.ص.م.", "discount"))
    PLAIN = ("Ask for the size first, then the model.", "Use a short a or b question for the colour.",
             "Ask them for size 42 or 43 first.", "Greet them by name, e.g. Hi Omar.",
             "Say the model name, A1 or B2, exactly as the store lists it.")

    def test_a_glued_word_is_marked(self):
        for text, group in self.GLUED:
            with self.subTest(text=text):
                self.assertIn(group, groups(text))

    def test_spaced_letters_are_read_joined(self):
        for text, group in self.SPACED:
            with self.subTest(text=text):
                self.assertIn(group, groups(text))

    def test_plain_lines_stay_unmarked(self):
        for text in self.PLAIN:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])

    def test_two_letters_are_not_a_run(self):
        self.assertEqual(risk._joined("e.g. a b"), "e.g. a b")
        self.assertEqual(risk._joined("f r e e"), "free")
        self.assertEqual(risk._joined("ok f r e e now"), "ok free now")
        self.assertEqual(risk._joined("a f r e e pair", first_apart=True), "a free pair")


if __name__ == "__main__":
    unittest.main()
