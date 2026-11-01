import contextlib
import http.client
import io
import json
import os
import secrets
import socket
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from channels import whatsapp as wa
from sales import loop
from kit import limits as limits_mod
from kit import media
from kit import switch
from kit.chats import Chats
from kit.db import Db
from kit.limits import Limits
from kit.model import ModelError
from reflection.lessons import Lessons
from reflection.results import Results
from tests.fake_model import FakeModel, call, clean_env, say

# Test values are made fresh on every run; none is a real key.
APP = secrets.token_hex(20)
OTHER = secrets.token_hex(20)
VERIFY = secrets.token_urlsafe(12)
BEARER = secrets.token_urlsafe(12)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
GIF = b"GIF89a" + b"\x00" * 200


def payload(*messages, pnid="111"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "201000000000", "phone_number_id": pnid},
        "messages": list(messages)}}]}]}


def text_msg(mid, body, frm="201111111111"):
    return {"from": frm, "id": mid, "timestamp": "1761600000", "type": "text", "text": {"body": body}}


def image_msg(mid, caption="", mime="image/jpeg"):
    return {"from": "201111111111", "id": mid, "timestamp": "1761600000", "type": "image",
            "image": {"id": "MEDIA1", "mime_type": mime, "caption": caption}}


def audio_msg(mid):
    return {"from": "201111111111", "id": mid, "timestamp": "1761600000", "type": "audio",
            "audio": {"id": "MEDIA2", "mime_type": "audio/ogg; codecs=opus", "voice": True}}


class SignatureCheck(unittest.TestCase):
    body = json.dumps(payload(text_msg("wamid.1", "hi"))).encode()

    def test_good(self):
        self.assertTrue(wa.verify_signature(self.body, wa.sign(self.body, APP), APP))

    def test_bad(self):
        self.assertFalse(wa.verify_signature(self.body, wa.sign(self.body, OTHER), APP))

    def test_missing(self):
        self.assertFalse(wa.verify_signature(self.body, None, APP))
        self.assertFalse(wa.verify_signature(self.body, "", APP))

    def test_tampered_body(self):
        sig = wa.sign(self.body, APP)
        self.assertFalse(wa.verify_signature(self.body.replace(b"hi", b"ho"), sig, APP))

    def test_malformed_header(self):
        hexsig = wa.sign(self.body, APP).split("=", 1)[1]
        for bad in (hexsig, "sha1=" + hexsig, "sha256=" + hexsig.upper(), "sha256=" + hexsig + " ", "sha256=zz"):
            self.assertFalse(wa.verify_signature(self.body, bad, APP), bad)

    def test_no_app_secret(self):
        self.assertFalse(wa.verify_signature(self.body, wa.sign(self.body, ""), ""))


