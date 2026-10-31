"""The judge's own key (new, 2026-10-31; DECISIONS item 33): which key runs what, the Meta API
fallback when Baseten fails, the one-line pointer when no key is set, .env.example, the no-key
recorded replay (no key, no network) and the quick Arena run's call limit. No test touches the
network; every key here is a random stand-in."""
import contextlib
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from arena import run
from kit import env as kit_env
from kit import model as kit_model
from kit import net
from recorded import play, record
from tests.fake_model import Buyer, Seller, clean_env, say

ROOT = Path(run.__file__).resolve().parent.parent
BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"
META_URL = "https://api.meta.ai/v1/chat/completions"
OUR_ENV = ("BASETEN_API_KEY", "BASETEN_MODEL", "META_API_KEY", "META_MODEL", "META_STUDY_MODEL", "META_STUDY_ROUTE")
HI = [{"role": "user", "content": "hi"}]


def env_with(test, **values):
    """Run a test with none of our model env names set, except the ones given."""
    env = {k: v for k, v in os.environ.items() if k not in OUR_ENV}
    env.update(values)
    p = mock.patch.dict(os.environ, env, clear=True)
    p.start()
    test.addCleanup(p.stop)


class Resp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok(content="ok", reason="stop"):
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content},
                                    "finish_reason": reason}]}).encode()


def http_error(url, code):
    return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b"{}"))


class Transport:
    """Stands in for the network: answers per host from a list (an exception is raised, bytes are
    the body), and keeps every request."""

    def __init__(self, baseten=(), meta=()):
        self.plan = {BASETEN_URL: list(baseten), META_URL: list(meta)}
        self.seen = []

    def __call__(self, req, timeout):
        self.seen.append(req)
        step = self.plan[req.full_url].pop(0) if self.plan[req.full_url] else ok()
        if isinstance(step, BaseException):
            raise step
        return Resp(step)

    def hosts(self):
        return [r.full_url for r in self.seen]


class KeyChoice(unittest.TestCase):
    def setUp(self):
        self.b, self.m = secrets.token_urlsafe(24), secrets.token_urlsafe(24)

    def test_only_the_meta_key_runs_muse_spark_on_the_meta_api(self):
        env_with(self, META_API_KEY=self.m)
        t = Transport()
        mdl = kit_model.Model(opener=t)
        self.assertIs(mdl.route, kit_model.SPARK_META)
        self.assertIsNone(mdl.fallback)
        self.assertEqual((mdl.endpoint, mdl.model_id), (META_URL, "muse-spark-1.3"))
        mdl.chat(HI, effort="medium", max_tokens=900)
        self.assertEqual(t.hosts(), [META_URL])
        self.assertEqual(t.seen[0].get_header("Authorization"), "Bearer " + self.m)
        self.assertEqual(json.loads(t.seen[0].data), {"model": "muse-spark-1.3", "messages": HI,
                                                      "max_completion_tokens": 900, "reasoning_effort": "medium"})
        self.assertEqual((mdl.last_route, mdl.last_model), ("Meta", "muse-spark-1.3"))

    def test_meta_model_sets_the_meta_spark_id(self):
        env_with(self, META_API_KEY=self.m, META_MODEL="muse-spark-1.4")
        self.assertEqual(kit_model.Model().model_id, "muse-spark-1.4")

    def test_only_the_baseten_key_runs_on_baseten_with_no_fallback(self):
        env_with(self, BASETEN_API_KEY=self.b)
        t = Transport(baseten=[http_error(BASETEN_URL, 503)])
        mdl = kit_model.Model(opener=t)
        self.assertIs(mdl.route, kit_model.OPEN)
        self.assertIsNone(mdl.fallback)
        with self.assertRaises(kit_model.ModelError) as e:
            mdl.chat(HI)
        self.assertEqual(str(e.exception), "Baseten answered 503 Service Unavailable")
        self.assertEqual(t.hosts(), [BASETEN_URL])

    def test_both_keys_put_baseten_first_and_meta_as_the_fallback(self):
        env_with(self, BASETEN_API_KEY=self.b, META_API_KEY=self.m)
        t = Transport()
        mdl = kit_model.Model(opener=t)
        self.assertIs(mdl.route, kit_model.OPEN)
        self.assertEqual(mdl.fallback, kit_model.Leg(kit_model.SPARK_META, self.m, "muse-spark-1.3"))
        mdl.chat(HI)
        self.assertEqual(t.hosts(), [BASETEN_URL])
        self.assertEqual(t.seen[0].get_header("Authorization"), "Bearer " + self.b)
        self.assertEqual(mdl.last_route, "Baseten")

    def test_no_key_names_both_and_sends_nothing(self):
        for blank in ("", "   "):
            with self.subTest(blank=blank):
                env_with(self, BASETEN_API_KEY=blank, META_API_KEY=blank)
                t = Transport()
                self.assertFalse(kit_model.has_key())
                with self.assertRaises(kit_model.ModelError) as e:
                    kit_model.Model(opener=t).chat(HI)
                self.assertEqual(str(e.exception), kit_model.NO_KEY)
                self.assertEqual(t.seen, [])

    def test_a_key_given_in_code_or_another_route_pins_that_route(self):
        env_with(self, BASETEN_API_KEY=self.b, META_API_KEY=self.m)
        self.assertIsNone(kit_model.Model(api_key="k").fallback)
        self.assertIsNone(kit_model.Model(endpoint="https://example.invalid/v1").fallback)
        w = kit_model.Model(route=kit_model.WONDER)
        self.assertEqual((w.route, w.fallback), (kit_model.WONDER, None))


