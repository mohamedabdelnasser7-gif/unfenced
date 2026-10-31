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


def write_plug(where, agent, kind=None, owner=None):
    d = json.loads(SALES_PLUG.read_text(encoding="utf-8"))
    d.pop("exam", None)
    d["agent"] = agent
    if kind:
        d["kind"] = kind
    if owner:
        d["owner"] = owner
    where.mkdir(parents=True, exist_ok=True)
    (where / "plug.json").write_text(json.dumps(d), encoding="utf-8")


def write_owner(folder, name):
    """The owner marker: folder is the owner's state folder of the plugs naming name."""
    (folder / grow.OWNER_FILE).write_text(json.dumps({"owner": name}), encoding="utf-8")


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


def train_of(base, pool, held=()):
    """The training cards grow.decks gives, as {id: weight}."""
    return {c["id"]: c["arena_weight"] for c in grow.decks(base, pool, set(held))[0]}


def lose(pool, card, n):
    for _ in range(n):
        pool.record(card, False)


class WeightPerLoss(unittest.TestCase):
    def test_each_loss_adds_lost_weight(self):
        pool = grow.Pool(folder(self), "sales")
        c = card(1, "size")
        self.assertEqual(pool.weight(c), 1)
        lose(pool, c, 2)
        pool.record(c, True)
        self.assertEqual(pool.weight(c), 1 + 2 * grow.LOST_WEIGHT)

    def test_a_card_that_beat_the_agent_is_drawn_more_often(self):
        pool = grow.Pool(folder(self), "sales")
        base = [card(1, "size"), card(2, "price")]
        lose(pool, base[0], 2)
        got = train_of(base, pool)
        self.assertAlmostEqual(got["persona-01"] / got["persona-02"], 1 + 2 * grow.LOST_WEIGHT, places=3)
        self.assertEqual(base[0]["arena_weight"], 0.5)  # the base cards are never changed in place

    def test_no_loss_and_no_grown_card_keeps_the_weights(self):
        base = [card(1, "size", 0.6), card(2, "price", 0.4)]
        self.assertEqual(train_of(base, grow.Pool(folder(self), "sales")), {"persona-01": 0.6, "persona-02": 0.4})

    def test_training_matches_are_counted_and_gate_matches_are_not(self):
        d = folder(self)
        pool = grow.Pool(d, "sales")
        arena = run.Arena([card(1, "size"), card(2, "price"), card(3, "trust")], agent_model=Agent(),
                          customer_model=Customer(buyers=()), calls=run.Calls(d / "calls.json", 300, day="2026-10-31"),
                          state=d, trust={"matches": 2, "wins": 2, "zero_failed_checks": True}, matches=3, rounds=1,
                          held_out=["persona-03"], now=lambda: NOW, pool=pool)
        rep = arena.run()
        self.assertEqual(sum(r["played"] for r in pool.played.values()), rep["rounds"][0]["training"]["played"])
        self.assertEqual(sum(r["lost"] for r in pool.played.values()), 3)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 2)
        self.assertFalse(pool.trained(card(3, "trust")))


class LossesByGroup(unittest.TestCase):
    """Losses are counted by the card's group (worry and why it will not buy), at most
    MAX_COUNTED_LOSSES of them, so a renumbered card keeps its group's count and no card runs away."""

    def setUp(self):
        self.pool = grow.Pool(folder(self), "sales")

    def test_a_renumbered_card_keeps_its_group_losses_and_a_new_card_under_an_old_id_does_not(self):
        lose(self.pool, card(3, "price"), 2)
        self.assertEqual(self.pool.weight(card(5, "price")), 1 + 2 * grow.LOST_WEIGHT)  # the next build calls it persona-05
        self.assertEqual(self.pool.weight(card(3, "size")), 1)  # persona-03 is another group now
        self.assertEqual(list(self.pool.played), ["base:price"])

    def test_why_it_will_not_buy_and_grown_cards_are_groups_of_their_own(self):
        nobudget = dict(card(8, "price"), unwinnable=True, why_unwinnable="no budget")
        lose(self.pool, nobudget, 1)
        self.assertEqual(self.pool.weight(card(2, "price")), 1)
        self.assertEqual(grow.group(nobudget), "base:price:no-budget")
        lose(self.pool, dict(card(1, "price"), id="grown-price"), 1)
        self.assertEqual(self.pool.weight(card(2, "price")), 1)
        self.assertEqual(self.pool.weight(dict(card(1, "price"), id="grown-price")), 1 + grow.LOST_WEIGHT)

    def test_at_most_max_counted_losses_count(self):
        self.assertEqual((grow.LOST_WEIGHT, grow.MAX_COUNTED_LOSSES), (3, 5))
        c = card(1, "price")
        lose(self.pool, c, grow.MAX_COUNTED_LOSSES + 95)
        self.assertEqual(self.pool.played["base:price"]["lost"], 100)  # every loss is kept, only 5 count
        self.assertEqual(self.pool.weight(c), 1 + grow.LOST_WEIGHT * grow.MAX_COUNTED_LOSSES)

    def test_rows_saved_under_a_card_id_or_with_bad_counts_are_dropped(self):
        self.pool.path.write_text(json.dumps({"kind": "sales", "played": {
            "persona-01": {"played": 3, "lost": 3}, "base:price": {"played": 2, "lost": 1},
            "base:size": {"played": True, "lost": 0}, "base:trust": {"played": 1, "lost": -1}}}), encoding="utf-8")
        self.assertEqual(grow.Pool(self.pool.owner, "sales").played, {"base:price": {"played": 2, "lost": 1}})


