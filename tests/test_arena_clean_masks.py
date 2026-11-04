"""Cleaning for the Arena, three more kinds (arena/clean.py, 2026-11-04): an Instagram header
line's display name (styled and flag letters too), the rest of a line after an address cue, and
the first name after a print cue; then scrub_file and scrub_folder on files already written.
Made-up lines only. Each rule's test is run once more with the rule taken out (a mutant) and
must fail then. Styled and flag letters are built with chr() so the file shows them."""
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from arena import clean as cl

NEVER = re.compile(r"(?!)")


def flag_letters(word):
    """A word spelled in regional indicator letters (U+1F1E6 is A)."""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in word.upper())


def bold(word):
    """A word in mathematical bold letters (U+1D400 is A, U+1D41A is a)."""
    return "".join(chr(0x1D400 + ord(c) - ord("A")) if c.isupper() else chr(0x1D41A + ord(c) - ord("a")) for c in word)


EGYPT = flag_letters("EG")  # one flag
FIRE = chr(0x1F525)


def cleaned(text, names=()):
    return cl.Cleaner(names).chat(names)(text)


def texts(rows, names=()):
    """rows: (team, text) pairs; one chat through ChatCleaner.texts."""
    return cl.Cleaner(names).chat(names).texts([SimpleNamespace(text=t, team=team) for team, t in rows])


class Check(unittest.TestCase):
    def check(self, cases):
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(cleaned(text), want)

    def fails_without(self, patch, cases):
        """The mutant: with the rule taken out, at least one case no longer cleans as wanted."""
        with patch:
            missed = [text for text, want in cases if cleaned(text) != want]
        self.assertTrue(missed, "the cases pass with the rule taken out")


HEADERS = [
    ("Zorvex Qatam replied to an ad. View ad", "[name] replied to an ad. View ad"),
    ("zorvex el 2attan replied to your story", "[name] replied to your story"),
    ("Zorvex Qatam replied to your ad", "[name] replied to your ad"),
    ("زورفكس الطحان mentioned you in their story", "[name] mentioned you in their story"),
    ("Zorvex reacted to your message", "[name] reacted to your message"),
    ("Zorvex reacted " + FIRE + " to your story", "[name] reacted " + FIRE + " to your story"),
    (bold("Zorvex") + " " + FIRE + " replied to an ad. View ad", "[name] replied to an ad. View ad"),
    (flag_letters("ZORVEX") + " replied to your story", "[name] replied to your story"),
    (FIRE + " زورفكس " + EGYPT + " replied to an ad. View ad", "[name] replied to an ad. View ad"),
    (FIRE + EGYPT + " replied to your story", "[name] replied to your story"),
    ("3amr_z.99 Zorvex replied to an ad. View ad\nعايز المقاس 43", "[name] replied to an ad. View ad\nعايز المقاس 43"),
]
HEADERS_STAY = ["You replied to their story", "Replied to your story", "I replied to your message yesterday",
                "the ad you replied to", "Mentioned you in their story"]


class Headers(Check):
    def test_the_display_name_before_the_action_is_a_name(self):
        self.check(HEADERS)

    def test_a_pronoun_or_no_name_stays(self):
        self.check([(text, text) for text in HEADERS_STAY])

    def test_mutant_without_the_header_rule(self):
        self.fails_without(mock.patch.object(cl, "HEADER", NEVER), HEADERS)


FLAGS = [("Hi " + flag_letters("ZORVEX"), "Hi [name]"), ("hi " + " ".join(flag_letters("Zorvex")), "hi [name]"),
         ("يا " + flag_letters("ZORVEX") + " فين الاوردر", "يا [name] فين الاوردر")]


