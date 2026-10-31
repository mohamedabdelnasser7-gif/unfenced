"""Practice customers grown from real chats (new, 2026-10-31; DECISIONS items 30, 32, 33, 48, 51):
the weight per loss, the caps held, easy wins and unclear chats skipped, cleaning applied, the
pool shared by siblings, refused across owners, and a new sibling at zero lessons facing the pool.
Made-up chats only, written into a test database; no model, no key."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arena import cards as cards_mod
from arena import grow, run
from arena import recipe as recipe_mod
from arena.scripted import ScriptedModel
from arena.tag import Tagger
from engine import plug as plug_mod
from kit.chats import Chats
from kit.db import Db
from reflection import history as hist
from reflection import night
from tests.fake_model import clean_env
from tests.test_arena_run import Agent, Customer, card

ROOT = Path(__file__).resolve().parent.parent
SALES_PLUG = ROOT / "sales" / "plug.json"
NOW = 1_800_000_000.0
H = 3600.0
SINCE = NOW - 48 * H
PHONE, NAME = "01012345678", "كريم"

# Made-up chats: (id, [(role, text, hours before NOW, step name)])
LOST = ("c-lost", [("user", f"بكام الجزمة السودا مقاس 43؟ اسمي {NAME} ورقمي {PHONE}", 80, None),
                   ("assistant", "الجزمة ب 1450 جنيه، المقاس 43 متاح", 79.9, None)])
EASY = ("c-easy", [("user", "عايز الجزمة البيضا مقاس 42", 70, None),
                   ("assistant", "السعر 1450 جنيه والشحن 60", 69.9, None),
                   ("user", "تمام اكدلي", 69.8, None),
                   ("assistant", "تم تسجيل الطلب", 69.7, None)])
HARD = ("c-hard", [("user", "السلام عليكم", 60, None), ("assistant", "اهلا بيك، تحب تشوف ايه؟", 59.9, None),
                   ("user", "عندكم جزمة حمرا؟", 59.8, None), ("assistant", "ايوه متاحة", 59.7, None),
                   ("user", "بكام؟", 59.6, None), ("assistant", "ب 1450 جنيه", 59.5, None),
                   ("user", "غالية شوية", 59.4, None), ("assistant", "دي جودة عالية", 59.3, None),
                   ("user", "طيب مقاس 44 متاح؟", 59.2, None), ("assistant", "متاح", 59.1, None),
                   ("user", "خلاص اكدلي", 59.0, None)])
NO_PRICE = ("c-noprice", [("user", "عندكم طقم كورة؟", 55, None),
                          ("assistant", "للأسف مش متاح دلوقتي", 54.9, None)])
OPEN = ("c-open", [("user", "بكام الجزمة؟", 3, None), ("assistant", "1450 جنيه", 2.9, None)])
PERSON = ("c-person", [("user", "الجزمة البيضا بكام؟", 66, None), ("assistant", "1450 جنيه", 65.9, None),
                       ("user", "اكدلي", 65.8, None), ("assistant", "تم تسجيل الطلب", 65.7, "person")])
ALL = (LOST, EASY, HARD, NO_PRICE, OPEN)


def folder(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def write_chats(db, chats, channel="whatsapp", customer="made-up", parent=None):
    """Steps: (role, text, hours before NOW, step name) or with a fifth part, the step's tool calls."""
    Chats(db)
    with db.tx() as c:
        for cid, steps in chats:
            times = [NOW - s[2] * H for s in steps]
            c.execute("INSERT INTO chats (id, channel, customer_id, parent_id, created_at, updated_at) "
                      "VALUES (?, ?, ?, ?, ?, ?)", (cid, channel, customer, parent, min(times), max(times)))
            for n, (role, text, h, name, *calls) in enumerate(steps, 1):
                c.execute("INSERT INTO steps (chat_id, n, role, content, name, tool_calls, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (cid, n, role, text, name, json.dumps(calls[0], ensure_ascii=False) if calls else None,
                           NOW - h * H))


