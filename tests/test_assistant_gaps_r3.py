"""Round 3 fixes to the assistant's gaps (new, 2026-11-01): a display name of two or more name words
counts whatever the address, a sign off cuts only a tail that reads like a signature, a signature is
masked word by word (name-like words only, also above a long last line or in a tail too long to
cut), and after with or مع only a listed name or one of the day's names is masked, lower case too.
Each rule both ways: the name masked and the content kept."""
import unittest
from unittest import mock

from assistant import arena, simday

USER = "mona.saleh@corp.example"
KARIM = "karim.tawfik@corp.example"
LONG = "this line is long enough to be passed over by the walk"


def body_of(body, frm=KARIM, **kw):
    e = {"type": "item", "id": "x1", "at": "10:00", "kind": "email", "from": frm, "to": USER,
         "subject": "Re: deck", "body": body, "hidden": {"urgent": False}}
    e.update(kw)
    day = simday.build_day(7, user=USER)
    day["events"] = [e]
    return arena.clean_day(day)["events"][0]


class DisplayName(unittest.TestCase):
    def test_a_full_name_from_a_service_or_shared_address_is_masked(self):
        for frm, name, body in (
                ("comments-noreply@docs.google.com", "Bahaa Shalaby (Google Docs)", "Bahaa Shalaby left a comment."),
                ("notifications@calendly.com", "Bahaa Shalaby via Calendly", "New event: Bahaa Shalaby, 30 min."),
                ("assistant@northwind.example", "Nadine Fawzy", "Nadine Fawzy asked to move the call."),
                ("info@northwind.example", "بهاء شلبي", "بهاء شلبي عايز يأجل الاجتماع.")):
            row = body_of(body, frm=frm, from_name=name)
            for part in name.split()[:2]:
                self.assertNotIn(part, row["body"] + row["from_name"], name)

    def test_one_word_takes_no_initials(self):
        self.assertEqual(arena._display_name("Qorvane", "q.ops@x.example"), "")
        self.assertEqual(arena._display_name("Qorvane", "qo@x.example"), "")
        self.assertEqual(arena._display_name("Qorvane", "qorvane.ops@x.example"), "Qorvane")


class SignOffCut(unittest.TestCase):
    def test_an_ask_after_a_sign_off_is_kept_with_no_question_mark(self):
        out = body_of("Hi Mona,\nThanks!\nPlease send the signed contract before Sunday noon.\nKarim")["body"]
        self.assertIn("\nThanks!\nPlease send the signed contract before Sunday noon.\n", out)
        self.assertNotIn("Karim", out)
        out = body_of("صباح الخير يا منى\nشكرا\nابعتيلي العقد قبل الحد الضهر\nكريم")["body"]
        self.assertIn("\nشكرا\nابعتيلي العقد قبل الحد الضهر\n", out)
        self.assertNotIn("كريم", out)

    def test_the_first_tail_line_has_at_most_three_words(self):
        text = "Thanks,\nship the blue ones\nZorvex"
        self.assertEqual(arena._sign_off_cut(text), text)
        self.assertEqual(arena._sign_off_cut("Regards,\nZorvex Qwilan Fahmy\nhead of sales"), "Regards,\n[name]")

    def test_every_tail_line_reads_like_a_signature(self):
        for tail in ("Zorvex\ncall me back.", "Zorvex\nwe go with the plan then",
                     "Zorvex\nextraordinarily comprehensive documentation attached", "Zorvex\nready by noon?"):
            self.assertEqual(arena._sign_off_cut("Thanks,\n" + tail), "Thanks,\n" + tail, tail)
        self.assertEqual(arena._sign_off_cut("Thanks,\nZorvex\nwe go with the plan"), "Thanks,\n[name]")
        self.assertEqual(arena._sign_off_cut("Thanks,\nZorvex\n" + "x" * 40), "Thanks,\n[name]")

    def test_at_most_four_tail_lines(self):
        self.assertEqual(arena._sign_off_cut("Thanks,\na\nb\nc\nd"), "Thanks,\n[name]")
        self.assertEqual(arena._sign_off_cut("Thanks,\na\nb\nc\nd\ne"), "Thanks,\na\nb\nc\nd\ne")


