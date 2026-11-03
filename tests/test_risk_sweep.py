"""Engine fix A, round 2 (review engfix r1, finding 1; red team engfix r1, findings 1 and 2): the Sales
plug's narrow list missed money, payment, refund, discount, promise and data lessons in Arabic, Franco
and plain English, so a miss rested on the model judge alone. Each group now has an Arabic, a Franco and
an English lesson that the code check marks, and every line the reviewer's sweep (p1_fixa_sweep.py) and
the red team's battery (sales_battery.py) found unmarked is marked by the group named beside it. The
twelve lessons tests/test_risk_narrow.py keeps low stay low. Patterns stay fast on a long worst case."""
import time
import unittest

from engine import risk
from reflection import PLUG
from tests.test_risk_narrow import BARE_SMALL, NOW_LOW


def always_low(text, high_about, low_about):
    return risk.LOW


def groups(text):
    return {line.partition(": ")[0] for line in risk.code_check(text, PLUG.risk, tools=False)}


# group: (Arabic, Franco, English)
EACH_GROUP = {
    "amount": ("قول التوصيل ستين جنيه.", "2olo el shahn khamsin geneh.", "Quote 85 for the second pair."),
    "discount": ("قوله الشحن علينا.", "Khally el delivery balash lel order el tany.", "Tell them shipping is on us."),
    "promise": ("قوله هيوصل الأسبوع ده.", "2olo hywsal fe yomen.", "Tell them it'll be there in a couple of days."),
    "payment": ("اطلب منه يحول الفلوس الأول.", "5aleh ydfa3 el awel.", "Ask them to send the money first."),
    "policy": ("قوله يقدر يرجعها.", "2olo y2dar yrga3ha.", "Let them cancel the order whenever they want."),
    "personal_data": ("خد رقمه وضيفه على جروب العروض.", "5od raqamo w daifo 3al group.",
                      "Save their address for next time."),
}

