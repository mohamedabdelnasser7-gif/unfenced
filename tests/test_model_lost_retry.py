"""A model call that got no answer at all (a timeout, a network failure, a 5xx or a 429) is asked once more,
counted like the empty answer's second ask (kit/model.py, 2026-11-04: a live run on the Meta key alone dropped
a match on one such failure). A fake transport only, no network."""
import json
import secrets
import socket
import unittest
import urllib.error

from kit import model as kit_model
from tests.test_judge_keys import BASETEN_URL, HI, META_URL, Transport, env_with, ok


def http_error(code):
    return urllib.error.HTTPError(META_URL, code, "x", {}, None)


class LostCallAskedOnce(unittest.TestCase):
    def setUp(self):
        env_with(self, META_API_KEY=secrets.token_urlsafe(24))

    def model(self, *steps):
        t = Transport(meta=list(steps))
        return kit_model.Model(opener=t), t

    def test_a_timeout_once_then_an_answer_is_returned_and_counted(self):
        m, t = self.model(socket.timeout("timed out"), ok("hello"))
        taken = []
        with kit_model.counting(lambda: taken.append(1)), self.assertLogs("kit.model", level="WARNING") as logs:
            got = m.chat(HI, max_tokens=900)
        self.assertEqual(got["content"], "hello")
        self.assertEqual(t.hosts(), [META_URL, META_URL])
        self.assertEqual([json.loads(r.data)["max_completion_tokens"] for r in t.seen], [900, 900])
        self.assertEqual(taken, [1])
        self.assertIn("asked once more", logs.output[0])
        self.assertEqual(m.last_route, "Meta")

    def test_a_network_failure_and_a_busy_host_are_asked_once_more(self):
        for first in (urllib.error.URLError("reset"), ConnectionResetError(), http_error(503), http_error(429)):
            with self.subTest(first=first):
                m, t = self.model(first, ok("hello"))
                with self.assertLogs("kit.model", level="WARNING"):
                    self.assertEqual(m.chat(HI)["content"], "hello")
                self.assertEqual(len(t.seen), 2)

    def test_lost_twice_raises_naming_both_and_asks_only_twice(self):
        m, t = self.model(socket.timeout(), socket.timeout(), ok("never asked"))
        with self.assertLogs("kit.model", level="WARNING"), self.assertRaises(kit_model.ModelError) as e:
            m.chat(HI)
        self.assertEqual(len(t.seen), 2)
        self.assertIn("asked once more", str(e.exception))

    def test_a_refused_count_stops_the_second_ask(self):
        m, t = self.model(socket.timeout(), ok("never asked"))

        def full():
            raise RuntimeError("the cap is reached")
        with kit_model.counting(full), self.assertRaises(RuntimeError):
            m.chat(HI)
        self.assertEqual(len(t.seen), 1)

    def test_a_4xx_is_not_asked_again(self):
        m, t = self.model(http_error(400), ok("never asked"))
        with self.assertRaises(kit_model.ModelError):
            m.chat(HI)
        self.assertEqual(len(t.seen), 1)


class WithAFallback(unittest.TestCase):
    def test_both_hosts_lost_then_the_chain_is_asked_once_more(self):
        env_with(self, BASETEN_API_KEY=secrets.token_urlsafe(24), META_API_KEY=secrets.token_urlsafe(24))
        t = Transport(baseten=[socket.timeout(), ok("hello")], meta=[socket.timeout()])
        m = kit_model.Model(opener=t)
        with self.assertLogs("kit.model", level="WARNING"):
            self.assertEqual(m.chat(HI)["content"], "hello")
        self.assertEqual(t.hosts(), [BASETEN_URL, META_URL, BASETEN_URL])


if __name__ == "__main__":
    unittest.main()
