"""Task t261029w: Bring back (calls 3A and 17A). A person brings a pulled lesson back as a new
lesson with the same text and stages, linked to the pulled one, signed with their yes, on
trial or waiting its turn; the pulled one stays pulled and unchanged. The morning page has
Bring back on its Pulled list and shows the link both ways. The rollback offers Bring back for
the lessons pulled since that night, does it only with --bring-back, inside the plan code and
the same transaction as the pulls, and lists a line that is back already. Made-up plugs and
temporary databases only."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from engine import lessons as lessons_mod
from engine import risk
from engine.lessons import KEPT, PULLED, TRYING, WAITING, Lessons
from kit.db import Db
from reflection import morning as mod
from reflection import night as night_mod
from reflection import snapshots as snap_mod
from tests import plugs
from tests.kept import kept_lesson
from tests import study_fakes as fk
from tests import test_morning as tm
from tests import test_snapshots as ts

DAY = 86400.0
T = 1_800_000_000.0
OWNER = "the owner"


def always_low(text, high_about, low_about):
    return risk.LOW


def raw(db, lesson_id):
    with db.tx() as c:
        return dict(c.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone())


def counts(db):
    with db.tx() as c:
        return tuple(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("lessons", "lesson_returns", "trials"))


class EngineBase(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.plug = plugs.load(plugs.WATERER, self)
        self.L = Lessons(self.db, self.plug, judge=always_low)

    def pulled(self, text="Water the grown beds at dusk.", stages=("grown",)):
        lid = self.L.add(text, list(stages), yes_by="tester", now=T)
        self.assertTrue(self.L.pull(lid, "stopped by the owner: too slow", now=T + 60))
        return lid


class Engine(EngineBase):
    def test_a_pulled_lesson_comes_back_as_a_new_lesson_on_trial_linked_to_it(self):
        a = self.pulled()
        before = raw(self.db, a)
        n = self.L.bring_back(a, "  Mohamed ", now=T + 120)
        new = self.L.get(n)
        self.assertEqual((new["text"], new["stages"], new["state"], new["share"], new["ends_at"]),
                         ("Water the grown beds at dusk.", ["grown"], TRYING, 0.5, T + 120 + 7 * DAY))
        self.assertEqual((new["yes_by"], new["yes_at"], new["source"], new["source_lesson_id"], new["risk"], new["score"]),
                         ("Mohamed", T + 120, f"brought back by Mohamed from lesson {a}", None, risk.LOW, 0.0))
        self.assertEqual({k: self.L.trial(n)[k] for k in ("share", "days", "started_at", "queued_at")},
                         {"share": 0.5, "days": 7.0, "started_at": T + 120, "queued_at": None})
        self.assertEqual(raw(self.db, a), before)  # the pulled one stays pulled and unchanged
        self.assertEqual(self.L.back_links(a), {"from": None, "as": [n]})
        self.assertEqual(self.L.back_links(n), {"from": a, "as": []})
        self.assertEqual([les["id"] for les in self.L.live(now=T + 200)], [n])

    def test_it_waits_its_turn_when_its_stage_has_a_trial_and_needs_no_other_yes(self):
        busy = self.L.propose("Visit the north bed first.", ["seedling"], sources=[], now=T)
        self.assertEqual(self.L.get(busy)["state"], TRYING)
        p = self.pulled("Leave the seedling beds for the end of the round.", ("seedling",))
        n = self.L.bring_back(p, OWNER, now=T + 120)
        new = self.L.get(n)
        self.assertEqual((new["state"], new["yes_by"]), (WAITING, OWNER))
        self.assertEqual(self.L.waits_for(n, T + 120), [busy])
        with self.assertRaisesRegex(ValueError, rf"lesson {p} is back already as lesson {n} \(waiting its turn\)"):
            self.L.bring_back(p, OWNER, now=T + 130)
        self.assertTrue(self.L.pull(busy, "no", now=T + 200))
        self.assertEqual(self.L.start_turns(T + 300), [n])
        self.assertEqual(self.L.get(n)["state"], TRYING)

    def test_a_high_risk_line_goes_on_trial_with_the_persons_yes(self):
        h = self.L.propose("Water bed 3 twice.", ["grown"], sources=[], now=T)
        self.assertEqual(self.L.get(h)["state"], WAITING)
        self.assertTrue(self.L.pull(h, "no from the owner", now=T + 60))
        n = self.L.bring_back(h, OWNER, now=T + 120)
        self.assertEqual((self.L.get(n)["state"], self.L.get(n)["risk"]), (TRYING, risk.HIGH))

    def test_todays_risk_list_can_make_the_line_high(self):
        a = self.pulled("Water the beds with the hose.")
        self.assertEqual(self.L.get(a)["risk"], risk.LOW)
        data = plugs.changed(plugs.WATERER)
        data["risk"]["high"]["words"]["tools"] = ["hose"]
        n = Lessons(self.db, plugs.load(data, self), judge=always_low).bring_back(a, OWNER, now=T + 120)
        new = self.L.get(n)
        self.assertEqual(new["risk"], risk.HIGH)
        self.assertIn("hose", new["risk_why"])

    def test_refusals_change_nothing(self):
        kept = self.L.add("Visit the grown beds last.", ["grown"], yes_by="tester", now=T)
        trying = self.L.propose("Visit the north bed first.", ["seedling"], sources=[], now=T)
        waiting = self.L.propose("Water bed 3 twice.", ["grown"], sources=[], now=T)
        fans = Lessons(self.db, plugs.load(plugs.FAN, self), judge=always_low)
        theirs = fans.add("Spin the fan at dawn.", ["grown"], yes_by="tester", now=T)
        self.assertTrue(fans.pull(theirs, "no", now=T + 1))
        a = self.pulled()
        before = counts(self.db)
        for lid, words in ((kept, "is not pulled"), (trying, "is not pulled"), (waiting, "is not pulled"),
                           (999, "no lesson 999 of waterer"), (theirs, f"no lesson {theirs} of waterer")):
            with self.subTest(lesson=lid), self.assertRaisesRegex(ValueError, words):
                self.L.bring_back(lid, OWNER, now=T + 120)
        for by in ("", "   ", "two\nlines", None):
            with self.subTest(by=by), self.assertRaisesRegex(ValueError, "by: one line"):
                self.L.bring_back(a, by, now=T + 120)
        self.assertEqual(counts(self.db), before)
        self.assertEqual(fans.get(theirs)["state"], PULLED)

    def test_a_line_back_already_is_refused_naming_its_copy_across_the_whole_family(self):
        a = self.pulled()
        n = self.L.bring_back(a, OWNER, now=T + 120)
        with self.assertRaisesRegex(ValueError, rf"lesson {a} is back already as lesson {n} \(on trial\)"):
            self.L.bring_back(a, OWNER, now=T + 130)
        self.assertTrue(self.L.keep(n))
        with self.assertRaisesRegex(ValueError, rf"lesson {a} is back already as lesson {n} \(kept\)"):
            self.L.bring_back(a, OWNER, now=T + 140)
        self.assertTrue(self.L.pull(n, "stopped", now=T + 150))
        n2 = self.L.bring_back(a, OWNER, now=T + 160)  # every copy pulled: it may come back again
        before = counts(self.db)
        with self.assertRaisesRegex(ValueError, rf"lesson {n} is back already as lesson {n2}"):
            self.L.bring_back(n, OWNER, now=T + 170)  # a sibling copy is live
        self.assertTrue(self.L.pull(n2, "stopped", now=T + 180))
        n3 = self.L.bring_back(n, OWNER, now=T + 190)
        with self.assertRaisesRegex(ValueError, rf"lesson {a} is back already as lesson {n3}"):
            self.L.bring_back(a, OWNER, now=T + 200)  # a copy of a copy is live
        self.assertEqual(counts(self.db)[1], before[1] + 1)
        self.assertEqual(self.L.back_links(a), {"from": None, "as": [n, n2]})
        self.assertEqual(self.L.back_links(n), {"from": a, "as": [n3]})

    def test_a_stage_the_plug_no_longer_declares_is_refused(self):
        a = self.pulled()
        before = counts(self.db)
        other = Lessons(self.db, plugs.load(plugs.changed(plugs.WATERER, stages=["seedling"]), self), judge=always_low)
        with self.assertRaisesRegex(ValueError, "declares no stage 'grown'"):
            other.bring_back(a, OWNER, now=T + 120)
        self.assertEqual(counts(self.db), before)

    def test_the_family_helpers(self):
        links = {2: 1, 3: 1, 4: 3, 9: 8}
        self.assertEqual(lessons_mod.back_family(links, 1), {1, 2, 3, 4})
        self.assertEqual(lessons_mod.back_family(links, 4), {1, 2, 3, 4})
        self.assertEqual(lessons_mod.back_family(links, 5), {5})
        states = {1: PULLED, 2: PULLED, 3: PULLED, 4: KEPT, 8: PULLED, 9: PULLED}
        self.assertEqual(lessons_mod.back_copy(links, states, 2), 4)
        self.assertIsNone(lessons_mod.back_copy(links, states, 4))  # itself is not its own copy
        self.assertIsNone(lessons_mod.back_copy(links, states, 8))


class Database(EngineBase):
    """The link table's own guards, met by writes that skip the engine."""

    def link(self, new, old):
        with self.db.tx() as c:
            c.execute("INSERT INTO lesson_returns (lesson_id, from_id, agent, by, at) VALUES (?, ?, 'waterer', 'x', 0)",
                      (new, old))

    def fresh(self, text):
        with self.db.tx() as c:
            return c.execute("INSERT INTO lessons (agent, text, stages, fields, risk, state, added_at) VALUES "
                             "('waterer', ?, ',grown,', ',gardening,', 'low', 'waiting', 0)", (text,)).lastrowid

    def test_a_link_comes_only_from_a_pulled_lesson_to_a_new_one_with_its_text(self):
        a = self.pulled()
        live = self.L.add("Visit the grown beds last.", ["grown"], yes_by="tester", now=T)
        for new, old in ((self.fresh("Visit the grown beds last."), live),  # from a lesson not pulled
                         (live, a),                                         # to a lesson that is not new
                         (self.fresh("Another line."), a)):                 # to a line with another text
            with self.subTest(new=new, old=old), self.assertRaisesRegex(sqlite3.IntegrityError, "comes back as a new"):
                self.link(new, old)

    def test_a_link_to_an_old_waiting_line_without_a_yes_is_refused(self):
        """Review t261029w r1 finding 1: only a new lesson, signed and with no trial yet, can be the copy."""
        a = self.pulled()
        signed = self.fresh("Water the grown beds at dusk.")
        with self.db.tx() as c:
            c.execute("UPDATE lessons SET yes_by = 'x', yes_at = 1 WHERE id = ?", (signed,))
            c.execute("INSERT INTO trials (lesson_id, agent, share, days, queued_at) VALUES (?, 'waterer', 0.5, 7, 1)",
                      (signed,))
        for new in (self.fresh("Water the grown beds at dusk."), signed):
            with self.subTest(new=new), self.assertRaisesRegex(sqlite3.IntegrityError, "comes back as a new"):
                self.link(new, a)
        self.assertEqual(self.L.back_links(a), {"from": None, "as": []})

    def test_a_second_link_while_a_copy_is_not_pulled_is_refused(self):
        a = self.pulled()
        self.L.bring_back(a, OWNER, now=T + 120)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "comes back as a new"):
            self.link(self.fresh("Water the grown beds at dusk."), a)

    def test_a_link_is_never_changed_deleted_or_replaced(self):
        a = self.pulled()
        n = self.L.bring_back(a, OWNER, now=T + 120)
        for sql, words in (("UPDATE lesson_returns SET by = 'y'", "never changed"),
                           ("DELETE FROM lesson_returns", "never deleted"),
                           (f"INSERT OR REPLACE INTO lesson_returns VALUES ({n}, {a}, 'waterer', 'y', 1)", "never replaced")):
            with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.DatabaseError, words), self.db.tx() as c:
                c.execute(sql)
        self.assertEqual(self.L.back_links(a), {"from": None, "as": [n]})


