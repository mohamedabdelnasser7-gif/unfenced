"""Privacy guards for the Arena personas (2026-10-30): one test per guard that no other test
caught when it was switched off (mutation run, round 4). The pipeline wiring (every display
name in the import, the chat's own Instagram username, the chat cleaner for the model's tags),
the place and out folder checks, error text kept out, and each cleaning layer on a line only it
masks. Made-up names and text only."""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from arena import cards as cards_mod
from arena import clean as cl
from arena import personas as pp
from arena import recipe as recipe_mod
from arena import tag as tag_mod
from tests import fake_recipe
from tests.test_arena_clean_probes import STORE, plain, write_chat

ROOT = Path(__file__).resolve().parent.parent
PLACED = "تمام، تم تسجيل الطلب"
SECRET = ("Zorvex", "Tamblin", "qorvix", "Sefru")
IG_START_MS = 1785578400000  # 2026-08-01 10:00 UTC, before every WhatsApp chat below


def write_instagram(src, folder, sender, lines):
    """One Instagram JSON thread, newest message first as Instagram writes it. lines: (side, text)."""
    msgs = [{"sender_name": STORE if side == "s" else sender, "timestamp_ms": IG_START_MS + n * 60000, "content": text}
            for n, (side, text) in enumerate(lines)]
    doc = {"participants": [{"name": sender}, {"name": STORE}], "messages": msgs[::-1], "title": sender,
           "is_still_participant": True, "thread_path": f"inbox/{folder}"}
    where = os.path.join(src, "instagram", "messages", "inbox", folder)
    os.makedirs(where)
    with open(os.path.join(where, "message_1.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)


def make_export(src):
    """Chat A: Zorvex Tamblin buys. Chat B: Qarlo Venmish buys and names Zorvex Tamblin, who is
    not a sender in B. Chat C: Instagram user qorvixblan (display name Sefru Blandin) types
    the username and goes quiet after the price."""
    os.makedirs(os.path.join(src, "whatsapp"))
    write_chat(src, "a", "Zorvex Tamblin", [("c", "الجزمة دي بكام"), ("s", "السعر 1450 جنيه"), ("c", "هاخدها"),
                                           ("s", PLACED)], 10)
    write_chat(src, "b", "Qarlo Venmish", [("c", "Zorvex Tamblin told me about you"), ("s", "السعر 1450 جنيه"),
                                          ("c", "تمام اكدلي"), ("s", PLACED)], 20)
    write_instagram(src, "qorvixblan_1000000001", "Sefru Blandin",
                    [("c", "qorvixblan here, price for 42?"), ("s", "1450 EGP")])


class Echo:
    """Writes the chat's own names back into the free text fields, as a model might."""
    label = "echo"

    def __init__(self, recipe):
        self.worry = recipe.worries[0]

    def chat(self, messages, **kw):
        data = messages[1]["content"]
        want, trigger = "boots", "the price"
        if "هاخدها" in data:
            want, trigger = "Zorvex wants boots", "Tamblin got free shipping"
        elif "price for 42" in data:
            want, trigger = "qorvixblan wants size 42", "Sefru asked twice"
        answer = {"want": want, "worry": self.worry, "buy_trigger": trigger, "patience": 1, "no_budget": False}
        return {"role": "assistant", "content": json.dumps(answer)}


class PipelineWiring(unittest.TestCase):
    """personas.run builds the cleaner from every display name, gives each Instagram chat its
    username and hands the chat cleaner to the tagger."""

    def test_no_name_or_username_reaches_the_replay_the_cards_or_the_tags(self):
        rec = fake_recipe.load()
        tags, real_call = [], tag_mod.Tagger.__call__

        def spy(tagger, *args, **kw):
            got = real_call(tagger, *args, **kw)
            tags.append(got)
            return got

        with tempfile.TemporaryDirectory() as work:
            src, out = os.path.join(work, "src"), os.path.join(work, "out")
            make_export(src)
            with mock.patch.object(tag_mod.Tagger, "__call__", spy):
                summary = pp.run(src, out, model=Echo(rec), recipe=rec, team=[STORE])
            self.assertEqual(summary["labels"], {"won": 2, "lost": 1, "unclear": 0})
            self.assertEqual(summary["read"]["instagram_chats"], 1)
            written = []
            for root, _, files in os.walk(out):
                for f in files:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        written.append(plain(fh.read()))
            with open(os.path.join(out, "replay.jsonl"), encoding="utf-8") as f:
                turns = [t.get("text") for line in f for t in json.loads(line)["turns"]]
        self.assertEqual(len(tags), 3)
        self.assertTrue(all(t is not None for t in tags))
        self.assertIn("[name] told me about you", turns)
        self.assertIn("[user] here, price for 42?", turns)
        self.assertIn("[name] wants boots", [t["want"] for t in tags])
        self.assertIn("[user] wants size 42", [t["want"] for t in tags])
        blob = "\n".join(written + [json.dumps(tags)])
        for s in SECRET:
            with self.subTest(secret=s):
                self.assertNotIn(s.casefold(), blob.casefold())


class Places(unittest.TestCase):
    def test_a_zip_inside_the_repo_is_refused_and_nothing_is_made(self):
        with tempfile.TemporaryDirectory() as work:
            src, out = os.path.join(work, "src"), os.path.join(work, "out")
            make_export(src)
            inside = ROOT / f"arena-guard-{os.getpid()}.zip"
            self.addCleanup(lambda: inside.unlink() if inside.exists() else None)
            with zipfile.ZipFile(inside, "w") as z:
                for p in sorted(Path(src).rglob("*")):
                    if p.is_file():
                        z.write(p, p.relative_to(src).as_posix())
            e = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(e):
                code = pp.main(["--source", str(inside), "--out", out, "--team", STORE, "--scripted", "--recipe",
                                str(fake_recipe.write(work))])
            self.assertEqual(code, 2)
            self.assertIn("inside the repo", e.getvalue())
            self.assertFalse(os.path.exists(out))

    def test_the_out_folder_is_checked_again_before_writing(self):
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "notes.txt"), "w", encoding="utf-8") as f:
                f.write("mine")
            with self.assertRaises(pp.hist.Refused):
                pp.write_out(out, [], [], {})
            self.assertEqual(os.listdir(out), ["notes.txt"])


