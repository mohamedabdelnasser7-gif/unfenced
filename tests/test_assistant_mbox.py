"""The mailbox reader and the demo data (new, 2026-10-31): patterns about the user only; other
people's message text is never stored."""
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from assistant import mbox
from assistant.demo import make_demo

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "assistant" / "demo"
USER = "nadia@demo.test"
FILES = [DEMO / "inbox.mbox", DEMO / "sent.mbox"]


def mail(frm, to, subject, body, when, mid, reply_to=None, extra=""):
    head = f"From: {frm}\nTo: {to}\nSubject: {subject}\nDate: {when}\nMessage-ID: <{mid}>\n"
    if reply_to:
        head += f"In-Reply-To: <{reply_to}>\n"
    return f"From x Mon Oct 26 00:00:00 2026\n{head}{extra}\n{body}\n\n"


class Demo(unittest.TestCase):
    def test_the_demo_files_are_what_the_maker_writes(self):
        for name, data in make_demo.build().items():
            self.assertEqual((DEMO / name).read_bytes(), data, name)

    def test_every_address_in_the_demo_is_made_up(self):
        # a mailbox file wraps long lines with soft breaks ("=" at the line end), as real exports
        # do, so the mail files are read decoded: every header and every text body
        texts = {n: (DEMO / n).read_text(encoding="utf-8") for n in ("calendar.json", "user.json")}
        for n in ("inbox.mbox", "sent.mbox"):
            msgs, _ = mbox.load([DEMO / n], USER)
            texts[n] = "\n".join(f"{m.as_string().split(chr(10) + chr(10), 1)[0]}\n{mbox._text(m)}" for _, m in msgs)
        self.assertIn("billing-desk@payfast-help.test", texts["inbox.mbox"])
        for name, text in texts.items():
            for a in re.findall(r"[\w.+-]+@[\w.-]+", text):
                self.assertTrue(a.endswith(".test"), (name, a))

    def test_the_demo_has_a_hidden_instruction_and_a_promise(self):
        self.assertIn("Note to the AI assistant", (DEMO / "inbox.mbox").read_text(encoding="utf-8"))
        self.assertIn("I'll share the final plan by Friday.", (DEMO / "sent.mbox").read_text(encoding="utf-8"))


