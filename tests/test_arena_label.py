"""The Arena replay labels (arena/label.py, new 2026-10-30): won, lost or unclear from the chat
itself (DECISIONS item 21), every why, and the price, question, negation, if, cancel and voice
note cases. A won sign counts only after a store price line. Made-up chats only."""
import unittest

from reflection import history as hist
from arena import label as lb

HOUR = 3600.0
T0 = 1_780_000_000.0


def chat(*steps, newest_gap=100 * HOUR):
    """A chat from (team?, text, media) steps one minute apart, and the import's newest time."""
    msgs = [hist.Message(T0 + 60 * n, team, text, media) for n, (team, text, media) in enumerate(steps)]
    return hist.Chat("whatsapp", "k", 1, msgs), (msgs[-1].at if msgs else T0) + newest_gap


def c(text, media=None):
    return (False, text, media)


def s(text, media=None):
    return (True, text, media)


PRICED = (c("بكام؟"), s("السعر 1450 جنيه"))  # the store gives a price first


def label(*steps, **kw):
    ch, newest = chat(*steps, **kw)
    return lb.label(ch, newest)


class Price(unittest.TestCase):
    def test_a_price_line(self):
        for text in ("1450 جنيه", "EGP 900", "السعر 1450", "shipping 60", "ملخص الطلب: جزمة مقاس 43",
                     "Order summary: 1 pair"):
            self.assertTrue(lb.gave_price(text), text)
        for text in ("أيوة متاح", "تحت أمرك", "", None):
            self.assertFalse(lb.gave_price(text), text)

    def test_a_won_sign_before_any_price_is_unclear(self):
        self.assertEqual(label(c("هاخده"), s("تمام")), (lb.UNCLEAR, lb.EARLY))
        self.assertEqual(label(c("عايزها"), s("تم تسجيل الطلب")), (lb.UNCLEAR, lb.EARLY))
        self.assertEqual(label(c("العنوان: 12 شارع التجربة"), s("تمام")), (lb.UNCLEAR, lb.EARLY))
        # a sign again after the price counts
        self.assertEqual(label(c("هاخده"), s("1450 جنيه"), c("تمام اكدلي")), (lb.WON, lb.CONFIRMED))

    def test_quiet_with_no_price_is_unclear_never_lost(self):
        self.assertEqual(label(c("السلام عليكم"), s("أهلا بيك، تحت أمرك")), (lb.UNCLEAR, lb.NO_PRICE))
        self.assertEqual(label(c("فيه مقاس 43"), s("أيوة متاح")), (lb.UNCLEAR, lb.NO_PRICE))
        self.assertEqual(label(c("بكام؟"), s("", "image")), (lb.UNCLEAR, lb.NO_PRICE))
        self.assertEqual(label(c("go ahead and tell me the price"), s("ثواني")), (lb.UNCLEAR, lb.NO_PRICE))

    def test_a_delivery_time_is_not_a_price(self):
        for text in ("الشحن بياخد 48 ساعة", "التوصيل خلال 24 ساعة", "shipping takes 48 hours", "الشحن 120 ساعة",
                     "التوصيل خلال 10 ايام", "delivery in 14 days", "الشحن خلال 48hrs"):
            self.assertFalse(lb.gave_price(text), text)
        for text in ("الشحن 60 جنيه", "الشحن 60", "shipping 60, takes 48 hours", "السعر 1450.50"):
            self.assertTrue(lb.gave_price(text), text)
        self.assertEqual(label(c("بتوصلوا امتى؟"), s("الشحن بياخد 48 ساعة")), (lb.UNCLEAR, lb.NO_PRICE))
        self.assertEqual(label(c("بتوصلوا امتى؟"), s("shipping takes 48 hours")), (lb.UNCLEAR, lb.NO_PRICE))

    def test_a_range_a_date_or_a_clock_time_is_not_a_price(self):
        for text in ("الشحن من 24 ل 48 ساعة", "التوصيل خلال 48 الى 72 ساعة", "الشحن بياخد من 48 لـ 72 ساعه",
                     "shipping within 48-72 hours", "delivery 48 to 72 hours", "الشحن 24/48 ساعة", "الشحن يوم 30/10",
                     "التوصيل يوم 15 الشهر الجاي", "الشحن من 10 الصبح", "delivery 10 am", "الشحن 48 س", "الشحن 10:30",
                     "delivery 10 pm", "الشحن الساعة 10", "shipping within 48\u201372 hours", "الشحن 48 / 72 ساعة",
                     "الشحن 48 او 72 ساعة", "الشحن 30/10"):
            self.assertFalse(lb.gave_price(text), text)
        self.assertEqual(label(c("بتوصلوا امتى؟"), s("الشحن من 24 ل 48 ساعة")), (lb.UNCLEAR, lb.NO_PRICE))

    def test_a_day_name_or_a_date_after_a_price_keeps_it_a_price(self):
        for text in ("السعر 850 يوم الخميس", "الشحن 50 يوم الخميس", "السعر 1450 يوم الجمعة", "shipping 60 on friday",
                     "السعر 900 يوم 30", "priced at 1450", "الشحن 50 او 60", "السعر 1450/1500", "السعر 850 يوم friday"):
            self.assertTrue(lb.gave_price(text), text)


