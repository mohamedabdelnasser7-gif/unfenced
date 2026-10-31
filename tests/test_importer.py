"""Task t261029y: the history importer. Each parser, the join, idempotence, the dry run, the caps
and refusals, history kept out of trials, the reply candidates with their masks and the demo
humanizer, and a night study over the fake history in demo/history. The files are fake; the
engine paths are the real ones."""
import contextlib
import csv
import datetime
import io
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from engine import humanizer as hum
from engine import plug as plug_mod
from engine import risk
from engine.lessons import KEPT, TRYING, WAITING, Lessons
from engine.log import Log
from engine.study import BAD, GOOD, PENDING, Study, settle
from engine.trial import Trials
from kit.db import Db
from reflection import PLUG
from reflection import history as hist
from reflection import importer as imp
from reflection.results import Results
from tests import study_fakes as fk

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "history"
TEAM = ["Beyond the Limits"]
CAIRO = ZoneInfo("Africa/Cairo")
NOW = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=CAIRO).timestamp()
DAY = 86400


def at(*args):
    return datetime.datetime(*args, tzinfo=CAIRO).timestamp()


def delivery_plug():
    """The Sales plug as a brand with a delivery source could run it: delivered decides good and
    refused bad. The Sales plug itself decides on order_created; this one keeps the importer's
    pending and settling guards checked."""
    d = json.loads((ROOT / "sales" / "plug.json").read_text(encoding="utf-8"))
    d["decides"] = {"good": "delivered", "bad": ["refused"]}
    return plug_mod.from_dict(d, folder=ROOT / "sales")


def moj(s):
    return s.encode("utf-8").decode("latin-1")


class Temp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = str(self.tmp / "h.db")

    def tearDown(self):
        self._tmp.cleanup()

    def open(self):
        db = Db(self.db)
        self.addCleanup(db.close)
        return db

    def demo(self, plug=None, **kw):
        args = dict(whatsapp=DEMO / "whatsapp", instagram=DEMO / "instagram", orders=DEMO / "orders.csv",
                    deliveries=DEMO / "deliveries.csv", team=TEAM, now=NOW)
        args.update(kw)
        return imp.run(self.db, plug or PLUG, **args)

    def wa(self, name, *lines, where="wa"):
        folder = self.tmp / where
        folder.mkdir(exist_ok=True)
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return folder


class WhatsAppAndroid(unittest.TestCase):
    def test_lines_multi_line_system_media_team_and_phone(self):
        counts = Counter()
        chat = hist.parse_whatsapp("\n".join([
            "05/07/2026, 10:00 - Messages and calls are end-to-end encrypted. Tap to learn more.",
            "05/07/2026, 10:01 - +20 100 000 0042: السلام عليكم",
            "05/07/2026, 10:02 - Beyond the Limits: أهلا بيكي",
            "05/07/2026, 10:03 - +20 100 000 0042: العنوان: 12 شارع التجربة",
            "مدينة نصر",
            "05/07/2026, 10:04 - +20 100 000 0042: <Media omitted>",
            "05/07/2026, 10:05 - +20 100 000 0042: This message was deleted",
            "13/07/2026, 2:05 pm - Beyond the Limits: تمام"]), TEAM, file_name="WhatsApp Chat with Demo.txt", counts=counts)
        m = chat.messages
        self.assertEqual([x.team for x in m], [False, True, False, False, True])
        self.assertEqual(m[2].text, "العنوان: 12 شارع التجربة\nمدينة نصر")
        self.assertEqual((m[3].media, m[3].text), ("media", ""))
        self.assertEqual(counts["system lines"], 2)
        self.assertEqual(chat.phone, "201000000042")
        self.assertEqual(m[0].at, at(2026, 7, 5, 10, 1))
        self.assertEqual(m[4].at, at(2026, 7, 13, 14, 5))

    def test_phone_from_the_file_name(self):
        chat = hist.parse_whatsapp("05/07/2026, 10:01 - Demo Mona: hi", TEAM,
                                   file_name="WhatsApp Chat with +20 100 000 0042.txt")
        self.assertEqual(chat.phone, "201000000042")
        self.assertEqual(hist.parse_whatsapp("05/07/2026, 10:01 - Demo Mona: hi", TEAM, file_name="x.txt").phone, "")

    def test_month_first_only_when_a_date_reads_only_that_way(self):
        chat = hist.parse_whatsapp("07/13/2026, 10:00 - Demo Mona: hi", TEAM)
        self.assertEqual(chat.messages[0].at, at(2026, 7, 13, 10, 0))

    def test_a_long_message_is_cut(self):
        chat = hist.parse_whatsapp("05/07/2026, 10:01 - Demo Mona: " + "ا" * 5000, TEAM)
        self.assertEqual(len(chat.messages[0].text), hist.MAX_TEXT)


class WhatsAppIos(unittest.TestCase):
    def test_lines_media_system_multi_line_and_pm(self):
        counts = Counter()
        chat = hist.parse_whatsapp("\n".join([
            "[05/07/2026, 10:00:00] ‪+20 100 000 0043‬: ‎Messages and calls are end-to-end encrypted.",
            "[05/07/2026, 10:01:09] ‪+20 100 000 0043‬: مساء الخير",
            "‎[05/07/2026, 10:02:10] ‪+20 100 000 0043‬: ‎image omitted",
            "[05/07/2026, 10:03:11] Beyond the Limits: اتفضلي",
            "سطر تاني",
            "[05/07/2026, 1:04:12 PM] Beyond the Limits: تمام"]), TEAM, counts=counts)
        m = chat.messages
        self.assertEqual(len(m), 4)
        self.assertEqual(counts["system lines"], 1)
        self.assertEqual((m[1].media, m[1].team), ("image", False))
        self.assertEqual(m[2].text, "اتفضلي\nسطر تاني")
        self.assertEqual(m[0].at, at(2026, 7, 5, 10, 1, 9))
        self.assertEqual(m[3].at, at(2026, 7, 5, 13, 4, 12))
        self.assertEqual(chat.phone, "201000000043")


