"""Call 16 and call 20 on the morning page: the trial level switch, Accept high risk with the
check mark that turns it off by itself, a waiting lesson's own level, and the locks that hold
whatever the switches say. The page's handlers are driven through its own server on 127.0.0.1
and through the Morning answers its routes call; the engine is the real one. The waterer
plug's levels are fast (0.8 of cases for 3 days) and careful (0.5 for 7 days). No model, no
network beyond 127.0.0.1."""
import http.client
import re
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

from engine import risk
from engine.lessons import DAY, TRYING, WAITING, Lessons
from engine.study import Study
from kit.db import Db
from reflection import PLUG as SALES
from reflection import morning as mod
from reflection import night as night_mod
from tests import plugs
from tests import study_fakes as fk

NOW = 1_800_000_000.0  # 15 Jan 2027 08:00 UTC
OWNER = mod.BY
LOW_A, LOW_B = "Visit the north bed first.", "Visit the grown beds last."
HIGH_A, HIGH_B = "Wash the pots with bleach first.", "Spray the pesticide at dusk."  # on the waterer's high list
COPY = "Visit the north bed first before noon."
CASE = "The gardener said visit the north bed first today."  # made up; shares five words in a row with COPY


def always_low(text, high_about, low_about):
    return risk.LOW


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.plug = plugs.load(plugs.WATERER, self)
        self.lessons = Lessons(self.db, self.plug, judge=always_low)
        self.sw = self.lessons.switches
        self.morning = mod.Morning(self.db, [self.plug], reports=self.dir)

    def new(self, text, stages=("seedling",), *, now=NOW, sources=()):
        return self.lessons.propose(text, list(stages), sources=list(sources), now=now)

    def page(self, now=NOW, token="t0ken"):
        return mod.render(self.morning.view(now), token=token)

    def agent(self, now=NOW):
        return next(a for a in self.morning.view(now)["agents"] if a["agent"] == "waterer")


class Served(Base):
    """The page served on a free port; each POST carries the page's token and its own Origin."""

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

    def call(self, method, path, fields=None, *, token=True, origin="same"):
        headers = {"Host": self.here}
        body = None
        if fields is not None:
            fields = dict(fields, token=self.server.token) if token else dict(fields)
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
            return r.status, r.read().decode("utf-8")
        finally:
            conn.close()

    def post(self, path, **fields):
        status, _ = self.call("POST", path, fields)
        self.assertEqual(status, 303)
        status, page = self.call("GET", "/", origin=None)
        self.assertEqual(status, 200)
        return page


class LevelSwitch(Served):
    def test_the_level_switch_flips_from_the_page_with_who_and_when(self):
        self.new(LOW_A)
        page = self.call("GET", "/", origin=None)[1]
        self.assertIn("Trial level: careful</span>, 1 in 2 cases for 7 days; careful until a person flips it.", page)
        self.assertIn("A trial keeps the level it started with, so a flip moves no trial already running.", page)
        self.assertIn('action="/level"', page)
        before = time.time()
        page = self.post("/level", agent="waterer", level="fast")
        got = self.sw.level()
        self.assertEqual((got["level"], got["by"]), ("fast", OWNER))
        self.assertGreaterEqual(got["at"], before)
        self.assertIn("The trial level of waterer is fast now: 80% of cases for 3 days", page)
        self.assertIn(f"Trial level: fast</span>, 80% of cases for 3 days; switched to fast by {OWNER} on "
                      f"{mod._when(got['at'])}.", page)
        self.assertIn(f"{mod._when(got['at'])}: {OWNER} switched the trial level to fast.", page)  # every flip

    def test_a_flip_without_the_pages_token_or_from_another_origin_changes_nothing(self):
        self.new(LOW_A)
        self.assertEqual(self.call("POST", "/level", {"agent": "waterer", "level": "fast"}, token=False)[0], 403)
        self.assertEqual(self.call("POST", "/level", {"agent": "waterer", "level": "fast"},
                                   origin="http://evil.example")[0], 403)
        self.assertEqual(self.sw.history(), [])

    def test_the_flips_show_in_the_next_nights_switches_line(self):
        self.new(LOW_A)
        self.morning.set_level("waterer", "fast", now=NOW)
        self.morning.set_accept("waterer", "on", "1", "2", now=NOW)
        rep = Study(self.db, self.plug, proposer=fk.Proposer(), tagger=fk.Tagger(), lessons=self.lessons).run(
            NOW - 14 * DAY, NOW + 60, now=NOW + 60)
        night_mod.save(rep, self.dir / "ascent.db")
        self.assertIn("Switches that night: trial level fast: 80% of cases for 3 days; Accept high risk on, turned on "
                      f"by {OWNER}, until Sun 17 Jan 2027, 10:00 Cairo.", self.page(NOW + 120))


