"""sim/score.py: week 1 against later weeks on simulated cases, and the remove-a-lesson proof.
Every case is made up and the model parts are scripted, so no model is called and nothing
goes over the network.

Each guard below failed on a mutant in a scratch copy before it was kept:
- the same seed gives the same numbers (mutant: a case's follow draw from random.random());
- the gain disappears without the lift (mutant: a case given any lesson ends good by itself);
- the run with the lesson pulled matches the run with no lessons (mutant: the pull skipped);
- unknown lift keys are refused (mutant: the lift's keys check widened);
- over four weeks, every case counts in the week it started (mutant: weeks 3 and 4 counted in
  week 2);
- the pulled run pulls every line a lift names, even one only it wrote (mutant: only the
  lines the first run gave are pulled);
- a pulled run that gave a line all the same says so (mutant: the plain lines dropped);
- each night checks the trials, then studies the night runner's own window (mutants: the
  study first; the window halved);
- an action is handed its lessons by its own time (mutant: by its case's start);
- a lift line no candidate writes is refused (mutant: the check removed)."""
import calendar
import copy
from collections import Counter
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from engine.lessons import Lessons
from engine.log import Log
from engine.study import BAD, GOOD, LEFT_OUT, PENDING, Study, chance_better
from engine.trial import Trials
from kit.db import Db
from reflection import night as night_runner
from sim import score, scripted, simulate
from tests.kept import kept_lesson

ROOT = Path(__file__).resolve().parent.parent
SALES = plug_mod.load(ROOT / "sales/plug.json")
SC = simulate.load(ROOT / "sim/scenarios/sales.json")
# the planted line and the null line, written out here so a changed scenario cannot move what is expected
LINE = "Before you send the summary, ask the buyer what size they normally wear."
NULL = "When a customer asks about the printing, say it is done with UV DTF."
SEEDS = (29, 30, 31, 32, 33)
ASKED = "Asked which size they usually wear before the summary."


def changed(sc, **kw):
    out = copy.deepcopy(sc)
    out.update(kw)
    return out


def no_lift(sc):
    out = copy.deepcopy(sc)
    out.pop("lift")
    return out


def week2(r):
    w = r["weeks"][1]
    return w["good"], w["settled"]


def runs(sc, seed, *modes):
    return [score.one_run(SALES, sc, seed=seed, mode=m) for m in modes]


FOUR = 4
SEEDS4 = (2, 29)
ONLY = 8  # over four weeks, the first run never writes the null line and the pulled run does, on night 24
SIX = 6  # weeks 5 and 6 come after the 14 day careful trials and their verdicts
KEPT = 4  # over six weeks, the size line's trial keeps it before week 5


def week(r, n):
    w = r["weeks"][n - 1]
    return w["good"], w["settled"]


def outcomes(r):
    """How every week's cases ended, without how many were given a lesson."""
    return [(w["cases"], w["settled"], w["good"], w["left_out"], w["pending"]) for w in r["weeks"]]


def cli(*args):
    return subprocess.run([sys.executable, "-I", str(ROOT / "sim/score.py"), *args], capture_output=True, text=True,
                          timeout=120)


