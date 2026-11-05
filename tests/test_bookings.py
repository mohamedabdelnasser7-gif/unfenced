"""Shared bookings per agent (kit/bookings.py, kit/tools/book.py, kit/tools/calendar_tool.py, 2026-11-05).

A built agent that books (an Apartment Viewing Booker on a sheet of apartments) books one row at a date and time,
checked in code only against every booking any live chat of the agent made, kept in
<db folder>/agents/<agent>/bookings.json; the row's viewing days and hours are the agent's to follow from its prompt
(Mohamed 2026-11-05). Start over on the page chat keeps them; Arena practice
never writes them. The assistant's calendar refuses a time another chat booked. Fake models only, no network."""
import datetime as dt
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from arena import practice
from kit import bookings, sample, turn
from kit.chats import Chats
from kit.db import Db
from kit.tools import book, calendar_tool, mailbox
from reflection import pages, quickstart as qs, try_sales
from tests.fake_model import FakeModel, say, tool_call
from tests.test_any_agent_r2 import THREE

# The sheet's shape (fake data, the same columns as the owner's apartments sheet)
SHEET = """name,area,bedrooms,bathrooms,size_m2,rent_egp_month,furnished,available_from,viewing_days,viewing_hours,notes
Nile View 3B,Zamalek,2,2,140,38000,yes,2026-11-15,Sun Mon Wed,11:00-17:00,Balcony facing the Nile
Garden Flat 12,Maadi Sarayat,2,1,120,14500,no,2026-11-10,Sun Tue Thu,10:00-16:00,Ground floor with a small garden
Villette Studio 4,New Cairo,1,1,65,11000,yes,2026-11-08,Every day,10:00-20:00,Compound with gym and pool
"""
AT = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))  # a Thursday
SUNDAY = "2026-11-08"
NAME = "apartment_viewing_booker"
CARD = {"agent": NAME, "name": "Apartment Viewing Booker",
        "does": "Answers people asking about our apartments for rent and books a viewing at a time that suits them.",
        "good": "The person has a viewing booked on a day and time the apartment is shown.",
        "bad": "Two people are booked for the same slot, or a viewing is booked when the flat is not shown.",
        "case": {"input": "a person asking about an apartment", "starts": "person",
                 "output": "a booked viewing", "ends": "when the viewing is booked or the person says no"},
        "never": ["Never books a viewing outside the apartment's viewing days and hours"],
        "needs": [{"what": "apartments with viewing days and hours", "tool": "", "connected": False},
                  {"what": "chat to answer people", "tool": "whatsapp", "connected": True},
                  {"what": "calendar to book viewings", "tool": "calendar", "connected": False}],
        "tools": ["whatsapp"], "kind": "sales", "level": "careful"}


def make_folder(root):
    a = THREE["lead_trial_booker"]
    folder = Path(root) / "agents" / NAME
    folder.mkdir(parents=True)
    raw = {k: v for k, v in a["plug"].items() if k != "exam"}
    raw["agent"] = NAME
    (folder / "plug.json").write_text(json.dumps(qs.clean_plug(raw, NAME, CARD["tools"], CARD)), encoding="utf-8")
    (folder / "card.json").write_text(json.dumps(CARD), encoding="utf-8")
    (folder / "instructions.md").write_text("You book apartment viewings with the book tool.", encoding="utf-8")
    sample.add(folder, text=SHEET)
    return folder


def books(item="Garden Flat 12", date=SUNDAY, start="11:00", **more):
    return tool_call(book.NAME, dict(item=item, date=date, start=start, **more))


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name).resolve()
        self.folder = make_folder(self.root)
        self.agent = turn.load(self.folder)
        self.store = bookings.path_of(self.folder)
        clock = mock.patch.object(mailbox, "now", return_value=AT)
        clock.start()
        self.addCleanup(clock.stop)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)

    def chat(self, call, who, live=True):
        """One live chat (bookings file handed, as the page chat does) that makes call; the tool's answer."""
        cid = self.chats.open("whatsapp", who)
        model = FakeModel(call, *[say("Done.")] * 4)
        turn.turn(self.agent, "I want to see it", chats=self.chats, chat_id=cid, model=model,
                  send=lambda to, t: None, customer_id=who, bookings=self.store if live else None)
        rows = [s for s in self.chats.steps(cid) if s["role"] == "tool" and s.get("name") == book.NAME]
        return json.loads(rows[-1]["content"])


