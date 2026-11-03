"""WhatsApp Cloud API channel: the webhook server and the Graph API client.

Run from the repo folder:  python3 -m channels.whatsapp
It listens on 127.0.0.1:PORT (default 8080). Meta must reach it through a public tunnel.

- GET  /webhook  the verify-token handshake.
- POST /webhook  the X-Hub-Signature-256 check runs on the raw bytes before anything
  parses the body (HMAC SHA-256 with the app secret, constant-time compare). Then text,
  voice notes and photos are parsed, deduped by message id (Meta retries), and queued.
  One worker thread answers them in order, so the webhook returns 200 at once.
- A customer over a model call limit (kit/limits.py) is not queued for a turn; the
  worker only saves the message (a photo or voice note as a mark, not downloaded) and
  sends the fixed line, once per window.
- The queue holds at most MAX_QUEUE messages. When it is full the webhook answers 503
  and forgets the id, so Meta's retry is taken later.
- Each socket read waits at most SOCKET_TIMEOUT seconds, the request line must arrive
  within FIRST_LINE_DEADLINE seconds of the connection, and the whole request within
  REQUEST_DEADLINE seconds. A slow or stalled body gets 408; a slow request line or slow
  headers end the connection with no reply.
- At most MAX_OPEN connections are served at once. One more gets 503 at once and is
  closed, so idle connections cannot hold a thread each without end. Meta retries.
- Media: only from Meta's media host over https, with no redirects, so the token is
  never sent anywhere else.
- Live only when connected (DECISIONS item 77, kit/connections.py): the channel answers only while
  the user has the Sales agent connected on WhatsApp from its page, after its Arena gate passed. When it
  is not, a message is marked done and not saved, nothing is sent, the quiet tick sends no notice and
  closes no chat, and the log says so in one line. A notice that fell due before the latest Connect is
  never sent. WHATSAPP_LIVE=off keeps it silent for a demo; on stands in for a missing row only, so
  it answers unless the latest row is a Pull, whenever that Pull was made (Pull always works);
  unset, it follows Connect and Pull. The webhook's signature check runs the same either way.
- No hand-off to a person (DECISIONS item 53): every message is a customer message and the
  agent answers it. A reply is a plain text message: it never quotes the customer's message
  (no context, no reply-to). Statuses are not read.
- A turn that crashes in code (App.turn_failed): the customer gets the model down line,
  and the second failure in a row, model errors included, is no safe reply (sales/loop.py).
- The lessons get the Meta risk judge (reflection/judge.py), not the engine's stub. It fails
  closed: with no key, an error or an odd answer the lesson counts as high and waits for a yes.
- A chat ends after quiet (DECISIONS item 54, sales/quiet.py): a second thread ticks every
  FAST_EVERY seconds, with no model call. After 30 quiet minutes the customer gets one notice
  that the chat closes in 30 minutes, through Graph.send like any reply; after 30 more the chat
  closes, and the next message starts a new chat. A paused agent (kit/switch.py) sends nothing.
  A chat whose customer has a message here not saved yet is left alone, and a notice already due
  when the process started is never sent: that chat closes silently. A notice that falls due
  while the process runs always goes out, however late the tick (App.started).
- Fast reflection (reflection/fast.py): the same thread then sweeps for chats that ended without
  an order and writes each one note for that customer's next chat only; the turn reads it into
  the prompt. A tick or sweep that fails is logged and the next one tries again.
- Chat memory (sales/memory.py): each turn hands the case's memory to the Sales turn, which keeps
  what falls out of the 40 message window, and a returning customer's earlier talks, as one note
  under the case. When it cannot start, turns see the last 40 messages as before.
- Night studies (reflection/scheduler.py): one more thread runs each agent's night once a night,
  at NIGHT_HOUR (default 3) in NIGHT_TZ (default Africa/Cairo), each night in a child process of
  its own so it never changes this server's env, logging or store. NIGHT_HOUR=off turns it off. It
  is never needed to answer: when it cannot start, the server runs as before.

Graph API version: GRAPH_API_VERSION, default v26.0, the latest in Meta's changelog
(https://developers.facebook.com/docs/graph-api/changelog, checked 28 Oct 2026; v26.0
released 29 Jul 2026). Message and media paths from the WhatsApp Cloud API reference:
POST /{version}/{phone_number_id}/messages and GET /{version}/{media_id}?phone_number_id=...
"""
import hashlib
import hmac
import io
import json
import logging
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from channels.base import Channel, Image, Message
from kit import connections
from kit import limits as limits_mod
from kit import media
from kit.net import NoRedirects, no_redirect_opener  # noqa: F401 (the tests read NoRedirects here)

