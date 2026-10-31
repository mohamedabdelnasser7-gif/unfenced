"""Task t261029s: one chain from a reply to a new lesson, each link checked. Twelve chats each
get a reply through the WhatsApp App with a team-kept lesson, then an order with its COD
risk, then Bosta's delivered or refused through the delivery webhook. The night study finds
that the high risk orders were mostly refused and writes one lesson, and the night's links
name the chats behind it. The Sales plug decides a case on order_created and only records
delivered and refused, so the study runs under the Sales plug as a brand with a delivery source
could run it (delivered good, refused bad), as tests/test_importer.py does. Fakes only: no
network, no repo database, no .env."""
import itertools
import json
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from channels import bosta
from channels import whatsapp as wa
from engine import plug as plug_mod
from kit.chats import Chats
from kit.db import Db
from kit.limits import Limits
from reflection import PLUG as SALES
from reflection import night
from reflection.judge import Judge
from reflection.lessons import Lessons
from reflection.results import Results
from tests import study_fakes as fk
from tests.fake_model import FakeModel, Outbox, clean_env, say
from tests.test_whatsapp import payload, text_msg
from tests.kept import kept_lesson

TONE = "Greet them warmly before anything else."
HIGH = "the order's COD risk was high"
LESSON = "When the risk check marks an order high, ask for a clear yes again before closing it."
CHATS = 12
REFUSED = {1, 2, 3, 4, 5, 12}  # five of the six high risk orders, one of the six low risk ones
STAMP = 1_761_700_000_000
ROOT = Path(__file__).resolve().parent.parent


def delivery_plug():
    """The Sales plug with delivered deciding good and refused bad; everything else as it is."""
    d = json.loads((ROOT / "sales" / "plug.json").read_text(encoding="utf-8"))
    d["decides"] = {"good": "delivered", "bad": ["refused"]}
    return plug_mod.from_dict(d, folder=ROOT / "sales")


def by_risk(plug, pattern, cases):
    """The tagger: yes when a step's detail has cod_risk high, no otherwise."""
    return {v["id"]: any(isinstance(s.get("detail"), dict) and s["detail"].get("cod_risk") == "high"
                         for s in v["steps"]) for v in cases}


class OneChain(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        ids = itertools.count(1)
        p = mock.patch("kit.chats.uuid.uuid4", side_effect=lambda: uuid.UUID(int=next(ids)))  # fixed chat ids
        p.start()
        self.addCleanup(p.stop)

    def test_a_refused_order_reaches_the_lesson_it_teaches(self):
        lessons = Lessons(self.db, judge=Judge(FakeModel(say("low"))))
        kept = kept_lesson(lessons, TONE, ["all"])
        results = Results(self.db)
        app = wa.App(Chats(self.db), FakeModel(*[say("Ask me anything.")] * CHATS), lessons, results,
                     SimpleNamespace(send=Outbox()), limits=Limits(self.db))
        chats = []
        for n in range(1, CHATS + 1):
            app.accept(wa.parse(payload(text_msg(f"m{n}", "hello there, a question", frm=f"2011111111{n:02d}"))))
            self.assertEqual(app.work_one(app.q.get_nowait()).outcome, "replied")
            chat = results.query(result="replied")[-1]["case_id"]
            chats.append(chat)
            results.record(chat, "order_created", stage="ordering", detail={
                "order": f"#10{n:02d}", "store": "shopify", "total": 850, "cod_risk": "high" if n <= 6 else "low",
                "reasons": []})
        deliveries = bosta.Deliveries(results)
        for n in range(1, CHATS + 1):
            refused = n in REFUSED
            body = {"_id": f"d{n}", "trackingNumber": f"T{n}", "state": 47 if refused else 45, "type": "SEND",
                    "exceptionCode": 8 if refused else None, "cod": 850, "timeStamp": STAMP + n,
                    "numberOfAttempts": 1,
                    "businessReference": f"10{n:02d}" if n % 2 else f"#10{n:02d}"}  # with the store's # or without
            self.assertEqual(deliveries.accept(body), (200, "recorded"))

        proposer = fk.Proposer({"pattern": HIGH, "helps": False, "lesson": LESSON,
                                "situation": "An order the risk check marks high.", "stages": ["ordering"]})
        plug = delivery_plug()
        self.assertEqual((SALES.decides.good, SALES.decides.bad), ("order_created", ()))  # it would settle all 12 good
        self.assertEqual((plug.agent, plug.decides.good, plug.decides.bad), ("sales", "delivered", ("refused",)))
        rep = night.night(self.db, plug, until=time.time() + 60, days=14, judge=Judge(FakeModel(say("low"))),
                          proposer=proposer, tagger=by_risk, fit=fk.Fit(), adapter=fk.Adapter())

        self.assertEqual(rep["decided"], {"good": 6, "bad": 6, "past_window": 0})
        cand, = rep["candidates"]
        self.assertEqual((cand["verdict"], cand["with"]["cases"], cand["with"]["good"], cand["without"]["cases"],
                          cand["without"]["good"]), ("lesson", 6, 1, 6, 5))
        card, = rep["cards"]
        self.assertEqual((card["state"], card["change"]), ("trying", LESSON))
        link, = rep["links"]["lessons"]
        self.assertEqual((link["lesson_id"], link["from_agent"], link["from_lesson"]),
                         (card["lesson_id"], "sales", None))
        self.assertEqual(sorted(link["cases"]), sorted(chats[:6]))
        self.assertEqual(rep["links"]["agents_read"][0], "sales")

        first = chats[0]
        self.assertIn(first, link["cases"])
        self.assertIn(first, lessons.get(card["lesson_id"])["source"])
        rows = results.for_chat(first)
        self.assertEqual([r["outcome"] for r in rows], ["replied", "order_created", "refused"])
        self.assertEqual(rows[0]["lessons"], [kept])
        self.assertEqual(rows[2]["detail"], {"order": "1001", "bosta": "T1", "state": 47, "code": 8, "at": STAMP + 1})
        seen = [s.get("lessons") for c in proposer.calls[0]["sample"] for s in c["steps"] if "lessons" in s]
        self.assertTrue(seen)
        self.assertTrue(all(given == [TONE] for given in seen))  # the study read which lesson each reply had


if __name__ == "__main__":
    unittest.main()
