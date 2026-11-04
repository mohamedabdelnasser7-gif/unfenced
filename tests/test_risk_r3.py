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



class FalsePositiveFixes(unittest.TestCase):
    """Review engfix r2, finding 2: the reviewer's fix list. The p5 lines now low are in
    tests/test_risk_sweep.py STAYS_LOW; here, beside each narrowed pattern, the money lines it still marks."""

    STILL = (
        ("Skip the delivery fee for repeat buyers.", "discount"), ("Cover the shipping for them.", "discount"),
        ("Don't charge delivery on a second pair.", "discount"), ("Never add extra fees.", "discount"),
        ("Bring the price down when they ask.", "discount"), ("Round the bill down.", "discount"),
        ("Put a water bottle in every order.", "discount"), ("Add a keychain to each order.", "discount"),
        ("Send 50 pounds credit with every order.", "discount"),
        ("Tell them we will make sure it arrives early.", "promise"),
        ("Tell them they'll have it before the weekend.", "promise"), ("Say it will be with them soon.", "promise"),
        ("Tell them they will receive it in two days.", "promise"),
        ("Say 1 500 for the pair.", "amount"), ("Say 1.500 for the pair.", "amount"), ("Say 1,500.", "amount"),
        ("Say 95 pounds for the pair.", "amount"), ("Say 60 for delivery.", "amount"),
        ("Charge 75 EGP for Alex.", "amount"), ("Quote them 1450.", "amount"),
        ("قوله 150 للجوز.", "amount"), ("قوله 95 جنيه.", "amount"), ("قول 95 للجوز التاني.", "amount"),
        ("2olo 150 lel goz.", "amount"), ("2olo 95 geneh.", "amount"), ("2olo khamsin.", "amount"),
        ("خلي التوصيل بلاش.", "discount"), ("خلي الشحن بلاش للقاهرة.", "discount"), ("الشحن علينا", "discount"),
        ("khally el delivery balash.", "discount"), ("el sha7n balash lel order el tany.", "discount"),
        ("el sha7n 3alena", "discount"), ("قوله هيوصل في أسرع وقت.", "promise"),
        ("اعمل لهم عرض على الجوز التاني.", "discount"), ("اعمل عرض خاص.", "discount"),
    )

    def test_each_narrowed_pattern_still_marks_money(self):
        for text, group in self.STILL:
            with self.subTest(text=text):
                self.assertIn(group, groups(text))

    def test_a_size_list_or_a_half_size_is_not_an_amount(self):
        for text in ("Sizes 40 41 42 run small.", "Offer 42.5 when 42 is sold out.", "Say 42 if their foot is 27 cm."):
            with self.subTest(text=text):
                self.assertNotIn("amount", groups(text))


if __name__ == "__main__":
    unittest.main()
