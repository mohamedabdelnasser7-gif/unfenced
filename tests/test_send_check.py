import unittest
from decimal import Decimal
from unittest import mock

from sales.loop import LIMIT_LINE, MODEL_DOWN, PHOTO_NOT_OPENED, VOICE_NOT_HEARD
from kit.send_check import amounts_in, check, detect_script, prices_in, size_number_amounts, stock_counts
from kit.tools import store
from tests.fake_model import clean_env
from kit import offers

AR = "عندكم جزم مقاس ٤٣؟"
FRANCO = "3ndko gezam size 43?"
EN = "Do you have football boots in size 43?"


class SendCheck(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.amounts = store.price_points()
        self.vocab = store.vocabulary()

    def ok(self, reply, customer, amounts=None):
        return check(reply, customer, self.amounts if amounts is None else amounts, self.vocab)

    # script match

    def test_detect(self):
        self.assertEqual(detect_script(AR), "arabic")
        self.assertEqual(detect_script(FRANCO), "franco")
        self.assertEqual(detect_script("enta bot wala eh?"), "franco")
        self.assertEqual(detect_script(EN), "english")
        self.assertIsNone(detect_script("؟ 43"))

    def test_arabic_in_arabic_out(self):
        self.assertTrue(self.ok("أيوه عندنا مقاس 43، الجزمة بـ 16500 جنيه.", AR)[0])
        self.assertTrue(self.ok("عندنا Nike Phantom 6 Elite مقاس 43 بـ 16500 جنيه.", AR)[0])
        passed, fb = self.ok("Yes, we have size 43 for 16500 EGP.", AR)
        self.assertFalse(passed)
        self.assertIn("Arabic letters", fb)

    def test_franco_in_latin_out(self):
        self.assertTrue(self.ok("aywa 3andena size 43, b 16500 geneh.", FRANCO)[0])
        passed, fb = self.ok("أيوه عندنا مقاس 43.", FRANCO)
        self.assertFalse(passed)
        self.assertIn("Franco", fb)

    def test_english_in_english_out(self):
        self.assertTrue(self.ok("Yes, size 43 is in stock at 16500 EGP.", EN)[0])
        self.assertFalse(self.ok("أيوه عندنا.", EN)[0])
        passed, fb = self.ok("aywa 3andena el size da.", EN)
        self.assertFalse(passed)
        self.assertIn("plain English", fb)

    # banned words and dashes

    def test_banned_words(self):
        for reply, word in (("16500 جنيه للجوز", "الجوز"), ("16500 geneh el goz", "el goz"), ("هيناسبك 43 مرتاح", "مرتاح")):
            customer = FRANCO if "geneh" in reply else AR
            passed, fb = self.ok(reply, customer)
            self.assertFalse(passed, reply)
            self.assertIn(word, fb)

    def test_sympathy_lines(self):
        passed, fb = self.ok("مقدر إنك متضايق وحقك تزعل، الاوردر في الطريق.", AR)
        self.assertFalse(passed)
        self.assertIn("sympathy", fb)
        self.assertFalse(self.ok("I understand your frustration. It ships tomorrow.", EN)[0])

    def test_dashes(self):
        for dash in ("\u2014", "\u2013"):
            passed, fb = self.ok(f"Yes {dash} size 43 is in stock.", EN)
            self.assertFalse(passed)
            self.assertIn("dashes", fb)
        self.assertTrue(self.ok("Sizes 39-42 and 43-46 are in stock.", EN)[0])

    # prices

    def test_price_must_be_in_the_data(self):
        passed, fb = self.ok("الجزمة بـ 349 جنيه.", AR)
        self.assertFalse(passed)
        self.assertIn("349", fb)
        for good in ("الجزمة بـ 16500 جنيه.", "الجزمة بـ ١٦٥٠٠ جنيه.", "الشحن 60 جنيه للقاهرة."):
            self.assertTrue(self.ok(good, AR)[0], good)
        self.assertTrue(self.ok("It is EGP 16500, delivery 85 EGP.", EN)[0])
        self.assertTrue(self.ok("Delivery takes 2 to 4 days, exchanges within 14 days.", EN)[0])

    def test_totals_pass_only_from_tool_results(self):
        self.assertFalse(self.ok("Your total is 16,560 EGP.", EN)[0])
        amounts = self.amounts | amounts_in({"ok": True, "order": {"total": "16560.00"}})
        self.assertTrue(self.ok("Your total is 16,560 EGP.", EN, amounts)[0])

    def test_prices_in(self):
        self.assertEqual(prices_in("16500 جنيه و 60 جنيه شحن"), [16500, 60])
        self.assertEqual(prices_in("EGP 16,560 total, 14 days"), [16560])
        self.assertEqual(prices_in("size 43, 2 pairs"), [])

    def test_a_weight_in_grams_is_not_an_amount(self):
        # The Vapor 17 line in the store data: "150 grams of pure speed" (root's call, 31 Oct).
        for reply, customer in (("The Vapor 17 Elite is 150 grams of pure speed.", EN),
                                ("الـ Vapor 17 Elite وزنها 150 جرام بس.", AR),
                                ("el Vapor 17 Elite 150 grams bas.", FRANCO)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [])
                self.assertTrue(self.ok(reply, customer)[0], reply)
        # 4 or more digits, a phone-like run of digits, or جم (the currency) stay amounts.
        for reply, n in (("It weighs 1234 grams.", [1234]), ("Weight 100 123 4567 grams.", [100123, 4567]),
                         ("It is 123 456 grams.", [123456]), ("الجزمة بـ 150 جم", [150])):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), n)
                passed, fb = self.ok(reply, AR if "جم" in reply else EN)
                self.assertFalse(passed, reply)
                self.assertIn("not in the store or delivery data", fb)

    def test_empty_reply(self):
        self.assertFalse(self.ok("  ", EN)[0])

    # our own fixed replies pass too

    def test_fixed_replies_pass(self):
        for script, customer in (("arabic", AR), ("franco", FRANCO), ("english", EN)):
            self.assertTrue(self.ok(PHOTO_NOT_OPENED[script], customer)[0], script)
            self.assertTrue(self.ok(VOICE_NOT_HEARD[script], customer)[0], script)
            self.assertTrue(self.ok(LIMIT_LINE[script], customer)[0], script)
            self.assertTrue(self.ok(MODEL_DOWN[script], customer)[0], script)

    # Mohamed's calls, 28 Oct

    def test_no_emoji(self):
        passed, fb = self.ok("Yes, size 43 is in stock " + chr(0x1F44D), EN)
        self.assertFalse(passed)
        self.assertIn("emoji", fb)
        self.assertFalse(self.ok("أيوه موجود " + chr(0x2764) + chr(0xFE0F), AR)[0])

    def test_no_markdown_bold(self):
        passed, fb = self.ok("The **Elite** boots are 16500 EGP.", EN)
        self.assertFalse(passed)
        self.assertIn("markdown", fb)

    def test_spaced_hyphen_used_as_a_dash(self):
        passed, fb = self.ok("Yes - size 43 is in stock.", EN)
        self.assertFalse(passed)
        self.assertIn("hyphen", fb)
        self.assertFalse(self.ok("الجزمة - 16500 جنيه.", AR)[0])
        self.assertTrue(self.ok("Sizes 40 - 45 are in stock.", EN)[0])
        self.assertTrue(self.ok("Sizes run 39-46.", EN)[0])

    def test_no_exact_stock_count(self):
        for reply, customer in (("Only 3 left in size 43.", EN), ("We have 2 pairs left.", EN),
                                ("فاضل 2 بس من المقاس ده.", AR), ("المقاس ده 3 قطع فاضلين.", AR),
                                ("fadel 3 bs mn el size da.", FRANCO), ("stock: 4", EN)):
            passed, fb = self.ok(reply, customer)
            self.assertFalse(passed, reply)
            self.assertIn("stock count", fb)
        for reply, customer in (("Only a few left in size 43.", EN), ("فاضل كام قطعة بس من المقاس ده.", AR),
                                ("Size 43 is in stock.", EN), ("مقاس 43 متاح.", AR)):
            self.assertTrue(self.ok(reply, customer)[0], reply)
        self.assertEqual(stock_counts("Only 3 left."), ["3 left"])

    def test_amount_in_words_is_refused(self):
        for reply, customer in (("It is five hundred pounds.", EN), ("الجزمة بخمسمية جنيه.", AR)):
            passed, fb = self.ok(reply, customer)
            self.assertFalse(passed, reply)
            self.assertIn("digits", fb)

    # numbers that are not amounts

    def test_sizes_dates_orders_and_units_are_not_amounts(self):
        for reply, customer in (
                ("عندنا الـ Academy مقاس EU 39-46 بـ 7500 جنيه.", AR),
                ("Size 43 is in stock for 16500 EGP.", EN),
                ("Sizes are 42 and 43, at 16500 EGP.", EN),
                ("Your order #1234 is on its way.", EN),
                ("Order #5521 is with the courier.", EN),  # F7 (t261028j): an order number needs its #
                ("اوردر #1234 اتسلم لبوسطة من 2 ايام.", AR),
                ("It arrives on 3 November.", EN),
                ("الطلب يوصل يوم 28/10 الساعة 10:30.", AR),
                ("Delivery is 2 to 4 days.", EN),
                ("التوصيل من 2 لـ 4 أيام.", AR),
                ("Exchanges are free for 14 days.", EN),
                ("It comes in 8 sizes for 16500 EGP.", EN)):
            self.assertTrue(self.ok(reply, customer)[0], reply)

    def test_catalogue_size_strings_are_not_amounts(self):
        reply = "The one for Kids 10 is in stock."
        self.assertEqual(prices_in(reply), [10])
        self.assertEqual(prices_in(reply, sizes=("Kids 10",)), [])
        self.assertTrue(check(reply, EN, self.amounts, self.vocab, sizes=("Kids 10",))[0])
        # The boots' bare sizes ("40"): after a weak word a size number is a size.
        reply = "The Academy boots for 40 are 7500 EGP."
        self.assertEqual(prices_in(reply), [7500, 40])
        self.assertEqual(prices_in(reply, sizes=store.size_strings()), [7500])
        self.assertTrue(check(reply, EN, self.amounts, self.vocab, sizes=store.size_strings())[0])
        # A size string with a range in brackets is masked whole, and its range counts as sizes.
        items = [{"title": "Range Boots", "variants": [{"size": "Adult (40-45)", "price": "7500"}]}]
        with mock.patch.object(store, "catalogue", return_value=items):
            sizes = store.size_strings()
        self.assertEqual(prices_in("Price for Adult (40-45): 7500 EGP."), [7500, 40])
        self.assertEqual(prices_in("Price for Adult (40-45): 7500 EGP.", sizes=sizes), [7500])
        self.assertEqual(prices_in(reply, sizes=sizes), [7500])

    # amounts from tool results

    def test_amounts_only_under_exact_keys(self):
        self.assertEqual(amounts_in({"coffee": 9999, "offer_amount": 7, "amount": 5, "cost": 3, "fees": 2}), set())
        self.assertEqual(amounts_in({"items": [{"price": "16500"}, {"fee": 60}], "subtotal": 16560, "total": "16,620.00"}),
                         {16500, 60, 16560, 16620})

    def test_strings_are_never_parsed_as_json(self):
        self.assertEqual(amounts_in({"ok": True, "text": '{"price": 5}'}), set())
        self.assertEqual(amounts_in('{"price": 5}'), set())
        self.assertEqual(amounts_in({"price": '{"price": 5}'}), set())

    def test_non_finite_amounts_are_ignored(self):
        for bad in ("inf", "nan", "1e400", float("inf"), float("nan"), 10 ** 400, True, None, [1, 2]):
            self.assertEqual(amounts_in({"price": bad}) - {1, 2}, set(), repr(bad)[:20])
        passed, _ = check("It is 16500 EGP.", EN, {16500, float("inf"), "x"}, self.vocab)
        self.assertTrue(passed)