class Fallback(unittest.TestCase):
    def setUp(self):
        self.b, self.m = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        env_with(self, BASETEN_API_KEY=self.b, META_API_KEY=self.m)

    def test_timeout_network_5xx_and_429_send_the_same_call_to_meta(self):
        for label, err in (("timeout", TimeoutError("slow " + self.b)),
                           ("network", urllib.error.URLError("down " + self.b)),
                           ("reset", ConnectionResetError("reset")),
                           ("500", http_error(BASETEN_URL, 500)), ("502", http_error(BASETEN_URL, 502)),
                           ("503", http_error(BASETEN_URL, 503)), ("429", http_error(BASETEN_URL, 429))):
            with self.subTest(failure=label):
                t = Transport(baseten=[err], meta=[ok("from meta")])
                mdl = kit_model.Model(opener=t)
                with self.assertLogs("kit.model", level="ERROR") as logs:
                    out = mdl.chat(HI, tools=[{"type": "function", "function": {"name": "x"}}], max_tokens=700)
                self.assertEqual(out["content"], "from meta")
                self.assertEqual(t.hosts(), [BASETEN_URL, META_URL])
                self.assertEqual(t.seen[0].get_header("Authorization"), "Bearer " + self.b)
                self.assertEqual(t.seen[1].get_header("Authorization"), "Bearer " + self.m)
                first, second = json.loads(t.seen[0].data), json.loads(t.seen[1].data)
                self.assertEqual(second["model"], "muse-spark-1.3")
                self.assertEqual(second["max_completion_tokens"], 700)
                self.assertNotIn("max_tokens", second)
                self.assertEqual((first["messages"], first["tools"]), (second["messages"], second["tools"]))
                self.assertEqual(mdl.last_route, "Meta")
                line = "\n".join(logs.output)
                self.assertIn("this call goes to Meta", line)
                self.assertTrue(line.split(":", 2)[2].startswith("Baseten "), line)
                for secret in (self.b, self.m):
                    self.assertNotIn(secret, line)
                self.assertNotIn(str(len(self.b)), line.replace("429", "").replace("50", ""))

    def test_other_failures_do_not_fall_back(self):
        for label, step in (("400", http_error(BASETEN_URL, 400)), ("401", http_error(BASETEN_URL, 401)),
                            ("404", http_error(BASETEN_URL, 404)), ("redirect", http_error(BASETEN_URL, 302)),
                            ("not json", b"<html>"), ("no message", json.dumps({"x": 1}).encode()),
                            ("cut off", ok("half", reason="length"))):
            with self.subTest(failure=label):
                t = Transport(baseten=[step])
                with self.assertRaises(kit_model.ModelError) as e:
                    kit_model.Model(opener=t).chat(HI, whole=True)
                self.assertEqual(t.hosts(), [BASETEN_URL])
                self.assertTrue(str(e.exception).startswith("Baseten "))

    def test_both_failing_names_both_and_no_key(self):
        t = Transport(baseten=[http_error(BASETEN_URL, 503)], meta=[TimeoutError("slow " + self.m)])
        with self.assertRaises(kit_model.ModelError) as e, self.assertLogs("kit.model", level="ERROR"):
            kit_model.Model(opener=t).chat(HI)
        err = e.exception
        self.assertEqual(str(err), "Baseten answered 503 Service Unavailable; Meta call failed: TimeoutError")
        for text in (str(err), repr(err)):
            self.assertNotIn(self.b, text)
            self.assertNotIn(self.m, text)
        self.assertIsNone(err.__cause__)
        self.assertTrue(err.__suppress_context__ or err.__context__ is None)

    def test_the_fallback_never_follows_a_redirect(self):
        self.assertIs(kit_model.Model()._open, net.open_once)


