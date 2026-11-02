"""Task t261029s gap 2: the night runner (reflection/night.py). It opens the agent's database,
loads its plug and the other plugs, runs the engine's night study once over a window with the
Meta parts, prints the report in plain lines and saves it as JSON next to the database. It
refuses to start without the keys it needs, naming the variable, and never prints a key.

No test touches the network or the repo's .env or data/: kit.net.open_once is a fake that
answers like the models, every key is a random stand-in, and each database is a temp file."""
import contextlib
import io
import json
import secrets
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from engine import risk
from engine.lessons import Lessons
from engine.log import Log
from kit import model as kit_model
from kit.db import Db
from reflection import PLUG as SALES
from reflection import night
from reflection.judge import Judge
from reflection.lessons import Lessons as SalesLessons
from tests import plugs
from tests import study_fakes as fk
from tests.test_engine_cases import OLD_ROWS, old_database, tables
from tests.test_model_routes import BASETEN_URL, META_URL, Resp, env_with
from tests.test_study_route import Network
from tests.kept import kept_lesson

ROOT = Path(night.__file__).resolve().parent.parent
BASETEN, META = kit_model.OPEN.key_env, kit_model.WONDER.key_env
ACROSS_UNTIL = fk.T0 + 60 * 86400  # long enough for a month of books to settle
FAN_EARLY = "Turn the fan on early in the morning."
FAN_TWICE = "Check the fan twice before turning it on."
KEPT_LINE = "Post entries in date sequence."
FAN_KEPT = "Spin the fans in house sequence."


class Models(Network):
    """The study route's fake network, with the judge answering low."""

    def __call__(self, req, timeout):
        body = json.loads(req.data)
        if body["messages"][0]["content"].startswith("You sort one lesson"):
            self.seen.append((req.full_url, req.get_header("Authorization"), body))
            return Resp(json.dumps({"choices": [{"message": {"role": "assistant", "content": "low"}}]}).encode())
        return super().__call__(req, timeout)


class Setup(unittest.TestCase):
    def setUp(self):
        self.stand_in = {BASETEN: secrets.token_urlsafe(24), META: secrets.token_urlsafe(24)}
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.plug_path = self.dir / "plug.json"
        self.plug_path.write_text(json.dumps(plugs.WATERER), encoding="utf-8")
        self.db_path = self.dir / "agent.db"
        db = Db(self.db_path)
        fk.beds(Log(db, plug_mod.load(self.plug_path)))
        db.close()
        p = mock.patch("kit.env.load", return_value=[])  # never the repo's .env
        p.start()
        self.addCleanup(p.stop)
        self.net = Models()
        p = mock.patch("kit.net.open_once", self.net)
        p.start()
        self.addCleanup(p.stop)

    def env(self, without=(), **values):
        given = {n: v for n, v in self.stand_in.items() if n not in without}
        given.update(values)
        env_with(self, **given)

    def run_main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(self.plug_path), "--db", str(self.db_path), "--days", "30", *extra],
                              until=fk.UNTIL)
        return code, out.getvalue(), err.getvalue()


class Refuses(Setup):
    def assert_refused(self, name):
        with mock.patch.object(night, "Db", side_effect=AssertionError("no database without the keys")):
            code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn(name, err)
        self.assertEqual(out, "")
        self.assertEqual(self.net.seen, [])
        self.assertEqual(list(self.dir.glob("night-*.json")), [])
        for value in self.stand_in.values():
            self.assertNotIn(value, err)
        return err

    def test_one_meta_key_is_enough(self):
        """Review round 1 finding 1: the fit check, the adapter and the judge run on Meta alone."""
        for flag in ({}, {"META_STUDY_ROUTE": "open"}):
            with self.subTest(flag=flag):
                self.env(without=(BASETEN,), **flag)
                self.assertEqual(night.missing_keys(), [])

    def test_no_model_key_at_all_names_both(self):
        self.env(without=(BASETEN, META), META_STUDY_ROUTE="open")
        self.assertEqual(night.missing_keys(), [night.MODEL_KEYS])
        self.assert_refused("META_API_KEY or BASETEN_API_KEY")
        self.env(without=(BASETEN, META))
        self.assertEqual(night.missing_keys(), [META])  # the wonder route's key is either key too

    def test_no_meta_key_on_the_wonder_route(self):
        for flag in ({}, {"META_STUDY_ROUTE": "wonder"}):
            with self.subTest(flag=flag):
                self.env(without=(META,), **flag)
                self.assert_refused(META)

    def test_the_open_route_needs_no_meta_key(self):
        self.env(without=(META,), META_STUDY_ROUTE="open")
        self.assertEqual(night.missing_keys(), [])

    def test_a_bad_route_value_is_named(self):
        self.env(META_STUDY_ROUTE="wondr")
        self.assert_refused("META_STUDY_ROUTE")

    def test_no_database_file_is_named_and_none_is_made(self):
        self.env()
        missing = self.dir / "none.db"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(self.plug_path), "--db", str(missing)], until=fk.UNTIL)
        self.assertEqual(code, 2)
        self.assertIn("no database", err.getvalue())
        self.assertFalse(missing.exists())
        self.assertEqual(self.net.seen, [])