class FlagLetters(Check):
    def test_normalize_reads_a_run_of_three_or_more_as_letters(self):
        self.assertEqual(cl.normalize(flag_letters("ZORVEX")), "ZORVEX")
        self.assertEqual(cl.normalize(" ".join(flag_letters("ZORVEX"))), "ZORVEX")
        self.assertEqual(cl.normalize(chr(0x200B).join(flag_letters("ZOR"))), "ZOR")  # a zero width space between
        self.assertEqual(cl.normalize("عايز تيشيرت " + EGYPT), "عايز تيشيرت " + EGYPT)  # one flag stays

    def test_a_name_in_flag_letters_is_masked(self):
        self.check(FLAGS)

    def test_mutant_without_the_flag_letters(self):
        self.fails_without(mock.patch.object(cl, "RI_RUN", NEVER), FLAGS)


ADDRESSES = [
    ("العنوان حدائق الزيتون محل النور للدهانات", "العنوان [address]"),
    ("العنوان بتاعي حدائق الزيتون محل النور", "العنوان بتاعي [address]"),
    ("عنوان التوصيل زهرة البستان عند النور", "عنوان التوصيل [address]"),
    ("el 3enwan zahret el bostan nour paints", "el 3enwan [address]"),
    ("address zahret el bostan, beside nour paints", "address [address]"),
    ("the address is zahret el bostan nour paints", "the address is [address]"),
    ("تمام، العنوان زهرة البستان محل النور", "تمام، العنوان [address]"),
    ("المقاس 43\nالعنوان زهرة البستان محل النور", "المقاس 43\nالعنوان [address]"),
]
ADDRESS_ASKS = ["العنوان فين؟", "what's the address of the store?", "address of the store?", "address please",
                "العنوان بتاعكم فين", "العنوان بالتفصيل لو سمحت", "هبعتلك العنوان بكرة", "ابعت العنوان",
                "name and address please", "العنوان صح؟", "عنوانك ايه؟", "address", "العنوان ده",
                # a first word that makes it a question or a remark, with other words after it
                "address of the new branch?", "العنوان صح كده ولا ايه", "العنوان مش واضح خالص",
                "address changed to the new one"]


class AddressCue(Check):
    def test_the_rest_of_the_line_after_an_address_cue_is_an_address(self):
        self.check(ADDRESSES)

    def test_a_question_or_an_ask_for_the_address_stays(self):
        self.check([(text, text) for text in ADDRESS_ASKS])

    def test_the_address_window_opens_after_a_cue_line(self):
        got = texts([(True, "تمام"), (False, "العنوان زهرة البستان"), (False, "محل النور للدهانات"),
                     (True, "تمام هيوصلك بكرة"), (False, "شكرا")])
        self.assertEqual(got, ["تمام", "العنوان [address]", "[address]", "تمام هيوصلك بكرة", "شكرا"])
        self.assertTrue(cl.address_answer("العنوان [address]\nالعنوان بتاعي [address]"))
        self.assertFalse(cl.address_answer("المقاس 43\nالعنوان [address]"))

    def test_mutant_without_the_address_rule(self):
        self.fails_without(mock.patch.object(cl, "ADDRESS_LINE", NEVER), ADDRESSES)

    def test_mutant_without_the_first_word_check(self):
        self.fails_without(mock.patch.object(cl, "NOT_ADDRESS_FIRST", frozenset()), [(t, t) for t in ADDRESS_ASKS])

    def test_mutant_without_the_window(self):
        with mock.patch.object(cl, "address_answer", lambda text: False):
            got = texts([(False, "العنوان زهرة البستان"), (False, "محل النور للدهانات")])
        self.assertNotEqual(got[1], "[address]")


PRINTS = [
    ("اطبع اسم زورفكس على الضهر", "اطبع اسم [name] على الضهر"),
    ("عايز اطبع اسم زورفكس عليها", "عايز اطبع اسم [name] عليها"),
    ("اكتب اسم زورفكس", "اكتب اسم [name]"),
    ("ممكن طباعة اسم زورفكس", "ممكن طباعة اسم [name]"),
    ("print name zorvex on the back", "print name [name] on the back"),
    ("print the name Zorvex please", "print the name [name] please"),
    ("etba3 esm zorvex", "etba3 esm [name]"),
    ("ekteb esm zorvex 3aleha", "ekteb esm [name] 3aleha"),
]
PRINTS_STAY = ["اطبع اسم الفريق", "اطبع اسم الاهلي", "print the name and number", "print name on the back",
               "write your name here", "اكتب اسمه", "اطبع الاسم و الرقم"]