class WebhookServer(unittest.TestCase):
    def setUp(self):
        self.got = []
        handler = wa.make_handler(APP, VERIFY, self.got.extend, "111")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/webhook"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(5)

    def request(self, raw=None, sig=None, query=None):
        headers = {"Content-Type": "application/json"}
        if sig is not None:
            headers["X-Hub-Signature-256"] = sig
        url = self.url + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(url, data=raw, headers=headers, method="POST" if raw is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_unsigned_is_rejected_before_parsing(self):
        self.assertEqual(self.request(b"not json", None)[0], 403)
        self.assertEqual(self.request(b"not json", "sha256=" + "0" * 64)[0], 403)
        # the same broken body, signed, gets as far as the parser: the signature ran first
        self.assertEqual(self.request(b"not json", wa.sign(b"not json", APP))[0], 400)
        self.assertEqual(self.got, [])

    def test_signed_message_is_accepted(self):
        raw = json.dumps(payload(text_msg("wamid.1", "عندكم جزم مقاس ٤٣؟"))).encode()
        self.assertEqual(self.request(raw, wa.sign(raw, APP)), (200, "ok"))
        self.assertEqual([(i.message_id, i.text) for i in self.got], [("wamid.1", "عندكم جزم مقاس ٤٣؟")])

    def test_tampered_body_is_rejected(self):
        raw = json.dumps(payload(text_msg("wamid.1", "hi"))).encode()
        sig = wa.sign(raw, APP)
        self.assertEqual(self.request(raw.replace(b"hi", b"yo"), sig)[0], 403)
        self.assertEqual(self.got, [])

    def test_other_phone_number_is_skipped(self):
        raw = json.dumps(payload(text_msg("wamid.1", "hi"), pnid="999")).encode()
        self.assertEqual(self.request(raw, wa.sign(raw, APP))[0], 200)
        self.assertEqual(self.got, [])

    def test_too_large_is_refused_unread(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        conn.putrequest("POST", "/webhook")
        conn.putheader("Content-Length", str(wa.MAX_BODY + 1))
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()
        self.assertEqual(self.got, [])

    def test_handshake(self):
        good = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
        self.assertEqual(self.request(query=good), (200, "1158201444"))
        self.assertEqual(self.request(query={**good, "hub.verify_token": VERIFY + "x"})[0], 403)
        self.assertEqual(self.request(query={**good, "hub.mode": "unsubscribe"})[0], 403)
        self.assertEqual(self.request(query={**good, "hub.challenge": "<b>"})[0], 403)

    def test_short_app_secret_refused(self):
        with self.assertRaises(ValueError):
            wa.make_handler("short", VERIFY, print)

    def test_negative_length_is_refused_unread(self):
        # Content-Length -1 would make rfile.read(-1) wait for the client to close
        s = socket.create_connection(("127.0.0.1", self.srv.server_address[1]), timeout=5)
        self.addCleanup(s.close)
        s.sendall(b"POST /webhook HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n{}")
        s.shutdown(socket.SHUT_WR)
        self.assertEqual(s.makefile("rb").readline().split(b" ")[1], b"413")
        self.assertEqual(self.got, [])

    def test_request_log_never_holds_the_verify_token(self):
        err = io.StringIO()
        good = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
        with self.assertLogs("channels.whatsapp", "INFO") as logs, contextlib.redirect_stderr(err):
            self.assertEqual(self.request(query=good)[0], 200)
            self.assertEqual(self.request(query={**good, "hub.verify_token": VERIFY + "x"})[0], 403)
        text = "\n".join(logs.output) + err.getvalue()
        self.assertIn("GET /webhook", text)
        self.assertNotIn(VERIFY, text)


class StalledBody(unittest.TestCase):
    HEAD = b"POST /webhook HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n"

    def serve(self, prepare=None, **kw):
        self.got = []
        handler = wa.make_handler(APP, VERIFY, self.got.extend, **kw)
        if prepare:
            prepare(handler)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.port = srv.server_address[1]
        return self.connect()

    def connect(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=6)
        self.addCleanup(s.close)
        return s

    def signed(self, message_id):
        raw = json.dumps(payload(text_msg(message_id, "hi"))).encode()
        head = (b"POST /webhook HTTP/1.1\r\nHost: x\r\nX-Hub-Signature-256: " + wa.sign(raw, APP).encode()
                + b"\r\nContent-Length: " + str(len(raw)).encode() + b"\r\n\r\n")
        return head, raw

    def trickle(self, s, data, every=0.3):
        """Send data a byte at a time until the server closes the connection."""
        for b in data:
            try:
                s.sendall(bytes([b]))
            except OSError:
                return
            time.sleep(every)

    def test_defaults(self):
        handler = wa.make_handler(APP, VERIFY, print)
        self.assertEqual(handler.timeout, 10)
        self.assertEqual((wa.SOCKET_TIMEOUT, wa.REQUEST_DEADLINE), (10, 15))
        self.assertEqual((wa.MAX_OPEN, wa.FIRST_LINE_DEADLINE), (32, 5))
        self.assertEqual([handler.slots.acquire(False) for _ in range(33)], [True] * 32 + [False])

    def test_open_connections_are_capped(self):
        held, freed = threading.Event(), threading.Event()

        def watch(handler):
            real = handler.slots

            class Watched:
                def acquire(self, blocking=True):
                    got = real.acquire(blocking)
                    if got:
                        held.set()
                    return got

                def release(self):
                    real.release()
                    freed.set()

            handler.slots = Watched()

        first = self.serve(prepare=watch, max_open=1)  # idle: holds the one slot
        self.assertTrue(held.wait(3))
        with self.assertLogs("channels.whatsapp", "INFO"):
            self.assertTrue(self.connect().makefile("rb").read().startswith(b"HTTP/1.0 503"))
        self.assertFalse(freed.is_set())
        first.close()
        self.assertTrue(freed.wait(3))
        head, raw = self.signed("wamid.10")
        s = self.connect()
        s.sendall(head + raw)
        self.assertTrue(s.makefile("rb").read().startswith(b"HTTP/1.0 200"))
        self.assertEqual([i.message_id for i in self.got], ["wamid.10"])

    def test_an_idle_connection_is_cut_at_the_first_line_deadline(self):
        s = self.serve(first_line=1, timeout=4)
        start = time.monotonic()
        with self.assertLogs("channels.whatsapp", "INFO"):
            self.assertEqual(s.makefile("rb").read(), b"")  # closed with no reply
        self.assertLess(time.monotonic() - start, 3)

    def test_after_the_first_line_the_full_deadline_holds(self):
        head, raw = self.signed("wamid.11")
        line, rest = head.split(b"\r\n", 1)
        s = self.serve(first_line=1, deadline=3)
        s.sendall(line + b"\r\n")
        time.sleep(1.5)
        s.sendall(rest + raw)
        self.assertTrue(s.makefile("rb").read().startswith(b"HTTP/1.0 200"))
        self.assertEqual([i.message_id for i in self.got], ["wamid.11"])

    def test_stalled_body_gets_408(self):
        s = self.serve(timeout=1)
        start = time.monotonic()
        with self.assertLogs("channels.whatsapp", "INFO"):
            s.sendall(self.HEAD)
            reply = s.makefile("rb").read()
        self.assertTrue(reply.startswith(b"HTTP/1.0 408"), reply[:40])
        self.assertLess(time.monotonic() - start, 3)

    def test_trickled_body_is_cut_at_the_deadline(self):
        s = self.serve(timeout=1, deadline=2)
        s.sendall(self.HEAD)
        start = time.monotonic()
        threading.Thread(target=self.trickle, args=(s, b"x" * 100), daemon=True).start()
        with self.assertLogs("channels.whatsapp", "INFO"):
            reply = s.makefile("rb").read()
        self.assertTrue(reply.startswith(b"HTTP/1.0 408"), reply[:40])
        self.assertLess(time.monotonic() - start, 4)

    def test_trickled_headers_are_cut_at_the_deadline(self):
        s = self.serve(timeout=1, deadline=2)
        start = time.monotonic()
        threading.Thread(target=self.trickle, args=(s, self.HEAD * 10), daemon=True).start()
        with self.assertLogs("channels.whatsapp", "INFO"):
            self.assertEqual(s.makefile("rb").read(), b"")  # closed with no reply
        self.assertLess(time.monotonic() - start, 4)

    def test_a_normal_request_still_works(self):
        raw = json.dumps(payload(text_msg("wamid.9", "hi"))).encode()
        s = self.serve(timeout=1, deadline=2)
        s.sendall(b"POST /webhook HTTP/1.1\r\nHost: x\r\nX-Hub-Signature-256: " + wa.sign(raw, APP).encode()
                  + b"\r\nContent-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw)
        self.assertTrue(s.makefile("rb").read().startswith(b"HTTP/1.0 200"))
        self.assertEqual([i.message_id for i in self.got], ["wamid.9"])

class Parsing(unittest.TestCase):
    def test_text_audio_image(self):
        items = wa.parse(payload(text_msg("a", "hi"), audio_msg("b"), image_msg("c", caption="3ndko de?"),
                                 {"from": "2011", "id": "d", "type": "sticker", "sticker": {}}), "111")
        self.assertEqual([i.kind for i in items], ["text", "audio", "image"])
        self.assertEqual(items[1].media_id, "MEDIA2")
        self.assertEqual((items[2].media_id, items[2].media_mime, items[2].text), ("MEDIA1", "image/jpeg", "3ndko de?"))
        self.assertEqual(items[0].timestamp, 1761600000)

    def test_junk_is_ignored(self):
        self.assertEqual(wa.parse({"entry": "x"}), [])
        self.assertEqual(wa.parse([1, 2]), [])
        self.assertEqual(wa.parse(payload({"type": "text"})), [])

    def test_retries_are_deduped(self):
        app = wa.App(Chats(Db(":memory:")), None, None, None, None)
        self.addCleanup(app.chats.db.close)
        items = wa.parse(payload(text_msg("wamid.same", "hi")))
        app.accept(items)
        app.accept(items)
        self.assertEqual(app.q.qsize(), 1)


class FakeResp:
    def __init__(self, data):
        self.data, self.reads = data, []

    def read(self, n=-1):
        self.reads.append(n)
        return self.data if n is None or n < 0 else self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGraph:
    def __init__(self, data=JPEG, mime="image/jpeg", error=None):
        self.data, self.mime, self.error, self.calls, self.caps = data, mime, error, 0, []

    def download(self, media_id, max_bytes):
        self.calls += 1
        self.caps.append(max_bytes)
        if self.error:
            raise self.error
        return self.data, self.mime


class Photos(unittest.TestCase):
    def inc(self, mime="image/jpeg", caption=""):
        return wa.parse(payload(image_msg("img", caption=caption, mime=mime)))[0]

    def test_photo_is_kept(self):
        msg = wa.to_message(self.inc(caption="3ndko de?"), FakeGraph())
        self.assertEqual((len(msg.images), msg.rejected_images, msg.text), (1, 0, "3ndko de?"))
        self.assertEqual(msg.images[0].mime, "image/jpeg")

    def test_the_channel_normalises_both_types_before_the_check(self):
        """Review t261030m round 1: check_image takes the type as given, so the channel must clean it."""
        msg = wa.to_message(self.inc(mime="IMAGE/JPEG; charset=x"), FakeGraph(JPEG, "Image/JPEG; q=1"))
        self.assertEqual((len(msg.images), msg.rejected_images), (1, 0))
        self.assertEqual(msg.images[0].mime, "image/jpeg")

    def test_wrong_declared_type_is_rejected_without_download(self):
        g = FakeGraph(GIF, "image/gif")
        msg = wa.to_message(self.inc(mime="image/gif"), g)
        self.assertEqual((len(msg.images), msg.rejected_images, g.calls), (0, 1, 0))

    def test_bytes_must_match_the_type(self):
        msg = wa.to_message(self.inc(), FakeGraph(GIF, "image/jpeg"))
        self.assertEqual((len(msg.images), msg.rejected_images), (0, 1))

    def test_oversize_is_rejected(self):
        msg = wa.to_message(self.inc(), FakeGraph(error=wa.TooBig("img")))
        self.assertEqual((len(msg.images), msg.rejected_images), (0, 1))
        big = b"\xff\xd8\xff" + b"\x00" * media.MAX_IMAGE_BYTES
        self.assertEqual(media.check_image(big, "image/jpeg"), (False, "size"))

    def test_graph_download_stops_at_the_cap(self):
        seen = []

        def opener(req, timeout):
            seen.append(req)
            if len(seen) == 1:
                return FakeResp(json.dumps({"url": "https://lookaside.fbsbx.com/x", "mime_type": "image/jpeg",
                                            "file_size": 10}).encode())
            return FakeResp(b"\xff\xd8\xff" + b"\x00" * 100)

        reads = []

        def recording(req, timeout):
            r = opener(req, timeout)
            reads.append(r.reads)
            return r

        g = wa.Graph(BEARER, "111", opener=recording)
        with self.assertRaises(wa.TooBig):
            g.download("123", max_bytes=50)
        self.assertEqual(seen[0].full_url, "https://graph.facebook.com/v26.0/123?phone_number_id=111")
        self.assertEqual(seen[1].get_header("Authorization"), "Bearer " + BEARER)
        # the media body is read with a cap of max_bytes + 1, never in full
        self.assertEqual(reads[1], [51])

    def test_graph_refuses_declared_oversize(self):
        calls = []

        def opener(req, timeout):
            calls.append(req)
            return FakeResp(json.dumps({"url": "https://x", "file_size": 999}).encode())

        with self.assertRaises(wa.TooBig):
            wa.Graph(BEARER, "111", opener=opener).download("123", max_bytes=50)
        self.assertEqual(len(calls), 1)

    def test_send_shape(self):
        seen = []

        def opener(req, timeout):
            seen.append(req)
            return FakeResp(b'{"messages":[{"id":"wamid.out"}]}')

        wa.Graph(BEARER, "111", opener=opener).send("201111111111", "تمام")
        body = json.loads(seen[0].data)
        self.assertEqual(seen[0].full_url, "https://graph.facebook.com/v26.0/111/messages")
        self.assertEqual((body["to"], body["type"], body["text"]["body"]), ("201111111111", "text", "تمام"))


    def test_typing_shape(self):
        seen, waits = [], []

        def opener(req, timeout):
            seen.append(req)
            waits.append(timeout)
            return FakeResp(b'{"success":true}')

        self.assertTrue(wa.Graph(BEARER, "111", opener=opener).typing("wamid.HBgM_abc="))
        body = json.loads(seen[0].data)
        self.assertEqual(seen[0].full_url, "https://graph.facebook.com/v26.0/111/messages")
        self.assertEqual(body, {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.HBgM_abc=",
                                "typing_indicator": {"type": "text"}})
        # the dots wait at most TYPING_TIMEOUT, never the 20 s a reply may take (review typing r1 finding 1)
        self.assertTrue(wa.Graph(BEARER, "111", opener=opener, timeout=1).typing("wamid.x"))
        self.assertEqual((wa.TYPING_TIMEOUT, waits), (3, [3, 1]))

    def test_typing_never_raises_and_skips_odd_ids(self):
        calls = []

        def refused(req, timeout):
            calls.append(req)
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"{}"))

        g = wa.Graph(BEARER, "111", opener=refused)
        with self.assertLogs("channels.whatsapp", "WARNING"):
            self.assertFalse(g.typing("wamid.ok"))
        for odd in ("", "abc", "wamid.", "wamid.a b", "wamid.a\n", None, 12345, b"wamid.ok", ["wamid.ok"]):
            self.assertFalse(g.typing(odd))
        self.assertEqual(len(calls), 1)


OGG = b"OggS" + b"\x00" * 60


class MediaPinning(unittest.TestCase):
    def graph(self, url):
        """A Graph whose media info points at url. Returns (requests made, graph)."""
        calls = []

        def opener(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                return FakeResp(json.dumps({"url": url, "mime_type": "audio/ogg", "file_size": 10}).encode())
            return FakeResp(OGG)

        return calls, wa.Graph(BEARER, "111", opener=opener)

    def test_media_url_must_be_https_on_metas_host(self):
        for url in ("http://lookaside.fbsbx.com/x", "ftp://lookaside.fbsbx.com/x", "https://evil.example/x",
                    "https://lookaside.fbsbx.com.evil.example/x", "https://evil.example/lookaside.fbsbx.com",
                    "https://user@lookaside.fbsbx.com/x", "https://user:pw@lookaside.fbsbx.com/x",
                    "https://lookaside.fbsbx.com:8443/x", "https://lookaside.fbsbx.com:80/x",
                    "https://lookaside.fbsbx.com:abc/x", "//lookaside.fbsbx.com/x", ""):
            with self.subTest(url=url):
                calls, g = self.graph(url)
                with self.assertRaises(ValueError):
                    g.download("123", 100)
                self.assertEqual(len(calls), 1)  # the token never went to the media url

    def test_metas_media_host_is_fetched(self):
        for url in ("https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1",
                    "https://lookaside.fbsbx.com:443/x"):
            with self.subTest(url=url):
                calls, g = self.graph(url)
                self.assertEqual(g.download("123", 100), (OGG, "audio/ogg"))
                self.assertEqual(calls[1].full_url, url)

    def test_media_id_shape(self):
        for bad in ("../x", "a/b", "1?x=2", "", "x" * 129, "١٢٣", None):
            with self.subTest(media_id=bad):
                calls = []
                g = wa.Graph(BEARER, "111", opener=lambda req, timeout: calls.append(req))
                with self.assertRaises(ValueError):
                    g.download(bad, 100)
                self.assertEqual(calls, [])

    def test_graph_opener_refuses_redirects(self):
        director = wa.Graph(BEARER, "111")._open.__self__
        self.assertIsInstance(director, urllib.request.OpenerDirector)
        self.assertTrue(any(isinstance(h, wa.NoRedirects) for h in director.handlers))
        self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in director.handlers))

    def test_redirect_is_not_followed(self):
        hits = []

        class Redirecting(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302 if self.path == "/a" else 200)
                if self.path == "/a":
                    self.send_header("Location", "/b")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Redirecting)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/a",
                                     headers={"Authorization": "Bearer " + BEARER})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            wa.no_redirect_opener().open(req, timeout=5)
        cm.exception.close()
        self.assertEqual((cm.exception.code, hits), (302, ["/a"]))


