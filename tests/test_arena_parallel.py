"""Arena matches several at a time (arena/run.py PARALLEL, 1 to 10, 10 when unset): the same saved run as one by one, groups that really
overlap, the cap inside a group, quick notes carried group to group, whole lines on the matches file."""
import json
import os
import threading
import time
import unittest
from unittest import mock

from arena import run
from tests.test_arena_run import Agent, Base, Customer, card

WAIT = 5  # seconds a fake match waits for the others of its group; a one by one build fails, never hangs


def judged(won):
    return {"won": won, "why": "fake", "quote": ""}


def fake_match(arena, card_, match_id, won):
    """What Arena.play gives for a judged match, its line left for the fold as the real play leaves it."""
    m = {"id": match_id, "card": card_["id"], "won": won}
    run.later(arena._write, m)
    return m, judged(won)


def no_match_threads():
    return not [t for t in threading.enumerate() if t.name.startswith("arena-match")]


class P(Base):
    def arena(self, cards, customer, **kw):
        kw.setdefault("state", self.dir)
        kw.setdefault("calls", run.Calls(self.dir / "calls.json", 300, day="2026-10-30"))
        kw.setdefault("trust", {"matches": 4, "wins": 3, "zero_failed_checks": True})
        return run.Arena(cards, agent_model=Agent(), customer_model=customer, now=lambda: 1_790_000_000.0, **kw)


class Slow(Customer):
    """Customer, slower with a buyer, so a later match that leaves ends before an earlier one that buys."""

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if "Your worry is size" in messages[0]["content"]:
            time.sleep(0.02)
        return super().chat(messages, tools=tools, effort=effort, max_tokens=max_tokens, whole=whole)


class Same(P):
    def go(self, n, name):
        state = self.dir / name
        cards = [card(1, "size"), card(2, "price"), card(3, "size"), card(4, "price"), card(5, "size")]
        with mock.patch.object(run, "PARALLEL", n):
            a = self.arena(cards, Slow(), matches=7, rounds=2, held_out=["persona-04", "persona-05"],
                           state=state, calls=run.Calls(self.dir / f"{name}.json", 300, day="2026-10-30"))
            rep = a.run()
        return rep, (state / run.MATCHES_FILE).read_text(encoding="utf-8")

    def test_three_at_a_time_saves_what_one_by_one_saves(self):
        one, lines_one = self.go(1, "one")
        three, lines_three = self.go(3, "three")
        self.assertEqual(lines_three, lines_one)  # the same matches, in the same order, byte for byte
        # the saved item's seal is keyed by a random key in each run's own folder (kit/seal.py), so it is left out
        self.assertNotEqual(one["item"].pop("seal"), three["item"].pop("seal"))
        self.assertEqual(json.dumps(three, sort_keys=True), json.dumps(one, sort_keys=True))
        self.assertEqual(three["stopped"], one["stopped"])
        self.assertEqual([r["gate"]["lost"] for r in three["rounds"]], [r["gate"]["lost"] for r in one["rounds"]])
        self.assertTrue(any(r["gate"]["lost"] for r in one["rounds"]))  # the test has losses to compare
        self.assertTrue(no_match_threads())

    def test_the_setting_is_one_to_ten_and_ten_when_unset(self):
        self.assertEqual(run.MAX_PARALLEL, 10)
        for raw, want in (("", 10), ("1", 1), ("2", 2), ("3", 3), ("9", 9), ("10", 10), ("11", 10), ("0", 1),
                          ("x", 10)):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {run.PARALLEL_ENV: raw}):
                self.assertEqual(run._parallel(), want)
        with mock.patch.object(run, "PARALLEL", None), mock.patch.dict(os.environ, {run.PARALLEL_ENV: "2"}):
            self.assertEqual(run.parallel(), 2)  # read on the first run, after main loads .env
            os.environ[run.PARALLEL_ENV] = "1"
            self.assertEqual(run.parallel(), 2)  # and only once


class Overlap(P):
    def test_a_group_of_five_is_in_flight_at_once_practice_and_gate(self):
        barrier, seen = threading.Barrier(5, timeout=WAIT), []

        def play(self, card_, match_id, **kw):
            barrier.wait()  # all five of the group are here, or BrokenBarrierError fails the run
            seen.append(match_id)
            return fake_match(self, card_, match_id, True)
        cards = [card(i, "size") for i in range(1, 11)]
        with mock.patch.object(run, "PARALLEL", None), mock.patch.dict(os.environ, {run.PARALLEL_ENV: ""}), \
                mock.patch.object(run.Arena, "play", play):
            rep = self.arena(cards, Customer(), matches=5, rounds=1,
                             trust={"matches": 5, "wins": 5, "zero_failed_checks": True}).run()
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual(len(seen), 10)
        self.assertEqual(rep["rounds"][0]["training"]["played"], 5)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 5)
        self.assertTrue(no_match_threads())

    def test_a_group_of_three_is_in_flight_at_once_practice_and_gate(self):
        barrier, seen = threading.Barrier(3, timeout=WAIT), []

        def play(self, card_, match_id, **kw):
            barrier.wait()  # all three of the group are here, or BrokenBarrierError fails the run
            seen.append(match_id)
            return fake_match(self, card_, match_id, True)
        cards = [card(i, "size") for i in range(1, 7)]
        with mock.patch.object(run, "PARALLEL", 3), mock.patch.object(run.Arena, "play", play):
            rep = self.arena(cards, Customer(), matches=3, rounds=1, trust={"matches": 3, "wins": 3, "zero_failed_checks": True}).run()
        self.assertEqual(rep["stopped"], run.PASSED)
        self.assertEqual(len(seen), 6)
        self.assertEqual(rep["rounds"][0]["training"]["played"], 3)
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 3)
        self.assertTrue(no_match_threads())


