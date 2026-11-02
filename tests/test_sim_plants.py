"""Step 5 part B2: the simulator and its plants. Made-up cases go into the real log through
the engine's own API, the real night study reads them, and each plant is checked against
the manifest, the simulator's own record of what it planted and how each case stands:
- a real pattern becomes a lesson card, with the numbers the manifest gives;
- a cause outside the agent is left out by name, never reaches the tagger, and the decoy
  pattern it would make is never a lesson;
- a bad source never goes on trial. On marketing the sources rule refuses spam from one
  account, and the copied words mark holds it when it is spread over 4 accounts. On the
  Sales agent one case is one source, so the copied words mark alone holds a ring of cases.
On the Sales agent a placed order decides: a chat ends good when the store takes the order.
A live chat that goes quiet closes after an hour with chat_closed, not good (DECISIONS item 54);
the Sales scenario sets bad to null, so its quiet chats carry no deciding row and settle not
good past the order's one day window, the engine's way for a chat that never closed.
The study tags a seeded sample of study.TAGGED settled cases when there are more, so every
count is checked on the cases the tagger read.
Reflection across agents is checked with spies: the fit check, Lessons.adapt and a judge that
must read marketing's own risk lines. The model parts are the scripted ones in
sim/scripted.py; no model is called and nothing goes over the network."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from engine import risk, study
from engine.lessons import DAY, TRYING, WAITING, Lessons
from engine.log import Log
from engine.study import BAD, GOOD, LEFT_OUT, PENDING, Study
from kit.db import Db
from sim import run, scripted, simulate
from tests import plugs
from tests import test_engine_quickcheck as quickcheck
from tests.kept import kept_lesson

ROOT = Path(__file__).resolve().parent.parent
SALES = plug_mod.load(ROOT / "sales/plug.json")
MARKETING = plug_mod.load(ROOT / "marketing/plug.json")
SALES_SCENARIO = simulate.load(ROOT / "sim/scenarios/sales.json")
_NO_BAD = json.loads((ROOT / "sales/plug.json").read_text(encoding="utf-8"))
_NO_BAD["decides"]["bad"] = []
SALES_NO_BAD = plug_mod.from_dict(_NO_BAD, ROOT / "sales")  # the Sales plug as it was before chat_closed
MK_SCENARIO = simulate.load(ROOT / "sim/scenarios/marketing.json")
BOTH = ((SALES, SALES_SCENARIO), (MARKETING, MK_SCENARIO))
CHOSEN = {"sales": 182, "marketing": 29}  # each scenario's own seed, the one its single night tests read

# the planted lines, written out here so a changed scenario cannot move what is expected
SALES_REAL = "Before you send the summary, ask the buyer what size they normally wear."
SALES_DECOY = "Warn buyers who pick size 45 in the Superfly 11 Elite or the F50 Elite that it may run out."
SALES_BAD = "Tell every buyer to hurry up because these pieces are almost gone."
MK_REAL = "Put the price in the first line of every post."
MK_DECOY = "Do not post on Thursdays."
MK_BAD = "Always tell people to hurry because everyone wants this."
MK_FROM_SALES_REAL = "Under each post, invite buyers to say their size and their area when they write in."
MK_FROM_SALES_BAD = "Tell every buyer to hurry up in each post."
PLANTS = {  # agent: (real, decoy, bad, how the manifest marks each)
    "sales": ((SALES_REAL, lambda c: c["traits"]["size_check"] == "never"),
              (SALES_DECOY, lambda c: c["traits"]["boots"] == "sold_out"),
              (SALES_BAD, lambda c: c["group"] == "ring")),
    "marketing": ((MK_REAL, lambda c: c["traits"]["first_line"] == "price"),
                  (MK_DECOY, lambda c: c["weekday"] == "thu"),
                  (MK_BAD, lambda c: c["group"] == "spam")),
}
# one null candidate per script, on a trait no plant touches: at the chosen seed the chance bar alone stops it
SALES_NULL = ("The customer asked about the name printing.",
              lambda c: c["traits"]["message"] == "printing" and c["group"] != "ring")
SALES_NULL_LINE = "When a customer asks about the printing, say it is done with UV DTF."
MK_NULL = ("The post was a video.", lambda c: c["traits"]["format"] == "video")
NEVER_ON_TRIAL = {SALES_DECOY, SALES_BAD, MK_DECOY, MK_BAD, MK_FROM_SALES_BAD}
COPIED = risk.COPIED
SCRIPTED = "Candidates are scripted to match what was planted; the study only counts and decides."


@contextlib.contextmanager
def tagged():
    """The cases the tagger read for each pattern, every time a study counted it:
    {(agent whose cases were counted, pattern): [case ids]}."""
    read, now, count, view = {}, [], study.Study._count, study._view

    def spy_view(plug, case, texts, *, blind):
        if blind:
            now.append(case.id)
        return view(plug, case, texts, blind=blind)

    def spy_count(self, plug, cand, *a):
        now.clear()
        got = count(self, plug, cand, *a)
        read.setdefault((plug.agent, cand["pattern"]), []).append(frozenset(now))
        return got

    with mock.patch.object(study, "_view", spy_view), mock.patch.object(study.Study, "_count", spy_count):
        yield read


def night(seed=None, pairs=run.AGENTS):
    """run.night, with the scripted parts it made and the cases the tagger read kept:
    {agent: (plug, manifest, report)}, parts, read."""
    made, real = [], scripted.parts

    def parts(*scenarios):
        made.append(real(*scenarios))
        return made[-1]

    with mock.patch.object(scripted, "parts", parts), tagged() as read:
        out = run.night(pairs, seed=seed)
    return {p.agent: (p, man, rep) for p, man, rep in out}, made[0], read


def tally(man, has, ids):
    """A pattern counted from the manifest as the study counts it: the settled cases the tagger
    read, with and without it."""
    settled = [c for c in man["cases"] if c["status"] in (GOOD, BAD) and c["id"] in ids]
    out = {}
    for side, cases in (("with", [c for c in settled if has(c)]), ("without", [c for c in settled if not has(c)])):
        out[side] = {"cases": len(cases), "good": sum(c["status"] == GOOD for c in cases),
                     "sources": len({c["source"] for c in cases})}
    out["ids"] = {c["id"] for c in settled if has(c)}
    return out


def why_lines(card):
    return [x for x in (card["risk_why"] or "").split("; ") if x]


class Plants(unittest.TestCase):
    def cand(self, rep, lesson, *, rep_key="candidates"):
        found = [c for c in rep[rep_key] if c["lesson"] == lesson]
        self.assertEqual(len(found), 1, f"candidates for {lesson!r}: {found}")
        return found[0]

    def card(self, rep, lesson):
        found = [c for c in rep["cards"] if c["change"] == lesson]
        self.assertLessEqual(len(found), 1, lesson)
        return found[0] if found else None

    def has_card(self, rep, lesson):
        card = self.card(rep, lesson)
        self.assertIsNotNone(card, f"no card for {lesson!r}")
        return card

    def read_for(self, read, man, pattern):
        """The cases the tagger read for the pattern on the manifest's cases: every settled case
        up to study.TAGGED, a sample of that many past it, and the same each time it is counted."""
        times = read[(man["agent"], pattern)]
        self.assertEqual(len(set(times)), 1, pattern)
        settled = {c["id"] for c in man["cases"] if c["status"] in (GOOD, BAD)}
        self.assertLessEqual(times[0], settled)
        self.assertEqual(len(times[0]), min(len(settled), study.TAGGED))
        return times[0]

    def assert_counts(self, man, rep):
        st = Counter(c["status"] for c in man["cases"])
        left = [c for c in man["cases"] if c["status"] == LEFT_OUT]
        self.assertEqual(rep["read"]["cases"], len(man["cases"]))
        self.assertEqual((rep["decided"]["good"], rep["decided"]["bad"], rep["pending"], rep["left_out"]["count"]),
                         (st[GOOD], st[BAD], st[PENDING], st[LEFT_OUT]))
        self.assertFalse(any(c["status"] == BAD and c["deciding"] is None for c in man["cases"]))  # no timer (item 66)
        self.assertEqual(rep["left_out"]["by_cause"], dict(Counter(c["cause"] for c in left)))
        self.assertEqual({c["case"] for c in rep["left_out"]["cases"]}, {c["id"] for c in left})

    def assert_numbers(self, rec, man, has, read):
        ids = self.read_for(read, man, rec["pattern"])
        want = tally(man, has, ids)
        self.assertEqual(rec["tagged"], len(ids))
        self.assertEqual((rec["with"], rec["without"], rec["unknown"]), (want["with"], want["without"], 0))
        return want

    def assert_null_has_no_gap(self, man, rep, null, read):
        """At the chosen seed the null candidate has the cases and sources to be judged, and the
        chance bar alone says no. Other seeds may make it a lesson, as a one sided bar allows."""
        self.assertEqual(man["seed"], CHOSEN[man["agent"]])
        pattern, has = null
        rec = next(c for c in rep["candidates"] if c["pattern"] == pattern)
        self.assert_numbers(rec, man, has, read)
        self.assertGreaterEqual(min(rec["with"]["cases"], rec["without"]["cases"]), study.MIN_CASES)
        self.assertGreaterEqual(min(rec["with"]["sources"], rec["without"]["sources"]), study.MIN_SOURCES)
        self.assertLess(rec["chance"], study.CHANCE)
        self.assertEqual(rec["verdict"], study.NO_GAP)
        self.assertIsNone(self.card(rep, rec["lesson"]))

    def assert_only_copied(self, card):
        lines = why_lines(card)
        self.assertTrue(lines)
        self.assertTrue(all(x.startswith(COPIED) for x in lines), lines)
        self.assertEqual((card["risk"], card["state"]), (risk.HIGH, WAITING))


class Simulator(Plants):
    """The simulator writes the same rows for the same seed, labels every row, keeps every
    row inside the window, and refuses a scenario that names what the plug did not declare."""

    def rows(self, plug, sc, **kw):
        db = Db(":memory:")
        self.addCleanup(db.close)
        man = simulate.simulate(db, plug, sc, **kw)
        return man, Log(db, plug).query()

    def test_the_same_seed_gives_the_same_rows(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                man1, rows1 = self.rows(plug, sc)
                man2, rows2 = self.rows(plug, sc)
                self.assertEqual(rows1, rows2)
                self.assertEqual(man1, man2)
                self.assertEqual(man1["seed"], sc["seed"])
                self.assertEqual(sc["seed"], CHOSEN[plug.agent])
                man3, rows3 = self.rows(plug, sc, seed=sc["seed"])
                self.assertEqual(rows1, rows3)

    def test_another_seed_gives_other_rows(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                _, rows1 = self.rows(plug, sc)
                man2, rows2 = self.rows(plug, sc, seed=sc["seed"] + 1)
                self.assertEqual(man2["seed"], sc["seed"] + 1)
                self.assertNotEqual([r["at"] for r in rows1], [r["at"] for r in rows2])

    def test_every_row_is_labelled_simulated(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                _, rows = self.rows(plug, sc)
                self.assertTrue(rows)
                for r in rows:
                    self.assertIs(r["detail"].get(simulate.LABEL), True, r)
                    self.assertTrue(r["case_id"].startswith(f"sim-{sc['name']}-"), r["case_id"])
                    self.assertTrue(r["source"].startswith("sim-"), r["source"])

    def test_nothing_is_written_at_or_after_the_end(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                man, rows = self.rows(plug, sc)
                self.assertEqual(man["until"] - man["since"], sc["days"] * DAY)
                self.assertTrue(all(man["since"] <= r["at"] < man["until"] for r in rows))
                self.assertEqual([r["at"] for r in rows], sorted(r["at"] for r in rows))

    def test_the_manifest_matches_the_log(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                man, rows = self.rows(plug, sc)
                self.assertEqual((man["agent"], man["scenario"], man["rows"]), (plug.agent, sc["name"], len(rows)))
                by_case = {}
                for r in rows:
                    by_case.setdefault(r["case_id"], []).append(r)
                self.assertEqual(len(man["cases"]), sc["cases"])
                self.assertEqual(set(by_case), {c["id"] for c in man["cases"]})
                deciders = (plug.decides.good, *plug.decides.bad)
                groups = {g["name"]: g for g in sc.get("groups", [])}
                self.assertEqual(Counter(c["group"] for c in man["cases"] if c["group"]),
                                 Counter({g: groups[g]["cases"] for g in groups}))
                for c in man["cases"]:
                    rs = by_case[c["id"]]
                    steps = [r for r in rs if r["step"] is not None]
                    ends = [r for r in rs if r["result"] in deciders]
                    self.assertEqual(len(steps), len(sc["steps"]))
                    self.assertEqual(len(rs), len(steps) + len(ends))
                    self.assertTrue(all(r["step"] is None for r in ends))
                    self.assertEqual({r["source"] for r in rs}, {c["source"]})
                    self.assertEqual([r["result"] for r in ends], [c["deciding"]] if c["deciding"] else [])
                    self.assertEqual([r["cause"] for r in ends], [c["cause"]] if c["deciding"] else [])
                    marked = not ends and c["cause"] is not None  # no deciding row, so its last step carries it
                    self.assertEqual([r["cause"] for r in steps],
                                     [None] * (len(steps) - 1) + [c["cause"] if marked else None])
                    self.assertEqual(c["day"], int((steps[0]["at"] - man["since"]) // DAY))
                    self.assertEqual(c["weekday"], time.strftime("%a", time.gmtime(steps[0]["at"])).lower())
                    if not ends:  # no deciding row: pending, whatever its age (item 66)
                        self.assertEqual(c["status"], PENDING)
                    elif c["cause"]:
                        self.assertEqual(c["status"], LEFT_OUT)
                    else:
                        self.assertEqual(c["status"], GOOD if c["deciding"] == plug.decides.good else BAD)
                    over = {int(k): set(d) for k, d in groups[c["group"]]["detail"].items()} if c["group"] else {}
                    for name, t in sc["traits"].items():
                        detail = t["values"][c["traits"][name]].get("detail", {})
                        got, kept = steps[t["step"]]["detail"], over.get(t["step"], set())
                        self.assertTrue(any(all(got.get(k) == v for k, v in d.items() if k not in kept)
                                            for d in (detail if isinstance(detail, list) else [detail])),
                                        (c["id"], name, got))

    def test_fast_results_are_the_same_in_every_case_so_the_cause_shows_only_at_the_end(self):
        for plug, sc in BOTH:
            with self.subTest(agent=plug.agent):
                man, rows = self.rows(plug, sc)
                steps = [(s["action"], s["result"], s.get("stage"), k + 1) for k, s in enumerate(sc["steps"])]
                causes = {r["cause"] for r in sc["outside"]}
                hidden = {*causes, plug.decides.good, *plug.decides.bad}
                self.assertEqual(len(hidden), len(causes) + 1 + len(plug.decides.bad))
                for c in man["cases"]:
                    acts = [r for r in rows if r["case_id"] == c["id"] and r["step"] is not None]
                    self.assertEqual([(r["action"], r["result"], r["stage"], r["step"]) for r in acts], steps)
                    marked = c["deciding"] is None and c["cause"] is not None
                    self.assertEqual([r["cause"] for r in acts],
                                     [None] * (len(acts) - 1) + [c["cause"] if marked else None])
                    for r in acts:
                        self.assertFalse(hidden & set(json.dumps(r["detail"]).replace('"', " ").split()), r)
                self.assertTrue(any(r["cause"] for r in rows if r["step"] is None))

    def test_with_no_bad_result_declared_a_case_with_no_result_stays_pending(self):
        # the fan declares no bad result, so a case that ends not good gets no slow result at all
        fan = plugs.load(dict(plugs.FAN, decides={"good": "cooled", "bad": []}), self)
        sc = {"name": "fan", "agent": "fan", "seed": 7, "start": "2026-10-01", "days": 10, "cases": 60, "rate": 0.5,
              "steps": [{"action": "spin", "result": "spun", "stage": "grown", "hours": 1}]}
        db = Db(":memory:")
        self.addCleanup(db.close)
        man = simulate.simulate(db, fan, sc)
        st = Counter((c["status"], c["deciding"]) for c in man["cases"])
        self.assertTrue(st[(PENDING, None)] and st[(GOOD, "cooled")], st)
        self.assertEqual(set(st), {(PENDING, None), (GOOD, "cooled")})
        self.assertEqual({r["result"] for r in Log(db, fan).query() if r["action"] is None}, {"cooled"})
        proposer, tagger, _, _ = scripted.parts(sc)
        rep = Study(db, fan, proposer=proposer, tagger=tagger, lessons=Lessons(db, fan, judge=scripted.judge_says_low)
                    ).run(man["since"], man["until"], now=man["until"])
        self.assert_counts(man, rep)
        self.assertEqual(rep["decided"]["bad"], 0)

    def test_a_plant_knob_keeps_the_same_cases(self):
        sc = copy.deepcopy(MK_SCENARIO)
        sc["groups"][0]["sources"] = 4
        base, _ = self.rows(MARKETING, MK_SCENARIO)
        moved, _ = self.rows(MARKETING, sc)
        self.assertEqual(len(base["cases"]), len(moved["cases"]))
        for a, b in zip(base["cases"], moved["cases"]):
            self.assertEqual({k: v for k, v in a.items() if k != "source"},
                             {k: v for k, v in b.items() if k != "source"})
            if a["group"] != "spam":
                self.assertEqual(a["source"], b["source"])
        spam = [c for c in moved["cases"] if c["group"] == "spam"]
        self.assertEqual({c["source"] for c in spam}, {f"sim-marketing-account-spam-{n}" for n in (1, 2, 3, 4)})
        self.assertEqual({c["source"] for c in base["cases"] if c["group"] == "spam"},
                         {"sim-marketing-account-spam-1"})

    def test_a_scenario_is_refused_for_what_the_plug_did_not_declare(self):
        def step(k, **kw):
            return lambda sc: sc["steps"][k].update(kw)

        def drop(key):
            return lambda sc: sc.pop(key)

        cases = (
            ("undeclared action", SALES, SALES_SCENARIO, step(0, action="dance"), "declares no action 'dance'"),
            ("undeclared result", SALES, SALES_SCENARIO, step(0, result="danced"), "declares no result 'danced'"),
            ("a result that ends another action", SALES, SALES_SCENARIO, step(0, result="order_created"),
             "does not end the action"),
            ("a deciding result as a step", SALES, SALES_SCENARIO, step(2, result="order_created"),
             "decides a case, so the simulator writes it"),
            ("undeclared stage", SALES, SALES_SCENARIO, step(0, stage="dancing"), "declares no stage 'dancing'"),
            ("undeclared cause", SALES, SALES_SCENARIO, lambda sc: sc["outside"][0].update(cause="rain"),
             "declares no cause 'rain'"),
            ("a slow result as a step", MARKETING, MK_SCENARIO, step(0, result="sold"), "does not end the action"),
            ("group sources where the case names the source", SALES, SALES_SCENARIO,
             lambda sc: sc["groups"][0].update(sources=2), "one case is one source"),
            ("sources where the case names the source", SALES, SALES_SCENARIO,
             lambda sc: sc.update(sources={"pool": 5, "name": "person"}), "one case is one source"),
            ("no sources where each row names its source", MARKETING, MK_SCENARIO, drop("sources"),
             "marketing saves each action with its source"),
            ("another agent's scenario", MARKETING, SALES_SCENARIO, lambda sc: None,
             "is for 'sales', not 'marketing'"),
            ("an unknown key", SALES, SALES_SCENARIO, lambda sc: sc.update(colour="red"), "unknown key 'colour'"),
            ("an unknown key in a step", SALES, SALES_SCENARIO, step(1, colour="red"), "unknown key 'colour'"),
            ("a missing key", SALES, SALES_SCENARIO, drop("rate"), "missing 'rate'"),
            ("a value no trait has", SALES, SALES_SCENARIO,
             lambda sc: sc["rates"][0]["when"].update(size_check="maybe"), "has no value 'maybe'"),
            ("a when on no trait", SALES, SALES_SCENARIO, lambda sc: sc["rates"][0]["when"].update(colour="red"),
             "is not a trait, day or weekday"),
            ("a bad result where none is declared bad", SALES_NO_BAD, SALES_SCENARIO,
             lambda sc: sc.update(bad="delivered"), "sales declares no not good deciding results"),
            ("a bad result the sales plug did not declare bad", SALES, SALES_SCENARIO,
             lambda sc: sc.update(bad="delivered"), "is not one of sales's not good deciding results"),
            ("a bad result not declared bad", MARKETING, MK_SCENARIO, lambda sc: sc.update(bad="published"),
             "is not one of marketing's not good deciding results"),
            ("more group cases than cases", SALES, SALES_SCENARIO, lambda sc: sc.update(cases=10),
             "more cases than the scenario has"),
            ("a rate above 1", SALES, SALES_SCENARIO, lambda sc: sc.update(rate=1.5), "a chance from 0 to 1"),
            ("a stamp on no step", MARKETING, MK_SCENARIO, lambda sc: sc["stamp"]["weekday"].update(step=9),
             "a step number from 0 to 2"),
        )
        for what, plug, base, change, message in cases:
            with self.subTest(what):
                sc = copy.deepcopy(base)
                change(sc)
                db = Db(":memory:")
                self.addCleanup(db.close)
                log = Log(db, plug)
                with self.assertRaisesRegex(ValueError, message):
                    simulate.simulate(db, plug, sc)
                self.assertEqual(log.query(), [])
        for seed in (-1, True, 1.5):
            db = Db(":memory:")
            self.addCleanup(db.close)
            with self.subTest(seed=seed), self.assertRaisesRegex(ValueError, "seed"):
                simulate.simulate(db, SALES, SALES_SCENARIO, seed=seed)


class HowASalesChatEnds(Plants):
    """The Sales plug decides a chat by its order: order_created, saved on the order action with
    no stage, step or lessons, as how the chat ended and not a step a lesson can reach. Its not
    good result is chat_closed, but the scenario sets bad to null, so a simulated quiet chat has
    no deciding row and counts as not good once the order's window has passed. A quiet chat for
    a boot that ran out carries its cause on its last step, so it is pending for that day and
    left out after it."""

    def rows(self, **kw):
        db = Db(":memory:")
        self.addCleanup(db.close)
        man = simulate.simulate(db, SALES, SALES_SCENARIO, **kw)
        by_case = {}
        for r in Log(db, SALES).query():
            by_case.setdefault(r["case_id"], []).append(r)
        return man, by_case

    def test_an_order_is_saved_on_the_order_action_as_how_the_chat_ended(self):
        self.assertEqual((SALES.decides.good, tuple(SALES.decides.bad)), ("order_created", ("chat_closed",)))
        self.assertEqual(SALES_SCENARIO["bad"], "chat_closed")  # a quiet chat closes, a day after (item 66)
        self.assertEqual(SALES.results["order_created"].after, "order")
        man, by_case = self.rows()
        self.assertTrue([r for rs in by_case.values() for r in rs if r["result"] == "chat_closed"])
        boots = {c["id"]: c["traits"]["boots"] for c in man["cases"]}
        ends = [r for rs in by_case.values() for r in rs if r["result"] == "order_created"]
        self.assertEqual(len(ends), sum(c["deciding"] == "order_created" for c in man["cases"]))
        self.assertTrue(ends)
        self.assertEqual({(r["action"], r["stage"], r["step"], tuple(r["lessons"])) for r in ends},
                         {("order", None, None, ())})
        self.assertEqual({r["cause"] for r in ends}, {None, "out_of_stock"})
        for r in ends:
            self.assertEqual(r["cause"] == "out_of_stock", boots[r["case_id"]] == "sold_out", r["case_id"])

    def test_the_study_settles_each_chat_as_the_manifest_says_inside_the_window_and_after_it(self):
        window = study.read_days(SALES) * DAY
        self.assertEqual(window, DAY)
        man, by_case = self.rows()
        later, later_rows = self.rows(until=man["end"] + window)
        for m, rows in ((man, by_case), (later, later_rows)):
            for c in m["cases"]:
                self.assertEqual(study.settle(SALES, rows[c["id"]], m["until"])[0], c["status"], c["id"])
        self.assertTrue(Counter(c["status"] for c in man["cases"])[PENDING])
        self.assertFalse(Counter(c["status"] for c in later["cases"])[PENDING])
        was = {c["id"]: c["status"] for c in man["cases"] if c["status"] != PENDING}
        self.assertEqual({c["id"]: c["status"] for c in later["cases"] if c["id"] in was}, was)

    def test_a_quiet_chat_for_a_boot_that_ran_out_is_left_out_once_its_day_has_passed(self):
        man, by_case = self.rows()
        quiet = [c for c in man["cases"] if c["deciding"] in (None, "chat_closed") and c["cause"]]
        self.assertTrue([c for c in quiet if c["status"] == LEFT_OUT])
        for c in quiet:
            rows = by_case[c["id"]]
            self.assertEqual(c["traits"]["boots"], "sold_out")
            ends = [r for r in rows if r["step"] is None]  # the chat_closed row, a day after, carries the cause
            self.assertEqual([r["result"] for r in ends], ["chat_closed"] if c["deciding"] else [])
            if not ends:  # not closed yet: pending, never timed out (item 66)
                self.assertEqual(study.settle(SALES, rows, rows[-1]["at"] + 30 * DAY)[0], PENDING)
                continue
            self.assertEqual([r["cause"] for r in rows], [None] * (len(rows) - 1) + ["out_of_stock"])
            self.assertEqual(study.settle(SALES, rows[:-1], ends[0]["at"])[0], PENDING)
            self.assertEqual(study.settle(SALES, rows, ends[0]["at"] + 1)[0], LEFT_OUT)
        for c in man["cases"]:  # a quiet chat with no cause is not good once it closed
            if c["deciding"] == "chat_closed" and not c["cause"]:
                self.assertEqual(c["status"], BAD)


class SimHasNoBusinessWords(unittest.TestCase):
    """Like the engine, the simulator knows no agent: an agent's words live in its plug and its scenario."""

    def test_no_business_words_in_sim(self):
        files = sorted((ROOT / "sim").glob("*.py"))
        self.assertLessEqual({"__init__.py", "simulate.py", "scripted.py", "run.py"}, {f.name for f in files})
        words = quickcheck.EngineHasNoBusinessWords.WORDS
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                found = words.findall(line.replace("ORDER BY", ""))
                self.assertFalse(found, f"{f.name}:{n} {found}")