class VoiceNotes(unittest.TestCase):
    def inc(self, mime="audio/ogg; codecs=opus"):
        m = audio_msg("v1")
        m["audio"]["mime_type"] = mime
        return wa.parse(payload(m))[0]

    def test_voice_note_is_fetched_with_the_audio_cap(self):
        g = FakeGraph(OGG, "audio/ogg; codecs=opus")
        msg = wa.to_message(self.inc(), g)
        self.assertEqual((msg.audio, msg.audio_failed), (OGG, False))
        self.assertEqual(g.caps, [16 * 1024 * 1024])

    def test_voice_must_be_audio_ogg(self):
        g = FakeGraph(OGG, "audio/ogg")
        msg = wa.to_message(self.inc("audio/mpeg"), g)
        self.assertEqual((msg.audio_failed, msg.audio, g.calls), (True, None, 0))  # refused before the download
        for data, mime in ((OGG, "audio/mpeg"), (OGG, "video/ogg"), (b"", "audio/ogg")):
            with self.subTest(mime=mime, size=len(data)):
                msg = wa.to_message(self.inc(), FakeGraph(data, mime))
                self.assertEqual((msg.audio_failed, msg.audio), (True, None))

    def test_failed_voice_download(self):
        for err in (wa.TooBig("v1"), ValueError("media url is not on Meta's media host"), OSError("down")):
            with self.subTest(err=type(err).__name__), self.assertLogs("channels.whatsapp", "ERROR"):
                msg = wa.to_message(self.inc(), FakeGraph(error=err))
                self.assertEqual((msg.audio_failed, msg.audio), (True, None))


