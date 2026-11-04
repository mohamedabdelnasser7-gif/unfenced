"""Try Sales, the chat box on the Sales agent's page (reflection/pages.py): the judge talks to the
trained Sales agent itself (sales/loop.py turn), on the demo store with no Shopify keys and no
operator number (arena/match.py demo_store), with the judge's own model key (kit/model.py reads it
from .env), so no real order or message ever goes out.

It keeps its chat in its own database in memory, never the page's: its turns are on the channel
"try", and nothing here writes the page's database, the Arena files, the exam rows or the connection
rows, so a try never counts for the gate, the exam, Reflection or Connect. It reads the agent's kept
lessons and the corrections that passed (arena/rounds.py Pool, as the Arena hands them), and counts
each model call on the day's Calls file (arena/run.py), the same cap as the Arena.

One turn at a time (a second message while one is answered is refused), at most MAX_TEXT characters
a message and MAX_TURNS turns a chat; Start over begins a new chat with a new made-up customer.
"""
import threading

from arena import match as match_mod
from arena import rounds
from arena import run
from channels.base import Message
from kit.chats import Chats
from kit.db import Db

CHANNEL = "try"
MAX_TEXT = 1000
MAX_TURNS = 20
NO_KEY = ("No model key is set, so Try Sales cannot answer. Put META_API_KEY or BASETEN_API_KEY in .env and start "
          "the page again. With no key, python3 -I recorded/play.py shows a recorded Sales chat.")
NO_FOLDER = "Try Sales needs the database folder for its model call count. Start the page with --db."
BUSY = "Sales is still answering the last message."
LONG = f"This chat has {MAX_TURNS} turns. Start over to try again."
NOTE = ("Talks to the trained Sales agent on the demo store with your own model key. No real order or message goes "
        "out, and these chats never count for the gate, the exam or Connect.")


class Refused(Exception):
    pass


class TrySales:
    def __init__(self, model=None):
        """model: the agent's model (a fake in tests); None uses kit.model.Model once a key is set."""
        self.model = model
        self.db = Db(":memory:")
        self.chats = Chats(self.db)
        from reflection.results import Results
        self.results = Results(self.db)
        self.lock = threading.Lock()
        self.busy = False
        self.chat_no = 1
        self.turns = []

    def ready(self):
        if self.model is not None:
            return True
        from kit import model as model_mod
        return model_mod.has_key()

    def customer(self):
        return f"try-{self.chat_no}"

    def thread(self):
        """The turns of the chat so far, each {said, replies, outcome}."""
        with self.lock:
            return [dict(t) for t in self.turns]

    def clear(self, m=None, now=None):
        with self.lock:
            if self.busy:
                raise Refused(BUSY)
            self.chat_no += 1
            self.turns = []
        return "Started over. The next message opens a new chat."

    def say(self, m, text, now=None):
        """One customer message to the Sales agent; its replies join the thread (the model's words)."""
        text = str(text or "").strip()
        if not text:
            raise Refused("Write a message first.")
        if len(text) > MAX_TEXT:
            raise Refused(f"A message is at most {MAX_TEXT} characters.")
        with self.lock:
            if self.busy:
                raise Refused(BUSY)
            if len(self.turns) >= MAX_TURNS:
                raise Refused(LONG)
            self.busy = True
        try:
            return self._turn(m, text)
        finally:
            with self.lock:
                self.busy = False

    def _turn(self, m, text):
        model = self._model(m)
        hand = self._lessons(m)
        from sales import loop
        sent = []
        try:
            with match_mod.demo_store():
                out = loop.turn(Message(channel=CHANNEL, customer_id=self.customer(), text=text), chats=self.chats,
                                model=model, lessons=hand, results=self.results,
                                send=lambda to, reply: sent.append(reply))
        except run.CapReached as e:
            raise Refused(f"Not answered: {e}.") from None
        with self.lock:
            self.turns.append({"said": text, "replies": list(sent), "outcome": out.outcome})
        if sent:
            return "Sales answered."
        return f"Sales sent no reply this time ({out.outcome.replace('_', ' ')})."

    def _model(self, m):
        if m.reports is None:
            raise Refused(NO_FOLDER)
        calls = run.Calls(m.reports / run.CALLS_FILE, run.DEFAULT_CAP)
        if calls.problem:
            raise Refused(f"Not answered: {calls.problem}.")
        if calls.count >= calls.cap:
            raise Refused(f"Not answered: the cap of {calls.cap} model calls for {calls.day} is reached.")
        inner = self.model
        if inner is None:
            if not self.ready():
                raise Refused(NO_KEY)
            from kit.model import Model
            inner = Model()
        return calls.model(inner)

    def _lessons(self, m):
        """What the turn is handed: the agent's kept lessons, and with the live database the corrections
        that passed (or had a person's yes after the exam held them) and run there, and the lessons on
        trial there (rounds.Pool and live_lessons, as the Arena hands them, decision 112). Read only."""
        from reflection import PLUG
        from reflection.exam import _Lessons
        lessons = m.lessons.get(PLUG.agent)
        if lessons is None:
            return _Lessons(None, None)
        path = getattr(m, "db_path", None)
        pool = rounds.Pool(lessons, hotfixes=(lambda: rounds.live_lessons(path, PLUG.agent)) if path else None)
        pool.refresh()
        return _Lessons(pool, None)