def order_call(**args):
    """A made-up draft_order tool call, as kit/chats.py saves it on the agent's step."""
    return [{"id": "call-1", "type": "function",
             "function": {"name": "draft_order", "arguments": json.dumps(args, ensure_ascii=False)}}]


def recipe():
    return recipe_mod.load(recipe_mod.EXAMPLE)


def write_plug(where, agent, kind=None):
    d = json.loads(SALES_PLUG.read_text(encoding="utf-8"))
    d.pop("exam", None)
    d["agent"] = agent
    if kind:
        d["kind"] = kind
    where.mkdir(parents=True, exist_ok=True)
    (where / "plug.json").write_text(json.dumps(d), encoding="utf-8")


def grown_pool(test, owner, chats=ALL):
    """The owner's pool after one night on the made-up chats, with the scripted tagger."""
    db = Db(":memory:")
    test.addCleanup(db.close)
    write_chats(db, chats)
    pool = grow.Pool(owner, "sales")
    model = ScriptedModel(recipe())
    counts = grow.grow(db, pool, since=SINCE, until=NOW, tagger=Tagger(model=model, cap=50, recipe=recipe()))
    pool.rebuild(recipe())
    pool.save()
    return pool, counts, model


class WeightPerLoss(unittest.TestCase):
    def test_each_loss_adds_lost_weight(self):
        pool = grow.Pool(folder(self), "sales")
        self.assertEqual(pool.weight("persona-01"), 1)
        pool.record("persona-01", False)
        pool.record("persona-01", False)
        pool.record("persona-01", True)
        self.assertEqual(pool.weight("persona-01"), 1 + 2 * grow.LOST_WEIGHT)

    def test_a_card_that_beat_the_agent_is_drawn_more_often(self):
        pool = grow.Pool(folder(self), "sales")
        for _ in range(2):
            pool.record("persona-01", False)
        base = [card(1, "size"), card(2, "size")]
        got = {c["id"]: c["arena_weight"] for c in grow.deck(base, pool)}
        self.assertAlmostEqual(got["persona-01"] / got["persona-02"], 1 + 2 * grow.LOST_WEIGHT, places=3)
        self.assertEqual(base[0]["arena_weight"], 0.5)  # the base cards are never changed in place

    def test_no_loss_and_no_grown_card_leaves_the_cards_as_they_are(self):
        base = [card(1, "size"), card(2, "price")]
        self.assertIs(grow.deck(base, grow.Pool(folder(self), "sales")), base)

    def test_training_matches_are_counted_and_gate_matches_are_not(self):
        d = folder(self)
        pool = grow.Pool(d, "sales")
        arena = run.Arena([card(1, "size"), card(2, "size"), card(3, "size")], agent_model=Agent(),
                          customer_model=Customer(buyers=()), calls=run.Calls(d / "calls.json", 300, day="2026-10-31"),
                          state=d, trust={"matches": 2, "wins": 2, "zero_failed_checks": True}, matches=3, rounds=1,
                          held_out=["persona-03"], now=lambda: NOW, pool=pool)
        rep = arena.run()
        self.assertEqual(sum(r["played"] for r in pool.played.values()), rep["rounds"][0]["training"]["played"])
        self.assertEqual(sum(r["lost"] for r in pool.played.values()), 3)
        self.assertNotIn("persona-03", pool.played)