class PrintName(Check):
    def test_the_first_name_after_a_print_cue_is_a_name(self):
        self.check(PRINTS)

    def test_a_team_word_or_no_name_stays(self):
        self.check([(text, text) for text in PRINTS_STAY])

    def test_one_word_only_and_the_name_is_learned_for_the_chat(self):
        self.assertEqual(cleaned("etba3 esm zorvex kbir"), "etba3 esm [name] kbir")  # kbir: big
        self.assertEqual(cleaned("اطبع اسم زورفكس قطامش"), "اطبع اسم [name]")  # a surname: the chain after a [name]
        got = texts([(False, "زورفكس هيستلم"), (False, "اطبع اسم زورفكس على الضهر")])
        self.assertEqual(got, ["[name] هيستلم", "اطبع اسم [name] على الضهر"])

    def test_mutant_without_the_print_cue(self):
        without = re.compile(cl.NAME_CUE.pattern.replace(cl.PRINT_NAME + "|", "", 1), re.IGNORECASE)
        self.assertNotEqual(without.pattern, cl.NAME_CUE.pattern)
        self.fails_without(mock.patch.object(cl, "NAME_CUE", without), PRINTS)

    def test_mutant_without_the_one_word_limit(self):
        with mock.patch.object(cl, "PRINT_START", NEVER):
            self.assertNotEqual(cleaned("اطبع اسم الفريق"), "اطبع اسم الفريق")
            self.assertNotEqual(cleaned("etba3 esm zorvex kbir"), "etba3 esm [name] kbir")


# ---- scrub_file and scrub_folder: made-up rows in the shapes arena/personas.py writes

def entry(i, *turns, label="lost"):
    return {"id": f"c{i:04d}", "label": label, "why": "quiet after the price", "source": "instagram",
            "worry": "price", "turns": [dict(t, min=n) for n, t in enumerate(turns)]}


def say(side, text=None, media=None):
    t = {"from": side}
    if text is not None:
        t["text"] = text
    if media is not None:
        t["media"] = media
    return t


ROWS = [
    entry(1, say("store", "Zorvex Qatam replied to an ad. View ad"), say("customer", "اطبع اسم زورفكس على الضهر"),
          say("customer", media="image"), say("customer", "زورفكس هيستلم"), say("store", "16,500 EGP.")),
    entry(2, say("customer", "العنوان حدائق الزيتون محل النور للدهانات"), say("customer", "الدور التالت"),
          say("store", "تمام"), label="won"),
    entry(3, say("customer", "بكام الجاكيت؟"), say("store", "850 جنيه")),
]
CARD = {"worry": "price", "unwinnable": False, "why_unwinnable": None, "want": ["a lower price"],
        "buy_trigger": ["a discount"], "patience": {"median": 2, "most": 4},
        "style": {"length": {"short": 1.0}, "language": {"arabic": 1.0}, "voice_notes": 0.0, "opening": {"price": 1.0}},
        "chats": 3, "won": 1, "lost": 2, "id": "persona-01",
        "examples": ["بكام الجاكيت ده لو سمحت", "print name zorvex on the back", "العنوان حدائق الزيتون محل النور"]}


def jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