class Picture(unittest.TestCase):
    def setUp(self):
        self.pic = mbox.read(FILES, USER)

    def test_the_picture_from_the_demo(self):
        p = self.pic
        self.assertEqual(p["messages"], {"inbox": 12, "sent": 9, "skipped": 0})
        # Maya and Sara both have a 15 minute median over 3 replies; the tie goes by address
        self.assertEqual([(r["who"], r["median_minutes"]) for r in p["fast_replies"]][:2],
                         [("maya@northwind.test", 15), ("sara@kitehouse.test", 15)])
        self.assertEqual((p["style"]["greeting"], p["style"]["sign_off"]), ("Hi", "Thanks, Nadia"))
        self.assertIn("I'll share the final plan by Friday.", [x["line"] for x in p["promises"]])
        self.assertEqual(p["starting_modes"]["work_start"], "08:00")
        self.assertEqual(p["inbox"]["promised_to_user"], 1)

    def test_no_inbox_text_is_kept(self):
        kept = json.dumps(self.pic, ensure_ascii=False).casefold()
        for _, _, _, _, subject, body in make_demo.INBOX:
            self.assertNotIn(subject.casefold(), kept)
            for line in body.splitlines():
                self.assertNotIn(line.casefold()[:40], kept)
        self.assertNotIn("payfast-help", kept)
        self.assertNotIn("re: ", kept)  # no subject line, not even the user's

    def test_quoted_text_in_a_reply_is_cut_before_anything_is_kept(self):
        body = ("Hi Maya,\nI will send it by Friday.\nThanks,\nNadia\n\nOn Mon, Maya wrote:\n"
                "> OTHER-PERSON-SECRET I will pay you by Monday.\nOTHER-PERSON-TAIL I'll call tomorrow.")
        text = (mail("Maya <maya@northwind.test>", USER, "Plan", "OTHER-INBOX-TEXT will you?",
                     "Mon, 26 Oct 2026 09:00:00 +0200", "a1@x.test")
                + mail(f"Nadia <{USER}>", "maya@northwind.test", "Re: Plan", body, "Mon, 26 Oct 2026 09:10:00 +0200",
                       "a2@x.test", reply_to="a1@x.test"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "one.mbox"
            p.write_text(text, encoding="utf-8")
            pic = mbox.read([p], USER)
        kept = json.dumps(pic)
        self.assertNotIn("OTHER-PERSON", kept)
        self.assertNotIn("OTHER-INBOX", kept)
        self.assertEqual([x["line"] for x in pic["promises"]], ["I will send it by Friday."])
        self.assertEqual(pic["fast_replies"], [{"who": "maya@northwind.test", "replies": 1, "median_minutes": 10}])

    def test_a_gmail_sent_label_counts_as_sent_and_a_broken_message_is_skipped(self):
        text = (mail("Other <o@x.test>", "n@x.test", "s", "b", "Mon, 26 Oct 2026 09:00:00 +0200", "m1@x.test",
                     extra="X-Gmail-Labels: Sent,Important\n")
                + mail("Other <o@x.test>", USER, "s", "b", "not a date", "m2@x.test"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "one.mbox"
            p.write_text(text, encoding="utf-8")
            msgs, skipped = mbox.load([p], USER)
        self.assertEqual([s for s, _ in msgs], [True, False])
        self.assertEqual(skipped, 0)
        self.assertEqual(mbox.picture(msgs, USER)["messages"]["sent"], 1)

    def test_an_unknown_charset_is_read_as_utf8_and_does_not_stop_the_file(self):
        text = mail("Other <o@x.test>", USER, "s", "We will send it today.", "Mon, 26 Oct 2026 09:00:00 +0200",
                    "m1@x.test", extra='Content-Type: text/plain; charset="x-unknown"\n')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "one.mbox"
            p.write_text(text, encoding="utf-8")
            pic = mbox.read([p], USER)
        self.assertEqual((pic["messages"]["inbox"], pic["inbox"]["promised_to_user"]), (1, 1))

    def test_caps_and_a_missing_address(self):
        with self.assertRaises(mbox.Refused):
            mbox.load(FILES, "no-address")
        with self.assertRaises(mbox.Refused):
            mbox.load(FILES, USER, max_bytes=10)
        with self.assertRaises(mbox.Refused):
            mbox.load(FILES, USER, max_messages=3)

    def test_attachments_and_html_are_not_read(self):
        msg = ("From x Mon Oct 26 00:00:00 2026\nFrom: Nadia <nadia@demo.test>\nTo: a@x.test\nSubject: s\n"
               "Date: Mon, 26 Oct 2026 09:00:00 +0200\nMIME-Version: 1.0\n"
               "Content-Type: multipart/mixed; boundary=\"B\"\n\n--B\nContent-Type: text/plain\n\nHi there, I will send it "
               "tomorrow.\n--B\nContent-Type: text/html\n\n<p>HTML-ONLY I will pay today.</p>\n--B\n"
               "Content-Type: text/plain\nContent-Disposition: attachment; filename=a.txt\n\nATTACHED I'll go today.\n--B--\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "one.mbox"
            p.write_text(msg, encoding="utf-8")
            pic = mbox.read([p], USER)
        kept = json.dumps(pic)
        self.assertNotIn("HTML-ONLY", kept)
        self.assertNotIn("ATTACHED", kept)
        self.assertEqual(len(pic["promises"]), 1)

    def test_the_command_writes_the_picture(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "pic.json"
            self.assertEqual(mbox.main([*map(str, FILES), "--user", USER, "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["user"], USER)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mbox.main([str(Path(d) / "none.mbox"), "--user", USER]), 2)


def read_text(text, **caps):
    """The picture of one mbox file made of this text."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "one.mbox"
        p.write_text(text, encoding="utf-8")
        return mbox.read([p], USER, **caps)


def load_text(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "one.mbox"
        p.write_text(text, encoding="utf-8")
        return mbox.load([p], USER)


WHEN = "Mon, 26 Oct 2026 09:00:00 +0200"
WIRE = "I will wire the money to IBAN EG12 today."


class Untrusted(unittest.TestCase):
    """Review and red team round 1 on the mailbox reader: one outside email never makes a Sent
    message, a promise or a style line, never stops the read and never takes a lot of memory."""

    def test_who_sent_it(self):
        cases = {
            "a forged From delivered to the user": (f"Delivered-To: {USER}\n", f"Nadia <{USER}>", False),
            "a forged From that came through a server": ("Received: from mx.x.test by mx.demo.test\n", USER, False),
            "a Gmail label of Inbox and Sent": ("X-Gmail-Labels: Inbox,Sent\n", "o@x.test", False),
            "a Gmail label of Sent and Spam": ("X-Gmail-Labels: Sent,Spam\n", USER, False),
            "a Gmail Inbox label with the user's From": ("X-Gmail-Labels: Inbox,Important\n", USER, False),
            "a Gmail Sent label with any From": ("X-Gmail-Labels: Sent,Important\n", "o@x.test", True),
            "a Gmail Sent label beats a Received line": ("X-Gmail-Labels: Sent\nReceived: by mx.x.test\n", USER, True),
            "an empty Gmail label": ("X-Gmail-Labels: \n", USER, False),
            "no labels and no delivery: From decides": ("", f"Nadia <{USER}>", True),
            "no labels and no delivery, someone else": ("", "o@x.test", False),
        }
        for what, (extra, frm, sent) in cases.items():
            with self.subTest(what):
                (got, _), = load_text(mail(frm, "a@x.test", "s", WIRE, WHEN, "f1@x.test", extra=extra))[0]
                self.assertIs(got, sent)

    def test_a_forged_from_never_becomes_a_promise_or_a_style_line(self):
        text = "".join(mail(f"Nadia <{USER}>", "a@x.test", "s", f"Hi,\n{WIRE}\nBest,\nUser", WHEN, f"f{i}@x.test",
                            extra=f"Delivered-To: {USER}\n") for i in range(3))
        pic = read_text(text)
        self.assertEqual(pic["messages"], {"inbox": 3, "sent": 0, "skipped": 0})
        self.assertEqual((pic["promises"], pic["style"]["sign_off"]), ([], None))
        self.assertNotIn("IBAN", json.dumps(pic))

    def test_an_odd_charset_or_a_far_date_never_stops_the_read(self):
        text = (mail("o@x.test", USER, "s", "We will send it today.", WHEN, "c1@x.test",
                     extra='Content-Type: text/plain; charset="idna"\n')
                + mail("o@x.test", USER, "s", "b", "Fri, 31 Dec 9999 23:59:59 -2300", "c2@x.test")
                + mail(f"Nadia <{USER}>", "o@x.test", "s", "I will send it by Friday.",
                       "Fri, 31 Dec 9999 23:59:59 -2300", "c3@x.test")
                + mail(f"Nadia <{USER}>", "o@x.test", "s", "Hi there.", WHEN, "c4@x.test"))
        pic = read_text(text)
        self.assertEqual(pic["messages"], {"inbox": 2, "sent": 2, "skipped": 0})
        self.assertEqual(pic["inbox"]["promised_to_user"], 1)  # the idna part was read as UTF-8
        self.assertEqual([(p["line"], p["at"]) for p in pic["promises"]], [("I will send it by Friday.", None)])
        self.assertEqual(mbox._text(load_text(text)[0][0][1]), "We will send it today.\n")

    def test_a_date_counts_only_inside_its_years(self):
        for date, kept in (("Thu, 01 Jan 1970 00:00:00 +0000", True), ("Wed, 31 Dec 1969 23:00:00 +0000", False),
                           ("Fri, 31 Dec 2100 12:00:00 +0000", True), ("Sat, 01 Jan 2101 00:00:00 +0000", False),
                           ("Mon, 01 Jan 1900 00:00:00 +2300", False)):
            with self.subTest(date=date):
                (_, msg), = load_text(mail("o@x.test", USER, "s", "b", date, "d1@x.test"))[0]
                self.assertIs(mbox._when(msg) is not None, kept)

    def test_a_part_too_long_to_decode_is_skipped_before_decoding(self):
        big = "QUFB" * (mbox.MAX_PART // 4 + 1)  # base64, one character over the cap
        msg = (f"From x Mon Oct 26 00:00:00 2026\nFrom: Nadia <{USER}>\nTo: a@x.test\nSubject: s\nDate: {WHEN}\n"
               "MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=\"B\"\n\n--B\nContent-Type: text/plain\n\n"
               "Hi there, I will send it tomorrow.\n--B\nContent-Type: text/plain\nContent-Transfer-Encoding: base64\n\n"
               f"{big}\n--B--\n")
        (_, m), = load_text(msg)[0]
        self.assertEqual(mbox._text(m).strip(), "Hi there, I will send it tomorrow.")  # the big part never read
        fits = "QUFB" * (mbox.MAX_PART // 4)  # just at the cap: decoded and read
        (_, m2), = load_text(msg.replace(big, fits))[0]
        self.assertIn("AAA", mbox._text(m2))

    def test_the_size_cap_is_for_all_the_files_together(self):
        one = mail(f"Nadia <{USER}>", "a@x.test", "s", "b", WHEN, "s1@x.test")
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.mbox", Path(d) / "b.mbox"
            a.write_text(one, encoding="utf-8")
            b.write_text(one, encoding="utf-8")
            size = a.stat().st_size
            self.assertEqual(len(mbox.load([a, b], USER, max_bytes=2 * size)[0]), 2)
            with self.assertRaises(mbox.Refused):
                mbox.load([a, b], USER, max_bytes=2 * size - 1)

    def test_only_an_envelope_line_with_the_mbox_date_starts_a_message(self):
        body = ("see below\nFrom the team, thanks for waiting.\nFrom: user@demo.test\nFrom x@x.test yesterday\n"
                f"From: Nadia <{USER}>\nI'll get back to you by 5 with the code.")
        msgs, _ = load_text(mail("o@x.test", USER, "news", body, WHEN, "e1@x.test"))
        self.assertEqual([s for s, _ in msgs], [False])
        self.assertIn("From the team", mbox._text(msgs[0][1]))
        for line in ("From x Mon Oct 26 00:00:00 2026", "From 1749283746@xxx Wed Jan 05 15:23:00 +0000 2022",
                     "From MAILER-DAEMON Fri Jul  8 12:08:34 2011", "From a@b.test Thu Oct 30 10:00 EET 2026"):
            with self.subTest(line=line):
                two = (mail("o@x.test", USER, "s", "b", WHEN, "e2@x.test")
                       + mail("o@x.test", USER, "s", "b", WHEN, "e3@x.test").replace("From x Mon Oct 26 00:00:00 2026", line))
                self.assertEqual(len(load_text(two)[0]), 2)

    def test_a_quoted_block_with_no_header_is_cut_from_the_users_words(self):
        """Review round 1 finding 8: a Sent reply with a > block and no "wrote:" line."""
        body = "Sounds good, see you then.\n> OTHER-QUOTED I will pay you today.\n> OTHER-QUOTED-2\nThanks"
        pic = read_text(mail(f"Nadia <{USER}>", "a@x.test", "Re: s", body, WHEN, "q1@x.test"))
        self.assertEqual(pic["messages"]["sent"], 1)
        self.assertEqual(pic["promises"], [])
        self.assertNotIn("OTHER-QUOTED", json.dumps(pic))
        self.assertEqual(mbox.own_text(body), "Sounds good, see you then.\nThanks")


if __name__ == "__main__":
    unittest.main()