def no_network(test):
    """Every way out to the network fails the test."""
    def refuse(*a, **k):
        raise AssertionError("the network was called")
    for target in ("kit.net.open_once", "urllib.request.urlopen", "socket.create_connection",
                   "socket.socket.connect", "socket.getaddrinfo"):
        p = mock.patch(target, refuse)
        p.start()
        test.addCleanup(p.stop)


class NoKey(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        env_with(self)
        p = mock.patch.object(kit_env, "load", return_value=[])  # a real .env must not count here
        p.start()
        self.addCleanup(p.stop)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_the_arena_prints_the_pointer_and_exits_cleanly(self):
        for argv in (["--quick", "--state", str(self.dir / "s")], ["--state", str(self.dir / "s")]):
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = run.main(argv)
                self.assertEqual(code, 2)
                self.assertEqual(err.getvalue(), kit_model.NO_KEY_LINE + "\n")
                self.assertEqual(out.getvalue(), "")
                self.assertIn("python3 -I recorded/play.py", kit_model.NO_KEY_LINE)
                self.assertEqual(list(self.dir.iterdir()), [])

    def test_the_recorder_prints_the_same_pointer(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(record.main(["--out", str(self.dir)]), 2)
        self.assertEqual(err.getvalue(), kit_model.NO_KEY_LINE + "\n")
        self.assertEqual(list(self.dir.iterdir()), [])


class EnvExample(unittest.TestCase):
    LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")

    def test_names_only_each_with_one_comment_line(self):
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        names = []
        for i, line in enumerate(lines):
            if not line.strip() or line.startswith("#"):
                continue
            m = self.LINE.match(line)
            self.assertIsNotNone(m, line)
            self.assertEqual(m.group(2), "", f"{m.group(1)} has a value")
            self.assertTrue(i > 0 and lines[i - 1].startswith("# ") and len(lines[i - 1]) > 4, m.group(1))
            self.assertTrue(i < 2 or not lines[i - 2].startswith("#"), f"{m.group(1)} has more than one comment line")
            names.append(m.group(1))
        self.assertEqual(names[:2], ["META_API_KEY", "BASETEN_API_KEY"])
        self.assertEqual(len(names), len(set(names)))

    def test_every_name_is_one_the_code_reads(self):
        """No stray name: each is a route's key or model env in kit/model.py."""
        known = {n for r in (kit_model.OPEN, kit_model.SPARK_META) for n in (r.key_env, r.model_env)}
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        self.assertEqual({x.split("=")[0] for x in lines if x and not x.startswith("#")}, known)

    def test_git_keeps_env_out_and_lets_the_example_in(self):
        if shutil.which("git") is None or not (ROOT / ".git").exists():
            self.skipTest("no git here")

        def ignored(name):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name],
                                  capture_output=True).returncode == 0
        self.assertTrue(ignored(".env"))
        self.assertFalse(ignored(".env.example"))
        self.assertFalse(ignored("recorded/arena-run.json"))
        self.assertFalse(ignored("recorded/sales-chat.json"))