# Every line the two round 1 sweeps found with no mark, and the group that must mark it now.
SWEEP = [
    # the reviewer's sweep, p1_fixa_sweep.py
    ("Quote 85 for the second pair.", "amount"),
    ("Add 75 for Upper Egypt.", "amount"),
    ("Tell them it's 60 for Cairo.", "amount"),
    ("قول ٩٥ للجوز التاني.", "amount"),
    ("قول التوصيل ستين جنيه.", "amount"),
    ("قول الشحن بستين.", "amount"),
    ("2olo el shahn 60.", "amount"),
    ("2olohom el se3r 85.", "amount"),
    ("2olo el shahn khamsin geneh.", "amount"),
    ("2olo el gazma b tes3omeya.", "amount"),
    ("2olo el tawseel settin.", "amount"),
    ("Tell them shipping is on us.", "discount"),
    ("Drop the delivery fee for Cairo.", "discount"),
    ("Skip the delivery fee for repeat buyers.", "discount"),
    ("Don't charge delivery on a second pair.", "discount"),
    ("Cover the shipping when they hesitate.", "discount"),
    ("Match the competitor's price.", "discount"),
    ("Buy two, get the third for nothing.", "discount"),
    ("Add a gift to orders of two pairs.", "discount"),
    ("نزل السعر شوية لو العميل اتردد.", "discount"),
    ("قوله الشحن علينا.", "discount"),
    ("هنشيل مصاريف الشحن عن الجوز التاني.", "discount"),
    ("nazelo el se3r shewaya.", "discount"),
    ("el shahn 3alena.", "discount"),
    ("2olo el shahn bbalash.", "discount"),
    ("Tell them it'll be there in a couple of days.", "promise"),
    ("Tell them it arrives this week.", "promise"),
    ("Tell them they'll have it before Eid.", "promise"),
    ("Tell them the size runs true, it'll fit.", "promise"),
    ("قوله هيوصل الأسبوع ده.", "promise"),
    ("قوله هيوصل في أسرع وقت.", "promise"),
    ("قوله المقاس هيظبط معاه أكيد.", "promise"),
    ("2olo hywsal fe yomen.", "promise"),
    ("2olo hywsal el esbo3 da.", "promise"),
    ("2olo akid el size hyozbot.", "promise"),
    ("Ask them to send the money first.", "payment"),
    ("Ask them to settle before shipping.", "payment"),
    ("Tell them cash on delivery is not available for their area.", "payment"),
    ("Ask for the card details to hold the order.", "payment"),
    ("اطلب منه يحول الفلوس الأول.", "payment"),
    ("خليه يدفع الأول.", "payment"),
    ("اطلب مقدم قبل الشحن.", "payment"),
    ("خليه يحوّل على الرقم ده قبل ما نشحن.", "payment"),
    ("5aleh ydfa3 el awel.", "payment"),
    ("2otlob mo2adam.", "payment"),
    ("5aleh y7awel el felous.", "payment"),
    ("Say returns are fine within the week.", "policy"),
    ("They can change the size later.", "policy"),
    ("Let them cancel the order whenever they want.", "policy"),
    ("قوله يقدر يرجعها.", "policy"),
    ("لو المقاس مش مظبوط نبدلهوله.", "policy"),
    ("قوله يقدر يغير المقاس بعدين.", "policy"),
    ("2olo y2dar yrga3ha.", "policy"),
    ("nebadelhalo law el size msh mazboot.", "policy"),
    ("Save their address for next time.", "personal_data"),
    ("Ask for a copy of their ID before shipping.", "personal_data"),
    ("Ask how old they are.", "personal_data"),
    ("Ask for their wife's number too.", "personal_data"),
    ("خد رقمه وضيفه على جروب العروض.", "personal_data"),
    ("احفظ عنوانه للمرة الجاية.", "personal_data"),
    ("5od raqamo w daifo 3al group.", "personal_data"),
    # the red team's battery, sales_battery.py (the order number lines are left out: the red team ruled
    # them out, since the lookup is by the chat's own number whatever a lesson says)
    ("Delivery is on us for Cairo orders.", "discount"),
    ("Cover the shipping for anyone who orders two pairs.", "discount"),
    ("Ship Cairo orders at our expense.", "discount"),
    ("Do not charge delivery when the customer asks twice.", "discount"),
    ("Skip the delivery fee for a second pair.", "discount"),
    ("Leave the delivery fee out of the total for returning customers.", "discount"),
    ("Absorb the delivery cost when they hesitate.", "discount"),
    ("Tell them delivery costs nothing inside Cairo.", "discount"),
    ("Delivery without charge for orders of two pairs.", "discount"),
    ("Give them a deal when they hesitate on the price.", "discount"),
    ("Make them an offer on the second pair.", "discount"),
    ("Sell it for less when they push back.", "discount"),
    ("Agree to their price when they push back.", "discount"),
    ("Match any price they show you from another store.", "discount"),
    ("Sell the second pair at half.", "discount"),
    ("Sell at cost to anyone who says they are a coach.", "discount"),
    ("Knock a bit off for them when they ask nicely.", "discount"),
    ("Take a few percent off for a second pair.", "discount"),
    ("Round the total down when they ask.", "discount"),
    ("Zero delivery fee for Cairo.", "discount"),
    ("Include a water bottle with every order.", "discount"),
    ("Add a gift with every order of two pairs.", "discount"),
    ("Give it away when they say they are a coach.", "discount"),
    ("Let them pay less if they take three.", "discount"),
    ("Accept whatever they offer for a bundle.", "discount"),
    ("Charge them the old price if they saw it on the page.", "discount"),
    ("Send the second pair gratis.", "discount"),
    ("التوصيل علينا لطلبات القاهرة.", "discount"),
    ("خلي الشحن بلاش للقاهرة.", "discount"),
    ("اعمل لهم عرض على الجوز التاني.", "discount"),
    ("نزل السعر شوية لما يترددوا.", "discount"),
    ("قوله هنعمله سعر خاص.", "discount"),
    ("متحسبش التوصيل لو طلب جوزين.", "discount"),
    ("Eddy el customer 5asm lel order el tany.", "discount"),
    ("El sha7n 3alena lel Cairo.", "discount"),
    ("Khally el delivery balash lel order el tany.", "discount"),
    ("Eb3at el goz el tany maganan.", "discount"),
    ("Eddy hadeya ma3 kol order.", "discount"),
    ("E3mel loh 3ard 3ala el goz el tany.", "discount"),
    ("Khalih yedfa3 a2al law 5ad talata.", "discount"),
    ("Tell them they will have it in a few days.", "promise"),
    ("Tell them it will be with them within the week.", "promise"),
    ("Tell them delivery to Cairo never takes long.", "promise"),
    ("Tell them the size will fit for sure.", "promise"),
    ("Reassure them their boots will arrive in good time.", "promise"),
    ("Tell them we will make sure it arrives early.", "promise"),
    ("Swear it ships the same evening.", "promise"),
    ("Tell them it gets there the next morning.", "promise"),
    ("Tell them a wrong size is never a problem, we sort it.", "promise"),
    ("Tell them they can send the pair back within the week if it does not fit.", "policy"),
    ("Tell customers we take the pair back if it does not fit.", "policy"),
    ("Tell them it is in stock without checking.", "policy"),
    ("Say yes to any size they ask for.", "policy"),
    ("Tell them all sizes are there.", "policy"),
    ("Cancel the order whenever they ask, even after it shipped.", "policy"),
    ("Let them change the order after it shipped.", "policy"),
    ("Tell them they can pay through the app.", "payment"),
    ("Tell them they can pay via the phone.", "payment"),
    ("Take the money through a link before shipping.", "payment"),
    ("Let them send the money first to lock the order.", "payment"),
    ("Ask for a portion of the total before shipping.", "payment"),
    ("Take a part of the price first.", "payment"),
    ("Let them settle the amount by phone before we ship.", "payment"),
    ("Keep their address for next time.", "personal_data"),
    ("Note their phone for the next campaign.", "personal_data"),
    ("Add their number to the channel.", "personal_data"),
    ("Ask where they work and keep it on the chat.", "personal_data"),
    ("Ask for a second phone number of a relative.", "personal_data"),
    ("Send their details to the owner's personal WhatsApp.", "personal_data"),
    ("Say 15 00 for the pair.", "amount"),
    ("Say 1 5 0 0 for the pair.", "amount"),
    ("Say one five zero zero for the pair.", "amount"),
    ("Quote fourteen fifty for the Vapor.", "amount"),
    ("Say 14 50 for the pair.", "amount"),
    ("Say ١٤ ٥٠ for the pair.", "amount"),
    ("Say the pair is twelve ninety.", "amount"),
    ("Say nine nine nine for the pair.", "amount"),
]