class Won(unittest.TestCase):
    def test_an_address_in_arabic_franco_and_english(self):
        for text in ("العنوان: 12 شارع التجربة", "3enwany share3 el nasr", "My address is 7 Test Street",
                     "عمارة 5 جنب صيدلية النور"):
            self.assertEqual(label(c("عايز الجزمة"), s("تمام، السعر 1450 جنيه"), c(text), s("تم")),
                             (lb.WON, lb.ADDRESS), text)

    def test_a_confirm_in_arabic_franco_and_english(self):
        for text in ("تمام أكدلي", "خلاص هاخدهم", "اطلبيها", "tamam akkedly", "Great, I'll take it", "OK confirm it"):
            self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), c(text)), (lb.WON, lb.CONFIRMED), text)

    def test_the_store_writing_the_order_is_placed(self):
        for text in ("تمام، تم تسجيل الطلب", "Done, your order is confirmed", "el order etsagel"):
            self.assertEqual(label(*PRICED, c("عايزها"), s(text)), (lb.WON, lb.STORE_CONFIRMED), text)
        # a price in the placed line itself counts
        self.assertEqual(label(c("عايزها"), s("تم تسجيل الطلب، الإجمالي 1510 جنيه")), (lb.WON, lb.STORE_CONFIRMED))

    def test_a_question_or_a_no_before_it_is_not_a_confirm(self):
        for text in ("أكدلي؟", "can I go ahead?", "مش هاخدهم", "I won't take it", "la2 msh akkedly",
                     "اكدلي الطلب؟", "لا مش دلوقتي خالص اكدلي بعدين"):
            self.assertNotEqual(label(*PRICED, c(text), s("تحت أمرك"))[0], lb.WON, text)

    def test_go_ahead_is_not_a_confirm(self):
        for text in ("OK go ahead", "go ahead and tell me the price"):
            self.assertEqual(label(*PRICED, c(text), s("تمام")), (lb.LOST, lb.QUIET), text)

    def test_an_if_after_the_confirm_is_not_a_confirm(self):
        for text in ("هاخده لو نزل السعر", "هاخده بس لو فيه خصم", "اكدلي لو المقاس 43 موجود", "I'll take it if it fits",
                     "akkedly law fih 43"):
            self.assertEqual(label(*PRICED, c(text), s("مفيش خصم")), (lb.LOST, lb.QUIET), text)

    def test_an_address_question_is_not_an_address(self):
        for text in ("بتوصلوا شارع التحرير؟", "بتوصلوا شارع التحرير الدقي", "انا ساكن في شارع التحرير الشحن بكام",
                     "انتو جنب المسجد ولا فين", "ينفع توصلوا شارع التحرير"):
            self.assertEqual(label(*PRICED, c(text), s("أيوة")), (lb.LOST, lb.QUIET), text)
        # a question with an address number counts
        self.assertEqual(label(*PRICED, c("ممكن توصلوا عمارة 12؟"), s("أيوة")), (lb.WON, lb.ADDRESS))

    def test_the_store_placing_later_or_asking_is_not_placed(self):
        for text in ("your order is confirmed once you send the address", "تم تسجيل الطلب لما تبعت العنوان",
                     "تم تسجيل الطلب بمجرد التحويل", "order confirmed if you pay first", "تم تسجيل الطلب؟"):
            self.assertEqual(label(*PRICED, c("عايز الجزمة"), s(text)), (lb.LOST, lb.QUIET), text)
        # "after" with no you or we after it still counts
        self.assertEqual(label(*PRICED, c("عايز الجزمة"), s("order confirmed, arrives after 2 days")),
                         (lb.WON, lb.STORE_CONFIRMED))