class Scrub(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.d = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_a_replay_file_is_cleaned_again_and_keeps_its_shape(self):
        src, dst = self.d / "replay.jsonl", self.d / "out.jsonl"
        src.write_text(jsonl(ROWS), encoding="utf-8")
        self.assertEqual(cl.scrub_file(src, dst), (3, 2))
        got = [json.loads(x) for x in dst.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([[t.get("text") for t in e["turns"]] for e in got], [
            ["[name] replied to an ad. View ad", "اطبع اسم [name] على الضهر", None, "[name] هيستلم", "16,500 EGP."],
            ["العنوان [address]", "[address]", "تمام"],
            ["بكام الجاكيت؟", "850 جنيه"]])
        for old, new in zip(ROWS, got):  # ids, labels, keys, media and minutes stay
            self.assertEqual({k: v for k, v in new.items() if k != "turns"}, {k: v for k, v in old.items() if k != "turns"})
            self.assertEqual([{k: v for k, v in t.items() if k != "text"} for t in new["turns"]],
                             [{k: v for k, v in t.items() if k != "text"} for t in old["turns"]])
            self.assertEqual(list(new), list(old))
        self.assertEqual(oct(os.stat(dst).st_mode & 0o777), "0o600")

    def test_a_clean_file_comes_back_byte_for_byte_and_in_place_works(self):
        src = self.d / "replay.jsonl"
        src.write_text(jsonl([ROWS[2]]) + "\n", encoding="utf-8")  # a blank line at the end stays
        before = src.read_bytes()
        self.assertEqual(cl.scrub_file(src, src), (1, 0))
        self.assertEqual(src.read_bytes(), before)

    def test_a_cards_folder_has_its_examples_cleaned(self):
        cards, out = self.d / "cards", self.d / "out"
        cards.mkdir()
        (cards / "persona-01.json").write_text(json.dumps(CARD, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        plain = dict(CARD, id="persona-02", examples=["بكام الجاكيت ده لو سمحت"])
        (cards / "persona-02.json").write_text(json.dumps(plain, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (cards / "notes.txt").write_text("not a card", encoding="utf-8")
        self.assertEqual(cl.scrub_folder(cards, out), (2, 1))
        self.assertEqual(sorted(os.listdir(out)), ["persona-01.json", "persona-02.json"])
        got = json.loads((out / "persona-01.json").read_text(encoding="utf-8"))
        self.assertEqual(got["examples"], ["بكام الجاكيت ده لو سمحت", "print name [name] on the back", "العنوان [address]"])
        self.assertEqual({k: v for k, v in got.items() if k != "examples"}, {k: v for k, v in CARD.items() if k != "examples"})
        self.assertEqual((out / "persona-02.json").read_bytes(), (cards / "persona-02.json").read_bytes())

    def test_scrub_walks_text_fields_only(self):
        data = {"id": "m1", "why": "Zorvex Qatam replied to an ad", "turns": [
            {"customer": "اطبع اسم زورفكس", "agent": "اطبع اسم زورفكس"}], "examples": [3, "etba3 esm zorvex"]}
        self.assertEqual(cl.scrub(data), {"id": "m1", "why": "Zorvex Qatam replied to an ad", "turns": [
            {"customer": "اطبع اسم [name]", "agent": "اطبع اسم زورفكس"}], "examples": [3, "etba3 esm [name]"]})

    def test_a_bad_line_stops_it_with_its_number_and_never_its_text(self):
        src, dst = self.d / "replay.jsonl", self.d / "out.jsonl"
        src.write_text(jsonl([ROWS[2]]) + "زورفكس قطامش {\n", encoding="utf-8")
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            code = cl.main(["scrub", str(src), str(dst)])
        self.assertEqual(code, 3)
        self.assertEqual(err.getvalue().strip(), "Stopped: line 2 is not JSON")
        self.assertNotIn("زورفكس", err.getvalue() + out.getvalue())
        self.assertFalse(dst.exists())

    def test_the_command_prints_counts_only(self):
        src, dst = self.d / "replay.jsonl", self.d / "out.jsonl"
        src.write_text(jsonl(ROWS), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cl.main(["scrub", str(src), str(dst)]), 0)
        self.assertEqual(out.getvalue(), "entries: 3, changed: 2\n")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cl.main(["scrub", str(src)]), 2)


if __name__ == "__main__":
    unittest.main()