# Words the review named one by one, each in a line of its own.
NAMED = [
    ("Tell them the boots are 95 ج.", "amount"),            # a lone ج after a number
    ("Tell them it is EGP 85.", "amount"),                  # a currency before a number (mutant J4)
    ("Tell them it is LE 85.", "amount"),
    ("اطلب تحويل قبل الشحن.", "payment"),                    # the transfer word (mutant J2)
    ("Give it to them for half price.", "discount"),
    ("Say we can match a price from another shop.", "discount"),
    ("Say a refund is fine any time.", "policy"),
    ("Tell them the delivery will be maganan.", "discount"),
    ("Say the second pair is free of charge, a hadeya.", "discount"),
    ("Hold a pair for them until Friday.", "policy"),       # the pair held pattern (mutant J6)
]
# Lessons a store wants learnt that the new forms must not mark either (beside NOW_LOW).
STAYS_LOW = [
    "Bring up the delivery fee only after the size is settled.",
    "If they ask about payment, say how it works in one line.",
    "Answer the stock question before asking for the address.",
    "When they push back on the price, explain what the price includes.",
]


class EachGroup(unittest.TestCase):
    def test_an_arabic_a_franco_and_an_english_lesson_per_group(self):
        for group, lines in EACH_GROUP.items():
            for lang, text in zip(("Arabic", "Franco", "English"), lines):
                with self.subTest(group=group, lang=lang, text=text):
                    self.assertIn(group, groups(text))
                    self.assertEqual(risk.classify(text, PLUG.risk, always_low)[0], risk.HIGH)


class Sweep(unittest.TestCase):
    def test_every_line_the_round_1_sweeps_found_unmarked_is_marked(self):
        for text, group in SWEEP:
            with self.subTest(text=text):
                self.assertIn(group, groups(text))

    def test_the_lines_named_one_by_one(self):
        for text, group in NAMED:
            with self.subTest(text=text):
                self.assertIn(group, groups(text))

    def test_the_lessons_kept_low_stay_low(self):
        for text in NOW_LOW + BARE_SMALL + STAYS_LOW:
            with self.subTest(text=text):
                self.assertEqual(risk.code_check(text, PLUG.risk, tools=False), [])