class Queueing(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)

    def app(self, **kw):
        return wa.App(self.chats, None, None, None, None, **kw)

    def test_default_queue_size(self):
        self.assertEqual((wa.MAX_QUEUE, self.app().q.maxsize), (200, 200))

    def test_full_queue_is_busy_and_forgets_the_id(self):
        app = self.app(maxsize=1)
        app.accept(wa.parse(payload(text_msg("m1", "hi"))))
        with self.assertRaises(wa.Busy):
            app.accept(wa.parse(payload(text_msg("m2", "hi again"))))
        self.assertEqual(app.q.qsize(), 1)
        self.assertFalse(self.chats.first_seen("m1"))  # kept
        self.assertTrue(self.chats.first_seen("m2"))   # forgotten, so Meta's retry is taken

    def test_webhook_answers_503_when_full(self):
        app = self.app(maxsize=1)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), wa.make_handler(APP, VERIFY, app.accept, "111"))
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def post(mid):
            raw = json.dumps(payload(text_msg(mid, "hi"))).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/webhook", data=raw,
                                         headers={"X-Hub-Signature-256": wa.sign(raw, APP)}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                with e:
                    return e.code

        self.assertEqual(post("m1"), 200)
        with self.assertLogs("channels.whatsapp", "WARNING"):
            self.assertEqual(post("m2"), 503)
        app.q.get_nowait()
        self.assertEqual(post("m2"), 200)  # Meta's retry is taken once there is room
        self.assertEqual(app.q.get_nowait()[1].message_id, "m2")

    def test_accept_marks_customers_over_a_limit(self):
        limits = Limits(self.db, per_customer=1, window=600, daily=3)
        limits.take(limits_mod.key("whatsapp", "201111111111"))
        app = self.app(limits=limits)
        app.accept(wa.parse(payload(text_msg("m1", "hi"), text_msg("m2", "hi", frm="202222222222"))))
        items = [app.q.get_nowait() for _ in range(2)]
        self.assertEqual([(over, inc.message_id) for over, inc in items], [("customer", "m1"), (None, "m2")])
        limits.take(limits_mod.key("whatsapp", "203333333333"))
        limits.take(limits_mod.key("whatsapp", "204444444444"))
        app.accept(wa.parse(payload(text_msg("m3", "hi", frm="202222222222"))))
        self.assertEqual(app.q.get_nowait()[0], "daily")

    def test_pending_messages_are_requeued_at_start(self):
        self.app().accept(wa.parse(payload(text_msg("m1", "hi"))))
        app = self.app()  # the process stopped before the turn was saved
        self.assertEqual(app.requeue_pending(), 1)
        over, inc = app.q.get_nowait()
        self.assertEqual((over, inc.message_id, inc.text, inc.kind), (None, "m1", "hi", "text"))