# One test per price spelling from the round 1 proofs (reviewer p1_price.py, red team F1).
# The store has no price of 1 or 500, so every one of these must be blocked.
HOODIE_AR = "عندكم هودي اسود؟"
HOODIE_EN = "how much is the black hoodie?"
SPELLINGS = {
    "geneha": ("الهودي الاسود بـ 1 جنيها", HOODIE_AR),
    "geneha_tanween_after_alif": ("الهودي الاسود بـ 1 جنيهاً", HOODIE_AR),
    "geneha_tanween_before_alif": ("الهودي الاسود بـ 1 جنيهًا", HOODIE_AR),
    "price_word_no_currency": ("الهودي الاسود سعره 1 بس", HOODIE_AR),
    "bare_geem": ("الهودي الاسود بـ 1 ج", HOODIE_AR),
    "geem_meem": ("الهودي الاسود بـ 1 جم", HOODIE_AR),
    "eastern_digits": ("الهودي الاسود بـ ١ جنيه", HOODIE_AR),
    "is_bare_number": ("The black hoodie is 1 today.", HOODIE_EN),
    "egyptian_pounds": ("The black hoodie is 1 Egyptian pounds.", HOODIE_EN),
    "pound_sign": ("The black hoodie is £1.", HOODIE_EN),
    "costs_slash_dash": ("The black hoodie costs 1/-", HOODIE_EN),
    "price_colon": ("Price: 1", HOODIE_EN),
    "for_number": ("You can have it for 1 now.", HOODIE_EN),
    "be_bare_number": ("الكوتشي بـ 500 بس", HOODIE_AR),
    "be_eastern_geem": ("ده بـ ٥٠٠ ج", HOODIE_AR),
    "be_attached": ("ده ب500 بس", HOODIE_AR),
    "franco_b": ("el hoodie b 500 bs", "3ndko hoodie eswed?"),
    # No price word before the number, and only 1 digit, so only the currency list can catch these.
    "no_cue_geneha": ("الهودي الاسود 1 جنيها", HOODIE_AR),
    "no_cue_geneha_tanween_after_alif": ("الهودي الاسود 1 جنيهاً", HOODIE_AR),
    "no_cue_geneha_tanween_before_alif": ("الهودي الاسود 1 جنيهًا", HOODIE_AR),
    "no_cue_bare_geem": ("الهودي الاسود ١ ج", HOODIE_AR),
    "no_cue_geem_meem": ("الهودي الاسود 1 جم", HOODIE_AR),
    "no_cue_egyptian_pounds": ("Black hoodie: 1 Egyptian pounds.", HOODIE_EN),
    "no_cue_pound_sign": ("Black hoodie: £1.", HOODIE_EN),
}


