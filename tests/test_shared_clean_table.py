"""The shared pool's clean check (reflection/shared.py check) against every line the round 1 review
and red team found passing: number words with no currency in English, Arabic and Franco (glued forms
too), spelled digit runs, shops and brands at the start or in lower case, places, platform words,
the customer's own Franco words, Arabic script and more than one sentence. Each must be refused.
Round 2 adds every line both round 2 reports found passing (sound alikes, split and misspelled
numbers, ordinals, fractions, money slang, lower case names, brands and places), refused by the
English word list. Plain lines for any agent kind (sales, support, booking, coaching, marketing)
must still pass."""
import unittest

from kit import send_check
from reflection import shared

REFUSED = {
    "amount words, no currency (en)": [
        "Offer fifty off when the customer hesitates after hearing the cost.",
        "When they hesitate, offer a fifty percent code before they leave the chat.",
        "Offer free delivery above seventy five when the customer waits on the cost.",
        "The customer wants it for under five grand and goes quiet after that.",
        "The customer offers fifty bucks less and leaves when the store says no.",
        "The customer hears it costs twenty quid more and leaves without a word.",
        "When they hesitate, offer ten percent off before they leave the chat.",
        "When the reader hesitates, offer a half price trial before they leave.",
    ],
    "amount words (ar)": [
        "العميل بيسأل لو ينفع بخمسين اقل وبعدين بيسكت خالص لما المحل يرفض",
        "العميل عايزه بخمستلاف بالظبط وبيمشي لما يسمع السعر الحقيقي من المحل",
        "اعرض خصم عشرين في المية لما العميل يتردد بعد ما يسمع السعر",
        "العميل طلبه بسعر خمسين جنيه ورفض يزود",
    ],
    "amount words (franco)": [
        "the customer wants it for khamsingeneh and goes quiet after that answer",
        "the customer wants it for khamsin bas and goes quiet after that answer",
        "el zbon 3ayzo b khamastalaf w byemshi lama yesma3 el se3r el 7a2i2i",
        "el zbon 3ayzo b 3eshreen w byemshi lama yesma3 el se3r el 7a2i2i",
        "the customer asks for talateen off and leaves when the store says no",
        "the customer wanted it for khamsingeneh and walked away unhappy today",
        "the customer offered khamsin geneh and we refused the low price",
        "he offered myteingeneh for the jacket and then left the shop",
        "When the customer asks for arba3een off, explain the price calmly.",
        "When the customer offers sabeen less, explain the price calmly.",
    ],
    "slang currency or k": [
        "The customer wants it for five k and goes quiet after the store answers.",
        "The customer wants it for fifty dollars and goes quiet after the answer.",
        "the customer offered fifty pounds and left without buying anything",
        "When the customer offers fiftypounds less, explain the price calmly.",
        "When the customer offers fivek less, explain the price calmly.",
    ],
    "spelled digits": [
        "Ask them to call zero one zero one two three four five six seven eight.",
        "the customer number is zero one zero one two three four five six seven eight",
        "reach them at oh one oh one two three four five six seven eight today",
        "the final total came to one six five zero zero for that buyer",
        "When the buyer gives order one two three, check it before you reply.",
    ],
    "digits": [
        "call the customer back on 01012345678 before the day ends please",
        "the boots were priced at 16500 for that customer order today",
        "deliver the parcel to 15 Tahrir Street for that waiting customer now",
        "the buyer lives in building 15 flat 3 so note that for delivery",
        "the agent should note my number is 01012345678 and then act quickly ok",
    ],
    "places": [
        "Zamalek customers ask about same day delivery and leave when it is late.",
        "Customers in zamalek ask about same day delivery and leave when it is late.",
        "Customers in nasr city ask about same day delivery and leave when late.",
        "Customers from tagamo3 ask about same day delivery and leave when late.",
        "Customers from sheikh zayed ask about same day delivery and leave when late.",
        "Customers from heliopolis ask about same day delivery and leave when late.",
        "عملاء الزمالك بيسألوا عن التوصيل في نفس اليوم وبيمشوا لو اتأخر",
        "عملاء التجمع بيسألوا عن التوصيل في نفس اليوم وبيمشوا لو اتأخر",
        "Alexandria buyers want delivery the same day and leave if it is not possible.",
        "Customers in alex ask about same day delivery and leave when it is late.",
    ],
    "names, shops and brands": [
        "Zorvex buyers go quiet after hearing the cost of the boots in the chat.",
        "Karim asks for a discount after the price and then goes quiet for good.",
        "Customers like karim ask for a discount after the price and go quiet.",
        "The customer ziad asks for a discount after the price and then goes quiet.",
        "Customers of zorvex sports ask twice about delivery and then go quiet.",
        "عملاء محل الأمل بيسألوا عن الخصم بعد السعر وبعدين بيسكتوا",
        "الزبون كريم بيسأل عن الخصم بعد السعر وبعدين بيسكت خالص",
        "Be kind. Zorvex buyers go quiet after hearing the cost of the boots.",
        "the agent should remember Ahmed prefers morning delivery slots always",
        "the agent should remember that ahmed prefers morning delivery times",
        "العميل محمد بيفضل التوصيل الصبح دايما في المعاد",
        "Customers of zorvexstore ask twice about delivery and then go quiet.",
    ],
    "contact details and platforms": [
        "Tell them to message the instagram page zorvexstore when they hesitate.",
        "Tell them to write to zorvex at gmail when they hesitate on the size.",
        "Send them the whatsapp group invite when they ask about restock dates.",
        "the customer asked us to email ahmed at gmail dot com for updates",
        "write to the buyer at ahmed dot khaled at gmail dot com each time",
        "the agent should send them to the shop at example dot com for sizes",
        "the customer prefers we message their handle @ahmedk for the order",
        "When the customer asks, send the tiktok handle before they leave.",
    ],
    "customer words unquoted": [
        "When they say ghali awi offer a smaller size before they leave the chat.",
        "When the customer writes mesh 3ayez el lon da, offer the other colour quickly.",
        'the customer kept repeating "cash only" so the agent should plan for it',
    ],
    "round 2 red team: sound alikes, split, misspelled and Franco numbers, ordinals, fractions, other "
    "languages, roman numerals, lower case names, brands and places": [
        'Ask them to call zero one zero one two three four five six seven eight.',
        "Ask them to call oh won oh won too tree for fife sicks sev'n ate before noon.",
        'Ask them to call oh won oh won too tree for fife sicks sevn ate before noon.',
        'Ask them to call oh won oh won too tree for fife sicks seven ate before noon.',
        'When the customer says one won one too, greet them again kindly.',
        'When the customer offers twenty five less, explain the price calmly.',
        'When the customer offers fif ty less, explain the price calmly.',
        'When the customer offers fif-ty less, explain the price calmly.',
        "When the customer offers fif'ty less, explain the price calmly.",
        'When the customer offers fiftee less, explain the price calmly.',
        'When the customer offers fiftyy less, explain the price calmly.',
        'When the customer offers twen ty fiv e less, explain the price calmly.',
        'When the customer offers f i f t y less, explain the price calmly.',
        'When the customer offers fiveteen hundred less, explain the price calmly.',
        'When the customer offers khamsin less, explain the price calmly.',
        'When the customer offers ashara less, explain the price calmly.',
        'When the customer offers kham sin less, explain the price calmly.',
        'When the customer offers khamsinn less, explain the price calmly.',
        'When the customer offers khamsin gen-eh less, explain the price calmly.',
        'When the customer offers tomanya less, explain the price calmly.',
        'When the customer offers meyteen less, explain the price calmly.',
        'When the customer offers arbaa less, explain the price calmly.',
        'When the customer offers nos alf less, explain the price calmly.',
        'When the customer offers setta w noss less, explain the price calmly.',
        'When the customer offers 3ashara less, explain the price calmly.',
        'When the customer asks for the fifth size, explain the price calmly.',
        'When the customer offers a quarter off, explain the price calmly.',
        'When the customer asks for a third off, explain the price calmly.',
        'When the customer offers twentieth less, explain the price calmly.',
        'When the customer asks for a couple off, explain the price calmly.',
        'When the customer wants a dozen pairs, explain the price calmly.',
        'When the customer wants half the pairs, explain the price calmly.',
        'When the customer asks for the price in gen-eh, explain the price calmly.',
        'When the customer asks for the price in e g p, explain the price calmly.',
        'When the customer asks for the price in £, explain the price calmly.',
        'When the customer offers cinquante less, explain the price calmly.',
        'When the customer offers cincuenta less, explain the price calmly.',
        'When the customer gives order xv ii, check it before you reply.',
        'Ask them to call ٠١٠١٢٣٤٥٦٧٨ before noon.',
        'When the customer offers ½ off, explain the price calmly.',
        'When the customer offers ㊿ off, explain the price calmly.',
        'When the customer offers ५० off, explain the price calmly.',
        'When the customer offers 五十 off, explain the price calmly.',
        'Customers of zorvex go quiet after hearing the cost of the boots.',
        'When the customer compares the boots with zorvex, explain the fit calmly.',
        'Customers like menna ask for a discount after the price and go quiet.',
        'Customers like abdelrahman ask for a discount after the price and go quiet.',
        'Customers like sherif ask for a discount after the price and go quiet.',
        'Customers in sheraton ask about same day delivery and leave when late.',
        'Customers in haram ask about same day delivery and leave when late.',
        'Customers in october city ask about same day delivery and leave when late.',
        'Customers in smouha ask about same day delivery and leave when late.',
        'Customers in khobar ask about same day delivery and leave when late.',
        'Customers in sayeda zeinab ask about same day delivery and leave when late.',
    ],
    "round 2 review: lower case shops, names and places, ordinals, Franco tens, money slang": [
        'When customers of zorvex ask for a refund, offer an exchange first.',
        'When customers ask whether noorly delivers abroad, explain the policy calmly.',
        'When customers from qena ask about delivery, explain the courier timing.',
        'When customers in beni suef ask about delivery, explain the courier timing.',
        'When customers from kafr el sheikh ask about delivery, explain cash on delivery.',
        'When customers in port said ask about delivery, explain the courier timing.',
        'When customers from matrouh ask about delivery, explain the courier timing.',
        'When customers from menoufia ask about delivery, explain the courier timing.',
        'When customers from sharqia ask about delivery, explain the courier timing.',
        'When customers from october ask about delivery, explain the courier timing.',
        'When ahmed asks about the hoodie again, reply with the size chart first.',
        'When mona complains about late delivery, apologise and share the tracking.',
        'When the customer mentions the order from the twentieth, check its status first.',
        'When customers ask for a hundredth time, stay calm and answer.',
        'Customers who pay ashara upfront expect a faster delivery.',
        'Customers who pay tamania upfront expect a faster delivery.',
        'Customers who pay alfen upfront expect a faster delivery.',
        'Customers who mention khamastashar expect a discount.',
        'When customers ask for a quarter off, explain the fixed price.',
        'When customers ask for a score off, explain the fixed price.',
        'When the customer at house won too tree asks again, answer calmly.',
        'When customers text from the number ending in double oh, answer calmly.',
        'When customers ask about the zorvex hoodie, share the size chart.',
        'When customers mention the haram branch, explain delivery times.',
        'When customers mention a tiktok seller, explain the original product.',
        'When customers ask about snap or tele, answer in chat only.',
        'When customers ask for a fiver off, explain the fixed price.',
        'When customers ask for a tenner off, explain the fixed price.',
        'When customers send a voice note from the abdeen area, reply in text.',
    ],
    "shape": [
        "When the guest asks twice, answer plainly. Then offer the next free slot.",
        "Zorvex is where buyers go quiet after hearing the cost of the boots.",
        "When the guest asks twice, answer plainly; then offer the next free slot.",
        "Wenn der Kunde zögert, biete eine kleinere Größe an und warte ab.",
    ],
}

