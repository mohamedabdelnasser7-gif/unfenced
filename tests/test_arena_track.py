"""The Arena track for an agent made here (DECISIONS 104; reflection/morning.py last_run, arena_summary,
hotfix_counts, run_train, stop_run; reflection/reflect_now.py built_cases; pages.py summary_html, train_card):
Run the Arena first; on a run that did not pass, the summary card (won N of M, the main reasons with counts, the
quick notes line), Train on every match that run lost, gate matches included, and the correction box, which sits
outside every part the poll swaps. Fake models only: no model call, no network; every line here is made up."""
import html.parser
import json
import time
import unittest
from unittest import mock

from arena import learn_built, run as run_mod
from engine import exam as engine_exam
from kit import turn
from reflection import morning as mo, pages, reflect_now
import tests.test_reflect_button as trb

ARENA_TAB = {"tab": ["arena"]}
AGENT = "stock_watch"


def stamp(at):
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(at))


class LiveParts(html.parser.HTMLParser):
    """Where each form sits: inside a data-live element (swapped by the poll) or not."""

    def __init__(self):
        super().__init__()
        self.stack, self.forms = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.forms.append((a.get("action"), [k for k in self.stack if k]))
        if tag not in ("input", "br", "img", "meta", "link", "path", "circle"):
            self.stack.append(a.get("data-live"))

    def handle_endtag(self, tag):
        if tag not in ("input", "br", "img", "meta", "link", "path", "circle") and self.stack:
            self.stack.pop()


def live_parts_of(page):
    p = LiveParts()
    p.feed(page)
    return dict(p.forms)


class Base(trb.Base):
    def setUp(self):
        super().setUp()
        self.m.arena_models = lambda: (trb.Quiet(), trb.Quiet(), trb.Quiet())
        self.held = []
        self.m.arena_start = lambda work, name: self.held.append((work, name))

    def full_run(self, whys, won=1, at=None):
        """A full run of the agent, as Run the Arena leaves it: its item (never sealed) and its judged matches in
        the folder's matches file, won training matches first, then a lost match for each why (gate matches from
        the third on). Returns its run id."""
        at = time.time() - 60 if at is None else at
        run = stamp(at)
        doc = {"agent": AGENT, "kind": "arena_rounds", "at": at, "run": run, "line": "The Arena ran 1 round.",
               "gate_won": 0, "gate_played": 1, "needs": 7, "stopped": "rounds", "quick": False, "lost": []}
        (self.dir / f"arena-{AGENT}-{run}.json").write_text(json.dumps(doc), encoding="utf-8")
        plug = turn.load(self.folder).plug
        rows = []
        for k in range(won):
            rows.append(dict(trb.match(f"{run}-r1-t{k + 1:02d}", True)))
        for i, why in enumerate(whys):
            mid = f"{run}-r1-t{won + i + 1:02d}" if i < 2 else f"{run}-r1-g{i - 1:02d}"
            m = dict(trb.match(mid, False), why=why)
            m["quote"] = {"turn": 2, "who": "customer", "text": "made-up customer words 7731"}
            if "-t" in mid:  # a lost training match is a case as it plays (the learner)
                learn_built.to_case(self.db, plug, m, {"won": False, "why": why, "quote": m["quote"]}, mid)
            rows.append(m)
        with open(self.folder / run_mod.MATCHES_FILE, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in rows))
        return run

    def tab(self):
        return self.page(query=ARENA_TAB)