class PriceSpellings(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.amounts = store.price_points()

    def blocked(self, reply, customer):
        passed, fb = check(reply, customer, self.amounts, store.vocabulary(), store.size_strings())
        self.assertFalse(passed, reply)
        self.assertIn("not in the store or delivery data", fb)


def _spelling_test(reply, customer):
    def test(self):
        self.blocked(reply, customer)
    return test


for _name, (_reply, _customer) in SPELLINGS.items():
    setattr(PriceSpellings, f"test_{_name}", _spelling_test(_reply, _customer))


# Normal replies with sizes, delivery days and order numbers, run through the check the
# way the loop runs it (store amounts, vocabulary and size strings). None names a price.
NORMAL = (
    ("is size 43 available?", "Your size is 43, and it is in stock."),
    ("when will it arrive?", "It arrives in 2 days."),
    ("where is my order?", "Order NLS0001 is on its way."),
    ("3ndko size 43?", "el size 43 mawgood"),
    ("delivery to Alexandria?", "Delivery to Alexandria is 2 to 3 days."),
    ("which sizes?", "The sizes are 42, 43 and 44, all in stock."),
    ("when does it come?", "Your order is out for delivery and arrives at 5 pm."),
    ("can I get 2?", "Yes, your order is 2 pairs in size 43."),
    ("size?", "Size 43 is only in Elite."),
    ("is 44 there?", "44 is in stock, and delivery to Giza is 2 days."),
    ("ordered on 25 October", "Your order from 25 October is on its way, it arrives in 2 days."),
    ("when?", "Delivery takes 2 to 3 working days."),
    ("do you have 43?", "Elite is available in 42 and 43."),
    ("do you have 43?", "The Elite ones are 42 and 43."),
    ("do you have 43?", "We only have 43 and 44 in Elite."),
    ("do you have 43?", "For 43 we have the Elite pair only, in stock."),
    ("do you have 43?", "We have 43 available in Elite."),
    ("el order emta yewsal?", "el order NLS0001 fel tare2 w hywsal fe 2 ayam"),
    ("el tawseel l Alex kam yom?", "el tawseel l Alex 2 l 3 ayam"),
    ("emta?", "hywsal fe 2 le 3 ayam"),
    ("3ndko 43?", "el eswed mawgood b 42 w 43 bs"),
    ("momken a3raf ma2as 44 mawgood?", "ma2as 44 mawgood, w el order hywsal fe 3 ayam"),
    ("عندكم مقاس ٤٣؟", "مقاس ٤٣ موجود"),
    ("الطلب هيوصل امتى؟", "الأوردر NLS0001 في الطريق وهيوصلك خلال يومين"),
    ("التوصيل للقاهرة بياخد قد ايه؟", "التوصيل للقاهرة من ٢ لـ ٣ أيام"),
    ("طلبي فين؟", "طلبك رقم #1042 اتشحن وهيوصل خلال ٣ أيام"),
    ("عايز اتنين", "تمام، الأوردر بتاعك ٢ قطع مقاس ٤٣"),
    ("عندكم ٤٣؟", "الأسود متاح ب ٤٢ و ٤٣"),
    # A bare number of 3 or more digits is an amount (28 Oct), but order numbers with #,
    # Egyptian phone numbers, years with a year word or month, times, percentages and
    # product codes still pass.
    ("where is my order?", "Your order #10234 is with the courier."),
    ("الاوردر فين؟", "الأوردر #1042 اتشحن وهيوصل بكرة"),
    ("el order fen?", "el order #1042 etsha7an w hywsal bokra"),
    ("what is your number?", "Call us on 01012345678."),
    ("what is your number?", "Our WhatsApp is +20 10 1234 5678."),
    ("what is your number?", "Write to 00201012345678 or +201012345678."),
    ("رقمكم كام؟", "كلمنا على ٠١٠١٢٣٤٥٦٧٨"),
    ("momken rakamko? 3ayez akalemko", "kalemna 3la 010 1234 5678"),
    ("since when?", "The shop has been open since May 2019."),
    ("is it new?", "This is the 2026 model."),
    ("موديل سنة كام؟", "ده موديل 2026"),
    ("اتعمل امتى؟", "ده اتعمل سنة ٢٠٢٤"),
    ("el model bta3 sana kam?", "el model 2026 mawgood"),
    ("when will it come?", "It arrives on Oct 30, 2026."),
    ("when do you answer?", "We answer from 10:00 to 22:00."),
    ("بتردوا امتى؟", "بنرد من الساعة ٩:٣٠ لحد ١٠:٠٠ بالليل"),
    ("are you sure?", "Yes, 100% sure."),
    ("which one?", "Code BO-2936845 is in stock."),
    ("how much?", "The Elite boots, 16500."),
    ("how much?", "They are 16500.00 EGP."),
)

# Mohamed's call, 28 Oct: a standalone number of 3 or more digits is an amount, with or
# without a currency or price word, and a unit after it does not change that.
BARE_BLOCKED = (
    ("how much?", "Hoodie: 500."),
    ("بكام؟", "الهودي ٥٠٠ بس"),
    ("el hoodie b kam ya basha?", "el hoodie 500 bas"),
    ("how much?", "The black boots, 500."),
    ("how much?", "Black boots 500 only today"),
    ("el gazma b kam ya basha?", "el gazma 500 bs ya basha"),
    ("بكام؟", "الكوتشي 500 بس"),
    ("بكام؟", "ده ٥٠٠ بس"),
    ("delivery?", "Shipping 500 le 2 days."),
    ("el tawseel b kam ya basha?", "el tawseel 500 le 3 ayam"),
    ("how long?", "You pay for 500 working days."),
    ("how long?", "It is 800 business days."),
    ("how much?", "Hoodie: 1,500."),
    ("how much?", "Boots 16500-1600."),
    ("size 43?", "Size 43, 500."),
    ("how much?", "It is 2000."),
    # A 4 digit number from 1900 to 2099 is a year only with a year word or a month next
    # to it, or inside a date (Mohamed, 28 Oct). Anything else is an amount.
    ("how much?", "Hoodie: 1999."),
    ("since when?", "The shop has been open since 2019."),
    ("is it new?", "Yes, the 2026 collection is in stock."),
)

# Still blocked: a price word in the sentence keeps a size number an amount, and the
# store's sizes run 39 to 46, so 1, 45 after a price word and 500 are all amounts.
STILL_BLOCKED = (
    ("delivery?", "Delivery to Giza is 45."),
    ("delivery?", "Shipping to Aswan takes longer and is 45."),
    ("delivery?", "It is 45 EGP."),
    ("price?", "It is 1 today."),
    ("el tawseel?", "el tawseel b 45"),
    ("el tawseel?", "el tawseel 45 le"),
    ("التوصيل؟", "التوصيل ب ٤٥"),
    ("بكام؟", "سعره ٤٥"),
)


class NormalReplies(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.args = (store.price_points(), store.vocabulary(), store.size_strings())

    def test_normal_replies_are_not_blocked(self):
        for customer, reply in NORMAL:
            with self.subTest(reply=reply):
                self.assertEqual(check(reply, customer, *self.args), (True, ""))

    def test_price_words_still_count_size_numbers(self):
        for customer, reply in STILL_BLOCKED:
            with self.subTest(reply=reply):
                passed, fb = check(reply, customer, *self.args)
                self.assertFalse(passed)
                self.assertIn("not in the store or delivery data", fb)

    def test_a_bare_size_after_a_price_word_is_an_amount(self):
        # The boots' sizes are bare numbers ("43"). Masked whole, they hid an amount after a price
        # word ("سعره 43") and a date's day or a time's minutes ("Oct 30, 2026", "10:30"), so a
        # bare size is read only by the size number rules: a size after a weak word, else an amount.
        self.assertIn("43", store.size_strings())
        for customer, reply in (("بكام؟", "سعره 43"), ("delivery?", "Delivery to Cairo is 40."),
                                ("el sha7n?", "el sha7n b 41"), ("shipping?", "Shipping:\nonly 43.")):
            with self.subTest(reply=reply):
                passed, fb = check(reply, customer, *self.args)
                self.assertFalse(passed)
                self.assertIn("not in the store or delivery data", fb)
        for customer, reply in (("do you have 43?", "Elite is available in 43."),
                                ("when?", "It arrives on Oct 30, 2026."), ("when?", "The courier comes at 10:30."),
                                ("3ndko 43?", "aywa, mawgood b 43")):
            with self.subTest(reply=reply):
                self.assertEqual(check(reply, customer, *self.args), (True, ""))
        self.assertEqual(prices_in("سعره 43", sizes=("43",)), [43])
        self.assertEqual(prices_in("Elite is available in 43.", sizes=("43",)), [])

    def test_a_count_that_is_not_a_size_is_still_refused(self):
        passed, fb = check("Only 3 left in 43.", "do you have 43?", *self.args)
        self.assertFalse(passed)
        self.assertIn("exact stock count", fb)

    def test_bare_numbers_of_three_digits_are_amounts(self):
        for customer, reply in BARE_BLOCKED:
            with self.subTest(reply=reply):
                passed, fb = check(reply, customer, *self.args)
                self.assertFalse(passed)
                self.assertIn("not in the store or delivery data", fb)
        self.assertEqual(len(NORMAL), 48)  # the 28 from round 2, plus 20 for the bare number and year rules


class NumbersAsWritten(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_emphasis_marks_and_invisible_characters_do_not_hide_an_amount(self):
        # Red team round 3: WhatsApp shows _500_ as an italic 500, and a zero width space splits 500.
        for customer, reply in (
                (EN, "The price is _500_ EGP."), (EN, "The black boots, ~500~."), (EN, "It is `500` EGP."),
                ("بكام الجزمة؟", "الجزمة _500_ جنيه"), ("bkam el gazma?", "el sha7n _70_ gneh"),
                (EN, "Black boots 5\u200b00."), ("بكام الكوتشي؟", "الكوتشي ٥\u200d٠٠")):
            with self.subTest(reply=reply):
                passed, fb = check(reply, customer, store.price_points())
                self.assertFalse(passed)
                self.assertIn("not in the store or delivery data", fb)
        self.assertTrue(check("The Academy boots are _7500 EGP_.", EN, store.price_points())[0])
        self.assertFalse(check("el gazma b meteen geneh", "bkam el gazma?", store.price_points())[0])

    def test_decimals_count_as_written(self):
        self.assertEqual(prices_in("It is 7500.99 EGP."), [Decimal("7500.99")])
        self.assertEqual(prices_in("الجزمة ٧٥٠٠٫٩٩ جنيه"), [Decimal("7500.99")])
        self.assertFalse(check("It is 7500.99 EGP.", EN, {7500, 16500})[0])
        self.assertFalse(check("The price is 7500.99", EN, {7500})[0])
        self.assertTrue(check("It is 16500.00 EGP.", EN, {16500})[0])
        self.assertTrue(check("It is 16500.50 EGP.", EN, {"16500.50"})[0])
        self.assertFalse(check("It is 16500 EGP.", EN, {"16500.50"})[0])
        self.assertEqual(amounts_in({"price": "16500.50", "fee": 60.0}), {Decimal("16500.5"), 60})

    def test_store_prices_keep_their_fractions(self):
        items = [{"title": "T", "variants": [{"size": "43", "price": "16500.50"}, {"size": "44", "price": "16500.00"}]}]
        with mock.patch.object(store, "catalogue", return_value=items):
            points = store.price_points()
        self.assertEqual(points, {Decimal("16500.5"), 16500, 60, 85})  # 60 and 85: the demo delivery fees

    def test_amounts_with_k_are_refused(self):
        for reply in ("It costs 1k EGP.", "Only 1.5k.", "EGP 2k", "The price is 1k"):
            with self.subTest(reply=reply):
                passed, fb = check(reply, EN, store.price_points())
                self.assertFalse(passed)
                self.assertIn("digits", fb)
        self.assertTrue(check("We have 1k followers on Instagram.", EN, store.price_points())[0])

    def test_a_size_string_never_hides_part_of_a_bigger_number(self):
        self.assertEqual(prices_in("The hoodie is 430.", sizes=("43",)), [430])
        self.assertEqual(prices_in("Hoodie: 1430.", sizes=("43",)), [1430])
        self.assertEqual(prices_in("Size 43 is in stock.", sizes=("43",)), [])

    def test_a_size_list_goes_on_only_with_small_numbers(self):
        self.assertEqual(prices_in("Sizes 42, 43 and 44 are in stock."), [])
        self.assertEqual(prices_in("Size 43, 500."), [500])

    def test_phones_codes_and_years_with_a_year_word_are_not_amounts(self):
        for reply in ("01012345678", "+20 10 1234 5678", "00201012345678", "201012345678", "+20 2 2345 6789",
                      "BO-2936845", "NLS0001", "100%", "١٠٠٪", "model 2019", "the 2019 model", "Model: 2026",
                      "سنة ٢٠١٩", "موديل 2026", "el model 2026", "May 2019", "30 Oct 2026", "Oct 30, 2026",
                      "٢٨ أكتوبر ٢٠٢٦", "28/10/2026", "2026-10-28", "2026/10/28"):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [])
        for reply, n in (("01012345", 1012345), ("1999.5", Decimal("1999.5")), ("2,019", 2019), ("2100", 2100),
                         ("since 2019", 2019), ("Hoodie: 1999.", 1999), ("the 2026 collection", 2026),
                         ("1999 years", 1999), ("Price is 1999, model 2026.", 1999)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])

    def test_size_numbers_that_are_also_prices(self):
        self.assertEqual(size_number_amounts({45, 16500, "60"}, ("Adult (40-45)", "Kids 60")), [45, 60])
        self.assertEqual(size_number_amounts({43, 16500, "60"}, ("43", "44")), [43])
        self.assertEqual(size_number_amounts(store.price_points(), store.size_strings()), [])


# Round 3 review (R3-1 to R3-5, false blocks) and red team (R3-F2 to R3-F4), 28 Oct.
FR = "3ndko gezam? bkam?"


class Round3(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.args = (store.price_points(), store.vocabulary(), store.size_strings())

    def refused(self, reply, customer, words):
        with self.subTest(reply=reply):
            passed, fb = check(reply, customer, *self.args)
            self.assertFalse(passed)
            self.assertIn(words, fb)

    def passes(self, reply, customer):
        with self.subTest(reply=reply):
            self.assertEqual(check(reply, customer, *self.args), (True, ""))

    def test_an_amount_in_words_after_a_price_word_or_be_is_refused(self):
        # R3-1 and R3-F3: no currency word after it, so only the words rule sees these.
        for reply, customer in (
                ("ده بألف", AR), ("الكوتشي بألفين", AR), ("سعره ألف", AR), ("الجزمة بخمسمية", AR),
                ("The price is one thousand.", EN), ("It costs five hundred.", EN), ("el se3r alf", FR),
                ("الهودي بألف بس", AR), ("الجزمة بميتين", AR), ("el gazma b meteen bs", FR),
                ("The boots are two hundred.", EN), ("el hoodie b alf", FR), ("nos alf gineh", FR),
                ("الجزمة بتلتمية", AR), ("el gazma b khomsomeya", FR), ("التوصيل بسبعين", AR),
                ("الجزمة بسبعين", AR), ("الجزمة ب سبعين", AR)):
            self.refused(reply, customer, "digits")

    def test_digits_then_the_word_for_thousand_are_refused(self):
        for reply, customer in (("الهودي 1.5 ألف", AR), ("الهودي ١٫٥ الف", AR), ("The price is 1 thousand.", EN),
                                ("It is 1 thousand EGP.", EN)):
            self.refused(reply, customer, "digits")

    def test_number_words_that_are_not_amounts_pass(self):
        for reply, customer in (
                ("ألف شكر", AR), ("ألف سلامة عليك", AR), ("إن شاء الله تكون بألف خير", AR), ("اغسله بمية ساقعة", AR),
                ("Delivery is for two days.", EN), ("It comes in two sizes.", EN), ("It is available in two sizes.", EN),
                ("Shipping takes two to three working days.", EN), ("التوصيل من تلاتة لخمسة أيام", AR),
                ("You can exchange it for another one in size 44.", EN), ("تقدر تبدله بواحد تاني مقاس 44", AR),
                ("Five hundred customers bought these this week.", EN)):
            self.passes(reply, customer)

    def test_short_fractions_and_dotted_dates_are_not_bare_amounts(self):
        for reply, customer in (("The courier comes between 10.30 and 12.30.", EN), ("It reaches you on 28.10.", EN),
                                ("هيوصلك يوم 28.10", AR)):
            self.passes(reply, customer)
        for reply, customer in (("Black boots 1.500", EN), ("الجزمة ١٫٥٠٠", AR), ("It is 12,3456.", EN),
                                ("Black boots 500.0.0", EN)):
            self.refused(reply, customer, "not in the store or delivery data")

    def test_a_price_word_before_an_order_number_keeps_the_amount(self):
        # R3-2, and the threshold in R3-F4.
        for reply, customer in (("اجمالي الطلب 1500", AR), ("حساب الطلب 1500", AR), ("Total for your order: 1500.", EN),
                                ("السعر رقم 500", AR), ("Free shipping on orders 500 and above.", EN)):
            self.refused(reply, customer, "not in the store or delivery data")
        # Red team t261028j F7: an order word with no # masks nothing, so "Your order 1500" is an amount.
        self.refused("Your order 1500 is ready.", EN, "not in the store or delivery data")
        self.passes("Your order #1500 is ready.", EN)
        self.passes("Your total for order #1042 is 16500 EGP.", EN)
        self.assertEqual(prices_in("Your order 1500 is ready."), [1500])

    def test_every_digit_counts_and_a_decimal_comma_is_a_point(self):
        # R3-3 and R3-F4: dot thousands, decimal commas, letters after the number, item-price lists.
        for reply, n in (("Black boots 1.500", Decimal("1.5")), ("الجزمة ١٫٥٠٠", Decimal("1.5")),
                         ("500,50", Decimal("500.5")), ("Black boots 7500,99.", Decimal("7500.99")),
                         ("The price is 7500,99", Decimal("7500.99")), ("الكوتشي ٥٠٠٬٠٠", 500), ("12,3456", 3456),
                         ("el gazma 500bs", 500), ("Black boots 500.0.0", 500)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])
        self.assertEqual(prices_in("Black boots-500, white boots-550."), [500, 550])
        for reply, customer in (("Black boots 1.500", EN), ("Black boots 7500,99.", EN), ("el gazma 500bs", FR)):
            self.refused(reply, customer, "not in the store or delivery data")
        self.passes("The Academy boots are 7500,00 EGP.", EN)
        for reply in ("NLS0001", "BO-2936845", "It arrives on 28.10.2026."):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [])

    def test_a_number_of_thousands_of_digits_never_raises(self):
        # R3-4: Python refuses to turn an int of more than 4300 digits into text.
        huge = "9" * 5000
        passed, fb = check("Hoodie: " + huge, EN, *self.args)
        self.assertFalse(passed)
        self.assertIn("9" * 20 + "...", fb)
        self.assertLess(len(fb), 1000)
        self.assertEqual(prices_in(huge), [Decimal(huge)])
        self.assertEqual(stock_counts(huge + " left"), [huge + " left"])

    def test_a_fee_after_a_city_or_before_a_time_is_read(self):
        # R3-F2: a fee table, a fee then a time, and Franco spellings of جنيه.
        for reply, ns in (("Cairo 70, Alex 90, other cities 95.", [70, 90, 95]),
                          ("القاهرة 70 والاسكندرية 90 وباقي المحافظات 95", [70, 90, 95]),
                          ("القاهرة 70 والاسكندرية 90", [70, 90]), ("cairo 70, alex 90, ba2i el mo7afzat 95", [70, 90, 95]),
                          ("Shipping 70 to 3 days.", [70]), ("el sha7n 70 le 3 ayam", [70]),
                          ("el gazma 70 gineh", [70]), ("el gazma 70 gineeh", [70]), ("el gazma 70 geneeh", [70]),
                          ("el gazma 70 ginee", [70]), ("E£70", [70])):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), ns)
        for reply, customer in (("Cairo 70, Alex 90, other cities 95.", EN), ("القاهرة 70 والاسكندرية 90", AR),
                                ("Shipping 70 to 3 days.", EN), ("el sha7n 70 le 3 ayam", FR),
                                ("Cairo 70 gineh, Alex 85 gineh.", EN)):
            self.refused(reply, customer, "not in the store or delivery data")
        for reply, customer in (("Cairo 60, Alex 85.", EN), ("القاهرة 60 والاسكندرية 85", AR),
                                ("Cairo 2 days, Alex 3 days.", EN), ("Delivery to Cairo 2 to 3 days.", EN)):
            self.passes(reply, customer)

    def test_franco_le_before_a_small_number_and_landlines_are_not_amounts(self):
        # False blocks from the round 3 review.
        for reply, customer in (("el ma2as mn 42 le 45.", FR), ("mawgod mn 42 le 45.", FR), ("el academy ma2as 39 le 46.", FR),
                                ("el academy mn 39 le 46.", FR), ("momken t8ayar le 44.", FR),
                                ("Call us on 02 2345 6789.", EN), ("Call us on 0223456789.", EN),
                                ("Our Alex office is on 03 4567890.", EN), ("كلمنا على ٠٢٢٣٤٥٦٧٨٩", AR),
                                ("Delivery on 28.10.2026.", EN)):
            self.passes(reply, customer)
        # Upper case LE stays the currency.
        self.refused("Black boots LE 70", EN, "not in the store or delivery data")

    def test_round3_review_survivors(self):
        # R3-5: each mutant that survived the reviewer's sweep.
        self.assertEqual(prices_in("model 1500"), [1500])        # year-any-4-digits
        self.assertEqual(prices_in("el model bta3 sana 2024"), [])  # year-sana-off
        for reply, n in (("1012345678", 1012345678), ("51012345678", 51012345678)):  # phone-prefix-any
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])


