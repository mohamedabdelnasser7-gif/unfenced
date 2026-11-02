"""Bosta's delivery webhook: the real result of an order reaches its chat.

Run from the repo folder:  python3 -m channels.bosta
It listens on 127.0.0.1:BOSTA_PORT (default 8081) for POST /bosta. Bosta must reach it
through a public tunnel or a host, like the WhatsApp webhook.

- Every request must carry the header X-Bosta-Secret with the value of BOSTA_WEBHOOK_SECRET,
  compared in constant time on the raw request before the body is parsed. Bosta signs
  nothing; it sends one custom header the business sets beside the webhook URL.
- Delivered (state 45) records "delivered" on the chat; a refusal (state 47 with exception
  code 8) records "refused", and so does a send returned to the business (state 46,
  Mohamed's call 14A, 29 Oct). For the Sales agent both are its second signal (sales/plug.json
  second_signal, DECISIONS item 66): shown beside a good chat and read by the delivery cards
  (reflection/facts.py), never deciding it; the order placed does, against a chat that closed
  after quiet with no order. For any other agent whose plug names delivered or refused among
  its late results (engine/plug.py Plug.late: decides with a slow result, or second_signal) the
  result goes to that agent's case, and there it may decide the case. Every result is saved
  through reflection/results.py late(), once a case for its group.
- A returned send most likely reaches the webhook as a delivery of its own: type RTO (the
  return leg), its own _id, state 46, and the send's businessReference. So a 46 is found
  through the same order lookup as the send and is taken once per order, not per delivery:
  when that order already has delivered or refused (from the send's 45 or 47 with code 8, or
  an earlier 46), nothing is saved and the answer is 200 "already recorded", not an error.
  That a 46 after a 47 with code 8 adds no second refused is call 14A, not Bosta's docs.
- A 46 on the send itself (SEND or FXF_SEND) is taken the same way, though Bosta's docs do
  not list 46 for a send: it costs nothing, since the order still gets one refused whichever
  delivery reports the return. A refusal takes its order first, so a 47 with code 8 after any
  46 for its order, on the send or on the return leg, is a replay (409).
- The case is found through the order number: Bosta echoes the businessReference the
  delivery was created with, which must be that order number (#1001, or 1001; both are one
  order). For the Sales agent it is the order its order_created row names (a Shopify order);
  for another agent, any action row of its own whose detail names that order. Only agents whose
  plug takes that result are searched. No case, or more than one across all those agents, is an
  unknown order and is refused (404); nothing is saved. A case that already has a result of that
  group (from the API check or a person on the morning page) saves nothing: 200 "already
  recorded".
- Each delivery gets each result once. A message already taken is refused (409): a replay
  or a retry saves nothing twice. A 46 already taken for its order is the one exception
  above: 200, and still nothing saved. A result whose write fails is forgotten, so Bosta
  can send it again.
- Any other failed attempt (state 47 with another exception code) is a note for the team,
  not a result: one line to OPERATOR_WHATSAPP when the WhatsApp keys are set, else the log.
- Every other state, and every delivery that is not a send to a customer (SEND, or FXF_SEND
  when Bosta Fulfillment ships it; the docs list state 45 for both), is answered 200 and
  ignored; the one exception is a 46 on RTO, above. A 46 on an exchange or a customer return
  pickup is not the order's result and is ignored. A body that cannot be read is 400. A
  wrong or missing secret is 403, checked before any byte of the body is read.
- The server keeps the WhatsApp server's limits: a deadline for the request line and for
  the whole request, a cap on the body and on open connections.

Bosta's webhook, from its own docs (https://docs.bosta.co/docs/how-to/get-delivery-status-via-webhook/,
read 29 Oct 2026): a JSON POST on each state change of a delivery, with the fields _id (the
delivery), trackingNumber, state (a number), type (SEND, EXCHANGE, CUSTOMER_RETURN_PICKUP, RTO,
SIGN_AND_RETURN, FXF_SEND), cod, timeStamp (a number; 13 digits in the examples),
isConfirmedDelivery, deliveryPromiseDate, exceptionReason, exceptionCode, businessReference
("The businessReference value that was sent in the creation request") and numberOfAttempts.
States: 45 Delivered, 46 Returned to business (listed for EXCHANGE, CUSTOMER_RETURN_PICKUP
and RTO only, not SEND), 47 Exception, 48 Terminated, 49 Canceled, 100 Lost, 101 Damaged.
Exception codes 1 to 8, 12 to 14, 100 and 101 are forward attempts; 8 is "Cancellation - the
customer refuses to receive the shipment"; 20 to 30 are the return leg. The header: Settings
> API Integration > Set Up Your Webhook takes the URL and an optional custom header name and
value; a delivery made through the API can carry webhookUrl and webhookCustomHeaders
(https://docs.bosta.co/api/api.yaml).
Not in Bosta's docs: a retry policy, the reply it expects, an id for one event, the
timeStamp unit, the order events arrive in, and the _id of a send's return leg. So a result
is taken once per delivery, a 46 once per order, and every field is read in read_event()
only.
"""
import hmac
import io
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from reflection.results import late
from channels.whatsapp import DeadlineReader, FIRST_LINE_DEADLINE, MAX_OPEN, MIN_SECRET, REQUEST_DEADLINE, \
    SOCKET_TIMEOUT