class OneWriter(unittest.TestCase):
    def test_bring_back_reads_the_family_under_the_write_lock(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = Path(d.name) / "agent.db"
        db = Db(path)
        self.addCleanup(db.close)
        L = Lessons(db, plugs.load(plugs.WATERER, self), judge=always_low)
        a = L.add("Water the grown beds at dusk.", ["grown"], yes_by="tester", now=T)
        L.pull(a, "no", now=T + 1)
        seen, real = [], lessons_mod.returns_in

        def spy(c, agent):
            other = sqlite3.connect(path, timeout=0)
            try:
                other.execute("BEGIN IMMEDIATE")
                other.rollback()
                seen.append(False)
            except sqlite3.OperationalError:
                seen.append(True)
            finally:
                other.close()
            return real(c, agent)
        with mock.patch.object(lessons_mod, "returns_in", spy):
            L.bring_back(a, OWNER, now=T + 2)
        self.assertEqual(seen, [True])


class Page(tm.Base):
    def setUp(self):
        super().setUp()
        self.live = self.lessons.add("Water the grown beds deeply.", ["grown"], yes_by="tester", now=tm.NOW)

    @staticmethod
    def item(page, lid):
        start = page.index(f'<li class="item" id="l{lid}">')
        return page[start:page.index("</li>", start)]

    def test_the_pulled_list_has_bring_back_and_the_link_shows_both_ways(self):
        self.morning.stop(self.live, "It drowned the roots.", now=tm.NOW + 1)
        page = mod.render(self.morning.view(tm.NOW + 2), token="tok")
        form = (f'<form method="post" action="/back"><input type="hidden" name="token" value="tok">'
                f'<input type="hidden" name="lesson" value="{self.live}"><button type="submit">Bring back</button></form>')
        self.assertIn(form, self.item(page, self.live))
        self.assertNotIn('action="/back"', mod.render(self.morning.view(tm.NOW + 2), token=None))
        said = self.morning.bring_back(str(self.live), now=tm.NOW + 3)
        n = self.lessons.back_links(self.live)["as"][0]
        self.assertEqual(said, f"Lesson {self.live} is back as lesson {n}; lesson {self.live} stays pulled. It is on trial.")
        self.assertEqual((self.lessons.get(n)["state"], self.lessons.get(n)["yes_by"]), (TRYING, mod.BY))
        self.assertEqual(self.lessons.get(self.live)["state"], PULLED)
        page = mod.render(self.morning.view(tm.NOW + 4), token="tok")
        old = self.item(page, self.live)
        self.assertNotIn('action="/back"', old)
        self.assertIn(f'<a href="#l{n}">brought back as lesson {n}</a>', old)
        self.assertIn(f'Its line is back already as lesson <a href="#l{n}">{n}</a>.', old)
        self.assertIn(f'<a href="#l{self.live}">brought back from lesson {self.live}</a>', self.item(page, n))

    def test_it_says_when_the_line_waits_its_turn(self):
        p = kept_lesson(self.lessons, "Leave the seedling beds for the end of the round.", ["seedling"], yes_by="t",
                        now=tm.NOW)
        self.lessons.propose("Visit the north bed first.", ["seedling"], sources=[], now=tm.NOW)
        self.morning.stop(p, "Too slow.", now=tm.NOW + 1)
        self.assertTrue(self.morning.bring_back(p, now=tm.NOW + 2).endswith(" It waits its turn."))

    def test_the_page_refuses_what_the_engine_refuses_and_changes_nothing(self):
        with self.assertRaisesRegex(mod.Refused, f"Lesson {self.live} is not pulled, so there is nothing to bring back"):
            self.morning.bring_back(self.live, now=tm.NOW + 1)
        with self.assertRaisesRegex(mod.Refused, "No lesson 999"):
            self.morning.bring_back(999, now=tm.NOW + 1)
        self.morning.stop(self.live, "It drowned the roots.", now=tm.NOW + 1)
        self.morning.bring_back(self.live, now=tm.NOW + 2)
        before = counts(self.db)
        with self.assertRaisesRegex(mod.Refused, rf"Lesson {self.live} was not brought back: lesson {self.live} is "
                                                 rf"back already as lesson \d+ \(on trial\)\."):
            self.morning.bring_back(self.live, now=tm.NOW + 3)
        self.assertEqual(counts(self.db), before)

    def test_an_agent_with_no_plug_has_no_bring_back(self):
        f = self.fans.add("Spin the fan at dawn.", ["grown"], yes_by="tester", now=tm.NOW)
        self.fans.pull(f, "no", now=tm.NOW + 1)
        page = mod.render(mod.Morning(self.db, [self.plug], reports=self.dir).view(tm.NOW + 2), token="tok")
        self.assertNotIn('action="/back"', page)
        with self.assertRaisesRegex(mod.Refused, "No plug for fan"):
            mod.Morning(self.db, [self.plug], reports=self.dir).bring_back(f, now=tm.NOW + 2)


class Server(tm.Base):
    call = tm.Server.call

    def setUp(self):
        super().setUp()
        self.gone = self.lessons.add("Water the grown beds deeply.", ["grown"], yes_by="tester", now=tm.NOW)
        self.lessons.pull(self.gone, "stopped by the owner: too slow", now=tm.NOW + 1)
        self.server = mod.make_server(self.morning, port=0)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(5)
        self.addCleanup(stop)
        self.here = f"127.0.0.1:{self.port}"

    def test_bring_back_from_the_page_needs_its_token_and_works_with_it(self):
        status, page, _ = self.call("GET", "/", origin=None)
        self.assertIn('action="/back"', page)
        status, _, _ = self.call("POST", "/back", {"token": "wrong", "lesson": str(self.gone)})
        self.assertEqual(status, 403)
        self.assertEqual(self.lessons.back_links(self.gone)["as"], [])
        status, _, headers = self.call("POST", "/back", {"token": self.server.token, "lesson": str(self.gone)})
        self.assertEqual((status, headers["Location"]), (303, "/"))
        n, = self.lessons.back_links(self.gone)["as"]
        self.assertEqual(self.lessons.get(n)["state"], TRYING)
        page = self.call("GET", "/", origin=None)[1]
        self.assertIn(f"Lesson {self.gone} is back as lesson {n}", page)


class Rollback(ts.Base):
    def steps(self, snap, at=ts.T3):
        with self.db.tx() as c:
            return {s["id"]: (s["do"], s["why"]) for s in snap_mod.plan(c, "waterer", snap, at)}

    def test_with_bring_back_the_lessons_pulled_since_come_back_in_the_same_go_signed(self):
        ids = self.build()
        preview = self.rollback("--by", "Mohamed")[1]
        code, out, err = self.paste(preview, bring_back=True)
        self.assertEqual((code, err), (0, ""))
        n, = self.lessons.back_links(ids["E"])["as"]
        new = self.lessons.get(n)
        self.assertEqual((new["text"], new["stages"], new["state"], new["yes_by"], new["source"]),
                         ("Visit the north bed first.", ["seedling"], WAITING, "Mohamed",
                          f"brought back by Mohamed from lesson {ids['E']}"))
        self.assertEqual(self.lessons.waits_for(n, ts.T3), [ids["C"]])  # its stage has a lesson ahead of it
        self.assertEqual(self.lessons.get(ids["E"])["state"], PULLED)
        rb, = snap_mod.rollbacks(self.db, "waterer")
        self.assertEqual((rb["detail"]["pulled"], rb["detail"]["brought_back"], rb["detail"]["offered_back"]),
                         ([ids["D"], ids["F"], ids["H"]], [{"id": ids["E"], "as": n}], []))
        self.assertIn(n, {e["id"] for e in rb["lessons"]})
        self.assertIn(f"Done, signed by Mohamed: pulled lesson {ids['D']}, {ids['F']}, {ids['H']}; brought back lesson "
                      f"{ids['E']} as lesson {n}. Recorded as snapshot {rb['id']} (rollback).\n", out)

    def test_the_pulls_go_first_so_a_stage_they_free_takes_the_line_at_once(self):
        L = self.lessons
        a = L.add("Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=ts.T1 - 7200)
        snap_mod.take(self.db, "waterer", ts.T1)
        L.pull(a, "stopped by the owner: too slow", now=ts.T1 + 3600)
        p = L.propose("Wait a day between rounds on the grown beds.", ["grown"], sources=[], now=ts.T1 + 3700)
        preview = self.rollback()[1]
        self.assertIn(f'  bring back: lesson {a} "Water the grown beds at dusk.": pulled since (stopped by the owner: '
                      "too slow); with --bring-back it comes back as a new lesson on trial or waiting its turn, and this one stays "
                      "pulled\n", preview)
        self.assertEqual(self.paste(preview, bring_back=True)[0], 0)
        n, = L.back_links(a)["as"]
        self.assertEqual((L.get(p)["state"], L.get(n)["state"]), (PULLED, TRYING))

    def test_a_bring_back_that_fails_undoes_the_pulls_too(self):
        ids = self.build()

        class Flaky(Lessons):
            def bring_back(self, lesson_id, by, **kw):
                raise ValueError("the stage is gone")

        before = self.tables()
        with self.assertRaisesRegex(snap_mod.Refused, f"lesson {ids['E']} could not come back \\(the stage is gone\\); "
                                                      "nothing done"):
            snap_mod.rollback(self.db, Flaky(self.db, self.plug, judge=always_low), self.first, OWNER, ts.T3,
                              code=self.code(self.first), bring_back=True)
        self.assertEqual(self.tables(), before)

    def test_the_code_covers_the_bring_back_list(self):
        ids = self.build()
        preview = self.rollback()[1]
        self.lessons.bring_back(ids["E"], "Ziad", now=ts.T3 - 60)  # a Bring back on the morning page meanwhile
        before = self.tables()
        code, out, err = self.paste(preview, bring_back=True)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("Not run: the plan changed; run it again without --yes.", err)
        self.assertEqual(self.tables(), before)
        steps = [{"id": 5, "line": "x", "do": snap_mod.PULL}]
        self.assertNotEqual(snap_mod.plan_code(self.first, steps),
                            snap_mod.plan_code(self.first, steps + [{"id": 2, "line": "y", "do": snap_mod.BACK}]))
        self.assertNotEqual(snap_mod.plan_code(self.first, steps + [{"id": 2, "line": "y", "do": snap_mod.BACK}]),
                            snap_mod.plan_code(self.first, steps + [{"id": 2, "line": "z", "do": snap_mod.BACK}]))

    def test_a_line_back_already_is_listed_and_its_copy_stays(self):
        ids = self.build()
        n = self.lessons.bring_back(ids["E"], OWNER, now=ts.T2 + 60)
        preview = self.rollback()[1]
        self.assertIn(f'  already back: lesson {ids["E"]} "Visit the north bed first.": pulled since (stopped by the '
                      f"owner: too slow); its line is back already as lesson {n}\n", preview)
        self.assertIn(f'  stays: lesson {n} "Visit the north bed first.": brought back since; its line was given that '
                      f"night as lesson {ids['E']}; it waits its turn\n", preview)
        self.assertNotIn("--bring-back", preview)
        self.assertEqual(self.paste(preview)[0], 0)
        self.assertEqual(self.lessons.get(n)["state"], WAITING)
        self.assertEqual(self.lessons.get(ids["H"])["state"], PULLED)

    def test_a_live_copy_stays_and_a_paused_copy_cannot_come_back(self):
        L = self.lessons
        a = L.add("Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=ts.T1 - 7200)
        first = snap_mod.take(self.db, "waterer", ts.T1)
        L.pull(a, "", now=ts.T1 + 3600)
        n = L.bring_back(a, OWNER, now=ts.T1 + 3700)
        self.assertEqual(self.steps(first), {
            a: (snap_mod.ALREADY, f"pulled since; its line is back already as lesson {n}"),
            n: (snap_mod.STAYS, f"brought back since; its line was given that night as lesson {a}")})
        self.assertTrue(L.pause(n, ts.T1 + 4000))
        self.assertEqual(self.steps(first)[n], (snap_mod.CANNOT, f"brought back since; its line was given that night "
                                                f"as lesson {a}; its trial ended since and waits for its verdict; a "
                                                "trial never starts again"))
        self.assertNotIn("--yes", self.rollback()[1])  # nothing to pull, nothing to bring back

    def test_a_copy_made_from_an_older_lesson_of_the_family_stands_for_the_line_too(self):
        L = self.lessons
        r = L.add("Water the grown beds at dusk.", ["grown"], yes_by=OWNER, now=ts.T1 - 7200)
        L.pull(r, "stopped", now=ts.T1 - 7000)
        m = L.bring_back(r, OWNER, now=ts.T1 - 6000)
        first = snap_mod.take(self.db, "waterer", ts.T1)  # m given that night
        L.pull(m, "stopped", now=ts.T1 + 3600)
        x = L.bring_back(r, OWNER, now=ts.T1 + 3700)  # from r, not from m
        self.assertEqual(self.steps(first), {
            m: (snap_mod.ALREADY, f"pulled since (stopped); its line is back already as lesson {x}"),
            x: (snap_mod.STAYS, f"brought back since; its line was given that night as lesson {m}")})


class NightReport(EngineBase):
    """The night report names each lesson it shows that a person brought back, with the pulled
    lesson it came from, from the engine's back_links()."""

    def night(self, until):
        return night_mod.night(self.db, self.plug, until=until, days=1, judge=always_low, proposer=fk.Proposer(),
                               tagger=fk.Tagger(), fit=fk.Fit(), adapter=fk.Adapter(), others=[])

    def test_a_trial_checked_names_the_lesson_it_was_brought_back_from(self):
        a = self.pulled()
        other = self.L.propose("Visit the north bed first.", ["seedling"], sources=[], now=T)
        self.assertEqual(self.L.get(other)["state"], TRYING)
        n = self.L.bring_back(a, OWNER, now=T + 120)
        rep = self.night(T + 2 * DAY)
        self.assertEqual(sorted(t["lesson_id"] for t in rep["trials"]["trials"]), sorted([other, n]))
        self.assertEqual(rep["links"]["brought_back"], [{"lesson_id": n, "from_lesson": a}])
        lines = night_mod.text(rep, self.plug)
        self.assertIn(f"  links 1\n    - lesson {n}: brought back from lesson {a} by a person\n", lines)
        self.assertNotIn(f"lesson {other}: brought back", lines)
        self.assertEqual(night_mod.links(rep)["brought_back"], [])  # no lessons given, no link read

    def test_a_trial_started_from_its_turn_names_it_too(self):
        a = self.pulled()
        p = self.L.propose("Visit the south bed last.", ["grown"], sources=[], now=T + 90)
        self.assertEqual(self.L.get(p)["state"], TRYING)
        n = self.L.bring_back(a, OWNER, now=T + 120)
        self.assertEqual(self.L.get(n)["state"], WAITING)
        rep = self.night(T + 9 * DAY)  # the trial of p has ended, so n starts from its turn
        self.assertEqual(rep["trials"]["started"], [n])
        self.assertNotIn(n, [t["lesson_id"] for t in rep["trials"]["trials"]])
        self.assertEqual(rep["links"]["brought_back"], [{"lesson_id": n, "from_lesson": a}])
        self.assertIn(f"    - lesson {n}: brought back from lesson {a} by a person", night_mod.text(rep, self.plug))
        self.assertNotIn(p, [b["lesson_id"] for b in rep["links"]["brought_back"]])


if __name__ == "__main__":
    unittest.main()