class AcceptHighRisk(Served):
    def test_on_with_the_check_mark_ends_on_its_day_by_itself(self):
        self.new(LOW_A)
        page = self.call("GET", "/", origin=None)[1]
        self.assertIn("Accept high risk: off until a person turns it on</span>.", page)
        self.assertIn('<input type="checkbox" name="auto" value="1"> Turn it off by itself after</label>', page)
        page = self.post("/accept", agent="waterer", on="on", auto="1", days="3")
        acc = self.sw.accept_high()
        self.assertTrue(acc["on"])
        self.assertEqual((acc["by"], acc["until"]), (OWNER, acc["at"] + 3 * DAY))
        self.assertIn(f"Accept high risk: on, turned on by {OWNER} on {mod._when(acc['at'])}, until "
                      f"{mod._when(acc['until'])}, then it turns off by itself</span>.", page)
        self.assertIn('action="/accept"', page)
        self.assertIn(">Turn off</button>", page)
        started = self.new(HIGH_A, ["grown"], now=acc["at"] + 1)  # on: no yes needed
        self.assertEqual((self.lessons.get(started)["state"], self.lessons.get(started)["yes_by"]),
                         (TRYING, f"{OWNER} (Accept high risk)"))
        held = self.new(HIGH_B, ["seedling", "grown"], now=acc["until"])  # its day: off by itself
        self.assertEqual((self.lessons.get(held)["state"], self.lessons.get(held)["yes_by"]), (WAITING, None))
        later = self.page(acc["until"] + 1)
        self.assertIn(f"Accept high risk: off, its days ran out on {mod._when(acc['until'])}", later)
        self.assertIn(f'id="l{held}"', later)

    def test_on_with_no_check_mark_has_no_end_and_turns_off_from_the_page(self):
        self.new(LOW_A)
        page = self.post("/accept", agent="waterer", on="on", days="")
        acc = self.sw.accept_high()
        self.assertEqual((acc["on"], acc["until"]), (True, None))
        self.assertIn("until a person turns it off</span>.", page)
        page = self.post("/accept", agent="waterer", on="off")
        acc = self.sw.accept_high()
        self.assertEqual((acc["on"], acc["by"]), (False, OWNER))
        self.assertIn(f"Accept high risk: off, turned off by {OWNER} on {mod._when(acc['at'])}</span>.", page)
        self.assertIn("turned Accept high risk on, with no end day.", page)
        self.assertIn("turned Accept high risk off.", page)

    def test_a_copy_still_waits_for_a_yes_under_accept_turned_on_from_the_page(self):
        """Call 20: a lesson that copies its cases' words waits for a yes, even with Accept high risk on."""
        self.new(LOW_B, ["grown"])
        self.post("/accept", agent="waterer", on="on")
        at = self.sw.accept_high()["at"]
        copy = self.new(COPY, ["seedling"], now=at + 1, sources=[CASE])
        got = self.lessons.get(copy)
        self.assertEqual((got["state"], got["yes_by"], self.lessons.trial(copy)), (WAITING, None, None))
        view = self.morning.view(at + 2)
        self.assertEqual([c["id"] for c in view["cards"]], [copy])
        page = mod.render(view, token="t0ken")
        self.assertIn("High risk: it copies words from the cases it came from.", page)
        self.assertIn("A lesson that copies words from the cases it came from always waits for your yes, even with "
                      "Accept high risk on.", page)