log = logging.getLogger("channels.bosta")

PATH = "/bosta"
HEADER = "X-Bosta-Secret"
MAX_BODY = 64 * 1024
PORT_DEFAULT = "8081"

DELIVERED, RETURNED, EXCEPTION = 45, 46, 47   # 46: "Returned to business", recorded as refused
FORWARD = ("SEND", "FXF_SEND")      # a delivery to the customer, from the business or from Bosta Fulfillment;
                                    # returns and exchanges are not the order's result
RETURN_LEG = "RTO"                  # a send coming back to the business: its own delivery, the send's
                                    # businessReference; only its 46 counts (refused, once per order)
REFUSED_CODE = 8                    # "the customer refuses to receive the shipment"
ATTEMPT_CODES = frozenset({*range(1, 9), 12, 13, 14, 100, 101})  # forward attempts, 8 included
MAX_TEXT = 200                      # Bosta's own words in a team note, cut here

SEEN = """
CREATE TABLE IF NOT EXISTS bosta_seen (
  key TEXT PRIMARY KEY,
  at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS bosta_orders (
  ref TEXT PRIMARY KEY,
  at REAL NOT NULL
);
"""
# bosta_seen: each message taken, by delivery. bosta_orders: each order that has its delivered
# or refused, by its number without the #, so a 46 adds a result to an order only once.
PUT_SEEN = "INSERT OR IGNORE INTO bosta_seen (key, at) VALUES (?, ?)"
PUT_ORDER = "INSERT OR IGNORE INTO bosta_orders (ref, at) VALUES (?, ?)"

# One line to the team member for a failed attempt, in the same voice as the WhatsApp team lines.
ATTEMPT_LINE = "بوسطة: محاولة توصيل الطلب {order} منجحتش (محاولة رقم {n})."
ATTEMPT_WHY = " السبب عندهم: {why}"


@dataclass
class Event:
    """One Bosta message, as read_event() reads it."""
    delivery: str
    tracking: str
    state: int
    kind: str
    order: str
    code: int = 0
    attempts: int = 0
    stamp: object = None
    why: str = ""