log = logging.getLogger("channels.whatsapp")

GRAPH = "https://graph.facebook.com"
GRAPH_VERSION_DEFAULT = "v26.0"
MAX_BODY = 1024 * 1024
MAX_AUDIO_BYTES = 16 * 1024 * 1024
AUDIO_TYPES = ("audio/ogg",)            # WhatsApp voice notes: audio/ogg; codecs=opus
MEDIA_HOSTS = ("lookaside.fbsbx.com",)  # where Graph's media urls point (checked 28 Oct 2026)
MIN_SECRET = 32
SOCKET_TIMEOUT = 10
REQUEST_DEADLINE = 15
FIRST_LINE_DEADLINE = 5
MAX_OPEN = 32
MAX_QUEUE = 200
REQUIRED_ENV = ("WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")
# The model key is either one (kit/model.py keyed_legs): META_API_KEY alone runs every call.
MODEL_KEYS = "META_API_KEY or BASETEN_API_KEY"
SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})")
CHALLENGE = re.compile(r"[0-9A-Za-z_-]{1,128}")
MAX_ERROR_BODY = 64 * 1024
TYPING_TIMEOUT = 3  # seconds at most for the typing dots: a slow Graph never holds the worker long
FAST_EVERY = 30  # seconds between quiet ticks and fast reflection sweeps, so a note is written within seconds of a chat ending
OLD_FIELDS = ("context_id", "error_code")  # Incoming fields before DECISIONS item 53
AGENT = "sales"  # the one agent this channel runs (kit/connections.py WORKS)
LIVE_SETTING = connections.SETTINGS[connections.WHATSAPP]  # unset: follow Connect and Pull; on or off, the demo
NOT_LIVE_LOG = "the Sales agent is not live on WhatsApp: a message came in and nothing was sent"


# signature

def sign(raw, secret):
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def verify_signature(raw, header, secret):
    """True only if header is "sha256=<hex>" of HMAC SHA-256 over the raw body with the app secret."""
    if not secret or not isinstance(header, str):
        return False
    m = SIGNATURE.fullmatch(header)
    if not m:
        return False
    want = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want.encode("ascii"), m.group(1).encode("ascii"))


# parsing

@dataclass
class Incoming:
    """One WhatsApp message as parsed from the webhook, before any media is downloaded."""
    message_id: str
    customer_id: str
    timestamp: int
    kind: str                 # text, audio or image
    text: str = ""
    media_id: str = ""
    media_mime: str = ""


def _d(x):
    return x if isinstance(x, dict) else {}


def _l(x):
    return x if isinstance(x, list) else []


def parse(payload, phone_number_id=None):
    """Text, audio and image messages from a webhook payload. Other types and statuses are skipped."""
    out = []
    for entry in _l(_d(payload).get("entry")):
        for change in _l(_d(entry).get("changes")):
            value = _d(_d(change).get("value"))
            pnid = str(_d(value.get("metadata")).get("phone_number_id", ""))
            if phone_number_id and pnid != str(phone_number_id):
                continue
            for m in _l(value.get("messages")):
                m = _d(m)
                kind, mid, sender = m.get("type"), m.get("id"), m.get("from")
                if not (isinstance(mid, str) and mid and isinstance(sender, str) and sender):
                    continue
                try:
                    ts = int(m.get("timestamp", 0))
                except (TypeError, ValueError):
                    ts = 0
                inc = Incoming(mid, sender, ts, str(kind))
                if kind == "text":
                    inc.text = str(_d(m.get("text")).get("body", ""))
                elif kind in ("audio", "image"):
                    part = _d(m.get(kind))
                    inc.media_id = str(part.get("id", ""))
                    inc.media_mime = str(part.get("mime_type", ""))
                    inc.text = str(part.get("caption", "")) if kind == "image" else ""
                else:
                    continue
                out.append(inc)
    return out