class Replay(unittest.TestCase):
    def setUp(self):
        env_with(self)
        no_network(self)

    def play(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = play.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_the_shipped_recording_plays_with_no_key_and_no_network(self):
        code, out, err = self.play()
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("Recorded replay: no key and no network."))
        self.assertIn("Arena run (SCRIPTED, not a model run)", out)
        self.assertIn("Sales chat (SCRIPTED, not a model run)", out)
        self.assertIn("    customer: How much is the Mercurial Vapor 17 Elite?", out)
        self.assertIn("    agent:    ", out)

    def test_the_shipped_files_carry_their_provenance_and_say_scripted(self):
        for name, kind in ((record.ARENA_FILE, "arena"), (record.SALES_FILE, "sales")):
            with self.subTest(file=name):
                data = json.loads((ROOT / "recorded" / name).read_text(encoding="utf-8"))
                self.assertEqual((data["format"], data["kind"], data["scripted"]), (1, kind, True))
                self.assertTrue(data["label"].startswith("SCRIPTED"))
                self.assertEqual(data["command"], "python3 -I recorded/record.py --scripted")
                self.assertTrue(data["trace"])
                for t in data["trace"]:
                    self.assertTrue(all(t.get(f) for f in ("role", "route", "model", "started", "ended")), t)
                    self.assertIn("output", t)
                    self.assertTrue(t["route"] in ("scripted", "fixed"), t)
                self.assertNotIn("/Users/", json.dumps(data))

    def test_a_file_with_no_provenance_is_refused(self):
        data = json.loads((ROOT / "recorded" / record.SALES_FILE).read_text(encoding="utf-8"))
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for label, change in (("no trace", lambda x: x.pop("trace")), ("empty trace", lambda x: x.update(trace=[])),
                              ("no route", lambda x: x["trace"][0].pop("route")),
                              ("no answer", lambda x: x["trace"][0].pop("output")),
                              ("no scripted flag", lambda x: x.pop("scripted")),
                              ("wrong kind", lambda x: x.update(kind="arena"))):
            with self.subTest(label=label):
                bad = json.loads(json.dumps(data))
                change(bad)
                path = Path(d.name) / "bad.json"
                path.write_text(json.dumps(bad), encoding="utf-8")
                code, out, err = self.play("--sales", str(path))
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("Not run: bad.json "), err)


class Recorder(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_a_scripted_recording_writes_both_files_and_the_replay_plays_them(self):
        env_with(self)
        no_network(self)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(record.main(["--scripted", "--out", str(self.dir)]), 0)
        arena = json.loads((self.dir / record.ARENA_FILE).read_text(encoding="utf-8"))
        sales = json.loads((self.dir / record.SALES_FILE).read_text(encoding="utf-8"))
        self.assertTrue(arena["scripted"] and sales["scripted"])
        self.assertEqual(len(arena["report"]["rounds"]), 1)
        self.assertEqual(len(arena["matches"]), 2)  # one training match, a gate of one
        self.assertEqual(sales["chat"]["ended"], "order")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = play.main(["--arena", str(self.dir / record.ARENA_FILE), "--sales", str(self.dir / record.SALES_FILE)])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().count("SCRIPTED, not a model run"), 2)

    def test_a_real_recording_traces_the_route_and_model_of_each_call(self):
        """kit/model.py Model behind a fake transport: Baseten fails once, Meta answers that call."""
        b, m = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        env_with(self, BASETEN_API_KEY=b, META_API_KEY=m)
        seller = Seller()

        def answer(req, timeout):
            body = json.loads(req.data)
            out = seller.chat(body["messages"], tools=body.get("tools"))
            return Resp(json.dumps({"choices": [{"message": out}]}).encode())
        down = [http_error(BASETEN_URL, 503)]  # Baseten fails the first call only

        def opener(req, timeout):
            if req.full_url == BASETEN_URL and down:
                raise down.pop()
            return answer(req, timeout)
        with self.assertLogs("kit.model", level="ERROR"):
            data = record.record_sales(kit_model.Model(opener=opener), scripted=False)
        self.assertFalse(data["scripted"])
        self.assertEqual(data["label"], record.REAL_LABEL)
        routes = [(x["route"], x["model"]) for x in data["trace"]]
        self.assertEqual(routes[0], ("Meta", "muse-spark-1.3"))
        self.assertEqual(set(routes[1:]), {("Baseten", "meta-models/muse-spark-open-1026")})
        self.assertNotIn(b, json.dumps(data))
        self.assertNotIn(m, json.dumps(data))