# plain patterns for any kind of agent: each must pass
CLEAN = [
    "When a customer goes quiet after hearing the cost, offer a smaller size before they leave.",
    "the agent should greet the customer and ask what they need politely",
    "Asks about delivery time twice, then goes quiet when the store does not say when.",
    "When no one has answered the customer yet, greet them and ask what they need.",
    "When the customer picks the one in the photo, confirm the size before the price.",
    "If a caller is upset about a late refund, explain the next step before anything else.",
    "Offer the next free slot when a guest asks to move the booking to another day.",
    "When a reader asks how to handle a broken login, explain the reset steps calmly.",
    "Customers who compare plans want the difference in plain words, not a list.",
    "When the store has no stock, say so plainly and offer to tell them when it is back.",
    "Ask one short question at a time when a new user is unsure what they need.",
    "Visitors who ask about the brand story stay longer when the answer is short and warm.",
    "Customers who shop for sportswear compare fabrics before they ask about the fit.",
    'When a customer asks for the price twice, answer once and add the delivery time.',
    'Offer the size chart before the customer asks for an exchange.',
    'Customers who hesitate after the price often want reassurance about returns.',
    'When a guest asks to move a booking, confirm the new time before closing.',
    'Ask which day suits the guest before offering a time slot.',
    'When a user reports a bug, thank them and ask for the steps they took.',
    'If a reader replies to a post with a complaint, answer in private with care.',
    'When someone asks if the product is original, explain how it is checked.',
    'Reply to a complaint with an apology before any explanation.',
    'Thank the customer and confirm the order summary before closing the chat.',
    'When a patient asks about a late appointment, apologise and offer the next free slot.',
    'Customers asking about stock usually want to know when it comes back.',
    'Listen first when a caller is angry, then restate the problem in plain words.',
    'When no one answers after the quote, follow up once the next day.',
    'Students who ask about the course length usually want to know the weekly time.',
    'Followers who comment on a post often want a quick private reply.',
    'Members who cancel often mention price, so ask what would keep them.',
    'When a tenant reports a leak, confirm the address details in private.',
    "When a coach is asked about a missed session, apologise and offer to rebook it.",
    "Patients who cancelled before often want an earlier appointment, so offer one plainly.",
    "If a follower asks about a same-day reply, explain when the team is online.",
    "Offer a one to one call when a learner is stuck on the same lesson twice.",
]


