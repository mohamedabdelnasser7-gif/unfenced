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
- Team replies: a text from the exact OPERATOR_WHATSAPP number that quotes a saved
  handoff note (the webhook's context.id) is sent to that note's customer as typed, from
  the business number. No model call, no send check, no limit counted. It is saved in
  the chat as a person's reply. A reply of only رجّع (or رجع, rag3, back) gives the chat
  back to the agent instead. A reply that reaches the customer after a hand back puts the
  chat back with the person. A note older than 48 hours routes nothing. Anything else from
  that number, including a quote of any other message or of an old note, is an ordinary
  customer message, so one phone can test both sides.
- A team reply WhatsApp refuses, at once or later in a "failed" status, goes to the result
  log as relay_failed and the team member gets one line; for error 131047 (the 24 hour
  window closed) that line says a template is needed. Meta's error page says an error can
  come back in the send response, in a status webhook, or both
  (https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes,
  checked 28 Oct 2026), so both are read. Only failed statuses of team replies are queued.
- A turn that crashes in code (App.turn_failed): the customer gets the model down line,
  and the second failure in a row, model errors included, hands the chat to a person. A
  team member whose reply crashed gets one line, as it may or may not have gone out.
- The lessons get the Meta risk judge (reflection/judge.py), not the engine's stub. It fails
  closed: with no key, an error or an odd answer the lesson counts as high and waits for a yes.

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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from channels.base import Channel, Image, Message
from kit import limits as limits_mod
from kit import media
from kit.net import NoRedirects, no_redirect_opener  # noqa: F401 (the tests read NoRedirects here)
from kit.tools.handoff import sent_id

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
REQUIRED_ENV = ("WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
                "BASETEN_API_KEY", "OPERATOR_WHATSAPP")
# OPERATOR_WHATSAPP as WhatsApp gives a sender's number: country code and digits, no + and no
# leading 0. In any other form team replies would read as customer messages (review t261028j finding 7).
OPERATOR_NUMBER = re.compile(r"[1-9][0-9]{7,14}")
SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})")
CHALLENGE = re.compile(r"[0-9A-Za-z_-]{1,128}")
MAX_ERROR_BODY = 64 * 1024
# Meta's error code for a free-form message sent more than 24 hours after the customer's
# last message (Re-engagement message): only a template can go then.
WINDOW_CLOSED = 131047

# Team replies
HAND_BACK = frozenset({"رجّع", "رجع", "rag3", "back"})
ARABIC_MARKS = re.compile("[\u064B-\u0652\u0640]")  # short vowels, shadda, sukun, tatweel
TEAM_LINES = {
    "handed_back": "تمام، الشات رجع للإيجنت.",
    "window_closed": "الرد موصلش لأن عدى أكتر من 24 ساعة من آخر رسالة من العميل، ومحتاج رسالة تمبلت.",
    "not_sent": "الرد موصلش للعميل، ابعته تاني كمان شوية.",
    "text_only": "بيوصل للعميل الكلام المكتوب بس، الصور والفويس مش بيتبعتوا.",
    "unsure": "حصلت مشكلة عندنا في الرد ده، ومش أكيد إنه اتنفذ.",
}


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
    context_id: str = ""      # the id of the message this one replies to (quotes), if any;
                              # for kind "failed", the id of our message that failed
    error_code: int = 0       # kind "failed" only: Meta's error code


def _d(x):
    return x if isinstance(x, dict) else {}


def _l(x):
    return x if isinstance(x, list) else []


FAILED = "failed:"  # prefix for the seen-id of a failed status, so it never meets a message id


def parse(payload, phone_number_id=None):
    """Text, audio and image messages from a webhook payload, and "failed" statuses of
    messages we sent (kind "failed"). Other types and statuses are skipped."""
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
                quoted = _d(m.get("context")).get("id")
                inc.context_id = quoted if isinstance(quoted, str) else ""
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
            for st in _l(value.get("statuses")):
                st = _d(st)
                sid = st.get("id")
                if st.get("status") != "failed" or not (isinstance(sid, str) and sid):
                    continue
                errors = _l(st.get("errors"))
                code = _d(errors[0]).get("code") if errors else 0
                try:
                    ts = int(st.get("timestamp", 0))
                except (TypeError, ValueError):
                    ts = 0
                out.append(Incoming(FAILED + sid, str(st.get("recipient_id", "")), ts, "failed", context_id=sid,
                                    error_code=code if isinstance(code, int) and not isinstance(code, bool) else 0))
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


# team replies