class TheBookTool(Base):
    def test_a_booking_agent_with_sample_rows_gets_the_book_tool(self):
        self.assertIn(book.NAME, self.agent.tools)
        self.assertTrue(book.books(CARD))
        plain = dict(CARD, does="Writes captions", good="A caption", needs=[], case={"output": "a caption"})
        self.assertFalse(book.books(plain))

    def test_a_booked_slot_is_refused_to_a_new_chat_and_another_slot_is_taken(self):
        first = self.chat(books(who="Mona"), "c1")
        self.assertTrue(first["ok"], first)
        self.assertEqual((first["booked"]["item"], first["booked"]["date"], first["booked"]["start"]),
                         ("Garden Flat 12", SUNDAY, "11:00"))
        again = self.chat(books(), "c2")
        self.assertFalse(again["ok"])
        self.assertIn("already booked", again["feedback"])
        self.assertIn("next free time that day is 11:30", again["feedback"])
        other = self.chat(books(start="12:00"), "c3")
        self.assertTrue(other["ok"], other)
        saved = bookings.read(self.store)
        self.assertEqual([(b["item"], b["start"]) for b in saved], [("Garden Flat 12", "11:00"), ("Garden Flat 12", "12:00")])
        self.assertEqual(saved[0]["who"], "Mona")
        self.assertTrue(self.chat(books(item="Nile View 3B"), "c4")["ok"])  # another flat at the same time is free

    def test_days_hours_and_move_in_dates_are_the_prompts_and_only_a_clash_is_refused(self):
        """Mohamed 2026-11-05: the agent follows viewing rules from its prompt, the code checks no day or hour.
        Garden Flat 12 is shown Sun Tue Thu 10:00-16:00 on the sheet; Monday 19:00 books, and the same flat at an
        overlapping time is still refused in another chat."""
        monday = self.chat(books(date="2026-11-09", start="19:00"), "c1")
        self.assertTrue(monday["ok"], monday)
        early = self.chat(books(start="07:00"), "c2")  # before any 09:00 default and the row's 10:00
        self.assertTrue(early["ok"], early)
        clash = self.chat(books(date="2026-11-09", start="19:15"), "c3")
        self.assertFalse(clash["ok"])
        self.assertIn("already booked on Monday 2026-11-09 from 19:00 to 19:30", clash["feedback"])
        self.assertIn("next free time that day is 19:30", clash["feedback"])
        self.assertEqual([(b["date"], b["start"]) for b in bookings.read(self.store)],
                         [("2026-11-09", "19:00"), (SUNDAY, "07:00")])
        listed = book.run({"item": "Garden Flat 12"}, mock.Mock(data=sample.read(self.folder), bookings=self.store,
                                                                chats=self.chats, chat_id=0))
        self.assertEqual(listed["rows"], [{"item": "Garden Flat 12"}])  # no days, hours or move in date given
        text = book.DEFINITION["function"]["description"]
        self.assertNotIn("own days", text)
        self.assertIn("refuses only a time another booking of that row overlaps", text)
        self.assertFalse(hasattr(book, "DEFAULT_HOURS"))

    def test_practice_never_writes_the_shared_bookings(self):
        practised = self.chat(books(), "c1", live=False)
        self.assertTrue(practised["ok"])
        self.assertIn("practice", practised["note"])
        self.assertFalse(self.store.exists())
        customer = FakeModel(say("Can I see Garden Flat 12 on Sunday at 11?"), *[say("[LEAVE]")] * 6)
        agent_model = FakeModel(books(), *[say("It is booked for Sunday at 11:00.")] * 8)
        match = practice.play(self.agent, {"input": "Can I see Garden Flat 12?"}, agent_model=agent_model,
                              customer_model=customer, max_turns=2)
        self.assertIn('"booked"', json.dumps(match))  # the practice agent did book, on its case copy
        self.assertFalse(self.store.exists())
        self.assertTrue(self.chat(books(), "c2")["ok"])  # the slot is still free for a real chat

    def test_two_bookings_at_once_both_keep(self):
        ready = threading.Barrier(8)
        outs = []

        def one(n):
            ready.wait()
            outs.append(bookings.add(self.store, {"item": "Garden Flat 12", "date": SUNDAY,
                                                  "start": f"1{n // 2}:{30 * (n % 2):02d}",
                                                  "end": f"1{n // 2}:{30 * (n % 2) + 29:02d}", "case": str(n)},
                                     lambda rows: time.sleep(0.01)))  # a slow test widens any race

        threads = [threading.Thread(target=one, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(bookings.read(self.store)), 8)

    def test_two_chats_racing_for_one_slot_only_one_gets_it(self):
        ready = threading.Barrier(6)
        outs = []

        def one(n):
            ready.wait()
            entry = {"item": "Garden Flat 12", "date": SUNDAY, "start": "11:00", "end": "11:30", "case": str(n)}
            outs.append(bookings.add(self.store, entry, lambda rows: time.sleep(0.01) or ("taken" if bookings.overlaps(
                rows, SUNDAY, "11:00", "11:30", "Garden Flat 12") else None))[0])

        threads = [threading.Thread(target=one, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(outs), [False] * 5 + [True])
        self.assertEqual(len(bookings.read(self.store)), 1)


class OnTheOverview(Base):
    def test_the_bookings_line_counts_and_escapes(self):
        self.assertEqual(pages.bookings_html([]), "")
        for n in range(4):
            bookings.add(self.store, {"item": "Garden Flat 12", "date": SUNDAY, "start": f"1{n}:00", "end": f"1{n}:30",
                                      "case": "c", "who": "<b>Mona</b>" if n == 3 else ""}, lambda rows: None)
        html = pages.bookings_html(bookings.read(self.store))
        self.assertIn("4 booked, newest 3:", html)
        self.assertIn("Garden Flat 12 2026-11-08 13:00 to 13:30", html)
        self.assertNotIn("<b>Mona", html)
        self.assertNotIn("10:00 to", html)


class StartOver(Base):
    def test_start_over_on_the_page_chat_keeps_the_booking(self):
        folder = self.folder

        class M:
            reports = self.root
            lessons = {}

            def agent_folder(self, agent):
                return folder

        box = try_sales.TryAgent(NAME, FakeModel(books(), say("Booked."), books(), say("Sorry, taken.")))
        self.addCleanup(box.db.close)
        box.say(M(), "Garden Flat 12 on Sunday at 11 please")
        self.assertEqual(len(bookings.read(self.store)), 1)
        box.clear()
        box.say(M(), "Garden Flat 12 on Sunday at 11 please")
        self.assertEqual(len(bookings.read(self.store)), 1)
        last = [s for c in box.cases() for s in c["steps"] if s["role"] == "tool"][-1]
        self.assertIn("already booked", json.loads(last["content"])["feedback"])


class AssistantCalendar(Base):
    def call(self, start, end, cid, path):
        ctx = mock.Mock(chats=self.chats, chat_id=cid, bookings=path)
        ctx.chats = self.chats
        return calendar_tool.run({"title": "Call with Omar", "start": start, "end": end}, ctx)

    def test_a_meeting_booked_in_one_chat_is_refused_in_another(self):
        path = self.root / "agents" / "assistant" / bookings.FILE
        path.parent.mkdir(parents=True)
        free = next(f"{h:02d}:00" for h in range(9, 17) if self.call(f"{h:02d}:00", f"{h:02d}:30",
                                                                      self.chats.open("whatsapp", f"p{h}"), None)["ok"])
        end = free[:3] + "30"
        first = self.call(free, end, self.chats.open("whatsapp", "a1"), path)
        self.assertTrue(first["ok"], first)
        again = self.call(free, end, self.chats.open("whatsapp", "a2"), path)
        self.assertFalse(again["ok"])
        self.assertIn("booked in another chat", again["feedback"])
        self.assertIn("next free time", again["feedback"])
        self.assertEqual(len(bookings.read(path)), 1)
        practice_only = self.call(free, end, self.chats.open("whatsapp", "a3"), None)
        self.assertTrue(practice_only["ok"])  # practice reads only its own copy
        self.assertEqual(len(bookings.read(path)), 1)


if __name__ == "__main__":
    unittest.main()