class CapsHeld(unittest.TestCase):
    def base(self):
        return [dict(card(1, "price", 0.2), want=["name printing on boots"]), card(2, "size", 0.4),
                card(3, "trust", 0.2),
                dict(card(4, "just browsing", 0.2), unwinnable=True, why_unwinnable="just browsing")]

    def deck(self, losses, loser=0):
        pool = grow.Pool(folder(self), "sales")
        base = self.base()
        lose(pool, base[loser], losses)
        return grow.decks(base, pool, set())[0]

    def test_printing_stays_at_most_a_quarter_after_many_losses(self):
        got = self.deck(8)
        printing = sum(c["arena_weight"] for c in got if any("printing" in w for w in c["want"]))
        self.assertLessEqual(printing, 0.25)
        self.assertGreater(printing, 0.2)  # it did grow, up to the cap

    def test_the_unwinnable_share_holds(self):
        for loser in (0, 3):  # a winnable card that beats the agent, then an unwinnable one
            got = self.deck(8, loser)
            total = sum(c["arena_weight"] for c in got)
            self.assertAlmostEqual(total, 1.0, places=3)
            self.assertAlmostEqual(sum(c["arena_weight"] for c in got if c["unwinnable"]) / total, 0.2, places=3)

    def test_grown_cards_keep_both_caps(self):
        owner = folder(self)
        pool, _, _ = grown_pool(self, owner)
        base = [dict(card(1, "price", 0.5), want=["name printing on boots"]),
                dict(card(2, "just browsing", 0.5), unwinnable=True, why_unwinnable="just browsing")]
        got = grow.decks(base, pool, set())[0]
        self.assertTrue(any(c["id"].startswith("grown-") for c in got))
        self.assertLessEqual(sum(c["arena_weight"] for c in got if any("printing" in w for w in c["want"])), 0.25)

    def test_an_owner_recipe_with_no_capped_want_adds_no_cap(self):
        data = json.loads(recipe_mod.EXAMPLE.read_text(encoding="utf-8"))
        data.pop("capped_wants")
        pool = grow.Pool(folder(self), "sales")
        pool.rebuild(recipe_mod.Recipe(data))
        self.assertEqual(pool.capped, [])
        base = [dict(card(1, "price", 0.2), want=["name printing on boots"]), card(2, "size", 0.8)]
        lose(pool, base[0], 8)
        self.assertGreater(train_of(base, pool)["persona-01"], 0.25)


def demo_cards():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "demo" / "personas" / "cards").glob("*.json"))]


def arena_with(test, cards, pool, **kw):
    d = folder(test)
    return run.Arena(cards, agent_model=Agent(), customer_model=Customer(buyers=()),
                     calls=run.Calls(d / "calls.json", 300, day="2026-10-31"), state=d,
                     trust={"matches": 2, "wins": 2, "zero_failed_checks": True}, matches=1, rounds=1,
                     now=lambda: NOW, pool=pool, **kw)


def share(cards, rx):
    total = sum(c["arena_weight"] for c in cards)
    return sum(c["arena_weight"] for c in cards if any(rx.search(w) for w in c["want"])) / total


class GateAndTraining(unittest.TestCase):
    """The base cards split first and the split kept; grown and trained cards never in the gate;
    the gate at weights before any loss; the caps held on the training draws and on the gate's."""

    def setUp(self):
        self.base = demo_cards()
        self.rx = recipe().capped[0][1]

    def test_printing_and_the_unwinnable_share_hold_on_the_training_draws(self):
        printing = next(c for c in self.base if any(self.rx.search(w) for w in c["want"]))
        unwinnable = sum(c["arena_weight"] for c in self.base if c["unwinnable"]) / sum(c["arena_weight"] for c in self.base)
        for seed in range(6):
            pool = grow.Pool(folder(self), "sales")
            lose(pool, printing, 50)
            a = arena_with(self, self.base, pool, seed=seed)
            self.assertNotIn(printing["id"], [c["id"] for c in a.held])
            self.assertLessEqual(share(a.train, self.rx), 0.25 + 1e-9, seed)
            self.assertGreater(share(a.train, self.rx), 0.2, seed)
            got = sum(c["arena_weight"] for c in a.train if c["unwinnable"]) / sum(c["arena_weight"] for c in a.train)
            self.assertAlmostEqual(got, unwinnable, places=2)
            self.assertAlmostEqual(sum(c["arena_weight"] for c in a.gate_cards), 1.0, places=3)
            self.assertLessEqual(share(a.gate_cards, self.rx), 0.25 + 1e-9)

    def test_the_gate_draws_at_its_weights_before_any_loss(self):
        pool = grow.Pool(folder(self), "sales")
        held = {"persona-02", "persona-04"}
        fresh = {c["id"]: c["arena_weight"] for c in grow.decks(self.base, pool, held)[1]}
        lose(pool, self.base[1], 10)  # persona-02 lost ten times, in some earlier run
        got = {c["id"]: c["arena_weight"] for c in grow.decks(self.base, pool, held)[1]}
        self.assertEqual(got, fresh)
        self.assertAlmostEqual(got["persona-02"] / got["persona-04"], 0.179 / 0.107, places=3)

    def test_printing_is_capped_on_the_gate_draws_on_their_own(self):
        pool = grow.Pool(folder(self), "sales")
        gate = grow.decks(self.base, pool, {"persona-05", "persona-06"})[1]
        self.assertEqual(sorted(c["id"] for c in gate), ["persona-05", "persona-06"])
        self.assertLessEqual(share(gate, self.rx), 0.25)

    def test_printing_stays_at_most_a_quarter_of_the_gate_when_rounding_would_push_it_over(self):
        # cap_wants rounds each weight to 3 places: on these gate cards alone printing would draw
        # 0.25025 of the gate; the gate's own hold (grow._hold) brings it back to 0.25 or under
        weights = (0.919, 0.284, 0.111, 0.806)
        base = [dict(card(i, "price", w), want=["name printing on boots"] if i == 1 else ["boots"])
                for i, w in enumerate(weights, 1)]
        gate = grow.decks(base, grow.Pool(folder(self), "sales"), {c["id"] for c in base})[1]
        self.assertEqual(len(gate), 4)
        self.assertLessEqual(share(gate, self.rx), 0.25)
        self.assertGreater(share(gate, self.rx), 0.2499)

    def test_the_split_stays_the_same_when_other_cards_train(self):
        pool = grow.Pool(folder(self), "sales")
        first = sorted(c["id"] for c in arena_with(self, self.base, pool, seed=0).held)
        self.assertEqual(first, ["persona-01", "persona-02"])
        pool.record(self.base[3], False)  # persona-04 trains: a fresh draw at seed 0 would now hold persona-06
        self.assertNotEqual(sorted(c["id"] for c in run.split(self.base, seed=0, never={"persona-04"})[1]), first)
        self.assertEqual(sorted(c["id"] for c in arena_with(self, self.base, pool, seed=0).held), first)

    def test_the_split_stays_the_same_as_the_pool_grows(self):
        owner = folder(self)
        pool = grow.Pool(owner, "sales")
        first = sorted(c["id"] for c in arena_with(self, self.base, pool).held)
        pool.save()
        grown_pool(self, owner)  # the night adds grown cards to the same pool
        pool = grow.Pool(owner, "sales")
        self.assertTrue(pool.cards)
        self.assertEqual(pool.split["held"], first)
        a = arena_with(self, self.base, pool)
        self.assertEqual(sorted(c["id"] for c in a.held), first)
        self.assertFalse(any(c["id"].startswith("grown-") for c in a.held + a.gate_cards))
        self.assertTrue(any(c["id"].startswith("grown-") for c in a.train))

    def test_a_card_that_has_trained_is_never_held_out(self):
        # round 2 of the feed: the saved split stays while its ids and seed match (a card of the
        # same worry training is no reason to drop it); a new draw and --held-out leave it out
        pool = grow.Pool(folder(self), "sales")
        held = [c["id"] for c in arena_with(self, self.base, pool).held]
        pool.record(next(c for c in self.base if c["id"] == held[0]), True)  # its group trained
        self.assertEqual([c["id"] for c in arena_with(self, self.base, pool).held], held)
        again = [c["id"] for c in arena_with(self, self.base, pool, seed=1).held]
        self.assertNotIn(held[0], again)
        with self.assertRaises(run.Refused):
            arena_with(self, self.base, pool, held_out=[held[0]])

    def test_a_grown_card_never_takes_the_gate(self):
        cards = self.base + [dict(card(9, "size"), id="grown-size")]
        for seed in range(8):
            _, held = run.split(cards, seed=seed)
            self.assertNotIn("grown-size", [c["id"] for c in held])
        with self.assertRaises(run.Refused):
            run.split(cards, ["grown-size"])

    def test_a_new_seed_or_new_base_cards_draw_a_new_split(self):
        pool = grow.Pool(folder(self), "sales")
        arena_with(self, self.base, pool, seed=0)
        self.assertEqual(pool.split["seed"], 0)
        arena_with(self, self.base[:-1], pool, seed=0)
        self.assertEqual(pool.split["cards"], sorted(c["id"] for c in self.base[:-1]))


