"""Part D of the losses work: the fact check failed a reply that gave the boot its own price, then the
name printing by its full title with "its price" and its own amount ("400 is the price of Beyond the
Limits Name Printing, and its clause does not name it", Arena run 20261104T120239). The extra's amount
may now follow the rest of its title and one own price word; every shape that joins the extra to the
boot still fails. Made-up text against the demo store data."""
import unittest

from arena import factcheck
from tests.fake_model import clean_env


def checks(reply, customer=""):
    return [f["check"] for f in factcheck.check(reply, customer)]


class ExtraByItsFullTitle(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_the_boot_price_then_the_extra_by_title_and_its_price_passes(self):
        for reply in ("Nike Mercurial Vapor 17 فئة Elite مقاس 42 سعره 16500 جنيه مع طباعة Beyond the Limits Name"
                      " Printing سعرها 400 جنيه بالنص Sara 7.",
                      "الـ Vapor 17 Elite بـ 16,500 جنيه مع الطباعة سعرها 400 جنيه",
                      "The Vapor 17 Elite is 16,500 EGP with Beyond the Limits Name Printing 400 EGP.",
                      "The Vapor 17 Elite is 16,500 EGP with Name Printing its price is 400 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(checks(reply), [])

    def test_the_red_team_shapes_still_fail(self):
        fee = next(str(int(float(z["fee"]))) for z in factcheck.store.delivery()["zones"] if "fee" in z)
        for reply in ("The Vapor 17 Elite with printing is 400 EGP.",
                      "The Vapor 17 Elite is 16,500 EGP with printing is 400 EGP.",
                      "The Vapor 17 Elite is 16,500 EGP with Beyond the Limits Name Printing is 400 EGP.",
                      "Nike Mercurial Vapor 17 فئة Elite مع طباعة Beyond the Limits Name Printing سعرها 400 جنيه",
                      f"Nike Mercurial Vapor 17 فئة Elite سعره {fee} جنيه مع طباعة سعرها 400 جنيه",
                      "The Vapor 17 Elite was 16,500 EGP and with printing its price 400 EGP.",
                      "The Vapor 17 Elite is 400 EGP with printing its price 400 EGP.",
                      "With printing the Vapor 17 Elite is 400 EGP.",
                      "The Vapor 17 Elite is 400 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(checks(reply), ["price"])


if __name__ == "__main__":
    unittest.main()
