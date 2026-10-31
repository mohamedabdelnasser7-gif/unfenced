"""Which model each night study part asks (reflection/study.py). The proposer and the tagger take
the study route: Muse Wonder on the Meta Model API by default, Muse Spark Open on Baseten with
META_STUDY_ROUTE=open. The fit check, the adapter and the judge stay on Spark Open. A missing
key or a bad route value makes no lesson. No test touches the network; every key here is a
random stand-in."""
import json
import secrets
import unittest
import urllib.error
from unittest import mock

from engine import risk
from engine.lessons import Lessons
from engine.log import Log
from engine.study import Study
from kit import model as kit_model
from kit.db import Db
from reflection import judge as judge_mod
from reflection import study as model_study
from tests import plugs
from tests import study_fakes as fk
from tests.test_model_routes import BASETEN_URL, META_URL, Recorder, Resp, env_with

WONDER_PARTS = (model_study.Proposer, model_study.Tagger)
OPEN_PARTS = (model_study.FitCheck, model_study.Adapter, judge_mod.Judge)


def always_low(text, high_about, low_about):
    return risk.LOW


class Network:
    """Stands in for kit.net.open_once: answers the proposer and the tagger like a model would
    and keeps each request's url, key header and body."""

    def __init__(self):
        self.seen = []

    def __call__(self, req, timeout):
        body = json.loads(req.data)
        self.seen.append((req.full_url, req.get_header("Authorization"), body))
        system, data = body["messages"][0]["content"], json.loads(body["messages"][1]["content"])
        if system.startswith("You study"):
            content = json.dumps([fk.EARLY])
        elif "cases" in data:
            content = json.dumps({v["id"]: "yes" if v["steps"][0]["detail"]["early"] else "no" for v in data["cases"]})
        else:  # the fit check
            content = "not"
        return Resp(json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode())