class CapsHeld(unittest.TestCase):
    def deck(self, losses, loser="persona-01"):
        pool = grow.Pool(folder(self), "sales")
        for _ in range(losses):
            pool.record(loser, False)
        base = [dict(card(1, "price", 0.2), want=["name printing on boots"]), card(2, "size", 0.4),
                card(3, "trust", 0.2),
                dict(card(4, "just browsing", 0.2), unwinnable=True, why_unwinnable="just browsing")]
        return grow.deck(base, pool)

    def test_printing_stays_at_most_a_quarter_after_many_losses(self):
        got = self.deck(8)
        printing = sum(c["arena_weight"] for c in got if any("printing" in w for w in c["want"]))
        self.assertLessEqual(printing, 0.25)
        self.assertGreater(printing, 0.2)  # it did grow, up to the cap

    def test_the_unwinnable_share_holds(self):
        for loser in ("persona-01", "persona-04"):  # a winnable card that beats the agent, then an unwinnable one
            got = self.deck(8, loser)
            total = sum(c["arena_weight"] for c in got)
            self.assertAlmostEqual(total, 1.0, places=3)
            self.assertAlmostEqual(sum(c["arena_weight"] for c in got if c["unwinnable"]) / total, 0.2, places=3)

    def test_grown_cards_keep_both_caps(self):
        owner = folder(self)
        pool, _, _ = grown_pool(self, owner)
        base = [dict(card(1, "price", 0.5), want=["name printing on boots"]),
                dict(card(2, "just browsing", 0.5), unwinnable=True, why_unwinnable="just browsing")]
        got = grow.deck(base, pool)
        self.assertTrue(any(c["id"].startswith("grown-") for c in got))
        self.assertLessEqual(sum(c["arena_weight"] for c in got if any("printing" in w for w in c["want"])), 0.25)


    def test_an_owner_recipe_with_no_capped_want_adds_no_cap(self):
        data = json.loads(recipe_mod.EXAMPLE.read_text(encoding="utf-8"))
        data.pop("capped_wants")
        pool = grow.Pool(folder(self), "sales")
        pool.rebuild(recipe_mod.Recipe(data))
        self.assertEqual(pool.capped, [])
        for _ in range(8):
            pool.record("persona-01", False)
        base = [dict(card(1, "price", 0.2), want=["name printing on boots"]), card(2, "size", 0.8)]
        got = {c["id"]: c["arena_weight"] for c in grow.deck(base, pool)}
        self.assertGreater(got["persona-01"], 0.25)


class WhichChats(unittest.TestCase):
    def setUp(self):
        self.owner = folder(self)
        self.pool, self.counts, self.model = grown_pool(self, self.owner)

    def test_lost_and_hard_kept_easy_wins_and_unclear_skipped(self):
        self.assertEqual(self.counts["added"], 2)
        self.assertEqual((self.counts["lost"], self.counts["hard"]), (1, 1))
        self.assertEqual(self.counts["easy wins, skipped"], 1)
        self.assertEqual(self.counts["unclear, skipped"], 2)
        self.assertEqual(sorted(i["label"] for i in self.pool.items), ["lost", "won"])
        self.assertEqual(len(self.model.calls), 2)  # nothing skipped ever reached the tagger

    def test_a_chat_is_read_once_and_a_chat_still_open_waits(self):
        self.assertTrue(all(self.pool.has(c) for c in ("c-lost", "c-hard", "c-easy", "c-noprice")))
        self.assertFalse(self.pool.has("c-open"))
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, ALL)
        again = grow.grow(db, grow.Pool(self.owner, "sales"), since=SINCE, until=NOW,
                          tagger=Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe()))
        self.assertEqual((again.get("added", 0), again["already read"]), (0, 4))

    def test_a_person_stepping_in_makes_a_win_hard(self):
        _, counts, _ = grown_pool(self, folder(self), chats=(PERSON,))
        self.assertEqual(counts.get("hard"), 1)
        chat = hist.Chat(source=hist.WHATSAPP, key="x", place=0, messages=[])
        self.assertFalse(grow.hard(chat, {"person": False, "check_failed": False}))
        self.assertTrue(grow.hard(chat, {"person": False, "check_failed": True}))


class CleaningApplied(unittest.TestCase):
    def test_no_name_or_number_in_the_pool_or_sent_to_the_tagger(self):
        owner = folder(self)
        _, _, model = grown_pool(self, owner)
        saved = (owner / "practice-sales.json").read_text(encoding="utf-8")
        sent = json.dumps(model.calls, ensure_ascii=False)
        for text in (saved, sent):
            self.assertNotIn(PHONE, text)
            self.assertNotIn(NAME, text)
        self.assertIn("[phone]", saved)
        self.assertIn("1450 جنيه", saved)  # prices stay: they are what the customers are about


