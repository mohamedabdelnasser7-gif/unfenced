"""The round 3 reviewer's minors on levels (review levels r3 items 1 to 7): a torn or missing record has
one step on the Arena tab (Start a new test set, posted with the page token), a never customer's Try
again is judged on its safety checks only, an unjudged test match is said as one, the refusal when the
test set cannot be filled, a levels run with blended customers, the top ups and the refusal at 99, and
the shape's mix passed to fixed_test. Fake models only."""
import http.client
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from arena import good, madeup, practice, retry, run
from kit import turn as turn_mod
from reflection import morning as mo
from reflection import pages
from tests import test_any_agent, test_blend, test_levels_lost, test_levels_practice, test_levels_tab
from tests import test_levels_testset as testset
from tests.fake_model import clean_env, say
from tests.test_arena_practice import World
from tests.test_customers_shape import Base, Writer

AGENT = "stock_watch"


def text(page):
    import re
    return " ".join(re.sub(r"<[^>]+>", " ", page).split())


class Record(test_levels_tab.Tab):
    """Item 1: a torn last line, a matches file gone beside test-set.json, or a torn test-set.json."""

    def run_page(self, world=None):
        world = world or World()
        self.m.arena_models = lambda: (world, world, world)
        self.starts.clear()
        self.m.run_arena(AGENT, full=True)
        self.starts[-1][0]()

    def old_customers(self):
        return {p.stem for p in (self.folder / madeup.FOLDER).glob("persona-*.json")}

    def check_way_on(self, file):
        note = self.m.arena_note(AGENT)
        self.assertIn(file, note)
        self.assertIn("press Start a new test set", note)
        self.assertEqual(self.m.arena_record(AGENT), file)
        page = self.tab()
        self.assertIn(f'action="{mo.NEW_TEST_PATH}"', page)
        self.assertIn('name="token" value="t"', page.split(f'action="{mo.NEW_TEST_PATH}"')[1].split("</form>")[0])
        self.assertNotIn(mo.NEW_TEST_PATH, self.tab(token=None))
        before = self.old_customers()
        self.assertEqual(mo.TWO_TAB_ACTIONS[mo.NEW_TEST_PATH](self.m, {"agent": [AGENT]}), mo.NEW_TEST_SET)
        self.assertIsNone(self.m.arena_note(AGENT))
        self.assertIsNone(self.m.arena_record(AGENT))
        self.assertEqual(len(self.starts), 1)  # the reset started nothing
        self.assertTrue(list(self.folder.glob("test-set-before-*.json")))  # set aside, never deleted
        done = {c for c, _ in practice.trained(self.folder)}
        self.assertLessEqual(before, done)  # every old customer counts as trained
        self.run_page()
        self.assertIsNone(self.m.arena_note(AGENT))
        held = {i for i, _ in practice.read_test(self.folder)}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & before)  # the new test set is new customers

    def test_a_torn_last_line_names_the_file_and_the_reset_gets_past_it(self):
        self.run_page()
        path = self.folder / run.MATCHES_FILE
        lines = path.read_text(encoding="utf-8").splitlines()
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines[-1][: len(lines[-1]) // 2])  # a write cut by a crash
        self.run_page()
        torn = path.read_bytes()
        self.check_way_on(run.MATCHES_FILE)
        kept = sorted(self.folder.glob("arena-matches-before-*.jsonl"))
        self.assertEqual(kept[0].read_bytes(), torn)  # set aside whole, never trimmed

    def test_a_matches_file_gone_beside_the_test_set(self):
        self.run_page()
        (self.folder / run.MATCHES_FILE).unlink()
        self.run_page()
        self.check_way_on(run.MATCHES_FILE)

    def test_a_torn_test_set(self):
        self.run_page()
        (self.folder / practice.TEST_FILE).write_text('{"test": [', encoding="utf-8")
        self.run_page()
        self.check_way_on(practice.TEST_FILE)

    def test_a_whole_record_is_not_reset_and_other_failures_offer_no_reset(self):
        self.run_page()
        with self.assertRaises(mo.Refused) as got:
            self.m.new_test_set(AGENT)
        self.assertIn("read whole", str(got.exception))
        self.assertEqual(list(self.folder.glob("*-before-*")), [])
        levels_file = self.folder / "level.json"
        levels_file.write_text("{broken", encoding="utf-8")  # another refusal: its own line, no reset
        self.run_page()
        if self.m.arena_note(AGENT):
            self.assertIsNone(self.m.arena_record(AGENT))
            self.assertNotIn(mo.NEW_TEST_PATH, self.tab())
        with self.assertRaises(mo.Refused):
            self.m.new_test_set("sales")

    def test_the_post_needs_the_page_token(self):
        self.run_page()
        (self.folder / run.MATCHES_FILE).unlink()
        self.run_page()
        server = test_any_agent.DataPost.serve(self)
        here = f"127.0.0.1:{server.server_address[1]}"

        def post(token):
            form = urllib.parse.urlencode({"token": token, "agent": AGENT, "back": f"/agents/{AGENT}"})
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            try:
                conn.request("POST", mo.NEW_TEST_PATH, form, {"Host": here, "Origin": f"http://{here}",
                                                             "Content-Type": "application/x-www-form-urlencoded"})
                r = conn.getresponse()
                r.read()
                return r.status
            finally:
                conn.close()
        self.assertEqual(post("guess"), 403)
        self.assertEqual(list(self.folder.glob("*-before-*")), [])
        self.assertEqual(post(server.token), 303)
        self.assertTrue(list(self.folder.glob("test-set-before-*.json")))
        self.assertNotIn(mo.NEW_TEST_PATH, mo.ACTIONS)  # the A3 page never sends it


class NeverTryAgain(Base):
    """Item 2: a never customer is on the lost list only for a safety slip; its Try again is judged on
    the safety checks only."""
    go = test_levels_lost.LostList.go

    def try_again(self, answer):
        name = sorted(self.folders)[0]
        picked = {}

        def lose(r, card):
            if card["unwinnable"]:
                first = picked.setdefault("never", card["id"])
                return f"{good.BROKE}: it promised" if card["id"] == first else "it will not buy"
            winnable = picked.setdefault("win", card["id"])
            return "not reached" if card["id"] == winnable else None
        rep, cards, saved = self.go(name, lose)
        folder = self.folders[name]
        path = folder / run.MATCHES_FILE
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        for m in rows:  # a saved match Try again can play from
            m["turns"] = [{"n": 1, "customer": "hi", "replies": ["hello"], "tools": [], "actions": []}]
        path.write_text("".join(json.dumps(m) + "\n" for m in rows), encoding="utf-8")
        agent = turn_mod.load(folder)

        def play(agent, card, **kw):
            return {"card": card["id"], "ended": "done",
                    "turns": [{"n": 1, "customer": "hi", "replies": ["a fixed reply"], "tools": [], "actions": []}]}

        class Judge:
            def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
                return say(json.dumps(answer))
        pool = type("Pool", (), {"refresh": lambda s: None, "live": lambda s, *a: [], "seen": []})()
        with mock.patch.object(practice, "play", play):
            got = retry.retry(agent=agent.name, run=rep["run"], cards=[x["card"] for x in saved["lost"]], state=folder,
                              reports=self.root, pool=pool, agent_model=None, customer_model=None, built=agent,
                              judge_model=Judge())
        return {r["card"]: r for r in got["results"]}, picked

    def test_a_fixed_never_slip_reads_won_and_a_winnable_one_still_needs_the_good_result(self):
        results, picked = self.try_again({"reached": False, "broke_never": False, "turn": 1, "why": "no sale"})
        self.assertEqual(results[picked["never"]]["result"], retry.WON_AGAIN)
        self.assertEqual(results[picked["never"]]["why"], retry.NEVER_SAFE)
        self.assertEqual(results[picked["win"]]["result"], retry.STILL_LOST)

    def test_a_never_line_broken_again_is_still_lost(self):
        results, picked = self.try_again({"reached": False, "broke_never": True, "turn": 1, "why": "it promised"})
        self.assertEqual(results[picked["never"]]["result"], retry.STILL_LOST)
        self.assertTrue(results[picked["never"]]["why"].startswith(good.BROKE))


class Unjudged(test_levels_tab.Tab):
    """Item 3: an unjudged test match is said as one, with its own block and no general help line."""

    def test_the_run_writes_the_unjudged_count_and_block(self):
        judge = test_levels_practice.AWholeGate.judge(None, ["won"] + ["unread", "unread"] + ["won"] * 9)
        world = World(judge=judge)
        rep = practice.practise(self.folder, agent_model=world, customer_model=world, judge_model=world, matches=1)
        item = json.loads((self.dir / (rep.get("item") or rep.get("stuck"))["file"]).read_text(encoding="utf-8"))
        self.assertEqual(item["unjudged"], 1)
        self.assertEqual(item["blocks"][0]["kind"], "unjudged")
        self.assertIn("1 test match could not be judged", item["blocks"][0]["line"])
        page = self.tab()
        self.assertIn("9 won of 9 played</b> (one test match could not be judged)", page)
        self.assertNotIn("the run stopped before all 10", page)
        self.assertIn("1 test match could not be judged", page)
        self.assertNotIn(pages.LEVEL_HELP, page)

    def test_a_cut_short_round_with_none_unjudged_keeps_its_line_and_help(self):
        self.item(gate_won=6, gate_played=7, gate_size=10, needs=7, failed_checks=0, scores=[6], stopped="cap",
                  level="medium")
        page = self.tab()
        self.assertIn("(the run stopped before all 10)", page)
        self.assertIn(pages.LEVEL_HELP, page)


class Filling(Base):
    """Items 4, 6 and 7: the refusal when the test set cannot be filled, the top ups, and the mix."""
    practise = testset.Kept.practise

    def all_trained(self, folder):
        """Every id a customer can have (persona-01 to persona-99) has a training match on record."""
        with open(folder / run.MATCHES_FILE, "a", encoding="utf-8") as f:
            for n in range(1, madeup.MAX_CUSTOMERS + 1):
                f.write(json.dumps({"id": f"old-r1-t{n:02d}", "card": f"persona-{n:02d}", "persona": "x"}) + "\n")

    def items(self):
        return list(self.root.glob("arena-*-*.json"))  # the run items, never the call count

    def test_a_test_set_that_cannot_be_filled_is_refused_with_no_item(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        self.all_trained(folder)
        writer = Writer()
        with self.assertRaises(run.Refused) as got:
            self.practise(name, 20, 10, writer=writer)
        self.assertIn("too few are left", str(got.exception))
        self.assertTrue(writer.asks)  # it tried to write more first
        self.assertEqual(self.items(), [])
        self.assertFalse((folder / practice.TEST_FILE).exists())

    def fake_writer(self, grow):
        """madeup.for_agent as a writer that repeats people: each call gives grow(count, calls) customers,
        so a top up adds fewer than asked. Every one has trained already."""
        counts = []

        def for_agent(folder, agent, card, model, profiles=None, count=None):
            counts.append(count)
            n = grow(count, len(counts))
            kinds = madeup.kinds_for(max(n, 2))
            return [{"id": f"persona-{i:02d}", "kind": k, "from_card": "F", "unwinnable": k == "never",
                     "made_up": True} for i, k in enumerate(kinds[:n], 1)], True
        return for_agent, counts

    def test_five_top_ups_then_the_refusal(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        self.all_trained(folder)
        for_agent, counts = self.fake_writer(lambda count, calls: 10 + calls)  # one new person a call
        with mock.patch.object(madeup, "for_agent", for_agent), self.assertRaises(run.Refused) as got:
            self.practise(name, 10, 3)
        self.assertIn("too few are left", str(got.exception))
        self.assertEqual(len(counts), 6)  # the first write and 5 top ups, no more
        self.assertEqual(counts, sorted(counts))
        self.assertLess(counts[-1] * 2, madeup.MAX_CUSTOMERS)  # far from 99: the top ups ran out, not the room
        self.assertEqual(self.items(), [])

    def test_the_plain_refusal_at_99(self):
        name = "support_calm_helper"
        folder = self.folders[name]
        self.all_trained(folder)
        for_agent, counts = self.fake_writer(lambda count, calls: count)
        with mock.patch.object(madeup, "for_agent", for_agent), self.assertRaises(run.Refused) as got:
            self.practise(name, 80, 10)
        self.assertIn("too few are left", str(got.exception))
        self.assertEqual(len(counts), 2)  # one top up; the next would pass 99, so it is refused there
        self.assertGreater(counts[1], counts[0])
        self.assertTrue(all(c <= madeup.MAX_CUSTOMERS for c in counts))
        self.assertEqual(self.items(), [])

    def test_the_shapes_mix_holds_against_a_saved_set_of_one_kind(self):
        name = "lead_trial_booker"
        folder = self.folders[name]
        practice.keep_trained(folder)  # the roster a first run leaves before it writes customers
        cards, _ = madeup.for_agent(folder, name, turn_mod.load(folder).card, Writer(), count=30)
        easy = [c for c in cards if c["kind"] == "easy"]
        self.assertTrue(any(int(c["id"][-2:]) > 20 for c in easy))  # some play past a medium run's 20
        practice.write_test(folder, [(c["id"], c["from_card"]) for c in easy])  # a saved set of 10 easy
        rep = self.practise(name, 20, 10)
        kinds = {c["id"]: c["kind"] for c in cards}
        got = [kinds[i] for i in rep["held_out_cards"]]
        self.assertEqual((got.count("easy"), got.count("unsure"), got.count("hard")), (4, 4, 2))


class Blended(test_blend.Base):
    """Item 5: a levels run whose customers behave like the owner's real ones."""

    def test_a_levels_run_with_blended_customers_holds_a_fixed_test_set(self):
        self.own()
        log = []
        with mock.patch.object(practice.Practice, "play", testset.recorded_play(log)):
            rep = practice.practise(self.folder, agent_model=None, customer_model=Writer(), judge_model=None,
                                    rounds=1, customers=20, gate_size=10)
            again = practice.practise(self.folder, agent_model=None, customer_model=Writer(), judge_model=None,
                                      rounds=1, customers=20, gate_size=10)
        self.assertEqual(rep["behaviour_from"], 8)
        cards = {c["id"]: c for c in madeup.read(self.folder / madeup.FOLDER, AGENT, self.card,
                                                  madeup.blend_source(self.card, madeup.owner_cards(self.folder)))}
        self.assertEqual(len(cards), 20)
        self.assertEqual(len(rep["held_out_cards"]), 10)
        self.assertTrue(all(run.can_buy(cards[i]) for i in rep["held_out_cards"]))
        self.assertEqual(again["held_out_cards"], rep["held_out_cards"])
        tested = {c for m, c in log if "-g" in m}
        self.assertFalse(tested & {c for c, _ in practice.trained(self.folder)})


if __name__ == "__main__":
    unittest.main()
