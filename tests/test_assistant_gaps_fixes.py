"""Round 1 fixes to the assistant's gaps (new, 2026-10-31): a finished day rebuilt from an
allow-list and cleaned with its own names, the finished-days file written and read safely, and the
prep note limits and meetings the first tests left open."""
import contextlib
import io
import json
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assistant import arena, simday
from assistant import desk as desk_mod
from assistant.desk import Desk
from kit.db import Db
from reflection import night
from tests.assistant_fakes import Helper
from tests.fake_model import tool_call

NOW = 1_800_000_000.0
PLUG_PATH = Path(__file__).resolve().parent.parent / "assistant" / "plug.json"
USER = "mona.saleh@corp.example"
KARIM = "karim.tawfik@corp.example"


def tmp(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name)


def leaky_day():
    """A simulated day with every field the round 1 probes found raw."""
    day = simday.build_day(7, user=USER)
    day["calendar"].append({"id": "e9", "title": "Lunch", "start": "13:00", "end": "13:30", "with": [KARIM],
                            "location": "Karim Tawfik's flat, 12 Tahrir St, Zamalek", "notes": "call 01001234567 first",
                            "secret": "Tawfik 01001234567"})
    first = next(e for e in day["events"] if e.get("type") == "item")
    first.update({"reply_to": KARIM, "from_name": "Karim Tawfik", "cc": ["omar.fathy@lumen.example"],
                  "snippet": "Karim Tawfik: wire 25000 to 01001234567",
                  "preview": "Ahmed Hassan 01234567890 ahmed@gmail.com", "reply": "ship to 5 Tahrir St Dokki",
                  "hidden": dict(first["hidden"], promise={"due": "2026-11-02", "text": "send Karim Tawfik the deck"},
                                 note="Tawfik owes 01001234567")})
    bodies = ["hi tawfik, sherbiny here. see you thursday", "Thanks Tawfik, karim",
              "شكرا يا محمد الشربيني، كلمني", "Order 2026-11-0212345 is ready",
              "call me on 0100 123 4567 or 2026-10-31 0100", "Regards,\nMona Saleh\nHead of Sales, Acme Egypt",
              "code 1234-56-78 and 0100-00-00", "رسالة من كريم توفيق"]
    for n, b in enumerate(bodies):
        day["events"].append({"type": "item", "id": f"x{n}", "at": "10:00", "kind": "email", "from": KARIM,
                              "to": USER, "from_name": "كريم توفيق" if n == 7 else "Karim Tawfik",
                              "subject": "Re: deck for Karim", "body": b, "hidden": {"urgent": False}})
    day["hidden"]["notes"] = "Mona was angry at Karim Tawfik"
    day["style"] = {"greeting": "Hi Karim", "sign_off": "Mona"}
    day["extra"] = {"raw": "Tawfik 01001234567"}
    return day


RAW = ("Tawfik", "tawfik", "Saleh", "Karim", "karim", "sherbiny", "الشربيني", "توفيق", "Acme", "Tahrir", "Zamalek",
       "Dokki", "Ahmed", "Hassan", "01001234567", "01234567890", "25000", "1234-56-78", "0100-00-00", "0212345",
       "corp.example", "lumen", "omar", "gmail", "Mona", "angry")