def _number(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _text(v):
    if isinstance(v, bool):
        return ""
    if isinstance(v, int):
        return str(v)
    return v.strip() if isinstance(v, str) else ""


def read_event(payload):
    """Bosta's body as an Event, or None when it lacks the delivery, its state or the order.
    The only place that knows Bosta's field names (see the docs quoted above)."""
    if not isinstance(payload, dict):
        return None
    delivery, state, order = _text(payload.get("_id")), _number(payload.get("state")), _text(
        payload.get("businessReference"))
    if not delivery or state is None or not order or len(order) > 64 or len(delivery) > 64:
        return None
    return Event(delivery=delivery, tracking=_text(payload.get("trackingNumber"))[:64], state=state,
                 kind=_text(payload.get("type")), order=order, code=_number(payload.get("exceptionCode")) or 0,
                 attempts=_number(payload.get("numberOfAttempts")) or 0,
                 stamp=_number(payload.get("timeStamp")), why=" ".join(_text(payload.get("exceptionReason")).split())[:MAX_TEXT])  # one line: it reaches the team


def outcome(ev):
    """delivered, refused, attempt (a note for the team) or None (ignored)."""
    if ev.state == RETURNED:
        return "refused" if ev.kind in FORWARD or ev.kind == RETURN_LEG else None
    if ev.kind not in FORWARD:
        return None
    if ev.state == DELIVERED:
        return "delivered"
    if ev.state == EXCEPTION and ev.code == REFUSED_CODE:
        return "refused"
    if ev.state == EXCEPTION and ev.code in ATTEMPT_CODES:
        return "attempt"
    return None


def order_names(order):
    """The order numbers a businessReference can stand for: as given, and with its # added or taken off."""
    return (order, order[1:]) if order.startswith("#") else (order, "#" + order)


def order_ref(order):
    """The order's number without its #, so #1001 and 1001 are one order."""
    return order[1:] if order.startswith("#") else order


def secret_ok(header, secret):
    """True only when the header is exactly the secret, compared in constant time."""
    if not secret or not isinstance(header, str):
        return False
    return hmac.compare_digest(header.encode("utf-8"), secret.encode("utf-8"))


class Deliveries:
    """Takes one Bosta message: records its result on the chat, tells the team, or ignores it."""

    def __init__(self, results, tell_team=None, plugs=()):
        """plugs: the other agents' plugs (reflection/night.py other_plugs); only those whose
        late results name delivered or refused are searched for an order's case."""
        self.results = results
        self.db = results.db
        self.tell_team = tell_team
        self.plugs = [p for p in plugs if p.agent != results.plug.agent and
                      {"delivered", "refused"} & {r for group in p.late() for r in group}]
        self.db.script(SEEN)

    def case_for_order(self, order, what):
        """(plug, case id) of the one case this order belongs to, among the agents that take
        this result, or None when there is none or more than one."""
        names = order_names(order)
        found = []
        sales = self.results.plug
        if what in {r for group in sales.late() for r in group}:
            chat = self.results.chat_for_order(*names)
            if chat is not None:
                found.append((sales, chat))
        marks = ", ".join("?" for _ in names)
        for plug in self.plugs:
            if what not in {r for group in plug.late() for r in group}:
                continue
            with self.db.tx() as c:
                rows = c.execute(
                    "SELECT DISTINCT case_id FROM trace WHERE agent = ? AND action IS NOT NULL "
                    "AND json_valid(detail) AND json_extract(detail, '$.history') IS NULL "
                    f"AND json_extract(detail, '$.order') IN ({marks})", (plug.agent, *names)).fetchall()
            found += [(plug, r["case_id"]) for r in rows]
            if len(found) > 1:
                break
        return found[0] if len(found) == 1 else None

    def accept(self, payload):
        """(HTTP status, short reply) for one parsed body."""
        ev = read_event(payload)
        if ev is None:
            return 400, "unreadable"
        what = outcome(ev)
        if what is None:
            return 200, "ignored"
        found = None if what == "attempt" else self.case_for_order(ev.order, what)
        if what == "attempt":
            found = self.case_for_order(ev.order, "delivered") or self.case_for_order(ev.order, "refused")
        if found is None:
            log.warning("a Bosta message names an order no single case placed; refused")
            return 404, "unknown order"
        plug, case = found
        key = f"{ev.delivery}:{what}"
        if what == "attempt":
            key += f":{ev.code}:{ev.attempts}:{ev.stamp}"
        returned = ev.state == RETURNED
        taken = self._take(key, None if what == "attempt" else order_ref(ev.order), what == "refused")
        if taken is None:
            return (200, "already recorded") if returned else (409, "already taken")
        if what == "attempt":
            self._note(ev)
            return 200, "noted"
        try:
            row = late(self.db, plug, case, what, detail={"order": ev.order, "bosta": ev.tracking or ev.delivery,
                                                          "state": ev.state, "code": ev.code or None, "at": ev.stamp})
        except Exception:
            self._forget(*taken)
            raise
        if row is None:  # the API check or a person brought this case's result first
            return 200, "already recorded"
        log.info("%s recorded for an order", what)
        return 200, "recorded"

    def _take(self, key, ref, order_first):
        """Takes one message in one transaction. Returns (key, ref) as far as this message wrote
        them, to undo if the result's write fails, or None when it is already taken.
        A refusal (a 46, or a 47 with code 8) takes its order first and gets nothing when the
        order already has delivered or refused, so one order is refused once whichever delivery
        reports it; then its own key. Any other message takes its key, and a result also marks
        its order (ref)."""
        now = time.time()
        with self.db.tx() as c:
            if order_first:
                if c.execute(PUT_ORDER, (ref, now)).rowcount != 1:
                    return None
                return (key if c.execute(PUT_SEEN, (key, now)).rowcount == 1 else None), ref
            if c.execute(PUT_SEEN, (key, now)).rowcount != 1:
                return None
            return key, (ref if ref is not None and c.execute(PUT_ORDER, (ref, now)).rowcount == 1 else None)

    def _forget(self, key, ref):
        """Undoes what _take wrote for a message whose result could not be saved; an order an
        earlier result marked stays marked."""
        with self.db.tx() as c:
            if key is not None:
                c.execute("DELETE FROM bosta_seen WHERE key = ?", (key,))
            if ref is not None:
                c.execute("DELETE FROM bosta_orders WHERE ref = ?", (ref,))

    def _note(self, ev):
        line = ATTEMPT_LINE.format(order=ev.order, n=ev.attempts or "?")
        if ev.why:
            line += ATTEMPT_WHY.format(why=ev.why)
        log.warning("a delivery attempt failed for an order (code %s)", ev.code)
        if self.tell_team is None:
            return
        try:
            self.tell_team(line)
        except Exception:
            log.exception("could not tell the team about a failed delivery attempt")


def make_handler(secret, accept, timeout=SOCKET_TIMEOUT, deadline=REQUEST_DEADLINE, first_line=FIRST_LINE_DEADLINE,
                 max_open=MAX_OPEN):
    """The request handler. accept(payload) -> (status, reply) runs only for a body that came
    with the right secret and parsed as JSON."""
    if not secret or len(secret) < MIN_SECRET:
        raise ValueError("BOSTA_WEBHOOK_SECRET is missing or too short")

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
                self.requestline = self.request_version = self.command = ""
                self.close_connection = True
                log.warning("%d connections open; asked the caller to retry", max_open)
                return self._reply(503, "busy")
            try:
                super().handle()
            finally:
                self.slots.release()

        def parse_request(self):
            self._reader.deadline = self._full_deadline
            return super().parse_request()

        def _reply(self, code, text=""):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urllib.parse.urlsplit(self.path).path != PATH:
                return self._reply(404, "not found")
            if not secret_ok(self.headers.get(HEADER), secret):  # before any byte of the body is read
                self.close_connection = True
                return self._reply(403, "forbidden")
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
                self.close_connection = True
                return self._reply(408, "request timeout")
            try:
                payload = json.loads(raw)
            except ValueError:
                return self._reply(400, "bad json")
            try:
                code, text = accept(payload)
            except Exception:
                log.exception("could not take a Bosta message")
                return self._reply(500, "error")
            return self._reply(code, text)

        def log_message(self, fmt, *args):
            path = urllib.parse.urlsplit(getattr(self, "path", None) or "").path
            log.info("%s %s", getattr(self, "command", None) or "-", path)

    Handler.timeout = timeout
    Handler.slots = threading.BoundedSemaphore(max_open)
    return Handler


# ---- the API status check (reflection/late.py runs it on the night run, DECISIONS item 66)
# From Bosta's API spec (https://docs.bosta.co/api/api.yaml, read 2 Nov 2026): GET
# /api/v2/deliveries/business/{trackingNumber} on app.bosta.co, the API key in the Authorization
# header, answers {success, message, data: {state: {code, value}, type: {code, value}, ...}}.
# The view carries no exceptionCode, so a refusal at the door (47 with code 8) cannot be told from
# another failed attempt there: the API path records only delivered (45 on a send) and returned
# to the business (46 on a send or its return leg), which this repo already counts as refused
# (call 14A). A refusal still comes from the webhook or a person. No rate limit is documented, so
# the night asks at most reflection/late.py MAX_ASKS a run, one at a time. Search by
# businessReference (POST /deliveries/search) lists only a Bearer login in the spec, so the check
# reads by tracking number alone.
API_BASE = "https://app.bosta.co/api/v2/deliveries/business/"
API_KEY = "BOSTA_API_KEY"
MAX_API_BODY = 256 * 1024
API_TIMEOUT = 15                    # seconds for the whole call: each read, and the answer in all
API_CHUNK = 16 * 1024


def api_outcome(tracking, key, *, opener=None, timeout=API_TIMEOUT):
    """(delivered or refused or None, the state code) for one tracking number, from Bosta's API.
    Raises on a failed call, so the caller counts it and moves on, and when the whole answer has not
    come within timeout seconds of the call, so a body sent a byte at a time never holds the night.
    The status line and headers are bounded only per read; a server that drips them is stopped by the
    night's own limit (reflection/scheduler.py LIMIT). The key is sent only to app.bosta.co, with no redirect followed, and never logged."""
    from kit import net
    tracking = _text(tracking)
    if not tracking or len(tracking) > 64 or not tracking.isalnum():
        raise ValueError("not a tracking number")
    if not key:
        raise ValueError(f"{API_KEY} is not set")
    req = urllib.request.Request(API_BASE + urllib.parse.quote(tracking, safe=""),
                                 headers={"Authorization": key, "Accept": "application/json"})
    deadline = time.monotonic() + timeout
    with (opener or net.open_once)(req, timeout) as r:
        raw = _read_by(r, deadline)
    data = json.loads(raw)
    view = data.get("data") if isinstance(data, dict) else None
    view = view if isinstance(view, dict) else {}
    state = view.get("state") if isinstance(view.get("state"), dict) else {}
    kind = view.get("type") if isinstance(view.get("type"), dict) else {}
    code, kind = _number(state.get("code")), _text(kind.get("value")).upper()
    if code == DELIVERED and kind in FORWARD:
        return "delivered", code
    if code == RETURNED and (kind in FORWARD or kind == RETURN_LEG):
        return "refused", code
    return None, code


def team_sender():
    """send(text) to OPERATOR_WHATSAPP through the WhatsApp Cloud API, or None when its keys are not set."""
    from channels import whatsapp as wa
    from kit import env
    names = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "OPERATOR_WHATSAPP")
    if any(not env.get(n) for n in names) or wa.wrong_env():
        return None
    graph = wa.Graph(env.get("WHATSAPP_TOKEN"), env.get("WHATSAPP_PHONE_NUMBER_ID"),
                     env.get("GRAPH_API_VERSION", wa.GRAPH_VERSION_DEFAULT))
    operator = env.get("OPERATOR_WHATSAPP")
    return lambda text: graph.send(operator, text)


