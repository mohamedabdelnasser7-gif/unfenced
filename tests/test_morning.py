"""Step 7: the morning page, on the made-up plugs and in-memory or temporary databases. Every
field is escaped; a change needs the page's token, a Host and an Origin of 127.0.0.1 or
localhost; Stop, Edit, Yes and No change the lessons as the engine allows; at most 5 cards,
the most to gain first; every link is on the page; the static copy has no forms. No model,
no network beyond 127.0.0.1."""
import contextlib
import http.client
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from engine import risk
from engine.lessons import KEPT, PULLED, TRYING, WAITING, Lessons
from engine.log import Log
from engine.trial import Trials
from kit.db import Db
from reflection import morning as mod
from tests import plugs
from tests.kept import kept_lesson

DAY = 86400
NOW = 1_800_000_000.0
END = NOW + 7 * DAY


def always_low(text, high_about, low_about):
    return risk.LOW


def bed_plug():
    """The waterer with a serious result, so a trial can ping."""
    data = plugs.changed(plugs.WATERER)
    data["results"]["flooded"] = {"speed": "fast", "shows_in_days": [0, 0], "after": "water", "about": "The bed flooded."}
    data["harm"] = {"results": ["ran_off", "flooded"], "about": "Wasted water.", "serious": ["flooded"]}
    return data


def card(lid, sure, n1, g1, n0, g0):
    """A study card as the night report saves it, with its numbers."""
    return {"lesson_id": lid, "sure": sure, "moves": {"result": "grew", "shows_in_days": [3, 10]},
            "cases": {"with": n1, "without": n0, "total": n1 + n0, "good_with": g1, "good_without": g0}}


class Base(unittest.TestCase):
    """A waterer and a fan in one database, a folder for night reports, and the page."""

    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.plug = plugs.load(bed_plug(), self)
        self.fan = plugs.load(plugs.FAN, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)
        self.fans = Lessons(self.db, self.fan, judge=always_low)
        self.morning = mod.Morning(self.db, [self.plug, self.fan], reports=self.dir)

    def high(self, text, stages=("seedling",), lessons=None):
        """A lesson with a number in it: high risk for these plugs, so it waits for a yes."""
        lid = (lessons or self.lessons).propose(text, list(stages), sources=[], now=NOW)
        self.assertEqual((lessons or self.lessons).get(lid)["state"], WAITING)
        return lid

    def report(self, agent, until, **parts):
        rep = {"agent": agent, "window": {"since": until - 14 * DAY, "until": until}, "cards": [], "notes": [],
               "links": {"lessons": []}, "trials": {"trials": []}}
        rep.update(parts)
        (self.dir / f"night-{agent}-{int(until)}.json").write_text(json.dumps(rep), encoding="utf-8")

    def page(self, now=NOW, token="t0ken"):
        return mod.render(self.morning.view(now), token=token)