class Summary(Base):
    WHYS = ["the customer left after this reply", "the customer left after this reply", "failed fact check",
            "the customer left after this reply", "no sale within the turns", "failed fact check",
            "a never line was broken", "something no group names"]

    def test_won_n_of_m_counts_every_judged_match_and_the_reasons_sum_to_the_rest(self):
        run = self.full_run(self.WHYS, won=2)
        s = self.m.arena_summary(AGENT)
        self.assertEqual((s["run"], s["won"], s["played"], s["lost"]), (run, 2, 10, 8))
        self.assertEqual(s["reasons"], [("The customer left after a reply", 3), ("A fact check failed", 2),
                                        ("A never line was broken", 1), (mo.REASON_OTHER, 2)])
        self.assertEqual(sum(n for _, n in s["reasons"]), s["played"] - s["won"])
        self.assertIsNone(s["notes"])

    def test_the_card_shows_counts_only_and_no_notes_line_without_notes(self):
        self.full_run(self.WHYS, won=2)
        page = self.tab()
        self.assertIn("Last run: won 2 of 10.", page)
        self.assertIn('<ul class="rsn" aria-label="What the last run lost">', page)
        self.assertIn("<li>The customer left after a reply: 3</li>", page)
        self.assertIn("<li>Other reasons: 2</li>", page)
        self.assertNotIn("made-up customer words 7731", page)  # never a customer's words
        self.assertNotIn("something no group names", page)
        self.assertNotIn("Fixed itself during the run", page)

    def test_the_notes_line_shows_the_runs_quick_notes(self):
        run = self.full_run(self.WHYS[:2])
        self.m._ran[AGENT] = {"run": run, "notes": {"written": 2, "stopped": 1}}
        self.assertIn("Fixed itself during the run: 2 quick notes written, 1 stopped by the safety check.", self.tab())
        self.m._ran[AGENT] = {"run": run, "notes": {"written": 1, "stopped": 0}}
        self.assertIn("Fixed itself during the run: 1 quick note written, 0 stopped by the safety check.", self.tab())
        self.m._ran[AGENT] = {"run": "20200101T000000", "notes": {"written": 9, "stopped": 9}}  # another run's
        self.assertNotIn("Fixed itself during the run", self.tab())

    def test_hotfix_counts_reads_written_and_stopped_rows_only(self):
        rep = {"rounds": [{"training": {"notes": [{"note": "Ask the size first."}, {"why": "stopped: a never line"},
                                                  {"why": "the writer failed"}, {"note": "", "why": "dropped"}]}},
                          {"training": {"notes": [{"note": "Name the price."}]}}]}
        self.assertEqual(mo.hotfix_counts(rep), {"written": 2, "stopped": 1})
        self.assertIsNone(mo.hotfix_counts({"rounds": [{"training": {}}]}))  # no notes key: no line
        self.assertEqual(mo.hotfix_counts({"rounds": [{"training": {"notes": []}}]}), {"written": 0, "stopped": 0})

    def test_a_passed_run_or_none_has_no_card(self):
        self.assertIsNone(self.m.arena_summary(AGENT))
        self.assertIsNone(self.m.last_run(AGENT))
        self.assertNotIn("Last run: won", self.tab())

    def test_matches_of_another_run_or_a_bad_line_never_count(self):
        run = self.full_run(self.WHYS[:2], won=1)
        with open(self.folder / run_mod.MATCHES_FILE, "a", encoding="utf-8") as f:
            f.write("not json\n")
            f.write(json.dumps({"id": "20200101T000000-r1-t01", "won": False}) + "\n")
            f.write(json.dumps({"id": f"{run}-r1-t09", "won": "no"}) + "\n")  # won not a bool
            f.write(json.dumps({"id": f"{run}-x", "won": False}) + "\n")
        last = self.m.last_run(AGENT)
        self.assertEqual((last["won"], last["played"], len(last["lost"])), (1, 3, 2))