class SalesNight(Plants):
    """Seed 182: the size line is found, a chat for a boot that ran out is left out whether it
    ordered or went quiet, and the ring of chats that types a note for the bot is held by the
    copied words mark alone."""

    @classmethod
    def setUpClass(cls):
        nights, (cls.proposer, cls.tagger, cls.fit, cls.adapter), cls.read = night()
        cls.plug, cls.man, cls.rep = nights["sales"]

    def test_counts_match_the_manifest(self):
        self.assert_counts(self.man, self.rep)
        st = Counter(c["status"] for c in self.man["cases"])
        self.assertTrue(all(st[s] for s in (GOOD, BAD, PENDING, LEFT_OUT)), st)
        self.assertGreater(st[GOOD] + st[BAD], study.TAGGED)  # so the tagger reads a sample

    def test_the_real_pattern_is_a_lesson_on_trial(self):
        rec = self.cand(self.rep, SALES_REAL)
        self.assert_numbers(rec, self.man, PLANTS["sales"][0][1], self.read)
        self.assertEqual(rec["verdict"], study.LESSON)
        self.assertGreaterEqual(rec["chance"], study.CHANCE)
        card = self.has_card(self.rep, SALES_REAL)
        self.assertEqual((card["state"], card["risk"], card["from"]), (TRYING, risk.LOW, None))
        self.assertEqual((card["cases"]["with"], card["cases"]["good_with"]),
                         (rec["with"]["cases"], rec["with"]["good"]))

    def test_the_outside_cause_is_left_out_by_name(self):
        left = [c for c in self.man["cases"] if c["status"] == LEFT_OUT]
        self.assertTrue(left)
        self.assertTrue(all(c["traits"]["boots"] == "sold_out" and c["cause"] == "out_of_stock" for c in left))
        self.assertEqual({c["deciding"] for c in left}, {"chat_closed", "order_created"})  # went quiet, or ordered
        self.assertTrue(all(c["status"] in (LEFT_OUT, PENDING) for c in self.man["cases"]
                            if c["traits"]["boots"] == "sold_out"))
        self.assertEqual(self.rep["left_out"]["by_cause"], {"out_of_stock": len(left)})

    def test_the_tagger_never_saw_an_outside_case(self):
        mine = [call for call in self.tagger.calls if call["agent"] == "sales"]
        self.assertTrue(mine)
        seen = Counter(s.get("detail", {}).get("boots") for call in mine for v in call["cases"] for s in v["steps"])
        self.assertTrue(seen["Mercurial Vapor 17 Elite, size 42"])
        self.assertFalse([b for b in seen if b and "size 45" in b])

    def test_the_decoy_is_no_lesson(self):
        rec = self.cand(self.rep, SALES_DECOY)
        self.assert_numbers(rec, self.man, PLANTS["sales"][1][1], self.read)
        self.assertEqual((rec["verdict"], rec["with"]["cases"]), (study.FEW_CASES, 0))
        self.assertIsNone(self.card(self.rep, SALES_DECOY))

    def test_the_ring_is_held_by_the_copied_words_mark_alone(self):
        rec = self.cand(self.rep, SALES_BAD)
        self.assert_numbers(rec, self.man, PLANTS["sales"][2][1], self.read)
        self.assertEqual(rec["verdict"], study.LESSON)
        self.assertEqual(rec["with"]["sources"], rec["with"]["cases"])
        self.assert_only_copied(self.has_card(self.rep, SALES_BAD))
        self.assertEqual(risk.classify(SALES_BAD, self.plug.risk, scripted.judge_says_low),
                         (risk.LOW, ["judge: low"]))

    def test_the_null_candidate_ends_with_no_gap_and_no_card(self):
        self.assert_null_has_no_gap(self.man, self.rep, SALES_NULL, self.read)

    def test_one_case_is_one_source_so_the_sources_rule_never_binds_here(self):
        self.assertEqual(self.plug.source.known_by, plug_mod.CASE)
        self.assertGreater(study.MIN_CASES, study.MIN_SOURCES)
        for rec in self.rep["candidates"]:
            self.assertEqual((rec["with"]["sources"], rec["without"]["sources"]),
                             (rec["with"]["cases"], rec["without"]["cases"]))
            self.assertNotEqual(rec["verdict"], study.FEW_SOURCES)


