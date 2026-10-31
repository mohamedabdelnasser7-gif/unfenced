"""Cleaning for the Arena (arena/clean.py, new 2026-10-30): each kind of name, number and place
taken out in Arabic, Franco and English, and prices and sizes kept. Made-up text only."""
import re
import unittest

from arena import clean as cl


def cleaned(text, names=(), users=()):
    return cl.Cleaner(names).chat(names, users)(text)


class Kinds(unittest.TestCase):
    def check(self, cases, names=(), users=()):
        for text, want in cases:
            self.assertEqual(cleaned(text, names, users), want, text)

    def test_phones(self):
        self.check([("رقمي ٠١٠٠٠٠٠١٢٣٤", "رقمي [phone]"), ("kalemny 01000001234", "kalemny [phone]"),
                    ("call me on +20 100 000 1234", "call me on [phone]")])

    def test_other_long_numbers(self):
        for text in ("الكارت 4111 1111 1111 1111", "el ra2am el qawmy 29001010101010", "card 4111-1111-1111-1111"):
            got = cleaned(text)
            self.assertIsNone(re.search(r"\d{4}", got), got)
            self.assertTrue(cl.PLACEHOLDER.search(got), got)

    def test_addresses(self):
        self.check([("العنوان: 12 شارع التجربة", "[address]"), ("3enwany share3 el nasr", "[address]"),
                    ("My address is 7 Test Street", "[address]"), ("قدام مدرسة التجربة", "[address]")])

    def test_places(self):
        self.check([("أنا من المنصورة", "أنا من [place]"), ("ana fel maadi", "ana fel [place]"),
                    ("I live in Nasr City", "I live in [place]"), ("الشحن لاسكندرية", "الشحن [place]")])

    def test_orders(self):
        self.check([("الطلب رقم 1045 اتأخر", "الطلب رقم [order] اتأخر"), ("el order number 1045", "el order number [order]"),
                    ("my order #1045", "my order [order]")])

    def test_emails_links_and_users(self):
        self.check([("ابعتلي على demo@example.com", "ابعتلي على [email]"), ("shoft wa.me/201000001234", "shoft [link]"),
                    ("see www.example.com/boots", "see [link]"), ("my friend @demo.friend", "my friend [user]"),
                    ("demouser here", "[user] here")], users=["demouser"])

    def test_names(self):
        self.check([("اسمي محمود تجربة", "اسمي [name]"), ("esmy Mahmoud", "esmy [name]"),
                    ("my name is Omar", "my name is [name]"), ("شكرا يا سلمى", "شكرا يا [name]"),
                    ("thanks Hany", "thanks [name]"), ("Karim here", "[name] here")], names=["Demo Karim"])

    def test_a_full_name_from_another_chat_is_masked(self):
        self.assertEqual(cl.Cleaner(["سلمى تجربة"]).chat([])("قولي لسلمى تجربة"), "قولي ل[name]")
        self.assertEqual(cl.Cleaner(["سلمى تجربة"]).chat([])("سلمى تجربة كلمتني"), "[name] كلمتني")

    def test_a_display_name_does_not_hide_its_words_in_other_chats(self):
        c = cl.Cleaner(["Real Madrid Fan", "Demo Hany"])
        self.assertEqual(c.chat(["Demo Hany"])("is it real leather?"), "is it real leather?")

    def test_forms_of_address_stay(self):
        self.check([("تمام يا فندم", "تمام يا فندم"), ("thanks bro", "thanks bro"), ("ya basha kam?", "ya basha kam?")])


class Kept(unittest.TestCase):
    def test_prices_and_sizes_stay(self):
        for text in ("السعر 1450 جنيه", "مقاس 43 متاح؟", "el se3r 1450 geneh", "size 42 please", "الطلب 850 جنيه",
                     "The boots are 1450 EGP, shipping is 60 EGP", "ana 42.5, a5od 42 wala 43?", "خصم 10%"):
            self.assertEqual(cleaned(text), text)

    def test_clubs_are_not_places(self):
        self.assertEqual(cleaned("عندكم طقم الزمالك؟"), "عندكم طقم الزمالك؟")


if __name__ == "__main__":
    unittest.main()