class LessonLevel(Served):
    def test_a_cards_own_level_from_the_page_is_read_when_its_trial_starts(self):
        card = self.new(HIGH_A)
        page = self.call("GET", "/", origin=None)[1]
        self.assertIn("Its trial will take the careful level, 1 in 2 cases for 7 days (from the trial level switch).", page)
        self.assertIn('action="/lesson_level"', page)
        page = self.post("/lesson_level", lesson=str(card), level="fast")
        own = self.sw.lesson_level(card)
        self.assertEqual((own["level"], own["by"]), ("fast", OWNER))
        self.assertIn(f"Its trial will take the fast level, 80% of cases for 3 days (picked by {OWNER} on "
                      f"{mod._when(own['at'])}).", page)
        self.assertEqual(self.sw.level()["level"], "careful")  # the switch did not move
        self.assertEqual(page.count("Its trial will take the fast level"), 2)  # its card and the Waiting list, not New
        self.post("/yes", lesson=str(card), shown="")
        got, trial = self.lessons.get(card), self.lessons.trial(card)
        self.assertEqual((got["state"], got["share"], trial["days"], trial["level"]), (TRYING, 0.8, 3, "fast"))

    def test_a_queued_lessons_own_level_is_read_at_its_turn(self):
        first = self.new(LOW_A)
        queued = self.new(LOW_B)
        self.assertEqual(self.lessons.waits_for(queued, NOW), [first])
        [item] = self.agent()["waiting"]
        self.assertEqual(item["level"]["level"], "careful")
        self.assertIn(f'name="lesson" value="{queued}"><input type="hidden" name="level" value="fast">', self.page())
        self.morning.lesson_level(queued, "fast", now=NOW + 1)
        self.morning.stop(first, "Not needed.", now=NOW + 2)
        self.assertEqual(self.lessons.start_turns(NOW + 3), [queued])
        got = self.lessons.get(queued)
        self.assertEqual((got["state"], got["share"], got["ends_at"]), (TRYING, 0.8, NOW + 3 + 3 * DAY))

    def test_a_started_trial_keeps_its_level_and_takes_no_own_level(self):
        running = self.new(LOW_A)
        self.assertEqual(self.lessons.get(running)["share"], 0.5)
        self.morning.set_level("waterer", "fast", now=NOW + 1)
        got = self.lessons.get(running)
        self.assertEqual((got["share"], got["ends_at"]), (0.5, NOW + 7 * DAY))
        with self.assertRaisesRegex(mod.Refused, "a trial keeps the level it started with"):
            self.morning.lesson_level(running, "fast", now=NOW + 2)
        self.assertIsNone(self.sw.lesson_level(running))
        self.assertIsNone(next(i for i in self.agent()["live"] if i["id"] == running)["level"])
        later = self.new(LOW_B, ["grown"], now=NOW + 3)
        self.assertEqual(self.lessons.get(later)["share"], 0.8)  # a new trial takes the flipped level

    def test_a_lesson_given_its_share_and_days_with_its_yes_takes_no_level(self):
        card = self.new(HIGH_A)
        first = self.new(LOW_A)
        self.lessons.approve(card, OWNER, share=0.3, days=5, now=NOW + 1)
        self.assertEqual((self.lessons.get(card)["state"], self.lessons.waits_for(card, NOW + 1)), (WAITING, [first]))
        [item] = self.agent(NOW + 2)["waiting"]
        self.assertEqual(item["level"], {"given": True})
        page = self.page(NOW + 2)
        self.assertIn("Its share and days were given with its yes, so no level applies to it.", page)
        for n in re.findall(r'href="#t(\d+)"', page):  # a trial link only where that trial is listed
            self.assertIn(f'id="t{n}"', page)
        self.assertNotIn(f'name="lesson" value="{card}"><input type="hidden" name="level"', page)
        with self.assertRaisesRegex(mod.Refused, "took its share and days with its yes"):
            self.morning.lesson_level(card, "fast", now=NOW + 3)
        self.assertFalse(self.sw.set_lesson_level(card, "fast", OWNER, now=NOW + 3))
        self.assertIsNone(self.sw.lesson_level(card))
        self.morning.stop(first, "Not needed.", now=NOW + 4)
        self.assertEqual(self.lessons.start_turns(NOW + 5), [card])
        trial = self.lessons.trial(card)
        self.assertEqual((self.lessons.get(card)["share"], trial["days"], trial["level"]), (0.3, 5, "given"))