class SendingGraph(FakeGraph):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.sent = []

    def send(self, to, text):
        self.sent.append((to, text))
        return {"ok": True}


class WorkerTurns(unittest.TestCase):
    """Messages through App.accept and work_one, the way the worker runs them."""
    WHO = "201111111111"

    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)
        self.graph = SendingGraph(OGG, "audio/ogg; codecs=opus")

    def run_one(self, message, model=None, limits=None):
        app = wa.App(self.chats, model or FakeModel(), Lessons(self.db), Results(self.db), self.graph, limits=limits)
        app.accept(wa.parse(payload(message)))
        return app.work_one(app.q.get_nowait())

    def over_limit(self):
        limits = Limits(self.db, per_customer=1, window=600, daily=100)
        limits.take(limits_mod.key("whatsapp", self.WHO))
        return limits

    def test_an_answered_turn_leaves_nothing_pending(self):
        r = self.run_one(text_msg("m1", "hello there, a question"), FakeModel(say("Ask me anything.")))
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.chats.pending(), [])

    def test_an_over_limit_turn_leaves_nothing_pending(self):
        r = self.run_one(text_msg("m1", "hello there, a question"), limits=self.over_limit())
        self.assertEqual(r.outcome, "limited")
        self.assertEqual(self.chats.pending(), [])

    def test_an_over_limit_voice_note_is_never_downloaded(self):
        r = self.run_one(audio_msg("v1"), limits=self.over_limit())
        self.assertEqual((r.outcome, self.graph.calls), ("limited", 0))
        self.assertEqual(self.chats.pending(), [])