class SplitKept(unittest.TestCase):
    """Review and red team round 2 of the feed (2026-10-31): the saved split stays while its ids and
    seed match; a new one prefers cards that have not trained and tops up from the least played;
    a saved split split() refuses is drawn again; --held-out for one run leaves the saved split."""

    def setUp(self):
        self.base = demo_cards()
        self.pool = grow.Pool(folder(self), "sales")

    def held(self, cards, held_out=None, seed=0):
        return sorted(c["id"] for c in run.fixed_split(cards, held_out, seed, self.pool)[1])

    def train_all(self, train):
        for c in train:
            self.pool.record(c, True)

    def test_two_cards_of_one_worry_the_second_run_keeps_the_gate(self):
        cards = [card(1, "size"), card(2, "size"), card(3, "price")]
        train, held = run.fixed_split(cards, None, 0, self.pool)
        self.train_all(train)  # the other size card trained: every worry has trained now
        self.assertTrue(all(self.pool.trained(c) for c in cards))
        self.assertEqual(self.held(cards), sorted(c["id"] for c in held))

    def test_one_held_out_run_leaves_the_saved_gate(self):
        first = self.held(self.base)
        self.assertEqual(first, ["persona-01", "persona-02"])
        self.train_all(c for c in self.base if c["id"] not in first)
        saved = dict(self.pool.split)
        train, _ = run.fixed_split(self.base, ["persona-01"], 0, self.pool)
        self.train_all(train)  # persona-02 trains in this one run
        self.assertEqual(self.pool.split, saved)
        self.assertEqual(self.held(self.base), first)

    def test_a_rebuild_where_every_card_has_trained_still_draws_a_gate(self):
        self.train_all(self.base)
        rebuilt = [c for c in self.base if c["id"] != "persona-01"]
        held = self.held(rebuilt)
        self.assertEqual(len(held), max(1, round(run.HELD_OUT_SHARE * len(rebuilt))))
        self.assertEqual(self.pool.split["held"], held)

    def test_the_top_up_takes_the_least_played_first(self):
        cards = [card(i, w) for i, w in enumerate(("size", "price", "trust", "delivery", "fit"), 1)]
        for c, n in zip(cards, (5, 1, 4, 2, 3)):
            for _ in range(n):
                self.pool.record(c, True)
        self.assertEqual(self.held(cards), ["persona-02", "persona-04"])  # 1 and 2 plays

    def test_a_new_split_holds_the_untrained_cards_spread_over_worries(self):
        cards = [card(i, "size") for i in range(1, 9)] + [card(9, "price"), card(10, "trust")]
        self.pool.record(cards[-1], True)
        for seed in range(6):
            self.pool.split = None
            held = self.held(cards, seed=seed)
            self.assertEqual(len(held), 3)
            self.assertIn("persona-09", held, seed)
            self.assertNotIn("persona-10", held, seed)

    def test_a_saved_split_split_refuses_is_drawn_again(self):
        first = self.held(self.base)
        changed = [dict(c, unwinnable=True) if c["id"] in first else c for c in self.base]  # same ids
        held = self.held(changed)
        self.assertTrue(set(held).isdisjoint(first))
        self.assertEqual(self.pool.split["held"], held)

    def test_another_seed_draws_a_new_split(self):
        self.held(self.base, seed=0)
        self.held(self.base, seed=1)
        self.assertEqual(self.pool.split["seed"], 1)

    def test_a_saved_split_with_no_held_card_or_one_not_in_its_cards_is_dropped_on_load(self):
        owner = folder(self)
        for split in ({"cards": ["persona-01", "persona-02"], "seed": 0, "held": []},
                      {"cards": ["persona-01", "persona-02"], "seed": 0, "held": ["persona-09"]}):
            (owner / "practice-sales.json").write_text(json.dumps({"kind": "sales", "split": split}), encoding="utf-8")
            self.assertIsNone(grow.Pool(owner, "sales").split, split)


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
        self.assertEqual({c: self.pool.progress(c)[0] for c in ("c-lost", "c-hard", "c-easy", "c-noprice")},
                         {"c-lost": 2, "c-hard": 11, "c-easy": 4, "c-noprice": 2})
        self.assertIsNone(self.pool.progress("c-open"))
        self.assertEqual(self.pool.pending, {"c-open": 1})  # still open: read first the next night
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