class Instagram(unittest.TestCase):
    def test_mojibake_arabic_is_fixed_and_typed_numbers_are_kept(self):
        t = int(at(2026, 8, 1, 12, 0) * 1000)
        doc = {"participants": [{"name": moj("سلمى تجربة")}, {"name": "Beyond the Limits"}], "messages": [
            {"sender_name": moj("سلمى تجربة"), "timestamp_ms": t + 3000, "content": moj("رقمي 01000000044 وطلبي #1044")},
            {"sender_name": "Beyond the Limits", "timestamp_ms": t + 2000, "content": moj("أهلا بيكي")},
            {"sender_name": moj("سلمى تجربة"), "timestamp_ms": t + 1500, "content": "Liked a message"},
            {"sender_name": moj("سلمى تجربة"), "timestamp_ms": t + 1000, "photos": [{"uri": "x.jpg"}]},
            {"sender_name": moj("سلمى تجربة"), "timestamp_ms": t, "content": moj("مساء الخير")}]}
        counts = Counter()
        chat = hist.parse_instagram([hist.load_json(json.dumps(doc))], TEAM, key="thread", counts=counts)
        self.assertEqual([m.text for m in chat.messages], ["مساء الخير", "", "أهلا بيكي", "رقمي 01000000044 وطلبي #1044"])
        self.assertEqual([m.team for m in chat.messages], [False, False, True, False])
        self.assertEqual(chat.messages[1].media, "image")
        self.assertEqual(counts["system lines"], 1)
        self.assertEqual((chat.phone, chat.typed_phones, chat.typed_orders), ("", {"201000000044"}, {"#1044"}))
        self.assertIn("سلمى تجربة", chat.names)

    def test_text_that_is_not_mojibake_stays(self):
        self.assertEqual(hist.fix_text("مرحبا"), "مرحبا")
        self.assertEqual(hist.fix_text("hello"), "hello")


ORDERS = ("Name,Total,Created at,Lineitem name,Phone,Shipping Phone,Billing Phone,Billing Name,Cancelled at\n"
          '#1,16960.00,2026-07-05 14:05:09 +0300,Nike Mercurial Vapor 17 - Elite / 43,01000000045,,,Demo One,\n'
          '#1,,,Beyond the Limits Name Printing,,,,,\n'
          '#2,11060.00,2026-07-06 09:00:00 +0300,Nike Phantom 6 - Pro / 42,,+20 100 000 0046,,,2026-07-06 10:00:00 +0300\n')


class OrdersAndDeliveries(unittest.TestCase):
    def test_line_items_group_by_name(self):
        got = hist.parse_orders(ORDERS, hist.Reader())
        self.assertEqual(set(got), {"#1", "#2"})
        self.assertEqual((got["#1"].phones, got["#1"].total, got["#1"].names), ({"201000000045"}, "16960.00", {"Demo One"}))
        self.assertEqual(got["#1"].at, at(2026, 7, 5, 14, 5, 9))
        self.assertEqual((got["#2"].phones, got["#2"].cancelled), ({"201000000046"}, True))

    def test_returned_counts_as_refused_and_the_last_row_wins(self):
        counts = Counter()
        got = hist.parse_deliveries("order,state,date\n#1,delivered,2026-07-08\n#1,returned,2026-07-10\n"
                                    "#2,lost,2026-07-09\n", hist.Reader(), counts=counts)
        self.assertEqual(got, {"#1": ("refused", at(2026, 7, 10, 12, 0), True)})
        self.assertEqual(counts["bad rows"], 1)


def good_cases(*msgs, names=(), orders=None, more=()):
    """plan() over one chat of these messages (and any more chats), its case marked delivered."""
    one = hist.Chat("whatsapp", "k", 0, list(msgs), names=set(names))
    cases = imp.plan([one, *more], orders or {}, {}, now=NOW, counts=Counter())
    cases[0]["good"] = True
    return cases


def texts(cases):
    return [c[1] for c in imp.candidates(cases, "sales")]


def chat(phone="", typed=(), orders=(), times=(0, 3600), source="whatsapp", key="c"):
    t0 = at(2026, 7, 5, 10, 0)
    return hist.Chat(source, key, 0, [hist.Message(t0 + t, False, "x") for t in times], phone=phone,
                     typed_phones=set(typed), typed_orders=set(orders))


def order(name, hours, *phones):
    return hist.Order(name, at(2026, 7, 5, 10, 0) + hours * 3600, {hist.phone_key(p) for p in phones} - {""})


class Join(unittest.TestCase):
    def test_phone_forms_meet(self):
        for form in ("01000000045", "+20 100 000 0045", "00201000000045", "+201000000045"):
            with self.subTest(form=form):
                joined, alone = hist.join([chat("201000000045")], {"#1": order("#1", 5, form)})
                self.assertEqual((joined, alone), ({0: ["#1"]}, []))

    def test_the_window(self):
        chats = [chat("201000000045")]
        for hours, fits in ((-1, False), (0.5, True), (1 + 71, True), (1 + 73, False), (1 + 96, False)):
            with self.subTest(hours=hours):
                joined, _ = hist.join(chats, {"#1": order("#1", hours, "01000000045")})
                self.assertEqual(bool(joined), fits)

    def test_no_match(self):
        self.assertEqual(hist.join([chat("201000000045")], {"#1": order("#1", 5, "01000000099")}), ({}, ["#1"]))

    def test_two_orders_join_one_chat_and_an_order_joins_one_chat(self):
        joined, _ = hist.join([chat("201000000045")], {"#2": order("#2", 30, "01000000045"),
                                                       "#1": order("#1", 5, "01000000045")})
        self.assertEqual(joined, {0: ["#1", "#2"]})
        early, late = chat("201000000045", key="a"), chat("201000000045", times=(24 * 3600, 25 * 3600), key="b")
        joined, _ = hist.join([early, late], {"#1": order("#1", 36, "01000000045")})
        self.assertEqual(joined, {1: ["#1"]})

    def test_an_instagram_chat_joins_only_on_what_the_customer_typed(self):
        orders = {"#1044": order("#1044", 5, "01000000044")}
        self.assertEqual(hist.join([chat(source="instagram")], orders)[0], {})
        self.assertEqual(hist.join([chat(source="instagram", typed={"201000000044"})], orders)[0], {0: ["#1044"]})
        self.assertEqual(hist.join([chat(source="instagram", orders={"#1044"})], orders)[0], {0: ["#1044"]})


