"""The Arena persona run (arena/personas.py, new 2026-10-30) on the made-up export from
demo/make_arena_history.py, with the scripted model or a fake one: never a real call, never a
real chat. Labels, grouping, card shape and weights, the call cap and the limit, failed and bad
answers, the out folder checks, folder and zip sources, the team, the recipe (required, never
in the repo; tests/fake_recipe.py stands in), file modes, counts-only output, demo/personas
equal to a fresh build with the test recipe (byte for byte) and the printing cap held in it."""
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from kit import model as model_mod
from arena import cards as cards_mod
from arena import personas as pp
from arena import recipe as recipe_mod
from arena.scripted import ScriptedModel
from tests import fake_recipe

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "personas"
MAKE = ROOT / "demo" / "make_arena_history.py"
TEAM = "Beyond the Limits"
ARABIC = re.compile(r"[\u0600-\u06FF]")


def remove_later(test, *paths):
    """A regression that writes into the repo must not leave its files there for the next run."""
    def gone():
        for p in paths:
            if os.path.islink(p) or os.path.isfile(p):
                os.unlink(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
    test.addCleanup(gone)


def make_history(out):
    run = subprocess.run([sys.executable, "-I", str(MAKE), "--out", str(out)], capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0, run.stderr


def zip_folder(folder, dest, extra=()):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(folder).rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
        for info, data in extra:
            z.writestr(info, data)


class Failing:
    label = "failing"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        raise model_mod.ModelError("Baseten answered 500 Internal Server Error")


class Junk:
    label = "junk"

    def chat(self, messages, **kw):
        return {"role": "assistant", "content": '{"want": "boots", "worry": "weather", "patience": 1}'}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.hist = cls.tmp / "hist"
        make_history(cls.hist)
        cls.recipe = fake_recipe.write(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._out = tempfile.TemporaryDirectory()
        self.base = Path(self._out.name)
        self.out = self.base / "out"

    def tearDown(self):
        self._out.cleanup()

    def main(self, *args, source=None, out=None, model=None, scripted=True, recipe=True):
        """recipe: True gives the test recipe unless args name one; False gives none."""
        argv = ["--source", str(source or self.hist), "--out", str(out or self.out), *args]
        if recipe and "--recipe" not in args:
            argv += ["--recipe", str(self.recipe)]
        if scripted and model is None:
            argv.append("--scripted")
        o, e = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            try:
                code = pp.main(argv, model=model)
            except SystemExit as x:  # argparse
                code = x.code
        return code, o.getvalue(), e.getvalue()

    def summary(self, out=None):
        return json.loads(((out or self.out) / "summary.json").read_text(encoding="utf-8"))

    def cards(self, out=None):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(((out or self.out) / "cards").iterdir())]

    def replay(self, out=None):
        return [json.loads(x) for x in ((out or self.out) / "replay.jsonl").read_text(encoding="utf-8").splitlines()]


class Run(Base):
    def test_labels_from_the_chats(self):
        code, _, err = self.main()
        self.assertEqual(code, 0, err)
        s = self.summary()
        self.assertEqual(s["labels"], {"won": 12, "lost": 16, "unclear": 5})
        self.assertEqual(s["why"]["won: address sent"], 3)
        self.assertEqual(s["why"]["unclear: last customer message is a voice note"], 1)
        self.assertEqual(s["why"]["unclear: cancelled after the won sign"], 1)
        self.assertEqual(s["read"], {"whatsapp_chats": 26, "instagram_chats": 7, "messages": 153})
        self.assertEqual(len(self.replay()), 28)
        self.assertEqual({r["label"] for r in self.replay()}, {"won", "lost"})

    def test_cards_group_by_worry_with_their_shape(self):
        self.main()
        cards, s = self.cards(), self.summary()
        keys = {"id", "worry", "unwinnable", "why_unwinnable", "want", "buy_trigger", "patience", "style", "chats",
                "won", "lost", "examples", "share", "arena_weight"}
        for c in cards:
            self.assertEqual(set(c), keys)
            self.assertEqual(set(c["style"]), {"length", "language", "voice_notes", "opening"})
            self.assertLessEqual(len(c["examples"]), cards_mod.MAX_EXAMPLES)
            self.assertEqual(c["won"] + c["lost"], c["chats"])
            for line in c["examples"]:
                self.assertTrue(cards_mod.example_ok(line), line)
        self.assertEqual(len({(c["worry"], c["why_unwinnable"]) for c in cards}), len(cards))
        self.assertEqual(sum(c["chats"] for c in cards), s["tagging"]["tagged"])
        self.assertAlmostEqual(sum(c["arena_weight"] for c in cards), 1.0, places=2)
        by = {(c["worry"], c["why_unwinnable"]): c for c in cards}
        self.assertEqual(by[("size", None)]["chats"], 6)
        self.assertEqual(by[("just browsing", "just browsing")]["chats"], 3)
        self.assertEqual(by[("price", "no budget")]["chats"], 1)

    def test_the_real_unwinnable_share_from_20_tagged_chats_else_the_set_share(self):
        self.main()
        info = self.summary()["cards"]
        self.assertEqual(info["tagged_chats"], 28)
        self.assertEqual(info["unwinnable_share_real"], round(4 / 28, 3))
        self.assertEqual(info["unwinnable_share_used"], info["unwinnable_share_real"])
        shutil.rmtree(self.out)
        self.main("--limit", "10")
        info = self.summary()["cards"]
        self.assertIsNone(info["unwinnable_share_real"])
        self.assertEqual(info["unwinnable_share_used"], cards_mod.UNWINNABLE_SHARE if info["unwinnable_chats"] else 0.0)

    def test_unwinnable_cards_only_from_data(self):
        recipe = fake_recipe.load()
        item = {"label": "lost", "turns": [], "style": {"length": "short", "language": {"arabic": 1, "franco": 0,
                                                                                        "english": 0},
                                                         "voice_notes": 0, "opening": "price"},
                "tags": {"want": "boots", "worry": "price", "buy_trigger": "a bundle", "patience": 0, "no_budget": False}}
        cards, info = cards_mod.build([item] * 25, recipe)
        self.assertEqual([c["unwinnable"] for c in cards], [False])
        self.assertEqual(info["unwinnable_share_used"], 0.0)
        self.assertEqual(cards[0]["arena_weight"], 1.0)

    def test_the_cap_and_the_limit(self):
        self.main("--cap", "3")
        t = self.summary()["tagging"]
        self.assertEqual((t["calls"], t["tagged"], t["cap"]), (3, 3, 3))
        # a cap below the 28 won and lost chats picks that many, spread over the dates, none left untagged
        self.assertEqual((t["picked"], t["not_tagged"]), (3, 0))
        shutil.rmtree(self.out)
        self.main("--limit", "5", "--cap", "300")
        t = self.summary()["tagging"]
        self.assertEqual((t["picked"], t["calls"]), (5, 5))
        shutil.rmtree(self.out)
        self.main("--limit", "2")
        self.assertEqual(self.summary()["tagging"]["cap"], 1000)  # the default, raised from 300 (DECISIONS item 33)
        for bad in ("1001", "0", "-1"):
            code, _, err = self.main("--cap", bad)
            self.assertEqual(code, 2, bad)
        self.assertIn("the cap can only be lowered", self.main("--cap", "1001")[2])

    def test_the_tagger_holds_its_own_cap(self):
        recipe = fake_recipe.load()
        model = ScriptedModel(recipe)
        tagger = pp.tag_mod.Tagger(model=model, cap=2, recipe=recipe)
        turns = [{"from": "customer", "text": "بكام؟"}, {"from": "store", "text": "1450 جنيه"}]
        tagger(turns, "lost")
        tagger(turns, "lost")
        with self.assertRaises(pp.tag_mod.CapReached):
            tagger(turns, "lost")
        self.assertEqual(len(model.calls), 2)
        for bad in (0, 1001, True, "3"):
            with self.assertRaises(ValueError):
                pp.tag_mod.Tagger(model=model, cap=bad, recipe=recipe)

    def test_three_failed_calls_in_a_row_stop_the_run(self):
        model = Failing()
        code, out, err = self.main(model=model)
        self.assertEqual(code, 0, err)
        t = self.summary()["tagging"]
        self.assertEqual((model.calls, t["calls"], t["failed"], t["tagged"]), (3, 3, 3, 0))
        self.assertEqual(t["stopped"], "3 failed calls in a row")
        self.assertEqual(t["not_tagged"], 25)
        self.assertIn("Baseten answered 500", out)

    def test_bad_answers_give_no_tag(self):
        code, _, err = self.main(model=Junk(), scripted=False)
        self.assertEqual(code, 0, err)
        s = self.summary()
        self.assertEqual((s["tagging"]["bad_answers"], s["tagging"]["tagged"], s["cards"]["cards"]), (28, 0, 0))
        self.assertEqual(self.cards(), [])
        self.assertEqual({r["worry"] for r in self.replay()}, {None})

    def test_the_model_sees_only_cleaned_text_and_the_recipe_prompt(self):
        recipe = fake_recipe.load()
        model = ScriptedModel(recipe)
        self.main(model=model)
        self.assertEqual(len(model.calls), 28)
        seen = json.dumps(model.calls, ensure_ascii=False)
        for word in ("تجربة", "Demo", "Karim", "طارق", "Beyond", "example.com", "@", "Alexandria", "مدينة نصر",
                     "القاهرة", "Nasr"):
            self.assertNotIn(word, seen.replace(recipe.prompt.replace("\n", "\\n"), ""), word)
        self.assertIsNone(re.search(r"\d{7}", seen))
        self.assertTrue(all(c[0]["content"] == recipe.prompt for c in model.calls))
        self.assertIn("size, price, cash on delivery", recipe.prompt)

    def test_a_name_the_model_writes_back_is_masked_in_the_cards(self):
        worry = sorted(fake_recipe.load().worries)[0]

        class Echo:
            label = "echo"

            def chat(self, messages, **kw):
                return {"role": "assistant", "content": json.dumps(
                    {"want": "Demo Karim wants boots", "worry": worry, "buy_trigger": "كريم تجربة got a discount",
                     "patience": 2, "no_budget": False}, ensure_ascii=False)}

        code, _, err = self.main(model=Echo(), scripted=False)
        self.assertEqual(code, 0, err)
        text = json.dumps(self.cards(), ensure_ascii=False)
        self.assertIn("wants boots", text)
        for word in ("Demo", "Karim", "كريم", "تجربة"):
            self.assertNotIn(word, text, word)


class OutFolder(Base):
    def test_inside_the_repo_is_refused_and_nothing_is_made(self):
        link = self.base / "into-repo"
        os.symlink(ROOT / "demo", link)
        remove_later(self, ROOT / "arena-out-test", ROOT / "demo" / "history" / "arena-out", ROOT / "demo" / "arena-out")
        for out in (ROOT / "arena-out-test", ROOT / "demo" / "history" / "arena-out", link / "arena-out"):
            code, _, err = self.main(out=out)
            self.assertEqual(code, 2, str(out))
            self.assertIn("Refused, nothing written: the out folder is inside the repo", err)
            self.assertFalse(os.path.lexists(out))
            self.assertFalse(os.path.lexists(ROOT / "demo" / "arena-out"))

    def test_a_link_or_a_foreign_file_is_refused(self):
        real = self.base / "real"
        real.mkdir()
        os.symlink(real, self.base / "link")
        self.assertEqual(self.main(out=self.base / "link")[0], 2)
        (real / "notes.txt").write_text("mine", encoding="utf-8")
        code, _, err = self.main(out=real)
        self.assertEqual(code, 2)
        self.assertIn("holds other files", err)
        self.assertEqual((real / "notes.txt").read_text(encoding="utf-8"), "mine")
        self.assertEqual(sorted(os.listdir(real)), ["notes.txt"])

    def test_a_link_with_a_trailing_slash_is_refused(self):
        real = self.base / "real"
        real.mkdir()
        os.symlink(real, self.base / "link")
        for out in (f"{self.base / 'link'}/", f"{self.base / 'link'}//"):
            code, _, err = self.main(out=out)
            self.assertEqual(code, 2, out)
            self.assertIn("the out folder is a link", err)
        self.assertEqual(os.listdir(real), [])

    def test_a_hard_link_in_the_out_folder_keeps_its_file(self):
        self.main()
        victim = self.base / "victim.txt"
        victim.write_text("mine", encoding="utf-8")
        for name in ("summary.json", "replay.jsonl"):
            os.unlink(self.out / name)
            os.link(victim, self.out / name)
        os.unlink(self.out / "cards" / "persona-01.json")
        os.link(victim, self.out / "cards" / "persona-01.json")
        code, _, err = self.main()
        self.assertEqual(code, 0, err)
        self.assertEqual(victim.read_text(encoding="utf-8"), "mine")
        self.assertEqual(os.stat(victim).st_nlink, 1)
        self.assertEqual(self.summary()["labels"]["won"], 12)
        self.assertEqual(sorted(p for p in os.listdir(self.out) if p.endswith(".tmp")), [])

    def test_a_second_run_writes_over_its_own_files_and_drops_stale_cards(self):
        self.main()
        (self.out / "cards" / "persona-99.json").write_text("{}", encoding="utf-8")
        code, _, err = self.main()
        self.assertEqual(code, 0, err)
        self.assertNotIn("persona-99.json", os.listdir(self.out / "cards"))

    def test_file_modes(self):
        self.main()
        self.assertEqual(stat.S_IMODE(os.stat(self.out).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.out / "cards").st_mode), 0o700)
        for p in [self.out / "summary.json", self.out / "replay.jsonl", *(self.out / "cards").iterdir()]:
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p.name)