class Escape(Base):
    def test_a_lesson_with_a_script_renders_inert(self):
        bad = self.high('<script>alert(1)</script> "x" & <b>bold</b>')
        kept = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], '<img src=x onerror=alert(1)>',
                                yes_by="<i>tester</i>", now=NOW)
        self.report("waterer", NOW, notes=["<script>steal()</script>"],
                    links={"lessons": [{"lesson_id": kept, "from_agent": "waterer", "cases": ["<u>c1</u>"]}]})
        page = self.page()
        self.assertIn(f'id="l{bad}"', page)
        for raw in ("<script", "<img", "<i>", "<u>", "<b>"):
            self.assertNotIn(raw, page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &quot;x&quot; &amp; &lt;b&gt;", page)
        self.assertIn("&lt;script&gt;steal()&lt;/script&gt;", page)
        self.assertIn('value="&lt;script&gt;alert(1)&lt;/script&gt; &quot;x&quot;', page)  # the Edit field too


class Server(Base):
    """The page served on 127.0.0.1 on a free port, started and stopped by each test."""

    def setUp(self):
        super().setUp()
        self.live = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="tester", now=NOW)
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

    def call(self, method, path, fields=None, *, host=None, origin="same"):
        headers = {"Host": host or self.here}
        body = None
        if fields is not None:
            body = urllib.parse.urlencode(fields)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if origin == "same":
            headers["Origin"] = f"http://{self.here}"
        elif origin is not None:
            headers["Origin"] = origin
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body, headers)
            r = conn.getresponse()
            return r.status, r.read().decode("utf-8"), dict(r.getheaders())
        finally:
            conn.close()

    def stop_form(self, **extra):
        return dict({"token": self.server.token, "lesson": str(self.live), "why": "It drowned the roots."}, **extra)

    def state(self):
        return self.lessons.get(self.live)["state"]

    def test_the_page_carries_its_token_and_a_stop_from_it_works(self):
        status, page, headers = self.call("GET", "/", origin=None)
        self.assertEqual(status, 200)
        self.assertIn(f'name="token" value="{self.server.token}"', page)
        self.assertTrue(headers["Content-Security-Policy"].startswith("default-src 'none'"))
        status, _, headers = self.call("POST", "/stop", self.stop_form())
        self.assertEqual((status, headers["Location"]), (303, "/"))
        self.assertEqual(self.state(), PULLED)

    def test_the_referrer_policy_lets_chrome_send_the_pages_origin(self):
        # Chrome sends "Origin: null" on a page's own form posts under no-referrer, and every answer is refused
        for method, path, fields in (("GET", "/", None), ("POST", "/stop", self.stop_form())):
            with self.subTest(method=method):
                self.assertEqual(self.call(method, path, fields)[2]["Referrer-Policy"], "same-origin")

    def test_a_yes_from_a_page_drawn_before_a_clash_pulls_nothing(self):
        new = Lessons(self.db, self.plug, judge=always_low).propose("Water the grown beds 3 times.", ["grown"],
                                                                    sources=[], now=NOW)
        status, page, _ = self.call("GET", "/", origin=None)
        self.assertIn(f'name="lesson" value="{new}"><input type="hidden" name="shown" value="">', page)
        self.lessons.clash(new, self.live, now=NOW)  # noted after the page was drawn
        fields = {"token": self.server.token, "lesson": str(new), "shown": ""}
        self.assertEqual(self.call("POST", "/yes", fields)[0], 303)
        self.assertEqual((self.state(), self.lessons.get(new)["state"]), (KEPT, WAITING))
        self.assertIn("changed after the page was drawn", self.call("GET", "/", origin=None)[1])

    def test_a_post_without_the_token_or_with_a_wrong_one_is_refused(self):
        form = self.stop_form()
        del form["token"]
        for fields in (form, self.stop_form(token="guess"), self.stop_form(token=""),
                       dict(self.stop_form(), token=[self.server.token, "x"])):
            with self.subTest(token=fields.get("token")):
                body = urllib.parse.urlencode(fields, doseq=True)
                self.assertEqual(self.raw_post(body), 403)
                self.assertEqual(self.state(), KEPT)

    def raw_post(self, body, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", "/stop", body, dict({"Host": self.here, "Origin": f"http://{self.here}",
                                                      "Content-Type": "application/x-www-form-urlencoded"},
                                                     **(headers or {})))
            r = conn.getresponse()
            r.read()
            return r.status
        finally:
            conn.close()

    def test_a_post_from_another_origin_is_refused(self):
        for origin in ("http://evil.example", None, "null", f"http://127.0.0.1:{self.port + 1}",
                       f"https://{self.here}", f"http://{self.here}.evil.example"):
            with self.subTest(origin=origin):
                status, _, _ = self.call("POST", "/stop", self.stop_form(), origin=origin)
                self.assertEqual(status, 403)
                self.assertEqual(self.state(), KEPT)
        status, _, _ = self.call("POST", "/stop", self.stop_form(), origin=f"http://localhost:{self.port}",
                                 host=f"localhost:{self.port}")
        self.assertEqual((status, self.state()), (303, PULLED))

    def test_another_host_is_refused_for_reading_and_for_changing(self):
        for host in ("evil.example", f"evil.example:{self.port}", f"127.0.0.1:{self.port + 1}", "127.0.0.1"):
            with self.subTest(host=host):
                status, page, _ = self.call("GET", "/", host=host, origin=None)
                self.assertEqual(status, 403)
                self.assertNotIn(self.server.token, page)
                self.assertEqual(self.call("POST", "/stop", self.stop_form(), host=host)[0], 403)
                self.assertEqual(self.state(), KEPT)

    def test_a_body_too_long_a_bad_length_a_bad_type_or_too_many_fields_is_refused(self):
        form = urllib.parse.urlencode(self.stop_form())
        for body, headers, want in ((urllib.parse.urlencode(self.stop_form(why="x" * mod.MAX_BODY)), {}, 413),
                                    (form, {"Content-Length": "-1"}, 413),
                                    (form, {"Content-Type": "text/plain"}, 415),
                                    (form + "&a=1&b=2&c=3&d=4&e=5&f=6", {}, 400)):  # 9 fields, 8 at most
            with self.subTest(want=want, headers=headers):
                self.assertEqual(self.raw_post(body, headers), want)
                self.assertEqual(self.state(), KEPT)
        self.assertEqual((self.raw_post(form), self.state()), (303, PULLED))

    def test_a_field_given_twice_is_refused(self):
        body = urllib.parse.urlencode(dict(self.stop_form(), lesson=[str(self.live)] * 2), doseq=True)
        self.assertEqual(self.raw_post(body), 303)
        self.assertEqual(self.state(), KEPT)
        self.assertIn("One lesson, please.", self.call("GET", "/", origin=None)[1])

    def test_only_the_page_itself_is_served(self):
        status, page, _ = self.call("GET", "/morning", origin=None)
        self.assertEqual(status, 404)
        self.assertNotIn(self.server.token, page)
        self.assertEqual(self.call("GET", "/?from=bookmark", origin=None)[0], 200)

    def test_a_silent_client_is_let_go_and_the_page_is_never_framed(self):
        self.assertTrue(0 < self.server.RequestHandlerClass.timeout <= 10)  # seconds a silent client may hold it
        headers = self.call("GET", "/", origin=None)[2]
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])


