"""The shared pool across owners (reflection/shared.py; DECISIONS items 24, 51, 62, 83): the clean
check blocks every leak class in English, Arabic and Franco, a pattern seen at one owner is never
shared, near equal patterns from two owners join, owners are kept as keyed hashes only, a dropped
pattern is never stored, and lost patterns become practice customers holding nothing of a chat.
The writer runs on the fake model; no key, no network."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from reflection import shared
from tests.fake_model import FakeModel, say

CLEAN_EN = "When a customer goes quiet after hearing the cost, offer a smaller size before they leave."
NEAR_EN = "If the customer goes quiet after hearing the cost, offer a smaller size before they leave."
LOST_EN = "Asks about delivery time twice, then goes quiet when the store does not say when."
OWNER_A, OWNER_B, OWNER_C = "north_shop", "south_shop", "east_shop"

LEAKS = {
    "a name": [
        "Customer Ahmed asks for a discount after the price and goes quiet.",
        "العميل اسمه محمد بيسأل عن الخصم وبعدين بيختفي",
        "the customer mahmoud asks for a discount and then goes quiet",
    ],
    "a digit": [
        "Offer the jacket at 500 when they hesitate on the cost of it.",
        "اعرض الجاكيت ب ٥٠٠ لما العميل يتردد في السعر بتاعه",
        "el 3amil bye2ool el se3r ghali w bymshi men gheir rad",
    ],
    "an amount or currency": [
        "Offer free delivery for orders above fifty dollars when they waver.",
        "اعرض توصيل مجاني لما الطلب يعدي خمسمية جنيه والعميل متردد",
        "the customer wants it for alf geneh and goes quiet after that.",
    ],
    "a place": [
        "A customer from Maadi asks for delivery the same day and leaves.",
        "العميل من المعادي بيسأل عن التوصيل في نفس اليوم ومش بيرد",
        "law el zbon mn masr el gedida yes2al 3an el sha7n bsor3a",
    ],
    "a phone": [
        "Ask them to call zero one zero when they hesitate: 01012345678",
        "اطلب منه يكلم الرقم ٠١٠١٢٣٤٥٦٧٨ لو اتردد في السعر",
        "2ollo yekalem 01012345678 law etradad fel se3r",
    ],
    "an email or a link": [
        "Tell them to email sales at shop dot com when they hesitate.",
        "قوله يبعت على الايميل sales@shop.com لو اتردد في الطلب",
        "2ollo yeshoof www.shop-site.com law mesh fahem el maqasat",
    ],
    "quoted words": [
        'When they say "too expensive for me" offer a smaller size quickly.',
        "لما العميل يقول «غالي اوي» اعرض عليه مقاس اصغر بسرعة",
        "lama el zbon y2ool 'ghali awi' e3red 3aleh 7aga ar5as",
    ],
    "a hand off": [
        "Hand the chat to the owner when the customer asks for a refund.",
    ],
    "a capitalised name": [
        "When the buyer mentions Zorvex boots, compare the two models calmly.",
    ],
    "a length": ["Too short.", "word " * 60],
    "a masked word": ["When [name] asks for the price again, answer it plainly and kindly."],
    "Arabic script": ["عندما يسأل العميل عن الشحن، اشرح المدة قبل أن تطلب العنوان."],
}


def fresh(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name) / "shared"


class CleanCheck(unittest.TestCase):
    def test_clean_patterns_pass(self):
        for text in (CLEAN_EN, NEAR_EN, LOST_EN):
            with self.subTest(text=text):
                self.assertEqual(shared.check(text), [])

    def test_each_leak_class_is_blocked_in_every_language(self):
        for leak, texts in LEAKS.items():
            for text in texts:
                with self.subTest(leak=leak, text=text):
                    self.assertNotEqual(shared.check(text), [])

    def test_the_reasons_name_the_leak(self):
        self.assertIn("a digit", shared.check(LEAKS["a digit"][1]))
        self.assertIn("a currency or an amount", shared.check(LEAKS["an amount or currency"][2]))
        self.assertIn("quoted words", shared.check(LEAKS["quoted words"][1]))
        self.assertIn("hands a chat to a person", shared.check(LEAKS["a hand off"][0]))
        self.assertIn("a capitalised name", shared.check(LEAKS["a capitalised name"][0]))
        self.assertTrue(any("[name]" in r for r in shared.check(LEAKS["a name"][2])))
        self.assertTrue(any("[place]" in r for r in shared.check(LEAKS["a place"][1])))
        self.assertTrue(any("[email]" in r for r in shared.check(LEAKS["an email or a link"][0])))
        self.assertIn("a masked word", shared.check(LEAKS["a masked word"][0]))
        self.assertIn("more than one line", shared.check(CLEAN_EN + "\n" + CLEAN_EN[:40]))

    def test_words_copied_from_the_source_are_quoted(self):
        said = "honestly the price feels high for what it is so maybe later"
        line = "When the customer says the price feels high for what it is, offer a smaller size."
        self.assertEqual(shared.check(line), [])
        self.assertIn("quoted words: a run of words copied from what it was written from",
                      shared.check(line, [said]))

    def test_amounts_in_words_with_no_currency_are_amounts(self):
        for text in ("Offer a discount when they want a thousand pieces at once from the store.",
                     "العميل عايز ألف قطعة مرة واحدة وبعدين بيسكت خالص",
                     "The customer asks for hundreds of pieces and then goes quiet after the cost."):
            with self.subTest(text=text):
                self.assertIn("an amount in words", shared.check(text))

    def test_an_amount_glued_to_its_currency_is_an_amount(self):
        for text in ("العميل يتردد لما يسمع خمسينجنيه ويمشي من غير ما يرد",
                     "the customer hears fiftypounds and goes quiet without a reply at all."):
            with self.subTest(text=text):
                self.assertIn("a currency or an amount", shared.check(text))

    def test_a_link_spelled_out_is_a_link(self):
        self.assertIn("a link, phone or handle",
                      shared.check("Tell them to visit shop dot com slash sizes when they ask twice."))

    def test_hidden_digits_and_styled_numbers_are_digits(self):
        for text in ("Offer the jacket at ５００ when they hesitate on the cost.",
                     "Offer the jacket at ۵۰۰ when they hesitate on the cost."):
            with self.subTest(text=text):
                self.assertIn("a digit", shared.check(text))


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.root = fresh(self)
        self.pool = shared.Pool("support", self.root)

    def test_a_pattern_seen_at_one_owner_is_never_shared(self):
        got, why = self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "lesson:a:1")
        self.assertEqual(why, [])
        self.pool.add(shared.LESSON, NEAR_EN, OWNER_A, "lesson:a2:7")  # a second agent of the same owner
        self.assertEqual(self.pool.shared(shared.LESSON), [])
        self.assertEqual(len(got["owners"]), 1)
        again = shared.Pool("support", self.root)
        self.assertEqual(again.shared(shared.LESSON), [])
        self.assertEqual(len(again.patterns), 1)

    def test_two_owners_near_equal_make_it_shared(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "lesson:a:1")
        got, _ = self.pool.add(shared.LESSON, NEAR_EN, OWNER_B, "lesson:b:4")
        self.assertEqual(len(got["owners"]), 2)
        out = shared.Pool("support", self.root).shared(shared.LESSON)
        self.assertEqual([p["text"] for p in out], [CLEAN_EN])  # the first wording stays
        self.assertEqual(shared.Pool("support", self.root).shared(shared.LESSON, but=OWNER_A), [])
        self.assertEqual(len(shared.Pool("support", self.root).shared(shared.LESSON, but=OWNER_C)), 1)

    def test_different_patterns_or_kinds_do_not_join(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        self.pool.add(shared.LESSON, LOST_EN, OWNER_B, "k2")
        self.pool.add(shared.LOST, CLEAN_EN, OWNER_B, "k3")
        self.assertEqual(self.pool.shared(shared.LESSON), [])
        self.assertEqual(self.pool.shared(shared.LOST), [])
        self.assertFalse(shared.same(shared.words(CLEAN_EN), shared.words(LOST_EN)))
        self.assertTrue(shared.same(shared.words(CLEAN_EN), shared.words(NEAR_EN)))

    def test_a_kind_is_its_own_pool(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        other = shared.Pool("sales", self.root)
        other.add(shared.LESSON, NEAR_EN, OWNER_B, "k2")
        self.assertEqual(shared.Pool("support", self.root).shared(shared.LESSON), [])
        self.assertEqual(shared.Pool("sales", self.root).shared(shared.LESSON), [])

    def test_an_owner_id_is_never_stored_raw(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "lesson:agent_a:1")
        self.pool.add(shared.LESSON, NEAR_EN, OWNER_B, "lesson:agent_b:2")
        raw = b"".join(p.read_bytes() for p in self.root.iterdir() if p.is_file())
        for owner in (OWNER_A, OWNER_B, "agent_a", "agent_b"):
            with self.subTest(owner=owner):
                self.assertNotIn(owner.encode(), raw)
                self.assertNotIn(hashlib.sha256(owner.encode()).hexdigest()[:32].encode(), raw)  # keyed, not bare
        data = json.loads((self.root / "patterns-support.json").read_text())
        self.assertEqual(set(data), {"kind", "patterns", "keys"})
        for o in data["patterns"][0]["owners"]:
            self.assertRegex(o, r"^[0-9a-f]{32}$")
        self.assertEqual(oct((self.root / "patterns-support.json").stat().st_mode & 0o777), "0o600")

    def test_hashes_are_keyed_per_folder(self):
        other = shared.Pool("support", fresh(self))
        self.assertNotEqual(self.pool.owner_hash(OWNER_A), other.owner_hash(OWNER_A))
        self.assertEqual(self.pool.owner_hash(OWNER_A), shared.Pool("support", self.root).owner_hash(OWNER_A))

    def test_a_dropped_pattern_is_never_stored(self):
        leak = LEAKS["a name"][0]
        got, why = self.pool.add(shared.LESSON, leak, OWNER_A, "lesson:a:9")
        self.assertIsNone(got)
        self.assertTrue(why)
        raw = (self.root / "patterns-support.json").read_text()
        self.assertNotIn("Ahmed", raw)
        self.assertEqual(json.loads(raw)["patterns"], [])
        self.assertTrue(self.pool.given(OWNER_A, "lesson:a:9"))  # only its hash: not asked again

    def test_a_hand_edited_dirty_pattern_is_not_read(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        self.pool.add(shared.LESSON, NEAR_EN, OWNER_B, "k2")
        path = self.root / "patterns-support.json"
        data = json.loads(path.read_text())
        data["patterns"][0]["text"] = "Customer Ahmed asks for a discount after the price and goes quiet."
        path.write_text(json.dumps(data))
        self.assertEqual(shared.Pool("support", self.root).shared(shared.LESSON), [])
        data["patterns"][0]["text"] = CLEAN_EN
        data["patterns"][0]["owners"] = [OWNER_A, OWNER_B]  # raw ids, not hashes
        path.write_text(json.dumps(data))
        self.assertEqual(shared.Pool("support", self.root).shared(shared.LESSON), [])

    def test_refusals(self):
        from arena import paths
        with self.assertRaises(shared.Refused):
            shared.Pool("support", paths.ROOT / "engine" / "shared")
        with self.assertRaises(shared.Refused):
            shared.Pool("Not A Kind", self.root)
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        (self.root / "patterns-sales.json").write_text((self.root / "patterns-support.json").read_text())
        with self.assertRaises(shared.Refused):
            shared.Pool("sales", self.root)

    def test_links_are_refused(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        other = self.root.parent / "elsewhere"
        other.mkdir()
        os.symlink(self.root, self.root.parent / "linked")
        with self.assertRaises(shared.Refused):  # the shared folder itself a link
            shared.Pool("support", self.root.parent / "linked")
        (other / "patterns-billing.json").write_text((self.root / "patterns-support.json").read_text()
                                                     .replace('"support"', '"billing"'))
        os.symlink(other / "patterns-billing.json", self.root / "patterns-billing.json")
        with self.assertRaises(shared.Refused):  # the pool file a link
            shared.Pool("billing", self.root)
        (other / "owner-key").write_bytes((self.root / "owner-key").read_bytes())
        (self.root / "owner-key").unlink()
        os.symlink(other / "owner-key", self.root / "owner-key")
        with self.assertRaises(shared.Refused):  # the key a link
            shared.Pool("support", self.root).owner_hash(OWNER_A)


def writer_of(*lines):
    """The pattern writer on the fake model, giving each line as the model's JSON answer."""
    return shared.Writer(model=FakeModel(*[say(json.dumps({"pattern": x}) if x is not None else "no json")
                                          for x in lines]))