class TheLift(unittest.TestCase):
    def test_the_scenario_plants_the_lift_on_the_learned_line(self):
        self.assertEqual(simulate.check(SALES, SC)["lift"],
                         [{"lesson": LINE, "trait": "size_check", "value": "asked", "follows": 0.9}])

    def test_a_case_given_the_lesson_ends_good_more_often(self):
        # sure chances, so the lift alone decides: asked always ends good, never asked never does.
        # The ring keeps its detail but loses its own chance, which would come before the rates.
        # Both logs run a day past the end, so every case has its order or has gone quiet.
        ring = {k: v for k, v in SC["groups"][0].items() if k != "rate"}
        sc = changed(SC, rate=1.0, rates=[{"when": {"size_check": "never"}, "rate": 0.0}], groups=[ring],
                     lift=[dict(SC["lift"][0], follows=1)])
        until = calendar.timegm(time.strptime(SC["start"], "%Y-%m-%d")) + (SC["days"] + 1) * simulate.DAY
        plain_db, db = Db(":memory:"), Db(":memory:")
        self.addCleanup(plain_db.close)
        self.addCleanup(db.close)
        plain = {c["id"]: c for c in simulate.simulate(plain_db, SALES, sc, until=until)["cases"]}
        lessons = Lessons(db, SALES)
        kept_lesson(lessons, LINE, ["ordering"], yes_by="the test")  # kept at once: every case is given it
        man = simulate.simulate(db, SALES, sc, lessons=lessons, until=until)
        lifted = [c for c in man["cases"] if c["lifted"]]
        self.assertEqual({c["id"] for c in lifted},
                         {i for i, c in plain.items() if c["traits"]["size_check"] == "never"})
        settled = [c for c in lifted if c["status"] in (GOOD, BAD)]
        self.assertGreater(len(settled), 20)
        for c in settled:
            self.assertEqual((c["lifted"], c["traits"]["size_check"], c["status"]),
                             ({"size_check": "never"}, "asked", GOOD))
            self.assertEqual(plain[c["id"]]["status"], BAD)
            steps = [r for r in Log(db, SALES).case(c["id"]) if r["step"] is not None]
            self.assertEqual(steps[1]["detail"]["said"], ASKED)
            self.assertIn(1, steps[1]["lessons"])
        self.assertEqual([c["given"] for c in man["cases"]], [[1]] * len(man["cases"]))

    def test_a_lesson_given_after_the_traits_step_changes_nothing(self):
        # the line is given only at the ordering stage, after the message is heard at step 0
        sc = changed(SC, lift=[{"lesson": LINE, "trait": "message", "value": "printing"}])
        db = Db(":memory:")
        self.addCleanup(db.close)
        lessons = Lessons(db, SALES)
        kept_lesson(lessons, LINE, ["ordering"], yes_by="the test")
        man = simulate.simulate(db, SALES, sc, lessons=lessons)
        self.assertTrue(all(c["given"] == [1] for c in man["cases"]))
        self.assertEqual([c for c in man["cases"] if c["lifted"]], [])

    def test_an_action_is_handed_by_its_own_time(self):
        # hand_from falls inside one case, between its second and third step
        plain_db, db = Db(":memory:"), Db(":memory:")
        self.addCleanup(plain_db.close)
        self.addCleanup(db.close)
        man = simulate.simulate(plain_db, SALES, SC)
        cut = "sim-sales-0100"
        hand_from = Log(plain_db, SALES).case(cut)[0]["at"] + 0.25 * simulate.HOUR
        lessons = Lessons(db, SALES)
        kept_lesson(lessons, LINE, ["ordering"], yes_by="the test", now=man["since"])  # kept: every case at ordering
        simulate.simulate(db, SALES, SC, lessons=lessons, hand_from=hand_from)
        rows = [r for rows in Log(db, SALES).window(man["since"], man["until"]).values() for r in rows]
        steps = [r for r in rows if r["step"] is not None]
        self.assertEqual(len(steps), len(SC["steps"]) * SC["cases"])
        for r in steps:
            self.assertEqual(list(r["lessons"]), [1] if r["at"] >= hand_from and r["stage"] == "ordering" else [], r)
        ended = [r for r in rows if r["step"] is None]
        self.assertTrue(ended)
        self.assertEqual([list(r["lessons"]) for r in ended], [[]] * len(ended))  # how a case ended is handed nothing
        self.assertEqual([list(r["lessons"]) for r in Log(db, SALES).case(cut) if r["step"] is not None],
                         [[], [], [1]])