class Answers(Base):
    def setUp(self):
        super().setUp()
        self.live = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="tester", now=NOW)

    def test_stop_pulls_a_live_lesson_with_its_why(self):
        for why in ("", "two\nlines", "x" * 301):
            with self.subTest(why=why[:10]), self.assertRaises(mod.Refused):
                self.morning.stop(self.live, why, now=NOW + 1)
        self.assertEqual(self.lessons.get(self.live)["state"], KEPT)
        self.morning.stop(self.live, "  It drowned the roots. ", now=NOW + 1)
        les = self.lessons.get(self.live)
        self.assertEqual((les["state"], les["pulled_why"]), (PULLED, "stopped by the owner: It drowned the roots."))
        card_ = self.high("Water bed 3 twice.")
        with self.assertRaisesRegex(mod.Refused, "not live"):
            self.morning.stop(card_, "No.", now=NOW + 1)

    def test_edit_pulls_the_lesson_and_adds_the_new_line_linked_to_it(self):
        with mock.patch.object(mod, "person_line", wraps=mod.person_line) as made:
            said = self.morning.edit(self.live, "Water the grown beds at dusk.", now=NOW + 1)
        self.assertEqual(made.call_count, 1)  # what a person's line becomes is decided in one place
        new = max(les["id"] for les in self.lessons.mine())
        old, les = self.lessons.get(self.live), self.lessons.get(new)
        self.assertEqual((old["state"], old["pulled_why"]), (PULLED, f"edited by the owner into lesson {new}"))
        self.assertEqual((les["state"], les["text"], les["stages"], les["yes_by"]),
                         (TRYING, "Water the grown beds at dusk.", ["grown"], "the owner"))
        self.assertEqual((les["origin"], said), ("person", f"Lesson {self.live} edited: the new line is lesson {new}. "
                                                           "It is on trial."))
        self.assertEqual(les["source"], f'edited by the owner from lesson {self.live}: "Water the grown beds deeply."')
        items = {i["id"]: i for a in self.morning.view(NOW + 2)["agents"] for i in a["live"] + a["pulled"]}
        self.assertIn({"text": f"edited from lesson {self.live}", "to": self.live}, items[new]["links"])
        self.assertIn({"text": f"edited into lesson {new}", "to": new}, items[self.live]["links"])
        page = self.page(NOW + 2)
        self.assertIn(f'<a href="#l{self.live}">edited from lesson {self.live}</a>', page)
        self.assertIn(f'id="l{self.live}"', page)

    def test_edit_refuses_a_bad_or_unchanged_line_and_changes_nothing(self):
        for line in ("Water the grown beds deeply.", "", "one\ntwo", "x" * 301):
            with self.subTest(line=line[:10]), self.assertRaises(mod.Refused):
                self.morning.edit(self.live, line, now=NOW + 1)
        self.assertEqual((self.lessons.get(self.live)["state"], len(self.lessons.mine())), (KEPT, 1))

    def test_an_edit_whose_pull_fails_leaves_no_new_line(self):
        for name, how in (("error", {"side_effect": sqlite3.OperationalError("database is locked")}),
                          ("pulled meanwhile", {"return_value": False})):
            with self.subTest(how=name):
                with mock.patch.object(Lessons, "pull", **how), \
                        self.assertRaises((mod.Refused, sqlite3.OperationalError)):
                    self.morning.edit(self.live, "Water the grown beds at dusk.", now=NOW + 1)
                self.assertEqual([(les["id"], les["state"]) for les in self.lessons.mine()], [(self.live, KEPT)])
        self.morning.edit(self.live, "Water the grown beds at dusk.", now=NOW + 2)  # a second Edit adds one line
        self.assertEqual([les["state"] for les in self.lessons.mine()], [PULLED, TRYING])

    def test_a_yes_whose_trial_fails_to_start_pulls_nothing(self):
        old = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        new = self.high("Water the seedlings 2 times, slowly.")
        self.lessons.clash(new, old, now=NOW)
        with mock.patch.object(Lessons, "approve", side_effect=sqlite3.OperationalError("database is locked")), \
                self.assertRaises(sqlite3.OperationalError):
            self.morning.yes(new, shown=str(old), now=NOW + 1)
        self.assertEqual((self.lessons.get(old)["state"], self.lessons.get(new)["state"]), (TRYING, WAITING))

    def test_yes_puts_a_card_on_trial_and_no_pulls_one(self):
        yes, no = self.high("Water bed 3 twice."), self.high("Water bed 4 at noon.", ["grown"])
        self.morning.yes(yes, now=NOW + 1)
        les = self.lessons.get(yes)
        self.assertEqual((les["state"], les["yes_by"]), (TRYING, "the owner"))
        with self.assertRaisesRegex(mod.Refused, "does not wait for a yes"):
            self.morning.yes(yes, now=NOW + 2)
        self.morning.no(no, "Too sure of a number.", now=NOW + 1)
        les = self.lessons.get(no)
        self.assertEqual((les["state"], les["pulled_why"], les["yes_at"]),
                         (PULLED, "no from the owner: Too sure of a number.", None))
        with self.assertRaisesRegex(mod.Refused, "does not wait for a yes"):
            self.morning.no(self.live, "", now=NOW + 1)
        self.assertEqual(self.lessons.get(self.live)["state"], KEPT)

    def test_a_replace_card_shows_both_lines_and_its_yes_pulls_the_old_one(self):
        old = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        new = self.high("Water the seedlings 2 times, slowly.")
        self.lessons.clash(new, old, now=NOW)
        view = self.morning.view(NOW + 1)
        [c] = view["cards"]
        self.assertEqual((c["id"], c["replaces"]), (new, [{"id": old, "text": "Water the seedlings slowly.",
                                                           "state": TRYING}]))
        page = mod.render(view, token="t")
        self.assertIn("Replace it? It would pull lesson", page)
        self.assertIn('<span class="old" dir="auto">Water the seedlings slowly.</span>', page)
        self.assertIn("Yes, replace it", page)
        self.assertIn(f'name="lesson" value="{new}"><input type="hidden" name="shown" value="{old}">', page)
        said = self.morning.yes(new, shown=str(old), now=NOW + 2)
        self.assertEqual(said, f"Lesson {new}: yes. It is on trial. Pulled: lesson {old}.")
        self.assertEqual(self.lessons.get(old)["pulled_why"], f"replaced by lesson {new}")
        self.assertEqual(self.lessons.get(new)["state"], TRYING)

    def test_a_yes_names_only_the_lines_it_pulled(self):
        one = kept_lesson(self.lessons, "Water the seedlings slowly.", ["seedling"], yes_by="tester", now=NOW)
        two = kept_lesson(self.lessons, "Water the seedlings at the root.", ["seedling"], yes_by="tester", now=NOW)
        new = self.high("Water the seedlings 2 times, slowly.")
        self.lessons.clash(new, one, now=NOW)
        self.lessons.clash(new, two, now=NOW)
        self.morning.stop(two, "It was wrong.", now=NOW + 1)  # after the page was drawn
        said = self.morning.yes(new, shown=f"{one},{two}", now=NOW + 2)
        self.assertEqual(said, f"Lesson {new}: yes. It is on trial. Pulled: lesson {one}.")
        self.assertEqual(self.lessons.get(two)["pulled_why"], "stopped by the owner: It was wrong.")

    def test_a_yes_on_a_card_that_names_other_lines_now_does_nothing(self):
        old = kept_lesson(self.lessons, "Water the seedlings slowly.", ["seedling"], yes_by="tester", now=NOW)
        new = self.high("Water the seedlings 2 times, slowly.")
        self.lessons.clash(new, old, now=NOW)  # noted after the page was drawn with no clash
        for shown in ("", f"{old},{old}", "x", str(old + 99)):
            with self.subTest(shown=shown), self.assertRaises(mod.Refused):
                self.morning.yes(new, shown=shown, now=NOW + 1)
            self.assertEqual((self.lessons.get(old)["state"], self.lessons.get(new)["state"]), (KEPT, WAITING))

    def test_a_replace_card_is_not_edited(self):
        old = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        new = self.high("Water the seedlings 2 times, slowly.")
        self.lessons.clash(new, old, now=NOW)
        with self.assertRaisesRegex(mod.Refused, f"asks to replace lesson {old}, so it is not edited here"):
            self.morning.edit(new, "Water the seedlings 3 times, slowly.", now=NOW + 1)
        self.assertEqual([(les["id"], les["state"]) for les in self.lessons.mine()],
                         [(self.live, KEPT), (old, TRYING), (new, WAITING)])
        page = self.page(NOW + 1)
        self.assertNotIn(f'action="/edit"><input type="hidden" name="token" value="t0ken"><input type="hidden" '
                         f'name="lesson" value="{new}">', page)
        self.assertIn(f'name="lesson" value="{old}">', page)  # the live line keeps its Edit

    def test_a_live_line_named_on_a_waiting_card_is_not_edited(self):  # review t261029m round 2, finding 1
        new = self.high("Water the grown beds 2 times at dusk.")
        self.lessons.clash(new, self.live, now=NOW)
        with self.assertRaisesRegex(mod.Refused, f"named on the card of lesson {new}, so it is not edited here"):
            self.morning.edit(self.live, "Water the grown beds at dusk.", now=NOW + 1)
        self.assertEqual([(les["id"], les["state"]) for les in self.lessons.mine()],
                         [(self.live, KEPT), (new, WAITING)])
        self.morning.no(new, "", now=NOW + 2)  # once the card is answered, the line can be edited
        self.morning.edit(self.live, "Water the grown beds at dusk.", now=NOW + 3)
        self.assertEqual(self.lessons.get(self.live)["state"], PULLED)

    def test_an_agent_with_no_plug_is_shown_without_buttons(self):
        ledger = Lessons(self.db, plugs.load(plugs.LEDGER, self), judge=always_low)
        lid = kept_lesson(ledger, "Post the rent first.", ["open"], yes_by="tester", now=NOW)
        [a] = [a for a in self.morning.view(NOW)["agents"] if a["agent"] == "ledger"]
        self.assertFalse(a["buttons"])
        with self.assertRaisesRegex(mod.Refused, "No plug for ledger"):
            self.morning.stop(lid, "No.", now=NOW)
        self.assertNotIn(f'name="lesson" value="{lid}"', self.page())