class Signature(unittest.TestCase):
    def test_an_arabic_mail_with_no_punctuation_keeps_every_word_but_the_name(self):
        body = "صباح الخير يا منى\nالاجتماع اتأجل لبكرة\nابعتيلي التقرير قبل الاجتماع"
        self.assertEqual(body_of(body)["body"], body.replace("منى", "[name]"))

    def test_only_name_like_words_are_masked(self):
        self.assertEqual(arena._signature("Got it.\nZorvex Qwilan\nhead of sales, Northwind"),
                         "Got it.\n[name] [name]\nhead of sales, [name]")
        self.assertEqual(arena._signature("ok.\nseif\nmanager"), "ok.\n[name]\nmanager")
        self.assertEqual(arena._signature("ok.\nzorvex\nmanager"), "ok.\nzorvex\nmanager")
        self.assertEqual(arena._signature("ok.\nzorvex\nmanager", frozenset({"zorvex"})), "ok.\n[name]\nmanager")

    def test_arabic_words_are_masked_only_in_a_name_line(self):
        self.assertEqual(arena._signature("تمام.\nبهاء شلبي\nمدير المبيعات"), "تمام.\n[name] [name]\n[name] [name]")
        self.assertEqual(arena._signature("تمام.\nكريم\nابعتلي الملف"), "تمام.\n[name]\nابعتلي الملف")
        self.assertEqual(arena._signature("تمام.\nالاجتماع اتأجل"), "تمام.\nالاجتماع اتأجل")
        self.assertEqual(arena._signature("تمام.\nاسبوع اللي فات"), "تمام.\nاسبوع اللي فات")
        self.assertTrue(arena._arabic_name_line(["مدير", "المبيعات"]))
        self.assertFalse(arena._arabic_name_line(["اسبوع", "الا"]))  # ال with one letter after is no family name
        self.assertFalse(arena._arabic_name_line(["حجز", "الطلب"]))  # a common word with ال is no family name

    def test_a_name_above_a_long_last_line_is_masked(self):
        for last in ("15 El Nasr Road, Nasr City, Cairo 11371",
                     "This email is confidential and intended only for the addressee."):
            out = body_of("see attached\nZorvex Qwilan\nCEO, Northwind\n" + last, frm="ops@corp.example")["body"]
            self.assertNotIn("Zorvex", out)
            self.assertNotIn("Qwilan", out)
        out = body_of("see attached\nZorvex Qwilan\n" + LONG)["body"]
        self.assertTrue(out.endswith("\n[name] [name]\n" + LONG), out)

    def test_at_most_three_long_lines_are_passed_over(self):
        self.assertEqual(arena._signature("Hi\nQuick Update\n" + "\n".join([LONG] * 3)),
                         "Hi\n[name] [name]\n" + "\n".join([LONG] * 3))
        text = "Hi\nQuick Update\n" + "\n".join([LONG] * 4)
        self.assertEqual(arena._signature(text), text)
        self.assertEqual(arena._signature("Hi\nQuick Update\n" + LONG + "\nCairo"),
                         "Hi\nQuick Update\n" + LONG + "\n[name]")  # passed over only at the very end
        text = "Hi\nQuick Update\ncan you look at the numbers before the call tomorrow"
        self.assertEqual(arena._signature(text + "?"), text + "?")

    def test_a_tail_too_long_to_cut_is_masked_up_to_its_sign_off(self):
        tail = "Zorvex Qwilan\nChief Officer\nNorthwind Trading\nTahrir Street\nCairo"
        for body in ("ok thanks\nBest regards,\n" + tail, "Thanks,\n" + tail):
            out = body_of(body, frm="ops@corp.example")["body"]
            self.assertNotIn("Zorvex", out)
            self.assertNotIn("Qwilan", out)
            self.assertEqual(out.count("\n"), body.count("\n"))  # not cut: each line masked word by word
        self.assertEqual(arena._signature("ok\nThanks,\nzorvex\none\ntwo\nthree\nfour", frozenset({"zorvex"})),
                         "ok\nThanks,\n[name]\none\ntwo\nthree\nfour")
        self.assertEqual(arena._signature("ok\nfine\nzorvex\none\ntwo\nthree\nfour", frozenset({"zorvex"})),
                         "ok\nfine\nzorvex\none\ntwo\nthree\nfour")


class WithAndNames(unittest.TestCase):
    def test_ordinary_words_after_with_or_ma_stay(self):
        for t in ("Call with Marketing at 3.", "Please go ahead with Option B.", "We meet with Google Cloud on Sunday.",
                  "Sync with Finance and Legal tomorrow.", "اجتماع مع فريق المبيعات بكرة", "مع السلامة"):
            self.assertEqual(arena._after_names(t), t, t)

    def test_a_known_name_after_with_ma_and_and_is_masked_lower_case_too(self):
        self.assertEqual(arena._after_names("Sync with Mark today"), "Sync with [name] today")
        self.assertEqual(arena._after_names("met with amal and noor today"), "met with [name] and [name] today")
        self.assertEqual(arena._after_names("اتكلمت مع امل امبارح"), "اتكلمت مع [name] امبارح")
        self.assertEqual(arena._after_names("met with [name] and seif"), "met with [name] and [name]")

    def test_one_of_the_day_s_names_after_with_is_masked(self):
        self.assertEqual(arena._after_names("met with zorvex today"), "met with zorvex today")
        self.assertEqual(arena._after_names("met with zorvex today", ("Zorvex Qadri",)), "met with [name] today")
        self.assertNotIn("zorvex", body_of("met with zorvex today", frm="zorvex@x.example")["body"])

    def test_every_text_gets_the_day_s_names(self):
        seen = []
        real = arena._after_names

        def spy(text, names=()):
            seen.append(tuple(names))
            return real(text, names)

        day = simday.build_day(7, user=USER)
        day["events"] = [{"type": "item", "id": "x1", "at": "10:00", "kind": "email", "from": KARIM, "to": USER,
                          "subject": "s", "body": "b", "hidden": {"urgent": False}},
                         {"type": "user_says", "at": "11:00", "text": "t"}]
        with mock.patch.object(arena, "_after_names", spy):
            arena.clean_day(day)
        self.assertGreaterEqual(len(seen), 3)
        self.assertTrue(all("karim tawfik" in n for n in seen), seen)

    def test_with_inside_a_word_is_no_cue(self):
        self.assertEqual(arena._after_names("Sign forthwith Mark"), "Sign forthwith Mark")

    def test_every_and_after_a_masked_name(self):
        self.assertEqual(arena._after_names("with Mark and Amal and Noor and Seif"),
                         "with [name] and [name] and [name] and [name]")


if __name__ == "__main__":
    unittest.main()
