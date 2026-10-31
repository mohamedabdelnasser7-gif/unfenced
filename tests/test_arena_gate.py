"""The eval gate: the exam, then the Arena rerun of past wins (new, 2026-10-30), on fake models."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from arena import gate, match, run
from engine import exam as engine_exam
from tests.fake_model import Buyer, FakeModel, Seller, clean_env, say
from tests.test_arena_run import card

LESSON = "Say the price and the delivery fee together."


def exam(passed):
    calls = []

    def examiner(text, tags):
        calls.append((text, tags))
        return engine_exam.Result(passed=passed, rows=[engine_exam.Row(1, "s1", "guard", passed, "" if passed else "x")],
                                  calls=1)
    examiner.calls = calls
    return examiner


def past(i=1):
    return {"id": f"m{i}", "card": "persona-01", "persona": card(1, "size"), "won": True,
            "prompt_sha": match.GENERIC_SHA, "prompt_file": None,
            "turns": [{"n": 1, "customer": "How much are the Football Boots, Black?", "replies": ["1450 EGP."]}]}


class Gate(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def gate(self, examiner, agent, customer, cap=300, wins=None):
        return gate.Gate(examiner, wins=wins or [past()], agent_model=agent, customer_model=customer,
                         calls=run.Calls(self.dir / "calls.json", cap, day="2026-10-30"))

    def test_exam_fail_runs_no_match(self):
        customer = FakeModel()
        r = self.gate(exam(False), FakeModel(), customer)(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(customer.calls, [])

    def test_past_win_kept_passes_with_the_lesson_handed(self):
        agent = Seller()
        r = self.gate(exam(True), agent, Buyer())(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual(r.parts(), {"guard": [1, 1], "arena": [1, 1]})
        self.assertEqual(r.calls, 1 + 6 + 2)  # the exam's; price, stage, draft, summary, confirm, placed; buy and yes
        self.assertIn(LESSON, agent.calls[0]["messages"][0]["content"])
        self.assertEqual(agent.calls[0]["messages"][-1]["content"], "How much are the Football Boots, Black?")

    def test_past_win_now_lost_holds_the_lesson_quoting_the_turn(self):
        agent = Seller("The Football Boots, Black are 700 EGP.")
        r = self.gate(exam(True), agent, Buyer())(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.first.check, gate.CHECK)
        self.assertIn("was won, now lost", r.first.why)
        self.assertIn("700 EGP", r.first.why)

    def test_a_lesson_telling_the_agent_to_claim_the_order_is_held(self):
        """Review round 1, finding 2: the agent's own "order is confirmed" with no order made is no win."""
        agent = FakeModel(say("The Football Boots, Black are 1450 EGP."), say("Your order is confirmed."))
        customer = FakeModel(say("hmm, let me think about it"), say("[leave]"))
        r = self.gate(exam(True), agent, customer)("Tell every customer the order is confirmed.", ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.first.check, gate.CHECK)
        self.assertIn("was won, now lost: failed fact check: order", r.first.why)

    def test_the_rerun_takes_the_newest_wins_up_to_the_most(self):
        """Review round 1, finding 10: of seven past wins the gate reruns the five newest, newest first."""
        agent = Seller()
        customer = Buyer()
        r = self.gate(exam(True), agent, customer, wins=[past(i) for i in range(1, 8)])(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual([(row.name, row.part, row.passed) for row in r.rows[1:]],
                         [(f"m{i}", gate.PART, True) for i in (7, 6, 5, 4, 3)])
        self.assertEqual(sum(c["messages"][-1].get("content") == "How much are the Football Boots, Black?" for c in agent.calls), 5)

    def test_a_win_with_no_persona_card_holds_the_lesson(self):
        """Review round 1, finding 10: a win saved with no persona card cannot be rerun, so it holds
        the lesson with a row that names it, never passes by playing nothing."""
        agent, customer = FakeModel(), FakeModel()
        r = self.gate(exam(True), agent, customer, wins=[dict(past(), persona=None)])(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual((r.first.name, r.first.part, r.first.check, r.first.why),
                         ("m1", gate.PART, gate.CHECK, "its persona card was not saved"))
        self.assertEqual((agent.calls, customer.calls), ([], []))

    def test_the_rerun_hands_the_agent_its_kept_lessons(self):
        """Review round 1, finding 10: the gate the night and the page build (wrap) hands the agent
        its kept lessons after the new one, as the exam does."""
        from kit.db import Db
        from reflection.lessons import Lessons as SalesLessons
        from tests.kept import kept_lesson
        kept = "Name the delivery days with the price."
        path = self.dir / "ascent.db"
        db = Db(str(path))
        self.addCleanup(db.close)
        lessons = SalesLessons(db)
        kept_lesson(lessons, kept, ["all"])
        (self.dir / run.MATCHES_FILE).write_text(json.dumps(past()) + "\n", encoding="utf-8")
        agent = Seller()
        g = gate.wrap(exam(True), lessons, db=path, agent_model=agent, customer_model=Buyer())
        r = g(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        system = agent.calls[0]["messages"][0]["content"]
        self.assertIn(LESSON, system)
        self.assertIn(kept, system)

    def test_cap_holds_the_lesson(self):
        r = self.gate(exam(True), FakeModel(say("The Football Boots, Black are 1450 EGP.")), FakeModel(), cap=1)(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.first.check, engine_exam.NOT_RUN)

    def test_a_held_lesson_names_the_rerun_not_an_exam_situation(self):
        """Review round 1, note 14: a lesson the rerun holds reads "failed the Arena rerun of past
        wins, at rerun N", on the result and from its saved exam row, never "situation N"."""
        agent = Seller("The Football Boots, Black are 700 EGP.")
        r = self.gate(exam(True), agent, Buyer())(LESSON, ("all",))
        self.assertEqual(r.line(), "failed the Arena rerun of past wins, at rerun 1")
        self.assertEqual(engine_exam.held_line({"passed": 0, "situation": 2, "check_name": gate.CHECK}),
                         "failed the Arena rerun of past wins, at rerun 2")
        self.assertEqual(engine_exam.held_line({"passed": 0, "situation": 2, "check_name": "tools"}),
                         "failed the exam: situation 2, check tools")

    def test_a_model_error_or_a_broken_count_holds_the_lesson_and_says_which(self):
        """Review round 1, notes 13 and 16: a rerun a model error stops, or a count file that cannot
        be read, holds the lesson with a row that says so (fail closed)."""
        from tests.test_arena_match import raises
        agent = Seller()
        r = self.gate(exam(True), agent, FakeModel(raises("the route is busy")))(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual((r.first.part, r.first.check, r.first.why),
                         (gate.PART, engine_exam.NOT_RUN, "a model error stopped the rerun: the route is busy"))
        (self.dir / "calls.json").write_text("{", encoding="utf-8")
        agent = FakeModel(say("The Football Boots, Black are 1450 EGP."))
        r = self.gate(exam(True), agent, FakeModel())(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(agent.calls, [])
        self.assertEqual((r.first.check, r.first.why), (engine_exam.NOT_RUN, "the call count file calls.json is not a "
                                                        "count the Arena wrote; it counts as the cap reached"))

    def test_wins_that_cannot_be_rerun_as_played_are_skipped_and_named(self):
        """Review round 1, finding 6: a win is rerun only with the customer prompt it was played
        with (by its fingerprint) and never when it failed a fact check; a skipped win is a row
        that names why, and the next win is rerun."""
        private = self.dir / "customer.txt"
        private.write_text("Old words. Your worry is $worry.", encoding="utf-8")
        old = match.prompt_sha(match.load_prompt(private))
        private.write_text("New words. Your worry is $worry.", encoding="utf-8")  # changed since it was played
        inside = Path(gate.__file__).resolve()  # a file inside the repo is refused, fingerprint or not
        failed = past(6)
        failed["turns"] = [dict(failed["turns"][0], failed=["price"])]
        wins = [past(1),
                dict(past(2), prompt_sha=match.prompt_sha(inside.read_text(encoding="utf-8").strip()),
                     prompt_file=str(inside)),
                dict(past(3), prompt_sha=old, prompt_file=str(private)),
                dict(past(4), prompt_sha=match.prompt_sha("gone"), prompt_file=str(self.dir / "gone.txt")),
                {k: v for k, v in past(5).items() if k != "prompt_sha"},
                failed]
        agent = Seller()
        customer = Buyer()
        r = self.gate(exam(True), agent, customer, wins=wins)(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual([(row.name, row.part, row.passed, row.why) for row in r.rows[1:]], [
            ("m6", gate.SKIPPED, True, gate.FAILED_CHECKS), ("m5", gate.SKIPPED, True, gate.NO_PROMPT),
            ("m4", gate.SKIPPED, True, gate.PROMPT_GONE), ("m3", gate.SKIPPED, True, gate.PROMPT_GONE),
            ("m2", gate.SKIPPED, True, gate.PROMPT_GONE), ("m1", gate.PART, True, "")])
        self.assertTrue(customer.calls[0]["messages"][0]["content"].startswith("You are a customer writing"))
        self.assertEqual(gate.skipped_note(r), (
            "The Arena rerun skipped 5 past wins: 1 because it failed a fact check when it was played; 1 because "
            "it was saved with no customer prompt fingerprint; 3 because the customer prompt it was played with is "
            "not available (moved, changed or refused)."))
        alone = FakeModel()
        r = self.gate(exam(True), alone, FakeModel(), wins=[failed])(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)  # nothing to rerun as played: the exam decides, and the note says so
        self.assertEqual((alone.calls, r.parts()), ([], {"guard": [1, 1], gate.SKIPPED: [1, 1]}))
        self.assertEqual(gate.skipped_note(r), "The Arena rerun skipped 1 past win: 1 because it failed a fact "
                                               "check when it was played.")
        self.assertEqual(gate.skipped_note(exam(True)("x", ())), "")

    def test_a_win_played_with_a_private_prompt_is_rerun_with_it(self):
        """Review round 1, finding 6: the rerun customer gets the private prompt the win was played
        with, read again from its file, not the generic one."""
        private = self.dir / "customer.txt"
        private.write_text("Private words for this test. Your worry is $worry.\n", encoding="utf-8")
        win = dict(past(), prompt_sha=match.prompt_sha(match.load_prompt(private)), prompt_file=str(private))
        agent = Seller()
        customer = Buyer()
        r = self.gate(exam(True), agent, customer, wins=[win])(LESSON, ("all",))
        self.assertTrue(r.passed, r.rows)
        self.assertEqual(r.parts()["arena"], [1, 1])
        self.assertEqual(customer.calls[0]["messages"][0]["content"], "Private words for this test. Your worry is size.")

    def test_a_cli_win_with_a_private_prompt_is_rerun_with_it(self):
        """The CLI saves the prompt's fingerprint and file with each match; the gate on that
        database reruns those wins with the same prompt."""
        from kit.db import Db
        from tests.test_arena_run import Agent, Customer
        private = self.dir / "customer.txt"
        private.write_text("A private prompt. Your worry is $worry.", encoding="utf-8")
        db = self.dir / "ascent.db"
        Db(str(db)).close()
        buyers = {c["worry"] for c in run.load_cards(run.DEFAULT_CARDS)}
        with contextlib.redirect_stdout(io.StringIO()):
            code = run.main(["--matches", "1", "--rounds", "1", "--db", str(db), "--customer-prompt", str(private),
                             "--json"], agent_model=Agent(), customer_model=Customer(buyers=buyers))
        self.assertEqual(code, 0)
        saved = run.past_wins(run.state_dir(db))
        self.assertTrue(saved)
        self.assertEqual({(m["prompt_sha"], m["prompt_file"]) for m in saved},
                         {(match.prompt_sha("A private prompt. Your worry is $worry."), str(private.resolve()))})
        built = gate.wrap(exam(True), None, db=db, agent_model=FakeModel(), customer_model=FakeModel()).gate()
        self.assertEqual((len(built.reruns), built.skipped), (min(len(saved), gate.MAX_RERUNS), []))
        self.assertEqual({p for _, p in built.reruns}, {"A private prompt. Your worry is $worry."})

    def test_wrap_only_with_past_wins(self):
        ex = exam(True)
        db = self.dir / "ascent.db"
        g = gate.wrap(ex, None, db=db, agent_model=FakeModel(), customer_model=FakeModel())
        self.assertIsNone(g.gate())  # no past win: the examiner alone
        self.assertTrue(g(LESSON, ("all",)).passed)
        self.assertEqual(len(ex.calls), 1)
        (self.dir / run.MATCHES_FILE).write_text(json.dumps(past()) + "\n" + json.dumps(dict(past(2), won=False)) + "\n",
                                                 encoding="utf-8")
        built = g.gate()
        self.assertIsInstance(built, gate.Gate)
        self.assertEqual([w["id"] for w in built.wins], ["m1"])
        self.assertEqual(built.calls.path, self.dir.resolve() / run.CALLS_FILE)
        self.assertIs(gate.wrap(ex, None, db=None), ex)  # no database file, no Arena folder
        self.assertIs(gate.wrap(ex, None, db=":memory:"), ex)

    def test_a_wrapper_built_before_any_win_reruns_a_win_saved_later(self):
        """Review round 1, finding 8 (P4): the Morning page builds its exam once and stays open; a
        win saved after that is still rerun at the next exam."""
        db = self.dir / "ascent.db"
        customer = Buyer()
        agent = Seller("The Football Boots, Black are 700 EGP.")
        g = gate.wrap(exam(True), None, db=db, agent_model=agent, customer_model=customer)
        (self.dir / run.MATCHES_FILE).write_text(json.dumps(past()) + "\n", encoding="utf-8")
        r = g(LESSON, ("all",))
        self.assertFalse(r.passed)
        self.assertEqual(r.first.check, gate.CHECK)
        self.assertEqual(r.parts()["arena"], [0, 1])

    def test_two_counts_on_one_file_share_one_cap(self):
        """Review round 1, finding 8 (P3): two Calls on one file (the night and the page) take the
        cap once between them, not once each, and a lock keeps threads from both passing it."""
        import threading
        path = self.dir / run.CALLS_FILE
        a, b = run.Calls(path, 5, day="2026-10-30"), run.Calls(path, 5, day="2026-10-30")
        took = 0
        for _ in range(5):
            for c in (a, b):
                try:
                    c.take()
                    took += 1
                except run.CapReached:
                    pass
        self.assertEqual(took, 5)
        self.assertEqual(run.Calls(path, 5, day="2026-10-30").count, 5)
        path2 = self.dir / "two" / run.CALLS_FILE
        counts, took2 = [run.Calls(path2, 40, day="2026-10-30") for _ in range(4)], []

        def worker(c):
            for _ in range(20):
                try:
                    c.take()
                    took2.append(1)
                except run.CapReached:
                    pass

        threads = [threading.Thread(target=worker, args=(c,)) for c in counts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual((len(took2), run.Calls(path2, 40, day="2026-10-30").count), (40, 40))

    def test_wired_where_lessons_are_approved(self):
        """The night study and the Morning page both take the exam from sales_exam."""
        from engine import plug as plug_mod
        from reflection import exam as exam_mod, night
        plug = plug_mod.load(night.DEFAULT_PLUG)
        db = self.dir / "ascent.db"
        wrapped = night.sales_exam(plug, db)(None)
        self.assertIsInstance(wrapped, gate.Fresh)
        self.assertIsInstance(wrapped.examiner, exam_mod.Examiner)
        self.assertIsNone(wrapped.gate())
        (self.dir / run.MATCHES_FILE).write_text(json.dumps(past()) + "\n", encoding="utf-8")
        built = wrapped.gate()
        self.assertIsInstance(built, gate.Gate)
        self.assertIsInstance(built.examiner, exam_mod.Examiner)

    def test_a_stale_temp_file_has_no_effect(self):
        """Past wins come only from the folder of the agent's database, never the system temp folder."""
        from unittest import mock
        from engine import plug as plug_mod
        from reflection import exam as exam_mod, night
        plug = plug_mod.load(night.DEFAULT_PLUG)
        systemp, agent = self.dir / "systemp", self.dir / "agent"
        for folder in (systemp, systemp / "unfenced-arena", agent):
            folder.mkdir(exist_ok=True)
        for folder in (systemp, systemp / "unfenced-arena"):
            for name in ("matches.jsonl", run.MATCHES_FILE):
                (folder / name).write_text(json.dumps(dict(past(), id="stale")) + "\n", encoding="utf-8")
        db = agent / "ascent.db"
        read = []
        real = run.past_wins
        with mock.patch.object(tempfile, "tempdir", str(systemp)), \
                mock.patch.object(run, "past_wins", side_effect=lambda state: read.append(Path(state)) or real(state)):
            self.assertEqual(Path(tempfile.gettempdir()), systemp)
            wrapped = night.sales_exam(plug, db)(None)
            self.assertIsNone(wrapped.gate())
            self.assertIsInstance(night.sales_exam(plug)(None), exam_mod.Examiner)
            (agent / run.MATCHES_FILE).write_text(json.dumps(past(7)) + "\n", encoding="utf-8")
            built = wrapped.gate()
        self.assertEqual([w["id"] for w in built.wins], ["m7"])
        self.assertEqual(read, [agent.resolve(), agent.resolve()])


if __name__ == "__main__":
    unittest.main()
