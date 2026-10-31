"""The demo's crowd (demo/make_crowd.py): simulated chats, the same bytes for the same count and seed."""
import collections
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from demo import make_crowd
from kit.tools import store
from reflection import PLUG
from reflection import exam
from tests.fake_model import FakeModel, clean_env, say

ROOT = Path(make_crowd.__file__).resolve().parent.parent
KEPT = ROOT / "demo" / "crowd.jsonl"


class Crowd(unittest.TestCase):
    def setUp(self):
        self.rows = [json.loads(line) for line in KEPT.read_text(encoding="utf-8").splitlines()]

    def test_a_fresh_run_writes_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "crowd.jsonl"
            run = subprocess.run([sys.executable, "-I", str(ROOT / "demo" / "make_crowd.py"), "--out", str(out)],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(out.read_bytes(), KEPT.read_bytes())

    def test_each_chat_is_simulated_and_fake(self):
        titles = {i["title"] for i in store._from_demo(store.DEMO_CATALOGUE)}
        self.assertEqual(len(self.rows), make_crowd.COUNT)
        self.assertEqual(len({r["phone"] for r in self.rows}), len(self.rows))
        for r in self.rows:
            self.assertIs(r["simulated"], True)
            self.assertRegex(r["phone"], r"^\+20 100 000 0\d{3}$")
            self.assertTrue(r["name"].endswith("تجربة") or r["name"].startswith("Demo "), r["name"])
            self.assertIn(r["stage"], PLUG.stages)
            self.assertIn(r["product"], titles)
            self.assertIn("customer", r["turns"][-1])
        langs = collections.Counter(r["language"] for r in self.rows)
        self.assertGreater(langs["arabic"], len(self.rows) / 2)  # most in Egyptian Arabic
        self.assertEqual(set(langs), {"arabic", "franco", "english"})

    def test_prices_and_sizes_come_from_the_demo_store(self):
        prices = set(store.price_points())
        for r in self.rows:
            for t in r["turns"]:
                for n in re.findall(r"\d{3,}", t.get("agent", "")):
                    self.assertIn(int(n), prices, t["agent"])

    def test_seed_and_count(self):
        self.assertEqual(make_crowd.crowd(5, 1), make_crowd.crowd(5, 1))
        self.assertNotEqual(make_crowd.crowd(5, 1), make_crowd.crowd(5, 2))
        with self.assertRaises(ValueError):
            make_crowd.crowd(501)
        with self.assertRaises(ValueError):
            make_crowd.crowd(0)

    def test_a_chat_runs_through_the_sales_reply_path(self):
        clean_env(self)
        did = exam.answer(self.rows[2], None, model=FakeModel(say("تمام، هشوفلك.")))
        self.assertEqual((did["reply"], did["customer_text"]), ("تمام، هشوفلك.", self.rows[2]["turns"][-1]["customer"]))


if __name__ == "__main__":
    unittest.main()