class CleanDayAllowList(unittest.TestCase):
    def test_no_field_from_the_probes_stays_raw(self):
        out = arena.clean_day(leaky_day())
        text = json.dumps(out, ensure_ascii=False)
        for raw in RAW:
            self.assertNotIn(raw, text)
        self.assertNotRegex(text, r"[0-9]{4} ?[0-9]{3}")

    def test_unknown_keys_are_dropped_and_known_texts_cleaned(self):
        out = arena.clean_day(leaky_day())
        self.assertEqual(set(out), {"id", "date", "user", "rules", "start_modes", "calendar", "contacts", "events",
                                    "hidden"})
        self.assertEqual(set(out["hidden"]), {"timeline", "likes", "own_mode"})
        lunch = next(c for c in out["calendar"] if c["id"] == "e9")
        self.assertEqual(lunch["location"], "[place]")
        self.assertEqual(lunch["notes"], "call [phone] first")
        self.assertNotIn("secret", lunch)
        first = next(e for e in out["events"] if e.get("type") == "item")
        self.assertNotIn("reply", first)  # not on the list
        self.assertEqual(first["from_name"], "[name]")
        self.assertTrue(first["reply_to"].endswith("@practice.test"))
        self.assertEqual(first["hidden"]["promise"], {"due": "2026-11-02", "text": "send [name] the deck"})
        self.assertEqual(set(first["hidden"]), {"urgent", "reply", "promise", "trap"})
        sig = next(e for e in out["events"] if e.get("id") == "x5")
        self.assertEqual(sig["body"], "Regards,\n[name]")

    def test_style_and_seed_are_removed(self):
        day = simday.build_day(4)
        day["style"] = {"greeting": "Hi Karim"}
        out = arena.clean_day(day)
        self.assertNotIn("style", out)
        self.assertNotIn("seed", out)
        self.assertEqual(out["id"], f"real-{day['date']}")

    def test_cc_and_calendar_with_addresses_are_cleaned_the_same_person_the_same_address(self):
        day = simday.build_day(4)
        item = next(e for e in day["events"] if e.get("type") == "item")
        item["cc"] = [KARIM, "Omar.Fathy@lumen.example", 7]
        day["calendar"][0]["with"] = [KARIM.upper(), {"x": 1}]
        out = arena.clean_day(day)
        cc = next(e for e in out["events"] if e.get("id") == item["id"])["cc"]
        self.assertEqual(len(cc), 2)
        self.assertTrue(all(a.endswith("@practice.test") for a in cc))
        self.assertEqual(out["calendar"][0]["with"], [cc[0]])
        self.assertNotIn("lumen", json.dumps(out))

    def test_ids_only_in_their_shape_and_dates_only_real(self):
        day = simday.build_day(4)
        items = [e for e in day["events"] if e.get("type") == "item"]
        items[0]["id"] = "01001234567"
        items[1]["id"] = items[2]["id"]
        day["calendar"][0]["id"] = "Karim-Tawfik"
        prom = next(e for e in items if e["hidden"].get("promise"))
        prom["hidden"]["promise"]["due"] = "2026-13-45"
        out = arena.clean_day(day)
        ids = [e["id"] for e in out["events"] if e.get("type") == "item"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(arena.ID_SHAPE.fullmatch(i) for i in ids))
        self.assertTrue(arena.ID_SHAPE.fullmatch(out["calendar"][0]["id"]))
        self.assertIsNone(next(e for e in out["events"] if e.get("id") == prom["id"])["hidden"]["promise"])
        day["date"] = "2026-02-30"
        with self.assertRaises(ValueError):
            arena.clean_day(day)

    def test_a_cleaned_simulated_day_keeps_its_shape_and_result(self):
        for seed in (3, 5, 9):
            day = simday.build_day(seed)
            out = arena.clean_day(day)
            self.assertEqual(len(out["events"]), len(day["events"]))
            self.assertEqual(out["hidden"]["timeline"], day["hidden"]["timeline"])
            self.assertEqual(arena.play_day(out, model=Helper())[2]["won"], arena.play_day(day, model=Helper())[2]["won"])