class Determinism(unittest.TestCase):
    def test_the_same_seed_gives_the_same_numbers(self):
        half = changed(SC, lift=[dict(SC["lift"][0], follows=0.5)])  # every follow draw counts
        for seed in (29, 31):
            with self.subTest(seed=seed):
                a, b = (json.dumps(score.score(SALES, half, seed=seed), sort_keys=True) for _ in range(2))
                self.assertEqual(a, b)
                self.assertTrue(json.loads(a)["runs"]["learned"]["lifted"])
        self.assertEqual(score.score(SALES, SC), score.score(SALES, SC, seed=SC["seed"]))
        out = [subprocess.run([sys.executable, "-I", str(ROOT / "sim/score.py"), "--json"], capture_output=True,
                              text=True, check=True, timeout=120).stdout for _ in range(2)]
        self.assertEqual(out[0], out[1])
        self.assertEqual(json.loads(out[0]), json.loads(json.dumps(score.score(SALES, SC))))

    def test_another_seed_gives_other_numbers(self):
        a, b = score.score(SALES, SC), score.score(SALES, SC, seed=30)
        self.assertNotEqual([w["good"] for w in a["runs"]["learned"]["weeks"]],
                            [w["good"] for w in b["runs"]["learned"]["weeks"]])


class TheGain(unittest.TestCase):
    def test_the_lesson_lifts_week_2_over_the_same_run_without_it(self):
        learned = none = 0
        for seed in SEEDS:
            a, n = runs(SC, seed, score.LEARNED, score.NONE)
            learned += week2(a)[0]
            none += week2(n)[0]
            self.assertEqual(week2(a)[1], week2(n)[1])
            self.assertGreaterEqual(week2(a)[0], week2(n)[0])
        self.assertGreater(learned, none)

    def test_the_gain_disappears_without_the_lift(self):
        sc = no_lift(SC)
        for seed in SEEDS:
            with self.subTest(seed=seed):
                a, n = runs(sc, seed, score.LEARNED, score.NONE)
                self.assertEqual(a["lifted"], [])
                given = [les for les in a["lessons"] if les["line"] == LINE]
                self.assertEqual(len(given), 1)
                self.assertGreater(given[0]["week_2"]["with"]["cases"], 0)  # it was given, and changed nothing
                # the same cases end the same way; only the count of cases given a lesson differs
                self.assertEqual([{k: v for k, v in w.items() if k != "given"} for w in a["weeks"]],
                                 [{k: v for k, v in w.items() if k != "given"} for w in n["weeks"]])
                self.assertEqual([w["given"] for w in n["weeks"]], [0, 0])