def is_hand_back(text):
    """True when a team reply is only the hand back word, ignoring spaces, case and Arabic marks."""
    if not isinstance(text, str):
        return False
    kept = "".join(ch for ch in text if not ch.isspace() and unicodedata.category(ch) != "Cf")
    return ARABIC_MARKS.sub("", kept).casefold() in {ARABIC_MARKS.sub("", w) for w in HAND_BACK}


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
    limit the customer was already at when the message came in. The worker takes a team
    member's reply to a note, and a failed status of such a reply, before any turn.
    """

    def __init__(self, chats, model, lessons, results, graph, limits=None, maxsize=MAX_QUEUE, operator=None):
        self.chats, self.model, self.lessons, self.results, self.graph = chats, model, lessons, results, graph
        self.limits = limits
        self.q = queue.Queue(maxsize=maxsize)
        if operator is None:
            from kit import env
            operator = env.get("OPERATOR_WHATSAPP")
        self.operator = operator

    def accept(self, items):
        for inc in items:
            if inc.kind == "failed" and self.chats.reply_step(inc.context_id) is None:
                continue  # only a team reply's failure is acted on
            if not self.chats.first_seen(inc.message_id, asdict(inc)):
                continue
            over = None
            if self.limits is not None and inc.kind != "failed":
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
                self.q.put_nowait((None, Incoming(**p)))
                n += 1
            except (TypeError, queue.Full):
                log.warning("could not re-queue a pending message")
        return n

    def work_one(self, item):
        from sales import loop
        over, inc = item
        if inc.kind == "failed":
            return self.reply_failed(inc)
        chat_id = self.team_chat(inc)
        if chat_id is not None:
            return self.team_reply(inc, chat_id)
        if over:
            # Over a limit: nothing is downloaded and no model is called. The text is saved for the team,
            # with a mark for a photo or voice note that was not opened.
            msg = Message(channel="whatsapp", customer_id=inc.customer_id, text=inc.text,
                          message_id=inc.message_id, timestamp=inc.timestamp,
                          rejected_images=1 if inc.kind == "image" else 0, audio_failed=inc.kind == "audio")
        else:
            msg = to_message(inc, self.graph)
        return loop.turn(msg, chats=self.chats, model=self.model, lessons=self.lessons,
                         results=self.results, send=self.graph.send, limits=self.limits, over=over)

    def team_chat(self, inc):
        """The chat a team member is answering, or None when this is not a team reply.

        Only the signed webhook's sender decides: it must be OPERATOR_WHATSAPP exactly, and
        the message must quote a note that went to that same number.
        """
        if not self.operator or inc.customer_id != self.operator or not inc.context_id:
            return None
        return self.chats.note_chat(inc.context_id, inc.customer_id)

    def team_reply(self, inc, chat_id):
        """Send a team member's reply to the note's customer as typed, or hand the chat back.

        No model call, no send check and no limit. The customer is never told about a hand back.
        """
        from sales.loop import TurnResult
        chat = self.chats.get(chat_id)
        stage = chat["stage"]
        if chat["channel"] != "whatsapp":
            log.warning("a team reply quoted a note for a chat on %s; not sent", chat["channel"])
            self.chats.mark_done(inc.message_id)
            return TurnResult(chat_id, "ignored")
        if inc.kind != "text" or not inc.text.strip():
            self.chats.mark_done(inc.message_id)
            self.tell_team("text_only")
            return TurnResult(chat_id, "ignored")
        if is_hand_back(inc.text):
            before = self.chats.hand_back(chat_id, inc.message_id)
            self.results.record(chat_id, "handed_back", stage=before, detail={"note": inc.context_id})
            log.info("chat %s handed back to the agent", chat_id)
            self.tell_team("handed_back")
            return TurnResult(chat_id, "handed_back")
        try:
            resp = self.graph.send(chat["customer_id"], inc.text)
        except Exception as e:
            window = isinstance(e, SendRefused) and e.code == WINDOW_CLOSED
            if isinstance(e, SendRefused):
                log.warning("a team reply was refused: HTTP %s, error %s", e.status, e.code)
            else:
                log.exception("a team reply could not be sent")
            self.chats.mark_done(inc.message_id)
            self.results.record(chat_id, "relay_failed", stage=stage, detail={
                "why": "window_closed" if window else "not_sent", "note": inc.context_id,
                "code": e.code if isinstance(e, SendRefused) else None})
            self.tell_team("window_closed" if window else "not_sent")
            return TurnResult(chat_id, "relay_failed")
        n = self.chats.add_person_reply(chat_id, inc.text, message_id=inc.message_id, sent_id=sent_id(resp))
        if stage != "with_person":
            # A reply after a hand back: the person is talking to the customer again, so the agent
            # waits instead of answering over them (red team t261028j F5).
            self.chats.set_stage(chat_id, "with_person")
        self.results.record(chat_id, "person_replied", step=n, stage=stage, detail={"note": inc.context_id})
        log.info("team reply sent in chat %s", chat_id)
        return TurnResult(chat_id, "person_replied", inc.text)

    def reply_failed(self, inc):
        """A "failed" status for a team reply that WhatsApp first accepted: log it, tell the team member."""
        from sales.loop import TurnResult
        found = self.chats.reply_step(inc.context_id)
        if found is None:
            self.chats.mark_done(inc.message_id)
            return None
        chat_id, step = found
        window = inc.error_code == WINDOW_CLOSED
        log.warning("a team reply in chat %s failed later: error %s", chat_id, inc.error_code)
        self.chats.not_delivered(chat_id, step, inc.error_code, inc.message_id)
        self.results.record(chat_id, "relay_failed", step=step, stage=self.chats.stage(chat_id), detail={
            "why": "window_closed" if window else "not_sent", "code": inc.error_code, "late": True})
        self.tell_team("window_closed" if window else "not_sent")
        return TurnResult(chat_id, "relay_failed")

    def tell_team(self, which):
        """One fixed line to the team member. A failure is logged, never raised."""
        try:
            self.graph.send(self.operator, TEAM_LINES[which])
        except Exception:
            log.exception("could not message the team member")

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
        """After work_one crashed: tell the person waiting, once. Never raises.

        A customer gets loop.failed_turn: the model down line, or a handoff on the second
        failure in a row. If that crashes too and nothing reached the customer, the line goes
        out directly. A team member gets TEAM_LINES["unsure"], and the reply is not tried
        again after a restart. A failed status is only logged.
        """
        from sales import loop
        _, inc = item
        if inc.kind == "failed":
            return
        team = False
        if self.operator and inc.customer_id == self.operator and inc.context_id:
            try:
                team = self.team_chat(inc) is not None
            except Exception:
                log.exception("could not tell if the failed turn was a team reply")
                team = True  # the team member's own number, quoting a message
        if team:
            try:
                self.chats.mark_done(inc.message_id)
            except Exception:
                log.exception("could not mark the team reply done")
            self.tell_team("unsure")
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


def missing_env():
    """Names in REQUIRED_ENV that are not set. The server does not start without them."""
    from kit import env
    return [n for n in REQUIRED_ENV if not env.get(n)]


def wrong_env():
    """Names that are set in a form the server cannot use. The server does not start with them."""
    from kit import env
    operator = env.get("OPERATOR_WHATSAPP")
    return ["OPERATOR_WHATSAPP"] if operator and not OPERATOR_NUMBER.fullmatch(operator) else []


def main():
    from kit import env
    from kit.chats import Chats
    from kit.db import Db
    from kit.limits import Limits
    from kit.model import Model
    from reflection.judge import Judge
    from reflection.lessons import Lessons
    from reflection.results import Results

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env.load()
    missing = missing_env()
    if missing:
        raise SystemExit("Missing in .env: " + ", ".join(missing))
    if wrong_env():
        raise SystemExit("OPERATOR_WHATSAPP in .env must be the team phone as digits, country code first, "
                         "with no + and no leading 0, for example 201000000001.")
    from sales import loop
    loop.warn_size_prices()
    db = Db()
    pnid = env.get("WHATSAPP_PHONE_NUMBER_ID")
    graph = Graph(env.get("WHATSAPP_TOKEN"), pnid, env.get("GRAPH_API_VERSION", GRAPH_VERSION_DEFAULT))
    # The Meta risk judge on Muse Spark Open. It fails closed: with no key, an error or an odd
    # answer it is unsure, and unsure counts as high, so the lesson waits for a person's yes.
    app = App(Chats(db), Model(), Lessons(db, judge=Judge()), Results(db), graph, limits=Limits(db))
    handler = make_handler(env.get("WHATSAPP_APP_SECRET"), env.get("WHATSAPP_VERIFY_TOKEN"), app.accept, pnid)
    port = int(env.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    requeued = app.requeue_pending()
    if requeued:
        log.info("re-queued %d messages saved before the last stop", requeued)
    threading.Thread(target=app.work, daemon=True).start()
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