class Import(Temp):
    def test_rows_are_history_with_their_keys_and_no_lessons(self):
        rep = self.demo()
        db = self.open()
        rows = Log(db, PLUG).query()
        self.assertTrue(rows)
        for r in rows:
            self.assertIs(r["detail"]["history"], True)
            self.assertIn(r["detail"]["source"], ("whatsapp", "instagram", "orders", "deliveries"))
            self.assertEqual(len(r["detail"]["import_key"]), 32)
            self.assertEqual(r["lessons"], [])
        self.assertEqual(Counter(r["result"] for r in rows if r["result"] in ("delivered", "refused")),
                         {"delivered": 12, "refused": 6})
        self.assertEqual(rep["counts"]["orders with no chat"], 4)
        self.assertEqual(rep["counts"]["chats with no order"], 5)
        self.assertIsNone(Results(db).chat_for_order("#1001"))  # a live courier result never lands on history
        with db.tx() as c:
            channels = {r[0] for r in c.execute("SELECT channel FROM chats")}
            past = c.execute("SELECT MAX(at) FROM steps").fetchone()[0]
        self.assertEqual(channels, {"history:whatsapp", "history:instagram"})
        self.assertLess(past, NOW)

    def test_the_same_files_twice_add_nothing(self):
        self.demo()
        rep = self.demo()
        c = Counter(rep["counts"])
        self.assertEqual((c["chats written"], c["steps written"], c["rows written"]), (0, 0, 0))
        self.assertEqual(c["rows already there"], 205)
        self.assertEqual(rep["candidates"]["added"], 0)
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM trace").fetchone()[0], 205)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM steps").fetchone()[0], 320)

    def test_the_dry_run_writes_nothing(self):
        with mock.patch.object(imp, "Db", side_effect=AssertionError("opened")):
            rep = self.demo(dry_run=True)
        self.assertFalse(Path(self.db).exists())
        self.assertEqual(rep["read"]["orders"], 22)
        self.assertIn("a dry run: nothing written", imp.text(rep))

    def test_the_report_names_no_one(self):
        rep = self.demo()
        out = imp.text(rep, "DB") + json.dumps(rep, ensure_ascii=False)
        for word in ("تجربة", "Demo Customer", "Demo Hany", "0100000", "100 000", "2010000", "الجزمة", "عايز", "#10"):
            self.assertNotIn(word, out)

    def test_rows_timed_after_now_are_not_written(self):
        now = at(2026, 8, 15, 12, 0)
        rep = self.demo(now=now)
        self.assertGreater(rep["counts"]["rows outside time"], 0)
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            self.assertLessEqual(con.execute("SELECT MAX(at) FROM trace").fetchone()[0], now)
            self.assertLessEqual(con.execute("SELECT MAX(at) FROM steps").fetchone()[0], now)

    def test_the_command_by_its_path(self):
        run = subprocess.run([sys.executable, "-I", str(ROOT / "reflection" / "importer.py"), "--db", self.db,
                              "--whatsapp", str(DEMO / "whatsapp"), "--orders", str(DEMO / "orders.csv"),
                              "--team", "Beyond the Limits", "--dry-run"], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("Read: 18 WhatsApp chats", run.stdout)
        self.assertFalse(Path(self.db).exists())

    def test_a_bad_plug_time_zone_or_pairs_file_stops_before_any_write(self):
        (self.tmp / "plug.json").write_text("not json", encoding="utf-8")
        (self.tmp / "pairs.json").write_text('{"pairs": 1}', encoding="utf-8")
        base = ["--db", self.db, "--whatsapp", str(DEMO / "whatsapp"), "--team", "Beyond the Limits"]
        with mock.patch("sys.stderr") as err:
            self.assertEqual(imp.main(base + ["--plug", str(self.tmp / "plug.json")], now=NOW), 2)
            self.assertEqual(imp.main(base + ["--pairs", str(self.tmp / "pairs.json")], now=NOW), 2)
            with self.assertRaises(SystemExit):
                imp.main(base + ["--tz", "Nowhere/Town"], now=NOW)
            with self.assertRaises(SystemExit):
                imp.main(base + ["--days", "31"], now=NOW)
        said = "".join(str(c.args[0]) for c in err.write.call_args_list)
        self.assertIn("Stopped:", said)
        self.assertIn("Refused, nothing written: a pairs file", said)
        self.assertFalse(Path(self.db).exists())

    def test_a_plug_without_the_results_it_writes_stops_before_any_write(self):
        with self.assertRaisesRegex(ValueError, "declares no result"):
            imp.run(self.db, plug_mod.load(ROOT / "marketing" / "plug.json"), whatsapp=DEMO / "whatsapp", team=TEAM,
                    now=NOW)
        self.assertFalse(Path(self.db).exists())

    def test_customer_text_on_a_row_is_cut(self):
        t = at(2026, 7, 5, 10, 0)
        c = hist.Chat("whatsapp", "k", 0, [hist.Message(t, False, "ا" * 3000), hist.Message(t + 60, True, "تمام")])
        cases = imp.plan([c], {}, {}, now=NOW, counts=Counter())
        self.assertEqual(len(cases[0]["rows"][0]["detail"]["customer"]), imp.MAX_CUSTOMER_CHARS)


def always_low(text, high_about, low_about):
    return risk.LOW


class HistoryNeverJudgesATrial(Temp):
    def test_a_history_case_inside_a_trial_window_is_not_counted(self):
        self.demo()
        db = self.open()
        log = Log(db, PLUG)
        start = min(r["at"] for r in log.query(result="order_created")) - 3600
        lessons = Lessons(db, PLUG, judge=always_low)
        lid = lessons.propose("Greet each buyer warmly.", ["all"], sources=[], now=start)
        if lessons.get(lid)["state"] == WAITING:
            lessons.approve(lid, "test", now=start)
        self.assertEqual(lessons.get(lid)["state"], TRYING)
        log.act("h-given", "reply", result="replied", lessons=[lid], detail={"history": True}, at=start + 60)
        log.act("live-1", "reply", result="replied", at=start + 120)
        rep = Trials(db, PLUG, lessons=lessons).check(start + 6 * DAY)
        entry = next(t for t in rep["trials"] if t["lesson_id"] == lid)
        self.assertEqual(entry["with"]["cases"], 0)
        self.assertEqual([c["case"] for c in entry["without"]["list"]], ["live-1"])


class Landmark:
    """The tagger's stand-in: yes when a team reply in the case asks for a landmark."""

    def __call__(self, plug, pattern, cases):
        return {v["id"]: any("علامة" in ((s.get("detail") or {}).get("reply") or "") for s in v["steps"])
                for v in cases}


CANDIDATE = {"pattern": "The team asked for a landmark near the address.", "helps": True,
             "lesson": "Ask for a landmark near the address before you confirm an order.",
             "situation": "A buyer gives an address.", "stages": ["ordering"]}


class StudyOverHistory(Temp):
    def study(self, plug):
        window = self.demo()["window"]
        db = self.open()
        proposer = fk.Proposer(CANDIDATE)
        rep = Study(db, plug, proposer=proposer, tagger=Landmark()).run(window["since"], NOW, now=NOW)
        lessons = Lessons(db, plug)
        for card in rep["cards"]:
            self.assertIn(card["state"], (WAITING, TRYING))
            self.assertNotEqual(lessons.get(card["lesson_id"])["state"], KEPT)
        self.assertNotIn("0100000", json.dumps(proposer.calls, ensure_ascii=False))
        return rep

    def test_it_proposes_from_history_and_never_keeps(self):
        """Under the Sales plug an imported order settles its case good."""
        rep = self.study(PLUG)
        rec = rep["candidates"][0]
        self.assertEqual((rec["with"]["good"], rec["with"]["cases"]), (10, 10))
        self.assertEqual((rec["without"]["good"], rec["without"]["cases"]), (7, 12))
        self.assertTrue(rep["cards"])

    def test_a_plug_deciding_on_the_delivery_result_reads_the_deliveries(self):
        rep = self.study(delivery_plug())
        rec = rep["candidates"][0]
        self.assertEqual((rec["with"]["good"], rec["with"]["cases"]), (8, 10))
        self.assertEqual((rec["without"]["good"], rec["without"]["cases"]), (3, 12))
        self.assertTrue(rep["cards"])


class Candidates(Temp):
    def test_only_team_replies_from_delivered_chats_masked(self):
        self.demo()
        db = self.open()
        got = hum.Candidates(db, PLUG.agent).mine()
        texts = " ".join(c["text"] for c in got)
        for word in ("عايز", "أكدوا", "العنوان:", "سلمى", "كريم", "ياسمين", "0100000"):
            self.assertNotIn(word, texts)
        self.assertIn("[phone]", texts)
        self.assertIn("أهلا يا [name]", texts)
        log = Log(db, PLUG)
        for c in got:
            decided = [r["result"] for r in log.case(c["case_id"]) if r["result"] in ("delivered", "refused")]
            self.assertEqual(decided[-1], "delivered")
        self.assertEqual(Counter(c["status"] for c in got), {"refined": 5, "rejected": 11})

    def test_the_masks(self):
        self.assertEqual(hist.mask("رقم طلبك #1044 وكلمينا على +20 100 000 0045 يا Demo Mona", {"Demo Mona"}, ["#1044"]),
                         "رقم طلبك [order] وكلمينا على [phone] يا [name]")
        self.assertEqual(hist.mask("كلمينا 010 500 12345 يا منى", {"منى تجربة"}), "كلمينا [phone] يا [name]")

    def test_the_caps(self):
        with mock.patch.object(imp, "MAX_CANDIDATES", 3):
            self.demo()
        db = self.open()
        self.assertEqual(hum.Candidates(db, PLUG.agent).count(), 3)

    def test_at_most_per_case_from_one_chat(self):
        with mock.patch.object(imp, "PER_CASE", 1):
            self.demo()
        cases = Counter(c["case_id"] for c in hum.Candidates(self.open(), PLUG.agent).mine())
        self.assertEqual(set(cases.values()), {1})

    def test_a_long_or_short_reply_is_not_a_candidate(self):
        t = at(2026, 7, 5, 10, 0)
        cases = good_cases(hist.Message(t, True, "كلمة " * 100), hist.Message(t + 1, True, "تمام"),
                           hist.Message(t + 2, True, "أهلا بيكي يا فندم"))
        self.assertEqual(texts(cases), ["أهلا بيكي يا فندم"])

    def test_a_refined_text_with_a_phone_is_rejected(self):
        self.demo(humanizer=lambda text: {"refined": "كلمينا على 01000000045"})
        got = hum.Candidates(self.open(), PLUG.agent).mine()
        self.assertEqual({c["status"] for c in got}, {"rejected"})
        self.assertTrue(all("phone" in c["why"] for c in got))

    def test_the_pairs_cap(self):
        with mock.patch.object(imp, "MAX_PAIRS", 1), self.assertRaisesRegex(hist.Refused, "at most 1"):
            imp.load_pairs(hist.Reader(), DEMO / "humanizer.json")


class Humanizer(unittest.TestCase):
    def setUp(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        self.store = hum.Candidates(db, "sales")
        for k in ("a", "b", "c"):
            self.store.add(k, f"reply {k} here", case_id="h1", source="whatsapp", at=1.0)

    def test_pairs_refine_and_reject_and_a_failure_waits(self):
        def down(text):
            raise RuntimeError("down")
        self.assertEqual(self.store.run(down), Counter({"waiting": 3}))
        ran = self.store.run(hum.Pairs([("reply a here", "رد أ"), ("reply b here", "رد 01000000045")]), check=imp.clean)
        self.assertEqual(ran, Counter({"refined": 1, "rejected": 2}))
        by = {c["key"]: c for c in self.store.mine()}
        self.assertEqual((by["a"]["status"], by["a"]["refined"]), ("refined", "رد أ"))
        self.assertIn("phone", by["b"]["why"])
        self.assertEqual(by["c"]["why"], hum.NOT_YET)

    def test_unclear_answers_wait(self):
        for answer in ("yes", {"refined": "x" * 600}, {"refined": ""}, {"rejected": ""}, {"refined": "a", "x": 1}):
            with self.subTest(answer=answer):
                self.assertEqual(hum.refine("t", lambda text, a=answer: a)[0], hum.WAITING)

    def test_a_run_from_a_stale_list_changes_nothing(self):
        stale = self.store.mine(hum.WAITING)
        self.store.run(hum.Pairs([("reply a here", "رد أ")]))
        with mock.patch.object(self.store, "mine", return_value=stale):
            self.store.run(lambda text: {"refined": "new"})
        by = {c["key"]: c for c in self.store.mine()}
        self.assertEqual((by["a"]["refined"], by["b"]["status"], by["c"]["status"]), ("رد أ", "rejected", "rejected"))

    def test_a_settled_candidate_never_changes(self):
        self.store.run(hum.Pairs([]))
        self.assertEqual(self.store.run(lambda text: {"refined": "new"}), Counter())
        self.assertEqual({c["status"] for c in self.store.mine()}, {"rejected"})
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.db.tx() as c:
                c.execute("UPDATE reply_candidates SET status = 'refined', refined = 'x'")
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.db.tx() as c:
                c.execute("INSERT INTO reply_candidates (agent, key, text, source, at, added_at) "
                          "VALUES ('sales', 'd', 't', 's', 1, 1)")
                c.execute("UPDATE reply_candidates SET text = 'other' WHERE key = 'd'")


ANDROID = ["05/07/2026, 10:00 - +20 100 000 0042: one", "05/07/2026, 10:01 - Beyond the Limits: two",
           "05/07/2026, 10:02 - +20 100 000 0042: three"]


class Caps(Temp):
    def run_wa(self, folder, **kw):
        return imp.run(self.db, PLUG, whatsapp=folder, team=TEAM, now=NOW, dry_run=True, **kw)

    def not_read(self, rep):
        return {n["why"]: n["files"] for n in rep["not_read"]}

    def test_the_size_cap_of_one_file(self):
        folder = self.wa("a.txt", *ANDROID)
        with mock.patch.object(hist, "MAX_FILE_BYTES", 50):
            rep = self.run_wa(folder)
        self.assertEqual(rep["read"]["whatsapp_chats"], 0)
        self.assertEqual(self.not_read(rep), {"over the size cap of one file": 1})

    def test_the_size_cap_of_the_whole_import(self):
        folder = self.wa("a.txt", *ANDROID)
        self.wa("b.txt", *ANDROID)
        with mock.patch.object(hist, "MAX_TOTAL_BYTES", (folder / "a.txt").stat().st_size + 1):
            rep = self.run_wa(folder)
        self.assertEqual(rep["read"]["whatsapp_chats"], 1)
        self.assertEqual(self.not_read(rep), {"over the size cap of the whole import": 1})

    def test_the_file_count_cap(self):
        folder = self.wa("a.txt", *ANDROID)
        self.wa("b.txt", *ANDROID)
        with mock.patch.object(hist, "MAX_FILES", 1):
            rep = self.run_wa(folder)
        self.assertEqual(self.not_read(rep), {"over the file count cap": 1})

    def test_the_message_caps(self):
        folder = self.wa("a.txt", *ANDROID)
        self.wa("b.txt", *ANDROID)
        with mock.patch.object(hist, "MAX_MESSAGES_PER_FILE", 2):
            self.assertEqual(self.not_read(self.run_wa(folder)), {"over the message cap of one file": 2})
        with mock.patch.object(hist, "MAX_MESSAGES", 4):
            self.assertEqual(self.not_read(self.run_wa(folder)), {"over the message cap of the whole import": 1})

    def test_the_row_cap(self):
        (self.tmp / "o.csv").write_text(ORDERS, encoding="utf-8")
        with mock.patch.object(hist, "MAX_ROWS", 2), self.assertRaisesRegex(hist.Refused, "orders file: over the row"):
            imp.run(self.db, PLUG, orders=self.tmp / "o.csv", now=NOW, dry_run=True)

    def test_json_depth(self):
        with self.assertRaisesRegex(hist.Refused, "too deep"):
            hist.load_json("[" * 30 + "]" * 30)
        self.assertEqual(hist.load_json('{"a": "[[[[[[[[[[[[[[[[[[[[[[[["}'), {"a": "[" * 24})
        thread = self.tmp / "ig" / "messages" / "inbox" / "t1"
        thread.mkdir(parents=True)
        (thread / "message_1.json").write_text('{"messages": ' + "[" * 30 + "]" * 30 + "}", encoding="utf-8")
        rep = imp.run(self.db, PLUG, instagram=self.tmp / "ig", team=TEAM, now=NOW, dry_run=True)
        self.assertEqual(self.not_read(rep), {"JSON nested too deep": 1})

    def test_links_are_refused(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("\n".join(ANDROID), encoding="utf-8")
        folder = self.wa("a.txt", *ANDROID)
        os.symlink(outside, folder / "b.txt")
        rep = self.run_wa(folder)
        self.assertEqual((rep["read"]["whatsapp_chats"], self.not_read(rep)), (1, {"a link": 1}))
        with self.assertRaisesRegex(hist.Refused, "a link"):
            hist.Reader().read(folder / "b.txt")
        os.symlink(folder, self.tmp / "wa-link")
        with self.assertRaisesRegex(hist.Refused, "WhatsApp folder: a link"):
            self.run_wa(self.tmp / "wa-link")
        inbox = self.tmp / "ig" / "messages" / "inbox"
        inbox.mkdir(parents=True)
        os.symlink(self.tmp, inbox / "t1")
        rep = imp.run(self.db, PLUG, instagram=self.tmp / "ig", team=TEAM, now=NOW, dry_run=True)
        self.assertEqual(self.not_read(rep), {"a link": 1})
        (self.tmp / "ig2").mkdir()
        os.symlink(self.tmp / "ig" / "messages", self.tmp / "ig2" / "messages")
        rep = imp.run(self.db, PLUG, instagram=self.tmp / "ig2", team=TEAM, now=NOW, dry_run=True)
        self.assertEqual(self.not_read(rep), {"a link": 1})

    def test_a_folder_given_as_a_file_is_refused(self):
        with self.assertRaisesRegex(hist.Refused, "orders file: not a plain file"):
            imp.run(self.db, PLUG, orders=self.tmp, now=NOW, dry_run=True)

    def test_a_file_that_grows_while_read(self):
        folder = self.wa("a.txt", *ANDROID)
        small = os.stat_result((stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 10, 0, 0, 0))
        with mock.patch.object(hist, "MAX_FILE_BYTES", 50), mock.patch.object(hist.os, "fstat", return_value=small):
            with self.assertRaisesRegex(hist.Refused, "^over the size cap$"):
                hist.Reader().read(folder / "a.txt")

    def test_the_repo_is_refused_but_demo_history(self):
        with self.assertRaisesRegex(hist.Refused, "orders file: inside the repo"):
            imp.run(self.db, PLUG, orders=ROOT / "LICENSE", now=NOW, dry_run=True)
        with self.assertRaisesRegex(hist.Refused, "WhatsApp folder: inside the repo"):
            self.run_wa(ROOT / "tests")
        self.assertEqual(self.run_wa(DEMO / "whatsapp")["read"]["whatsapp_chats"], 18)

    def test_3_a_change_of_case_is_still_the_repo(self):
        swapped = Path(str(ROOT).swapcase())
        if not (swapped / "LICENSE").exists():
            self.skipTest("this disk tells case apart, so the swapped path is not the repo")
        with self.assertRaisesRegex(hist.Refused, "orders file: inside the repo"):
            imp.run(self.db, PLUG, orders=swapped / "LICENSE", now=NOW, dry_run=True)
        with self.assertRaisesRegex(hist.Refused, "^inside the repo"):
            hist.Reader().read(swapped / "LICENSE")
        with self.assertRaisesRegex(hist.Refused, "WhatsApp folder: inside the repo"):
            self.run_wa(swapped / "tests")
        self.assertEqual(self.run_wa(swapped / "demo" / "history" / "whatsapp")["read"]["whatsapp_chats"], 18)
        self.assertTrue(imp.demo_only(swapped / "demo" / "history" / "orders.csv"))


class Round1Fixes(Temp):
    """Review t261029y round 1: each finding's guard."""

    def brand(self):
        """The demo files copied out of the repo: a real brand's import as far as the code can tell."""
        shutil.copytree(DEMO, self.tmp / "brand")
        b = self.tmp / "brand"
        return dict(whatsapp=b / "whatsapp", instagram=b / "instagram", orders=b / "orders.csv",
                    deliveries=b / "deliveries.csv")

    def test_1_a_real_import_runs_no_humanizer_and_its_candidates_wait(self):
        rep = self.demo(**self.brand())
        self.assertEqual(rep["candidates"]["ran"], {})
        self.assertEqual(rep["candidates"]["status"], {"refined": 0, "rejected": 0, "waiting": 16})
        self.assertTrue(imp.demo_only(DEMO / "whatsapp", None, DEMO / "orders.csv"))
        self.assertFalse(imp.demo_only(DEMO / "whatsapp", self.tmp / "brand" / "orders.csv"))
        self.assertFalse(imp.demo_only(None, None))

    def test_1_the_demo_pairs_leave_another_imports_waiting_candidates_alone(self):
        db = Db(self.db)
        hum.Candidates(db, PLUG.agent).add("other", "رد من ملفات براند تانية هنا", case_id="h2", source="whatsapp",
                                           at=1.0)
        db.close()
        rep = self.demo()
        self.assertEqual(rep["candidates"]["status"], {"refined": 5, "rejected": 11, "waiting": 1})
        self.assertEqual(hum.Candidates(self.open(), PLUG.agent).mine(hum.WAITING)[0]["key"], "other")

    def test_1_rejected_candidates_hold_no_place_under_the_cap(self):
        db = Db(self.db)
        store = hum.Candidates(db, PLUG.agent)
        for k in ("a", "b", "c"):
            store.add(k, f"old reply {k} here", case_id="h1", source="whatsapp", at=1.0)
        store.run(hum.Pairs([]))
        db.close()
        with mock.patch.object(imp, "MAX_CANDIDATES", 3):
            rep = self.demo(**self.brand())
            self.assertEqual((rep["candidates"]["added"], rep["candidates"]["status"]["waiting"]), (3, 3))
            self.assertEqual(self.demo(whatsapp=DEMO / "whatsapp")["candidates"]["added"], 0)  # waiting ones hold theirs

    def test_2_an_arabic_indic_phone_is_masked_in_customer_text_and_a_reply(self):
        t = at(2026, 7, 5, 10, 0)
        cases = good_cases(hist.Message(t, False, "رقمي ٠١٠٠٠٠٠٠٠٠٢"),
                           hist.Message(t + 60, True, "هنكلمك على ٠١٠٠٠٠٠٠٠٠٢ بكرة يا فندم"))
        detail = cases[0]["rows"][0]["detail"]
        for text in (detail["customer"], detail["reply"], texts(cases)[0], cases[0]["steps"][0]["text"]):
            self.assertNotIn("٠١٠", text)
            self.assertIn("[number]", text)

    def test_4_a_large_multi_line_message_reads_in_well_under_a_few_seconds(self):
        text = "05/07/2026, 10:01 - Demo Mona: start\n" + "\n".join(["سطر طويل شوية في رسالة كبيرة جدا"] * 120_000)
        start = time.monotonic()
        chat = hist.parse_whatsapp(text, TEAM)
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(len(chat.messages[0].text), hist.MAX_TEXT)
        self.assertTrue(chat.messages[0].text.startswith("start\nسطر طويل"))

    def test_5_an_unreadable_thread_folder_is_refused_counted_and_not_named(self):
        if os.geteuid() == 0:
            self.skipTest("root reads any folder")
        thread = self.tmp / "ig" / "messages" / "inbox" / "demo.customer_7"
        thread.mkdir(parents=True)
        (thread / "message_1.json").write_text('{"messages": []}', encoding="utf-8")
        os.chmod(thread, 0)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = imp.main(["--db", self.db, "--instagram", str(self.tmp / "ig"), "--team", "Beyond the Limits",
                                 "--dry-run"], now=NOW)
        finally:
            os.chmod(thread, 0o755)
        said = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, said)
        self.assertIn("Not read: 1 instagram file(s), a folder that cannot be read", said)
        self.assertNotIn("customer_7", said)
        self.assertNotIn("Traceback", said)

    def test_5_a_csv_field_over_the_csv_limit_is_refused(self):
        big = "x" * (csv.field_size_limit() + 10)
        (self.tmp / "o.csv").write_text(f"Name,Created at,Note\n#1,2026-07-05 14:05:09 +0300,{big}\n", encoding="utf-8")
        (self.tmp / "d.csv").write_text(f"order,state,date,note\n#1,delivered,2026-07-08,{big}\n", encoding="utf-8")
        with self.assertRaisesRegex(hist.Refused, "^the orders file: a CSV line that cannot be read"):
            imp.run(self.db, PLUG, orders=self.tmp / "o.csv", now=NOW, dry_run=True)
        with self.assertRaisesRegex(hist.Refused, "^the deliveries file: a CSV line that cannot be read"):
            imp.run(self.db, PLUG, deliveries=self.tmp / "d.csv", now=NOW, dry_run=True)

    def test_6_dots_order_names_emails(self):
        m = hist.Masker(set(), ["#1045", "#104567", "#12"])
        self.assertEqual(m("كلمني على 010.0000.0002"), "كلمني على [number]")
        self.assertEqual(m("رقم الاوردر 1045 وصل"), "رقم الاوردر [order] وصل")
        self.assertEqual(m("طلبي # 104567"), "طلبي [order]")
        self.assertEqual(m("اوردر 12 مقاس 12 و 104567 و 10450"), "اوردر [order] مقاس 12 و [order] و 10450")
        self.assertEqual(m("ابعتلي على demo.customer+1@example.com لو سمحت"), "ابعتلي على [email] لو سمحت")

    def test_6_every_name_in_the_import_is_masked_in_every_chat(self):
        t = at(2026, 7, 5, 10, 0)
        other = hist.Chat("whatsapp", "o", 0, [hist.Message(t, False, "x")], names={"Demo Hala", "Demo Sara"})
        unjoined = {"#1": hist.Order("#1", t, {"201000000099"}, names={"Demo Rasha"})}
        cases = good_cases(hist.Message(t, True, "تمام يا Hala، Sara هتكلمك و Rasha كمان"), more=[other],
                           orders=unjoined)
        self.assertEqual(cases[0]["rows"][0]["detail"]["reply"], "تمام يا [name]، [name] هتكلمك و [name] كمان")
        self.assertEqual(hist.mask("شكرا يا Rasha", {"Demo Rasha"}), "شكرا يا [name]")
        self.assertEqual(hist.mask("أهلا يا Mo Sa", {"Mo Sa"}), "أهلا يا [name]")

    def test_6_a_name_after_ya_that_no_mask_caught_drops_the_candidate(self):
        t = at(2026, 7, 5, 10, 0)
        cases = good_cases(*(hist.Message(t + i, True, s) for i, s in enumerate((
            "أهلا يا احمد، اتفضل تحت أمرك", "أهلا يا Ahmed، اتفضل تحت أمرك", "أهلا يا أستاذ، اتفضل تحت أمرك",
            "تمام يا جماعة هنشحن بكرة"))), names={"Ahmed Ali"})
        with mock.patch.object(imp, "PER_CASE", 10):
            self.assertEqual(texts(cases), ["أهلا يا [name]، اتفضل تحت أمرك", "أهلا يا أستاذ، اتفضل تحت أمرك",
                                            "تمام يا جماعة هنشحن بكرة"])
        self.assertTrue(hist.calls_by_name("أهلا يا احمد"))
        self.assertFalse(hist.calls_by_name("أهلا يا فندم، ويا [name]"))

    def test_7_address_numbers_are_masked_and_a_reply_with_an_address_is_no_candidate(self):
        self.assertEqual(hist.mask("العنوان: 12 شارع التجربة"), "العنوان: [number] شارع التجربة")
        self.assertEqual(hist.mask("عمارة 125 الدور 3 شقة 12"), "عمارة [number] الدور [number] شقة [number]")
        t = at(2026, 7, 5, 10, 0)
        cases = good_cases(hist.Message(t, True, "هنوصلك على 12 شارع التجربة بكرة"),
                           hist.Message(t + 1, True, "المحل في عمارة 5 جنب البنك"),
                           hist.Message(t + 2, True, "أهلا بيكي يا فندم"))
        self.assertEqual(texts(cases), ["أهلا بيكي يا فندم"])
        self.demo()
        rows = Log(self.open(), PLUG).query(result="person_replied")
        customer = "\n".join((r["detail"] or {}).get("customer", "") for r in rows)
        self.assertNotIn("12 شارع", customer)
        self.assertIn("[number] شارع التجربة", customer)

    def test_8_chat_steps_keep_only_masked_text(self):
        self.demo()
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            stored = "\n".join(r[0] for r in con.execute("SELECT content FROM steps WHERE content IS NOT NULL"))
        for word in ("0100000", "كريم", "سلمى", "ياسمين", "#1020"):
            self.assertNotIn(word, stored)
        self.assertIn("[phone]", stored)
        self.assertIn("[number] شارع التجربة", stored)

    def test_9_a_second_import_with_a_corrected_team_adds_nothing(self):
        folder = self.wa("WhatsApp Chat with Demo Mona.txt", "05/07/2026, 10:00 - Demo Mona: السلام عليكم",
                         "05/07/2026, 10:01 - Beyond the Limits: أهلا بيكي", "05/07/2026, 10:02 - Demo Mona: تمام شكرا")
        imp.run(self.db, PLUG, whatsapp=folder, team=["Beyond the Limits", "Demo Mona"], now=NOW)
        rep = imp.run(self.db, PLUG, whatsapp=folder, team=["Beyond the Limits"], now=NOW)
        c = Counter(rep["counts"])
        self.assertEqual((c["chats written"], c["steps written"], c["rows written"]), (0, 0, 0))
        with contextlib.closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM steps").fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM chats").fetchone()[0], 1)
        self.assertEqual(c["messages on the other side before"], 2)  # Demo Mona's two lines
        self.assertIn("2 messages were imported before on the other side", imp.text(rep))
        again = imp.run(self.db, PLUG, whatsapp=folder, team=["Beyond the Limits", "Demo Mona"], now=NOW)
        self.assertNotIn("other side", imp.text(again))


