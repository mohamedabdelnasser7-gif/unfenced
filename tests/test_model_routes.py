"""kit/model.py's two routes: OPEN (Muse Spark Open on Baseten, the default for everything) and
WONDER (Muse Wonder on the Meta Model API, for the night study's proposer and tagger). Each
route reads its own key and model id from env and sends its key to its own host only. WONDER
never sends reasoning_effort "none" or logprobs (both answer HTTP 400). No error ever holds a
key. No test touches the network; every key here is a random stand-in."""
import io
import json
import os
import secrets
import unittest
import urllib.error
from unittest import mock

from kit import model as kit_model
from kit import net

BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"
META_URL = "https://api.meta.ai/v1/chat/completions"
OUR_ENV = ("BASETEN_API_KEY", "BASETEN_MODEL", "META_API_KEY", "META_STUDY_MODEL", "META_STUDY_ROUTE", "BOSTA_API_KEY")
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


class Recorder:
    """Stands in for the network: keeps each request and answers with one message."""

    def __init__(self, content="ok", error=None, payload=None):
        self.seen = []
        self.error = error
        self.payload = payload if payload is not None else json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()

    def __call__(self, req, timeout):
        self.seen.append(req)
        if self.error is not None:
            raise self.error
        return Resp(self.payload)

    def body(self, n=0):
        return json.loads(self.seen[n].data)


class Routes(unittest.TestCase):
    def setUp(self):
        self.baseten_key = secrets.token_urlsafe(24)
        self.meta_key = secrets.token_urlsafe(24)

    def test_open_is_still_the_default(self):
        env_with(self, BASETEN_API_KEY=self.baseten_key, META_API_KEY=self.meta_key)
        rec = Recorder()
        m = kit_model.Model(opener=rec)
        self.assertIs(m.route, kit_model.OPEN)
        self.assertEqual((m.endpoint, m.model_id), (BASETEN_URL, "meta-models/muse-spark-open-1026"))
        m.chat(HI)
        self.assertEqual(rec.seen[0].full_url, BASETEN_URL)
        self.assertEqual(rec.seen[0].get_header("Authorization"), "Bearer " + self.baseten_key)
        self.assertEqual(rec.body()["max_tokens"], 1500)
        self.assertNotIn("max_completion_tokens", rec.body())

    def test_the_wonder_route_names_the_meta_api_and_the_wonder_id(self):
        self.assertEqual(kit_model.WONDER.endpoint, META_URL)
        self.assertEqual((kit_model.WONDER.key_env, kit_model.WONDER.model_env), ("META_API_KEY", "META_STUDY_MODEL"))
        env_with(self, BASETEN_API_KEY=self.baseten_key, META_API_KEY=self.meta_key,
                 BASETEN_MODEL="meta-models/muse-spark-open")
        rec = Recorder()
        m = kit_model.Model(route=kit_model.WONDER, opener=rec)
        self.assertEqual((m.endpoint, m.model_id), (META_URL, "muse-wonder-1.0"))
        m.chat(HI, effort=kit_model.EFFORT_STUDY, max_tokens=4000)
        req, body = rec.seen[0], rec.body()
        self.assertEqual((req.full_url, req.get_method()), (META_URL, "POST"))
        self.assertEqual(req.get_header("Authorization"), "Bearer " + self.meta_key)
        self.assertEqual(body, {"model": "muse-wonder-1.0", "messages": HI, "max_completion_tokens": 4000,
                                "reasoning_effort": "high"})

    def test_meta_study_model_sets_the_wonder_id_only(self):
        env_with(self, META_STUDY_MODEL="muse-wonder-1.1")
        self.assertEqual(kit_model.Model(route=kit_model.WONDER).model_id, "muse-wonder-1.1")
        self.assertEqual(kit_model.Model().model_id, kit_model.DEFAULT_MODEL)

    def test_each_route_sends_its_own_key_to_its_own_host(self):
        env_with(self, BASETEN_API_KEY=self.baseten_key, META_API_KEY=self.meta_key)
        for route, url, key in ((kit_model.OPEN, BASETEN_URL, self.baseten_key),
                                (kit_model.WONDER, META_URL, self.meta_key)):
            with self.subTest(route=route.name):
                rec = Recorder()
                kit_model.Model(route=route, opener=rec).chat(HI, effort="high")
                self.assertEqual(rec.seen[0].full_url, url)
                self.assertEqual(rec.seen[0].get_header("Authorization"), "Bearer " + key)

    def test_the_wonder_call_never_follows_a_redirect(self):
        env_with(self)
        self.assertIs(kit_model.Model(route=kit_model.WONDER)._open, net.open_once)