class WriterAndLink(unittest.TestCase):
    def setUp(self):
        self.root = fresh(self)

    def test_the_writer_reads_the_models_line(self):
        w = writer_of(CLEAN_EN, None)
        self.assertEqual(w(shared.LESSON, "support", {"lesson": "x"}), CLEAN_EN)
        self.assertIsNone(w(shared.LESSON, "support", {"lesson": "x"}))
        sent = w.model.calls[0]["messages"]
        self.assertIn("never quote", sent[0]["content"])
        self.assertEqual(json.loads(sent[1]["content"]), {"lesson": "x"})

    def test_a_kept_lesson_is_given_once_and_a_leak_is_dropped(self):
        a = shared.Link("support", OWNER_A, writer_of(CLEAN_EN, LEAKS["a phone"][0]), self.root)
        got = a.give_lesson("helper", {"id": 1, "text": "Say how long delivery takes before asking for the address."})
        self.assertIsNotNone(got["pattern"])
        self.assertEqual(a.give_lesson("helper", {"id": 1, "text": "anything"})["why"], "given before")
        bad = a.give_lesson("helper", {"id": 2, "text": "Give the store line when they ask."})
        self.assertIsNone(bad["pattern"])
        self.assertTrue(bad["why"].startswith("dropped: "))
        self.assertEqual(len(a.writer.model.calls), 2)  # the given one was not asked again
        self.assertNotIn("01012345678", (self.root / "patterns-support.json").read_text())

    def test_a_link_reads_only_what_other_owners_saw(self):
        a = shared.Link("support", OWNER_A, writer_of(CLEAN_EN), self.root)
        b = shared.Link("support", OWNER_B, writer_of(NEAR_EN), self.root)
        c = shared.Link("support", OWNER_C, None, self.root)
        a.give_lesson("helper", {"id": 1, "text": "one"})
        self.assertEqual(c.lessons(), [])  # seen at one owner: not shared
        b.give_lesson("desk", {"id": 3, "text": "two"})
        self.assertEqual([(x["text"], x["owners"]) for x in c.lessons()], [(CLEAN_EN, 2)])
        self.assertEqual(shared.Link("support", OWNER_A, None, self.root).lessons(), [])

    def test_an_agent_with_no_owner_gives_nothing(self):
        lone = shared.Link("support", "", writer_of(CLEAN_EN), self.root)
        self.assertEqual(lone.give_lesson("x", {"id": 1, "text": "y"})["why"],
                         "this agent names no owner, so it gives nothing")
        self.assertEqual(lone.writer.model.calls, [])

    def test_a_lost_chat_copied_word_for_word_is_dropped(self):
        turns = [{"from": "customer", "text": "how long does the delivery take to reach me please tell me"}]
        copied = "Asks how long does the delivery take to reach me, and then goes quiet."
        a = shared.Link("support", OWNER_A, writer_of(copied), self.root)
        got = a.give_chat("c1:4", turns, "delivery time")
        self.assertIsNone(got["pattern"])
        self.assertIn("copied", got["why"])