class Round2Fixes(Temp):
    def test_3_an_order_missing_from_a_given_deliveries_file_is_not_good_not_pending(self):
        rows = (DEMO / "deliveries.csv").read_text(encoding="utf-8").splitlines()
        self.assertTrue(rows[1].startswith("#1001,"))
        (self.tmp / "d.csv").write_text("\n".join(rows[:1] + rows[2:]) + "\n", encoding="utf-8")
        self.demo(deliveries=self.tmp / "d.csv")
        late = NOW + 365 * 86400
        cases = Log(self.open(), PLUG).window(0, late)
        [case] = [rows for rows in cases.values() if any((r["detail"] or {}).get("order") == "#1001" for r in rows)]
        self.assertFalse(any((r["detail"] or {}).get("result_unknown") for r in case))
        self.assertEqual(settle(delivery_plug(), case, late)[0], BAD)
        self.assertEqual(settle(PLUG, case, late)[0], GOOD)  # the Sales plug: the order settles it

    def test_4_a_name_typed_joined_to_ya_or_wa_is_masked(self):
        m = hist.Masker(names=["منى علي", "Demo Mona"])
        self.assertEqual(m("يامنى الطلب وصل"), "[name] الطلب وصل")
        self.assertEqual(m("ياMona تمام"), "[name] تمام")
        self.assertEqual(m("ومنى كمان"), "[name] كمان")
        self.assertEqual(m("يا جماعة"), "يا جماعة")
        m = hist.Masker(names=["عبد الله", "A"])
        self.assertEqual(m("والله تمام"), "والله تمام")  # و plus an al word is a word, not a name
        self.assertEqual(m("A B"), "A B")  # a one letter name masks nothing

    def test_5_ya_with_no_name_keeps_the_reply(self):
        for text in ("يا ريت تبعتي المقاس", "يا رب يوصل بسرعة", "ياريت", "يا ستي ولا يهمك", "يا اما الاسود يا اما الابيض",
                     "يا فَنْدِم", "يا الف مبروك", "يافندم", "ممكن ياخد يومين", "يانهار ابيض", "يادوب", "الياقة"):
            self.assertFalse(hist.calls_by_name(text), text)
        for text in ("يا سمير", "يا  سمير الطلب جاهز"):
            self.assertTrue(hist.calls_by_name(text), text)

    def test_6_a_price_or_size_that_matches_an_order_number_is_kept(self):
        m = hist.Masker(orders=["#450", "#1045", "#43"])
        self.assertEqual(m("السعر 450 جنيه"), "السعر 450 جنيه")
        self.assertEqual(m("بـ 1045 ج"), "بـ 1045 ج")
        self.assertEqual(m("مقاس 43"), "مقاس 43")
        self.assertEqual(m("مقاس 450"), "مقاس 450")
        self.assertEqual(m("السعر: 1045"), "السعر: 1045")
        self.assertEqual(m("450 EGP"), "450 EGP")
        self.assertEqual(m("رقم الاوردر 450"), "رقم الاوردر [order]")
        self.assertEqual(m("#450 اتشحن"), "[order] اتشحن")
        self.assertEqual(m("الطلب 1045 خرج"), "الطلب [order] خرج")
        self.assertEqual(m("1045 خرج"), "[order] خرج")

    def test_10_m07_the_last_row_by_date_wins_whatever_the_file_order(self):
        got = hist.parse_deliveries("order,state,date\n#1,returned,2026-07-10\n#1,delivered,2026-07-08\n"
                                    "#2,delivered,2026-07-09\n#2,refused,2026-07-07\n", hist.Reader())
        self.assertEqual(got, {"#1": ("refused", at(2026, 7, 10, 12, 0), True),
                               "#2": ("delivered", at(2026, 7, 9, 12, 0), False)})

    def test_10_m14_an_ios_line_marked_u200e_is_a_system_line(self):
        counts = Counter()
        chat = hist.parse_whatsapp("[05/07/2026, 10:00:00] Demo Mona: " + chr(0x200E) + "Your security code changed.\n"
                                   "[05/07/2026, 10:01:00] Demo Mona: مساء الخير", TEAM, counts=counts)
        self.assertEqual(([m.text for m in chat.messages], counts["system lines"]), (["مساء الخير"], 1))

    def test_10_m10_a_message_or_order_before_2000_is_not_written(self):
        old, new = at(1999, 12, 31, 10, 0), at(2026, 7, 5, 10, 0)
        c = hist.Chat("whatsapp", "k", 0, [hist.Message(old, False, "قديم"), hist.Message(new, False, "جديد")],
                      phone="201000000045")
        counts = Counter()
        cases = imp.plan([c], {"#1": hist.Order("#1", old + 60, {"201000000045"})}, {}, now=NOW, counts=counts)
        self.assertEqual([s["message"].text for s in cases[0]["steps"]], ["جديد"])
        self.assertEqual((cases[0]["rows"], counts["rows outside time"]), ([], 2))

    def test_10_m06_an_instagram_time_out_of_bounds_is_a_bad_line(self):
        ok = int(at(2026, 8, 1, 12, 0) * 1000)
        doc = {"messages": [{"sender_name": "Demo Mona", "timestamp_ms": ms, "content": text}
                            for ms, text in ((10 ** 20, "huge"), (1000, "early"), (ok, "ok"))]}
        counts = Counter()
        chat = hist.parse_instagram([doc], TEAM, key="t", counts=counts)
        self.assertEqual(([m.text for m in chat.messages], counts["bad lines"]), (["ok"], 2))

    def test_10_m13_a_result_joins_its_orders_chat_across_imports(self):
        a = ["05/07/2026, 10:00 - Demo Mona: عايز الجزمة السودا ورقمي 01000000045", "05/07/2026, 10:05 - Beyond the Limits: تمام"]
        b = ["05/07/2026, 12:00 - Demo Hala: ورقمي 01000000045 برضه"]
        first = self.wa("a.txt", *a, where="wa1")
        second = self.wa("a.txt", *a, where="wa2")
        self.wa("b.txt", *b, where="wa2")
        (self.tmp / "o.csv").write_text("Name,Created at,Phone\n#1,2026-07-05 14:00:00 +0300,01000000045\n",
                                        encoding="utf-8")
        (self.tmp / "d.csv").write_text("order,state,date\n#1,delivered,2026-07-08\n", encoding="utf-8")
        imp.run(self.db, PLUG, whatsapp=first, orders=self.tmp / "o.csv", team=TEAM, now=NOW)
        imp.run(self.db, PLUG, whatsapp=second, orders=self.tmp / "o.csv", deliveries=self.tmp / "d.csv", team=TEAM,
                now=NOW)
        chats, orders, _ = imp.read_all(hist.Reader(), whatsapp=second, orders=self.tmp / "o.csv", team=TEAM)
        now_on = next(c["case"] for c in imp.plan(chats, orders, {}, now=NOW, counts=Counter()) if c["orders"])
        rows = Log(self.open(), PLUG).query()
        created = next(r["case_id"] for r in rows if r["result"] == "order_created")
        delivered = next(r["case_id"] for r in rows if r["result"] == "delivered")
        self.assertNotEqual(now_on, created)  # in the second import the order fits the later chat
        self.assertEqual(delivered, created)

    def test_10_m08_a_team_photo_with_a_caption_is_not_a_candidate(self):
        t = at(2026, 7, 5, 10, 0)
        cases = good_cases(hist.Message(t, True, "دي الجزمة اللي حضرتك طلبتها", "image"),
                           hist.Message(t + 1, True, "أهلا بيكي يا فندم"))
        self.assertEqual(texts(cases), ["أهلا بيكي يا فندم"])

    def test_11_with_no_deliveries_file_orders_stay_pending_and_the_report_says_so(self):
        rep = self.demo(deliveries=None)
        rows = Log(self.open(), PLUG).query()
        self.assertEqual([r for r in rows if r["result"] in ("delivered", "refused")], [])
        self.assertEqual(sum(r["result"] == "order_created" for r in rows), 18)
        said = imp.text(rep)
        self.assertIn("No deliveries file: no delivered or refused written for 18 orders; this plug does not "
                      "decide on them, so their cases do not wait", said)
        self.assertNotIn("pending", said)
        held = imp.text(self.demo(plug=delivery_plug(), deliveries=None, dry_run=True))
        self.assertIn("No deliveries file: 18 orders stay pending, with no delivered or refused written for them", held)
        self.assertNotIn("No deliveries file", imp.text(self.demo()))

    def test_11_an_order_with_no_deliveries_file_stays_pending_in_the_study_until_its_result_comes(self):
        self.demo(deliveries=None)
        late = NOW + 365 * 86400  # long after every deciding window
        cases = Log(self.open(), PLUG).window(0, late)
        unknown = [rows for rows in cases.values()
                   if any((r["detail"] or {}).get("result_unknown") for r in rows)]
        self.assertEqual(len(unknown), 17)  # every chat joined to an order
        self.assertEqual({settle(delivery_plug(), rows, late)[0] for rows in unknown}, {PENDING})
        self.assertEqual({settle(PLUG, rows, late)[0] for rows in unknown}, {GOOD})  # the order settles it
        self.demo()  # the deliveries file comes later
        cases = Log(self.open(), PLUG).window(0, late)
        after = {settle(delivery_plug(), rows, late)[0] for rows in cases.values()
                 if any((r["detail"] or {}).get("result_unknown") for r in rows)}
        self.assertNotIn(PENDING, after)


class FakeHistory(unittest.TestCase):
    def test_the_generator_writes_the_same_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run([sys.executable, "-I", str(ROOT / "demo" / "make_history.py"), "--out", tmp],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            made = {p.relative_to(tmp): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
            kept = {p.relative_to(DEMO): p.read_bytes() for p in DEMO.rglob("*") if p.is_file()}
            self.assertEqual(sorted(made), sorted(kept))
            for path in made:
                self.assertEqual(made[path], kept[path], str(path))


if __name__ == "__main__":
    unittest.main()
