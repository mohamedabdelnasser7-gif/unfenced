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
from unittest import mock
from pathlib import Path

from reflection import shared
from tests import plugs
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


class NearEqual(unittest.TestCase):
    """Patterns that say the opposite never join (review crossowner round 1, item 4)."""
    PAIRS = (("Ask the size before you tell the customer the price of the item.",
              "Ask the size after you tell the customer the price of the item."),
             ("Offer a discount when the customer hesitates after hearing the cost.",
              "Never offer a discount when the customer hesitates after hearing the cost."),
             ("Share the delivery cost first when the customer asks about the order.",
              "Share the delivery cost last when the customer asks about the order."),
             ("Ask about the size more often when the customer hesitates on the fit.",
              "Ask about the size less often when the customer hesitates on the fit."),
             ("Offer the smaller size when the customer hesitates on the cost again.",
              "Offer the smaller size when the customer hesitates on the cost once."),
             ("Offer the smaller size when the customer usually hesitates on the cost.",
              "Offer the smaller size when the customer rarely hesitates on the cost."),
             ("Offer the smaller size when the customer always hesitates on the cost.",
              "Offer the smaller size when the customer hesitates on the cost."),
             ("Do offer a smaller size when the customer hesitates on the cost of it.",
              "Do not offer a smaller size when the customer hesitates on the cost of it."))

    def test_opposite_patterns_from_two_owners_stay_apart(self):
        for one, two in self.PAIRS:
            with self.subTest(one=one):
                self.assertEqual(shared.check(one), [])
                self.assertEqual(shared.check(two), [])
                self.assertFalse(shared.same(shared.words(one), shared.words(two)))
                pool = shared.Pool("sales", fresh(self))
                pool.add(shared.LESSON, one, OWNER_A, "k1")
                got, _ = pool.add(shared.LESSON, two, OWNER_B, "k2")
                self.assertEqual(len(got["owners"]), 1)
                self.assertEqual(pool.shared(shared.LESSON), [])

    def test_short_patterns_join_only_when_their_words_are_the_same(self):
        two, three = ["cost", "quiet"], ["cost", "quiet", "size"]
        self.assertFalse(shared.same(two, three))  # under MIN_SAME_WORDS: only the very same words are one
        self.assertTrue(shared.same(two, list(reversed(two))))
        self.assertTrue(shared.same(three + ["fit"], three + ["fit", "colour"]))  # 4 of 5 at MIN_SAME_WORDS up

    def test_a_worry_label_that_leaks_is_not_kept(self):
        pool = shared.Pool("sales", fresh(self))
        for worry, kept in (("zamalek", None), ("ahmed", None), ("fifty pounds", None), ("delivery time", "delivery time")):
            with self.subTest(worry=worry):
                got, why = pool.add(shared.LOST, LOST_EN, OWNER_A, f"chat:{worry}", worry=worry)
                self.assertEqual(why, [])
                self.assertEqual(got["worry"], kept)
                pool.patterns.clear()  # the next label starts a fresh pattern
                pool._save()

    def test_the_same_polar_word_on_both_sides_still_joins(self):
        self.assertTrue(shared.same(shared.words(NEAR_EN), shared.words(CLEAN_EN)))
        self.assertTrue(shared.same(shared.words("Never offer a discount when the customer hesitates on the cost."),
                                    shared.words("Never offer a discount if a customer hesitates on the cost.")))