class Source(Base):
    def test_a_source_inside_the_repo_is_refused(self):
        code, _, err = self.main(source=ROOT / "arena")
        self.assertEqual(code, 2)
        self.assertIn("inside the repo", err)
        self.assertFalse(self.out.exists())

    def test_a_zip_gives_the_same_files_as_the_folder(self):
        self.main()
        dest = self.base / "export.zip"
        zip_folder(self.hist, dest)
        second = self.base / "second"
        code, _, err = self.main(source=dest, out=second)
        self.assertEqual(code, 0, err)
        for rel in ("summary.json", "replay.jsonl", *("cards/" + p.name for p in (self.out / "cards").iterdir())):
            self.assertEqual((self.out / rel).read_bytes(), (second / rel).read_bytes(), rel)

    def test_zip_entries_refused_and_counted(self):
        link = zipfile.ZipInfo("whatsapp/link.txt")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        extra = [(link, "/etc/hosts"), ("instagram/messages/inbox/someone_1/message_1.html", "<html></html>"),
                 ("inner.zip", b"PK"), ("__MACOSX/whatsapp/._x.txt", "x")]
        dest = self.base / "export.zip"
        zip_folder(self.hist, dest, extra)
        code, _, err = self.main(source=dest)
        self.assertEqual(code, 0, err)
        got = {(n["kind"], n["why"]): n["files"] for n in self.summary()["not_read"]}
        self.assertEqual(got, {("whatsapp", "a link"): 1, ("zip", "a zip inside the zip"): 1,
                               ("instagram", "an HTML download; ask Instagram for JSON"): 1})
        self.assertEqual(self.summary()["read"]["whatsapp_chats"], 26)

    def test_encrypted_entries_and_the_entry_cap(self):
        class Z:
            def __init__(self, infos):
                self.infos = infos

            def infolist(self):
                return self.infos
        locked = zipfile.ZipInfo("whatsapp/locked.txt")
        locked.flag_bits |= 1
        reader = pp.hist.Reader()
        wa, threads = pp._members(reader, Z([locked]))
        self.assertEqual((wa, threads), ([], {}))
        self.assertEqual(dict(reader.refused), {("whatsapp", "encrypted"): 1})
        with mock.patch.object(pp, "MAX_MEMBERS", 1):
            with self.assertRaises(pp.hist.Refused):
                pp._members(reader, Z([locked, locked]))

    def test_a_bad_zip_is_refused(self):
        dest = self.base / "bad.zip"
        dest.write_bytes(b"not a zip")
        code, _, err = self.main(source=dest)
        self.assertEqual(code, 2)
        self.assertIn("a zip that cannot be read", err)