class Refusals(Base):
    """Every bad answer is refused by the page itself and writes no switch row."""

    def test_bad_switch_answers_are_refused_and_change_nothing(self):
        m = self.morning
        lid = self.new(HIGH_A)
        bad = [lambda: m.set_level("waterer", "slow"),
               lambda: m.set_level("waterer", "careful"),          # the level it reads already
               lambda: m.set_level("nobody", "fast"),
               lambda: m.set_accept("waterer", "maybe"),
               lambda: m.set_accept("waterer", "off"),              # off already
               lambda: m.set_accept("waterer", "on", "", "5"),      # days with no tick
               lambda: m.set_accept("nobody", "on"),
               lambda: m.set_accept("waterer", "on", "1", True),     # a bool is not a number of days
               lambda: m.lesson_level(lid, "slow")]
        bad += [lambda d=d: m.set_accept("waterer", "on", "1", d) for d in ("", "0", "91", "x", "2.5", "-1")]
        for i, call in enumerate(bad):
            with self.subTest(i=i), self.assertRaises(mod.Refused):
                call()
        self.assertEqual(self.sw.history(), [])

    def test_ninety_days_is_the_most(self):
        got = self.morning.set_accept("waterer", "on", "1", "90", now=NOW)
        self.assertIn("then it turns off by itself", got)
        self.assertEqual(self.sw.accept_high(NOW)["until"], NOW + 90 * DAY)

    def test_turning_it_on_again_gives_it_new_days(self):
        self.morning.set_accept("waterer", "on", "1", "2", now=NOW)
        self.morning.set_accept("waterer", "on", "1", "5", now=NOW + 1)
        self.assertEqual(self.sw.accept_high(NOW + 3 * DAY)["until"], NOW + 1 + 5 * DAY)


class Locks(Base):
    def test_the_sales_lists_its_own_locks_under_accept(self):
        lines = mod.locks(SALES.agent)
        self.assertEqual(lines[:2], ["The price check before every reply: a reply with an amount the store data does "
                                     "not have is never sent.",
                                     "The plain yes lock: no order is placed without the customer's plain yes to its "
                                     "summary."])
        self.assertIn("A lesson that copies a customer's own words from the chats always waits for your yes, even with "
                      "Accept high risk on.", lines)
        self.assertTrue(any(x.startswith("The auto pause:") for x in lines))
        self.assertNotIn("price check", " ".join(mod.locks("waterer")))

    def test_the_static_page_shows_the_switches_and_locks_with_no_forms(self):
        self.new(HIGH_A)
        page = self.page(token=None)
        self.assertIn("Accept high risk: off until a person turns it on", page)
        self.assertNotIn("<form", page)  # no Turn on form either
        self.morning.set_accept("waterer", "on", "1", "3", now=NOW)
        page = self.page(token=None)
        self.assertIn("Accept high risk: on, turned on by", page)
        self.assertIn("These hold whatever the switches say:", page)
        self.assertIn("Its trial will take the careful level", page)
        self.assertNotIn("<form", page)

    def test_an_agent_with_a_log_row_shows_its_switches_before_its_first_lesson(self):
        from engine.log import Log
        Log(self.db, self.plug).act("bed-1", "water", result="soaked", at=NOW)
        [a] = self.morning.view(NOW)["agents"]
        self.assertEqual((a["agent"], a["switches"]["level"]["level"]), ("waterer", "careful"))
        self.assertEqual(mod.Morning(self.db, [], reports=self.dir).view(NOW)["agents"], [])  # no plug, no section

    def test_every_field_of_a_switch_is_escaped(self):
        self.new(LOW_A)
        self.sw.set_level("fast", "<b>Mona</b>", now=NOW)
        page = self.page()
        self.assertNotIn("<b>Mona", page)
        self.assertIn("&lt;b&gt;Mona&lt;/b&gt;", page)
        self.assertTrue(re.search(r"switched to fast by &lt;b&gt;Mona&lt;/b&gt; on ", page))
        self.sw.set_accept_high(True, "<i>Sam</i>", now=NOW)
        page = self.page()
        self.assertNotIn("<i>Sam", page)
        self.assertIn("Accept high risk: on, turned on by &lt;i&gt;Sam&lt;/i&gt; on ", page)


if __name__ == "__main__":
    unittest.main()