class Train(Base):
    def done(self, pending):
        def study(db, db_path, between, *, steps, stop=None):
            pending.extend(between.pending)
            return {"lost": len(between.pending), "proposed": 0, "passed": 0, "cards": [], "notes": [], "queued": 0}
        return study

    def test_train_studies_every_lost_match_of_the_run_gate_matches_included(self):
        run = self.full_run(["no stock answer", "no stock answer", "no stock answer", "no stock answer"], won=1)
        self.assertEqual(self.m.arena_status(AGENT)["next"], "train")
        self.assertEqual(self.m.run_train(AGENT), mo.TRAIN_STARTED)
        pending = []
        with mock.patch.object(reflect_now, "study_built", self.done(pending)):
            self.held[0][0]()
        ids = [f"{run}-r1-t02", f"{run}-r1-t03", f"{run}-r1-g01", f"{run}-r1-g02"]
        self.assertEqual(pending, [learn_built.case_id(AGENT, i) for i in ids])
        self.assertIsNone(self.m.arena_note(AGENT))
        done = self.m.trained(AGENT)
        self.assertEqual((done["lost"], done["run"]), (4, run))
        with self.db.tx() as c:  # each gate loss is a case now, written once
            n = c.execute("SELECT COUNT(DISTINCT case_id) FROM trace WHERE case_id LIKE ?",
                          (f"arena-{AGENT}-{run}-%",)).fetchone()[0]
        self.assertEqual(n, 4)
        self.assertEqual(self.m.arena_status(AGENT)["next"], "arena")  # then Run the Arena again, never Connect
        self.assertFalse(self.m.arena_status(AGENT)["ready"])

    def test_refusals_start_nothing_and_lose_nothing(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.run_train(AGENT)
        self.assertEqual(str(e.exception), mo.TRAIN_NO_RUN)
        self.full_run([], won=3)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_train(AGENT)
        self.assertEqual(str(e.exception), mo.TRAIN_NO_LOSS)
        self.assertEqual(mo.TRAIN_NO_LOSS, "The last run lost no match, so there is nothing to train on.")
        self.assertEqual((self.held, self.m.training(AGENT), self.m.trained(AGENT)), ([], None, None))
        self.assertNotIn(f'action="{mo.TRAIN_PATH}"', self.tab())  # no Train button on a run that lost nothing

    def test_while_train_runs_the_arena_reflection_and_a_second_train_are_refused_and_stop_stops_it(self):
        self.full_run(["no stock answer"])
        self.m.run_train(AGENT)
        self.assertEqual(self.m.training(AGENT), reflect_now.READ)
        for go, line in ((self.m.run_train, mo.TRAIN_TWICE), (self.m.run_arena, mo.TRAIN_TWICE)):
            with self.subTest(go=go.__name__), self.assertRaises(mo.Refused) as e:
                go(AGENT)
            self.assertEqual(str(e.exception), line)
        self.lose()
        with self.assertRaises(mo.Refused) as e:
            self.m.run_reflection(AGENT)
        self.assertEqual(str(e.exception), mo.REFLECT_TRAINING)
        self.assertEqual(self.starts, [])
        self.assertEqual(self.m.stop_run(AGENT), mo.STOPPING)
        self.assertTrue(self.m._stops[AGENT].is_set())
        self.assertEqual(len(self.held), 1)

    def test_stop_with_nothing_running_is_refused(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.stop_run(AGENT)
        self.assertEqual(str(e.exception), mo.STOP_NONE)

    def test_train_is_refused_while_the_arena_runs(self):
        self.full_run(["no stock answer"])
        self.m.run_arena(AGENT, full=True)
        with self.assertRaises(mo.Refused) as e:
            self.m.run_train(AGENT)
        self.assertEqual(str(e.exception), mo.TRAIN_ARENA)
        self.assertNotIn("Last run: won", self.tab())  # the card waits while a run goes
        self.assertNotIn(f'action="{mo.TRAIN_PATH}"', self.tab())


class CorrectionBox(Base):
    def test_it_is_open_before_any_run_and_outside_every_part_the_poll_swaps(self):
        forms = live_parts_of(self.tab())
        self.assertEqual(forms["/correct"], [])
        self.assertIn("arena", forms[pages.ARENA_PATH])

    def test_it_survives_the_poll_while_train_and_while_a_run_go(self):
        self.full_run(["no stock answer"])
        forms = live_parts_of(self.tab())
        self.assertEqual(forms["/correct"], [])
        self.assertEqual(forms[mo.TRAIN_PATH], ["train"])  # Train sits in the swapped part, the box does not
        self.m.run_train(AGENT)
        page = self.tab()
        self.assertIn('data-live="train" data-running', page)
        forms = live_parts_of(page)
        self.assertEqual(forms["/correct"], [])
        self.assertIn(mo.STOP_PATH, forms)
        self.held.clear()
        self.m._train.clear()
        self.m._stops.clear()
        self.m.run_arena(AGENT, full=True)
        page = self.tab()
        self.assertIn('data-live="arena" data-running', page)
        self.assertEqual(live_parts_of(page)["/correct"], [])


class Stop(Base):
    def test_stop_during_train_reaches_its_study(self):
        self.full_run(["no stock answer"])
        self.m.run_train(AGENT)
        seen = []

        def study(db, db_path, between, *, steps, stop=None):
            seen.append(stop())
            self.assertEqual(self.p.actions[mo.STOP_PATH](self.m, {"agent": [AGENT]}), mo.STOPPING)  # the page's Stop
            seen.append(stop())
            return {"lost": 1, "proposed": 0, "passed": 0, "cards": [], "notes": [], "queued": 2}
        with mock.patch.object(reflect_now, "study_built", study):
            self.held[0][0]()
        self.assertEqual(seen, [False, True])
        self.assertEqual(self.m.trained(AGENT)["queued"], 2)
        self.assertNotIn(AGENT, self.m._stops)  # gone once it ends: a second Stop is refused
        with self.assertRaises(mo.Refused) as e:
            self.m.stop_run(AGENT)
        self.assertEqual(str(e.exception), mo.STOP_NONE)

    def test_stop_during_run_reflection_reaches_its_run(self):
        self.lose()
        self.m.run_reflection(AGENT)
        self.assertEqual(self.m.stop_run(AGENT), mo.STOPPING)
        seen = []

        def run(db, db_path, plug, **kw):
            seen.append(kw["stop"]())
            raise RuntimeError("made up: the run ends here")
        with mock.patch.object(reflect_now, "run", run):
            self.starts[0][0]()
        self.assertEqual(seen, [True])
        self.assertNotIn(AGENT, self.m._stops)

    def test_stop_for_an_agent_not_here_or_not_a_name_is_refused(self):
        for agent in ("nobody", None, ["x"]):
            with self.subTest(agent=agent), self.assertRaises(mo.Refused) as e:
                self.m.stop_run(agent)
            self.assertEqual(str(e.exception), mo.STOP_NONE)


class OneLitButton(Base):
    def lit(self):
        """Which of Run the Arena and Train is lit (class yes) on the Arena tab, and which are there."""
        page = self.tab()
        out = {}
        for name, path in (("arena", pages.ARENA_PATH), ("train", mo.TRAIN_PATH)):
            parts = page.split(f'action="{path}"')
            if len(parts) == 2:
                out[name] = '<button class="yes"' in parts[1].split("</form>")[0]
        return out

    def test_one_next_step_is_lit_at_each_point_of_the_track(self):
        self.assertEqual(self.lit(), {"arena": True})  # before any run
        self.full_run(["no stock answer"], at=time.time() - 120)
        self.assertEqual(self.lit(), {"arena": False, "train": True})  # a run that lost: Train
        self.m._trained[AGENT] = {"at": time.time(), "cards": [3], "lost": 1, "written": 1, "passed": 1, "notes": [],
                                  "queued": 0, "seen": [], "run": "x"}
        self.assertEqual(self.lit(), {"arena": True, "train": False})  # after Train: Run the Arena again
        self.assertIn(f"{mo.ARENA_AGAIN}</button>", self.tab())


class Revise(unittest.TestCase):
    """Edit on a live lesson (Morning.revise, DECISIONS 100): passed, failed, the exam could not run, no exam."""

    def setUp(self):
        import tests.test_morning as tm
        self.tm = tm
        base = tm.Base(methodName="setUp")
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.lessons = base.lessons
        self.live = tm.kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="tester", now=tm.NOW)
        self.seen = []
        self.result = engine_exam.Result(True, [engine_exam.Row(1, "s1", "guard", True)], calls=1)

        def examiner(text, stages):
            self.seen.append(text)
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
        self.m = mo.Morning(base.db, [base.plug], reports=base.dir, judge=tm.always_low, exams={"waterer": examiner})

    def unchanged(self):
        les = self.lessons.get(self.live)
        self.assertEqual((les["state"], les["text"], len(self.lessons.mine())),
                         (self.tm.KEPT, "Water the grown beds deeply.", 1))

    def test_a_version_that_passes_replaces_it_and_the_old_line_stays_in_the_history(self):
        said = self.m.revise(self.live, "Water the grown beds at dusk.", now=self.tm.NOW + 1)
        new = max(les["id"] for les in self.lessons.mine())
        self.assertEqual(said, f"Lesson {self.live} edited: the new line is lesson {new}. It is on trial.")
        old = self.lessons.get(self.live)
        self.assertEqual((old["state"], old["text"]), (self.tm.PULLED, "Water the grown beds deeply."))
        self.assertEqual(self.lessons.get(new)["text"], "Water the grown beds at dusk.")
        self.assertEqual(self.seen, ["Water the grown beds at dusk."])

    def test_a_version_that_fails_changes_nothing(self):
        self.result = engine_exam.Result(False, [engine_exam.Row(2, "s2", "guard", False, "tone", "too long")], calls=1)
        said = self.m.revise(self.live, "Water the grown beds at dusk.", now=self.tm.NOW + 1)
        self.assertEqual(said, mo.REVISE_FAILED.format(line="failed the exam on situation 2: too long", id=self.live))
        self.unchanged()

    def test_an_exam_that_cannot_run_changes_nothing(self):
        self.result = RuntimeError("made up: the exam broke")
        said = self.m.revise(self.live, "Water the grown beds at dusk.", now=self.tm.NOW + 1)
        self.assertEqual(said, mo.REVISE_FAILED.format(line="failed the exam: it could not run", id=self.live))
        self.unchanged()

    def test_no_exam_here_or_the_same_words_take_no_exam_and_change_nothing(self):
        with self.assertRaises(mo.Refused) as e:
            self.m.revise(self.live, "Water the grown beds deeply.")
        self.assertIn("the same as the old one", str(e.exception))
        self.m.exams = {}
        with self.assertRaises(mo.Refused) as e:
            self.m.revise(self.live, "Water the grown beds at dusk.")
        self.assertEqual(str(e.exception), mo.REVISE_NO_EXAM)
        self.assertEqual(self.seen, [])
        self.unchanged()


class EditRows(Base):
    def test_a_lessons_words_are_escaped_in_its_edit_row(self):
        from engine.lessons import Lessons as EngineLessons
        from tests.kept import kept_lesson
        kept_lesson(EngineLessons(self.db, self.m.plugs[AGENT]), '<script>alert(1)</script> "x"', ["all"],
                    yes_by="test", skip_exam=True)
        page = self.tab()
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &quot;x&quot;", page)
        self.assertIn(f'action="{mo.REVISE_PATH}"', page)
        self.assertNotIn(f'action="{mo.REVISE_PATH}"', self.page(query=ARENA_TAB, token=None))  # no token: no form


if __name__ == "__main__":
    unittest.main()