class TeamAndRecipe(Base):
    def test_the_team_found_or_given(self):
        self.main()
        self.assertEqual(self.summary()["team"], {"from": "found", "names": 1})
        few = self.base / "few"
        (few / "whatsapp").mkdir(parents=True)
        for p in sorted((self.hist / "whatsapp").iterdir())[:2]:
            shutil.copy(p, few / "whatsapp" / p.name)
        code, _, err = self.main(source=few, out=self.base / "o2")
        self.assertEqual(code, 2)
        self.assertIn("no team found; give --team", err)
        code, _, err = self.main("--team", TEAM, source=few, out=self.base / "o3")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.summary(self.base / "o3")["team"], {"from": "given", "names": 1})

    def test_an_own_recipe_is_used_and_a_bad_one_refused(self):
        data = fake_recipe.data()
        data["worries"] =[{"name": "fit", "words": ["مقاس", "size", "ma2as"]}, {"name": "money", "words": ["بكام"]},
                           {"name": "anything else", "words": []}]
        data["unwinnable"], data["fallback"] = [], "anything else"
        own = self.base / "recipe.json"
        own.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, _, err = self.main("--recipe", str(own))
        self.assertEqual(code, 0, err)
        s = self.summary()
        self.assertEqual(s["recipe"], "own")
        self.assertEqual({c["worry"] for c in self.cards()} - {"fit", "money", "anything else"}, set())
        for broken in ({**data, "prompt": "no placeholder"}, {**data, "fallback": "nothing"},
                       {**data, "worries": [{"name": "Bad Name", "words": []}, {"name": "ok", "words": []}]}):
            own.write_text(json.dumps(broken), encoding="utf-8")
            code, _, err = self.main("--recipe", str(own), out=self.base / "o4")
            self.assertEqual(code, 2, err)
            self.assertIn("Refused, nothing written: the recipe", err)
            self.assertFalse((self.base / "o4").exists())

    def test_no_recipe_is_refused_and_nothing_is_written(self):
        """The recipe is private (DECISIONS item 17): there is no built-in one to fall back on."""
        for none in (None, ""):
            with self.assertRaises(recipe_mod.hist.Refused) as e:
                recipe_mod.load(none)
            self.assertIn("none given", str(e.exception))
            self.assertIn("--recipe", str(e.exception))
            self.assertIn("demo/personas/recipe.example.json", str(e.exception))
        code, _, err = self.main(recipe=False)
        self.assertEqual(code, 2)
        self.assertIn("Refused, nothing written: the recipe: none given", err)
        self.assertFalse(self.out.exists())
        with self.assertRaises(recipe_mod.hist.Refused):
            pp.tag_mod.Tagger(model=ScriptedModel(fake_recipe.load()))
        with self.assertRaises(recipe_mod.hist.Refused):
            pp.run(self.hist, self.base / "lib", model=ScriptedModel(fake_recipe.load()))

    def test_the_example_shows_the_shape_and_nothing_more(self):
        doc = json.loads(recipe_mod.EXAMPLE.read_text(encoding="utf-8"))
        rec = recipe_mod.load(recipe_mod.EXAMPLE)
        self.assertTrue(rec.example)
        self.assertFalse(fake_recipe.load().example)
        self.assertEqual(rec.worries, ("size", "price", "cash on delivery", "trust", "delivery time", "just browsing",
                                       "other"))
        self.assertEqual((sorted(rec.unwinnable), rec.fallback), (["just browsing"], "other"))
        self.assertLessEqual(max(len(w["words"]) for w in doc["worries"]), 2)
        self.assertLess(len(doc["prompt"]), 300)
        code, _, err = self.main("--recipe", str(recipe_mod.EXAMPLE))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.summary()["recipe"], "example")

    def test_no_recipe_file_but_the_example_under_demo_on_disk(self):
        found = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "demo").rglob("*") if "recipe" in p.name.lower())
        self.assertEqual(found, ["demo/personas/recipe.example.json"])
        self.assertFalse((DEMO / "recipe.json").exists())

    def test_no_recipe_file_but_the_example_tracked_under_demo(self):
        try:
            run = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, timeout=30)
        except OSError:
            run = None
        if run is None or run.returncode != 0:
            self.skipTest("not a git checkout, or git cannot run")
        listed = [n for n in run.stdout.decode("utf-8").split("\0") if n]
        if not listed:
            self.skipTest("a repo before its first add: git tracks no file yet")
        tracked = [n for n in listed if n.startswith("demo/")]
        self.assertIn("demo/personas/summary.json", tracked)
        self.assertNotIn("demo/personas/recipe.json", tracked)
        self.assertEqual([n for n in tracked if "recipe" in n.rsplit("/", 1)[-1].lower()],
                         ["demo/personas/recipe.example.json"])

    def test_no_key_is_refused_before_anything_is_read(self):
        env = {k: v for k, v in os.environ.items() if k not in ("BASETEN_API_KEY", "META_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(pp.env, "load", return_value=[]), \
                mock.patch.object(pp, "read_source") as read:
            code, _, err = self.main(scripted=False)
        self.assertEqual(code, 2)
        self.assertIn("no model key is set (META_API_KEY or BASETEN_API_KEY) (or give --scripted)", err)
        read.assert_not_called()
        self.assertFalse(self.out.exists())


class Output(Base):
    def assert_counts_only(self, text):
        self.assertIsNone(ARABIC.search(text), text)
        # the recipe's short hash is hex and may open with 7 digits; no phone number hides in it
        self.assertIsNone(re.search(r"\d{7}", re.sub(r'"recipe_sha256": "[0-9a-f]{12}"', "", text)), text)
        for word in ("Demo", "@", "example", str(self.base), str(self.hist), "Beyond", "[name]", "[phone]"):
            self.assertNotIn(word, text)

    def test_counts_only_in_process_and_by_path_under_isolated_mode(self):
        remove_later(self, ROOT / "arena-out-test")
        code, out, err = self.main()
        self.assertEqual(code, 0, err)
        self.assert_counts_only(out + err)
        self.assert_counts_only(self.main("--json", out=self.base / "j")[1])
        run = subprocess.run([sys.executable, "-I", str(ROOT / "arena" / "personas.py"), "--source", str(self.hist),
                              "--out", str(self.base / "p"), "--scripted", "--recipe", str(self.recipe)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("Labels: 12 won, 16 lost, 5 unclear (skipped)", run.stdout)
        self.assert_counts_only(run.stdout + run.stderr)
        refused = subprocess.run([sys.executable, "-I", str(ROOT / "arena" / "personas.py"), "--source",
                                  str(self.hist), "--out", str(ROOT / "arena-out-test"), "--scripted", "--recipe",
                                  str(self.recipe)],
                                 capture_output=True, text=True, timeout=120)
        self.assertEqual(refused.returncode, 2)
        self.assert_counts_only(refused.stdout + refused.stderr)

    def test_the_generator_refuses_the_repo(self):
        remove_later(self, ROOT / "arena-hist-test")
        run = subprocess.run([sys.executable, "-I", str(MAKE), "--out", str(ROOT / "arena-hist-test")],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 2)
        self.assertFalse((ROOT / "arena-hist-test").exists())

    def test_the_generator_refuses_a_case_changed_repo_path(self):
        name = ROOT.name.upper() if ROOT.name.upper() != ROOT.name else ROOT.name.lower()
        changed = ROOT.parent / name
        if changed == ROOT or not changed.exists():
            self.skipTest("the disk tells case apart")
        remove_later(self, ROOT / "arena-hist-case")
        run = subprocess.run([sys.executable, "-I", str(MAKE), "--out", str(changed / "arena-hist-case")],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertFalse((ROOT / "arena-hist-case").exists())

    def demo(self):
        cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DEMO / "cards").iterdir())]
        return json.loads((DEMO / "summary.json").read_text(encoding="utf-8")), cards

    def test_demo_personas_equal_a_fresh_build_with_the_test_recipe(self):
        """The demo cards and summary were built with the test recipe and the scripted model, so a
        fresh build gives the same files, byte for byte (replay.jsonl is never copied to the demo)."""
        code, _, err = self.main()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.summary()["recipe_sha256"], fake_recipe.load().sha)
        names = sorted(p.name for p in (self.out / "cards").iterdir())
        self.assertEqual(names, sorted(p.name for p in (DEMO / "cards").iterdir()))
        self.assertEqual(len(names), 8)
        for name in names:
            self.assertEqual((self.out / "cards" / name).read_bytes(), (DEMO / "cards" / name).read_bytes(), name)
        self.assertEqual((self.out / "summary.json").read_bytes(), (DEMO / "summary.json").read_bytes())
        self.assertEqual(sorted(p.name for p in DEMO.iterdir()), ["cards", "recipe.example.json", "summary.json"])

    def test_the_demo_cards_hold_the_printing_cap(self):
        """DECISIONS item 33: the demo cards a printing want is on weigh at most its share, and the
        summary says so, under the test recipe and the example recipe alike."""
        demo, demo_cards = self.demo()
        for recipe in (fake_recipe.load(), recipe_mod.load(recipe_mod.EXAMPLE)):
            (name, rx, most), = recipe.capped
            mine = [c for c in demo_cards if any(rx.search(w) for w in c["want"])]
            with self.subTest(example=recipe.example):
                self.assertEqual((name, most), ("name printing", 0.25))
                self.assertTrue(mine)
                self.assertLessEqual(round(sum(c["arena_weight"] for c in mine), 3), most)
        (rec,) = demo["cards"]["capped_wants"]
        self.assertEqual((rec["name"], rec["most"]), ("name printing", 0.25))
        self.assertLessEqual(rec["share_used"], rec["most"])
        rx = fake_recipe.load().capped[0][1]
        self.assertEqual(rec["share_used"], round(sum(c["arena_weight"] for c in demo_cards
                                                      if any(rx.search(w) for w in c["want"])), 3))


class CappedWants(unittest.TestCase):
    """DECISIONS item 33: the name printing is at most 25% of practice customers. The recipe names
    a capped want and its most share; the card build holds the Arena's draws to it."""

    STYLE = {"length": "short", "language": {"arabic": 1.0, "franco": 0.0, "english": 0.0}, "voice_notes": 0.0,
             "opening": "price"}

    def items(self, *groups):
        """(n, worry, want) groups as tagged items."""
        return [{"label": "lost", "turns": [], "style": self.STYLE,
                 "tags": {"want": want, "worry": worry, "buy_trigger": "a clear answer", "patience": 0,
                          "no_budget": False}}
                for n, worry, want in groups for _ in range(n)]

    def weights(self, cards):
        return {(c["worry"], c["unwinnable"]): c["arena_weight"] for c in cards}

    def test_the_printing_cards_are_cut_to_the_share_and_the_rest_go_to_their_side(self):
        recipe = fake_recipe.load()
        cards, info = cards_mod.build(self.items((9, "other", "name printing on boots"),
                                                 (6, "price", "name printing on boots"),
                                                 (5, "size", "football boots"), (5, "just browsing", "a football kit")),
                                      recipe)
        self.assertEqual(self.weights(cards), {("other", False): 0.15, ("price", False): 0.1, ("size", False): 0.55,
                                               ("just browsing", True): 0.2})  # before: 0.36, 0.24, 0.2 and 0.2
        self.assertEqual(info["capped_wants"], [{"name": "name printing", "most": 0.25, "share_real": 0.6,
                                                 "share_used": 0.25}])
        self.assertEqual(info["unwinnable_share_used"], 0.2)
        self.assertAlmostEqual(sum(c["arena_weight"] for c in cards), 1.0, places=6)

    def test_under_the_share_nothing_moves_and_no_cap_named_none(self):
        groups = ((2, "other", "name printing on boots"), (6, "size", "football boots"), (2, "price", "boots"))
        cards, info = cards_mod.build(self.items(*groups), fake_recipe.load())
        self.assertEqual(self.weights(cards), {("other", False): 0.2, ("size", False): 0.6, ("price", False): 0.2})
        self.assertEqual(info["capped_wants"][0]["share_used"], 0.2)
        data = fake_recipe.data()
        del data["capped_wants"]
        cards, info = cards_mod.build(self.items((8, "other", "name printing on boots"), (2, "size", "boots")),
                                      recipe_mod.Recipe(data))
        self.assertEqual((self.weights(cards)[("other", False)], info["capped_wants"]), (0.8, []))

    def test_with_no_other_card_on_its_side_the_rest_cross_and_with_none_at_all_it_is_not_held(self):
        cards, info = cards_mod.build(self.items((20, "other", "name printing on boots"),
                                                 (5, "just browsing", "a football kit")), fake_recipe.load())
        self.assertEqual(self.weights(cards), {("other", False): 0.25, ("just browsing", True): 0.75})
        self.assertEqual((info["capped_wants"][0].get("crossed"), info["unwinnable_share_used"]), (True, 0.75))
        cards, info = cards_mod.build(self.items((3, "other", "name printing on boots"),
                                                 (1, "size", "printing a name")), fake_recipe.load())
        self.assertEqual(self.weights(cards), {("other", False): 0.75, ("size", False): 0.25})
        self.assertIs(info["capped_wants"][0]["held"], False)

    def test_a_bad_capped_want_is_refused(self):
        good = {"name": "name printing", "words": ["printing"], "most": 0.25}
        self.assertEqual(recipe_mod.Recipe({**fake_recipe.data(), "capped_wants": [good]}).capped[0][::2],
                         ("name printing", 0.25))
        for bad in ({**good, "most": 0}, {**good, "most": 1}, {**good, "most": True}, {**good, "most": "0.25"},
                    {**good, "most": float("nan")}, {**good, "words": []}, {**good, "words": [" "]},
                    {**good, "words": "printing"}, {**good, "name": "Printing"}, "printing", [good, good],
                    [dict(good, name=f"want {c}") for c in "abcde"]):
            with self.subTest(bad=bad), self.assertRaises(recipe_mod.hist.Refused) as e:
                recipe_mod.Recipe({**fake_recipe.data(), "capped_wants": bad if isinstance(bad, list) else [bad]})
            self.assertRegex(str(e.exception), r"^the recipe: (each )?capped[ _]want")


class TagRequest(unittest.TestCase):
    """A real persona build: reasoning tokens count against max_tokens, so at medium effort and
    1500 tokens half the answers came back cut off and the run stopped asking. The tagger asks at
    low effort with 4000 tokens, and that is what the request to Muse Spark Open holds."""

    def test_the_tagger_asks_at_low_effort_with_room_for_the_answer(self):
        import secrets
        from kit import net
        from tests.test_model_routes import Recorder, env_with
        recipe = fake_recipe.load()
        worry = sorted(recipe.worries)[0]
        rec = Recorder(json.dumps({"want": "boots", "worry": worry, "buy_trigger": "a clear price", "patience": 1,
                                   "no_budget": False}))
        env_with(self, BASETEN_API_KEY=secrets.token_urlsafe(24))  # a random stand-in, never a real key
        with mock.patch.object(net, "open_once", rec):
            tagger = pp.tag_mod.Tagger(cap=2, recipe=recipe)  # no model given: the one the persona build makes
            tags = tagger([{"from": "customer", "text": "hi"}], "lost")
        self.assertEqual(tags["worry"], worry)
        self.assertEqual(rec.seen[0].full_url, model_mod.ENDPOINT)
        self.assertEqual((rec.body()["reasoning_effort"], rec.body()["max_tokens"]), ("low", 4000))


class MaxFiles(Base):
    """A real chat export can hold more files than reflection/history.py lets one upload read.
    --max-files raises that cap for the persona build only, to 20000 at most; its default is the
    cap, and every other reader keeps it."""

    def capped(self, summary):
        return sum(n["files"] for n in summary["not_read"] if n["why"] == "over the file count cap")

    def test_it_raises_the_cap_for_the_persona_build_only(self):
        self.assertEqual((pp.hist.MAX_FILES, pp.hist.Reader().max_files), (5000, 5000))
        dest = self.base / "export.zip"
        zip_folder(self.hist, dest)
        with mock.patch.object(pp.hist, "MAX_FILES", 20):  # the cap made small: the made-up export has 31 files
            for n, source in enumerate((self.hist, dest)):
                with self.subTest(source=source.name):
                    code, _, err = self.main(source=source, out=self.base / f"default-{n}")
                    self.assertEqual(code, 0, err)
                    self.assertEqual(self.capped(self.summary(self.base / f"default-{n}")), 13)
                    code, _, err = self.main("--max-files", "33", source=source, out=self.base / f"raised-{n}")
                    self.assertEqual(code, 0, err)
                    s = self.summary(self.base / f"raised-{n}")
                    self.assertEqual((self.capped(s), s["read"]["whatsapp_chats"]), (0, 26))
            self.assertEqual((pp.hist.MAX_FILES, pp.hist.Reader().max_files), (20, 20))  # no other reader raised

    def test_over_twenty_thousand_is_refused_before_anything_is_read(self):
        for bad in ("20001", "0"):
            code, _, err = self.main("--max-files", bad)
            self.assertEqual(code, 2, bad)
            self.assertIn("--max-files is 1 to 20000", err)
            self.assertFalse(self.out.exists())
        self.assertEqual(self.main("--max-files", "20000")[0], 0)
        self.assertEqual(pp.MOST_FILES, 20000)
        with self.assertRaises(pp.hist.Refused):
            pp.run(self.hist, self.base / "lib", recipe=fake_recipe.load(), max_files=20001)
        self.assertFalse((self.base / "lib").exists())


if __name__ == "__main__":
    unittest.main()
