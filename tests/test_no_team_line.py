"""DECISIONS 74: nothing tells the Sales agent to say it will check with the team. The instruction
line, the exam and the tool texts only state what is known or missing; no new rule takes the
team line's place."""
import json
import re
import types
import unittest
from pathlib import Path
from unittest import mock

from kit import tools
from kit.tools import delivery, draft_order, store
from reflection import PLUG
from reflection import exam

ROOT = Path(__file__).resolve().parent.parent
TEAM = re.compile(r"check with the team|فريق|team", re.IGNORECASE)


class NoTeamLine(unittest.TestCase):
    def test_instruction_line_keeps_never_guess_without_the_team(self):
        text = (ROOT / "sales" / "instructions.md").read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("Use only facts from your tools"))
        self.assertIn("Never guess.", line)
        self.assertNotRegex(line, TEAM)
        self.assertNotIn("check with the team", text)

    def test_exam_has_no_team_check_or_expectation(self):
        self.assertNotIn("check_with_team", exam.CHECKS)
        self.assertNotIn("check_with_team", PLUG.exam.checks)
        self.assertFalse(hasattr(exam, "TEAM_WORD"))
        sits = json.loads(PLUG.exam.situations.read_text(encoding="utf-8"))["situations"]
        self.assertEqual([s["name"] for s in sits if "team" in s["expect"]], [])
        self.assertEqual([s["name"] for s in sits if TEAM.search(s.get("note", ""))], [])

    def test_a_failed_tool_says_only_that_it_failed(self):
        ctx = types.SimpleNamespace(stage="asking")
        with mock.patch.object(tools, "offered", return_value=["store"]), \
                mock.patch.object(store, "check", return_value=(True, "")), \
                mock.patch.object(store, "run", side_effect=RuntimeError("down")), \
                self.assertLogs("kit.tools", level="ERROR"):
            out = tools.run("store", {}, ctx)
        self.assertEqual(out, {"ok": False, "feedback": "The tool store failed."})

    def test_no_fee_says_only_what_is_missing(self):
        with mock.patch.object(store, "delivery", return_value={"zones": []}):
            out = delivery.quote("Cairo")
        self.assertEqual(out, {"ok": False, "note": "The delivery data has no fee for this governorate."})

    def test_no_price_says_only_what_is_missing(self):
        catalogue = [{"title": "Plain Boot", "variants": [{"size": "42"}]}]
        self.assertEqual(draft_order._variant(catalogue, "Plain Boot", "42"),
                         (None, None, "This product has no price in the store data."))


if __name__ == "__main__":
    unittest.main()