class TypingGraph(SendingGraph):
    """Keeps the typing dots and the sends in one ordered list, events, which the model shares."""

    def __init__(self, *a, events=None, answer=True, **kw):
        super().__init__(*a, **kw)
        self.events = events if events is not None else []
        self.answer = answer  # what typing returns; False is a refusal

    def typing(self, message_id):
        self.events.append(("typing", message_id))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def send(self, to, text):
        self.events.append(("send", text))
        return super().send(to, text)


class InOrderModel(FakeModel):
    """FakeModel that adds ("model",) to the shared events at each call."""

    def __init__(self, events, *script):
        super().__init__(*script)
        self.events = events

    def chat(self, messages, **kw):
        self.events.append(("model",))
        return super().chat(messages, **kw)


class TypingDots(unittest.TestCase):
    """The typing dots through work_one: once, with the message's wamid, right before the first model
    call, and only for a turn that will answer (review typing r1 findings 2 and 3)."""
    WHO = WorkerTurns.WHO
    WAMID = "wamid.HBgMMjAxMTExMTExMTExFQIAEhgg"
    ANSWER = "Ask me anything."

    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats = Chats(self.db)
        self.events = []
        self.graph = TypingGraph(OGG, "audio/ogg; codecs=opus", events=self.events)

    def app(self, *script, limits=None):
        return wa.App(self.chats, InOrderModel(self.events, *script), Lessons(self.db), Results(self.db), self.graph,
                      limits=limits)

    def run_one(self, message, *script, limits=None):
        app = self.app(*script, limits=limits)
        app.accept(wa.parse(payload(message)))
        return app.work_one(app.q.get_nowait())

    def limits(self, taken):
        limits = Limits(self.db, per_customer=1, window=600, daily=100)
        if taken:
            limits.take(limits_mod.key("whatsapp", self.WHO))
        return limits

    def test_dots_once_with_the_wamid_right_before_the_model_call(self):
        r = self.run_one(text_msg(self.WAMID, "hello there, a question"), say(self.ANSWER), limits=self.limits(False))
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.events, [("typing", self.WAMID), ("model",), ("send", self.ANSWER)])

    def test_dots_once_for_a_turn_of_many_model_calls(self):
        r = self.run_one(text_msg(self.WAMID, "hello there, a question"), say(""), say(self.ANSWER))
        self.assertEqual(r.outcome, "replied")
        self.assertEqual(self.events, [("typing", self.WAMID), ("model",), ("model",), ("send", self.ANSWER)])

    def test_the_reply_goes_out_when_the_dots_are_refused(self):
        for answer in (False, RuntimeError("down")):
            with self.subTest(answer=answer):
                self.events.clear()
                self.graph.answer = answer
                with self.assertLogs("sales.loop", "WARNING") if isinstance(answer, Exception) else contextlib.nullcontext():
                    r = self.run_one(text_msg(f"{self.WAMID}{len(self.graph.sent)}", "hello there, a question"),
                                     say(self.ANSWER))
                self.assertEqual(r.outcome, "replied")
                self.assertEqual([e[0] for e in self.events], ["typing", "model", "send"])
                self.assertEqual(self.graph.sent[-1], (self.WHO, self.ANSWER))

    def test_no_dots_over_a_limit_found_at_the_webhook(self):
        r = self.run_one(text_msg(self.WAMID, "hello there, a question"), limits=self.limits(True))
        self.assertEqual(r.outcome, "limited")
        self.assertEqual([e[0] for e in self.events], ["send"])  # the limit line only

    def test_no_dots_over_a_limit_reached_after_the_webhook(self):
        limits = self.limits(False)
        app = self.app(limits=limits)
        app.accept(wa.parse(payload(text_msg(self.WAMID, "hello there, a question"))))
        limits.take(limits_mod.key("whatsapp", self.WHO))  # another message's turn used the last call
        item = app.q.get_nowait()
        self.assertIsNone(item[0])
        self.assertEqual(app.work_one(item).outcome, "limited")
        self.assertEqual([e[0] for e in self.events], ["send"])

    def test_no_dots_when_the_agent_is_paused(self):
        switch.pause(db=self.db)
        r = self.run_one(text_msg(self.WAMID, "hello there, a question"), say(self.ANSWER))
        self.assertEqual(r.outcome, loop.PAUSED)
        self.assertEqual(self.events, [])

    def test_no_dots_for_a_turn_of_fixed_lines_only(self):
        self.graph.error = OSError("down")
        with self.assertLogs("channels.whatsapp", "ERROR"):
            r = self.run_one(image_msg(self.WAMID))
        self.assertEqual(r.outcome, "replied")
        self.assertEqual([e[0] for e in self.events], ["send"])  # the photo line, no model call

    def test_no_safe_reply_sends_nothing_after_the_dots(self):
        r = self.run_one(text_msg(self.WAMID, "hello there, a question"), say(""), say(""), say(""))
        self.assertEqual(r.outcome, "no_safe_reply")
        self.assertEqual(self.events, [("typing", self.WAMID), ("model",), ("model",), ("model",)])
        self.assertEqual(self.graph.sent, [])


