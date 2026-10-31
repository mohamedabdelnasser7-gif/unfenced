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


if __name__ == "__main__":
    unittest.main()