class MissingKey(unittest.TestCase):
    def test_a_missing_meta_key_names_the_variable_and_sends_nothing(self):
        other = secrets.token_urlsafe(24)
        for blank in (None, "", "   "):
            with self.subTest(meta_api_key=blank):
                extra = {} if blank is None else {"META_API_KEY": blank}
                env_with(self, BASETEN_API_KEY=other, META_STUDY_MODEL="muse-wonder-1.0", **extra)
                rec = Recorder()
                with self.assertRaises(kit_model.ModelError) as e:
                    kit_model.Model(route=kit_model.WONDER, opener=rec).chat(HI, effort="high")
                self.assertEqual(str(e.exception), "META_API_KEY is not set")
                self.assertNotIn(other, str(e.exception))
                self.assertEqual(rec.seen, [])

    def test_a_missing_baseten_key_still_names_its_own_variable(self):
        """With a Meta key the default call now goes to Muse Spark on the Meta API (DECISIONS item
        33; tests/test_judge_keys.py). An empty key given in code still names Baseten's variable."""
        env_with(self, META_API_KEY=secrets.token_urlsafe(24))
        rec = Recorder()
        with self.assertRaises(kit_model.ModelError) as e:
            kit_model.Model(api_key="", opener=rec).chat(HI)
        self.assertEqual(str(e.exception), "BASETEN_API_KEY is not set")
        self.assertEqual(rec.seen, [])


class WonderBody(unittest.TestCase):
    """Meta's reasoning page: effort "none" and logprobs answer HTTP 400."""

    def setUp(self):
        env_with(self, META_API_KEY=secrets.token_urlsafe(24))

    def test_low_medium_and_high_go_and_nothing_else_is_sent(self):
        tools = [{"type": "function", "function": {"name": "store"}}]
        for effort in ("low", "medium", "high"):
            with self.subTest(effort=effort):
                rec = Recorder()
                kit_model.Model(route=kit_model.WONDER, opener=rec).chat(HI, tools=tools, effort=effort)
                body = rec.body()
                self.assertEqual(body["reasoning_effort"], effort)
                self.assertEqual(set(body), {"model", "messages", "max_completion_tokens", "reasoning_effort",
                                             "tools", "tool_choice"})
                self.assertEqual(body["tool_choice"], "auto")
                self.assertNotIn("logprobs", body)
                self.assertNotIn("top_logprobs", body)

    def test_effort_none_or_anything_odd_is_refused_before_sending(self):
        for effort in ("none", "None", "NONE", " none", "", None, "off", "xlow"):
            with self.subTest(effort=effort):
                rec = Recorder()
                m = kit_model.Model(route=kit_model.WONDER, opener=rec)
                with self.assertRaises(kit_model.ModelError) as e:
                    m.chat(HI, effort=effort)
                self.assertEqual(str(e.exception), "Meta takes reasoning effort low, medium, high only")
                self.assertEqual(rec.seen, [])
                with self.assertRaises(kit_model.ModelError):
                    m.body(HI, effort=effort)


class NoKeyInErrors(unittest.TestCase):
    """Whatever fails, and wherever the key shows up in what failed, the ModelError holds no key."""

    def http_error(self, url, code, msg, headers, body):
        err = urllib.error.HTTPError(url, code, msg, headers, io.BytesIO(body))
        self.addCleanup(err.close)
        return err

    def failures(self, key, url):
        echo = ('{"error": {"message": "bad", "echo": "Bearer ' + key + '"}}').encode()
        return [
            ("http 400", Recorder(error=self.http_error(url, 400, "Bad " + key, {}, echo))),
            ("http 401", Recorder(error=self.http_error(url, 401, key, {"X-Key": key}, echo))),
            ("http odd", Recorder(error=self.http_error(url, 599, key, {}, b""))),
            ("url error", Recorder(error=urllib.error.URLError("refused " + key))),
            ("timeout", Recorder(error=TimeoutError("slow " + key))),
            ("not json", Recorder(payload=("Bearer " + key).encode())),
            ("no message", Recorder(payload=json.dumps({"echo": key}).encode())),
        ]

    def test_no_key_value_can_appear_in_a_model_error(self):
        key, other = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        for route, url in ((kit_model.WONDER, META_URL), (kit_model.OPEN, BASETEN_URL)):
            env_with(self, META_API_KEY=key if route is kit_model.WONDER else other,
                     BASETEN_API_KEY=key if route is kit_model.OPEN else other)
            cases = self.failures(key, url)
            if route is kit_model.WONDER:  # Baseten's efforts are not checked here
                cases.append(("effort none", Recorder()))
            for label, rec in cases:
                with self.subTest(route=route.name, failure=label):
                    with self.assertRaises(kit_model.ModelError) as e:
                        kit_model.Model(route=route, opener=rec).chat(HI, effort="none" if label == "effort none" else "high")
                    err = e.exception
                    for text in (str(err), repr(err), *map(str, err.args)):
                        self.assertNotIn(key, text)
                        self.assertNotIn(other, text)
                    self.assertIsNone(err.__cause__)
                    self.assertTrue(err.__suppress_context__ or err.__context__ is None)
                    self.assertTrue(str(err).startswith(route.name + " "))

    def test_meta_errors_name_meta_and_only_the_status(self):
        key = secrets.token_urlsafe(24)
        env_with(self, META_API_KEY=key)
        rec = Recorder(error=self.http_error(META_URL, 400, "Bad Request " + key, {}, b"{}"))
        with self.assertRaises(kit_model.ModelError) as e:
            kit_model.Model(route=kit_model.WONDER, opener=rec).chat(HI, effort="high")
        self.assertEqual(str(e.exception), "Meta answered 400 Bad Request")


if __name__ == "__main__":
    unittest.main()