def add_steps(db, cid, steps):
    """More steps on a chat already written: (role, text, hours before NOW, step name)."""
    with db.tx() as c:
        n0 = c.execute("SELECT COALESCE(MAX(n), 0) FROM steps WHERE chat_id = ?", (cid,)).fetchone()[0]
        for k, (role, text, h, name) in enumerate(steps, 1):
            c.execute("INSERT INTO steps (chat_id, n, role, content, name, at) VALUES (?, ?, ?, ?, ?, ?)",
                      (cid, n0 + k, role, text, name, NOW - h * H))
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (NOW - steps[-1][2] * H, cid))


class Reading(unittest.TestCase):
    """Progress per chat by the last step read; only settled talks marked; leftovers first."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.pool = grow.Pool(folder(self), "sales")
        self.model = ScriptedModel(recipe())

    def night(self, until, most=grow.MAX_NEW, model=None):
        return grow.grow(self.db, self.pool, since=until - 48 * H, until=until, most=most,
                         tagger=Tagger(model=model or self.model, cap=50, recipe=recipe()))

    def test_a_repeat_customer_later_talk_is_read(self):
        write_chats(self.db, [EASY])
        self.assertEqual(self.night(NOW)["easy wins, skipped"], 1)
        add_steps(self.db, "c-easy", [("user", "عندكم شنطة رياضة؟", -20 * 24, None),
                                      ("assistant", "ايوه ب 900 جنيه", -20 * 24 - 0.1, None)])
        got = self.night(NOW + 23 * 24 * H)
        self.assertEqual((got.get("added"), got.get("lost")), (1, 1), got)
        self.assertEqual([t["text"] for t in self.pool.items[0]["turns"]], ["عندكم شنطة رياضة؟", "ايوه ب 900 جنيه"])
        self.assertEqual(self.pool.items[0]["read"], "c-easy:6")

    def test_a_talk_waiting_for_a_person_is_read_once_it_settles(self):
        write_chats(self.db, [("c-wait", [("user", "بكام الجزمة السودا؟", 5, None), ("assistant", "ب 1450 جنيه", 4.9, None),
                                          ("user", "ممكن تخفيض؟", 4.8, None)])])
        got = self.night(NOW)
        self.assertEqual(got["unclear, skipped"], 1)
        self.assertIsNone(self.pool.progress("c-wait"))
        self.assertIn("c-wait", self.pool.pending)
        add_steps(self.db, "c-wait", [("assistant", "اخر سعر 1400 جنيه", -10, "person"), ("user", "تمام اكدلي", -10.1, None),
                                      ("assistant", "تم تسجيل الطلب", -10.2, "person")])
        got = self.night(NOW + 24 * H)
        self.assertEqual((got.get("added"), got.get("hard")), (1, 1), got)
        self.assertEqual(self.pool.pending, {})

    def test_another_unclear_talk_is_left_unmarked_and_not_pending(self):
        write_chats(self.db, [("c-cancel", [("user", "بكام؟", 70, None), ("assistant", "ب 1450 جنيه", 69.9, None),
                                            ("user", "تمام اكدلي", 69.8, None), ("user", "لا الغي معلش", 69.7, None),
                                            ("assistant", "تمام", 69.6, None)])])
        got = self.night(NOW)
        self.assertEqual(got["unclear, skipped"], 1)
        self.assertIsNone(self.pool.progress("c-cancel"))
        self.assertEqual(self.pool.pending, {})

    def test_leftovers_are_read_first_the_next_night_whatever_the_window(self):
        write_chats(self.db, [(f"l{i}", [("user", "بكام الجزمة؟", 80 - i * 0.01, None),
                                         ("assistant", "ب 1450 جنيه", 79.9 - i * 0.01, None)]) for i in range(5)])
        got = self.night(NOW, most=3)
        self.assertEqual((got["added"], got["left for a later night"]), (3, 2))
        self.assertEqual(self.pool.pending, {"l3": 0, "l4": 0})
        got = self.night(NOW + 30 * 24 * H, most=3)  # the window is long past them
        self.assertEqual(got.get("added"), 2, got)
        self.assertEqual(self.pool.pending, {})
        self.assertEqual(sorted(i["read"] for i in self.pool.items), [f"l{i}:2" for i in range(5)])

    def test_no_talk_joins_twice(self):
        write_chats(self.db, [LOST])
        self.night(NOW)
        item = dict(self.pool.items[0])
        item.pop("read")
        self.pool.add(item, "c-lost", 2, NOW)
        self.assertEqual(len(self.pool.items), 1)
        self.pool.read.clear()  # even when the progress is gone
        self.assertEqual(self.night(NOW).get("added", 0), 1)
        self.assertEqual(len(self.pool.items), 1)

    def test_a_tagger_that_never_answers_lets_the_chat_go_after_max_tries(self):
        write_chats(self.db, [LOST])
        bad = mock.Mock(chat=mock.Mock(side_effect=ValueError("down")), label="x")
        for k in range(grow.MAX_TRIES):
            got = self.night(NOW + k * H, model=bad)
            self.assertEqual(got.get("not tagged"), 1)
        self.assertEqual(self.pool.pending, {})
        self.assertEqual(self.pool.progress("c-lost")[0], 2)

    def test_history_and_branch_chats_are_never_read(self):
        write_chats(self.db, [LOST])
        write_chats(self.db, [("c-history", LOST[1])], channel="history:whatsapp")
        write_chats(self.db, [("c-branch", LOST[1])], parent="c-lost")
        self.pool.pending = {"c-history": 0, "c-branch": 0}
        got = self.night(NOW)
        self.assertEqual((got["read"], got["added"]), (1, 1), got)
        self.assertEqual(set(self.pool.read), {"c-lost"})

    def test_a_dropped_progress_never_reads_a_chat_from_its_first_step(self):
        write_chats(self.db, [(f"l{i}", [("user", "بكام الجزمة؟", 80 - i, None),
                                         ("assistant", "ب 1450 جنيه", 79.9 - i, None)]) for i in range(3)])
        with mock.patch.object(grow, "MAX_READ", 2):
            self.assertEqual(self.night(NOW)["added"], 3)
            self.assertEqual(sorted(self.pool.read), ["l1", "l2"])
            self.assertEqual(self.pool.floor, NOW - 79.9 * H)
            got = self.night(NOW)
        self.assertEqual((got.get("added", 0), got["already read"]), (0, 3))
        self.assertEqual(len(self.pool.items), 3)

    def test_progress_survives_a_save(self):
        write_chats(self.db, [LOST, OPEN])
        self.night(NOW)
        self.pool.save()
        again = grow.Pool(self.pool.owner, "sales")
        self.assertEqual((again.read, again.pending, again.floor), (self.pool.read, self.pool.pending, None))


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
        (_, chat, _, _), = grow.real_chats(db, SINCE - 96 * H, NOW)
        self.assertEqual(chat.phone, "201009998877")
        self.assertEqual(chat.names, {"نورهان الشربيني"})
        self.assertEqual(chat.typed_phones, {"201009998877", "201001112233"})
        self.assertEqual(chat.addresses, {"شارع واحد اتنين"})


class NamesWithNoOrder(unittest.TestCase):
    """Lost chats have no order to learn a name from (review round 2 of the feed, 2026-10-31): a
    surname beside a masked name, a name a cue showed, typed again alone, never reaches the pool or
    the tagger. And a name given for an order in an earlier talk is masked in a later one."""

    LINES = {"q-a": ("بكام الجزمة السودا؟ نورهان الشربيني", ["نورهان", "الشربيني"]),
             "q-b": ("hi karim tawfik here, how much are the black boots?", ["karim", "tawfik"]),
             "q-c": ("الشربيني معاك تاني، بكام الجزمة الحمرا؟", ["الشربيني"]),
             "q-e": ("عايز اطبع يوسف الحناوي على الجزمة، بكام؟", ["يوسف", "الحناوي"]),
             "q-f": ("Tawfik Mansour, size 43 black boots price?", ["Tawfik", "Mansour"])}

    def grown(self, chats):
        owner = folder(self)
        _, counts, model = grown_pool(self, owner, chats=chats)
        return counts, (owner / "practice-sales.json").read_text(encoding="utf-8"), json.dumps(model.calls, ensure_ascii=False)

    def test_the_review_lines_lost_with_no_order(self):
        counts, saved, sent = self.grown([(k, [("user", text, 70, None), ("assistant", "ب 1450 جنيه، المقاس متاح", 69.9, None)])
                                          for k, (text, _) in self.LINES.items()])
        self.assertEqual(counts.get("lost"), 5, counts)
        for _, words in self.LINES.values():
            for w in words:
                self.assertNotIn(w, saved)
                self.assertNotIn(w, sent)
        self.assertIn("اطبع", saved)  # the want stays: printing is capped by it

    def test_a_name_given_after_the_store_asks_then_the_surname_alone(self):
        steps = [("user", "بكام الجاكيت الاسود؟ بلاتيرو بيسأل", 80, None), ("assistant", "الجاكيت ب 950 جنيه. تحب تطلبه؟", 79.9, None),
                 ("user", "تمام", 79.8, None), ("assistant", "ممكن الاسم بالكامل؟", 79.7, None),
                 ("user", "زورفانو بلاتيرو", 79.6, None), ("assistant", "تمام، والعنوان؟", 79.5, None),
                 ("user", "هبعته بكرة، بلاتيرو", 79.4, None), ("assistant", "تمام، مستنيك", 79.3, None)]
        counts, saved, sent = self.grown([("c-lost-name", steps)])
        self.assertEqual(counts.get("lost"), 1, counts)
        for text in (saved, sent):
            self.assertNotIn("بلاتيرو", text)
            self.assertNotIn("زورفانو", text)

    def test_an_order_name_from_an_earlier_talk_is_masked_in_a_later_talk(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, [("c-repeat", [("user", "عايز الجزمة البيضا 42", 70, None), ("assistant", "ب 1450 جنيه", 69.9, None),
                                       ("user", "تمام", 69.8, None),
                                       ("assistant", "", 69.7, None, order_call(items=[], name="نورهان بلاتيرو",
                                                                                address="12 شارع النصر المعادي")),
                                       ("assistant", "تم تسجيل الطلب", 69.6, None)])])
        pool = grow.Pool(folder(self), "sales")
        first = grow.grow(db, pool, since=SINCE, until=NOW, tagger=Tagger(model=ScriptedModel(recipe()), cap=50, recipe=recipe()))
        self.assertEqual(first.get("easy wins, skipped"), 1, first)
        add_steps(db, "c-repeat", [("user", "بلاتيرو تاني، بكام الشنطة؟", -20 * 24, None),
                                   ("assistant", "ب 900 جنيه", -20 * 24 - 0.1, None)])
        model = ScriptedModel(recipe())
        later = NOW + 23 * 24 * H
        got = grow.grow(db, pool, since=later - 24 * H, until=later, tagger=Tagger(model=model, cap=50, recipe=recipe()))
        self.assertEqual(got.get("lost"), 1, got)
        self.assertEqual(pool.items[0]["read"], "c-repeat:7")
        self.assertNotIn("بلاتيرو", json.dumps(pool.items, ensure_ascii=False))
        self.assertNotIn("بلاتيرو", json.dumps(model.calls, ensure_ascii=False))


class Siblings(unittest.TestCase):
    def setUp(self):
        self.owner = folder(self)
        write_owner(self.owner, "acme")
        write_plug(self.owner / "store_a", "store_a", "sales", owner="acme")
        write_plug(self.owner / "store_b", "store_b", "sales", owner="acme")
        write_plug(self.owner / "other", "other_kind", owner="acme")

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
        write_owner(self.owner, "acme")
        write_plug(self.owner / "store_a", "store_a", "sales", owner="acme")
        write_plug(self.owner / "store_b", "store_b", "sales", owner="acme")
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

    def test_the_arena_saves_what_training_counted_and_the_gate_split(self):
        db_path = self.owner / "store_b" / "ascent.db"
        Db(str(db_path)).close()
        with contextlib.redirect_stdout(io.StringIO()):
            run.main(["--cards", str(self.cards), "--matches", "1", "--rounds", "1", "--db", str(db_path), "--json"],
                     agent_model=Agent(), customer_model=Customer(buyers=("size", "price", "other")))
        saved = json.loads((self.owner / "practice-sales.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["played"])
        self.assertTrue(saved["split"]["held"])


class FoldedCards(unittest.TestCase):
    def test_cards_built_with_the_pool_take_no_grown_card_again(self):
        owner = folder(self)
        pool, _, _ = grown_pool(self, owner)
        items = [{**i, "grown": True} for i in pool.items]
        built, _ = cards_mod.build(items, recipe())
        self.assertEqual(sum(c["grown"] for c in built), len(items))
        self.assertFalse(any(i.startswith("grown-") for i in train_of(built, pool)))
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

    def test_the_night_builds_the_grown_cards(self):
        self.run_main("--recipe", str(recipe_mod.EXAMPLE))
        cards = grow.Pool(self.dir, "sales").cards
        self.assertTrue(cards)
        self.assertTrue(all(c["id"].startswith("grown-") for c in cards))

    def test_the_call_cap_stops_the_step_and_the_report_says_so(self):
        with mock.patch.object(run, "DEFAULT_CAP", 1):
            rep = self.run_main("--recipe", str(recipe_mod.EXAMPLE))
        self.assertEqual(rep["practice"]["stopped"], "the Arena's call cap")
        self.assertEqual(rep["practice"]["added"], 1)

    def test_a_failing_practice_step_still_saves_the_report(self):
        with mock.patch.object(grow, "night", side_effect=RuntimeError("made-up")):
            rep = self.run_main("--recipe", str(recipe_mod.EXAMPLE))
        self.assertEqual(rep["practice"], {"kind": "sales", "stopped": "failed: RuntimeError"})
        self.assertIn("snapshot", rep)

    def test_a_pool_that_cannot_be_saved_is_named_and_the_report_saved(self):
        with mock.patch.object(grow.Pool, "save", side_effect=PermissionError("made-up")):
            rep = self.run_main("--recipe", str(recipe_mod.EXAMPLE))
        self.assertEqual(rep["practice"]["stopped"], "the pool was not saved (PermissionError)")
        self.assertEqual(rep["practice"]["added"], 2)
        self.assertFalse((self.dir / "practice-sales.json").exists())


class OwnerMarker(unittest.TestCase):
    """Folders alone never make an owner (red team F3, review 6): owner.json above the agents'
    folders names the owner, and each plug must name the same one."""

    def setUp(self):
        self.root = folder(self)

    def test_two_owners_side_by_side_with_no_marker_never_share(self):
        write_plug(self.root / "ownera_sales", "ownera_sales", "sales")
        write_plug(self.root / "ownerb_sales", "ownerb_sales", "sales")
        a, b = grow.for_state(self.root / "ownera_sales"), grow.for_state(self.root / "ownerb_sales")
        self.assertEqual(a.path, self.root / "ownera_sales" / "practice-sales.json")
        self.assertNotEqual(a.path, b.path)
        self.assertEqual(grow.siblings(a.owner, "sales"), [])
        grown_pool(self, a.owner)
        self.assertEqual(grow.for_state(self.root / "ownerb_sales").items, [])
        self.assertEqual(a.summary()["siblings"], [])

    def test_a_plug_naming_no_owner_or_another_keeps_its_own_folder(self):
        write_owner(self.root, "acme")
        write_plug(self.root / "mine", "mine", "sales", owner="acme")
        write_plug(self.root / "none", "none", "sales")
        write_plug(self.root / "zed", "zed", "sales", owner="zed")
        self.assertEqual(grow.owner_of(self.root / "mine"), self.root)
        self.assertEqual(grow.owner_of(self.root / "none"), self.root / "none")
        self.assertEqual(grow.owner_of(self.root / "zed"), self.root / "zed")
        self.assertEqual(grow.siblings(self.root, "sales"), ["mine"])

    def test_a_marker_that_is_a_link_or_not_exactly_a_name_names_no_owner(self):
        write_plug(self.root / "mine", "mine", "sales", owner="acme")
        other = folder(self)
        write_owner(other, "acme")
        os.symlink(other / grow.OWNER_FILE, self.root / grow.OWNER_FILE)
        self.assertEqual(grow.owner_of(self.root / "mine"), self.root / "mine")
        os.unlink(self.root / grow.OWNER_FILE)
        for bad in ('{"owner": "Acme"}', '{"owner": ["acme"]}', '["acme"]', "not json"):
            (self.root / grow.OWNER_FILE).write_text(bad, encoding="utf-8")
            self.assertEqual(grow.owner_of(self.root / "mine"), self.root / "mine", bad)
            self.assertEqual(grow.siblings(self.root, "sales"), [], bad)

    def test_personas_state_reads_the_pool_the_arena_reads(self):
        from arena import personas
        write_owner(self.root, "acme")
        write_plug(self.root / "store_a", "store_a", "sales", owner="acme")
        grown_pool(self, self.root)
        seen = {}

        def fake_run(*a, grown=None, **k):
            seen["grown"] = grown
            return {}
        with mock.patch.object(personas, "run", side_effect=fake_run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = personas.main(["--source", str(folder(self)), "--out", str(folder(self) / "out"),
                                  "--recipe", str(recipe_mod.EXAMPLE), "--state", str(self.root / "store_a"),
                                  "--scripted", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["grown"], grow.for_state(self.root / "store_a").items)
        self.assertEqual(len(seen["grown"]), 2)

    def test_the_plug_owner_key(self):
        write_plug(self.root / "mine", "mine", "sales", owner="acme")
        self.assertEqual(plug_mod.load(self.root / "mine" / "plug.json").owner, "acme")
        self.assertEqual(plug_mod.load(SALES_PLUG).owner, "")


class PoolFile(unittest.TestCase):
    """The pool's file: written the safe way, its kind and values checked on load (F4, F6)."""

    def setUp(self):
        self.owner = folder(self)
        self.pool, _, _ = grown_pool(self, self.owner)
        self.data = json.loads(self.pool.path.read_text(encoding="utf-8"))

    def reload(self, **changes):
        self.pool.path.write_text(json.dumps({**self.data, **changes}), encoding="utf-8")
        return grow.Pool(self.owner, "sales")

    def test_save_writes_through_no_link_and_a_new_owner_folder_is_private(self):
        outside = folder(self) / "outside.json"
        outside.write_text("kept", encoding="utf-8")
        os.symlink(outside, self.pool.path.with_name(self.pool.path.name + ".tmp"))
        self.pool.save()
        self.assertEqual(outside.read_text(encoding="utf-8"), "kept")
        self.assertFalse(self.pool.path.is_symlink())
        self.assertEqual(os.stat(self.pool.path).st_mode & 0o777, 0o600)
        fresh = folder(self) / "new-owner"
        pool = grow.Pool(fresh, "sales")
        pool.changed = True
        pool.save()
        self.assertEqual(os.stat(fresh).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(pool.path).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(p.name for p in fresh.iterdir()), ["practice-sales.json"])

    def test_a_pool_file_of_another_kind_is_refused(self):
        with self.assertRaises(grow.Refused):
            self.reload(kind="marketing")

    def test_a_bad_capped_pattern_gives_the_example_caps(self):
        pool = self.reload(capped=[{"name": "printing", "pattern": "(", "most": 0.25},
                                   {"name": "size", "pattern": "size", "most": 0.25}])
        self.assertIsNone(pool.capped)  # the example recipe's caps (item 33) hold, not none
        grow.decks([card(1, "size")], pool, set())
        self.assertEqual(self.reload(capped=[{"name": "size", "pattern": "size", "most": 0.25}]).capped,
                         [{"name": "size", "pattern": "size", "most": 0.25}])

    def test_cards_with_values_the_deck_cannot_draw_are_dropped(self):
        good = self.data["cards"][0]
        bad = [{**good, "chats": 1e999}, {**good, "chats": 0}, {**good, "chats": True}, {**good, "chats": 1.5},
               {**good, "arena_weight": float("inf")}, {**good, "arena_weight": float("nan")},
               {**good, "arena_weight": -1}, {**good, "want": ["ok", 3]}]
        for c in bad:
            self.assertEqual(self.reload(cards=[c]).cards, [], c)
        self.assertEqual(len(self.reload(cards=[good]).cards), 1)

    def test_items_with_tags_or_style_out_of_shape_are_dropped(self):
        item = self.data["items"][0]
        bad = [{**item, "tags": {**item["tags"], "patience": "3"}},
               {**item, "tags": {**item["tags"], "worry": None}},
               {**item, "tags": {**item["tags"], "no_budget": 0}},
               {**item, "style": {**item["style"], "language": {}}},
               {**item, "style": {**item["style"], "voice_notes": float("nan")}},
               {**item, "style": {**item["style"], "length": 3}},
               {**item, "turns": [{"from": "customer", "text": 5}]},
               {**item, "turns": ["text"]}]
        for i in bad:
            self.assertEqual(self.reload(items=[i]).items, [], i)
        self.assertEqual(len(self.reload(items=[item]).items), 1)
        with self.assertRaises(ValueError):
            self.pool.add(bad[0], "c-x", 1, NOW)