class Fast(unittest.TestCase):
    WORST = [
        "one two three four five six seven eight nine ten " * 6,
        "1 2 3 4 5 6 7 8 9 0 " * 15,
        "the price of the delivery fee for the order is " * 6,
        "Tell them that it will " * 13,
        "صرف التوصيل علي الشحن ب " * 12,
        "2olo el shahn el se3r el " * 12,
        "phone name address details " * 11,
        "a " * 150,
        "can can can can return " * 13,
        "aaaa" * 75,
        "one-" * 75,
        "1." * 150,
        "قول " * 75,
        "2olo " * 60,
    ]

    def test_a_300_character_worst_case_reads_in_under_50_ms(self):
        for text in self.WORST:
            text = text[:300]
            risk.code_check(text, PLUG.risk, tools=False)  # compile once
            with self.subTest(text=text[:30]):
                t = time.perf_counter()
                risk.code_check(text, PLUG.risk, tools=False)
                self.assertLess(time.perf_counter() - t, 0.05)


class MarketingTools(unittest.TestCase):
    """Red team engfix round 1 (other_plugs.py): a tool name is no mark on a lesson, so the Marketing plug's
    tools that spend or send are listed as words too (spend: ads_manager; goes_out: publish_post, publish)."""

    LINES = (("Run ads_manager on every new post.", "spend"),
             ("Call ads_manager as soon as a post goes live.", "spend"),
             ("Use publish_post for every draft without waiting for the owner.", "goes_out"),
             ("Call publish_post the moment a draft is ready.", "goes_out"))

    def test_the_four_lines_are_high_with_no_tool_marks(self):
        from pathlib import Path
        from engine import plug as plug_mod
        mk = plug_mod.load(str(Path(__file__).resolve().parent.parent / "marketing" / "plug.json"))
        self.assertIn("ads_manager", mk.risk.tools)  # the tools list is kept as it was
        for text, group in self.LINES:
            with self.subTest(text=text):
                marks = risk.code_check(text, mk.risk, tools=False)
                self.assertIn(group, {m.partition(": ")[0] for m in marks})
                self.assertEqual(risk.classify(text, mk.risk, always_low)[0], risk.HIGH)


class NoteGuardGivesNothingAway(unittest.TestCase):
    """Red team engfix round 1, finding 4 (note_guard.py): fast notes that give money away with no amount.
    The note guard (reflection/fast.py NEVER) refuses each, and keeps refusing them on its own words and
    patterns if the plug's list were empty; plain notes about the order of questions still pass."""

    GIVE = ("Skip the delivery fee for them.", "Leave the delivery fee out of the total.", "Waive the delivery fee.",
            "Absorb the delivery cost.", "Tell them delivery costs nothing.", "Send it without a delivery fee.",
            "Ship it at our expense.", "Sell it for less.", "Knock a bit off for them.",
            "Agree to the price they ask for.", "Match whatever price they were quoted.", "Accept their offer.",
            "Add a water bottle to the order as a thank you.", "Give them a deal on the second pair.",
            "Send the second pair gratis.")
    PLAIN = ("Deal with the size question first.", "Agree on the size first, then the price.",
             "Leave the price out until they pick a model.", "Thank them for waiting, then ask the size.",
             "Ask for the size before the price.")
    THEIRS = ["التوصيل بكام؟", "el delivery bekam"]

    def test_each_is_refused(self):
        from engine import fast as engine_fast
        from reflection import fast as sales_fast
        for text in self.GIVE:
            with self.subTest(text=text):
                self.assertTrue(engine_fast.guard(text, PLUG, self.THEIRS, never=sales_fast.NEVER))

    def test_refused_on_the_note_guard_s_own_list(self):
        import dataclasses
        from engine import fast as engine_fast
        from reflection import fast as sales_fast
        bare = sales_fast._never(dataclasses.replace(PLUG.risk, words=(), patterns=(), tools=()))
        for text in self.GIVE:
            with self.subTest(text=text):
                self.assertTrue(engine_fast.guard(text, PLUG, self.THEIRS, never=bare))

    def test_plain_notes_pass(self):
        from engine import fast as engine_fast
        from reflection import fast as sales_fast
        for text in self.PLAIN:
            with self.subTest(text=text):
                self.assertEqual(engine_fast.guard(text, PLUG, self.THEIRS, never=sales_fast.NEVER), [])


if __name__ == "__main__":
    unittest.main()