class OwnerId(unittest.TestCase):
    """The pool counts an owner by an id the system writes into its state folder, never by the name
    owner.json or a plug gives (red team crossowner round 1 item 2, review item 3)."""

    def setUp(self):
        self.root = fresh(self)
        self.plug, self.folder = plugs.owned(dict(plugs.FAN, agent="fan_a", kind="fans", owner="acme"), self)
        self.home = self.folder.parent

    def rename(self, name):
        (self.home / "owner.json").write_text(json.dumps({"owner": name}), encoding="utf-8")
        data = json.loads((self.folder / "plug.json").read_text(encoding="utf-8"))
        data["owner"] = name
        (self.folder / "plug.json").write_text(json.dumps(data), encoding="utf-8")

    def test_the_id_is_written_once_and_is_not_the_name(self):
        got = shared.owner_id(self.folder)
        self.assertRegex(got, r"^owner-id:[0-9a-f]{32}$")
        self.assertNotIn("acme", got)
        self.assertEqual(shared.owner_id(self.folder), got)
        self.assertEqual(oct((self.home / shared.OWNER_ID_FILE).stat().st_mode & 0o777), "0o600")
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith(".")], [])

    def test_a_renamed_owner_is_one_owner_and_its_lesson_given_before(self):
        lesson = {"id": 3, "text": "Offer the smaller fan first."}
        a = shared.Link.for_agent(self.plug, self.folder, writer_of(CLEAN_EN), self.root).give_lesson("fan_a", lesson)
        self.rename("acme_new")
        b = shared.Link.for_agent(self.plug, self.folder, writer_of(NEAR_EN), self.root).give_lesson("fan_a", lesson)
        self.assertIsNone(a["why"])
        self.assertEqual(b["why"], "given before")
        c = shared.Link.for_agent(self.plug, self.folder, writer_of(NEAR_EN), self.root).give_lesson(
            "fan_a", {"id": 4, "text": "Offer the smaller fan."})
        self.assertEqual(c["owners"], 1)  # a near equal pattern of the renamed owner joins as the same owner
        self.assertEqual(shared.Pool("fans", self.root).shared(shared.LESSON), [])

    def test_no_owner_json_or_another_name_gives_nothing(self):
        (self.home / "owner.json").unlink()
        self.assertEqual(shared.owner_id(self.folder), "")
        self.assertEqual(shared.owner_id(None), "")
        (self.home / "owner.json").write_text(json.dumps({"owner": "other"}), encoding="utf-8")
        self.assertEqual(shared.owner_id(self.folder), "")
        link = shared.Link.for_agent(self.plug, self.folder, writer_of(CLEAN_EN), self.root)
        self.assertEqual(link.give_lesson("fan_a", {"id": 1, "text": "x"})["why"],
                         "this agent names no owner, so it gives nothing")
        self.assertFalse((self.home / shared.OWNER_ID_FILE).exists())

    def test_two_agents_of_one_owner_share_its_id(self):
        other = self.home / "fan_b"
        other.mkdir()
        (other / "plug.json").write_text(json.dumps(dict(plugs.FAN, agent="fan_b", kind="fans", owner="acme")),
                                         encoding="utf-8")
        self.assertEqual(shared.owner_id(other), shared.owner_id(self.folder))

    def test_an_id_file_that_is_a_link_or_out_of_shape_is_refused(self):
        path = self.home / shared.OWNER_ID_FILE
        path.write_text("not an id", encoding="utf-8")
        with self.assertRaises(shared.Refused):
            shared.owner_id(self.folder)
        path.unlink()
        (self.home / "elsewhere").write_text("a" * 32, encoding="utf-8")
        path.symlink_to(self.home / "elsewhere")
        with self.assertRaises(shared.Refused):
            shared.owner_id(self.folder)


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
        self.assertEqual(set(data), {"kind", "patterns", "keys", "names"})
        for o in data["patterns"][0]["owners"]:
            self.assertRegex(o, r"^[0-9a-f]{48}$")  # the keyed hash, then its seal
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
        self.assertTrue(self.pool.given("lesson:a:9"))  # only its hash: not asked again

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

    def two_shared(self):
        self.pool.add(shared.LESSON, CLEAN_EN, OWNER_A, "k1")
        self.pool.add(shared.LESSON, NEAR_EN, OWNER_B, "k2")
        self.pool.add(shared.LOST, LOST_EN, OWNER_A, "k3")
        self.pool.add(shared.LOST, LOST_EN, OWNER_B, "k4")
        path = self.root / "patterns-support.json"
        return path, json.loads(path.read_text())

    def test_owners_are_sealed_to_their_pattern(self):
        path, data = self.two_shared()
        self.assertEqual(len(shared.Pool("support", self.root).shared(shared.LESSON)), 1)
        cases = {
            "an owner added by hand": lambda d: d["patterns"][0]["owners"].append("f" * 48),
            "a seal copied to a new owner hash": lambda d: d["patterns"][0]["owners"].append(
                "e" * 32 + d["patterns"][0]["owners"][0][32:]),  # the seal covers the owner (E07)
            "an owner moved from another pattern": lambda d: d["patterns"][0]["owners"].__setitem__(
                1, d["patterns"][1]["owners"][1]),
            "the words changed": lambda d: d["patterns"][0].__setitem__("text", NEAR_EN),
            "the worry changed": lambda d: d["patterns"][0].__setitem__("worry", "price"),
            "the id changed": lambda d: d["patterns"][0].__setitem__("id", "a" * 12),
            "lesson made lost": lambda d: d["patterns"][0].__setitem__("what", shared.LOST),
            "the same owner twice": lambda d: d["patterns"][0]["owners"].__setitem__(
                1, d["patterns"][0]["owners"][0]),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                d = json.loads(json.dumps(data))
                edit(d)
                path.write_text(json.dumps(d))
                pool = shared.Pool("support", self.root)
                self.assertEqual(pool.shared(shared.LESSON), [])  # the edited row is dropped
                self.assertEqual(len(pool.shared(shared.LOST)), 1)  # the other row stands
                self.assertFalse(pool.broken)

    def test_a_pool_with_no_key_or_a_new_key_is_broken_and_never_written(self):
        path, data = self.two_shared()
        before = path.read_bytes()
        (self.root / shared.KEY_FILE).unlink()
        pool = shared.Pool("support", self.root)
        self.assertFalse((self.root / shared.KEY_FILE).exists())  # reading never makes a key
        self.assertTrue(pool.broken)
        self.assertEqual(pool.patterns, [])
        with self.assertRaises(shared.Refused):
            pool.add(shared.LESSON, CLEAN_EN, OWNER_C, "k5")  # read under the lock first: no key is made
        self.assertFalse((self.root / shared.KEY_FILE).exists())
        self.assertEqual(pool.shared(shared.LESSON, but=OWNER_C), [])
        self.assertFalse((self.root / shared.KEY_FILE).exists())
        (self.root / shared.KEY_FILE).write_text("b" * 64)  # a new key, which seals none of them
        with self.assertRaises(shared.Refused):
            shared.Pool("support", self.root).add(shared.LESSON, CLEAN_EN, OWNER_C, "k6")
        self.assertEqual(path.read_bytes(), before)

    def test_a_file_that_cannot_be_read_is_never_written_over(self):
        path, data = self.two_shared()
        good = path.read_bytes()
        cases = {"out of shape": b'{"kind": "support", "patterns": {}}', "not json": b"{not json",
                 "a list": b"[]", "cut short": good[:len(good) // 2], "oversize": good}
        for name, raw in cases.items():
            with self.subTest(name):
                path.write_bytes(raw)
                with mock.patch.object(shared, "MAX_FILE", len(good) - 1 if name == "oversize" else shared.MAX_FILE):
                    pool = shared.Pool("support", self.root)
                    self.assertTrue(pool.broken)
                    with self.assertRaises(shared.Refused):
                        pool.add(shared.LESSON, CLEAN_EN, OWNER_C, "k9")
                self.assertEqual(path.read_bytes(), raw)
        path.unlink()
        self.assertFalse(shared.Pool("support", self.root).broken)  # no file yet is a fresh pool
        self.assertGreaterEqual(shared.MAX_FILE, shared.MAX_PATTERNS * shared.MAX_OWNERS * 51)

    def test_a_file_whose_rows_all_fail_the_row_check_is_broken_and_never_written_over(self):
        # red team crossowner round 2, item 3: an older file format, or rows the clean check now refuses
        path, data = self.two_shared()
        cases = {"owners unsealed": lambda p: p.update(owners=[o[:32] for o in p["owners"]]),
                 "text now refused": lambda p: p.update(text="Customers of zorvex go quiet after hearing the cost."),
                 "not a row": lambda p: p.clear()}
        for name, edit in cases.items():
            with self.subTest(name):
                d = json.loads(json.dumps(data))
                for p in d["patterns"]:
                    edit(p)
                path.write_text(json.dumps(d))
                before = path.read_bytes()
                pool = shared.Pool("support", self.root)
                self.assertTrue(pool.broken)
                with self.assertRaises(shared.Refused):
                    pool.add(shared.LESSON, CLEAN_EN, OWNER_C, "k7")
                self.assertEqual(path.read_bytes(), before)

    def test_rows_copied_to_another_kind_do_not_verify(self):
        path, data = self.two_shared()
        data["kind"] = "sales"
        (self.root / "patterns-sales.json").write_text(json.dumps(data))
        pool = shared.Pool("sales", self.root)
        self.assertEqual(pool.patterns, [])
        self.assertTrue(pool.broken)

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

    def test_a_pattern_copying_five_words_of_its_lesson_is_dropped(self):
        lesson = {"id": 7, "text": "Explain the quiet setting first when the grower asks about noise twice."}
        copied = "When the grower asks about noise, explain the quiet setting before anything else."
        self.assertEqual(shared.check(copied), [])  # clean on its own: only the copy drops it
        got = shared.Link("support", OWNER_A, writer_of(copied), self.root).give_lesson("desk", lesson)
        self.assertIsNone(got["pattern"])
        self.assertIn("copied", got["why"])
        self.assertEqual(shared.Pool("support", self.root).patterns, [])


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


class RefusePath(unittest.TestCase):
    """Red team crossowner round 2 item 4 and review item 2: the pool is read under the lock before
    the writer is asked; a broken pool, a pool that refuses, and a writer with no line each count as
    failed, so the night asks the writer nothing more."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "shared"
        self.asked = []

    def writer(self, line):
        def w(what, kind, data):
            self.asked.append(what)
            return line
        return w

    def broken(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "patterns-support.json").write_text("{cut short", encoding="utf-8")

    def test_a_broken_pool_is_failed_before_the_writer_is_asked(self):
        self.broken()
        link = shared.Link("support", OWNER_A, self.writer(CLEAN_EN), self.root)
        for got in (link.give_lesson("a", {"id": 1, "text": "Spin the fans slowly."}),
                    link.give_chat("c1", [{"text": "hello"}], "price")):
            self.assertTrue(got["failed"])
            self.assertIsNone(got["pattern"])
        self.assertEqual(self.asked, [])
        self.assertFalse((self.root / shared.KEY_FILE).exists())

    def test_a_writer_with_no_line_is_failed_and_not_kept_as_given(self):
        shared.Pool("support", self.root).add(shared.LESSON, CLEAN_EN, OWNER_B, "other")  # the pool has a key
        for line in (None, ""):
            with self.subTest(line=line):
                link = shared.Link("support", OWNER_A, self.writer(line), self.root)
                got = link.give_lesson("a", {"id": 2, "text": "Spin the fans slowly."})
                self.assertEqual((got["failed"], got["asked"], got["pattern"]), (True, True, None))
                self.assertEqual(link.pool.ready(f"{link.db}\x00lesson:2", OWNER_A), None)  # asked again later

    def test_a_pool_that_breaks_after_it_was_read_is_failed(self):
        link = shared.Link("support", OWNER_A, self.writer(CLEAN_EN), self.root)
        with mock.patch.object(shared.Pool, "ready", return_value=None):
            self.broken()
            got = link.give_lesson("a", {"id": 3, "text": "Spin the fans slowly."})
        self.assertTrue(got["failed"])
        self.assertIn("the pool refused it", got["why"])

    def test_a_grow_night_on_a_broken_pool_asks_the_writer_nothing(self):
        from arena import grow
        from arena.scripted import ScriptedModel
        from arena.tag import Tagger
        from kit.db import Db
        from tests.test_arena_grow import LOST, NOW, SINCE, recipe, write_chats, write_owner, write_plug
        owner = self.root.parent / "agents"
        owner.mkdir(parents=True)
        write_owner(owner, "north")
        write_plug(owner / "store_north", "store_north", "sales", owner="north")
        self.root.mkdir()
        (self.root / "patterns-sales.json").write_text("{cut short", encoding="utf-8")
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, tuple((f"{LOST[0]}-{i}", LOST[1]) for i in range(8)))
        link = shared.Link("sales", shared.owner_id(owner / "store_north"), self.writer(LOST_EN), self.root)
        counts = grow.grow(db, grow.Pool(owner, "sales"), since=SINCE, until=NOW, shared=link,
                           tagger=Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe()))
        self.assertEqual(self.asked, [])
        self.assertEqual(counts.get("writer failed"), 1)