class ValuesInRange(unittest.TestCase):
    """Red team round 2 of the feed (2026-10-31), item 1: a huge number or a pattern that backtracks
    for ever in the pool file is dropped on load, and run.main says "Not run" instead of a traceback."""

    def setUp(self):
        self.owner = folder(self)
        self.pool, _, _ = grown_pool(self, self.owner)
        self.data = json.loads(self.pool.path.read_text(encoding="utf-8"))

    def reload(self, **changes):
        self.pool.path.write_text(json.dumps({**self.data, **changes}), encoding="utf-8")
        return grow.Pool(self.owner, "sales")

    def test_numbers_past_two_to_the_53_are_dropped_and_the_deck_still_draws(self):
        big, good, item = 10 ** 400, self.data["cards"][0], self.data["items"][0]
        for c in ({**good, "chats": big}, {**good, "chats": 2 ** 53 + 1}, {**good, "arena_weight": big}):
            pool = self.reload(cards=[c])
            self.assertEqual(pool.cards, [], c["chats"])
            grow.decks([card(1, "size")], pool, set())
        self.assertEqual(len(self.reload(cards=[{**good, "chats": 2 ** 53}]).cards), 1)
        pool = self.reload(read={"c-1": [1, big], "c-2": [1, -big], "c-3": [1, NOW]}, floor=big,
                           items=[{**item, "style": {**item["style"], "voice_notes": big}}])
        self.assertEqual((list(pool.read), pool.floor, pool.items), (["c-3"], None, []))

    def test_a_group_with_a_quantifier_or_a_bar_repeated_again_gives_the_example_caps(self):
        for pat in (r"^(\w+\s?)*$", r"(a|a)*", r"(a+)+", r"((a+))*", r"([a-z]+){2,}"):
            pool = self.reload(capped=[{"name": "printing", "pattern": pat, "most": 0.25}])
            self.assertIsNone(pool.capped, pat)
            grow.decks([dict(card(1, "size"), want=["a" * 28 + "!"])], pool, set())
        kept = (r"(?:ab)*", r"[(a+)]*", r"(a[|+])*", r"\(a+\)*", r"(\w+)?", r"(a+)\w*", r"(a+)[bc]*",
                recipe().capped[0][1].pattern)
        for pat in kept:
            pool = self.reload(capped=[{"name": "printing", "pattern": pat, "most": 0.25}])
            self.assertEqual(pool.capped[0]["pattern"], pat)

    def test_an_overflow_or_a_refusal_in_a_run_is_not_run_not_a_traceback(self):
        cards = folder(self) / "cards"
        cards.mkdir()
        for c in (card(1, "size"), card(2, "price")):
            (cards / f"{c['id']}.json").write_text(json.dumps(c), encoding="utf-8")
        for err in (OverflowError("int too large to convert to float"), hist.Refused("the pool cannot be read")):
            err_out = io.StringIO()
            with mock.patch.object(grow, "for_state", side_effect=err), contextlib.redirect_stderr(err_out):
                code = run.main(["--cards", str(cards), "--state", str(folder(self) / "state")],
                                agent_model=Agent(), customer_model=Customer())
            self.assertEqual(code, 2)
            self.assertIn("Not run: " + str(err), err_out.getvalue())