class Cards(Base):
    def test_at_most_five_cards_the_most_to_gain_first_across_agents(self):
        ids = [self.high(f"Water bed {n} twice.") for n in range(1, 7)]
        fan = self.high("Spin the fan 3 times at noon.", lessons=self.fans)
        l1, l2, l3, l4, l5, l6 = ids
        self.report("waterer", NOW, cards=[card(l1, 0.80, 20, 15, 20, 10), card(l2, 0.95, 20, 18, 20, 8),
                                           card(l3, 0.90, 10, 8, 10, 4), card(l4, 0.76, 30, 20, 30, 18),
                                           card(l5, 0.85, 40, 30, 40, 20)])
        self.report("fan", NOW, cards=[card(fan, 0.99, 6, 6, 6, 1)])
        view = self.morning.view(NOW)
        # gains: fan .62, l2 .43, l3 .30, l5 .20, l1 .18, l4 .05; l6 has no numbers
        self.assertEqual([c["id"] for c in view["cards"]], [fan, l2, l3, l5, l1])
        self.assertEqual(view["more"], 2)
        page = mod.render(view, token="t")
        self.assertEqual(page.count('action="/yes"'), 5)
        self.assertIn("2 more wait for a yes", page)
        self.assertIn("the chance it is better is 99%", page)

    def test_five_cards_at_a_time_and_an_answered_card_makes_room(self):
        ids = [self.high(f"Water bed {n} twice.") for n in range(1, 8)]
        self.assertEqual(([c["id"] for c in self.morning.view(NOW)["cards"]], self.morning.view(NOW)["more"]),
                         (ids[:5], 2))
        self.morning.no(ids[0], now=NOW + 1)
        self.assertEqual([c["id"] for c in self.morning.view(NOW + 1)["cards"]], ids[1:6])

    def test_cards_with_no_numbers_come_last_the_oldest_first(self):
        a, b, c = (self.high(f"Water bed {n} at dusk.") for n in (1, 2, 3))
        self.report("waterer", NOW, cards=[card(c, 0.76, 10, 6, 10, 5)])
        self.assertEqual([x["id"] for x in self.morning.view(NOW)["cards"]], [c, a, b])

    def test_a_lesson_waiting_its_turn_is_not_a_card(self):
        first = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        turn = self.lessons.propose("Water the seedlings at the root.", ["seedling"], sources=[], now=NOW)
        self.assertEqual(self.lessons.waits_for(turn, NOW), [first])
        view = self.morning.view(NOW)
        self.assertEqual(view["cards"], [])
        [item] = [i for a in view["agents"] for i in a["waiting"]]
        self.assertEqual((item["id"], item["status"]), (turn, "waits its turn"))
        with self.assertRaises(mod.Refused):
            self.morning.yes(turn, now=NOW)