class MarketingNight(Plants):
    """Seed 29: the price line is found and waits for a yes, the payment page down on day 6
    is left out, and spam from one account is refused by the sources rule; spread over 4
    accounts, it passes that rule and the copied words mark holds it."""

    @classmethod
    def setUpClass(cls):
        nights, (cls.proposer, cls.tagger, cls.fit, cls.adapter), cls.read = night()
        cls.plug, cls.man, cls.rep = nights["marketing"]

    def test_counts_match_the_manifest(self):
        self.assert_counts(self.man, self.rep)
        st = Counter(c["status"] for c in self.man["cases"])
        self.assertTrue(all(st[s] for s in (GOOD, BAD, PENDING, LEFT_OUT)), st)

    def test_the_real_pattern_is_found_and_waits_for_a_yes(self):
        rec = self.cand(self.rep, MK_REAL)
        self.assert_numbers(rec, self.man, PLANTS["marketing"][0][1], self.read)
        self.assertEqual(rec["verdict"], study.LESSON)
        card = self.has_card(self.rep, MK_REAL)
        self.assertEqual((card["state"], card["risk"]), (WAITING, risk.HIGH))
        self.assertIn("number: price", why_lines(card))
        self.assertFalse([x for x in why_lines(card) if x.startswith(COPIED)])

    def test_the_outside_cause_is_left_out_by_name(self):
        left = [c for c in self.man["cases"] if c["status"] == LEFT_OUT]
        self.assertTrue(left)
        self.assertTrue(all(c["day"] == 6 and c["weekday"] == "thu" and c["cause"] == "payment_down" for c in left))
        self.assertEqual(self.rep["left_out"]["by_cause"], {"payment_down": len(left)})

    def test_the_tagger_never_saw_a_thursday_case(self):
        thursdays = [c for c in self.man["cases"] if c["weekday"] == "thu"]
        self.assertTrue(thursdays)
        self.assertTrue(all(c["status"] in (LEFT_OUT, PENDING) for c in thursdays))
        mine = [call for call in self.tagger.calls if call["agent"] == "marketing"]
        self.assertTrue(mine)
        seen = Counter(s.get("detail", {}).get("weekday") for call in mine for v in call["cases"] for s in v["steps"])
        self.assertTrue(seen["fri"])
        self.assertEqual(seen["thu"], 0)

    def test_the_thursday_decoy_is_no_lesson(self):
        rec = self.cand(self.rep, MK_DECOY)
        self.assert_numbers(rec, self.man, PLANTS["marketing"][1][1], self.read)
        self.assertEqual((rec["verdict"], rec["with"]["cases"]), (study.FEW_CASES, 0))
        self.assertIsNone(self.card(self.rep, MK_DECOY))

    def test_the_null_candidate_ends_with_no_gap_and_no_card(self):
        self.assert_null_has_no_gap(self.man, self.rep, MK_NULL, self.read)

    def test_spam_from_one_account_is_refused_by_the_sources_rule(self):
        rec = self.cand(self.rep, MK_BAD)
        self.assert_numbers(rec, self.man, PLANTS["marketing"][2][1], self.read)
        self.assertEqual(rec["verdict"], study.FEW_SOURCES)
        self.assertEqual(rec["with"]["sources"], 1)
        # only the sources rule stands in its way: enough cases and a clear gap
        self.assertGreaterEqual(min(rec["with"]["cases"], rec["without"]["cases"]), study.MIN_CASES)
        self.assertGreaterEqual(rec["chance"], study.CHANCE)
        self.assertIsNone(self.card(self.rep, MK_BAD))

    def test_spam_over_four_accounts_passes_the_floor_and_the_copy_mark_holds_it(self):
        sc = copy.deepcopy(MK_SCENARIO)
        sc["groups"][0]["sources"] = 4
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "marketing.json"
            path.write_text(json.dumps(sc), encoding="utf-8")
            nights, _, read = night(pairs=(("marketing/plug.json", str(path)),))
        _, man, rep = nights["marketing"]
        rec = self.cand(rep, MK_BAD)
        self.assert_numbers(rec, man, PLANTS["marketing"][2][1], read)
        self.assertEqual(rec["with"]["sources"], 4)
        self.assertEqual(rec["with"]["cases"], self.cand(self.rep, MK_BAD)["with"]["cases"])
        self.assertEqual(rec["verdict"], study.LESSON)
        self.assert_only_copied(self.has_card(rep, MK_BAD))
        self.assertEqual(risk.classify(MK_BAD, MARKETING.risk, scripted.judge_says_low), (risk.LOW, ["judge: low"]))