class NamesFromOrders(unittest.TestCase):
    """What the customer gave for an order (draft_order's name, print name, address and phone) is
    masked wherever it is typed: bare, with no cue word, in any case, in a later message too."""

    def grow_one(self, steps, other=()):
        owner = folder(self)
        pool, counts, model = grown_pool(self, owner, chats=(("c-order", steps), *other))
        self.assertGreaterEqual(counts.get("added", 0), 1, counts)
        saved = (owner / "practice-sales.json").read_text(encoding="utf-8")
        return saved, json.dumps(model.calls, ensure_ascii=False)

    def steps(self, typed, later, args):
        return [("user", "بكام الجزمة السودا مقاس 38؟", 70, None), ("assistant", "ب 1450 جنيه", 69.9, None),
                ("user", typed, 69.8, None),
                ("assistant", "", 69.7, None, order_call(items=[{"product": "boots", "size": "38"}], **args)),
                ("assistant", "تمام، الطلب جاهز. اكدلي؟", 69.6, None),
                ("user", "غالية شوية بصراحة", 69.5, None), ("assistant", "دي جودة عالية", 69.4, None),
                ("user", "طب هفكر", 69.3, None), ("assistant", "براحتك", 69.2, None),
                ("user", later, 69.1, None), ("assistant", "تحت امرك", 69.0, None),
                ("user", "تمام اكدلي", 68.9, None), ("assistant", "تم تسجيل الطلب", 68.8, None)]

    def test_a_full_name_typed_bare_with_no_cue(self):
        saved, sent = self.grow_one(self.steps("تمام هاخدها، نورهان الشربيني", "اوك",
                                               {"name": "نورهان الشربيني", "governorate": "Cairo", "address": "x x x x x"}))
        for text in (saved, sent):
            self.assertNotIn("نورهان", text)
            self.assertNotIn("الشربيني", text)

    def test_an_arabic_surname_alone_in_a_later_message(self):
        saved, sent = self.grow_one(self.steps("تمام هاخدها", "الشربيني معاك تاني، الاوردر اتأخر",
                                               {"name": "نورهان الشربيني", "governorate": "Cairo", "address": "x x x x x"}))
        for text in (saved, sent):
            self.assertNotIn("الشربيني", text)
        self.assertIn("الاوردر اتأخر", saved)  # the rest of the line stays

    def test_a_latin_lowercase_name(self):
        saved, sent = self.grow_one(self.steps("ok take it, karim tawfik mansour", "mansour here again, any news?",
                                               {"name": "Karim Tawfik Mansour", "governorate": "Cairo", "address": "x x x x x"}))
        for text in (saved, sent):
            for word in ("karim", "tawfik", "mansour"):
                self.assertNotIn(word, text.casefold())

    def test_a_name_from_one_chat_is_masked_in_another_chat_of_the_night(self):
        other = ("c-other", [("user", "سلام، انا سلمى الشربيني اختها", 60, None), ("assistant", "ب 1450 جنيه", 59.9, None)])
        saved, sent = self.grow_one(self.steps("تمام هاخدها", "اوك",
                                               {"name": "سلمى الشربيني", "governorate": "Cairo", "address": "x x x x x"}),
                                    other=(other,))
        for text in (saved, sent):
            self.assertNotIn("الشربيني", text)

    def test_the_address_and_the_print_name_given_for_the_order(self):
        args = {"items": [{"product": "printing", "print_name": "Zorvanello"}], "name": "x y",
                "governorate": "Cairo", "address": "الياسمين الكوثر"}
        steps = self.steps("واكتب عليها Zorvanello", "نفس المكان اللي فات: الياسمين الكوثر", {})
        steps[3] = ("assistant", "", 69.7, None, order_call(**args))
        saved, sent = self.grow_one(steps)
        for text in (saved, sent):
            self.assertNotIn("الياسمين", text)
            self.assertNotIn("Zorvanello", text)

    def test_the_chat_carries_the_number_and_what_was_typed(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, [("c-order", self.steps("تمام", "اوك", {"name": "نورهان الشربيني", "phone": "0100 111 2233",
                                                                "governorate": "Cairo", "address": "شارع واحد اتنين"}))],
                    customer="201009998877")
        (_, chat, _), = grow.real_chats(db, SINCE - 96 * H, NOW)
        self.assertEqual(chat.phone, "201009998877")
        self.assertEqual(chat.names, {"نورهان الشربيني"})
        self.assertEqual(chat.typed_phones, {"201009998877", "201001112233"})
        self.assertEqual(chat.addresses, {"شارع واحد اتنين"})