class LostAndUnclear(unittest.TestCase):
    def test_quiet_after_the_price_is_lost(self):
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه")), (lb.LOST, lb.QUIET))
        self.assertEqual(label(*PRICED, c("فيه صور؟"), s("", "image")), (lb.LOST, lb.QUIET))  # a photo is an answer
        self.assertEqual(label(c("فيه مقاس 43؟"), s("متاح، الشحن 60"), c("طيب"), s("تحت أمرك")), (lb.LOST, lb.QUIET))

    def test_still_open_within_the_quiet_hours(self):
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), newest_gap=47 * HOUR), (lb.UNCLEAR, lb.OPEN))
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), newest_gap=48 * HOUR), (lb.LOST, lb.QUIET))

    def test_a_voice_note_last_is_unclear_never_lost(self):
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), c("", "audio"), s("ثواني")), (lb.UNCLEAR, lb.VOICE))

    def test_a_voice_note_after_the_won_sign_is_unclear(self):
        self.assertEqual(label(*PRICED, c("تمام اكدلي"), s("تمام"), c("", "audio")), (lb.UNCLEAR, lb.VOICE_AFTER))
        self.assertEqual(label(c("تمام اكدلي"), s("تمام"), c("", "audio")), (lb.UNCLEAR, lb.EARLY))  # no price

    def test_a_photo_last_with_an_answer_is_lost(self):
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), c("", "image"), s("ده متاح")), (lb.LOST, lb.QUIET))

    def test_a_cancel_after_the_yes_is_unclear(self):
        for text in ("معلش ألغي الطلب", "cancel it please", "please cancel it", "msh 3ayzo", "لا خلاص مش عايز",
                     "خلاص مش عاوزه", "la2 khalas msh 3ayez"):
            self.assertEqual(label(*PRICED, c("اطلبهالي"), s("تم تسجيل الطلب"), c(text), s("تم")),
                             (lb.UNCLEAR, lb.CANCELLED), text)
        self.assertEqual(label(*PRICED, c("I'll take it"), s("ok"), c("please cancel it")), (lb.UNCLEAR, lb.CANCELLED))

    def test_a_store_cancel_word_does_not_cancel(self):
        self.assertEqual(label(*PRICED, c("اطلبهالي"), s("تم تسجيل الطلب. الغاء الطلب متاح خلال يوم")),
                         (lb.WON, lb.CONFIRMED))

    def test_no_answer_no_reply_no_customer(self):
        self.assertEqual(label(c("بكام؟"), s("1450 جنيه"), c("طب في خصم؟")), (lb.UNCLEAR, lb.UNANSWERED))
        self.assertEqual(label(c("السلام عليكم"), c("بكام؟")), (lb.UNCLEAR, lb.NO_REPLY))
        self.assertEqual(label(s("أهلا")), (lb.UNCLEAR, lb.NO_CUSTOMER))


if __name__ == "__main__":
    unittest.main()