class CrashedTurns(unittest.TestCase):
    """A turn that crashes in code, through App.work like the worker runs it."""
    WHO = WorkerTurns.WHO
    LINE = loop.MODEL_DOWN["arabic"]

    def setUp(self):
        clean_env(self)
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.chats, self.results = Chats(self.db), Results(self.db)
        self.graph = SendingGraph(OGG, "audio/ogg; codecs=opus")
        self.app = wa.App(self.chats, FakeModel(), Lessons(self.db), self.results, self.graph)

    def crash(self, *messages, when=None, after=False):
        """Queue the messages and run the worker. work_one raises, on every call or on the calls
        when(n) picks; after=True runs the real turn first, as a bug after the reply would."""
        real, n = self.app.work_one, [0]

        def work_one(item):
            n[0] += 1
            if when is not None and not when(n[0]):
                return real(item)
            if after:
                real(item)
            raise RuntimeError("a bug in the turn")

        self.app.accept(wa.parse(payload(*messages)))
        self.app.q.put(None)
        with mock.patch.object(self.app, "work_one", side_effect=work_one), self.assertLogs(level="WARNING"):
            self.app.work()  # returns at the None: no crash escapes

    def chat(self):
        return self.chats.open("whatsapp", self.WHO)

    def outcomes(self):
        return [(r["outcome"], (r["detail"] or {}).get("by"), (r["detail"] or {}).get("in_a_row"))
                for r in self.results.for_chat(self.chat())]

    def test_a_crash_sends_the_model_down_line_and_saves_the_message(self):
        self.crash(text_msg("m1", "عندكم جزم؟"))
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])
        cid = self.chat()
        self.assertEqual((self.chats.stage(cid), self.chats.model_errors(cid)), ("asking", 1))
        self.assertEqual(self.outcomes(), [("turn_failed", None, 1)])
        self.assertEqual([(s["role"], s["content"]) for s in self.chats.steps(cid) if s["role"] != "event"],
                         [("user", "عندكم جزم؟"), ("assistant", self.LINE)])
        self.assertEqual(self.chats.pending(), [])

    def test_the_line_follows_the_customer_script(self):
        self.crash(text_msg("m1", "hello there, a question"))
        self.assertEqual(self.graph.sent, [(self.WHO, loop.MODEL_DOWN["english"])])

    def test_a_photo_that_crashed_is_saved_as_a_photo(self):
        self.crash(image_msg("p1"))
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])
        users = [s for s in self.chats.steps(self.chat()) if s["role"] == "user"]
        self.assertEqual([(s["content"], s["media"]) for s in users], [(None, [{"kind": "image"}])])
        self.assertEqual(self.chats.pending(), [])

    def test_a_second_crash_in_a_row_is_no_safe_reply_and_sends_nothing(self):
        self.crash(text_msg("m1", "عندكم جزم؟"), text_msg("m2", "عندكم جزم؟"))
        cid = self.chat()
        self.assertEqual((self.chats.stage(cid), self.chats.model_errors(cid)), ("asking", 0))
        self.assertEqual(self.outcomes(), [("turn_failed", None, 1), ("no_safe_reply", "turn_failed", 2)])
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])

    def test_a_model_error_then_a_crash_is_no_safe_reply_and_sends_nothing(self):
        def down(messages, tools_sent):
            raise ModelError("Baseten call failed: URLError")

        self.app.model = FakeModel(down)
        with self.assertLogs("sales.loop", "WARNING"):
            self.assertEqual(self.app.work_one((None, wa.parse(payload(text_msg("m1", "عندكم جزم؟")))[0])).outcome,
                             "model_error")
        self.crash(text_msg("m2", "عندكم جزم؟"))
        self.assertEqual(self.chats.stage(self.chat()), "asking")
        self.assertEqual(self.outcomes()[-1], ("no_safe_reply", "turn_failed", 2))
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])  # the model error's line only

    def test_a_passing_reply_starts_the_count_again(self):
        self.crash(text_msg("m1", "عندكم جزم؟"))
        self.app.model = FakeModel(say("Ask me anything."))
        self.app.work_one((None, wa.parse(payload(text_msg("m2", "hello there, a question")))[0]))
        self.crash(text_msg("m3", "عندكم جزم؟"))
        self.assertEqual(self.chats.stage(self.chat()), "asking")
        self.assertEqual(self.outcomes()[-1], ("turn_failed", None, 1))

    def test_a_crash_after_the_reply_went_out_sends_nothing_more(self):
        self.app.model = FakeModel(say("Ask me anything."))
        self.crash(text_msg("m1", "hello there, a question"), after=True)
        self.assertEqual(self.graph.sent, [(self.WHO, "Ask me anything.")])
        self.assertEqual(self.outcomes(), [("replied", None, None)])
        self.assertEqual(self.chats.model_errors(self.chat()), 0)

    def test_words_next_to_a_tool_call_are_not_a_reply(self):
        def bug(messages, tools_sent):
            raise RuntimeError("a bug in the turn")

        step = call("not_a_tool")
        step["content"] = "Let me check the store."
        self.app.model = FakeModel(step, bug)
        self.app.accept(wa.parse(payload(text_msg("m1", "عندكم جزم؟"))))
        self.app.q.put(None)
        with self.assertLogs(level="WARNING"):
            self.app.work()  # the real turn: the second model step raises a plain bug
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])
        self.assertEqual(self.outcomes(), [("turn_failed", None, 1)])

    def test_a_note_to_the_team_is_not_a_line_to_the_customer(self):
        team = "201000000001"

        def note_then_crash(msg, *, send, **kw):
            send(team, "a note")
            raise RuntimeError("the database is gone")

        with mock.patch.object(loop, "failed_turn", side_effect=note_then_crash):
            self.crash(text_msg("m1", "عندكم جزم؟"))
        self.assertEqual(self.graph.sent, [(team, "a note"), (self.WHO, self.LINE)])

    def test_the_worker_keeps_going_after_a_crash(self):
        self.app.model = FakeModel(say("Ask me anything."))
        self.crash(text_msg("m1", "عندكم جزم؟"), text_msg("m2", "hello there, a question"), when=lambda n: n == 1)
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE), (self.WHO, "Ask me anything.")])
        self.assertEqual([o for o, _, _ in self.outcomes()], ["turn_failed", "replied"])

    def test_if_the_fallback_crashes_too_the_line_goes_out_directly(self):
        with mock.patch.object(loop, "failed_turn", side_effect=RuntimeError("the database is gone")):
            self.crash(text_msg("m1", "عندكم جزم؟"))
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])

    def test_no_second_line_when_the_fallback_sent_one_and_then_crashed(self):
        with mock.patch.object(self.results, "record", side_effect=RuntimeError("the database is gone")):
            self.crash(text_msg("m1", "عندكم جزم؟"))
        self.assertEqual(self.graph.sent, [(self.WHO, self.LINE)])