class OneNight(Setup):
    def test_it_runs_the_study_with_the_meta_parts_and_prints_plain_lines(self):
        self.env()
        code, out, err = self.run_main()
        self.assertEqual(code, 0, err)
        urls = [u for u, _, _ in self.net.seen]
        self.assertIn(META_URL, urls)      # the proposer and the tagger on Muse Wonder
        self.assertIn(BASETEN_URL, urls)   # the judge on Muse Spark Open
        for url, auth, _ in self.net.seen:
            self.assertEqual(auth, "Bearer " + self.stand_in[META if url == META_URL else BASETEN])
        self.assertIn("Night study of waterer", out)
        self.assertIn("read 20 cases", out)
        self.assertIn(f'"{fk.EARLY["lesson"]}": on trial', out)
        self.assertIn("proposer Meta muse-wonder-1.0", out)
        self.assertIn("judge Baseten", out)

    def test_the_report_is_saved_as_json_next_to_the_database(self):
        self.env()
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        saved = list(self.dir.glob("night-waterer-*.json"))
        self.assertEqual(len(saved), 1)
        self.assertIn(str(saved[0]), out)
        rep = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertEqual(rep["agent"], "waterer")
        self.assertEqual(rep["window"], {"since": fk.UNTIL - 30 * 86400, "until": fk.UNTIL})
        self.assertEqual([c["state"] for c in rep["cards"]], ["trying"])

    def test_json_prints_the_same_report(self):
        self.env()
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        saved = next(self.dir.glob("night-waterer-*.json"))
        self.assertEqual(json.loads(out), json.loads(saved.read_text(encoding="utf-8")))

    def test_no_key_is_printed_or_saved(self):
        self.env()
        code, out, err = self.run_main()
        saved = next(self.dir.glob("night-waterer-*.json")).read_text(encoding="utf-8")
        for value in self.stand_in.values():
            for where in (out, err, saved):
                self.assertNotIn(value, where)

    def test_a_refused_call_is_a_note_and_makes_no_lesson(self):
        self.env()

        def refuse(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

        with mock.patch("kit.net.open_once", refuse):
            code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("lesson cards 0", out)
        self.assertIn("the proposer failed", out)
        for value in self.stand_in.values():
            self.assertNotIn(value, out + err)

    def test_the_other_plugs_in_the_repo_are_given(self):
        self.env()
        self.run_main()
        rep = json.loads(next(self.dir.glob("night-waterer-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(sorted(a["agent"] for a in rep["across"]), ["assistant", "marketing", "sales"])


def always_low(text, high_about, low_about):
    return risk.LOW


class TheSalesNight(unittest.TestCase):
    """Review t261029s finding 4: the Sales agent's night gives its lessons the night's judge,
    never the engine's stub, and first moves an old results table into the engine's log."""

    def night(self, db, **kw):
        with mock.patch.object(night, "LinkedStudy", wraps=night.LinkedStudy) as study:
            rep = night.night(db, SALES, until=200.0, days=1, proposer=fk.Proposer(fk.EARLY, fk.TWICE),
                              tagger=fk.Tagger(), fit=fk.Fit(), adapter=fk.Adapter(), others=[], **kw)
        return rep, study.call_args.kwargs["lessons"]

    def memory_db(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        return db

    def test_the_lessons_get_the_judge_given(self):
        _, lessons = self.night(self.memory_db(), judge=always_low)
        self.assertIsInstance(lessons, SalesLessons)
        self.assertIs(lessons.judge, always_low)

    def test_by_default_the_lessons_get_the_meta_judge(self):
        env_with(self)  # no key; the judge is built and not called
        with mock.patch("kit.env.load", return_value=[]), \
                mock.patch("kit.net.open_once", side_effect=AssertionError("no call in this test")):
            rep, lessons = self.night(self.memory_db())
        self.assertIsInstance(lessons.judge, Judge)
        self.assertIsNot(lessons.judge, risk.no_judge)
        self.assertIs(lessons.judge.model.route, kit_model.OPEN)

    def test_the_night_checks_the_trials_first(self):
        db = self.memory_db()
        les = SalesLessons(db, judge=always_low)
        lid = les.propose("Ask for the size before you show the colours.", ["all"], source="test", sources=[],
                          now=0.0)
        self.assertEqual(les.get(lid)["state"], "trying")
        rep, _ = self.night(db, judge=always_low)  # until 200.0 is before its end date: still on trial
        self.assertEqual([(t["lesson_id"], t["status"]) for t in rep["trials"]["trials"]], [(lid, "on trial")])
        rep = night.night(db, SALES, until=30 * 86400.0, days=1, proposer=fk.Proposer(), tagger=fk.Tagger(),
                          fit=fk.Fit(), adapter=fk.Adapter(), others=[], judge=always_low)
        entry, = rep["trials"]["trials"]
        self.assertEqual((entry["lesson_id"], entry["status"]), (lid, "unclear"))  # no case was given it
        self.assertEqual(les.get(lid)["state"], "trying")  # given in no case, it waits for a person
        self.assertIn(f'  trials checked 1\n    - lesson {lid} "Ask for the size before you show the colours.": '
                      f'unclear. ', night.text(rep, SALES))

    def test_an_old_results_table_is_moved_first(self):
        db = Db(old_database(self))
        self.addCleanup(db.close)
        self.night(db, judge=always_low)
        self.assertNotIn("results", tables(db))
        with db.tx() as c:
            moved = c.execute("SELECT count(*) AS n FROM trace WHERE agent = ?", (SALES.agent,)).fetchone()["n"]
        self.assertEqual(moved, len(OLD_ROWS))


class Links(unittest.TestCase):
    """Each new lesson in the night's report links back to every case that had its pattern, or
    to the other agent's kept lesson it came from, and the report names the agents it read."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.waterer = plugs.load(plugs.WATERER, self)
        self.fan = plugs.load(plugs.FAN, self)
        self.ledger = plugs.load(plugs.LEDGER, self)
        self.logs = {p.agent: Log(self.db, p) for p in (self.waterer, self.fan, self.ledger)}

    def night(self, plug, **kw):
        kw.setdefault("proposer", fk.Proposer(fk.EARLY, fk.TWICE))
        kw.setdefault("fit", fk.Fit())
        kw.setdefault("adapter", fk.Adapter())
        return night.night(self.db, plug, until=ACROSS_UNTIL, days=60, judge=always_low, tagger=fk.Tagger(), **kw)

    def test_an_own_lesson_links_to_every_case_with_its_pattern(self):
        fk.beds(self.logs["waterer"], early_good=18, early_bad=5)
        rep = self.night(self.waterer, others=[])
        card, = rep["cards"]
        link, = rep["links"]["lessons"]
        self.assertEqual({k: v for k, v in link.items() if k != "cases"},
                         {"lesson_id": card["lesson_id"], "state": "trying", "from_agent": "waterer",
                          "from_lesson": None, "waits_for": []})
        self.assertEqual(sorted(link["cases"]), sorted(f"bed{n}" for n in range(1, 24)))  # all 23
        self.assertIn("and 3 more", card["source"])  # where the lesson's source line names 20
        self.assertEqual((rep["links"]["agents_read"], rep["links"]["agents_not_read"]), (["waterer"], []))
        lines = night.text(rep, self.waterer)
        self.assertIn(f'lesson {card["lesson_id"]} (on trial): from waterer cases bed1, bed2, ', lines)
        self.assertIn("bed20 and 3 more (all in the saved report)", lines)
        self.assertIn("agents read: waterer; not read: none", lines)

    def test_lessons_from_other_agents_link_to_their_cases_or_their_kept_lesson(self):
        fk.beds(self.logs["waterer"])
        fk.entries(self.logs["ledger"])
        kept = kept_lesson(Lessons(self.db, self.ledger, judge=always_low), KEPT_LINE, ["all"], yes_by="owner")
        fit = fk.Fit({fk.EARLY["lesson"]: "partly", fk.TWICE["lesson"]: "fully", KEPT_LINE: "partly"})
        adapter = fk.Adapter({fk.EARLY["lesson"]: FAN_EARLY, fk.TWICE["lesson"]: FAN_TWICE, KEPT_LINE: FAN_KEPT})
        rep = self.night(self.fan, others=[self.ledger, self.waterer], fit=fit, adapter=adapter)
        ids = {c["change"]: c["lesson_id"] for c in rep["cards"]}
        self.assertEqual(set(ids), {FAN_EARLY, FAN_TWICE, FAN_KEPT})
        got = {link["lesson_id"]: link for link in rep["links"]["lessons"]}
        self.assertEqual(set(got), set(ids.values()))
        early, twice, adapted = got[ids[FAN_EARLY]], got[ids[FAN_TWICE]], got[ids[FAN_KEPT]]
        self.assertEqual((early["from_agent"], sorted(early["cases"]), early["from_lesson"]),
                         ("waterer", sorted(f"bed{n}" for n in range(1, 11)), None))
        self.assertEqual((twice["from_agent"], sorted(twice["cases"]), twice["from_lesson"]),
                         ("ledger", sorted(f"month{n}" for n in range(1, 11)), None))
        self.assertEqual((adapted["from_agent"], adapted["cases"], adapted["from_lesson"]), ("ledger", [], kept))
        self.assertEqual((rep["links"]["agents_read"], rep["links"]["agents_not_read"]),
                         (["fan", "waterer", "ledger"], []))
        lines = night.text(rep, self.fan)
        # one trial per stage: the two ledger lessons wait their turn behind the first (step 6)
        self.assertIn(f"lesson {ids[FAN_KEPT]} (waits its turn): adapted from ledger lesson {kept}", lines)
        self.assertIn(f"lesson {ids[FAN_TWICE]} (waits its turn): from ledger cases month1, ", lines)
        self.assertIn(f'"{FAN_KEPT}" (adapted from ledger): waits its turn behind lesson {ids[FAN_EARLY]}, '
                      f'{ids[FAN_TWICE]}', lines)

    def test_the_agents_not_read_are_named(self):
        fk.beds(self.logs["waterer"])
        fk.entries(self.logs["ledger"])
        rep = self.night(self.fan, others=[self.waterer])
        self.assertEqual((rep["links"]["agents_read"], rep["links"]["agents_not_read"]),
                         (["fan", "waterer"], ["ledger"]))
        self.assertIn("agents read: fan, waterer; not read: ledger", night.text(rep, self.fan))
        study = night.LinkedStudy(self.db, self.fan, proposer=fk.Proposer(), tagger=fk.Tagger(),
                                  others=[self.waterer])  # a plug given, but no fit check or adapter
        rep = study.run(fk.SINCE, ACROSS_UNTIL, now=ACROSS_UNTIL)
        self.assertEqual(night.links(rep, study.others)["agents_not_read"], ["ledger", "waterer"])


class TheWindow(unittest.TestCase):
    def test_default_days_come_from_the_plug(self):
        self.assertEqual(night.default_days(SALES), 2.0)  # an order shows within a day, the window for a chat never closed
        self.assertEqual(night.default_days(plug_mod.load(ROOT / "marketing" / "plug.json")), 8.0)

    def test_the_sales_night_runs_on_its_own_bindings(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        rep = night.night(db, SALES, until=fk.UNTIL, others=[], judge=lambda *a: "unsure",
                          proposer=fk.Proposer(), tagger=fk.Tagger())
        self.assertEqual((rep["agent"], rep["days"]), ("sales", 2.0))
        self.assertEqual(rep["window"]["since"], fk.UNTIL - 2 * 86400)

    def test_days_must_be_more_than_zero(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        with self.assertRaises(night.Refused):
            night.night(db, SALES, days=0, until=fk.UNTIL, others=[], judge=lambda *a: "unsure",
                        proposer=fk.Proposer(), tagger=fk.Tagger())


if __name__ == "__main__":
    unittest.main()