class SeedsHold(Plants):
    """Over several seeds: the counts match the manifest, the real lines are found, and no
    decoy or bad line ever goes on trial."""

    SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 29, 182)

    @classmethod
    def setUpClass(cls):
        cls.nights = {}
        for seed in cls.SEEDS:
            nights, _, read = night(seed)
            cls.nights[seed] = (nights, read)

    def each(self):
        """(seed, agent, manifest, report, read) for every night; each test wraps its own subTest."""
        for seed, (nights, read) in self.nights.items():
            for agent, (plug, man, rep) in nights.items():
                yield seed, agent, man, rep, read

    def test_each_seed_reaches_every_scenario(self):
        for seed, agent, man, rep, read in self.each():
            with self.subTest(seed=seed, agent=agent):
                self.assertEqual(man["seed"], seed)

    def test_counts_match_the_manifest(self):
        for seed, agent, man, rep, read in self.each():
            with self.subTest(seed=seed, agent=agent):
                self.assert_counts(man, rep)

    def test_the_real_line_is_found(self):
        for seed, agent, man, rep, read in self.each():
            with self.subTest(seed=seed, agent=agent):
                line, has = PLANTS[agent][0]
                rec = self.cand(rep, line)
                self.assert_numbers(rec, man, has, read)
                self.assertEqual(rec["verdict"], study.LESSON)
                self.has_card(rep, line)

    def test_no_decoy_is_a_lesson(self):
        for seed, agent, man, rep, read in self.each():
            with self.subTest(seed=seed, agent=agent):
                line, has = PLANTS[agent][1]
                rec = self.cand(rep, line)
                self.assert_numbers(rec, man, has, read)
                self.assertNotEqual(rec["verdict"], study.LESSON)
                self.assertIsNone(self.card(rep, line))

    def test_no_bad_line_goes_on_trial(self):
        for seed, agent, man, rep, read in self.each():
            with self.subTest(seed=seed, agent=agent):
                line, has = PLANTS[agent][2]
                self.assert_numbers(self.cand(rep, line), man, has, read)
                on_trial = [c["change"] for c in rep["cards"] if c["state"] == TRYING]
                self.assertFalse(NEVER_ON_TRIAL & set(on_trial), on_trial)
                for c in rep["cards"]:
                    if c["change"] in NEVER_ON_TRIAL:
                        self.assert_only_copied(c)

    def test_spam_never_passes_the_sources_rule(self):
        for seed, agent, man, rep, read in self.each():
            if agent == "marketing":
                with self.subTest(seed=seed):
                    rec = self.cand(rep, MK_BAD)
                    self.assertIn(rec["verdict"], (study.FEW_SOURCES, study.FEW_CASES))
                    self.assertEqual(rec["with"]["sources"], 1 if rec["with"]["cases"] else 0)