class CapInGroup(P):
    def test_the_cap_inside_a_group_stops_new_calls_and_folds_nothing_after(self):
        barrier, first_out, after = threading.Barrier(3, timeout=WAIT), threading.Event(), []
        calls = run.Calls(self.dir / "calls.json", 5, day="2026-10-30")

        def play(self, card_, match_id, **kw):
            barrier.wait()
            if match_id.endswith("-t01"):
                try:
                    while True:
                        self.calls.take()
                except run.CapReached:
                    self.halt = run.CAP
                    first_out.set()
                    return None
            first_out.wait(WAIT)
            try:
                self.calls.take()
                after.append(match_id)
            except run.CapReached:
                pass
            return fake_match(self, card_, match_id, False)
        cards = [card(i, "size") for i in range(1, 7)]
        with mock.patch.object(run, "PARALLEL", 3), mock.patch.object(run.Arena, "play", play):
            rep = self.arena(cards, Customer(), matches=6, rounds=2, calls=calls).run()
        self.assertEqual(rep["stopped"], run.CAP)
        self.assertEqual(after, [])  # no call after the cap
        self.assertEqual(calls.count, 5)
        self.assertEqual(len(rep["rounds"]), 1)
        self.assertEqual(rep["rounds"][0]["training"]["played"], 0)  # t02 and t03 finished but are never folded
        self.assertEqual(rep["rounds"][0]["gate"]["played"], 0)  # nothing unchecked goes on
        self.assertFalse((self.dir / run.MATCHES_FILE).exists())
        self.assertFalse(calls.stopping)
        self.assertTrue(no_match_threads())


class Notes:
    """The run's quick notes (arena/notes.py RunNotes shape): one held after each lost match."""

    def __init__(self):
        self.held = []

    def after_loss(self, m, judged_, match_id):
        self.held.append({"text": f"note from {match_id}", "match": match_id})
        return {"match": match_id}

    def clear(self, round_no):
        self.held = []
        return []


class NotesByGroup(P):
    def test_a_loss_in_group_one_reaches_group_two_and_not_its_own_group(self):
        saw, barrier = {}, threading.Barrier(3, timeout=WAIT)

        def play(self, card_, match_id, *, training=False, **kw):
            if training:
                barrier.wait()  # the whole group is in flight before anyone reads the notes
                saw[match_id[-3:]] = [h["match"][-3:] for h in self.notes.held]
                time.sleep(0.05)  # a group mate's loss has every chance to land, if it could
            return fake_match(self, card_, match_id, not match_id.endswith("-t01"))
        cards = [card(i, "size") for i in range(1, 7)]
        with mock.patch.object(run, "PARALLEL", 3), mock.patch.object(run.Arena, "play", play):
            rep = self.arena(cards, Customer(), matches=6, rounds=1, notes=Notes()).run()
        self.assertEqual(saw["t01"], [])
        self.assertEqual(saw["t02"], [])  # its own group never sees the loss of t01
        self.assertEqual(saw["t03"], [])
        for k in ("t04", "t05", "t06"):
            self.assertEqual(saw[k], ["t01"])  # the next group plays with it
        self.assertEqual(rep["rounds"][0]["training"]["notes_handed"], 3)
        self.assertTrue(no_match_threads())


class WholeLines(P):
    def test_concurrent_writes_leave_only_whole_lines(self):
        path = self.dir / run.MATCHES_FILE
        big = "x" * 200_000  # far past one buffer, so a split write would show

        def write(i):
            for j in range(10):
                run.append_line(path, json.dumps({"i": i, "j": j, "pad": big}))
        threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sorted((r["i"], r["j"]) for r in rows), [(i, j) for i in range(8) for j in range(10)])

    def test_a_write_waits_for_the_one_lock(self):
        path = self.dir / run.MATCHES_FILE
        with run.WRITE_LOCK:
            t = threading.Thread(target=run.append_line, args=(path, "{}"))
            t.start()
            t.join(0.2)
            self.assertFalse(path.exists() and path.read_text(encoding="utf-8"))
        t.join(WAIT)
        self.assertEqual(path.read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
    unittest.main()