class Guards(unittest.TestCase):
    """One test per behaviour the mutant sweep found unpinned (review 9)."""

    def setUp(self):
        self.owner = folder(self)

    def test_a_pool_file_that_is_a_link_inside_the_owner_folder_is_refused(self):
        (self.owner / "other.json").write_text("{}", encoding="utf-8")
        os.symlink(self.owner / "other.json", self.owner / "practice-sales.json")
        with self.assertRaises(grow.Refused):
            grow.Pool(self.owner, "sales")

    def test_the_owner_folder_itself_is_never_the_pool_file(self):
        with self.assertRaises(grow.Refused):
            grow.Pool(self.owner, "sales", path=self.owner)

    def test_a_link_put_at_the_pool_path_after_it_was_read_is_replaced_not_written_through(self):
        pool = grow.Pool(self.owner, "sales")
        outside = folder(self) / "outside.json"
        outside.write_text("kept", encoding="utf-8")
        os.symlink(outside, pool.path)
        pool.changed = True
        pool.save()
        self.assertEqual(outside.read_text(encoding="utf-8"), "kept")
        self.assertFalse(pool.path.is_symlink())

    def test_no_chat_is_tagged_once_the_call_cap_is_reached(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        write_chats(db, ALL)
        pool, model = grow.Pool(self.owner, "sales"), ScriptedModel(recipe())
        got = grow.grow(db, pool, since=SINCE, until=NOW, tagger=Tagger(model=model, cap=50, recipe=recipe()),
                        calls=mock.Mock(reached=True))
        self.assertEqual((got.get("added", 0), got["left for a later night"]), (0, 2))
        self.assertEqual(pool.items, [])

    def test_a_step_after_the_window_closed_is_not_read(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        cid, steps = LOST
        write_chats(db, [(cid, steps + [("user", "لسه متاحة؟", -5, None)])])
        with db.tx() as c:  # a night run for a window that closed before the chat's newest step
            c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (NOW - 79.9 * H, cid))
        (_, chat, _, last), = grow.real_chats(db, SINCE - 96 * H, NOW)
        self.assertEqual(last, (2, NOW - 79.9 * H))
        self.assertEqual(len(chat.messages), 2)

    def test_a_cap_whose_most_is_not_a_share_gives_the_example_caps(self):
        pool, _, _ = grown_pool(self, self.owner)
        data = json.loads(pool.path.read_text(encoding="utf-8"))
        for most in (1.5, 1, 0, True, -0.2):
            pool.path.write_text(json.dumps({**data, "capped": [{"name": "printing", "pattern": "x", "most": most}]}),
                                 encoding="utf-8")
            self.assertIsNone(grow.Pool(self.owner, "sales").capped, most)

    def test_a_card_from_the_pool_file_that_is_not_grown_is_dropped(self):
        pool, _, _ = grown_pool(self, self.owner)
        data = json.loads(pool.path.read_text(encoding="utf-8"))
        pool.path.write_text(json.dumps({**data, "cards": [{**data["cards"][0], "id": "persona-01"}]}), encoding="utf-8")
        self.assertEqual(grow.Pool(self.owner, "sales").cards, [])

    def test_a_no_budget_card_has_its_own_group_id(self):
        self.assertEqual(grow.grown_id({"worry": "price", "why_unwinnable": "no budget"}), "grown-price-no-budget")
        self.assertEqual(grow.grown_id({"worry": "price", "why_unwinnable": None}), "grown-price")


class KindRule(unittest.TestCase):
    """One rule for a plug's kind and the pool's (F10)."""

    def plug(self, **keys):
        d = json.loads(SALES_PLUG.read_text(encoding="utf-8"))
        d.pop("exam")
        return plug_mod.from_dict({**d, **keys})

    def test_a_kind_the_plug_takes_the_pool_takes(self):
        self.assertIs(grow.KIND, plug_mod.AGENT_NAME)
        longest = "k" * 41
        self.assertEqual(self.plug(kind=longest).kind, longest)
        grow.Pool(folder(self), longest)
        for bad in ("k" * 42, "sales\n"):
            with self.assertRaises(ValueError):
                self.plug(kind=bad)
            with self.assertRaises(grow.Refused):
                grow.Pool(folder(self), bad)
        for key in ("agent", "owner"):
            with self.assertRaises(ValueError):
                self.plug(**{key: "a" * 42})


if __name__ == "__main__":
    unittest.main()