class PracticeCards(unittest.TestCase):
    def test_shared_lost_patterns_become_cards_holding_no_chat(self):
        root = fresh(self)
        turns_a = [{"from": "customer", "text": "zorvexian boots arrive when exactly in my area"}]
        turns_b = [{"from": "customer", "text": "plumtree jacket shipping takes how many days"}]
        shared.Link("support", OWNER_A, writer_of(LOST_EN), root).give_chat("a:1", turns_a, "delivery time")
        self.assertEqual(shared.practice_cards("support", root), [])  # one owner only
        near = "Asks about the delivery time twice, then goes quiet when the store does not say when."
        shared.Link("support", OWNER_B, writer_of(near), root).give_chat("b:9", turns_b, "delivery time")
        cards = shared.practice_cards("support", root)
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertTrue(c["id"].startswith("grown-shared-"))
        self.assertEqual((c["worry"], c["want"], c["examples"], c["unwinnable"]), (LOST_EN, [], [], False))
        self.assertEqual(c["shared"], {"owners": 2, "worry": "delivery time"})
        blob = json.dumps(cards) + (root / "patterns-support.json").read_text()
        for word in ("zorvexian", "plumtree", "my area"):
            self.assertNotIn(word, blob)
        self.assertEqual(shared.practice_cards("support", None), [])
        self.assertEqual(shared.practice_cards("sales", root), [])


if __name__ == "__main__":
    unittest.main()