class SpyLessons(Lessons):
    """Lessons that remember what was proposed and what was adapted."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.proposed, self.adapted = [], []

    def propose(self, text, stages, **kw):
        lid = super().propose(text, stages, **kw)
        self.proposed.append(dict(kw, text=text, id=lid))
        return lid

    def adapt(self, text, stages, **kw):
        lid = super().adapt(text, stages, **kw)
        self.adapted.append(dict(kw, text=text, id=lid))
        return lid


class SpyJudge:
    """A judge that says low and remembers the risk lines it was given."""

    def __init__(self):
        self.seen = []

    def __call__(self, text, high_about, low_about):
        self.seen.append((text, high_about, low_about))
        return risk.LOW


class CrossAgent(Plants):
    """Marketing's night with the Sales agent given: the fit check is asked about the Sales
    agent's lines, what fits is written through Lessons.adapt, and the risk is marketing's own:
    a line low under the Sales agent's list waits for a yes in marketing. A buyer's area is
    personal data on a public page."""

    @classmethod
    def setUpClass(cls):
        cls.db = Db(":memory:")
        mans = {p.agent: simulate.simulate(cls.db, p, sc) for p, sc in BOTH}
        since = min(m["since"] for m in mans.values())
        until = max(m["until"] for m in mans.values())
        cls.sales_man = mans["sales"]
        cls.proposer, cls.tagger, cls.fit, cls.adapter = scripted.parts(SALES_SCENARIO, MK_SCENARIO)
        cls.judge = SpyJudge()
        cls.lessons = SpyLessons(cls.db, MARKETING, judge=cls.judge)
        with tagged() as cls.read:
            cls.rep = Study(cls.db, MARKETING, proposer=cls.proposer, tagger=cls.tagger, fit=cls.fit,
                            adapter=cls.adapter, others=[SALES], lessons=cls.lessons).run(since, until, now=until)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_the_fit_check_is_asked_about_the_sales_lines(self):
        asked = {(c["agent"], c["other"], c["candidate"]["lesson"]) for c in self.fit.calls}
        self.assertEqual(asked, {("marketing", "sales", SALES_REAL), ("marketing", "sales", SALES_BAD)})
        across = self.rep["across"]
        self.assertEqual([a["agent"] for a in across], ["sales"])
        self.assertEqual({r["lesson"]: r["fit"] for r in across[0]["candidates"]},
                         {SALES_REAL: "partly", SALES_DECOY: None, SALES_BAD: "partly", SALES_NULL_LINE: None})

    def test_what_fits_is_written_through_lessons_adapt(self):
        self.assertEqual({a["text"] for a in self.lessons.adapted}, {MK_FROM_SALES_REAL, MK_FROM_SALES_BAD})
        self.assertEqual({p["text"] for p in self.lessons.proposed}, {MK_REAL})
        for a in self.lessons.adapted:
            les = self.lessons.get(a["id"])
            self.assertEqual(les["agent"], "marketing")
            self.assertTrue(les["source"].startswith("adapted partly from sales cases sim-sales-"),
                            les["source"])
            self.assertIn("ended order_created", les["source"])
        card = self.has_card(self.rep, MK_FROM_SALES_REAL)
        self.assertEqual((card["from"]["agent"], card["from"]["fit"]), ("sales", "partly"))
        rec = self.cand(self.rep["across"][0], SALES_REAL)
        want = self.assert_numbers(rec, self.sales_man, PLANTS["sales"][0][1], self.read)
        self.assertEqual(set(card["from"]["cases"]), want["ids"])

    def test_a_line_low_at_the_sales_waits_for_a_yes_in_marketing(self):
        card = self.has_card(self.rep, MK_FROM_SALES_REAL)
        self.assertEqual((card["state"], card["risk"]), (WAITING, risk.HIGH))
        self.assertIn("personal_data: area", why_lines(card))
        self.assertFalse([x for x in why_lines(card) if x.startswith(COPIED)])
        level, why = risk.classify(MK_FROM_SALES_REAL, MARKETING.risk, scripted.judge_says_low)
        self.assertEqual(level, risk.HIGH)
        self.assertIn("personal_data: area", why)
        self.assertEqual(risk.classify(MK_FROM_SALES_REAL, SALES.risk, scripted.judge_says_low),
                         (risk.LOW, ["judge: low"]))

    def test_the_adapted_ring_line_is_held_as_copied(self):
        self.assert_only_copied(self.has_card(self.rep, MK_FROM_SALES_BAD))
        self.assertEqual(risk.classify(MK_FROM_SALES_BAD, MARKETING.risk, scripted.judge_says_low),
                         (risk.LOW, ["judge: low"]))


class JudgeAcross(Plants):
    """A kept Sales agent lesson adapted into marketing reaches the judge with marketing's own
    risk lines, never the Sales agent's."""

    KEPT = "Thank each buyer once the size is chosen."
    ADAPTED = "Thank the people who comment on each post."

    @classmethod
    def setUpClass(cls):
        cls.db = Db(":memory:")
        mans = [simulate.simulate(cls.db, p, sc) for p, sc in BOTH]
        since = min(m["since"] for m in mans)
        until = max(m["until"] for m in mans)
        kept_lesson(Lessons(cls.db, SALES, judge=scripted.judge_says_low), cls.KEPT, ["asking"], yes_by="team",
                    now=since)
        mk = copy.deepcopy(MK_SCENARIO)
        mk["script"]["adapt"][cls.KEPT] = {"fit": "partly", "lesson": cls.ADAPTED,
                                           "situation": "Answering comments.", "stages": ["drafting"]}
        proposer, tagger, fit, adapter = scripted.parts(SALES_SCENARIO, mk)
        cls.judge = SpyJudge()
        cls.lessons = SpyLessons(cls.db, MARKETING, judge=cls.judge)
        cls.rep = Study(cls.db, MARKETING, proposer=proposer, tagger=tagger, fit=fit, adapter=adapter,
                        others=[SALES], lessons=cls.lessons).run(since, until, now=until)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_the_kept_lesson_is_adapted(self):
        self.assertIn(self.ADAPTED, {a["text"] for a in self.lessons.adapted})
        self.has_card(self.rep, self.ADAPTED)

    def test_the_judge_reads_marketings_own_risk_lines(self):
        self.assertIn((self.ADAPTED, MARKETING.risk.high_about, MARKETING.risk.low_about), self.judge.seen)
        self.assertTrue(all(h == MARKETING.risk.high_about for _, h, _ in self.judge.seen))
        self.assertNotEqual(SALES.risk.high_about, MARKETING.risk.high_about)


