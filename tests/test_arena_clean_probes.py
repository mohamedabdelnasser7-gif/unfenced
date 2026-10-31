"""Cleaning for the Arena (arena/clean.py, 2026-10-30): every probe line from the persona review
and red team round 1, the chat-level rules, a whole run on a made-up export and the gate on
card examples. Made-up text only; hidden marks are built with chr() so the file shows them."""
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from arena import cards as cards_mod
from arena import clean as cl
from arena import personas as pp
from arena.scripted import ScriptedModel
from tests import fake_recipe

STORE = "Beyond the Limits"
UNSAVED = "+20 100 777 3321"
ZWSP, ZWJ, ZWNJ, LRM, WJ, BOM = (chr(c) for c in (0x200B, 0x200D, 0x200C, 0x200E, 0x2060, 0xFEFF))
NBSP, THIN, EN_DASH = chr(0xA0), chr(0x2009), chr(0x2013)
CGJ, VS16, KEYCAP = chr(0x34F), chr(0xFE0F), chr(0x20E3)  # combining marks: grapheme joiner, emoji style, keycap


def cleaned(text, names=(), users=()):
    return cl.Cleaner(names).chat(names, users)(text)


class Check(unittest.TestCase):
    def check(self, cases, names=(), users=()):
        c = cl.Cleaner(names).chat(names, users)
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(c(text), want)


class NamesWithNoDisplayName(Check):
    """The customer is an unsaved contact: the sender shows as a number."""

    def test_cues_titles_and_greetings(self):
        self.check([
            ("اهلا ياسين مرزوق، تحت امرك", "اهلا [name]، تحت امرك"),
            ("الاسم:\nياسين مرزوق\nالموبايل: 0100 777 3321", "الاسم:\n[name]\nالموبايل: [phone]"),
            ("اسمي ياسين مرزوق الجندي", "اسمي [name]"),
            ("انا ياسين مرزوق عايز مقاس 43", "انا [name] عايز مقاس 43"),
            ("ana Yassin Marzouk 3ayez el gazma", "ana [name] 3ayez el gazma"),
            ("المستلم: ياسين مرزوق", "المستلم: [name]"),
            ("الاوردر باسم ياسين مرزوق", "الاوردر باسم [name]"),
            ("اسم صاحب الطلب: ياسين مرزوق", "اسم صاحب الطلب: [name]"),
            ("el order be esm Yassin Marzouk", "el order be esm [name]"),
            ("hi yassin, the boots are 1450", "hi [name], the boots are 1450"),
            ("ابعتها لـ كريم مرزوق", "ابعتها ل [name]"),
            ("deliver to Karim Marzouk please", "deliver to [name] please"),
            ("ابعتوا الاوردر لاخويا كريم مرزوق", "ابعتوا الاوردر لاخويا [name]"),
            ("تمام يا ياسين هنبعت على 0100 777 3321", "تمام يا [name] هنبعت على [phone]"),
        ], names=(UNSAVED, STORE))

    def test_cue_forms_with_a_name_on_no_list(self):
        self.check([
            ("الاسم - زوزو مرزوق", "الاسم - [name]"), ("الاسم/ زوزو مرزوق", "الاسم/ [name]"),
            ("الاسم | زوزو مرزوق", "الاسم | [name]"), ("name - Zorvex Tamblin", "name - [name]"),
            ("full name / zorvex tamblin", "full name / [name]"), ("ابعتها لـ زوزو", "ابعتها ل [name]"),
            ("ابعتها ل zorvex", "ابعتها ل [name]"), ("deliver to zorvex", "deliver to [name]"),
            ("ship it to Zorvex", "ship it to [name]"), ("ship it to zorvex please", "ship it to [name] please"),
            ("send them to zorvex", "send them to [name]"), ("ياعم زوزو", "ياعم [name]"), ("Thx Zorvex", "Thx [name]"),
            ("thnx Zorvex", "thnx [name]"),
        ], names=(UNSAVED, STORE))
        self.check([  # the same cues with no name after them stay
            ("send it to me please", "send it to me please"), ("deliver to the office", "deliver to the office"),
            ("ship it to my brother", "ship it to my brother"), ("ابعتها ل البيت", "ابعتها ل البيت"),
            ("thx a lot", "thx a lot"), ("name - size 42", "name - size 42"),
        ], names=(UNSAVED, STORE))

    def test_a_lower_case_name_after_an_english_title(self):
        self.check([
            ("deliver to dr zorvex", "deliver to dr [name]"), ("ship it to mr zorvex", "ship it to mr [name]"),
            ("thanks mrs tamblin", "thanks mrs [name]"), ("hi madam zorvex", "hi madam [name]"),
        ], names=(UNSAVED, STORE))
        self.check([  # the title with no name after it, and doctor, which needs a capital, stay
            ("i miss you", "i miss you"), ("the doctor told me", "the doctor told me"),
        ], names=(UNSAVED, STORE))

    def test_franco_3ali_is_high_not_a_name(self):
        self.check([("el se3r 3ali awi", "el se3r 3ali awi"), ("da 3ali shwaya", "da 3ali shwaya"),
                    ("ana 3ali", "ana [name]"), ("ana Ali", "ana [name]"), ("ali", "[name]")], names=(UNSAVED, STORE))