class ErrorText(unittest.TestCase):
    """An error's text could hold a message; only its type is shown."""

    def test_main_names_the_error_type_only(self):
        with tempfile.TemporaryDirectory() as work:
            e = io.StringIO()
            with mock.patch.object(pp, "run", side_effect=RuntimeError("Zorvex 01001234567")), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(e):
                code = pp.main(["--source", work, "--out", os.path.join(work, "out"), "--scripted", "--recipe",
                                str(fake_recipe.write(work))])
        self.assertEqual(code, 3)
        self.assertEqual(e.getvalue(), "Stopped: RuntimeError\n")

    def test_the_tagger_keeps_the_error_type_only(self):
        class Raising:
            label = "raising"

            def chat(self, messages, **kw):
                raise ValueError("Zorvex 01001234567")

        tagger = tag_mod.Tagger(model=Raising(), recipe=fake_recipe.load())
        self.assertIsNone(tagger([{"from": "customer", "text": "بكام"}], "lost"))
        self.assertEqual(tagger.last_error, "the model call failed: ValueError")

    def test_a_long_turn_is_cut_before_the_model(self):
        got = tag_mod.turns_for_model([{"from": "customer", "text": "ب" * 500}])
        self.assertEqual(got, [{"from": "customer", "text": "ب" * tag_mod.MAX_LINE}])
        self.assertEqual(tag_mod.MAX_LINE, 400)


class Layers(unittest.TestCase):
    """Each line here is masked by one cleaning layer only (no names known for the chat)."""

    def check(self, cases):
        c = cl.Cleaner().chat()
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(c(text), want)

    def test_a_handle_after_a_cue_word(self):
        self.check([("my insta zorvexblan", "my insta [user]"), ("ig: zorvexblan", "ig: [user]"),
                    ("snap zorvex.blan", "snap [user]")])

    def test_a_dotted_handle(self):
        self.check([("zor.vex.blan", "[user]"), ("follow zorvex.k99 pls", "follow [user] pls")])

    def test_a_listed_name_with_one_digit(self):
        self.check([("karim7", "[user]"), ("ahmed7 here", "[user] here")])

    def test_a_word_after_ya(self):
        self.check([("يا زوزو", "يا [name]"), ("تمام يا زوزو المقاس متاح", "تمام يا [name] المقاس متاح")])

    def test_a_latin_call(self):
        self.check([("ya zorvex", "ya [name]"), ("Hi Zorvex, size 42 is ready", "Hi [name], size 42 is ready"),
                    ("Thanks Zorvex", "Thanks [name]"), ("hello Zorvex the size is ready",
                                                        "hello [name] the size is ready"),
                    ("hi zorvex", "hi zorvex")])

    def test_any_answer_to_the_name_question_is_a_name(self):
        for answer in ("zorvex", "Zorvex", "زوزو", "zorvex tamblin"):
            rows = [SimpleNamespace(text="تمام يا فندم، اسم حضرتك؟", team=True), SimpleNamespace(text=answer, team=False)]
            with self.subTest(answer=answer):
                self.assertEqual(cl.Cleaner().chat().texts(rows)[1], "[name]")

    def test_recipe_words_and_places_are_plain_text(self):
        """clean._latin_place builds the Latin places and a recipe's words: a sign in them is
        that sign, never a pattern."""
        rx = re.compile(cl._latin_place("st. catherine?"), re.IGNORECASE)
        self.assertIsNotNone(rx.fullmatch("st. catherine?"))
        self.assertIsNone(rx.fullmatch("stx catherin"))
        data = fake_recipe.data()
        data["worries"] = [{"name": "money", "words": ["how much?"]}, {"name": "other", "words": []}]
        data["unwinnable"], data["fallback"] = [], "other"
        words = recipe_mod.Recipe(data).words["money"]
        self.assertIsNotNone(words.search("ok how much? for 42"))
        self.assertIsNone(words.search("how muc is it"))


class CardExamples(unittest.TestCase):
    def test_a_word_after_ya_that_looks_like_a_name_is_never_an_example(self):
        line = "تمام يا زوزو المقاس متاح"
        self.assertFalse(cl.has_name(line))
        self.assertFalse(cards_mod.example_ok(line))
        self.assertTrue(cards_mod.example_ok("تمام يا فندم المقاس متاح"))


if __name__ == "__main__":
    unittest.main()