class Siblings(unittest.TestCase):
    def setUp(self):
        self.owner = folder(self)
        write_plug(self.owner / "store_a", "store_a", "sales")
        write_plug(self.owner / "store_b", "store_b", "sales")
        write_plug(self.owner / "other", "other_kind")

    def test_plugs_of_one_kind_in_one_owner_folder_share_the_pool(self):
        a, b = grow.for_state(self.owner / "store_a"), grow.for_state(self.owner / "store_b")
        self.assertEqual(a.path, b.path)
        self.assertEqual(a.path, self.owner / "practice-sales.json")
        self.assertEqual(grow.siblings(self.owner, "sales"), ["store_a", "store_b"])
        grown_pool(self, self.owner)
        self.assertEqual(len(grow.for_state(self.owner / "store_b").items), 2)

    def test_a_plug_of_another_kind_has_its_own_pool(self):
        grown_pool(self, self.owner)
        other = grow.for_state(self.owner / "other")
        self.assertEqual(other.path.name, "practice-other_kind.json")
        self.assertEqual(other.items, [])

    def test_the_plug_kind(self):
        self.assertEqual(plug_mod.load(SALES_PLUG).kind, "sales")
        self.assertEqual(plug_mod.load(self.owner / "store_a" / "plug.json").kind, "sales")
        self.assertEqual(plug_mod.load(self.owner / "other" / "plug.json").kind, "other_kind")
        d = json.loads(SALES_PLUG.read_text(encoding="utf-8"))
        d.pop("exam")
        with self.assertRaises(ValueError):
            plug_mod.from_dict({**d, "kind": "Sales Agent"})


class AcrossOwners(unittest.TestCase):
    def setUp(self):
        self.a, self.b = folder(self), folder(self)
        grown_pool(self, self.b)

    def test_a_pool_path_in_another_owner_folder_is_refused(self):
        with self.assertRaises(grow.Refused):
            grow.Pool(self.a, "sales", path=self.b / "practice-sales.json")

    def test_a_link_to_another_owner_pool_is_refused(self):
        os.symlink(self.b / "practice-sales.json", self.a / "practice-sales.json")
        with self.assertRaises(grow.Refused):
            grow.Pool(self.a, "sales")

    def test_another_owner_never_sees_the_pool(self):
        self.assertEqual(grow.for_state(self.a).items, [])
        self.assertEqual(len(grow.for_state(self.b).items), 2)

    def test_a_kind_that_could_name_a_path_and_a_folder_in_the_repo_are_refused(self):
        for kind in ("../sales", "sales/x", "Sales", ""):
            with self.assertRaises(grow.Refused):
                grow.Pool(self.a, kind)
        with self.assertRaises(grow.Refused):
            grow.Pool(ROOT / "sales", "sales")