class Runner(unittest.TestCase):
    """sim/run.py prints each agent's night: found, ignored, refused and not proven. An adapted
    card's numbers carry the source agent's own result word and name where they were counted."""

    def main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = run.main(list(argv))
        self.assertEqual(code, 0)
        return buf.getvalue()

    def blocks(self, out):
        head, _, rest = out.partition("\n\n")
        self.assertIn("every case below is made up", head)
        self.assertIn(SCRIPTED, head)
        return {b.split(":", 1)[0]: b.splitlines() for b in rest.strip().split("\n\n")}

    def test_text_names_an_adapted_cards_numbers_with_their_agent(self):
        cases = {"with": 81, "without": 95, "total": 176, "good_with": 42, "good_without": 83}
        s = {"agent": "marketing", "read": 100, "seed": 29, "window": {"since": 0, "until": DAY}, "good": "sold",
             "settled": {"good": 3, "bad": 2}, "pending": 1, "ignored": {"cases": 0, "by_cause": {}},
             "held": [], "refused": [], "sources_note": None, "not_proven": [],
             "found": [{"lesson": "Own line.", "pattern": "Own pattern.", "helps": True,
                        "state": TRYING, "risk": "low", "why": "judge: low", "sure": 0.9,
                        "cases": dict(cases, good_with=21), "counted": {"agent": "marketing", "good": "sold"},
                        "from": None},
                       {"lesson": "Borrowed line.", "pattern": "Their pattern.", "helps": False,
                        "state": TRYING, "risk": "low", "why": "judge: low",
                        "sure": 0.9999999,
                        "cases": cases, "counted": {"agent": "sales", "good": "order_created"},
                        "from": {"agent": "sales", "cases": [], "fit": "partly"}}]}
        lines = run.text(s).splitlines()
        own = lines[lines.index('    - "Own line.": on trial') + 1]
        borrowed = lines[lines.index('    - "Borrowed line." (adapted from sales): on trial') + 1]
        self.assertEqual(own.strip(), 'pattern "Own pattern." helps: with it 21 of 81 sold, without it 83 of 95; '
                                      'chance it helps 90%')
        self.assertEqual(borrowed.strip(), 'from sales\'s cases: pattern "Their pattern." hurts: with it 42 of 81 '
                                           'order_created, without it 83 of 95; chance it hurts over 99%')
        self.assertEqual([run._pct(x) for x in (1.0, 0.996, 0.994, 0.9, 0.0)],
                         ["over 99%", "over 99%", "99%", "90%", "0%"])

    def test_the_printed_night(self):
        data = {s["agent"]: s for s in json.loads(self.main("--json"))}
        blocks = self.blocks(self.main())
        self.assertEqual(set(blocks), {"sales", "marketing"})
        for agent, s in data.items():
            lines = blocks[agent]
            self.assertTrue(s["simulated"])
            self.assertIn(f'settled {s["settled"]["good"] + s["settled"]["bad"]} ({s["settled"]["good"]} '
                          f'{s["good"]}, {s["settled"]["bad"]} not), pending {s["pending"]}', lines[1])
            for f in s["found"]:
                if not f["cases"]:
                    continue
                ats = [n for n, x in enumerate(lines) if x.startswith(f'    - "{f["lesson"]}"')]
                self.assertEqual(len(ats), 1, f["lesson"])
                at, c, word = ats[0], f["cases"], f["counted"]["good"]
                way = "helps" if f["helps"] else "hurts"
                self.assertIn(f'pattern "{f["pattern"]}" {way}: with it {c["good_with"]} of {c["with"]} {word}, '
                              f'without it {c["good_without"]} of {c["without"]}; chance it {way} ', lines[at + 1])
                if f["from"]:
                    self.assertEqual(f["counted"]["agent"], f["from"]["agent"])
                    self.assertNotEqual(word, s["good"])
                    self.assertTrue(lines[at + 1].strip().startswith(f'from {f["from"]["agent"]}\'s cases: '))
                    self.assertNotIn(f'{c["good_with"]} of {c["with"]} {s["good"]}', lines[at + 1])
        adapted = [f for f in data["marketing"]["found"] if f["from"]]
        self.assertEqual([(f["lesson"], f["counted"]) for f in adapted],
                         [(MK_FROM_SALES_REAL, {"agent": "sales", "good": "order_created"})])

    def test_the_sales_says_what_holds_a_ring_of_cases(self):
        data = {s["agent"]: s for s in json.loads(self.main("--json"))}
        note = data["sales"]["sources_note"]
        self.assertIn("copied words mark", note)
        self.assertIn(f"{study.MIN_SOURCES} sources rule", note)
        self.assertTrue(note.endswith("that rule is shown on marketing."), note)
        self.assertIsNone(data["marketing"]["sources_note"])
        lines = self.blocks(self.main())["sales"]
        held = [n for n, x in enumerate(lines) if x.startswith("  held for a yes ")]
        self.assertEqual(len(held), 1, lines)
        held = held[0]
        listed = int(lines[held].split()[-1])
        self.assertEqual(lines[held + listed + 1], f"    {note}")
        self.assertTrue(lines[held + listed + 2].startswith("  refused "), lines)
        self.assertFalse(any(note in x for x in self.blocks(self.main())["marketing"]))

    def test_found_ignored_held_and_refused(self):
        data = {s["agent"]: s for s in json.loads(self.main("--json"))}
        sales, mk = data["sales"], data["marketing"]
        self.assertEqual([f["lesson"] for f in sales["found"]], [SALES_REAL])
        self.assertEqual({h["lesson"]: h["held"] for h in sales["held"]},
                         {SALES_BAD: "it copies words from the cases it came from"})
        self.assertEqual(sales["refused"], [])
        self.assertEqual([f["lesson"] for f in mk["found"]], [MK_REAL, MK_FROM_SALES_REAL])
        self.assertEqual({h["lesson"]: h["held"] for h in mk["held"]},
                         {MK_FROM_SALES_BAD: "it copies words from the cases it came from"})
        self.assertEqual({r["lesson"]: r["refused"] for r in mk["refused"]},
                         {MK_BAD: f"only 1 different source(s) behind one side; {study.MIN_SOURCES} are needed"})
        self.assertEqual(set(sales["ignored"]["by_cause"]), {"out_of_stock"})
        self.assertEqual(set(mk["ignored"]["by_cause"]), {"payment_down"})
        self.assertEqual({n["why"] for n in sales["not_proven"] + mk["not_proven"]}, {study.FEW_CASES, study.NO_GAP})
        blocks = self.blocks(self.main())
        self.assertIn("  held for a yes 1", blocks["sales"])
        self.assertIn("  refused 0", blocks["sales"])
        self.assertIn("  refused 1", blocks["marketing"])

    def test_not_proven_lines_carry_their_counts(self):
        data = {s["agent"]: s for s in json.loads(self.main("--json"))}
        blocks = self.blocks(self.main())
        seen = set()
        for agent, s in data.items():
            for n in s["not_proven"]:
                w, wo = n["with"], n["without"]
                head = (f'    - "{n["pattern"]}": {n["why"]}; with the pattern {w["good"]} of {w["cases"]} '
                        f'{s["good"]}, without it {wo["good"]} of {wo["cases"]}')
                ats = [x for x in blocks[agent] if x.startswith(head)]
                self.assertEqual(len(ats), 1, (head, blocks[agent]))
                left = f'; the {s["ignored"]["cases"]} cases left out for a cause outside the agent are not counted'
                if n["why"] == study.FEW_CASES:
                    self.assertGreater(s["ignored"]["cases"], 0)
                    self.assertEqual(ats[0], head + left)
                else:
                    self.assertEqual(ats[0], head)
                seen.add(n["why"])
        self.assertEqual(seen, {study.FEW_CASES, study.NO_GAP})

    def test_the_run_takes_no_database(self):
        db = Db(":memory:")
        try:
            with self.assertRaises(TypeError):
                run.night(db=db)
        finally:
            db.close()

    def test_every_scenario_file_is_run_with_the_plug_its_agent_names(self):
        self.assertEqual(run.AGENTS, (("marketing/plug.json", "sim/scenarios/marketing.json"),
                                      ("sales/plug.json", "sim/scenarios/sales.json")))
        for _, path in run.AGENTS:
            self.assertEqual(json.loads((ROOT / path).read_text(encoding="utf-8"))["script"]["about"],
                             SCRIPTED.replace("Candidates are scripted", "Candidates scripted"))

    def test_the_seed_flag_reaches_every_scenario(self):
        data = json.loads(self.main("--json", "--seed", "3"))
        self.assertEqual([(s["agent"], s["seed"]) for s in data], [("marketing", 3), ("sales", 3)])
        self.assertNotEqual(data, json.loads(self.main("--json")))

    def test_the_script_runs_isolated_from_any_folder(self):
        with tempfile.TemporaryDirectory() as d:
            got = subprocess.run([sys.executable, "-I", str(ROOT / "sim" / "run.py")], cwd=d, capture_output=True,
                                 text=True, timeout=60)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, self.main())


if __name__ == "__main__":
    unittest.main()