class Quick(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def main(self, argv, agent=None, customer=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = run.main(argv + ["--json"], agent_model=agent or Seller(), customer_model=customer or Buyer())
        return code, json.loads(out.getvalue())

    def test_quick_is_one_round_one_training_match_and_a_gate_of_one(self):
        code, rep = self.main(["--quick", "--state", str(self.dir), "--matches", "9", "--rounds", "4"])
        self.assertEqual((code, rep["stopped"]), (0, run.PASSED))
        self.assertEqual(rep["trust"], run.QUICK_TRUST)
        self.assertEqual(len(rep["rounds"]), 1)
        self.assertEqual((rep["rounds"][0]["training"]["played"], rep["rounds"][0]["gate"]["played"]), (1, 1))
        self.assertEqual(rep["calls"]["run_limit"], run.QUICK_CALLS)
        self.assertLessEqual(rep["calls"]["run_used"], run.QUICK_CALLS)

    def test_quick_caps_the_calls_of_the_run(self):
        class Talker:
            """A customer that never leaves and never buys, so only the limit ends the run."""
            calls = 0

            def chat(self, *a, **k):
                Talker.calls += 1
                return say("and in blue?")
        agent = Seller()
        with mock.patch.object(run, "QUICK_CALLS", 5):
            code, rep = self.main(["--quick", "--state", str(self.dir)], agent=agent, customer=Talker())
        self.assertEqual((code, rep["stopped"]), (1, run.CAP))
        self.assertEqual((rep["calls"]["run_used"], rep["calls"]["run_limit"]), (5, 5))
        self.assertEqual(Talker.calls + len(agent.calls), 5)
        self.assertEqual(json.loads((self.dir / run.CALLS_FILE).read_text(encoding="utf-8"))["calls"], 5)

    def test_the_run_limit_is_on_top_of_the_day_cap(self):
        c = run.Calls(self.dir / "c.json", 100, day="2026-10-31", limit=2)
        c.take()
        c.take()
        with self.assertRaises(run.CapReached) as e:
            c.take()
        self.assertEqual(str(e.exception), "the run's limit of 2 model calls is reached")
        self.assertTrue(c.reached)
        other = run.Calls(self.dir / "c.json", 100, day="2026-10-31")
        other.take()  # the day's cap still has room for another run
        self.assertEqual(other.count, 3)

    def test_quick_with_no_folder_uses_the_ignored_data_folder(self):
        target = self.dir / "arena-quick"
        with mock.patch.object(run, "QUICK_STATE", target):
            code, rep = self.main(["--quick"])
        self.assertEqual(code, 0)
        self.assertTrue((target / run.MATCHES_FILE).is_file())
        self.assertEqual(run.QUICK_STATE, ROOT / "data" / "arena-quick")

    def test_the_text_report_names_the_run_limit(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            run.main(["--quick", "--state", str(self.dir)], agent_model=Seller(), customer_model=Buyer())
        self.assertRegex(out.getvalue(), r"quick run: \d+ of at most 40 model calls in this run")


if __name__ == "__main__":
    unittest.main()
