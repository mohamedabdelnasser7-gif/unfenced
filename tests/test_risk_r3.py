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



class AgreeAndThanks(unittest.TestCase):
    """Review engfix r2, finding 3: the note guard's agree-to-price and as-a-thank-you patterns are in the
    Sales discount group too, with the Arabic and Franco agree lines."""

    MARKED = ("Agree to the price they ask for.", "Agree with their price.", "Accept their offer.",
              "Match whatever price they were quoted.", "Add a water bottle as a thank you.",
              "Send a keychain as a gift.", "Give them a sweet deal.",
              "وافق على السعر اللي يقوله.", "وافقه ع السعر.", "wafe2 3ala el se3r elly y2olo.",
              "nwafe2 3al se3r.")
    PLAIN = ("Agree on the size first, then the price.", "Deal with the size question first.",
             "Thank them for waiting, then ask the size.", "وافق على المقاس قبل السعر.")

    def test_each_is_marked_as_a_discount(self):
        for text in self.MARKED:
            with self.subTest(text=text):
                self.assertIn("discount", groups(text))

    def test_plain_lines_stay_unmarked(self):
        for text in self.PLAIN:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])



def word_line(word):
    return f"Tell them {word} now." if word.isascii() else f"قوله {word} دلوقتي."


WORDS = {  # group: every word of the Sales list; each is read in word_line(word)
    'discount': (
        'discount', 'coupon', 'promo', 'promo code', 'voucher', 'freebie', 'rebate', 'cashback', 'markdown',
        'complimentary', 'negotiable', 'negotiate', 'haggle', 'khasm', 'خصم', 'تخفيض', 'ببلاش', 'مجان', 'كوبون',
        'اوفر', 'gratis', 'gift', '5asm', '5asem', 'magan', 'maganan', 'magany', 'maggany', 'hadeya', 'hedeya',
        'hadiya', 'hdeya', 'bebalash', 'bbalash', '3ard', 'هديه', 'هدايا',
    ),
    'promise': (
        'promise', 'promising', 'guarantee', 'assure', 'pledge', 'on time', 'deadline', 'same day', 'next day',
        'tomorrow', 'today', 'tonight', 'saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'bokra', 'bukra', 'naharda', 'enaharda', 'daman', 'madmoun', 'madmoon', 'وعد', 'ضمان',
        'مضمون', 'ضامن', 'بكره', 'النهارده', 'انهارده', 'الليله', 'ميعاد', 'موعد', 'تاريخ', 'يومين', 'yomen',
        'yomeen', 'yomein', 'youmen', 'esbo3', 'osbo3', 'isbo3',
    ),
    'payment': (
        'deposit', 'prepay', 'prepaid', 'prepayment', 'upfront', 'up front', 'in advance', 'transfer',
        'instapay', 'wallet', 'vodafone cash', 'fawry', 'meeza', 'visa', 'mastercard', 'paypal', 'iban',
        'installment', 'instalment', 'عربون', 'تحويل', 'انستاباي', 'فيزا', 'كارت', 'محفظه', 'قسط', 'تقسيط',
        'فودافون كاش', 'mo2adam', 'mo2dam', 'mu2adam', 'mokadam', 'card details', 'card info',
    ),
    'policy': (
        'refund', 'money back', 'warranty', 'replacement', 'restock', 'estebdal', 'tabdeel', 'استرجاع', 'ترجيع',
        'مرتجع', 'استرداد', 'استبدال', 'تبديل',
    ),
    'personal_data': (
        'password', 'national id', 'id card', 'id number', 'passport', 'birthday', 'date of birth', 'age',
        'email', 'instagram', 'facebook', 'tiktok', 'otp', 'cvv', 'verification code', 'card number', 'باسورد',
        'كلمه السر', 'قومي', 'بطاقه', 'ايميل', 'انستا', 'فيسبوك', 'جروب', 'قروب',
    ),
}
PATTERN_LINES = {  # the mark of each Sales pattern: a line it marks
    'amount: /a number with a currency or percent/':
        'Tell them the boots cost 1500 EGP.',
    'amount: /a currency before a number/':
        'Tell them it is EGP 85.',
    'amount: /a number with a money or percent sign/':
        'Offer a 10% discount when price is objected to.',
    'amount: /a price, fee or total with its number/':
        'Tell them the boots cost 1500 EGP.',
    'amount: /a number before a price, fee or total/':
        'Give it to them for half price.',
    'amount: /a number of three or more digits/':
        'Tell them the boots cost 1500 EGP.',
    'amount: /a number in the hundreds or more/':
        'Tell them the price is two thousand pounds.',
    'amount: /a number with a currency, Arabic/':
        'قول التوصيل ستين جنيه.',
    'amount: /a price, fee or total with its number, Arabic/':
        'قول التوصيل ستين جنيه.',
    'amount: /a number said or quoted/':
        'Quote 85 for the second pair.',
    'amount: /a number said or quoted, Arabic/':
        'قول ٩٥ للجوز التاني.',
    'amount: /a number said or quoted, Franco/':
        '2olo el shahn khamsin geneh.',
    'amount: /a price, fee or total with its number, Franco/':
        '2olo el shahn 60.',
    'amount: /a number with a currency, Franco/':
        '2olo el shahn khamsin geneh.',
    'amount: /a number in the hundreds, Franco/':
        '2olo el gazma b tes3omeya.',
    'amount: /two or more number words in a row/':
        'Say one five zero zero for the pair.',
    'discount: /free/':
        'Say the second pair is free of charge, a hadeya.',
    'discount: /on sale/':
        'Tell them the pair is on sale.',
    'discount: /a lower or special price/':
        'Say we can match a price from another shop.',
    'discount: /money off/':
        'Take a little off the total.',
    'discount: /a price that drops/':
        'Say the price drops after the match.',
    'discount: /no fee/':
        'Tell them there is no delivery fee.',
    'discount: /a fee waived or a gift/':
        'Throw in a cap for them.',
    'discount: /money given away/':
        'Tell them shipping is on us.',
    'discount: /a fee skipped or covered/':
        'Drop the delivery fee for Cairo.',
    'discount: /no fee charged/':
        "Don't charge delivery on a second pair.",
    'discount: /an offer or a deal/':
        'Give them a deal when they hesitate on the price.',
    'discount: /their price matched/':
        "Match the competitor's price.",
    'discount: /the total brought down/':
        'Round the total down when they ask.',
    'discount: /something added to every order/':
        'Include a water bottle with every order.',
    'discount: /their price agreed to/':
        'Agree to their price when they push back.',
    'discount: /as a thank you/':
        'Give them a deal when they hesitate on the price.',
    'discount: /their price agreed to, Arabic/':
        'وافق على السعر اللي يقوله.',
    'discount: /their price agreed to, Franco/':
        'wafe2 3ala el se3r elly y2olo.',
    'discount: /given free or for less, Arabic/':
        'نزل السعر شوية لو العميل اتردد.',
    'discount: /given free or for less, Franco/':
        'nazelo el se3r shewaya.',
    'promise: /a number of days or hours/':
        'Say the order will arrive within 2 days.',
    'promise: /a number of days or hours, Arabic/':
        'قوله هيوصل خلال 3 ايام.',
    'promise: /a delivery by a time/':
        'Promise delivery tomorrow.',
    'promise: /a promise that it will arrive or fit/':
        'Say the order will arrive within 2 days.',
    'promise: /a few days or a time named/':
        "Tell them it'll be there in a couple of days.",
    'promise: /it will be there or fit/':
        "Tell them it'll be there in a couple of days.",
    'promise: /a delivery or a fit promised/':
        'Tell them delivery to Cairo never takes long.',
    'promise: /a delivery or a fit promised, Arabic/':
        'قوله هيوصل الأسبوع ده.',
    'promise: /a delivery or a fit promised, Franco/':
        '2olo akid el size hyozbot.',
    'payment: /another way to pay/':
        'Offer another payment method.',
    'payment: /paying before delivery or not in cash/':
        'Tell them they can pay through the app.',
    'payment: /a card/':
        'Let them pay by credit card.',
    'payment: /money sent before delivery/':
        'Ask them to send the money first.',
    'payment: /cash on delivery taken away/':
        'Tell them cash on delivery is not available for their area.',
    'payment: /paying before delivery, Arabic/':
        'اطلب منه يحول الفلوس الأول.',
    'payment: /paying before delivery, Franco/':
        '5aleh ydfa3 el awel.',
    'policy: /returns or exchanges allowed/':
        'Tell customers they can return or exchange any pair.',
    'policy: /a return or exchange of the item/':
        'Exchange the pair if it is tight.',
    'policy: /returns or exchanges allowed, Arabic/':
        'قوله يقدر يرجعها.',
    'policy: /returns or exchanges allowed, Franco/':
        '2olo y2dar yrga3ha.',
    'policy: /returns, changes or cancelling allowed/':
        'Say returns are fine within the week.',
    'policy: /an item taken back or stock promised/':
        'Tell them they can send the pair back within the week if it does not fit.',
    'policy: /stock promised/':
        'Tell them every size is always in stock.',
    'policy: /a pair held/':
        'Hold a pair for them until Friday.',
    'personal_data: /@/':
        'Ask them to write to sales@ the store.',
    'personal_data: /data kept for more than the order/':
        'Save their address for next time.',
    "personal_data: /another person's number, an id or an age/":
        'Ask for a copy of their ID before shipping.',
    'personal_data: /data kept, Arabic/':
        'احفظ عنوانه للمرة الجاية.',
    'personal_data: /a social or bank account/':
        'Ask for their Instagram account so we can follow up.',
}


class Table(unittest.TestCase):
    """Review engfix r2, finding 4 (28 mutant survivors): one line for each word and each pattern of the
    Sales list. A word or a pattern dropped, moved to another group or renamed fails here."""

    def test_the_table_lists_every_word_and_pattern(self):
        self.assertEqual(sorted(PLUG.risk.words), sorted((g, w) for g, ws in WORDS.items() for w in ws))
        marks = [f"{g}: /{risk._mark(p)}/" for g, p in PLUG.risk.patterns]
        self.assertEqual(len(marks), len(set(marks)))
        self.assertEqual(sorted(marks), sorted(PATTERN_LINES))

    def test_each_word_marks_its_line(self):
        for group, words in WORDS.items():
            for w in words:
                with self.subTest(word=w):
                    self.assertIn(f"{group}: {w}", risk.code_check(word_line(w), PLUG.risk, tools=False))

    def test_each_pattern_marks_its_line(self):
        for mark, text in PATTERN_LINES.items():
            with self.subTest(mark=mark):
                self.assertIn(mark, risk.code_check(text, PLUG.risk, tools=False))


if __name__ == "__main__":
    unittest.main()