class CleanTable(unittest.TestCase):
    def test_every_probe_line_is_refused(self):
        for group, lines in REFUSED.items():
            for line in lines:
                with self.subTest(group=group, line=line):
                    self.assertNotEqual(shared.check(line), [])

    def test_plain_lines_for_any_kind_pass(self):
        for line in CLEAN:
            with self.subTest(line=line):
                self.assertEqual(shared.check(line), [])

    def test_the_reasons_name_each_new_guard(self):
        cases = [
            ("العميل محمد بيفضل التوصيل الصبح دايما في المعاد", "Arabic script: a pattern is written in English"),
            ("Wenn der Kunde zögert, biete eine kleinere Größe an und warte ab.", "letters other than English"),
            ("When the guest asks twice, answer plainly. Then offer the next free slot.", "more than one sentence"),
            ("Zorvex is where buyers go quiet after hearing the cost of the boots.",
             "does not start with a listed opener"),
            ("When the buyer gives order one two three, check it before you reply.", "a number in words"),
            ("When the customer offers fivek less, explain the price calmly.", "a currency or an amount"),
            ("When the customer asks for arba3een off, explain the price calmly.", "a number in words"),
            ("When they say ghali awi offer a smaller size before they leave the chat.",
             "a Franco word: the customer's own words"),
            ("When the customer asks, send the tiktok handle before they leave.", "a platform or handle word"),
            ("Customers in zamalek ask about same day delivery and leave when it is late.", "a place"),
            ("Customers of zorvexstore ask twice about delivery and then go quiet.", "a shop, brand or page name"),
            ("Customers of zorvex sports ask twice about delivery and then go quiet.", "a shop, brand or page name"),
            ("When they hesitate, offer a fifty percent code before they leave the chat.",
             "a currency or an amount"),
            ("When they hesitate, offer a discount of half % before they leave.", "a currency or an amount"),
        ]
        for line, reason in cases:
            with self.subTest(line=line):
                self.assertIn(reason, shared.check(line))

    def test_a_lone_one_is_a_word_but_one_beside_a_digit_word_is_a_number(self):
        self.assertNotIn("a number in words", shared.check("When no one replies, greet the customer again kindly."))
        self.assertIn("a number in words", shared.check("When the customer says one two, greet them again kindly."))
        self.assertIn("a number in words", shared.check("When the customer says nine one, greet them again kindly."))

    def test_each_number_form_alone_is_a_number(self):
        # one line per form, nothing else in it to refuse, so each part of NUMBER_TOKEN is needed
        numbers = {"a number in words", "an amount in words", "a currency or an amount"}
        for form in ("talattashar", "khamastashar", "meetein", "khomsomeya", "khamastalaf", "talattalaf",
                     "btalateen", "bel3eshreen", "twentyfive", "fiftyandfive", "one oh one oh"):
            line = f"When the customer offers {form} less, explain the price calmly."
            with self.subTest(form=form):
                self.assertEqual(shared.check(line.replace(form, "a little")), [])
                self.assertTrue(numbers & set(shared.check(line)), shared.check(line))

    def test_the_new_guards_say_why(self):
        cases = [
            ("Customers of zorvex go quiet after hearing the cost of the boots.", "a word not in the English word list"),
            ("When mona complains about late delivery, apologise and share the tracking.", "a first name"),
            ("When customers in port said ask about delivery, explain the courier timing.", "a place"),
            ("Ask them to call oh won oh won too tree for fife sicks seven ate before noon.", "a number in words"),
            ("When customers text from the number ending in double oh, answer calmly.", "a number in words"),
            ("When customers ask for a fiver off, explain the fixed price.", "a word not in the English word list"),
            ("When the customer asks for the price in gen-eh, explain the price calmly.", "a currency or an amount"),
        ]
        for line, reason in cases:
            with self.subTest(line=line):
                self.assertIn(reason, shared.check(line))

    def test_the_word_list_is_the_public_domain_dictionary_without_numbers_or_capitals(self):
        import lzma
        head = lzma.decompress(shared.WORDS_FILE.read_bytes())[:400].decode("ascii")
        self.assertIn("Webster's Second International Dictionary (1934), public domain", head)
        words = shared.english()
        self.assertGreater(len(words), 150_000)
        for w in ("customer", "hesitate", "delivery", "refund", "price"):
            self.assertIn(w, words)
        for w in ("fiver", "tenner", "score", "quarter", "half", "dozen", "couple", "pair", "grand", "fifth",
                  "twentieth", "hundredth", "october", "monday", "cairo", "mona", "sherif", "zorvex"):
            with self.subTest(word=w):
                self.assertNotIn(w, words)
        for w in ("customers", "hesitated", "apologised", "colours", "stopped", "don't", "customer's", "same-day"):
            with self.subTest(word=w):
                self.assertTrue(shared._english_word(w))

    def test_sound_alikes_count_only_in_a_run(self):
        self.assertEqual(shared.check("When the customer won too, thank them and offer the next size."), [])
        self.assertEqual(shared.check("Offer a one to one call when a learner is stuck on the same lesson."), [])
        self.assertIn("a number in words", shared.check("When the customer at house won too tree asks, answer."))
        self.assertIn("a number in words", shared.check("When the customer says one won one too, greet them."))

    def test_the_franco_tens_with_a_currency_are_a_spelled_amount_in_the_send_check(self):
        for line in ("el zbon 3ayez talateen geneh", "3ayez khamseen gneh bas", "be arba3een geneh"):
            with self.subTest(line=line):
                self.assertIsNotNone(send_check.SPELLED_AMOUNT.search(line))


if __name__ == "__main__":
    unittest.main()