class Links(Base):
    """A lesson with a trial that ended kept or pulled and pinged, and a lesson adapted from the fan."""

    def setUp(self):
        super().setUp()
        self.lid = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        log = Log(self.db, self.plug)
        n = 0
        for given, good, count in ((True, True, 16), (True, False, 4), (False, True, 20), (False, False, 20)):
            for _ in range(count):
                n += 1
                log.act(f"bed{n}", "water", result="soaked", stage="seedling", lessons=[self.lid] if given else [],
                        at=NOW + DAY)
                log.result(f"bed{n}", "grew" if good else "wilted", at=NOW + 4 * DAY)
        log.act("bed99", "water", result="flooded", stage="seedling", lessons=[self.lid], at=NOW + DAY)
        log.result("bed99", "grew", at=NOW + 4 * DAY)
        Trials(self.db, self.plug, lessons=self.lessons).check(END)
        self.trials = Trials(self.db, self.plug, lessons=self.lessons)
        self.src = kept_lesson(self.fans, "Spin the fan slowly at dawn.", ["all"], yes_by="tester", now=NOW)
        self.adapted = self.lessons.adapt("Water the grown beds slowly at dawn.", ["grown"], sources=[],
                                          source=f'adapted fully from fan lesson {self.src}: "Spin the fan slowly."',
                                          source_lesson_id=self.src, now=END)
        self.report("waterer", END, links={"lessons": [
            {"lesson_id": self.lid, "state": "trying", "from_agent": "waterer", "cases": ["bed1", "bed2", "bed17"],
             "from_lesson": None, "waits_for": []},
            {"lesson_id": self.adapted, "state": "trying", "from_agent": "fan", "cases": [],
             "from_lesson": self.src, "waits_for": []}]})

    def test_every_link_is_on_the_page(self):
        page = self.page(END + DAY)
        self.assertIn("The 3 cases behind it are named in the saved night report.", page)
        for case_id in ("bed1, bed2", "bed17", "bed99"):  # no raw case id on the page
            self.assertNotIn(case_id, page)
        self.assertIn(f'<a href="#l{self.src}">adapted from fan lesson {self.src}</a>', page)
        self.assertIn(f'id="l{self.src}"', page)
        self.assertNotIn("learned from fan cases", page)  # one link for one source, not two
        [verdict] = self.trials.marks(self.lid, "verdict")
        [ping] = self.trials.marks(self.lid, "ping")
        self.assertIn(f"verdict mark {verdict['id']}", page)
        self.assertIn(f"ping mark {ping['id']}", page)
        self.assertIn(f"ping mark {ping['id']}, ", page)
        self.assertIn(f": row {ping['row_id']}, flooded. ", page)
        for side in ("with", "without"):
            c = next(c for c in verdict["detail"][side]["list"] if c["row"] is not None)
            self.assertIn(f"{c['status']}, settled by row {c['row']}", page)
            self.assertNotIn(f"case {c['case']}", page)
        self.assertIn(f'id="t{self.lid}"', page)
        self.assertIn(f'href="#t{self.lid}"', page)
        self.assertIn(f"(from verdict mark {verdict['id']})", page)

    def test_a_running_trial_shows_its_days_left(self):
        [t] = [t for a in self.morning.view(END + DAY)["agents"] for t in a["trials"] if t["id"] == self.adapted]
        self.assertEqual(t["status"], "still running, about 6 days left")