class OrderSummary(unittest.TestCase):
    """Day 3: the order summary shows the address, the phone and the draft's name."""
    setUp, refused, passes = Round3.setUp, Round3.refused, Round3.passes

    def test_address_numbers_are_not_amounts(self):
        for reply in ("عمارة 125، الدور 3، شقة 12", "Building 125, Flat 12", "3emara 125", "el 3emara 125 el dor 3",
                      "Bldg. no. 125", "بالعمارة 125", "للعمارة: 125", "Apt #125", "St. 125"):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [])
        self.passes("العنوان: الدقي، عمارة 125، الدور 3، شقة 12. سعر الجزمة 16500 جنيه.", AR)
        self.passes("Your address is Building 125, Flat 12. The boots are 16500 EGP.", EN)
        # Review t261028j 4: after a price word in the same sentence, an address number is an amount.
        self.refused("Delivery to Building 125, Flat 12. The boots are 16500 EGP.", EN, "125")

    def test_an_address_word_never_hides_a_price(self):
        # A currency word is read first. Words that also sit before prices (a piece, a shop, a zone)
        # are not address words, and a number glued to a word before it (1st) is not after one.
        for reply, n in (("عمارة 125 جنيه", 125), ("سعر القطعة 16500", 16500), ("سعرها في المحل 16500", 16500),
                         ("Price per unit 16500", 16500), ("Delivery to your zone: 70", 70), ("المنطقة 150", 150),
                         ("1st 500", 500), ("عمارة 1,500", 1500)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])
        self.refused("عمارة 125 جنيه.", AR, "not in the store or delivery data")

    def test_a_draft_name_after_a_price_word_is_masked(self):
        self.assertEqual(prices_in("Total for order #D1958 is 16500 EGP."), [16500])
        self.assertEqual(prices_in("Total: # D12"), [])
        self.passes("Your total for draft #D1958 is 16500 EGP.", EN)
        # The draft's name is not a Franco word, but other Franco next to it still is.
        self.passes("Your order #D12 is received. The total is 16500 EGP.", EN)
        self.refused("Order #D12: 3ndna el gazma.", EN, "not Franco")

    def test_a_number_with_a_plus_and_eight_or_more_digits_is_a_phone(self):
        for reply in ("+44 7700 900123", "+447700900123", "+1 202 555 0143", "Phone: +971501234567"):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [])
        for reply, n in (("+1500", 1500), ("Total +1500", 1500), ("1+1500", 1500)):
            with self.subTest(reply=reply):
                self.assertEqual(prices_in(reply), [n])


def setUpModule():
    """These tests read the zone fees (60, 85) as they were before decision 105: the store with no offers.
    The offers' own paths are in tests/test_offers.py and tests/test_offers_paths.py."""
    global _OFFERS_TOKEN
    _OFFERS_TOKEN = offers.OFFERS.set(offers.EMPTY)


def tearDownModule():
    offers.OFFERS.reset(_OFFERS_TOKEN)


if __name__ == "__main__":
    unittest.main()