def main():
    from kit import env
    from kit.db import Db
    from reflection.results import Results

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    env.load()
    secret = env.get("BOSTA_WEBHOOK_SECRET")
    if len(secret) < MIN_SECRET:
        raise SystemExit(f"BOSTA_WEBHOOK_SECRET in .env must be set, at least {MIN_SECRET} characters.")
    from kit.db import DEFAULT_PATH
    from reflection.night import other_plugs
    from reflection import PLUG
    db = Db()
    tell = team_sender()
    if tell is None:
        log.info("no WhatsApp keys: failed delivery attempts go to this log only")
    app = Deliveries(Results(db), tell_team=tell, plugs=other_plugs(PLUG, db=str(DEFAULT_PATH)))
    port = int(env.get("BOSTA_PORT", PORT_DEFAULT))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(secret, app.accept))
    log.info("listening on 127.0.0.1:%d%s", port, PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        db.close()


if __name__ == "__main__":
    main()


def _read_by(r, deadline):
    """The answer's body, read a chunk at a time (read1 gives what has come, never waiting for a
    full chunk), all of it by deadline (time.monotonic) and at most MAX_API_BODY bytes."""
    read = getattr(r, "read1", None) or r.read
    parts, size = [], 0
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("the answer did not come in time")
        chunk = read(API_CHUNK)
        if not chunk:
            return b"".join(parts)
        size += len(chunk)
        if size > MAX_API_BODY:
            raise ValueError("the answer was too large")
        parts.append(chunk)