class Guards(Base):
    """The guards a reviewer's mutants showed had no failing test."""

    def setUp(self):
        super().setUp()
        self.live = kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="tester", now=NOW)

    def test_edit_refuses_a_pulled_lesson_and_one_waiting_its_turn(self):
        self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        turn = self.lessons.propose("Water the seedlings at the root.", ["seedling"], sources=[], now=NOW)
        self.morning.stop(self.live, "Wrong.", now=NOW + 1)
        for lid in (self.live, turn):
            with self.subTest(lid=lid), self.assertRaisesRegex(mod.Refused, "neither live nor waiting"):
                self.morning.edit(lid, "Water the seedlings at dusk.", now=NOW + 1)
        self.assertEqual(len(self.lessons.mine()), 3)

    def test_a_lesson_with_a_yes_is_not_a_card_even_with_no_turn_row(self):
        first = self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)
        lid = self.high("Water bed 3 twice.")
        self.morning.yes(lid, now=NOW + 1)
        self.assertEqual(self.lessons.waits_for(lid, NOW + 1), [first])
        with self.db.tx() as c:
            c.execute("DELETE FROM trials WHERE lesson_id = ?", (lid,))
        for answer in (self.morning.no, self.morning.yes):
            with self.subTest(answer=answer.__name__), self.assertRaisesRegex(mod.Refused, "does not wait for a yes"):
                answer(lid, now=NOW + 2)
        self.assertEqual(self.lessons.get(lid)["state"], WAITING)

    def test_an_answer_holds_the_write_lock_from_its_first_read(self):
        path = self.dir / "agents.db"
        one, two = Db(path), Db(path)
        self.addCleanup(one.close)
        self.addCleanup(two.close)
        live = kept_lesson(Lessons(one, self.plug, judge=always_low), "Water the beds.", ["grown"], yes_by="tester", now=NOW)
        morning = mod.Morning(one, [self.plug])
        two.conn.execute("PRAGMA busy_timeout = 0")
        tried, read = [], mod._one_line

        def another_night_writes(*a, **k):  # runs after the answer read the lesson
            try:
                with two.tx() as c:
                    c.execute("UPDATE lessons SET score = 1 WHERE id = ?", (live,))
                tried.append("written")
            except sqlite3.OperationalError as e:
                tried.append(str(e))
            return read(*a, **k)
        with mock.patch.object(mod, "_one_line", another_night_writes):
            morning.stop(live, "Wrong.", now=NOW + 1)
        self.assertEqual(tried, ["database is locked"])
        card = Lessons(one, self.plug, judge=lambda *a: risk.HIGH).propose("Water bed 3 twice.", ["grown"],
                                                                           sources=[], now=NOW)
        with mock.patch.object(mod, "_one_line", another_night_writes):  # review t261029m round 2, finding 2
            morning.no(card, "", now=NOW + 1)
        self.assertEqual(tried, ["database is locked", "database is locked"])

    def test_the_page_rebuilds_an_old_marks_table_when_it_opens(self):  # review t261029m round 2, finding 3
        db = Db(":memory:")
        self.addCleanup(db.close)
        lid = kept_lesson(Lessons(db, self.plug, judge=always_low), "Water the beds.", ["grown"], yes_by="tester", now=NOW)
        db.script("CREATE TABLE trial_marks (id INTEGER PRIMARY KEY, agent TEXT NOT NULL, lesson_id INTEGER NOT NULL "
                  "REFERENCES lessons (id), kind TEXT NOT NULL CHECK (kind IN ('limit', 'paused', 'ping', 'verdict', "
                  "'sent')), case_id TEXT, row_id INTEGER, value REAL, by TEXT, detail TEXT, at REAL NOT NULL);")
        with db.tx() as c:
            c.execute("INSERT INTO trial_marks (id, agent, lesson_id, kind, at) VALUES (7, ?, ?, 'sent', 0)",
                      (self.plug.agent, lid))
        mod.Morning(db, [self.plug])
        with db.tx() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT id, kind FROM trial_marks")], [(7, "reported")])

    def test_a_report_gives_numbers_only_to_its_own_agents_cards(self):
        fan = self.high("Spin the fan 3 times at noon.", lessons=self.fans)
        self.report("waterer", NOW, cards=[card(fan, 0.99, 6, 6, 6, 1)])
        [c] = self.morning.view(NOW)["cards"]
        self.assertEqual((c["id"], c["numbers"]), (fan, None))

    def test_a_report_too_big_is_skipped_and_named(self):
        lid = self.high("Water bed 3 twice.")
        self.report("waterer", NOW, cards=[card(lid, 0.9, 10, 8, 10, 4)])
        with mock.patch.object(mod, "MAX_REPORT", 100):
            view = self.morning.view(NOW)
        self.assertIsNone(view["cards"][0]["numbers"])
        self.assertEqual(view["problems"], [f"A saved night report could not be read: night-waterer-{int(NOW)}.json"])

    def test_an_agent_with_no_plug_has_no_cards(self):
        ledger = Lessons(self.db, plugs.load(plugs.LEDGER, self), judge=always_low)
        lid = ledger.propose("Post the rent first.", ["open"], sources=[], trial=False, now=NOW)
        self.assertEqual(ledger.get(lid)["state"], WAITING)
        self.assertEqual(self.morning.view(NOW)["cards"], [])

    def test_numbers_that_cannot_be_are_read_as_none(self):
        self.assertIsNotNone(mod._numbers(card(1, 0.9, 10, 8, 10, 4)))
        for bad in (card(1, 1.5, 10, 8, 10, 4), card(1, -0.1, 10, 8, 10, 4), card(1, True, 10, 8, 10, 4),
                    card(1, 0.9, 10, 11, 10, 4), card(1, 0.9, 10, 8, 10, 11), card(1, 0.9, 10, 8, 10, -1)):
            with self.subTest(bad=bad):
                self.assertIsNone(mod._numbers(bad))

    def test_equal_gains_go_to_the_card_with_more_cases(self):
        a, b = self.high("Water bed 1 twice."), self.high("Water bed 2 twice.")
        self.report("waterer", NOW, cards=[card(a, 0.8, 10, 8, 10, 2), card(b, 0.8, 22, 17, 22, 5)])
        cards = self.morning.view(NOW)["cards"]
        self.assertEqual(cards[0]["numbers"]["gain"], cards[1]["numbers"]["gain"])
        self.assertEqual([c["id"] for c in cards], [b, a])


