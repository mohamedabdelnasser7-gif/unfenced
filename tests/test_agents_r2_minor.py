"""Minor fixes from review t261029l round 2 (29 Oct), in the agents' plugs and the simulator.

4. In the marketing plug, "مكان" (a place) is personal data, but not inside "إمكان" (being
   able to): بإمكانك and إمكانية are plain words.
6. The simulator's found line names the pattern behind each lesson and whether it helps or
   hurts, so a hurting pattern no longer reads as one that helps.
8. Gaps the mutant sweep found: the simulator closes its in memory log when the run ends or
   fails (u02) and takes a scenario's agent only as a plain name (u03); in the marketing plug,
   a street, where someone lives and شارع are personal data (p03, p04, p05).
"""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import plug as plug_mod
from engine import risk
from sim import run
from tests import test_sim_plants as plants

ROOT = Path(__file__).resolve().parent.parent
MARKETING = plug_mod.load(ROOT / "marketing/plug.json")


def place_lines(text):
    """The code check's lines for "a place" in the marketing plug."""
    return [x for x in risk.code_check(text, MARKETING.risk) if "مكان" in x]


class APlace(unittest.TestCase):
    def test_being_able_to_is_not_a_place(self):
        for text in ("بإمكانك تطلب من الصفحة على طول.", "بامكانك تطلب من الصفحة على طول.",
                     "إمكانية الشحن لكل المحافظات.", "امكانية الشحن لكل المحافظات.", "بالإمكان نرجعه."):
            with self.subTest(text=text):
                self.assertEqual(place_lines(text), [])

    def test_a_place_is_still_personal_data(self):
        for text in ("اكتبلنا مكانك في الكومنت.", "قولنا المكان فين.", "ابعتلنا مكان التسليم."):
            with self.subTest(text=text):
                self.assertEqual(place_lines(text), ["personal_data: /(?<!ا)مكان/"])
                self.assertEqual(risk.classify(text, MARKETING.risk, lambda *a: risk.LOW)[0], risk.HIGH)


class FoundLine(unittest.TestCase):
    NEVER_ASKED = "The agent sent the summary without asking the usual size."
    PRICE_FIRST = "The post showed the price in its first line."

    def main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(run.main(list(argv)), 0)
        return buf.getvalue()

    def under(self, out, lesson):
        lines = out.splitlines()
        at = [n for n, x in enumerate(lines) if x.startswith(f'    - "{lesson}"')]
        self.assertEqual(len(at), 1, lesson)
        return lines[at[0] + 1].strip()

    def test_the_found_line_names_the_pattern_and_which_way_it_goes(self):
        out = self.main()
        self.assertTrue(self.under(out, plants.SALES_REAL).startswith(
            f'pattern "{self.NEVER_ASKED}" hurts: with it 59 of 99 order_created, without it 87 of 101; chance it '
            'hurts '))
        self.assertTrue(self.under(out, plants.MK_REAL).startswith(f'pattern "{self.PRICE_FIRST}" helps: with it '))
        self.assertTrue(self.under(out, plants.MK_FROM_SALES_REAL).startswith(
            f'from sales\'s cases: pattern "{self.NEVER_ASKED}" hurts: with it 59 of 99 order_created, '))
        self.assertNotIn("chance it is better", out)

    def test_the_summary_carries_the_pattern_and_which_way_it_goes(self):
        data = {s["agent"]: s for s in json.loads(self.main("--json"))}
        got = {(f["lesson"], f["pattern"], f["helps"]) for s in data.values() for f in s["found"]}
        self.assertEqual(got, {(plants.SALES_REAL, self.NEVER_ASKED, False),
                               (plants.MK_REAL, self.PRICE_FIRST, True),
                               (plants.MK_FROM_SALES_REAL, self.NEVER_ASKED, False)})


class PersonalData(unittest.TestCase):
    def test_a_street_and_where_someone_lives_are_personal_data(self):
        for text, line in (("Tell us which street you are on.", "personal_data: street"),
                           ("Name the streets near the shop.", "personal_data: street"),
                           ("Tell us where you live in the comments.", "personal_data: where you live"),
                           ("قولنا الشارع اللي انت فيه.", "personal_data: شارع"),
                           ("اكتب اسم شارعك في الكومنت.", "personal_data: شارع")):
            with self.subTest(text=text):
                level, why = risk.classify(text, MARKETING.risk, lambda *a: risk.LOW)
                self.assertEqual(level, risk.HIGH)
                self.assertIn(line, why)


class TheLogCloses(unittest.TestCase):
    def spy(self):
        made, real = [], run.Db

        def db(*args, **kw):
            made.append(real(*args, **kw))
            return made[-1]
        return made, mock.patch.object(run, "Db", db)

    def assert_closed(self, made):
        self.assertEqual(len(made), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            made[0].conn.execute("SELECT 1")

    def test_the_log_is_closed_when_the_run_ends(self):
        made, patch = self.spy()
        with patch:
            self.assertEqual(len(run.night()), 2)
        self.assert_closed(made)

    def test_the_log_is_closed_when_a_study_fails(self):
        made, patch = self.spy()
        with patch, mock.patch.object(run.Study, "run", side_effect=RuntimeError("down")):
            with self.assertRaises(RuntimeError):
                run.night()
        self.assert_closed(made)


class ScenarioAgentName(unittest.TestCase):
    def agents(self, agent):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "sim" / "scenarios"
            folder.mkdir(parents=True)
            (folder / "x.json").write_text(json.dumps({"agent": agent}), encoding="utf-8")
            with mock.patch.object(run, "ROOT", Path(d)):
                return run._agents()

    def test_the_agent_must_be_a_plain_name(self):
        for agent in ("../sales", "Sales agent", "a/b", "", 7, None):
            with self.subTest(agent=agent):
                with self.assertRaises(ValueError) as e:
                    self.agents(agent)
                self.assertIn("x.json: the agent must be a plain name", str(e.exception))

    def test_a_plain_name_names_its_plug_folder(self):
        self.assertEqual(self.agents("sales"), (("sales/plug.json", "sim/scenarios/x.json"),))


if __name__ == "__main__":
    unittest.main()