class Setup(unittest.TestCase):
    def setUp(self):
        self.baseten_key = secrets.token_urlsafe(24)
        self.meta_key = secrets.token_urlsafe(24)
        self.waterer = plugs.load(plugs.WATERER, self)

    def env(self, **values):
        env_with(self, BASETEN_API_KEY=self.baseten_key, META_API_KEY=self.meta_key, **values)

    def network(self, net):
        p = mock.patch("kit.net.open_once", net)
        p.start()
        self.addCleanup(p.stop)
        return net

    def night(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        fk.beds(Log(db, self.waterer))
        lessons = Lessons(db, self.waterer, judge=always_low)
        rep = Study(db, self.waterer, proposer=model_study.Proposer(), tagger=model_study.Tagger(),
                    lessons=lessons).run(fk.SINCE, fk.UNTIL, now=fk.NOW)
        return rep, lessons


class TheSplit(Setup):
    def test_the_proposer_and_the_tagger_ask_muse_wonder_on_the_meta_api(self):
        self.env(BASETEN_MODEL="meta-models/muse-spark-open")
        for part in WONDER_PARTS:
            with self.subTest(part=part.__name__):
                m = part().model
                self.assertIs(m.route, kit_model.WONDER)
                self.assertEqual((m.endpoint, m.model_id), (META_URL, "muse-wonder-1.0"))
                self.assertEqual(m.timeout, model_study.TIMEOUT)

    def test_meta_study_model_names_the_wonder_id_for_those_two_only(self):
        self.env(META_STUDY_MODEL="muse-wonder-1.1")
        for part in WONDER_PARTS:
            self.assertEqual(part().model.model_id, "muse-wonder-1.1")
        for part in OPEN_PARTS:
            self.assertEqual(part().model.model_id, kit_model.DEFAULT_MODEL)

    def test_the_fit_check_the_adapter_and_the_judge_stay_on_spark_open(self):
        for flag in (None, "wonder", "open"):
            self.env(**({} if flag is None else {"META_STUDY_ROUTE": flag}))
            for part in OPEN_PARTS:
                with self.subTest(flag=flag, part=part.__name__):
                    m = part().model
                    self.assertIs(m.route, kit_model.OPEN)
                    self.assertEqual((m.endpoint, m.model_id), (BASETEN_URL, kit_model.DEFAULT_MODEL))

    def test_each_call_carries_its_own_routes_key_to_its_own_host(self):
        self.env()
        net = self.network(Network())
        model_study.Proposer()(self.waterer, [{"id": "k1", "steps": []}], 3, [])
        model_study.FitCheck()(self.waterer, self.waterer, fk.EARLY)
        (url_p, auth_p, body_p), (url_f, auth_f, body_f) = net.seen
        self.assertEqual((url_p, auth_p), (META_URL, "Bearer " + self.meta_key))
        self.assertEqual((url_f, auth_f), (BASETEN_URL, "Bearer " + self.baseten_key))
        self.assertEqual(body_p["model"], "muse-wonder-1.0")
        self.assertEqual(body_p["reasoning_effort"], "high")
        self.assertEqual(body_p["max_completion_tokens"], model_study.MAX_TOKENS)
        self.assertNotIn("logprobs", body_p)
        self.assertEqual(body_f["model"], kit_model.DEFAULT_MODEL)


class TheFlag(Setup):
    def test_open_puts_the_study_back_on_spark_open(self):
        for flag in ("open", "OPEN", " Open "):
            self.env(META_STUDY_ROUTE=flag)
            for part in WONDER_PARTS:
                with self.subTest(flag=flag, part=part.__name__):
                    m = part().model
                    self.assertIs(m.route, kit_model.OPEN)
                    self.assertEqual((m.endpoint, m.model_id), (BASETEN_URL, kit_model.DEFAULT_MODEL))

    def test_wonder_or_unset_is_wonder(self):
        for flag in (None, "", "wonder", "Wonder"):
            self.env(**({} if flag is None else {"META_STUDY_ROUTE": flag}))
            with self.subTest(flag=flag):
                self.assertIs(model_study.Proposer().model.route, kit_model.WONDER)
                self.assertIs(model_study.study_route(), kit_model.WONDER)

    def test_the_whole_night_follows_the_flag(self):
        for flag, url, key in ((None, META_URL, "meta_key"), ("open", BASETEN_URL, "baseten_key")):
            with self.subTest(flag=flag):
                self.env(**({} if flag is None else {"META_STUDY_ROUTE": flag}))
                net = self.network(Network())
                rep, lessons = self.night()
                self.assertEqual([c["change"] for c in rep["cards"]], [fk.EARLY["lesson"]])
                self.assertEqual(lessons.get(rep["cards"][0]["lesson_id"])["state"], "trying")
                self.assertGreater(len(net.seen), 1)
                self.assertEqual({(u, a) for u, a, _ in net.seen}, {(url, "Bearer " + getattr(self, key))})

    def test_any_other_value_makes_no_model_and_no_lesson(self):
        for flag in ("opn", "spark", "baseten", "wonder open"):
            self.env(META_STUDY_ROUTE=flag)
            net = self.network(Recorder())
            with self.subTest(flag=flag):
                with self.assertRaises(kit_model.ModelError) as e:
                    model_study.Tagger().model
                self.assertEqual(str(e.exception), "META_STUDY_ROUTE must be wonder or open")
                rep, _ = self.night()
                self.assertEqual(rep["cards"], [])
                self.assertEqual(net.seen, [])
                self.assertIn("waterer: the proposer failed (PartError: META_STUDY_ROUTE must be wonder or open); "
                              "no candidates", rep["notes"])
                self.assertEqual(rep["parts"]["proposer"], "no model: META_STUDY_ROUTE must be wonder or open")


class NoKeyNoLesson(Setup):
    def test_a_missing_meta_key_makes_no_lesson_and_sends_nothing(self):
        env_with(self, BASETEN_API_KEY=self.baseten_key)
        net = self.network(Recorder())
        with self.assertRaises(kit_model.ModelError) as e:
            model_study.Proposer().model.chat([], effort=model_study.EFFORT)
        self.assertEqual(str(e.exception), "META_API_KEY is not set")
        self.assertNotIn(self.baseten_key, str(e.exception))
        rep, _ = self.night()
        self.assertEqual(rep["cards"], [])
        self.assertEqual(net.seen, [])
        self.assertIn("waterer: the proposer failed (PartError: META_API_KEY is not set); no candidates", rep["notes"])
        self.assertNotIn(self.baseten_key, json.dumps(rep))

    def test_a_refused_call_is_named_in_the_notes(self):
        self.env()

        def refuse(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        self.network(refuse)
        rep, _ = self.night()
        self.assertEqual(rep["cards"], [])
        self.assertIn("waterer: the proposer failed (PartError: Meta answered 401 Unauthorized); no candidates",
                      rep["notes"])
        self.assertNotIn(self.meta_key, json.dumps(rep))


    def test_an_answer_cut_off_at_the_token_limit_is_named(self):
        self.env()
        cut = json.dumps({"choices": [{"message": {"role": "assistant", "content": "[{\"pattern\""},
                                       "finish_reason": "length"}]}).encode()
        self.network(Recorder(payload=cut))
        rep, _ = self.night()
        self.assertEqual(rep["cards"], [])
        self.assertIn(f"waterer: the proposer failed (PartError: Meta answer was cut off at {model_study.MAX_TOKENS} "
                      "tokens); no candidates", rep["notes"])
        # outside the study a cut answer is still an answer
        got = kit_model.Model(route=kit_model.WONDER).chat([], effort="high")
        self.assertEqual(got["content"], "[{\"pattern\"")

    def test_an_answer_stopped_by_the_content_filter_is_named(self):
        self.env()
        cut = json.dumps({"choices": [{"message": {"role": "assistant", "content": ""},
                                       "finish_reason": "content_filter"}]}).encode()
        self.network(Recorder(payload=cut))
        rep, _ = self.night()
        self.assertEqual(rep["cards"], [])
        self.assertIn("waterer: the proposer failed (PartError: Meta answer was stopped by its content filter); "
                      "no candidates", rep["notes"])


class TheReport(Setup):
    def test_the_night_names_the_host_and_model_of_each_part(self):
        for flag, want in ((None, "Meta muse-wonder-1.0"), ("open", f"Baseten {kit_model.DEFAULT_MODEL}")):
            with self.subTest(flag=flag):
                self.env(**({} if flag is None else {"META_STUDY_ROUTE": flag}))
                self.network(Network())
                rep, _ = self.night()
                self.assertEqual(rep["parts"], {"proposer": want, "tagger": want})


if __name__ == "__main__":
    unittest.main()