class Switches(Base):
    """The night's switches on the page, and a lesson Accept high risk started (fix round 1)."""
    READING = {"level": "fast", "share": 0.8, "days": 3,
               "accept_high": {"on": True, "by": "Mona", "until": NOW + 2 * DAY, "ran_out": False}}

    def a_lesson(self):  # the page draws an agent with at least one lesson
        self.lessons.propose("Water the seedlings slowly.", ["seedling"], sources=[], now=NOW)

    def test_the_page_names_the_switches_that_night(self):
        self.a_lesson()
        self.report("waterer", NOW, switches=self.READING)
        self.assertIn("Switches that night: trial level fast: 80% of cases for 3 days; Accept high risk on, turned on "
                      "by Mona, until Sun 17 Jan 2027, 10:00 Cairo.", self.page())

    def test_a_report_with_switches_that_cannot_be_read_shows_no_line_and_still_draws(self):
        bad = ({"level": "fast"}, {**self.READING, "accept_high": {"on": False, "ran_out": True, "until": "soon"}},
               {**self.READING, "share": "most"})
        self.a_lesson()
        for sw in bad:
            with self.subTest(sw=sw):
                self.report("waterer", NOW, switches=sw)
                page = self.page()
                self.assertNotIn("Switches that night", page)
                self.assertIn(f"night-waterer-{int(NOW)}.json", page)

    def test_the_page_opens_a_database_with_no_switches_table_and_no_plug(self):
        db = Db(":memory:")
        self.addCleanup(db.close)
        self.assertEqual(mod.Morning(db, [], reports=self.dir).view(NOW)["agents"], [])

    def test_a_lesson_accept_started_never_reads_as_a_persons_yes(self):
        self.lessons.switches.set_accept_high(True, "Mona", now=NOW)
        on = self.lessons.propose("Water bed 3 twice.", ["seedling"], sources=[], now=NOW)
        turn = self.lessons.propose("Water bed 4 at dusk.", ["seedling"], sources=[], now=NOW)
        kept = self.lessons.propose("Water bed 5 at dawn.", ["grown"], sources=[], now=NOW)
        self.assertEqual([self.lessons.get(i)["state"] for i in (on, turn, kept)], [TRYING, WAITING, TRYING])
        with self.db.tx() as c:
            c.execute("UPDATE lessons SET state = 'kept', share = 1.0 WHERE id = ?", (kept,))
        [a] = [a for a in self.morning.view(NOW + 1)["agents"] if a["agent"] == "waterer"]
        got = {i["id"]: (i["status"], i["why"]) for i in a["live"] + a["waiting"]}
        under = "Accept high risk (switched on by Mona)"
        self.assertEqual(got[on][0], "on trial")
        self.assertTrue(got[on][1].startswith(f"On trial, started under {under}, in 50% of cases until "), got[on][1])
        self.assertEqual(got[turn], ("waits its turn", f"One trial runs on a stage at a time; it waits behind lesson "
                                     f"{on}. It waits under {under}: it starts with no yes only if the switch is still "
                                     "on at its turn, else it waits for a yes."))
        self.assertEqual(got[kept], ("kept", f"Kept by its trial; it started under {under}."))
        for lid in (on, turn, kept):
            self.assertNotIn("'s yes", got[lid][1])


