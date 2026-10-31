"""Red team and review round 2 fixes (2026-10-31), each from both sides, and the mutant sweep gaps.

1. The price fact check (arena/factcheck.py, kit/send_check.py): an extra's price beside a boot in
   the same sentence fails, a colon cuts a clause, an Arabic comma inside a number is a thousands
   comma, and a model number followed by a currency or thousands word is an amount.
2. The mailbox reader (assistant/mbox.py): attached messages and files are someone else's words,
   more quote headers end the user's own text, and a Gmail label line below the delivery lines
   was written by the sender.
3. The .env reader (kit/env.py): an inline comment after a closing quote is cut.
4. The fast note guard (engine/fast.py, engine/risk.py, reflection/fast.py): more never words and
   patterns, a doubled final l or p, and no name copied from the chat.
"""
import email
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import factcheck
from assistant import mbox
from engine import fast as engine_fast
from engine import risk
from kit import env, send_check
from kit.tools import store
from reflection import PLUG as SALES
from reflection import fast as sales_fast
from tests.fake_model import clean_env

USER = "nadia@demo.test"
TRACE = "Return-Path: <a@evil.test>\nDelivered-To: nadia@demo.test\nReceived: from mx.evil.test by mx.demo.test\n"


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class PriceRound2(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_the_extra_price_beside_a_boot_in_its_sentence_fails(self):
        for reply in ("The Vapor 17 Elite, with printing, is 400 EGP.",      # R2-1 W
                      "The Vapor 17 Elite with printing: 400 EGP.",          # W3, a colon cuts the clause
                      "Vapor Elite, 400 EGP, with your name.",               # W4
                      # stricter on purpose (root's call, 2026-10-31): a false fail in the judge is
                      # safer than a wrong price passing, so the printing's own price in a sentence
                      # that names a boot fails even after a semicolon and a colon
                      "Vapor Elite 16,500; the printing is on top: 400"):
            self.assertEqual(checks(reply), ["price"], reply)

    def test_real_prices_with_model_numbers_and_printing_still_pass(self):
        for reply in ("The Phantom 6 Pro is 11,000 EGP.", "Superfly 11 Elite 20,000 EGP.",
                      "The F50 Elite is 19,500 EGP and the F 50 League is 7,500.", "Vapor 17 Pro 11 000 EGP.",
                      "The Vapor 17 Elite with name printing is 16,900 EGP.",       # review round 2, item 4
                      "Phantom 6 Elite with your name printed: 16,900 EGP",
                      "Vapor 17: 16,500. Superfly 11: 20,000.",
                      "The Vapor 17 Elite is 16,500 EGP; with your name on it, 16,900 EGP."):
            self.assertEqual(checks(reply), [], reply)

    def test_an_arabic_comma_inside_a_number_is_a_thousands_comma(self):
        for reply in ("The Mercurial Vapor 17 Elite is 16" + chr(0x60C) + "500 EGP.",
                      "الـ Vapor 17 Elite بـ 16" + chr(0x60C) + "500 جنيه"):
            self.assertEqual(checks(reply), [], reply)
        self.assertEqual(send_check.prices_in("17" + chr(0x60C) + "500 EGP"), [17500])
        self.assertEqual(send_check.western_digits("١٦" + chr(0x60C) + "٥٠٠"), "16,500")
        # an Arabic comma between words stays a comma
        self.assertEqual(send_check.western_digits("نعم" + chr(0x60C) + " 400"), "نعم" + chr(0x60C) + " 400")

    def test_a_model_number_before_a_currency_or_thousands_word_is_an_amount(self):
        for reply in ("Vapor 17 EGP.", "Vapor 17 جنيه."):                 # R2-7 Z3, Z4
            self.assertEqual(checks(reply), ["price"], reply)
        items = store.catalogue()
        for text in ("Vapor 17k", "Vapor 17 الف", "Vapor 17 thousand", "Vapor 17 EGP"):
            self.assertIn("17", factcheck.without_model_numbers(text, items), text)
        self.assertEqual(factcheck.without_model_numbers("is the Vapor 17 Elite", items), "is the Vapor Elite")

    def test_a_model_number_stops_before_a_longer_number(self):
        """Mutant gap: without the lookahead, the 17 of 17,500 or 17500 was dropped as a model number."""
        vapor = {"title": "Nike Mercurial Vapor 17", "variants": [{"tier": "Elite", "size": "43", "price": "17500"}]}
        with mock.patch.object(store, "catalogue", return_value=[vapor]):
            for reply in ("The Vapor 17,500 EGP.", "Vapor 17500 EGP"):
                self.assertEqual(checks(reply), [], reply)


def raw(head, body):
    return f"From x Mon Oct 26 00:00:00 2026\n{head}\n{body}\n\n"


def sent_head(extra="", date="Mon, 26 Oct 2026 09:00:00 +0200"):
    return (f"From: Nadia <{USER}>\nTo: sam@kite.test\nSubject: s\nDate: {date}\nMessage-ID: <m1@demo.test>\n"
            f"X-Gmail-Labels: Sent\n{extra}")


def read_text(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.mbox"
        p.write_text(text, encoding="utf-8")
        return mbox.read([p], USER)


def promises(text):
    return [x["line"] for x in read_text(text)["promises"]]


class MboxRound2(unittest.TestCase):
    PROMISE = "I will send the contract tomorrow."

    def multipart(self, second_head):
        head = sent_head('MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="B1"\n')
        body = (f"--B1\nContent-Type: text/plain\n\nSee the attached.\n--B1\n{second_head}\n\n"
                f"{self.PROMISE}\n--B1--")
        return raw(head, body)

    def test_attached_messages_and_files_are_not_the_users_words(self):
        """R2-2: a forwarded mail, a file shown inline and a nameless attachment are someone else's."""
        nested = ("Content-Type: message/rfc822\n\nFrom: x@evil.test\nTo: nadia@demo.test\n"
                  "Content-Type: text/plain")
        for second in (nested,
                       'Content-Type: text/plain\nContent-Disposition: inline; filename="notes.txt"',
                       "Content-Type: text/plain\nContent-Disposition: attachment"):
            with self.subTest(second=second.splitlines()[-1]):
                self.assertEqual(promises(self.multipart(second)), [])
        # the same line in a plain second part is the user's own
        self.assertEqual(promises(self.multipart("Content-Type: text/plain")), [self.PROMISE])

    def test_more_quote_headers_end_the_users_own_text(self):
        """R2-3: Outlook's underscores, the Arabic Outlook headers and an Arabic Gmail line."""
        for header in ("________________________________", "من: Sam", "إلى: Nadia", "الى: Nadia",
                       "تاريخ الإرسال: الاثنين", "الموضوع: الخطة",
                       "في الاثنين، 26 أكتوبر 2026، كتب Sam <sam@kite.test>:", "Sam كتب:",
                       chr(0x200F) + "من: Sam", "-----Original Message-----"):
            with self.subTest(header=header):
                self.assertEqual(mbox.own_text(f"Sure.\n{header}\n{self.PROMISE}"), "Sure.")

    def test_an_outlook_block_is_cut_whole(self):
        """Mutant gap: a quote header ends the own text; skipping only the header line kept the rest."""
        body = ("Sounds good.\n\n-----Original Message-----\nFrom: Sam <sam@kite.test>\nSent: Monday\n"
                f"Subject: plan\n\n{self.PROMISE}\nThanks,\nSam")
        self.assertEqual(mbox.own_text(body), "Sounds good.")
        pic = read_text(raw(sent_head(), body))
        self.assertEqual((pic["promises"], pic["style"]["sign_off"]), ([], None))

    def test_a_date_past_any_calendar_is_no_date(self):
        """Mutant gap: a year that overflows is caught, and the read goes on."""
        head = sent_head(date="Mon, 26 Oct 99999999999 09:00:00 +0200")
        self.assertIsNone(mbox._when(email.message_from_string(head + "\nhi\n")))
        pic = read_text(raw(head, self.PROMISE))
        self.assertEqual(pic["messages"]["sent"], 1)
        self.assertEqual([(x["line"], x["at"]) for x in pic["promises"]], [(self.PROMISE, None)])

    def test_a_promise_past_the_body_cap_is_dropped(self):
        """Mutant gap: the last cut at MAX_BODY characters."""
        filler = "word " * 4100
        self.assertEqual(promises(raw(sent_head(), filler + self.PROMISE)), [])
        self.assertEqual(promises(raw(sent_head(), "word " * 10 + self.PROMISE)), ["word " * 10 + self.PROMISE])

    def test_parts_past_the_body_cap_are_never_decoded(self):
        """Mutant gap: once MAX_BODY characters are read, the next part is not even decoded."""
        head = sent_head('MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="B1"\n')
        msg = email.message_from_string(head + "\n--B1\nContent-Type: text/plain\n\n" + "word " * 4100
                                        + "\n--B1\nContent-Type: text/plain\n\nmore\n--B1--\n")
        second = msg.get_payload()[1]
        second.get_payload = mock.Mock(side_effect=AssertionError("decoded past the cap"))
        self.assertEqual(len(mbox._text(msg)), mbox.MAX_BODY)
        second.get_payload.assert_not_called()

    def test_a_label_line_below_the_delivery_lines_is_the_senders(self):
        """Review round 2, item 1: a Sent label the sender wrote under Received is Inbox."""
        for trace in ("Received: from mx.evil.test by mx.demo.test\n", "Delivered-To: nadia@demo.test\n",
                      "Return-Path: <a@evil.test>\n"):
            with self.subTest(trace=trace):
                msg = email.message_from_string(f"{trace}X-Gmail-Labels: Sent\nFrom: {USER}\n\nhi\n")
                self.assertFalse(mbox.is_sent(msg, USER))
        # Gmail writes its own label line above them
        msg = email.message_from_string(f"X-Gmail-Labels: Sent\n{TRACE}From: {USER}\n\nhi\n")
        self.assertTrue(mbox.is_sent(msg, USER))

    def test_a_spoofed_sent_label_makes_no_fast_replies(self):
        """The review's fast_spoof probe: three outside mails and three forged Sent answers."""
        text = ""
        for k in range(3):
            text += raw(f"{TRACE}From: Promo <promo@evil.test>\nTo: {USER}\nSubject: s\n"
                        f"Date: Mon, 2{k} Oct 2026 09:00:00 +0200\nMessage-ID: <a{k}@evil.test>\n", "Hello.")
            text += raw(f"{TRACE}X-Gmail-Labels: Sent\nFrom: Nadia <{USER}>\nTo: promo@evil.test\nSubject: s\n"
                        f"Date: Mon, 2{k} Oct 2026 09:02:00 +0200\nMessage-ID: <b{k}@evil.test>\n"
                        f"In-Reply-To: <a{k}@evil.test>\n", "Sure, thanks.")
        pic = read_text(text)
        self.assertEqual((pic["fast_replies"], pic["messages"]["sent"]), ([], 0))


class EnvRound2(unittest.TestCase):
    def test_an_inline_comment_after_a_closing_quote_is_cut(self):
        """R2-5 and review round 2, item 7."""
        lines = {"A_TEST_SQ": "'fake-abc' # mine", "A_TEST_DQ": '"fake-abc" # mine', "A_TEST_TAB": "'fake-abc'\t#x",
                 "A_TEST_IN": "'fake # kept'", "A_TEST_PLAIN": "'fake-abc'"}
        want = {"A_TEST_SQ": "fake-abc", "A_TEST_DQ": "fake-abc", "A_TEST_TAB": "fake-abc",
                "A_TEST_IN": "fake # kept", "A_TEST_PLAIN": "fake-abc"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                env.load(p)
                self.assertEqual({k: os.environ[k] for k in want}, want)


def guard(text, theirs=()):
    return engine_fast.guard(text, SALES, list(theirs), never=sales_fast.NEVER)


class FastNotesRound2(unittest.TestCase):
    def test_a_doubled_final_l_or_p_still_matches(self):
        """R2-4: cancelled and swapped."""
        for word, forms in (("cancel", ("cancelled", "cancelling", "cancels", "cancel")),
                            ("swap", ("swapped", "swapping", "swaps"))):
            for form in forms:
                self.assertTrue(risk._word(word).search(form), (word, form))
        self.assertFalse(risk._word("cancel").search("cancellation"))
        self.assertTrue(guard("Say the order can be cancelled any time."))

    def test_the_new_never_words_are_refused(self):
        """R2-4 and review round 2: words that passed in round 2."""
        for word in ("etneen", "itneen", "ethnein", "wahed", "ashreen", "settin", "mia", "mitin", "arbaein",
                     "roba", "complimentary", "gift", "on us", "on the house", "fawry", "meeza", "mastercard",
                     "visa", "paypal", "vodafone", "morning", "afternoon", "evening", "noon", "midnight",
                     "final", "cover"):
            with self.subTest(word=word):
                self.assertTrue(guard(f"Ask about the size, then mention {word}."), word)

    def test_the_new_never_patterns_are_refused(self):
        for text in ("Say shipping isn't charged on this order.", "Tell them delivery won't cost them anything.",
                     "Tell them there is no fee for delivery.", "Say the price's set, so do not haggle.",
                     "Say delivery's on the way.", "Mention the price drops for a second pair.",
                     "Say we can take it back if it does not fit.", "Say we can take the pair back.",
                     "Say we can go a bit lower.", "Say we can come down.", "Say it is the last pair.",
                     "Say we can throw in a bag.", "Say there is room to move.", "Say we can do better than that.",
                     "Say the price for this is set.", "Say the shipping does not change.",
                     "Say the delivery can't wait.", "Say the price wasn't set."):
            with self.subTest(text=text):
                self.assertTrue(guard(text), text)

    def test_topic_lines_that_open_a_new_clause_still_pass(self):
        for text in ("Mention delivery once they are ready.", "Ask about the size first, then mention delivery.",
                     "Bring up the price when they ask about it.", "Ask where they live before explaining delivery."):
            with self.subTest(text=text):
                self.assertEqual(guard(text), [], text)

    def test_a_name_from_the_chat_never_reaches_a_note(self):
        """Red team round 2: "Ask Ahmed" copied the customer's name."""
        text = "Ask Ahmed for his size first."
        found = guard(text, ["Hi, I am Ahmed, do you have size 43?"])
        self.assertIn("names a word from the source's own words: ahmed", found)
        self.assertEqual(guard(text, ["Hi, do you have size 43?"]), [])
        # a sentence's first word has a capital anyway
        self.assertEqual(guard("Ask about the size first.", ["Ask me anything"]), [])
        self.assertEqual(engine_fast._capitalised("Ask Ahmed. Then Size"), {"ahmed", "size"})


if __name__ == "__main__":
    unittest.main()