class TheProof(unittest.TestCase):
    def test_the_pulled_run_matches_the_no_lesson_run(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                s = score.score(SALES, SC, seed=seed)
                pulled = s["runs"]["pulled"]
                none = score.one_run(SALES, SC, seed=seed, mode=score.NONE)
                self.assertIn(LINE, [p["line"] for p in pulled["pulled"]])
                self.assertEqual(outcomes(pulled)[0], outcomes(s["runs"]["learned"])[0])  # week 1 ends the same
                self.assertEqual(pulled["lifted"], [])
                (g1, n1), (g0, n0) = week2(pulled), week2(none)
                self.assertEqual(n1, n0)
                self.assertLessEqual(abs(g1 - g0), 0)  # within noise: here none, both runs draw the same numbers
                self.assertTrue(0.4 < chance_better(g1, n1, g0, n0) < 0.6)
                for les in pulled["lessons"]:
                    if les["line"] == LINE:
                        self.assertEqual(les["week_2"]["with"]["cases"], 0)

    def test_the_default_seed_pulls_the_lesson_before_day_8(self):
        s = score.score(SALES, SC)
        self.assertEqual([(p["line"], p["night"]) for p in s["runs"]["pulled"]["pulled"]], [(LINE, 7)])
        self.assertGreater(week2(s["runs"]["learned"])[0], week2(s["runs"]["pulled"])[0])

    def test_the_pulled_run_pulls_a_lift_line_only_it_wrote(self):
        # seed 8 over four weeks: the first run never writes the null line, the pulled run
        # writes it on night 24. Here a lift names it, so the pulled run must pull it too.
        self.assertIn(NULL, [c["lesson"] for c in SC["script"]["candidates"]])
        sc = changed(SC, lift=SC["lift"] + [{"lesson": NULL, "trait": "size_check", "value": "asked"}])
        s = score.score(SALES, sc, seed=ONLY, weeks=FOUR)
        first, pulled = s["runs"]["learned"], s["runs"]["pulled"]
        none = score.one_run(SALES, sc, seed=ONLY, mode=score.NONE, weeks=FOUR)
        self.assertNotIn(NULL, [les["line"] for les in first["lessons"]])
        self.assertEqual([(p["line"], p["night"]) for p in pulled["pulled"]], [(LINE, 7), (NULL, 24)])
        self.assertEqual((pulled["lifted"], [w["given"] for w in pulled["weeks"]]), ([], [0, 0, 0, 0]))
        self.assertEqual(outcomes(pulled), outcomes(none))
        self.assertNotIn("Given all the same", score.text(s))

    def test_a_line_the_pulled_run_gave_all_the_same_is_printed(self):
        # the same seed with the scenario as it is: no lift names the null line, so it is not
        # pulled, and the 19 week 4 cases given it are said plainly
        self.assertNotIn(NULL, [r["lesson"] for r in SC["lift"]])
        s = score.score(SALES, SC, seed=ONLY, weeks=FOUR)
        pulled = s["runs"]["pulled"]
        self.assertEqual([w["given"] for w in pulled["weeks"]], [0, 0, 0, 19])
        les = [x for x in pulled["lessons"] if x["cases_given"]]
        self.assertEqual([(x["line"], x["night"], x["given_by_week"]) for x in les], [(NULL, 24, [0, 0, 0, 19])])
        self.assertEqual(pulled["lifted"], [])
        lines = score.text(s).splitlines()
        self.assertIn("Given all the same in the second run, in 19 cases: a line the first run gave in no case and "
                      "no lift names, so it was not pulled. A lesson changed 0 of the cases in that run.", lines)
        self.assertIn(f'  - lesson {les[0]["lesson_id"]}, night 24: "{NULL}", given in 19 cases, week by '
                      "week: 0, 0, 0, 19", lines)


class TheNights(unittest.TestCase):
    """Each night runs as reflection/night.py runs one: the trial check, then the study over the
    runner's own window, both at the night's time."""

    @staticmethod
    def spied(fn):
        calls = []
        check, study = Trials.check, Study.run

        def spy_check(this, now=None):
            calls.append(("trial check", now))
            return check(this, now)

        def spy_study(this, since, until, *, now=None, **kw):
            calls.append(("study", since, until, now))
            return study(this, since, until, now=now, **kw)

        with mock.patch.object(Trials, "check", spy_check), mock.patch.object(Study, "run", spy_study):
            out = fn()
        return calls, out

    def test_each_night_checks_the_trials_then_studies_the_night_runners_window(self):
        until = calendar.timegm(time.strptime(SC["start"], "%Y-%m-%d")) + 21.0 * simulate.DAY

        def runner():
            db = Db(":memory:")
            try:
                proposer, tagger, fit, adapter = scripted.parts(SC)
                return night_runner.night(db, SALES, until=until, others=[], judge=scripted.judge_says_low,
                                          proposer=proposer, tagger=tagger, fit=fit, adapter=adapter)
            finally:
                db.close()

        ran, _ = self.spied(runner)
        window = 2 * simulate.DAY  # twice the day an order can take to come in
        self.assertEqual(ran, [("trial check", until), ("study", until - window, until, until)])
        calls, r = self.spied(lambda: score.one_run(SALES, SC))
        self.assertEqual(r["nights"], 9)  # the end of day 7 to the end of day 15, when the score is read
        nights = [r["split"] + d * simulate.DAY for d in range(r["nights"])]
        self.assertEqual(calls, [c for t in nights for c in (("trial check", t), ("study", t - window, t, t))])

    def test_a_line_close_to_one_pulled_that_night_waits_for_a_yes(self):
        # Where the order shows: a close rewording of the planted line, tagged on the question
        # about colours, whose chance is high up to day 20 and drops from day 20, first wins on
        # night 22, the night the trial pulls the planted line (seed 42, six weeks, careful). The
        # trial check comes first, so the rewording is close to a pulled line and waits for a
        # yes; with the study first it would go on trial and be given.
        reword = "Before you send the summary, ask each buyer what size they normally wear."
        sc = copy.deepcopy(SC)
        sc["rates"] = [{"when": {"message": "colours", "day": list(range(20, 42))}, "rate": 0.2},
                       {"when": {"message": "colours", "day": list(range(0, 20))}, "rate": 0.95}] + sc["rates"]
        sc["script"]["candidates"].append(
            {"pattern": "The customer asked which colours the boots come in.", "helps": False, "lesson": reword,
             "situation": "Getting an order ready to send.", "stages": ["ordering"],
             "tag": {"key": "heard", "has": "colours"}})
        r = score.one_run(SALES, sc, seed=42, weeks=SIX)
        by_line = {les["line"]: les for les in r["lessons"]}
        planted = by_line[LINE]
        self.assertEqual((planted["trial"]["status"], planted["trial"]["night"]), ("pulled", 22))
        les = by_line[reword]
        self.assertEqual((les["night"], les["state"], les["trial"], les["cases_given"]),
                         (22, "waits for a yes", None, 0))


class LongerRuns(unittest.TestCase):
    """--weeks N: the scenario over more weeks at the same cases a day. A careful trial runs 14
    days and its verdict can wait a day more for results, so at six weeks, weeks 5 and 6 come
    after the trials."""

    def test_the_same_seed_gives_the_same_numbers(self):
        for seed in SEEDS4:
            with self.subTest(seed=seed):
                a, b = (json.dumps(score.score(SALES, SC, seed=seed, weeks=FOUR), sort_keys=True)
                        for _ in range(2))
                self.assertEqual(a, b)
                self.assertTrue(json.loads(a)["runs"]["learned"]["lifted"])
        out = [cli("--weeks", "4", "--json") for _ in range(2)]
        self.assertEqual([o.returncode for o in out], [0, 0])
        self.assertEqual(out[0].stdout, out[1].stdout)
        self.assertEqual(json.loads(out[0].stdout), json.loads(json.dumps(score.score(SALES, SC, weeks=FOUR))))

    def test_every_case_counts_in_the_week_it_started(self):
        long = score.stretched(SALES, SC, FOUR)
        self.assertEqual((long["days"], long["cases"], long["seed"]), (28, 600, SC["seed"]))
        self.assertIs(score.stretched(SALES, SC), SC)
        db = Db(":memory:")
        self.addCleanup(db.close)
        started = Counter(c["day"] // 7 + 1 for c in simulate.simulate(db, SALES, long)["cases"])
        r = score.one_run(SALES, SC, weeks=FOUR)
        self.assertEqual([w["cases"] for w in r["weeks"]], [started[n] for n in (1, 2, 3, 4)])
        self.assertEqual([w["days"] for w in r["weeks"]], [[1, 7], [8, 14], [15, 21], [22, 28]])
        self.assertEqual([w["pending"] for w in r["weeks"]], [0, 0, 0, 0])
        self.assertEqual(r["read_at"], r["since"] + (28 + 1) * simulate.DAY)
        self.assertEqual([x["week"] for x in r["against"]], [2, 3, 4])
        self.assertEqual((r["gain"], r["chance"]), (r["against"][-1]["gain"], r["against"][-1]["chance"]))

    def test_the_kept_lesson_reaches_most_of_week_6_and_lifts_it(self):
        s = score.score(SALES, SC, seed=KEPT, weeks=SIX)
        a = s["runs"]["learned"]
        none = score.one_run(SALES, SC, seed=KEPT, mode=score.NONE, weeks=SIX)
        les = next(x for x in a["lessons"] if x["line"] == LINE)
        self.assertEqual(les["trial"]["status"], "kept")
        self.assertLessEqual(les["trial"]["night"], 28)  # kept before week 5 starts
        self.assertGreater(les["given_by_week"][5], 0.9 * a["weeks"][5]["cases"])
        self.assertEqual(week(a, 6)[1], week(none, 6)[1])
        self.assertGreater(week(a, 6)[0], week(none, 6)[0])
        self.assertGreater(a["chance"], 0.95)

    def test_the_gain_disappears_without_the_lift(self):
        sc = no_lift(SC)
        for seed in SEEDS4:
            with self.subTest(seed=seed):
                a, n = (score.one_run(SALES, sc, seed=seed, mode=m, weeks=FOUR) for m in (score.LEARNED, score.NONE))
                self.assertEqual(a["lifted"], [])
                self.assertGreater(sum(w["given"] for w in a["weeks"][1:]), 0)  # given, and changed nothing
                self.assertEqual(outcomes(a), outcomes(n))

    def test_the_pulled_run_matches_the_no_lesson_run(self):
        for seed in SEEDS4:
            with self.subTest(seed=seed):
                s = score.score(SALES, SC, seed=seed, weeks=FOUR)
                pulled = s["runs"]["pulled"]
                none = score.one_run(SALES, SC, seed=seed, mode=score.NONE, weeks=FOUR)
                self.assertIn(LINE, [p["line"] for p in pulled["pulled"]])
                self.assertEqual(outcomes(pulled)[0], outcomes(s["runs"]["learned"])[0])  # week 1 ends the same
                self.assertEqual((pulled["lifted"], [w["given"] for w in pulled["weeks"]]), ([], [0, 0, 0, 0]))
                self.assertEqual(outcomes(pulled), outcomes(none))  # within noise: here none, the same draws
                (g1, n1), (g0, n0) = week(pulled, 4), week(none, 4)
                self.assertTrue(0.4 < chance_better(g1, n1, g0, n0) < 0.6)

    def test_the_printed_run_shows_all_three(self):
        s = score.score(SALES, SC, weeks=SIX)
        lines = score.text(s).splitlines()
        a = s["runs"]["learned"]
        self.assertIn("week 1 (days 1 to 7, before any lesson) against week 6 (days 36 to 42)", lines[1])
        self.assertEqual(lines[2], "Trial level careful: each trial gives its lesson in 20% of the cases at its stages "
                                   "for 14 days.")
        self.assertTrue(lines[5].endswith("gain          chance week 6 beats week 1"), lines[5])
        row = [x for x in lines if x.startswith("  with what the nights learned")]
        self.assertEqual(len(row), 1, lines)
        for w in a["weeks"]:
            self.assertIn(score._share(w), row[0])
        self.assertIn(f'{a["gain"]:+.1f} points', row[0])
        self.assertTrue(row[0].endswith(score._pct(a["chance"])), row[0])
        one, two = a["weeks"][0], a["against"][0]
        self.assertAlmostEqual(two["chance"], chance_better(*week(a, 2), *week(a, 1)))
        self.assertIn(f'  week 2: {score._share(a["weeks"][1])} against {score._share(one)}, {two["gain"]:+.1f} points, '
                      f'chance week 2 beats week 1 {score._pct(two["chance"])}', lines)
        self.assertNotIn("is real", score.text(s))
        les = next(x for x in a["lessons"] if x["line"] == LINE)
        t = les["trial"]
        self.assertAlmostEqual(t["chance"], chance_better(t["with"]["good"], t["with"]["settled"],
                                                          t["without"]["good"], t["without"]["settled"]))
        self.assertIn(f'  lesson {les["lesson_id"]}, on trial from night {les["night"]}: with it {score._share(t["with"])}, '
                      f'without it {score._share(t["without"])}; chance it is better {score._pct(t["chance"])}; '
                      f'{t["status"]} on night {t["night"]}', lines)
        self.assertIn("  cases" + " " * 29 + "".join(f'{w["cases"]:<20}' for w in a["weeks"]).rstrip(), lines)

    def test_other_weeks_are_refused(self):
        for weeks in (1, 9, 0, True, 2.0, "4", None):
            with self.subTest(weeks=weeks), self.assertRaisesRegex(ValueError, "weeks: a whole number from 2 to 8"):
                score.one_run(SALES, SC, weeks=weeks)
        done = cli("--weeks", "1")
        self.assertEqual((done.returncode, done.stdout), (2, ""))
        self.assertIn("weeks: a whole number from 2 to 8", done.stderr)


class Refused(unittest.TestCase):
    def test_unknown_lift_keys_are_refused(self):
        base = SC["lift"][0]
        cases = (
            ("an unknown key", [dict(base, boost=0.2)], "unknown key 'boost'"),
            ("a missing value", [{k: v for k, v in base.items() if k != "value"}], "missing 'value'"),
            ("not a trait", [dict(base, trait="mood")], "'mood' is not a trait"),
            ("not a value", [dict(base, value="sometimes")], "has no value 'sometimes'"),
            ("follows over 1", [dict(base, follows=1.5)], "follows: a chance from 0 to 1"),
            ("follows true", [dict(base, follows=True)], "follows: a number"),
            ("an empty line", [dict(base, lesson=" ")], "one line of text"),
            ("two lines", [dict(base, lesson="One.\nTwo.")], "one line of text"),
            ("a line no candidate writes", [dict(base, lesson="Ask the buyer for a size.")],
             "not one of the script's candidate lines"),
            ("a candidate's pattern, not its line", [dict(base, lesson=SC["script"]["candidates"][0]["pattern"])],
             "not one of the script's candidate lines"),
            ("not a list", base, "lift: a list"),
            ("one lesson and trait twice", [base, dict(base, value="never")], "the same lesson and trait twice"),
        )
        for what, lift, msg in cases:
            with self.subTest(what), self.assertRaisesRegex(ValueError, msg):
                simulate.check(SALES, changed(SC, lift=lift))
        with self.assertRaisesRegex(ValueError, "unknown key 'lifts'"):
            simulate.check(SALES, changed(SC, lifts=SC["lift"]))

    def test_a_scenario_of_other_days_is_refused(self):
        with self.assertRaisesRegex(ValueError, "days: 14"):
            score.one_run(SALES, changed(SC, days=10))

    def test_an_unknown_agent_is_refused(self):
        for agent in ("nobody", "../sales", ""):
            with self.subTest(agent=agent), self.assertRaises(ValueError):
                score.pair(agent)
        done = subprocess.run([sys.executable, "-I", str(ROOT / "sim/score.py"), "--plug", "nobody"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout), (2, ""))
        self.assertIn("no scenario in sim/scenarios for 'nobody'", done.stderr)

    def test_a_case_not_labelled_simulated_is_refused(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        man = simulate.simulate(db, SALES, SC)
        Log(db, SALES).act("sim-sales-9999", "reply", result="replied", stage="asking", detail={}, at=man["since"])
        split = man["since"] + score.WEEK * simulate.DAY
        with self.assertRaisesRegex(ValueError, "sim-sales-9999: a case not labelled simulated"):
            score._tally(db, SALES, Lessons(db, SALES), man, split, man["until"])


class Printed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = score.score(SALES, SC)
        cls.lines = score.text(cls.s).splitlines()
        cls.six = score.score(SALES, SC, weeks=SIX)
        cls.six_kept = score.score(SALES, SC, seed=KEPT, weeks=SIX)

    def test_every_case_is_simulated_and_settled_when_read(self):
        self.assertTrue(self.s["simulated"])
        start = calendar.timegm(time.strptime(SC["start"], "%Y-%m-%d"))
        self.assertEqual(self.s["read_at"], start + (14 + 1) * simulate.DAY)
        for r in self.s["runs"].values():
            self.assertEqual(sum(w["cases"] for w in r["weeks"]), SC["cases"])
            self.assertEqual([w["pending"] for w in r["weeks"]], [0, 0])
            for w in r["weeks"]:
                self.assertEqual(w["settled"] + w["left_out"], w["cases"])
        # week 1's cases start before any lesson; one still open after night 7 can be given one
        # at a later step (TheLift); with the lesson pulled, none is
        self.assertEqual(self.s["runs"]["pulled"]["weeks"][0]["given"], 0)
        self.assertNotIn(LEFT_OUT, (PENDING,))

    def test_the_printed_score_matches_the_data(self):
        for mode, label in (("learned", "with what the nights learned"), ("pulled", "the same, its lessons pulled")):
            r = self.s["runs"][mode]
            one, two = r["weeks"]
            row = [x for x in self.lines if x.startswith(f"  {label}")]
            self.assertEqual(len(row), 1, self.lines)
            for w in (one, two):
                self.assertIn(f'{w["good"]} of {w["settled"]} ({round(w["share"] * 100)}%)', row[0])
            self.assertIn(f'{r["gain"]:+.1f} points', row[0])
            self.assertTrue(row[0].endswith(score._pct(r["chance"])), row[0])
            self.assertAlmostEqual(r["chance"], chance_better(two["good"], two["settled"], one["good"], one["settled"]))
        self.assertIn("pulled the night it was written, before any case was given it: lesson 1 (night 7).",
                      self.lines[-1])
        self.assertTrue(self.lines[5].endswith("gain          chance week 2 beats week 1"), self.lines[5])
        for s in (self.s, self.six, self.six_kept):  # the default seed's and the kept seed's pulled runs gave nothing
            self.assertEqual([w["given"] for w in s["runs"]["pulled"]["weeks"]], [0] * s["weeks"])
            self.assertNotIn("Given all the same", score.text(s))

    def test_the_default_seed_tells_the_story(self):
        # the run a page quotes: the size line on trial from night 7 in 1 case in 5, week 2 above
        # week 1 with a chance over 95% and above week 2 with the lesson pulled; over six weeks
        # its trial keeps it and week 6 beats week 1 with a chance over 95%
        a, p = self.s["runs"]["learned"], self.s["runs"]["pulled"]
        les = next(x for x in a["lessons"] if x["line"] == LINE)
        self.assertEqual((les["night"], les["share"], les["state"]), (7, 0.2, "trying"))
        self.assertGreater(les["week_2"]["with"]["cases"], 0)
        self.assertGreater(a["gain"], 0)
        self.assertGreater(a["chance"], 0.95)
        self.assertGreater(a["weeks"][1]["share"], p["weeks"][1]["share"])
        six = self.six["runs"]["learned"]
        self.assertEqual(next(x for x in six["lessons"] if x["line"] == LINE)["trial"]["status"], "kept")
        self.assertGreater(six["chance"], 0.95)


class Levels(unittest.TestCase):
    """--level: the run sets the level switch before its first night, so every trial takes that
    level's share and days from the plug."""

    def test_a_fast_run_gives_each_trial_the_fast_share(self):
        s = score.score(SALES, SC, level="fast")
        self.assertEqual(s["level"], {"name": "fast", "share": 0.5, "days": 7})
        self.assertEqual([r["level"] for r in s["runs"].values()], ["fast", "fast"])
        self.assertEqual(score.text(s).splitlines()[2], "Trial level fast: each trial gives its lesson in 50% of the "
                                                         "cases at its stages for 7 days.")
        les = next(x for x in s["runs"]["learned"]["lessons"] if x["line"] == LINE)
        self.assertEqual(les["share"], 0.5)
        careful = score.score(SALES, SC)
        self.assertEqual(careful["level"], {"name": "careful", "share": 0.2, "days": 14})
        self.assertEqual([r["level"] for r in careful["runs"].values()], ["careful", "careful"])
        out = cli("--level", "fast", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["level"]["name"], "fast")

    def test_other_levels_are_refused(self):
        for level in ("slow", "Fast", "", None, True):
            with self.subTest(level=level), self.assertRaisesRegex(ValueError, "level: fast or careful"):
                score.one_run(SALES, SC, level=level)
        done = cli("--level", "slow")
        self.assertEqual((done.returncode, done.stdout), (2, ""))
        self.assertIn("invalid choice", done.stderr)


if __name__ == "__main__":
    unittest.main()