class RequiredEnv(unittest.TestCase):
    FULL = {**{n: "set" for n in wa.REQUIRED_ENV}, "META_API_KEY": "fake-meta-key-for-tests"}

    def test_one_model_key_of_either_kind_is_enough(self):
        """Review round 1 finding 1, red team finding 5: one Meta key starts the webhook."""
        self.assertNotIn("BASETEN_API_KEY", wa.REQUIRED_ENV)
        base = {k: v for k, v in self.FULL.items() if k not in ("META_API_KEY", "BASETEN_API_KEY")}
        for keys in ({"META_API_KEY": "fake-meta"}, {"BASETEN_API_KEY": "fake-baseten"},
                     {"META_API_KEY": "fake-meta", "BASETEN_API_KEY": "fake-baseten"}):
            with self.subTest(keys=sorted(keys)), mock.patch.dict(os.environ, {**base, **keys}, clear=True):
                self.assertEqual(wa.missing_env(), [])
        for keys in ({}, {"META_API_KEY": " ", "BASETEN_API_KEY": ""}):
            with mock.patch.dict(os.environ, {**base, **keys}, clear=True):
                self.assertEqual(wa.missing_env(), [wa.MODEL_KEYS])
        with mock.patch.dict(os.environ, {k: v for k, v in base.items() if k != "WHATSAPP_TOKEN"}, clear=True):
            self.assertEqual(wa.missing_env(), ["WHATSAPP_TOKEN", wa.MODEL_KEYS])

    def start(self, env):
        """main() with this env and no server or database file, up to building the App."""
        db = Db(":memory:")
        self.addCleanup(db.close)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("kit.env.load", return_value=[]), \
                mock.patch("logging.basicConfig"), mock.patch("sales.loop.warn_size_prices"), \
                mock.patch("kit.db.Db", return_value=db), mock.patch.object(wa, "ThreadingHTTPServer") as server, \
                mock.patch.object(wa, "App", side_effect=StopIteration) as app:
            with self.assertRaises(StopIteration):
                wa.main()
        server.assert_not_called()
        return app.call_args

    def test_the_server_starts_on_one_meta_key_and_the_fast_writer_shares_its_limits(self):
        env = {k: v for k, v in self.FULL.items() if k != "BASETEN_API_KEY"}
        self.assertIn("META_API_KEY", env)
        call = self.start(env)
        limits, fast = call.kwargs["limits"], call.kwargs["fast"]
        self.assertIsInstance(limits, Limits)
        self.assertIs(fast.limits, limits)

    def test_the_server_does_not_start_with_no_model_key(self):
        env = {k: v for k, v in self.FULL.items() if k not in ("META_API_KEY", "BASETEN_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("kit.env.load", return_value=[]), \
                mock.patch("logging.basicConfig"), mock.patch.object(wa, "ThreadingHTTPServer") as server:
            with self.assertRaises(SystemExit) as cm:
                wa.main()
        self.assertEqual(str(cm.exception.code), "Missing in .env: " + wa.MODEL_KEYS)
        server.assert_not_called()

    def test_start_checks_prices_against_size_numbers(self):
        class Stop(Exception):
            pass

        with mock.patch.dict(os.environ, self.FULL, clear=True), mock.patch("kit.env.load", return_value=[]), \
                mock.patch("logging.basicConfig"), mock.patch.object(wa, "ThreadingHTTPServer") as server, \
                mock.patch("sales.loop.warn_size_prices", side_effect=Stop) as warn, \
                mock.patch("kit.db.Db") as db:
            with self.assertRaises(Stop):
                wa.main()
        warn.assert_called_once_with()
        db.assert_not_called()  # the check runs right after the env check, before the database opens
        server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
