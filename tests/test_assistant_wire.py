"""The assistant's new mode step wired into Reflection (new, 2026-10-31): the night writes the
card's path into its report, the Morning page shows the open card, an answer from the page's
own form reaches newmode.answer_card, and a card named by a path from the form is refused.
No model, no network beyond 127.0.0.1."""
import contextlib
import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from assistant import PLUG, newmode
from kit.db import Db
from kit.model import ModelError
from reflection import morning as mod
from reflection import night

NOW = 1_800_000_000.0
PLUG_PATH = Path(__file__).resolve().parent.parent / "assistant" / "plug.json"
TRAVEL = [{"said": s, "date": d} for s, d in (("at the airport, travelling all day", "2026-11-02"),
                                               ("travelling again today", "2026-11-05"),
                                               ("still travelling, short replies", "2026-11-09"))]
CAND = {"name": "travell", "words": ["travelling"], "moments": 3, "days": 3}
COUNTS = {"days": 2, "without": 0, "with": 2, "fixed": 2, "broken": 0, "passed": True}


def folder(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name)


class Night(unittest.TestCase):
    """main() for the assistant's plug, with the night study itself stood in: the step after it."""

    def setUp(self):
        self.dir, self.state = folder(self), folder(self)
        self.db_path = self.dir / "agent.db"
        Db(self.db_path).close()
        newmode.keep_moments(self.state, TRAVEL)
        (self.state / "assistant-days.json").write_text(json.dumps({"real": [{"day": 1}, {"day": 2}]}), encoding="utf-8")
        rep = {"agent": "assistant", "window": {"since": NOW - 86400, "until": NOW}, "snapshot": {}}
        for p in (mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]),
                  mock.patch.object(night, "night", return_value=rep), mock.patch("kit.model.Model")):
            p.start()
            self.addCleanup(p.stop)

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = night.main(["--plug", str(PLUG_PATH), "--db", str(self.db_path), "--json",
                               "--assistant-state", str(self.state)])
        self.assertEqual(code, 0, err.getvalue())
        saved = sorted(self.dir.glob("night-assistant-*.json"))
        self.assertEqual(len(saved), 1)
        return json.loads(saved[0].read_text(encoding="utf-8"))

    def test_the_night_writes_the_card_path_into_the_report(self):
        with mock.patch("assistant.arena.play_day", side_effect=lambda day, model, added: (None, None, {"won": bool(added)})):
            rep = self.run_main()
        card = Path(rep["mode_card"])
        self.assertEqual(card.parent, self.dir.resolve())
        self.assertEqual(newmode.open_cards(self.dir.resolve()), [card])
        self.assertEqual(json.loads(card.read_text(encoding="utf-8"))["name"], "travell")

    def test_a_model_that_does_not_answer_stops_the_step_with_no_card(self):
        with mock.patch("assistant.arena.play_day", side_effect=ModelError("no answer")):
            rep = self.run_main()
        self.assertIsNone(rep["mode_card"])
        self.assertEqual(rep["mode_card_stopped"], "ModelError")
        self.assertEqual(newmode.open_cards(self.dir), [])


class Page(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.dir, self.state, self.elsewhere = folder(self), folder(self), folder(self)
        self.card = newmode.write_card(self.dir, CAND, COUNTS, now=NOW)
        self.morning = mod.Morning(self.db, [PLUG], reports=self.dir, modes_state=self.state)

    def test_the_morning_view_shows_the_open_card(self):
        mine = next(a for a in self.morning.view(NOW)["agents"] if a["agent"] == "assistant")
        self.assertEqual((mine["mode_card"]["file"], mine["mode_card"]["name"]), (self.card.name, "travell"))
        self.assertEqual((mine["mode_card"]["fixed"], mine["mode_card"]["broken"]), (2, 0))
        page = mod.render(self.morning.view(NOW), token="t0ken")
        self.assertIn("A new mode?", page)
        self.assertIn('action="/mode"', page)
        self.assertIn(f'name="card" value="{self.card.name}"', page)
        self.assertNotIn('action="/mode"', mod.render(self.morning.view(NOW), token=None))  # the static copy

    def test_an_answered_card_is_not_shown(self):
        self.morning.answer_mode("assistant", self.card.name, "drop")
        mine = [a for a in self.morning.view(NOW)["agents"] if a["agent"] == "assistant"]
        self.assertTrue(all(a["mode_card"] is None for a in mine))


class Server(Page):
    def setUp(self):
        super().setUp()
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

    def post(self, card, choice="yes", *, token=None, **extra):
        fields = dict({"token": self.server.token if token is None else token, "agent": "assistant", "card": card,
                       "choice": choice}, **extra)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", "/mode", urllib.parse.urlencode(fields),
                         {"Host": self.here, "Origin": f"http://{self.here}",
                          "Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            r.read()
            return r.status
        finally:
            conn.close()

    def test_a_post_answer_reaches_answer_card(self):
        with mock.patch("assistant.newmode.answer_card", wraps=newmode.answer_card) as answer:
            self.assertEqual(self.post(self.card.name, "rename", name="Travel"), 303)
        answer.assert_called_once()
        self.assertEqual(answer.call_args.args[:3], (self.card, self.state, "rename"))
        self.assertEqual(answer.call_args.kwargs, {"name": "Travel", "by": mod.BY})
        self.assertEqual(newmode.read_modes(self.state)["added"], [{"name": "travel", "words": ["travelling"]}])
        self.assertEqual(newmode.open_cards(self.dir), [])

    def test_a_post_with_a_forged_path_is_refused(self):
        other = newmode.write_card(self.elsewhere, CAND, COUNTS, now=NOW)  # an open card outside the page's folder
        forged = (str(other), f"../{self.elsewhere.name}/{other.name}", str(self.card), f"./{self.card.name}")
        with mock.patch("assistant.newmode.answer_card", wraps=newmode.answer_card) as answer:
            for card in forged:
                self.assertEqual(self.post(card), 303)
            self.assertEqual(self.post(self.card.name, token="wrong"), 403)  # the page's checks stay in front
        answer.assert_not_called()
        self.assertEqual(newmode.open_cards(self.elsewhere), [other])
        self.assertEqual(newmode.open_cards(self.dir), [self.card])
        self.assertFalse((self.state / newmode.MODES_FILE).exists())


if __name__ == "__main__":
    unittest.main()