class NamesTypedAnotherWay(Check):
    def test_forms_of_a_display_name(self):
        for display, text, want in [
            ("Yassin Marzouk", "الاوردر باسم ياسين مرزوق", "الاوردر باسم [name]"),
            ("أحمد خالد", "انا احمد خالد", "انا [name]"),
            ("منة عادل", "انا منه عادل", "انا [name]"),
            ("عبد الرحمن سعيد", "انا عبدالرحمن سعيد", "انا [name]"),
            ("عبدالله سعيد", "انا عبد الله سعيد", "انا [name]"),
            ("منى عادل", "اسمي مُنى عَادِل", "اسمي [name]"),
            ("محمد سعيد", "انا محمّد سعيد", "انا [name]"),
            ("Mohamed Ali", "ana Mo7amed 3ali", "ana [name]"),
            ("محمد سعيد", "انا محمد\U0001F525سعيد", "انا [name]"),
            ("محمد سعيد", "انا محـــمد", "انا [name]"),
            ("محمد سعيد", "انا مح" + ZWSP + "مد سعيد", "انا [name]"),
            ("محمد سعيد", "انا مح" + CGJ + "مد سعيد", "انا [name]"),
            ("زوزو مرزوق", "انا زو" + CGJ + "زو مر" + CGJ + "زوق", "انا [name]"),
            ("زوزو مرزوق", "اسمي زو" + CGJ + "زو", "اسمي [name]"),
            ("محمد سعيد", "فمحمد هيستلم", "ف[name] هيستلم"),
            ("Mo Salah", "ابعتها لـ Mo", "ابعتها ل [name]"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(cleaned(text, (display, STORE)), want)


class Phones(Check):
    def test_every_way_of_writing_a_phone(self):
        for text in ["0100 777 3321", "0100" + ZWSP + "777" + ZWSP + "3321", "0100" + ZWJ + "7773321",
                     "0100" + ZWNJ + "7773321", "0100" + LRM + "7773321", "0100" + BOM + "7773321",
                     "0100" + WJ + "7773321", "0100_777_3321", "0100,777,3321", "0100،777،3321", "0100*777*3321",
                     "٠١٠٠" + ZWJ + "٧٧٧" + ZWJ + "٣٣٢١", "01OO7773321", "+2 0100 777 3321", "0100.777.3321",
                     "0100 777 و 3321", "0100" + NBSP + "777" + NBSP + "3321", "0100" + THIN + "777" + THIN + "3321",
                     "0100" + EN_DASH + "777" + EN_DASH + "3321", "０１００７７７３３２１", "٠١٠٠١٢٣٤٥٦٧",
                     "010 0123 4567", "0100 123 4567", "+20 100 123 4567", "00201001234567", "010-012-34567",
                     "o1oo1234567", "٠١٠-٠١٢-٣٤٥٦٧", "0100.123.4567", "010" + LRM + "01234567",
                     "010" + NBSP + "0123" + NBSP + "4567", "0100١٢٣٤٥٦٧", "0122 34 56 789", "01０01234567",
                     "۰۱۰۰۱۲۳۴۵۶۷", "𝟎𝟏𝟎𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕"]:
            with self.subTest(text=text):
                self.assertEqual(cleaned(text), "[phone]")

    def test_other_runs_of_digits(self):
        self.check([
            ("0 1 0 0 7 7 7 3 3 2 1", "[number]"), ("رقمي01007773321", "رقمي[number]"), ("0100\n7773321", "[number]"),
            ("رقمي 01001234567", "رقمي [phone]"), ("01001234567كلمني", "[phone]كلمني"),
            ("كلمني01001234567", "كلمني[number]"), ("واتس 1001234567", "واتس [number]"),
            ("phone: 2 0 1 0 0 1 2 3", "phone: [number]"), ("رقم البطاقة 4111/1111/1111/1111", "رقم البطاقة [number]"),
            ("visa 4111 1111 1111 1111", "visa [number]"), ("(010) 0123-4567", "[number]"),
            ("tel:1001234567x", "tel:[number]x"), ("الرقم القومي 29901011234567", "الرقم القومي [number]"),
            ("zip 11511", "zip [number]"), ("رقم المحفظة 01001234567", "رقم المحفظة [phone]"),
            ("tracking 123456", "tracking [number]"), ("رقم الشحنة 9876543", "رقم الشحنة [number]"),
            ("بوليصة 55512", "بوليصة [number]"), ("AWB 55512", "AWB [number]"), ("طلبي 104567", "طلبي [number]"),
        ])

    def test_any_sign_between_the_groups(self):
        for sign in (";", ":", "؛", "|", "=", "~", "+", "'", "^", "!", "؟", "#", "%", "&", ">", "\\", " ... ", " ;; ",
                     " | ", "\U0001F525", "•", "、", "°"):
            text = "رقمي 0100" + sign + "777" + sign + "3399"
            with self.subTest(text=text):
                self.assertEqual(cleaned(text), "رقمي [number]")
        keycaps = "".join(d + VS16 + KEYCAP for d in "01007773399")
        self.check([
            (keycaps, "[phone]"), ("+20;100;777;3399", "[number]"), ("0100;777;3399 جنيه", "[number] جنيه"),
            ("1;2;3;4;5;6;7", "[number]"), ("1001;234;567 جنيه", "[number] جنيه"),
            ("1450;1450;1450;1450 جنيه", "[number] جنيه"), ("+1450+90=1540 جنيه", "[number] جنيه"),
            ("رقمي 123 و 4567", "رقمي [number]"), ("02;2345;6789 جنيه", "[number] جنيه"),
            ("00;123;456;789 جنيه", "[number] جنيه"),
        ])

    def test_prices_sizes_and_times_in_store_lines_stay(self):
        self.check([(text, text) for text in (
            "1450 جنيه", "مقاس 42", "48 ساعة", "الشحن بياخد 48 ساعة", "السعر 1450 جنيه والشحن 60",
            "1450 + 90 = 1540 جنيه", "1450+90=1540 جنيه", "1450 + 90 شحن = 1540", "المقاسات 40|41|42",
            "متاح 41 و 42 و 43", "خصم 10% على 1450", "هيوصلك يوم 30/10", "EGP 1,450.00", "2x1450=2900 EGP",
        )])

    def test_a_number_after_an_account_cue(self):
        self.check([
            ("رقم الحساب 123456", "رقم الحساب [number]"), ("رقم حساب 123456", "رقم حساب [number]"),
            ("ورقم الحساب: 12345", "ورقم الحساب: [number]"), ("رقم الحساب 1234", "رقم الحساب [number]"),
            ("رقم الحساب 123456 جنيه", "رقم الحساب [number] جنيه"), ("رقم حسابي هو 98765", "رقم حسابي هو [number]"),
            ("رقم الحساب البنكي بتاعي 123456", "رقم الحساب البنكي بتاعي [number]"),
            ("الحساب البنكي 123456", "الحساب البنكي [number]"), ("الايبان 1234567890", "الايبان [number]"),
            ("رقم الاكونت 55512", "رقم الاكونت [number]"), ("رقم الكارت 4111", "رقم الكارت [number]"),
            ("IBAN EG380019000500000000263180002", "IBAN [number]"),
            ("iban: EG38 0019 0005 0000 0000 2631 8000 2", "iban: [number]"),
            ("account number 12345", "account number [number]"), ("acc no. 1234", "acc no. [number]"),
            ("A/C 1234 5678", "A/C [number]"), ("bank account # 12345", "bank account # [number]"),
            ("rakam el 7esab 123456", "rakam el 7esab [number]"), ("ra2am 7sab 1234", "ra2am 7sab [number]"),
            ("الحساب البنكي 1234", "الحساب البنكي [number]"), ("الايبان 1234", "الايبان [number]"),
            ("رقم الحساب بتاعي 1234", "رقم الحساب بتاعي [number]"),
        ])
        self.check([(text, text) for text in (  # the bill stays
            "الحساب 1450 جنيه", "الحساب 12500", "الحساب: 12500 جنيه", "اجمالي الحساب 12500", "حساب الاوردر 12500 جنيه",
            "الحساب كله 1450 جنيه", "total 12500",
        )])


class LongLines(unittest.TestCase):
    """A long word with no gap must not make a pattern quadratic (finding 9: 8 s on a 32K line)."""

    def test_a_long_line_finishes_in_time(self):
        for name, line in (("OBF_EMAIL", "a-" * 16000), ("DOTTED", "a" * 64000 + ".x")):
            with self.subTest(pattern=name):
                start = time.perf_counter()
                getattr(cl, name).sub("", line)
                self.assertLess(time.perf_counter() - start, 1.0)
        start = time.perf_counter()
        cleaned("a-" * 16000)
        self.assertLess(time.perf_counter() - start, 2.0)

    def test_the_account_and_order_rules_are_linear(self):
        for name, line in (("ACCOUNT_NUMBER", "account" + " :" * 16000),
                           ("ACCOUNT_NUMBER", "رقم الحساب" + " :" * 8000 + " x" * 8000),
                           ("ORDER_NUMBER", "order" + " #" * 16000), ("ORDER_NUMBER", "order" + " ," * 16000),
                           ("ORDER_NUMBER", "order" + " number" * 2000)):
            with self.subTest(pattern=name, line=line[:12]):
                start = time.perf_counter()
                getattr(cl, name).sub("", line)
                self.assertLess(time.perf_counter() - start, 1.0)


H_FILLER, BRAILLE = chr(0x3164), chr(0x2800)


class RoundThree(Check):
    """Round 3 review and red team: leaks, small cue gaps, and common words no longer masked."""

    def test_an_email_with_a_space_next_to_the_at(self):
        self.check([("zorvex@ gmail.com", "[email]"), ("zorvex @ gmail . com", "[email]"), ("mail zorvex@", "mail [user]"),
                    ("write to zorvex@ then call", "write to [user] then call")])

    def test_an_account_number_with_a_letter_after_it(self):
        self.check([("رقم الحساب 1234567جنيه", "رقم الحساب [number]جنيه"), ("رقم الحساب 123456جنيه", "رقم الحساب [number]جنيه"),
                    ("ac no 1234", "ac no [number]"), ("A/C no. 1234", "A/C no. [number]"),
                    ("رقم الحساب 1234abc", "رقم الحساب [number]abc"), ("ac 1234", "ac 1234")])

    def test_blanks_that_are_letters_spacing_marks_or_unassigned(self):
        for display, text, want in [
            ("محمد سعيد", "انا مح" + H_FILLER + "مد", "انا [name]"),
            ("زوزو مرزوق", "انا زو" + H_FILLER + "زو مر" + H_FILLER + "زوق", "انا [name]"),
            ("زوزو مرزوق", "انا زو" + BRAILLE + "زو", "انا [name]"),
            ("محمد سعيد", "انا مح" + chr(0xE000) + "مد", "انا [name]"),
            ("محمد سعيد", "انا مح" + chr(0x0378) + "مد", "انا [name]"),
            ("محمد سعيد", "انا مح" + chr(0x093E) + "مد", "انا [name]"),
            ("Beyond Team", "0100" + H_FILLER + "777" + H_FILLER + "3399", "[phone]"),
            ("Beyond Team", "الاسم" + chr(0xA789) + " زوزو مرزوق", "الاسم: [name]"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(cleaned(text, (display, STORE)), want)

    def test_more_name_cue_forms(self):
        self.check([
            ("اسم: زوزو مرزوق", "اسم: [name]"), ("الاسم:\n\nزوزو مرزوق", "الاسم:\n\n[name]"),
            ("المستلم\n\nزوزو مرزوق", "المستلم\n\n[name]"), ("الاسم = زوزو مرزوق", "الاسم = [name]"),
            ("الاسم .. زوزو مرزوق", "الاسم .. [name]"), ("الاسم ، زوزو مرزوق", "الاسم ، [name]"),
            ("الاسم: \U0001F464 زوزو مرزوق", "الاسم: \U0001F464 [name]"), ("Name Zorvex Tamblin", "Name [name]"),
            ("recipient zorvex tamblin", "recipient [name]"), ("Name = Zorvex Tamblin", "Name = [name]"),
            ("besm zorvex", "besm [name]"), ("b esm zorvex", "b esm [name]"), ("esm el mostalem zorvex", "esm el mostalem [name]"),
            ("deliver to: zorvex", "deliver to: [name]"), ("deliver to\nzorvex", "deliver to\n[name]"),
            ("mr زوزو", "mr [name]"), ("dr زوزو", "dr [name]"), ("mr.zorvex", "mr.[name]"), ("dr zorvex's order", "dr [name] order"),
            ("mr zorvex2", "mr [name]"), ("ياعمو زوزو", "ياعمو [name]"), ("ابعتها لزوزو", "ابعتها ل[name]"),
            ("وصلها لزوزو مرزوق", "وصلها ل[name]"),
        ], names=(UNSAVED, STORE))
        self.check([(text, text) for text in (
            "besm allah", "ابعتها لمكتبي", "ابعتها للبيت", "وصلها لعند الباب", "name - size 42", "name and address please",
            "name tag?", "اسم الموديل: Nike",
        )], names=(UNSAVED, STORE))

    def test_order_numbers_past_signs_and_longer_fillers(self):
        self.check([
            ("الاوردر اللي انا كنت عملته من يومين 1045 وصل فين", "الاوردر اللي انا كنت عملته من يومين [order] وصل فين"),
            ("my order from the other day last week 1045", "my order from the other day last week [order]"),
            ("الاوردر بتاعي من 3 ايام 1045", "الاوردر بتاعي من 3 ايام [order]"), ("الاوردر بتاعي، 1045", "الاوردر بتاعي، [order]"),
            ("my order, 1045", "my order, [order]"), ("order - 1045", "order - [order]"),
            ("الاوردر بتاعي - 1045", "الاوردر بتاعي - [order]"), ("اوردر/1045", "اوردر/[order]"),
            ("الاوردر \"1045\"", "الاوردر \"[order]\""), ("my order (from yesterday) 1045", "my order (from yesterday) [order]"),
            ("1045، ده رقم الاوردر", "[order]، ده رقم الاوردر"),
        ])
        self.check([(text, text) for text in (
            "order 2 pairs 1450", "الطلب 2 جزمة ب 1450", "الاوردر 1500 جنيه", "order from the other day for 1450",
        )])

    def test_phone_groups_split_by_more_signs_or_words(self):
        for text in ("رقمي 0100 ...... 777 ...... 3399", "رقمي 0100------777------3399",
                     "رقمي 0100\n\n\n\n\n\n777\n\n\n\n\n\n3399", "رقمي 0100 then 777 then 3399", "رقمي 0100 ثم 777 ثم 3399",
                     "رقمي 0100 و بعدين 777 و بعدين 3399", "رقمي 0100 و\n777 و\n3399", "رقمي 0100\nو\n777\nو\n3399",
                     "رقمي 0100 ، و 777 ، و 3399"):
            with self.subTest(text=text):
                self.assertEqual(cleaned(text), "رقمي [number]")

    def test_sums_with_no_currency_stay(self):
        self.check([(text, text) for text in ("1450 + 60 = 1510", "2*1450=2900", "1450 × 2 = 2900", "1450+60=1510")])
        self.check([("0100+777=3399", "[number]"), ("100+777=3399", "[number]"), ("1450 + 60 + 90", "[number]"),
                    ("+1450+60=1510", "[number]"), ("1450 + 60 = 1510 + 2222222", "[number]")])

    def test_common_words_after_a_title_or_a_delivery_cue_stay(self):
        self.check([(text, text) for text in (
            "don't miss our new collection", "i miss shopping here", "madam kindly check", "send it to work",
            "deliver to home please", "send to email", "ابعتها ل مكتبي", "hi madam ok", "miss u", "mr al",
        )], names=(UNSAVED, STORE))
        self.check([("Miss Zorvex", "Miss [name]"), ("hi madam zorvex", "hi madam [name]"),
                    ("deliver to dr zorvex", "deliver to dr [name]")], names=(UNSAVED, STORE))


class AfterRoundThreeCheck(Check):
    def test_a_name_after_an_account_cue_does_not_shield_the_number(self):
        c = cl.Cleaner((UNSAVED, STORE)).chat((UNSAVED, STORE), ())
        for text, digits in (("رقم الحساب هيثم 123456 جنيه", "123456"), ("acc israa 1234", "1234"),
                             ("IBAN هو هيثم 1234", "1234")):
            with self.subTest(text=text):
                self.assertNotIn(digits, c(text))

    def test_allah_inside_a_name_and_besm_allah(self):
        c = cl.Cleaner((UNSAVED, STORE)).chat((UNSAVED, STORE), ())
        self.assertNotIn("zorvex", c("my name is abd allah zorvex"))
        self.assertEqual(c("besm allah"), "besm allah")


DELIVERY_VERBS = "ابعتها ابعتوها ابعته ابعتوه ابعتيها وصلها وصلوها وصله وصلوه هاتها هاته سلمها سلمه سلموها سلموه".split()
NEW_STOP = ("مكتب مكتبي مكتبنا شغل شغلي بيت بيتي البيت محل المحل فرع اقرب ايميل ايميلي الايميل بوابه البواب"
            " work home house office email mail gmail inbox kindly check").split()


class RoundThreeParts(Check):
    """Mutation sweep of the round 3 rules: each case fails when one part of a rule is taken out."""

    def texts(self, rows):
        return cl.Cleaner([]).chat([]).texts([msg(t, team) for team, t in rows])

    def test_more_name_asks_open_the_window(self):
        for ask in ("اتشرف باسمك", "الاسم يافندم", "والاسم؟", "ممكن اسامي المستلمين", "el esm please", "esm?",
                    "طيب والاسم يا فندم؟"):
            with self.subTest(ask=ask):
                self.assertEqual(self.texts([(True, ask), (False, "لوكاس مارتن")])[1], "[name]")
        # three words with a name word and no ask: the store names a product
        self.assertEqual(self.texts([(True, "الموديل اسمه فانتوم"), (False, "لوكاس مارتن")])[1], "لوكاس مارتن")

    def test_short_store_lines_and_the_name_window(self):
        asked = [(True, "اسمك ايه؟"), (False, "لحظة")]
        for ack in ("IMG-20241030-WA0001.jpg (file attached)", "Beyond the Limits sent an attachment.",
                    "<تم حذف هذه الرسالة>", "<Ce message a été supprimé>"):
            with self.subTest(ack=ack):
                self.assertEqual(self.texts(asked + [(True, ack), (False, "لوكاس مارتن")])[3], "[name]")
        # four words with no question move on
        self.assertEqual(self.texts(asked + [(True, "المقاس 42 متاح بكرة"), (False, "لوكاس مارتن")])[3], "لوكاس مارتن")
        # a short line that asks the address moves on to the address
        self.assertEqual(self.texts(asked + [(True, "ابعت العنوان"), (False, "شارع 9")])[3], "[address]")
        # a short line that asks only the name again: every answer up to the next store line is the name
        got = self.texts([(True, "ابعتلي الاسم والعنوان"), (True, "الاسم"), (False, "لوكاس مارتن"), (False, "شارع 9")])
        self.assertEqual(got[2:], ["[name]", "[name]"])

    def test_emails_payment_ids_and_marks(self):
        self.check([("zorvex @gmail.com", "[email]"), ("pay to zorvex@instapay.", "pay to [user]."),
                    ("zorvex@instapay.", "[user]."), ("my mail is zorvex@gmail.", "my mail is [user]."), ("zorvex@.", "[user]."),
                    ("pay to zorvex@@instapay", "pay to [user]"), ("zorvex@@gmail.com", "[user]"),
                    ("zorvex@@ ok", "[user] ok")])
        for text in ("انا مح" + chr(0x115F) + "مد", "انا مح" + chr(0x301) + "مد"):  # Hangul choseong filler, combining acute
            with self.subTest(text=text):
                self.assertEqual(cleaned(text, ("محمد سعيد", STORE)), "انا [name]")

    def test_more_cue_title_and_delivery_forms(self):
        self.check([("الاسم: - \U0001F464 زوزو مرزوق", "الاسم: - \U0001F464 [name]"), ("ms zorvex", "ms [name]"), ("mister zorvex", "mister [name]"),
                    ("madame zorvex", "madame [name]"), ("dr zorvex’s order", "dr [name] order"), ("وصلها؟ لقيتها", "وصلها؟ لقيتها")]
                   + [(v + " لزوزو", v + " ل[name]") for v in DELIVERY_VERBS], names=(UNSAVED, STORE))
        self.check([(text, text) for text in ("the product name Mercurial Vapor", "what is the brand name Nike Air")])

    def test_orders_sums_and_phones(self):
        self.check([("my order that i made from the shop last week 1045", "my order that i made from the shop last week [order]"),
                    ("الاوردر بتاعي، من يومين، 1045", "الاوردر بتاعي، من يومين، [order]"),
                    ("رقمي 0100 بعدين 777 بعدين 3399", "رقمي [number]"), ("رقمي 0100 Then 777 Then 3399", "رقمي [number]"),
                    ("1234=5678", "[number]"), ("1450 - 60 = 1390", "[number]")])
        self.check([(text, text) for text in ("my order from yesterday,for 1450", "الطلب ده،ب 1450")])

    def test_the_new_stop_words(self):
        self.check([(text, text) for text in (
            "deliver to house", "deliver to office", "send to mail", "send to gmail", "send to inbox", "madam check the size",
            "ابعتها ل مكتب", "ابعتها ل مكتبنا", "ابعتها ل شغل", "ابعتها ل شغلي", "ابعتها ل محل", "ابعتها ل فرع", "ابعتها ل اقرب",
            "ابعتها ل ايميل", "ابعتها ل بوابه")] + [("اسمي زوزو البواب", "اسمي [name] البواب")], names=(UNSAVED, STORE))
        for word in NEW_STOP:
            with self.subTest(word=word):
                self.assertTrue(cl.is_stop(word))


class MoreForms(Check):
    def test_more_separators_and_a_longer_filler(self):
        self.check([
            ("الاسم " + EN_DASH + " زوزو مرزوق", "الاسم " + EN_DASH + " [name]"),
            ("recipient - zorvex tamblin", "recipient - [name]"), ("recipient | Zorvex Tamblin", "recipient | [name]"),
            ("الاوردر اللي كنت عملته من يومين 1045", "الاوردر اللي كنت عملته من يومين [order]"),
        ], names=(UNSAVED, STORE))

    def test_short_words_and_forms_of_address_after_a_cue_stay(self):
        self.check([(text, text) for text in (
            "thx kteer", "tnx bgd", "deliver to boss", "ship it to sir", "ship it to mrs", "send it to ur place",
            "ship it to da address",
        )], names=(UNSAVED, STORE))


class LinksAndHandles(Check):
    def test_links_emails_and_handles(self):
        self.check([
            ("linktr.ee/yassinmarzouk", "[link]"),
            ("see yassin.ai or yassin.dev or yassin.sa or yassin.uk", "see [link] or [link] or [link] or [link]"),
            ("my insta is yassin.marzouk.99", "my insta is [user]"), ("insta: yassin_marzouk99", "insta: [user]"),
            ("@ياسين_مرزوق", "[user]"), ("snap: yassinm99", "snap: [user]"),
            ("https://maps.google.com/?q=30.0444,31.2357", "[link]"), ("tiktok.com/@yassinm", "[link]"),
            ("yassin dot marzouk at gmail dot com", "[email]"), ("karim@example.com", "[email]"),
            ("karim at example dot com", "[email]"), ("karim(at)example.com", "[email]"),
            ("كريم@مثال.مصر", "[email]"), ("karim@example", "[user]"),
            ("https://maps.app.goo.gl/AbCdEf", "[link]"), ("wa.me/201001234567", "[link]"), ("bit.ly/xyz", "[link]"),
            ("example.com.eg/track/123", "[link]"), ("hxxp://example[.]com", "[link]"), ("t.me/karimfz", "[link]"),
            ("fb.com/karim.fawzy", "[link]"), ("facebook.com/karim.fawzy.5", "[link]"),
            ("instapay karim.fz@instapay", "instapay [user]"), ("حولت على فودافون كاش", "حولت على فودافون كاش"),
        ])

    def test_a_cue_word_needs_a_gap_before_the_handle(self):
        self.check([("instapay", "instapay"), ("snapchat story", "snapchat story")])


class Orders(Check):
    def test_order_numbers_and_amounts(self):
        self.check([
            ("الاوردر بتاعي 1045 وصل فين", "الاوردر بتاعي [order] وصل فين"), ("1045 ده رقم الاوردر", "[order] ده رقم الاوردر"),
            ("الاوردر اللي عملته من يومين 1045 وصل فين", "الاوردر اللي عملته من يومين [order] وصل فين"),
            ("my order from the other day 1045", "my order from the other day [order]"),
            ("الطلب اللي قبل كده كان 1450 جنيه", "الطلب اللي قبل كده كان 1450 جنيه"),
            ("order from the other day for 1450", "order from the other day for 1450"),
            ("my order from yesterday 1045 is late", "my order from yesterday [order] is late"),
            ("اوردر رقم 1045", "اوردر رقم [order]"), ("#1045", "[order]"), ("رقم الاوردر 1045", "رقم الاوردر [order]"),
            ("order 1045", "order [order]"), ("order #1045", "order [order]"), ("الطلب رقم ١٠٤٥", "الطلب رقم [order]"),
            ("رقم الطلب: BTL1045", "رقم الطلب: [user]"), ("order number is 1045", "order number is [order]"),
            ("the order (1045)", "the order ([order])"), ("my order no. 104", "my order no. [order]"),
            ("اوردر 1045 لسه موصلش", "اوردر [order] لسه موصلش"), ("كود الخصم KARIM10", "كود الخصم [user]"),
            ("رقم الطلب 1045 السعر 850 جنيه", "رقم الطلب [order] السعر 850 جنيه"),
            ("الاوردر 1500 جنيه", "الاوردر 1500 جنيه"),
        ])


class Addresses(Check):
    def test_addresses_and_places(self):
        address = ["جنب مطعم ابو علي", "المعادي دجلة ورا السنترال", "7ay el 3ashir", "عباس العقاد مدينة نصر",
                   "عنوان الشحن: المعادي دجلة", "30.0444, 31.2357", "30°02'39.8\"N 31°14'08.5\"E", "7GXHX6QM+2V",
                   "30.0444,31.2357", "٣٠٫٠٤٤٤، ٣١٫٢٣٥٧", "location: 30.0444 31.2357", "بالمنصورة", "للمنصورة",
                   "وبالمنصورة", "قرية الشهيد", "عزبة النخل", "ورا محطة البنزين", "جنب البنك الاهلي", "قصاد جامع النور",
                   "الدور التالت شقة 5", "الدور الرابع", "floor 3 flat 7", "عند كارفور المعادي", "عند سيتي ستارز",
                   "مول العرب", "Cairo Festival City"]
        self.check([(text, "[address]") for text in address])
        self.check([
            ("انا يوسف من طنطا", "انا [name] من [place]"), ("انا في المعادي", "انا في [place]"),
            ("انا ساكن في التجمع", "انا ساكن في [place]"), ("ساكن ف زهراء المعادي", "ساكن ف [place]"),
            ("ساكن في حدائق القبة", "ساكن في [place]"), ("انا في الشيخ زايد", "انا في [place]"),
            ("انا في 6 اكتوبر", "انا في [place]"), ("انا ف ٦ اكتوبر", "انا ف [place]"),
            ("انا في كفر الشيخ", "انا في [place]"), ("انا في الاسكندرية", "انا في [place]"),
            ("انا ف اسكندرية", "انا ف [place]"), ("ana fel ma3adi", "ana fel [place]"), ("ana f maadi", "ana f [place]"),
            ("ana fe tanta", "ana fe [place]"), ("ana f eskendereya", "ana f [place]"), ("ana fe alex", "ana fe [place]"),
            ("sakn fe nasr city", "sakn fe [place]"), ("انا في المنصوره", "انا في [place]"),
            ("في الدقهلية", "في [place]"), ("في ميت غمر", "في [place]"), ("في بلبيس", "في [place]"),
            ("في دسوق", "في [place]"), ("في العاشر", "في [place]"),
        ])

    def test_a_number_word_is_not_a_place(self):
        self.check([("الشحن تسعين جنيه", "الشحن تسعين جنيه"), ("الجزمة بالتسعين جنيه؟", "الجزمة بالتسعين جنيه؟")])


class NamesInOneChat(Check):
    """The review's chat: customer Karim Fawzy, own IG username karim.fz99."""
    NAMES = ("Karim Fawzy", "كريم فوزي", "Beyond Team", "Salma Test", "سلمى تجربة")

    def test_names_that_are_not_the_display_name(self):
        self.check([
            ("يا أستاذ محمد الطلب جاهز", "يا أستاذ [name] الطلب جاهز"), ("استاذ محمد الطلب جاهز", "استاذ [name] الطلب جاهز"),
            ("أهلا كابتن عمرو، المقاس متاح", "أهلا كابتن [name]، المقاس متاح"),
            ("مدام منى المقاس متاح", "مدام [name] المقاس متاح"), ("الاستاذ علي وصل", "الاستاذ [name] وصل"),
            ("تمام يا فندم يا هاني", "تمام يا فندم يا [name]"),
            ("الاستلام باسم محمود عبد الرحمن", "الاستلام باسم [name]"), ("ابعته لاخويا يوسف", "ابعته لاخويا [name]"),
            ("انا اسمي يوسف", "انا اسمي [name]"), ("Thanks Ahmed, your order is on the way",
                                                  "Thanks [name], your order is on the way"),
            ("Ahmed, the size 43 is available", "[name], the size 43 is available"), ("hello ahmed", "hello [name]"),
            ("Dear Mr Smith", "Dear Mr [name]"), ("msa2 el 5er ya 7oda", "msa2 el 5er ya [name]"),
            ("ya Hamada el ma2as 42", "ya [name] el ma2as 42"), ("ana Hamada", "ana [name]"),
            ("esmy Hamada Ali", "esmy [name]"), ("يا7ودة", "يا[name]"), ("يامحمد", "يا[name]"),
            ("ياأحمد المقاس موجود", "يا[name] المقاس موجود"), ("يا حمادة", "يا [name]"), ("يا مُحَمَّد", "يا [name]"),
        ], names=self.NAMES, users=["karim.fz99"])

    def test_the_chat_own_names_and_handles(self):
        self.check([
            ("karim", "[name]"), ("Karim", "[name]"), ("KARIM fawzy", "[name]"), ("كريم", "[name]"), ("وكريم", "[name]"),
            ("لكريم", "[name]"), ("بكريم", "[name]"), ("فكريم", "ف[name]"), ("اكريم", "[name]"),
            ("كريمفوزي", "[name]"), ("Karim.Fawzy", "[name]"), ("karim_fawzy", "[user]"), ("karim.fz99", "[user]"),
            ("@karim.fz99", "[user]"), ("instagram.com/karim.fz99", "[link]"), ("karimfz99", "[user]"),
        ], names=self.NAMES, users=["karim.fz99"])

    def test_a_title_with_a_common_word_after_it_stays(self):
        self.check([("يا استاذ ايه الاخبار", "يا استاذ ايه الاخبار")], names=self.NAMES)


def msg(text, team=False):
    return SimpleNamespace(text=text, team=team)


class ChatLevel(unittest.TestCase):
    def texts(self, rows):
        return cl.Cleaner([]).chat([]).texts([msg(t, team) for team, t in rows])

    def test_the_answer_to_the_name_question_is_a_name(self):
        moved = "تمام يا فندم، المقاس متاح والشحن بكرة"
        got = self.texts([(True, "تمام يا فندم، اسم حضرتك؟"), (False, "حسام"), (True, moved),
                          (False, "مقاس 42 لو سمحت")])
        self.assertEqual(got, ["تمام يا فندم، اسم حضرتك؟", "[name]", moved, "مقاس 42 لو سمحت"])

    def test_the_name_window_stays_open_to_the_store_next_message(self):
        moved = "تمام يا فندم، المقاس 42 متاح بسعر 1450 جنيه"
        got = self.texts([(True, "اسمك ايه؟"), (False, "لحظة"), (False, "لوكاس مارتن"), (False, "مقاس 42"),
                          (True, moved), (False, "لوكاس مارتن")])
        self.assertEqual(got, ["اسمك ايه؟", "[name]", "[name]", "[name]", moved, "لوكاس مارتن"])

    def test_more_ways_to_ask_the_name(self):
        for ask in ("ممكن الاسم بالكامل", "الاسم الثلاثي لو سمحت", "الاسم لو سمحت", "ممكن الاسم", "اسم المستلم؟",
                    "اسم المستلم والعنوان", "الاسم الكريم؟", "مين معايا؟", "اتشرف بمين؟", "احتاج الاسم والعنوان والتليفون",
                    "الاسم بالكامل و العنوان بالتفصيل", "Name?", "Full name?", "name and address please",
                    "who am i talking to", "الاسم"):
            with self.subTest(ask=ask):
                self.assertEqual(self.texts([(True, ask), (False, "لوكاس مارتن")])[1], "[name]")
        for line in ("الموديل اسمه Mercurial Vapor 15 والسعر 1450 جنيه", "تمام يا فندم"):  # no name asked
            with self.subTest(line=line):
                self.assertEqual(self.texts([(True, line), (False, "لوكاس مارتن")])[1], "لوكاس مارتن")

    def test_a_short_store_reply_keeps_the_name_window_open(self):
        for ack in ("تمام", "\U0001F44D", "ok", "منتظرك", "تمام يا فندم", "<تم استبعاد الوسائط>", "تم حذف هذه الرسالة",
                    "<Media omitted>", "This message was deleted"):
            with self.subTest(ack=ack):
                got = self.texts([(True, "اسمك ايه؟"), (False, "لحظة"), (True, ack), (False, "لوكاس مارتن")])
                self.assertEqual(got[3], "[name]")
        for moved in ("مقاس كام؟", "تمام يا فندم، المقاس 42 متاح بسعر 1450 جنيه"):  # a question or a longer line
            with self.subTest(moved=moved):
                got = self.texts([(True, "اسمك ايه؟"), (False, "لحظة"), (True, moved), (False, "لوكاس مارتن")])
                self.assertEqual(got[3], "لوكاس مارتن")
        got = self.texts([(True, "ابعتلي الاسم والعنوان"), (True, "تمام"), (False, "لوكاس مارتن"), (False, "شارع 9")])
        self.assertEqual(got[2:], ["[name]", "[address]"])

    def test_name_and_address_asked_at_once(self):
        got = self.texts([(True, "ابعتلي الاسم والعنوان"), (False, "لوكاس مارتن"), (False, "شارع الوادي 12"),
                          (False, "الحي التالت"), (True, "تمام"), (False, "الجزمة دي بكام")])
        self.assertEqual(got, ["ابعتلي الاسم والعنوان", "[name]", "[address]", "[address]", "تمام", "الجزمة دي بكام"])

    def test_the_address_window_from_the_store(self):
        got = self.texts([(True, "ابعتلي العنوان لو سمحت"), (False, "مدينة الشروق"), (False, "الحي التالت"),
                          (True, "تمام"), (False, "الجزمة دي بكام")])
        self.assertEqual(got, ["ابعتلي العنوان لو سمحت", "[address]", "[address]", "تمام", "الجزمة دي بكام"])

    def test_the_address_window_from_a_place(self):
        got = self.texts([(False, "مدينة نصر"), (False, "وصلها بكرة لو سمحت"), (True, "تمام"),
                          (False, "وصلها بكرة لو سمحت")])
        self.assertEqual(got, ["[address]", "[address]", "تمام", "وصلها بكرة لو سمحت"])
        got = self.texts([(False, "انا في المعادي"), (False, "وصلها بكرة لو سمحت")])
        self.assertEqual(got, ["انا في [place]", "وصلها بكرة لو سمحت"])
        got = self.texts([(False, "المعادي"), (False, "وصلها بكرة لو سمحت")])
        self.assertEqual(got[1], "[address]")

    def test_no_text_gives_an_empty_line(self):
        self.assertEqual(self.texts([(False, ""), (False, None)]), ["", ""])


def write_chat(src, name, sender, lines, day):
    rows = [f"{day:02d}/08/2026, 1{n % 10}:0{n % 10} - {STORE if side == 's' else sender}: {text}"
            for n, (side, text) in enumerate(lines)]
    with open(os.path.join(src, "whatsapp", f"WhatsApp Chat with {name}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")


PLACED = "تمام، تم تسجيل الطلب"
CHATS = [
    ("Abo Hamid", [("c", "الجزمة دي بكام"), ("s", "أهلا يا أستاذ محمود، الجزمة ب 1450 جنيه"),
                   ("c", "تمام ابعتها باسم محمود عبد الرحمن"), ("s", "تمام يا باشمهندس محمود"),
                   ("c", "مدينة نصر"), ("c", "عباس العقاد"), ("c", "فوق بنك مصر"), ("c", "الدور الخامس"),
                   ("c", "اللوكيشن ٣٠٫٠٤٤٤، ٣١٫٢٣٥٧"), ("s", PLACED)]),
    ("Zizo", [("c", "Hi, I'm Yasmine, boots in 38?"), ("s", "Hi Yasmine! yes, السعر 900 جنيه، معاك سارة من خدمة العملاء"),
              ("c", "حولتلك على انستاباي yasmine.k1990@instapay"), ("c", "my insta is yasmine_k1990 btw"),
              ("c", "el 3enwan: 5 share3 el nasr"), ("s", PLACED)]),
    ("+20 100 000 2222", [("c", "عايز جزمة مقاس 42 لابني عمر"), ("s", "تمام يا فندم، اسم حضرتك؟"),
                          ("c", "حسام"), ("s", "تمام يا أستاذ حسام، السعر 1450 جنيه"), ("c", "ابعتها لماما فاطمة"),
                          ("c", "ياريت توصل بكرة، انا في حدائق القبة"), ("s", PLACED)]),
    ("Team Ultras", [("c", "عايز التيشيرت مكتوب عليه HASSAN 10"), ("s", "تمام، هنطبع HASSAN 10، السعر 600 جنيه"),
                     ("c", "akkedly"), ("s", "el order et2aked, kalem el mandoob 01001234567 aw 012 3456 7890")]),
]
PROBES = ["محمود", "عبد الرحمن", "عباس العقاد", "بنك مصر", "الخامس", "30.0444", "Yasmine", "سارة", "yasmine", "1990",
          "nasr", "عمر", "حسام", "فاطمة", "حدائق القبة", "HASSAN", "012 3456 7890", "3456", "Hamid", "Zizo", "2222"]


def plain(raw):
    """A written file with its JSON escapes undone, so an Arabic probe can be found in it."""
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False)
    except ValueError:
        pass
    lines = []
    for line in raw.splitlines():
        try:
            lines.append(json.dumps(json.loads(line), ensure_ascii=False))
        except ValueError:
            lines.append(line)
    return "\n".join(lines)


class WholeRun(unittest.TestCase):
    def test_no_probe_string_reaches_the_replay_or_the_cards(self):
        with tempfile.TemporaryDirectory() as work:
            src = os.path.join(work, "src")
            os.makedirs(os.path.join(src, "whatsapp"))
            for i, (sender, lines) in enumerate(CHATS):
                write_chat(src, f"c{i}", sender, lines, 2 + 3 * i)
            write_chat(src, "filler", "Filler Person", [("c", "hi"), ("s", "hello")], 25)
            out = os.path.join(work, "out")
            rec = fake_recipe.load()
            summary = pp.run(src, out, model=ScriptedModel(rec), recipe=rec, team=[STORE])
            self.assertEqual(summary["labels"].get("won"), 4)
            written = []
            for root, _, files in os.walk(out):
                for f in files:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        written.append(plain(fh.read()))
            blob = "\n".join(written)
            for p in PROBES:
                with self.subTest(probe=p):
                    self.assertNotIn(p, blob)
            with open(os.path.join(out, "replay.jsonl"), encoding="utf-8") as f:
                rows = [json.loads(line) for line in f]
            turns = {r["id"]: [t.get("text") for t in r["turns"]] for r in rows}
            third = next(v for v in turns.values() if "تمام يا فندم، اسم حضرتك؟" in v)
            self.assertEqual(third[2], "[name]")
            first = next(v for v in turns.values() if "الجزمة دي بكام" in v)
            self.assertEqual(first[4:9], ["[address]"] * 5)


class Examples(unittest.TestCase):
    def test_lines_refused(self):
        for line in ["العنوان: 12 شارع التجربة", "شكرا يا حمادة على الرد", "الكود 12345 مش شغال",
                     "رقمي 0100 123 كلمني بكرة", "1-2-3-4-5 تمام كده", "كلمني على 01.23.45 بكرة",
                     "محمد قالي المقاس صغير", "وكريم قالي المقاس صغير", "ابعتها ل [name] بكرة",
                     "قال [na" + ZWSP + "me] المقاس صغير", "الكود ١٢٣٤٥ مش شغال", "الكود ０１２３４ مش شغال",
                     "مح" + ZWSP + "مد قالي المقاس صغير", "", None, "تمام", "x " * 120]:
            with self.subTest(line=line):
                self.assertFalse(cards_mod.example_ok(line))

    def test_lines_kept(self):
        for line in ["المقاس صغير شوية عليا", "السعر 1450 جنيه غالي شوية", "مقاس 42 او 43 متاح؟",
                     "is it real leather?"]:
            with self.subTest(line=line):
                self.assertTrue(cards_mod.example_ok(line))


if __name__ == "__main__":
    unittest.main()