# Graph API

class TooBig(Exception):
    pass


class SendRefused(Exception):
    """WhatsApp answered a send with an HTTP error. code: Meta's error code, 0 if the body had none."""

    def __init__(self, status, code):
        super().__init__(f"WhatsApp refused the send: HTTP {status}, error {code}")
        self.status, self.code = status, code


def error_code(body):
    """Meta's error code from an error body ({"error": {"code": 131047, ...}}), or 0."""
    try:
        err = json.loads(body.decode("utf-8")).get("error")
        code = err.get("code") if isinstance(err, dict) else 0
        return code if isinstance(code, int) and not isinstance(code, bool) else 0
    except (AttributeError, UnicodeDecodeError, ValueError):
        return 0


class Busy(Exception):
    """The queue is full; the webhook answers 503 so Meta retries later."""


def media_url_ok(url):
    """True only for an https url on Meta's media host, default port, no user info."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname in MEDIA_HOSTS and port in (None, 443)
            and parts.username is None and parts.password is None)


class Graph(Channel):
    """Sends replies and downloads media through the Graph API."""

    name = "whatsapp"

    def __init__(self, token, phone_number_id, version=GRAPH_VERSION_DEFAULT, opener=None, timeout=20):
        self._token = token
        self.phone_number_id = phone_number_id
        self.version = version
        self._open = opener or no_redirect_opener().open
        self.timeout = timeout

    def _req(self, url, data=None):
        headers = {"Authorization": "Bearer " + self._token}
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode("utf-8")
        return urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")

    def send(self, to, text):
        url = f"{GRAPH}/{self.version}/{self.phone_number_id}/messages"
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
                "type": "text", "text": {"preview_url": False, "body": text}}
        try:
            with self._open(self._req(url, body), timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            with e:
                try:
                    code = error_code(e.read(MAX_ERROR_BODY))
                except Exception:
                    code = 0
            raise SendRefused(e.code, code) from None

    def typing(self, message_id):
        """Marks the customer's message read and shows the typing dots until the reply is sent or
        25 seconds pass (Meta's typing indicator). Only for a message we answer. Never raises: the
        dots are a courtesy, so a refusal is logged and the reply goes out as usual. Waits at most
        TYPING_TIMEOUT seconds."""
        if not isinstance(message_id, str) or not re.fullmatch(r"wamid\.[0-9A-Za-z_=+/-]{1,256}", message_id):
            return False
        url = f"{GRAPH}/{self.version}/{self.phone_number_id}/messages"
        body = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id,
                "typing_indicator": {"type": "text"}}
        try:
            with self._open(self._req(url, body), timeout=min(self.timeout, TYPING_TIMEOUT)) as r:
                r.read(MAX_ERROR_BODY)
            return True
        except Exception as e:
            if isinstance(e, urllib.error.HTTPError):
                e.close()  # the refusal's body is not read; its connection is let go, as send does
            log.warning("the typing dots were refused: %s", type(e).__name__)
            return False

    def download(self, media_id, max_bytes):
        """(bytes, mime) for a media id. Raises TooBig past max_bytes without reading the rest."""
        if not re.fullmatch(r"[0-9A-Za-z_-]{1,128}", media_id or ""):
            raise ValueError("bad media id")
        q = urllib.parse.urlencode({"phone_number_id": self.phone_number_id})
        with self._open(self._req(f"{GRAPH}/{self.version}/{media_id}?{q}"), timeout=self.timeout) as r:
            info = json.loads(r.read().decode("utf-8"))
        if int(info.get("file_size") or 0) > max_bytes:
            raise TooBig(media_id)
        url = str(info.get("url", ""))
        if urllib.parse.urlsplit(url).scheme != "https":
            raise ValueError("media url is not https")
        if not media_url_ok(url):
            raise ValueError("media url is not on Meta's media host")
        with self._open(self._req(url), timeout=self.timeout) as r:
            data = r.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise TooBig(media_id)
        return data, str(info.get("mime_type", ""))


def to_message(inc, graph):
    """Download what the message carries and build the channel-neutral Message."""
    msg = Message(channel="whatsapp", customer_id=inc.customer_id, text=inc.text,
                  message_id=inc.message_id, timestamp=inc.timestamp)
    if inc.kind == "audio":
        declared = inc.media_mime.split(";")[0].strip().lower()
        if declared not in AUDIO_TYPES:
            msg.audio_failed = True
            return msg
        try:
            audio, mime = graph.download(inc.media_id, MAX_AUDIO_BYTES)
        except Exception:
            log.exception("voice note download failed")
            msg.audio_failed = True
            return msg
        mime = mime or inc.media_mime
        if mime.split(";")[0].strip().lower() not in AUDIO_TYPES or not audio:
            msg.audio_failed = True
            return msg
        msg.audio, msg.audio_mime = audio, mime
    elif inc.kind == "image":
        declared = inc.media_mime.split(";")[0].strip().lower()
        if declared not in media.IMAGE_TYPES:
            msg.rejected_images += 1
            return msg
        try:
            data, mime = graph.download(inc.media_id, media.MAX_IMAGE_BYTES)
        except TooBig:
            msg.rejected_images += 1
            return msg
        except Exception:
            log.exception("photo download failed")
            msg.rejected_images += 1
            return msg
        mime = (mime or declared).split(";")[0].strip().lower()
        ok, _ = media.check_image(data, mime)
        if ok:
            msg.images.append(Image(data, mime))
        else:
            msg.rejected_images += 1
    return msg


# server

class DeadlineReader(io.RawIOBase):
    """Reads one request from the socket. Each read waits at most per_read seconds, and
    every read must end by a deadline, so a client that sends a byte at a time cannot keep
    the connection open. The handler moves deadline from the request line's to the full one."""

    def __init__(self, conn, deadline, per_read=None):
        self._conn, self.deadline, self._per_read = conn, deadline, per_read

    def readable(self):
        return True

    def readinto(self, buf):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("request deadline passed")
        self._conn.settimeout(min(left, self._per_read) if self._per_read else left)
        try:
            return self._conn.recv_into(buf)
        finally:
            self._conn.settimeout(self._per_read)  # writes keep the normal timeout


def make_handler(app_secret, verify_token, accept, phone_number_id=None, timeout=SOCKET_TIMEOUT,
                 deadline=REQUEST_DEADLINE, first_line=FIRST_LINE_DEADLINE, max_open=MAX_OPEN):
    """The request handler. accept(list of Incoming) runs only for signed, parsed bodies.

    timeout: seconds per socket read. first_line: seconds for the request line to arrive.
    deadline: seconds for the whole request to arrive. max_open: connections served at once.
    """
    if not app_secret or len(app_secret) < MIN_SECRET:
        raise ValueError("WHATSAPP_APP_SECRET is missing or too short")
    if not verify_token:
        raise ValueError("WHATSAPP_VERIFY_TOKEN is missing")

    class Handler(BaseHTTPRequestHandler):
        server_version = "ascent"
        sys_version = ""

        def setup(self):
            super().setup()
            self.rfile.close()  # the plain socket reader, replaced by one with a deadline
            start = time.monotonic()
            self._full_deadline = start + deadline
            self._reader = DeadlineReader(self.connection, start + min(first_line, deadline), timeout)
            self.rfile = io.BufferedReader(self._reader)

        def handle(self):
            if not self.slots.acquire(blocking=False):
                # Nothing is read yet, so the log and the reply have no request line to show.
                self.requestline = self.request_version = self.command = ""
                self.close_connection = True
                log.warning("%d connections open; asked the caller to retry", max_open)
                return self._reply(503, "busy")
            try:
                super().handle()
            finally:
                self.slots.release()

        def parse_request(self):
            # The request line is in: the headers and the body get the rest of the full deadline.
            self._reader.deadline = self._full_deadline
            return super().parse_request()

        def _reply(self, code, text=""):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            mode = q.get("hub.mode", [""])[0]
            token = q.get("hub.verify_token", [""])[0]
            challenge = q.get("hub.challenge", [""])[0]
            if (mode == "subscribe" and CHALLENGE.fullmatch(challenge)
                    and hmac.compare_digest(token.encode("utf-8"), verify_token.encode("utf-8"))):
                return self._reply(200, challenge)
            return self._reply(403, "forbidden")

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._reply(411, "length required")
            if length < 0 or length > MAX_BODY:
                self.close_connection = True
                return self._reply(413, "too large")
            try:
                raw = self.rfile.read(length)
            except TimeoutError:
                log.warning("request body did not arrive in time; dropped")
                self.close_connection = True
                return self._reply(408, "request timeout")
            if not verify_signature(raw, self.headers.get("X-Hub-Signature-256"), app_secret):
                return self._reply(403, "bad signature")
            try:
                payload = json.loads(raw)
            except ValueError:
                return self._reply(400, "bad json")
            try:
                accept(parse(payload, phone_number_id))
            except Busy:
                log.warning("queue full; asked Meta to retry")
                return self._reply(503, "busy")
            except Exception:
                log.exception("could not queue messages")
                return self._reply(500, "error")
            return self._reply(200, "ok")

        def log_message(self, fmt, *args):
            # The default log prints the full request line, and the GET query holds the verify token.
            # A request cut off before its first line has no command or path yet.
            path = urllib.parse.urlsplit(getattr(self, "path", None) or "").path
            log.info("%s %s", getattr(self, "command", None) or "-", path)

    Handler.timeout = timeout  # seconds per socket read; a stalled body ends the connection
    Handler.slots = threading.BoundedSemaphore(max_open)
    return Handler


class App:
    """Dedupes and queues incoming messages, and answers them one at a time.

    Queue items are (over, Incoming): over is None for a normal turn, or the model call
    limit the customer was already at when the message came in.
    """

    def __init__(self, chats, model, lessons, results, graph, limits=None, maxsize=MAX_QUEUE, fast=None, clock=None,
                 connected=None, memory=None):
        """connected: None follows the user's Connect and Pull on the agent page (kit/connections.py,
        read from the chats' database before every turn and tick); False keeps it silent and True
        answers unless the latest row is a Pull, for tests and the demo (main reads WHATSAPP_LIVE)."""
        self.chats, self.model, self.lessons, self.results, self.graph = chats, model, lessons, results, graph
        self.connected = connected
        self.limits = limits
        self.clock = clock or getattr(chats, "clock", time.time)  # the quiet tick's clock; tests set it
        self.started = self.clock()  # a quiet notice already due by now is never sent (sales/quiet.py)
        self.fast = fast  # fast reflection's notes (reflection.fast.FastNotes), or None for none
        self.memory = memory  # the Sales chat memory (sales.memory.Memory), or None: the last 40 messages only
        self.q = queue.Queue(maxsize=maxsize)

    def accept(self, items):
        for inc in items:
            if not self.chats.first_seen(inc.message_id, asdict(inc)):
                continue
            over = None
            if self.limits is not None:
                over = self.limits.over(limits_mod.key("whatsapp", inc.customer_id))
            try:
                self.q.put_nowait((over, inc))
            except queue.Full:
                self.chats.forget(inc.message_id)
                raise Busy() from None

    def requeue_pending(self):
        """At start: queue the messages a stopped process had accepted but never saved."""
        room = self.q.maxsize - self.q.qsize() if self.q.maxsize > 0 else MAX_QUEUE
        n = 0
        for p in self.chats.pending(limit=max(room, 0)):
            try:
                # a message saved before item 53 may carry context_id or error_code; they are not read
                self.q.put_nowait((None, Incoming(**{k: v for k, v in p.items() if k not in OLD_FIELDS})))
                n += 1
            except (TypeError, queue.Full):
                log.warning("could not re-queue a pending message")
        return n

    def live(self):
        """Is the Sales agent live on WhatsApp now? Off when fixed off; fixed on, live unless its latest
        row (by row, never by clock) is a Pull, so Pull always works, a Pull made before this process
        started too; else its latest Connect or Pull. A state that cannot be read counts as not live,
        so nothing goes out."""
        if self.connected is False:
            return False
        try:
            if self.connected:
                got = connections.state(self.chats.db, AGENT).get(connections.WHATSAPP)
                return got is None or got["on"]
            return connections.live(self.chats.db, AGENT, connections.WHATSAPP)
        except Exception:
            log.exception("the live state could not be read; answering nothing")
            return False

    def work_one(self, item):
        from sales import loop
        over, inc = item
        if inc.kind == "failed":  # a status queued before item 53: statuses are not read
            self.chats.mark_done(inc.message_id)
            return None
        if not self.live():  # not connected: nothing goes out, and the message is not answered later
            self.chats.mark_done(inc.message_id)
            log.info(NOT_LIVE_LOG)
            return None
        if over:
            # Over a limit: nothing is downloaded and no model is called. The text is saved,
            # with a mark for a photo or voice note that was not opened.
            msg = Message(channel="whatsapp", customer_id=inc.customer_id, text=inc.text,
                          message_id=inc.message_id, timestamp=inc.timestamp,
                          rejected_images=1 if inc.kind == "image" else 0, audio_failed=inc.kind == "audio")
        else:
            msg = to_message(inc, self.graph)
        dots = getattr(self.graph, "typing", None)  # a test channel may have no dots
        typing = (lambda: dots(inc.message_id)) if dots else None  # the turn calls it once, only when it will answer
        return loop.turn(msg, chats=self.chats, model=self.model, lessons=self.lessons, results=self.results,
                         send=self.graph.send, limits=self.limits, over=over, fast=self.fast, typing=typing,
                         memory=self.memory)

    def sweep_fast(self, stop=None, every=FAST_EVERY):
        """The quiet tick, then fast reflection's sweep, every `every` seconds until stop (a
        threading.Event) is set. The tick goes first, so a chat it closes gets its note in the same pass."""
        stop = stop if stop is not None else threading.Event()
        while not stop.wait(every):
            self.quiet_once()
            self.sweep_once()

    def quiet_once(self):
        """One quiet tick (sales/quiet.py): the notice and the close, no model call. Returns what
        it did; never raises."""
        from sales import quiet
        if not self.live():  # not connected: no notice and no close until it is
            return []
        try:
            return quiet.tick(chats=self.chats, results=self.results, send=self.graph.send, channel="whatsapp",
                              now=self.clock(), limits=self.limits, started=self._since())
        except Exception:
            log.exception("the quiet tick failed")
            return []

    def _since(self):
        """The quiet tick's start: the later of this process's start and the latest row when it is a
        Connect, so a notice that fell due while the agent was not live is never sent; that chat closes
        silently. The same with WHATSAPP_LIVE=on, so a Pull then a Connect sends no overdue notice; the
        process start alone only when there is no row."""
        try:
            got = connections.state(self.chats.db, AGENT).get(connections.WHATSAPP)
        except Exception:
            got = None
        at = got["at"] if got and got["on"] else None
        return self.started if at is None else max(self.started, at)

    def sweep_once(self):
        """One fast reflection sweep. Returns what it wrote; never raises."""
        if self.fast is None:
            return []
        try:
            return self.fast.sweep()
        except Exception:
            log.exception("the fast reflection sweep failed")
            return []

    def work(self):
        while True:
            item = self.q.get()
            if item is None:
                return
            try:
                self.work_one(item)
            except Exception:
                log.exception("turn failed")
                self.turn_failed(item)

    def turn_failed(self, item):
        """After work_one crashed: tell the customer, once. Never raises.

        The customer gets loop.failed_turn: the model down line, or no safe reply on the second
        failure in a row. If that crashes too and nothing reached the customer, the line goes
        out directly.
        """
        from sales import loop
        _, inc = item
        if inc.kind == "failed" or not self.live():
            return
        reached = []

        def send(to, text):
            resp = self.graph.send(to, text)
            if to == inc.customer_id:
                reached.append(text)
            return resp

        msg = Message(channel="whatsapp", customer_id=inc.customer_id, text=inc.text,
                      message_id=inc.message_id, timestamp=inc.timestamp)
        try:
            loop.failed_turn(msg, chats=self.chats, model=self.model, results=self.results, send=send,
                             limits=self.limits, kind=inc.kind)
        except Exception:
            log.exception("the failed turn could not be handled")
            if reached:
                return
            try:
                self.graph.send(inc.customer_id, loop.model_down_line(inc.text))
                log.warning("sent the model down line directly")
            except Exception:
                log.exception("could not send the model down line")


def live_setting(value):
    """WHATSAPP_LIVE as App's connected: unset or empty follows Connect and Pull on the agent page (None);
    "on" is True and "off" is False. Anything else stops the server, so a typo never answers by itself."""
    value = (value or "").strip().lower()
    if not value:
        return None
    if value not in ("on", "off"):
        raise SystemExit(f"{LIVE_SETTING} is on or off, or unset to follow Connect and Pull on the agent page")
    return value == "on"


def missing_env():
    """Names in REQUIRED_ENV that are not set, and MODEL_KEYS when neither model key is. The
    server does not start without them."""
    from kit import env
    from kit import model
    missing = [n for n in REQUIRED_ENV if not env.get(n)]
    return missing if model.has_key() else missing + [MODEL_KEYS]


def start_nights(db, db_path):
    """Each agent's night study once a night (reflection/scheduler.py), as one more thread. It is
    never needed to answer: NIGHT_HOUR=off, or a scheduler that cannot start, leaves the service
    running as before, and the log says why. The thread, or None."""
    try:
        from reflection import scheduler
        return scheduler.start(db, db_path)
    except Exception:
        log.exception("the night scheduler is off: it could not start")
        return None


def main():
    from kit import env
    from kit.chats import Chats
    from kit.db import DEFAULT_PATH, Db
    from kit.limits import Limits
    from kit.model import Model
    from reflection.fast import FastNotes
    from reflection.judge import Judge
    from reflection.lessons import Lessons
    from reflection.results import Results

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env.load()
    missing = missing_env()
    if missing:
        raise SystemExit("Missing in .env: " + ", ".join(missing))
    from sales import loop
    loop.warn_size_prices()
    db = Db()
    pnid = env.get("WHATSAPP_PHONE_NUMBER_ID")
    graph = Graph(env.get("WHATSAPP_TOKEN"), pnid, env.get("GRAPH_API_VERSION", GRAPH_VERSION_DEFAULT))
    # The Meta risk judge on Muse Spark Open. It fails closed: with no key, an error or an odd
    # answer it is unsure, and unsure counts as high, so the lesson waits for a person's yes.
    chats = Chats(db)
    limits = Limits(db)
    try:  # fast reflection is never needed to answer: if it cannot start, the agent runs without it
        fast = FastNotes(db, chats, limits=limits)  # its writer calls count in the same limits
    except Exception:
        log.exception("fast reflection is off: its notes could not be set up")
        fast = None
    try:  # the chat memory is never needed to answer: if it cannot start, turns see the last 40 messages
        from sales.memory import Memory
        memory = Memory(db, chats)
    except Exception:
        log.exception("chat memory is off: it could not be set up")
        memory = None
    app = App(chats, Model(), Lessons(db, judge=Judge()), Results(db), graph, limits=limits, fast=fast,
              connected=live_setting(env.get(LIVE_SETTING)), memory=memory)
    handler = make_handler(env.get("WHATSAPP_APP_SECRET"), env.get("WHATSAPP_VERIFY_TOKEN"), app.accept, pnid)
    port = int(env.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    requeued = app.requeue_pending()
    if requeued:
        log.info("re-queued %d messages saved before the last stop", requeued)
    threading.Thread(target=app.work, daemon=True).start()
    threading.Thread(target=app.sweep_fast, daemon=True).start()
    start_nights(db, DEFAULT_PATH)
    log.info("listening on 127.0.0.1:%d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.q.put(None)
        server.server_close()


if __name__ == "__main__":
    main()