class ZeroLessonsAtStart(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.owner = folder(self)
        write_plug(self.owner / "store_a", "store_a", "sales")
        write_plug(self.owner / "store_b", "store_b", "sales")
        grown_pool(self, self.owner)
        self.cards = self.owner / "cards"
        self.cards.mkdir()
        for c in (card(1, "size"), card(2, "size")):
            (self.cards / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")

    def test_a_new_sibling_starts_with_zero_lessons_and_faces_the_grown_pool(self):
        db_path = self.owner / "store_b" / "ascent.db"
        from reflection.lessons import Lessons
        db = Db(str(db_path))
        Lessons(db)
        with db.tx() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM lessons").fetchone()[0], 0)
        db.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.main(["--cards", str(self.cards), "--matches", "1", "--rounds", "1", "--db", str(db_path),
                             "--json"], agent_model=Agent(), customer_model=Customer(buyers=("size", "price", "other")))
        self.assertIn(code, (0, 1))
        rep = json.loads(out.getvalue())
        drawn = rep["training_cards"] + rep["held_out_cards"]
        self.assertTrue(any(i.startswith("grown-") for i in drawn), drawn)
        self.assertEqual(rep["pool"]["siblings"], ["store_a", "store_b"])
        self.assertTrue((self.owner / "store_b" / run.MATCHES_FILE).is_file())  # its own Arena files stay its own
        self.assertFalse((self.owner / run.MATCHES_FILE).exists())


class FoldedCards(unittest.TestCase):
    def test_cards_built_with_the_pool_take_no_grown_card_again(self):
        owner = folder(self)
        pool, _, _ = grown_pool(self, owner)
        items = [{**i, "grown": True} for i in pool.items]
        built, _ = cards_mod.build(items, recipe())
        self.assertEqual(sum(c["grown"] for c in built), len(items))
        got = grow.deck(built, pool)
        self.assertFalse(any(c["id"].startswith("grown-") for c in got))
        plain, _ = cards_mod.build(pool.items, recipe())
        self.assertNotIn("grown", plain[0])


class PersonasState(unittest.TestCase):
    def test_a_state_folder_in_the_repo_outside_data_is_refused(self):
        from arena import personas
        out = folder(self) / "out"
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = personas.main(["--source", str(folder(self)), "--out", str(out), "--recipe", str(recipe_mod.EXAMPLE),
                                  "--state", str(ROOT / "sales"), "--scripted"])
        self.assertEqual(code, 2)
        self.assertIn("inside the repo", err.getvalue())
        self.assertFalse(out.exists())


class NightStep(unittest.TestCase):
    """main() for the Sales agent's plug, with the night study itself stood in: the step after it."""

    def setUp(self):
        self.dir = folder(self)
        self.db_path = self.dir / "ascent.db"
        db = Db(str(self.db_path))
        write_chats(db, ALL)
        db.close()
        rep = {"agent": "sales", "window": {"since": SINCE, "until": NOW}, "snapshot": {}}
        for p in (mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]),
                  mock.patch.object(night, "night", return_value=rep), mock.patch("kit.model.Model"),
                  mock.patch.object(grow, "tag_model", side_effect=lambda: ScriptedModel(recipe()))):
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(SALES_PLUG), "--db", str(self.db_path), "--json", *extra])
        self.assertEqual(code, 0, err.getvalue())
        return json.loads(sorted(self.dir.glob("night-sales-*.json"))[0].read_text(encoding="utf-8"))

    def test_the_night_grows_the_owner_pool(self):
        rep = self.run_main("--recipe", str(recipe_mod.EXAMPLE))
        self.assertEqual(rep["practice"]["added"], 2)
        self.assertEqual(rep["practice"]["easy wins, skipped"], 1)
        self.assertIsNone(rep["practice"]["stopped"])
        self.assertEqual(len(grow.Pool(self.dir, "sales").items), 2)
        self.assertTrue(json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"] == 2)

    def test_with_no_recipe_no_chat_is_read(self):
        rep = self.run_main()
        self.assertTrue(rep["practice"]["stopped"].startswith("no recipe"))
        self.assertFalse((self.dir / "practice-sales.json").exists())


if __name__ == "__main__":
    unittest.main()
