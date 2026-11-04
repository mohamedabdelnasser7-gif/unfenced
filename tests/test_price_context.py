"""The extra price rule follows the extra named in the sentence before (live Sales Arena run 2026-11-04:
3 of the 4 losses in 20 matches were this false fail). A price clause that names no product, no tier
and no extra, in a sentence that names a boot or a tier only after it, takes the extra named before
it in its sentence, else the extra the nearest sentence before names. A boot or a tier before the
amount keeps the strict rule, a sentence in between that names a boot or a tier ends the context,
and every earlier guard still fails. Made-up text against the demo store data; no model, no network."""
import unittest

from arena import factcheck
from tests.fake_model import clean_env

AC = chr(0x60C)  # the Arabic comma


def prices(reply, customer=""):
    return [f["why"] for f in factcheck.check(reply, customer) if f["check"] == "price"]


LIVE = ("We have Beyond the Limits Name Printing, your name printed with UV DTF: two stickers, one on each "
        "shoe. Price is 400 EGP, and it is free with any Elite boot, one free printing for each Elite pair.")


class TheExtraFromTheSentenceBefore(unittest.TestCase):

    def setUp(self):
        clean_env(self)

    def test_the_live_reply_passes(self):
        self.assertEqual(prices(LIVE), [])

    def test_variants_pass(self):
        for reply in ("Printing is available. It costs 400 EGP, free with an Elite.",
                      "Name printing is available. Price is 400 EGP, and it is free with any Elite pair.",
                      "Name Printing, 400 EGP, free with any Elite.",
                      "We print your name on two stickers. Sizes are all fine. It is 400 EGP, free with an Elite.",
                      "Want name printing? It is 400 EGP, free with an Elite.",
                      "عندنا طباعة الاسم. سعرها 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "3andena tba3et el esm. Se3rha 400 EGP, w free m3 ay Elite."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])


class TheStrictRuleStays(unittest.TestCase):

    def setUp(self):
        clean_env(self)

    def test_a_boot_or_tier_before_the_amount_in_the_same_sentence_fails(self):
        for reply in ("Name Printing is great. The Elite is 400 EGP, free printing too.",
                      "Name Printing is great. For the Elite, it is 400 EGP, free printing too.",
                      "Name Printing is great. The Vapor 17 Elite is 400 EGP, and it ships with the Elite box.",
                      "طباعة الاسم متاحة. الـ Elite بـ 400 جنيه" + AC + " والطباعة مجانية."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_a_sentence_in_between_that_names_a_boot_or_tier_ends_the_context(self):
        for reply in ("Name Printing is great. The Vapor 17 Elite is a fast boot. It is 400 EGP, free with an Elite.",
                      "Name Printing is great. The Elite is our best tier. It is 400 EGP, free with an Elite.",
                      "Name Printing is great. Do you want the Vapor 17 Elite? It is 400 EGP, free with an Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_a_sentence_before_that_names_a_boot_with_the_extra_gives_no_context(self):
        for reply in ("The Vapor 17 Elite with printing. Total is 400 EGP, and it ships with the Elite box.",
                      "The Vapor 17 Elite, with printing. It is 400 EGP, free with an Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_the_earlier_guards_still_fail(self):
        for reply in ("The Vapor 17 Elite, with printing, is 400 EGP.",
                      "The Elite is 400 EGP more, and printing is available too.",
                      "The Vapor 17 Elite with printing is 400 EGP.",
                      "With printing the Vapor 17 Elite is 400 EGP."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_the_earlier_passes_still_pass(self):
        for reply in ("Printing on the Vapor 17 Elite is 400 EGP.",
                      "If you add printing to the Elite, it's 400 EGP more."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])

    def test_a_question_reads_as_today(self):
        """The price rule never skipped a question; a boot before the amount still fails it, and a
        question after the extra's sentence reads the extra like a statement does."""
        for reply in ("Is the Elite 400 EGP?", "Name Printing is great. Is the Elite 400 EGP, free printing too?"):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))
        self.assertEqual(prices("Name printing is available. Is it 400 EGP, free with an Elite?"), [])

    def test_a_made_up_amount_still_fails_with_the_context(self):
        self.assertTrue(prices("Printing is available. It costs 450 EGP, free with an Elite."))


class ABootAfterTheAmountMustOfferTheExtraFree(unittest.TestCase):
    """The sentence before holds only while every boot or tier after the amount offers the extra free
    with it, or carries its own boot price. Otherwise the amount is the boot's (review pricectx round
    1, finding 1)."""

    def setUp(self):
        clean_env(self)

    def test_a_boot_priced_at_the_extras_amount_fails(self):
        for reply in ("Printing is available. The price is 400 EGP, for the Elite.",
                      "We do name printing. The total is 400 EGP, with the Vapor 17 Elite.",
                      "Name printing is available. It is 400 EGP, the Vapor 17 Elite.",
                      "Name printing is available. Our cheapest boot: 400 EGP, the Phantom 6 Academy.",
                      "Printing is available. Price: 400 EGP, Vapor 17 Elite.",
                      "Printing is available. That one is 400 EGP, the Elite.",
                      "Name printing is available. 400 EGP for the boot, Elite tier.",
                      "Name printing is available. The boot alone is 400 EGP, Vapor 17 Elite.",
                      "Printing is available. Boot plus printing comes to 400 EGP, Elite.",
                      "Printing is available. Your total is 400 EGP, Elite plus printing.",
                      "طباعة الاسم متاحة. السعر 400 جنيه" + AC + " للـ Elite.",
                      "طباعة الاسم متاحة. الجزمة بـ 400 جنيه" + AC + " Elite.",
                      "Tba3et el esm available. El se3r 400 EGP, lel Elite.",
                      "Tba3et el esm available. El gazma b 400 EGP, Elite.",
                      "Printing is great, but the price is 400 EGP, for the Elite.",
                      "With printing, total 400 EGP, Vapor 17 Elite.",
                      "Printing is available. Total with delivery is 460 EGP, for the Elite.",
                      "Printing is available. Total with delivery is 485 EGP, Vapor 17 Elite.",
                      "Printing is available. Which boot do you like? It is 400 EGP, the Elite.",
                      "Printing is available. Great choice! The Elite is 400 EGP.",
                      "Printing is available. It is 400 EGP, Vapor 17 Elite with free printing.",
                      "Printing is available. It is 400 EGP, the Elite with 0 EGP delivery.",
                      "Printing is available. It is 400 EGP, the Elite with free delivery.",
                      "Printing is available. It is 400 EGP, the Mercurial; Vapor 17 too."):
            with self.subTest(reply=reply):
                amount = "485" if "485" in reply else "460" if "460" in reply else "400"
                self.assertTrue(any(amount in w for w in prices(reply)), prices(reply))

    def test_the_customer_naming_the_extra_gives_no_pass(self):
        self.assertTrue(prices("Price is 400 EGP, for the Elite.", "Do you do name printing?"))
        self.assertTrue(prices("Price is 400 EGP, for the Elite."))

    def test_a_boot_cut_by_a_mark_before_the_amount_fails(self):
        """The text up to the clause's end is read whole: "The Mercurial; Vapor 17" names the boot even
        though neither clause names it alone (review pricectx round 1, finding 3)."""
        for reply in ("Name Printing is great. The Mercurial; Vapor 17 is 400 EGP, free printing too.",
                      "Name Printing is great. Vapor 17 (Elite) costs 400 EGP, free printing too.",
                      "Name Printing is great. Vapor - 17 Elite, 400 EGP, free printing too."):
            with self.subTest(reply=reply):
                self.assertTrue(prices(reply), reply)

    def test_a_boot_word_joined_to_the_extra_fails(self):
        for reply in ("Boot plus printing comes to 400 EGP, Elite.",
                      "Boot plus printing comes to 400 EGP.",
                      "Your boot with printing is 400 EGP.",
                      "الجزمة مع الطباعة بـ 400 جنيه."):
            with self.subTest(reply=reply):
                self.assertTrue(prices(reply), reply)

    def test_the_extra_offered_free_or_a_boot_with_its_own_price_passes(self):
        for reply in ("Printing costs 400 EGP, free with an Elite.",
                      "Printing is available. It costs 400 EGP, free with an Elite.",
                      "Name printing is available. It is 400 EGP, and the Elite is 16,500 EGP.",
                      "Name printing is available. It is 400 EGP, and with the Elite it is 16,900 EGP.",
                      "Two stickers with your name cost 400 EGP, free with an Elite.",
                      "Your name on the shoe costs 400 EGP, free with an Elite.",
                      "We have printing. Your name on two stickers costs 400 EGP, free with an Elite.",
                      "Printing is available. It is 400 EGP, and it is included with any Elite.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " وهدية مع أي Elite.",
                      "Tba3et el esm available. B 400 EGP, w bbalash m3 ay Elite.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " وببلاش مع أي جزمة Elite.",
                      "Printing on your boot is 400 EGP.",
                      "Name printing is 400 EGP for each pair."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])


class RoundTwoGuards(unittest.TestCase):
    """Review pricectx round 2: a clause that opens with a word for a boot prices the boot (finding 1),
    a free word about delivery offers no extra (finding 2), and a boot word joins the extra only when it
    opens the clause with no amount between (finding 3). The last list kills the reverts of item 4."""

    def setUp(self):
        clean_env(self)

    def test_a_clause_that_opens_with_a_boot_word_fails(self):
        for reply in ("Printing is available. The boot is 400 EGP, free printing with an Elite.",
                      "Printing is available. Boot price 400 EGP, free with an Elite.",
                      "Printing is available. The shoe is 400 EGP, free with an Elite.",
                      "طباعة الاسم متاحة. الجزمة بـ 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "Tba3et el esm available. El gazma b 400 EGP, w free m3 ay Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_a_price_per_pair_passes(self):
        for reply in ("Printing is available. Per pair it is 400 EGP, free with an Elite.",
                      "Printing is available. For each pair it is 400 EGP, free with an Elite.",
                      "Printing is available. It is 400 EGP a pair, free with an Elite.",
                      "Printing is available. It is 400 EGP per pair, free with an Elite.",
                      "طباعة الاسم متاحة. لكل جزمة 400 جنيه" + AC + " ومجانية مع أي Elite."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])

    def test_a_free_word_about_delivery_offers_no_extra(self):
        for reply in ("Printing is available. Total is 400 EGP, free delivery with the Elite.",
                      "Printing is available. It is 400 EGP, free delivery with the Elite.",
                      "Printing is available. Your total is 400 EGP, free shipping on the Elite.",
                      "Printing is available. The price is 400 EGP, includes free delivery for the Elite.",
                      "طباعة الاسم متاحة. الإجمالي 400 جنيه" + AC + " والتوصيل مجاني مع الـ Elite.",
                      "طباعة الاسم متاحة. الإجمالي 400 جنيه" + AC + " توصيل ببلاش مع الـ Elite.",
                      "Tba3et el esm available. El total 400 EGP, delivery bbalash m3 el Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_delivery_in_its_own_clause_keeps_the_free_offer(self):
        """Only the clause with the free word is read for delivery; the 60 fails on its own here (the
        demo store's free delivery offer sets every fee to 0), the 400 stays the printing's."""
        found = prices("طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " ومجانية مع أي Elite" + AC + " والتوصيل 60 جنيه.")
        self.assertFalse(any("400" in w for w in found), found)

    def test_a_boot_word_that_does_not_join_the_extra_passes(self):
        for reply in ("Send me your shoe size and printing is 400 EGP.",
                      "Tell me your shoe size and name printing costs 400 EGP.",
                      "Pick any boot and printing is 400 EGP.",
                      "Every pair comes in a box and printing is 400 EGP.",
                      "Your boot costs 16,500 EGP plus printing at 400 EGP.",
                      "ابعتلي مقاس الجزمة والطباعة بـ 400 جنيه.",
                      "الجزمة بـ 16500 جنيه والطباعة بـ 400 جنيه.",
                      "Ab3atly maas el gazma w el tba3a b 400 EGP.",
                      "El gazma b 16500 EGP w el tba3a b 400 EGP.",
                      "Choose your boot and the printing costs 400 EGP extra.",
                      "Any boot can take printing for 400 EGP.",
                      "Each pair with name printing costs 400 EGP more.",
                      "Boot plus printing comes to 16,900 EGP.",
                      "Boot plus printing is 16,900 EGP and printing alone is 400 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])

    def test_the_surviving_reverts_fail(self):
        for reply in ("Printing is available. It is 400 EGP, free - Elite.",
                      "الجزمة بالطباعة بـ 400 جنيه.",
                      "The boot and printing is 400 EGP.",
                      "El gazma m3 el tba3a b 400 EGP.",
                      "El gazma w el tba3a b 400 EGP."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))


class RoundThreeGuards(unittest.TestCase):
    """Review pricectx round 3: the extra's own price before the join word still joins (finding 1), a
    delivery word after the boot keeps the free offer and وشحن or وتوصيل is delivery too (finding 2),
    and a Franco w before the boot word still opens the clause (finding 3)."""

    def setUp(self):
        clean_env(self)

    def test_a_boot_priced_at_the_extras_amount_before_the_join_fails(self):
        for reply in ("Boot at 400 EGP with printing.",
                      "Your boot is 400 EGP with printing.",
                      "The boot comes to 400 EGP including printing.",
                      "The pair is 400 EGP with name printing.",
                      "The boot is 400 EGP plus printing.",
                      "الجزمة بـ 400 جنيه مع الطباعة.",
                      "الجزمة بـ 400 جنيه بالطباعة.",
                      "الجزمة بـ 400 جنيه والطباعة.",
                      "El gazma b 400 EGP m3 el tba3a.",
                      "El gazma b 400 EGP ma3 el tba3a."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_a_boot_price_or_the_extra_named_first_still_passes(self):
        for reply in ("The boot is 16,500 EGP with printing at 400 EGP.",
                      "الجزمة بـ 16500 جنيه مع الطباعة بـ 400 جنيه.",
                      "The boot printing is 400 EGP with any name.",
                      "Boots get printing at 400 EGP with any name you want.",
                      "الجزمة الطباعة عليها بـ 400 جنيه مع اسمك.",
                      "The boot is 16,500 EGP, printing 400 EGP with your name.",
                      "Your boot can take name printing for 400 EGP plus delivery.",
                      "Every boot ships with a box and printing costs 400 EGP.",
                      "Any boot works with printing for 400 EGP.",
                      "اختار الجزمة اللي تعجبك مع طباعة اسمك بـ 400 جنيه.",
                      "Ekhtar el gazma elly te3gebak m3 tba3et esmak b 400 EGP.",
                      "Send me your boot size with the name you want and printing is 400 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])

    def test_delivery_after_the_boot_keeps_the_free_offer(self):
        for reply in ("Printing is available. It is 400 EGP, free with an Elite and free delivery too.",
                      "Printing is available. It is 400 EGP, free with any Elite and delivery is free as well.",
                      "Printing is available. It is 400 EGP, free with an Elite plus free shipping.",
                      "Printing is available. It costs 400 EGP, but it is free with an Elite and ships in 2 days.",
                      "Printing is available. It is 400 EGP, free with an Elite and cash on delivery works.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " ومجانية مع أي Elite والتوصيل مجاني كمان.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " ومجانية مع أي Elite والشحن علينا.",
                      "Tba3et el esm available. B 400 EGP, w free m3 ay Elite w el delivery bbalash.",
                      "Tba3et el esm available. B 400 EGP, w free m3 ay Elite w el sha7n 3alena."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])

    def test_free_delivery_as_the_boots_offer_fails(self):
        for reply in ("طباعة الاسم متاحة. الإجمالي 400 جنيه" + AC + " وشحن مجاني مع الـ Elite.",
                      "طباعة الاسم متاحة. الإجمالي 400 جنيه" + AC + " وتوصيل مجاني مع الـ Elite.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " وشحن مجاني مع الـ Elite.",
                      "طباعة الاسم متاحة. سعرها 400 جنيه" + AC + " فالتوصيل مجاني مع الـ Elite.",
                      "Printing is available. It is 400 EGP, with free delivery on the Elite.",
                      "Printing is available. It is 400 EGP, free home delivery with the Elite.",
                      "Printing is available. It is 400 EGP, free courier delivery with the Elite.",
                      "Printing is available. It is 400 EGP, delivery is free with the Elite.",
                      "Tba3et el esm available. B 400 EGP, tawseel bbalash m3 el Elite.",
                      "Tba3et el esm available. B 400 EGP, el sha7n free m3 el Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_the_opening_boot_word_after_a_franco_w_fails(self):
        for reply in ("Tba3et el esm available. W el gazma b 400 EGP, w free m3 ay Elite.",
                      "Tba3et el esm available. Wa el gazma b 400 EGP, w free m3 ay Elite.",
                      "W el gazma m3 el tba3a b 400 EGP.",
                      "Printing is available. Your boots are 400 EGP, free printing with an Elite.",
                      "Printing is available. \"The boot\" is 400 EGP, free with an Elite.",
                      "Printing is available. The cleats cost 400 EGP, free with an Elite.",
                      "طباعة الاسم متاحة. والجزمة بـ 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "طباعة الاسم متاحة. الكوتشي بـ 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "Printing is available. So the pair is 400 EGP, free with an Elite."):
            with self.subTest(reply=reply):
                self.assertTrue(any("400" in w for w in prices(reply)), prices(reply))

    def test_a_clause_that_does_not_open_with_a_boot_word_passes(self):
        for reply in ("Printing is available. Each boot is 400 EGP extra, free with an Elite.",
                      "Printing is available. \"Per pair\" it is 400 EGP, free with an Elite.",
                      "Printing is available. The boot size does not matter, it is 400 EGP, free with an Elite.",
                      "طباعة الاسم متاحة. على الجزمة بـ 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "طباعة الاسم متاحة. للجزمة الواحدة 400 جنيه" + AC + " ومجانية مع أي Elite.",
                      "Tba3et el esm available. 3al gazma b 400 EGP, w free m3 ay Elite.",
                      "Tba3et el esm available. Wait, it is 400 EGP, free m3 ay Elite."):
            with self.subTest(reply=reply):
                self.assertEqual(prices(reply), [])


if __name__ == "__main__":
    unittest.main()