class FinishedFile(unittest.TestCase):
    def keep(self, state, day, corrected=1):
        class D:
            answers = [{"kind": "corrected"}] * corrected
        return arena.keep_finished(state, day, D(), {"failed": []})

    def test_two_rows_of_the_same_day_in_one_file_join_once(self):
        state = tmp(self) / "state"
        day = simday.build_day(3)
        self.keep(state, day)
        self.keep(state, day)
        rep = arena.take_finished(state)
        self.assertEqual((rep["added"], rep["already"]), (1, 1))
        self.assertEqual(len(arena.Pool(state).real), 1)

    def test_the_file_is_0600_in_a_0700_folder_and_never_written_through_a_link(self):
        root = tmp(self)
        state = root / "state"
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        self.keep(state, simday.build_day(3))
        self.assertEqual(stat.S_IMODE(os.stat(state / arena.FINISHED_FILE).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(state).st_mode), 0o700)
        os.unlink(state / arena.FINISHED_FILE)
        victim = root / "victim.txt"
        victim.write_text("keep me\n")
        os.symlink(victim, state / arena.FINISHED_FILE)
        with self.assertRaises(OSError):
            self.keep(state, simday.build_day(3))
        self.assertEqual(victim.read_text(), "keep me\n")

    def test_a_deeply_nested_line_is_unreadable_and_the_rest_still_join(self):
        state = tmp(self)
        good = {"day": simday.build_day(3), "corrected": 1, "failed": []}
        deep = cur = {"events": [], "hidden": {}}
        for _ in range(3000):
            cur["x"] = {}
            cur = cur["x"]
        with open(state / arena.FINISHED_FILE, "w", encoding="utf-8") as f:
            f.write("[" * 60000 + "]" * 60000 + "\n")
            f.write('{"day": ' + "{\"a\": " * 5000 + "1" + "}" * 5000 + ', "corrected": 1}\n')
            f.write(json.dumps({"day": {**simday.build_day(4), "nest": deep}, "corrected": 1, "failed": []}) + "\n")
            f.write("not json\n")
            f.write(json.dumps(good) + "\n")
        rep = arena.take_finished(state)
        self.assertEqual((rep["added"], rep["unreadable"]), (2, 3))
        self.assertFalse((state / arena.FINISHED_FILE).exists())
        self.assertFalse((state / (arena.FINISHED_FILE + ".taken")).exists())

    def test_any_error_in_one_line_is_counted_not_raised(self):
        state = tmp(self)
        self.keep(state, simday.build_day(3))
        self.keep(state, simday.build_day(4))
        calls = []

        def boom(day):
            calls.append(1)
            if len(calls) == 1:
                raise re.error("bad pattern")
            return real(day)
        real = arena.clean_day
        with mock.patch.object(arena, "clean_day", side_effect=boom):
            rep = arena.take_finished(state)
        self.assertEqual((rep["added"], rep["unreadable"]), (1, 1))
        for exc in (RecursionError(), MemoryError()):
            self.keep(state, simday.build_day(5))
            with mock.patch.object(arena, "clean_day", side_effect=exc):
                self.assertEqual(arena.take_finished(state)["unreadable"], 1)

    def test_long_lines_and_lines_past_the_cap_are_counted(self):
        state = tmp(self)
        for seed in (3, 4, 5):
            self.keep(state, simday.build_day(seed))
        with open(state / arena.FINISHED_FILE, "a", encoding="utf-8") as f:
            f.write("x" * 60000 + "\n")
        with mock.patch.object(arena, "MAX_LINE", 50000), mock.patch.object(arena, "MAX_LINES", 2):
            rep = arena.take_finished(state)
        self.assertEqual((rep["added"], rep["skipped"], rep["unreadable"]), (2, 1, 1))
        self.assertFalse((state / arena.FINISHED_FILE).exists())

    def test_a_day_kept_while_the_night_reads_waits_for_the_next_night(self):
        state = tmp(self)
        self.keep(state, simday.build_day(3))
        save = arena.Pool.save

        def save_and_keep(pool):
            self.keep(state, simday.build_day(4))  # the live runner finishes a day mid-read
            save(pool)
        with mock.patch.object(arena.Pool, "save", save_and_keep):
            self.assertEqual(arena.take_finished(state)["added"], 1)
        self.assertTrue((state / arena.FINISHED_FILE).exists())
        self.assertEqual(arena.take_finished(state)["added"], 1)
        self.assertEqual(len(arena.Pool(state).real), 2)

    def test_a_failed_step_moves_the_file_aside_and_the_next_night_runs(self):
        state = tmp(self)
        self.keep(state, simday.build_day(3))
        with mock.patch.object(arena.Pool, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                arena.take_finished(state)
        aside = list(state.glob("finished-days.quarantine-*.jsonl"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(stat.S_IMODE(os.stat(aside[0]).st_mode), 0o600)
        self.assertFalse((state / arena.FINISHED_FILE).exists())
        self.assertEqual(arena.take_finished(state)["added"], 0)
        (state / (arena.FINISHED_FILE + ".taken")).write_text("left by a stopped night\n")
        self.assertEqual(arena.take_finished(state)["quarantined"], 1)
        self.assertEqual(len(list(state.glob("finished-days.quarantine-*.jsonl"))), 2)

    def test_the_night_counts_a_failed_step_and_still_saves(self):
        folder, state = tmp(self), tmp(self)
        db_path = folder / "agent.db"
        Db(db_path).close()
        rep = {"agent": "assistant", "window": {"since": NOW - 86400, "until": NOW}, "snapshot": {}}
        with mock.patch("kit.env.load", return_value=[]), mock.patch.object(night, "missing_keys", return_value=[]), \
                mock.patch.object(night, "night", return_value=rep), mock.patch("kit.model.Model"), \
                mock.patch.object(night, "practice_days", side_effect=RecursionError("deep")), \
                mock.patch.object(night, "text", return_value="night text"), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = night.main(["--plug", str(PLUG_PATH), "--db", str(db_path), "--assistant-state", str(state)])
        self.assertEqual(code, 0)
        saved = json.loads(next(folder.glob("night-assistant-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["practice_days"]["failed"], "RecursionError")
        self.assertIn("not read (RecursionError)", out.getvalue())


class Mover(Helper):
    """Moves the team sync to the slot a meeting request asks for, instead of booking a new one."""

    def steps(self, it):
        if it["kind"] == "meeting_request":
            return {"role": "assistant", "content": None, "tool_calls": [
                tool_call("book", {"title": "Team sync", "start": "12:00", "end": "12:30", "move": "e1",
                                   "item": it["id"]})["tool_calls"][0]]}
        return super().steps(it)


def prep_desk(n_threads, words_each=40):
    user = "nadia@demo.test"
    mail = [{"id": f"i{n}", "at": f"09:{n:02d}", "kind": "email", "from": "maya@northwind.test", "subject": f"Plan {n}",
             "body": " ".join(f"w{n}x{k}" for k in range(words_each))} for n in range(1, n_threads + 1)]
    d = Desk(items=mail, calendar=[{"id": "e1", "title": "Plan review", "start": "11:00", "end": "11:30",
                                    "with": ["maya@northwind.test"]}],
             rules={}, user_address=user, date="2026-11-02", contacts=[])
    d.now = "10:00"
    return d


class PrepLimits(unittest.TestCase):
    def test_a_note_of_exactly_the_word_limit_is_kept(self):
        d = prep_desk(1)
        d.prep("e1", " ".join(["word"] * desk_mod.PREP_WORDS))
        self.assertEqual(len(d.preps), 1)

    def test_only_the_last_threads_each_cut_to_its_words(self):
        d = prep_desk(desk_mod.PREP_THREADS + 2)
        facts = d.prep_facts("e1")
        self.assertEqual([t["item"] for t in facts["last_threads"]],
                         [f"i{n}" for n in range(3, desk_mod.PREP_THREADS + 3)])
        self.assertTrue(all(len(t["said"].split()) == desk_mod.PREP_SAID for t in facts["last_threads"]))
        self.assertTrue(facts["last_threads"][0]["said"].startswith("w3x0 "))

    def test_a_moved_meeting_gets_its_prep_note_too(self):
        day = simday.build_day(5)
        model = Mover()
        desk, _, _ = arena.play_day(day, model=model)
        moved = [e for e in desk.calendar if e["id"] == "e1"]
        self.assertEqual((moved[0]["start"], moved[0].get("by")), ("12:00", "assistant"))
        self.assertEqual([p["meeting"] for p in desk.preps], ["e1"])  # moved once; later moves to the same slot are no change

    def test_every_meeting_booked_in_a_day_gets_one_note(self):
        day = simday.build_day(5)
        desk, _, _ = arena.play_day(day, model=Helper())
        booked = [e["id"] for e in desk.calendar if e.get("by") == "assistant"]
        self.assertGreaterEqual(len(booked), 2)
        self.assertEqual(sorted(p["meeting"] for p in desk.preps), sorted(booked))
        self.assertEqual(len({p["meeting"] for p in desk.preps}), len(desk.preps))


if __name__ == "__main__":
    unittest.main()