class Static(Base):
    def test_the_static_file_has_no_forms(self):
        self.high("Water bed 3 twice.")
        kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by="tester", now=NOW)
        out = self.dir / "morning.html"
        mod.write_html(self.morning, out)
        text = out.read_text(encoding="utf-8")
        self.assertIn("Water bed 3 twice.", text)
        self.assertIn("A static copy: no buttons.", text)
        for word in ("<form", "<button", 'name="token"', "<input"):
            self.assertNotIn(word, text)

    def test_the_command_writes_the_static_page(self):
        path = self.dir / "agents.db"
        db = Db(path)
        kept_lesson(Lessons(db, self.plug, judge=always_low), "Water the grown beds deeply.", ["grown"], yes_by="tester",
                                                     now=NOW)
        db.close()
        out = self.dir / "page.html"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--db", str(path), "--html", str(out)]), 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("Water the grown beds deeply.", text)
        self.assertNotIn("<form", text)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main(["--db", str(self.dir / "none.db"), "--html", str(out)]), 2)

    def test_the_served_page_takes_its_exams_with_the_database_given(self):
        """Review round 1, finding 10: the page's exams read the Arena wins next to the --db it was
        started with, so a page on another database never reruns the default one's wins."""
        path = self.dir / "agents.db"
        Db(path).close()
        seen = []

        class Server:
            server_address = ("127.0.0.1", 0)

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                seen.append("closed")

        with mock.patch.object(mod.env, "load"), mock.patch.dict(os.environ, {"MORNING_PORT": "0"}), \
                mock.patch.object(mod, "page_exams", side_effect=lambda plugs, morning, db=None: seen.append(db) or {}), \
                mock.patch.object(mod, "make_server", return_value=Server()), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["--db", str(path)]), 0)
        self.assertEqual(seen, [str(path), "closed"])


class PlainWhy(unittest.TestCase):
    def test_each_saved_reason_reads_in_plain_words(self):
        for saved, want in (
                ("amount: /[0-9]/", "it matches a pattern on the amount list"),
                ("price: cheap", 'the word "cheap" is on the price list'),
                ("tool: draft_order", "it names the tool draft_order"),
                ("core: phone number", "it has a phone number"),
                ("core: copied from source 2", "it copies words from the cases it came from"),
                ("judge: high", "the judge said high"),
                ("judge failed (TimeoutError), counted as high", "judge failed (TimeoutError), counted as high"),
                ("", "no reason saved")):
            with self.subTest(saved=saved):
                self.assertEqual(mod.plain_why(saved), want)

    def test_reasons_keep_their_order(self):
        self.assertEqual(mod.plain_why("core: link; amount: /[0-9]/"),
                         "it has a link; it matches a pattern on the amount list")

    def test_a_reason_that_reads_the_same_shows_once(self):
        saved = "; ".join(f"core: copied from source {n}" for n in range(21, 36)) + "; price: cheap"
        self.assertEqual(mod.plain_why(saved),
                         'it copies words from the cases it came from; the word "cheap" is on the price list')


if __name__ == "__main__":
    unittest.main()
