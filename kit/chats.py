"""Saved chats: every step of every chat, so a chat can resume and be replayed.

Steps are numbered from 1 inside each chat. Besides the messages the model sees
(user, assistant, tool), a chat holds "event" steps: stage changes, failed send
checks and model errors. That way branch() can rebuild the stage and both counts
at any step.

Media bytes are never stored, only a sha256 and the mime type.

Webhook message ids: an id is saved as pending, with the parsed message, when it is
queued, and marked done in the same transaction that saves the customer's step; the
parsed message is dropped then, since the step holds it. A restart re-queues pending
messages (at most MAX_ATTEMPTS times each), so nothing that Meta already got a 200 for
is lost.

Team notes: when a chat is handed to a person, each part of the note sent to the team
member is saved by its channel message id, with the chat it belongs to and the number it
went to. A reply that quotes one of those ids reaches that chat and no other, for
NOTE_SECONDS (48 hours) after the note went out (red team t261028j F5). What the
person writes back is saved as an assistant step whose name is PERSON, so the reflection
can tell a person's reply from the agent's, and the id WhatsApp gave that message is
kept with its step, so a late "failed" status can be matched to it. A fixed line the agent
sends (model down, limit, handoff) is saved with the name FIXED, so it never counts as a
reply the model wrote (an order summary).
"""
import json
import time
import uuid

from kit.db import Db

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'asking',
  failed_checks INTEGER NOT NULL DEFAULT 0,
  parent_id TEXT,
  branched_at INTEGER,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  model_errors INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chats_customer ON chats (channel, customer_id, parent_id);
CREATE TABLE IF NOT EXISTS steps (
  chat_id TEXT NOT NULL REFERENCES chats (id),
  n INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'event')),
  content TEXT,
  tool_calls TEXT,
  tool_call_id TEXT,
  name TEXT,
  media TEXT,
  at REAL NOT NULL,
  PRIMARY KEY (chat_id, n)
);
CREATE TABLE IF NOT EXISTS seen_messages (
  message_id TEXT PRIMARY KEY,
  at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  payload TEXT,
  attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS team_notes (
  message_id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats (id),
  sent_to TEXT NOT NULL,
  at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS team_replies (
  message_id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats (id),
  step INTEGER NOT NULL,
  at REAL NOT NULL
);
"""
# Columns added after the first live tests, for databases made before them.
CHAT_COLUMNS = (
    ("model_errors", "INTEGER NOT NULL DEFAULT 0"),
)
SEEN_COLUMNS = (
    ("status", "TEXT NOT NULL DEFAULT 'done'"),
    ("payload", "TEXT"),
    ("attempts", "INTEGER NOT NULL DEFAULT 0"),
)

FIRST_STAGE = "asking"
MAX_ATTEMPTS = 3
NOTE_SECONDS = 48 * 3600   # a team note older than this no longer routes a reply
PERSON = "person"   # the name on an assistant step a team member wrote
FIXED = "fixed"     # the name on a fixed line the agent sent (model down, limit, handoff, photo or voice line)


class Chats:
    def __init__(self, db=None):
        self.db = db if db is not None else Db()
        self.db.script(SCHEMA)
        with self.db.tx() as c:
            for table, columns in (("chats", CHAT_COLUMNS), ("seen_messages", SEEN_COLUMNS)):
                have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
                for name, decl in columns:
                    if name not in have:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # chats

    def open(self, channel, customer_id):
        """The customer's current chat on this channel, or a new one. Branches are never reopened."""
        with self.db.tx() as c:
            row = c.execute(
                "SELECT id FROM chats WHERE channel = ? AND customer_id = ? AND parent_id IS NULL "
                "ORDER BY created_at DESC LIMIT 1", (channel, customer_id)).fetchone()
            if row:
                return row["id"]
            return self._new(c, channel, customer_id)

    def _new(self, c, channel, customer_id, stage=FIRST_STAGE, failed=0, parent=None, at_step=None,
             model_errors=0):
        chat_id = uuid.uuid4().hex
        now = time.time()
        c.execute("INSERT INTO chats (id, channel, customer_id, stage, failed_checks, model_errors, parent_id, "
                  "branched_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (chat_id, channel, customer_id, stage, failed, model_errors, parent, at_step, now, now))
        return chat_id

    def get(self, chat_id):
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if row is None:
            raise KeyError(chat_id)
        return dict(row)

    def stage(self, chat_id):
        return self.get(chat_id)["stage"]

    def set_stage(self, chat_id, stage):
        """Move the chat and record the move as an event step. No-op if already there."""
        if self.stage(chat_id) == stage:
            return
        with self.db.tx() as c:
            c.execute("UPDATE chats SET stage = ?, updated_at = ? WHERE id = ?", (stage, time.time(), chat_id))
            self._add(c, chat_id, "event", content=json.dumps({"stage": stage}))

    def failed_checks(self, chat_id):
        return self.get(chat_id)["failed_checks"]

    def add_failed_check(self, chat_id, feedback):
        """Count one failed send check in this chat. Returns the new count."""
        with self.db.tx() as c:
            c.execute("UPDATE chats SET failed_checks = failed_checks + 1, updated_at = ? WHERE id = ?",
                      (time.time(), chat_id))
            self._add(c, chat_id, "event", content=json.dumps({"check_failed": feedback}, ensure_ascii=False))
            return c.execute("SELECT failed_checks FROM chats WHERE id = ?", (chat_id,)).fetchone()[0]

    def reset_failed_checks(self, chat_id):
        """After a reply passes the check, the count starts again. Recorded as an event when it was not 0."""
        with self.db.tx() as c:
            cur = c.execute("UPDATE chats SET failed_checks = 0, updated_at = ? WHERE id = ? AND failed_checks > 0",
                            (time.time(), chat_id))
            if cur.rowcount:
                self._add(c, chat_id, "event", content=json.dumps({"checks_reset": True}))

    def model_errors(self, chat_id):
        return self.get(chat_id)["model_errors"]

    def add_model_error(self, chat_id, reason):
        """Count one model error in a row in this chat. Returns the new count."""
        with self.db.tx() as c:
            c.execute("UPDATE chats SET model_errors = model_errors + 1, updated_at = ? WHERE id = ?",
                      (time.time(), chat_id))
            self._add(c, chat_id, "event", content=json.dumps({"model_error": reason}, ensure_ascii=False))
            return c.execute("SELECT model_errors FROM chats WHERE id = ?", (chat_id,)).fetchone()[0]

    def reset_model_errors(self, chat_id):
        """After a reply passes, the count starts again. Recorded as an event when it was not 0."""
        with self.db.tx() as c:
            cur = c.execute("UPDATE chats SET model_errors = 0, updated_at = ? WHERE id = ? AND model_errors > 0",
                            (time.time(), chat_id))
            if cur.rowcount:
                self._add(c, chat_id, "event", content=json.dumps({"model_errors_reset": True}))

    def hand_back(self, chat_id, message_id=None):
        """A team member gives the chat back to the agent: stage asking, both counts at 0.

        One event step records it, so branch() rebuilds the same state. message_id: the
        team member's webhook id, marked done here. Returns the stage the chat was in.
        """
        with self.db.tx() as c:
            row = c.execute("SELECT stage FROM chats WHERE id = ?", (chat_id,)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            c.execute("UPDATE chats SET stage = ?, failed_checks = 0, model_errors = 0, updated_at = ? WHERE id = ?",
                      (FIRST_STAGE, time.time(), chat_id))
            self._add(c, chat_id, "event", content=json.dumps(
                {"stage": FIRST_STAGE, "checks_reset": True, "model_errors_reset": True, "handed_back": True}))
            self._done(c, message_id)
            return row["stage"]

    # steps

    def add_step(self, chat_id, role, content=None, tool_calls=None, tool_call_id=None, name=None, media=None,
                 message_id=None):
        """Save one step. Returns its number. message_id: the webhook id this step saves, marked done here."""
        with self.db.tx() as c:
            n = self._add(c, chat_id, role, content, tool_calls, tool_call_id, name, media)
            c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))
            self._done(c, message_id)
            return n

    def add_person_reply(self, chat_id, text, message_id=None, sent_id=None):
        """Save what a team member sent the customer, as written. Returns its step number.

        message_id: the team member's webhook id, marked done here. sent_id: the id WhatsApp
        gave the message the customer got, kept with the step.
        """
        with self.db.tx() as c:
            n = self._add(c, chat_id, "assistant", content=text, name=PERSON)
            c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))
            self._done(c, message_id)
            if sent_id:
                c.execute("INSERT OR IGNORE INTO team_replies (message_id, chat_id, step, at) VALUES (?, ?, ?, ?)",
                          (sent_id, chat_id, n, time.time()))
            return n

    def reply_step(self, sent_id):
        """(chat_id, step) of the person's reply WhatsApp knows by sent_id, or None."""
        if not (isinstance(sent_id, str) and sent_id):
            return None
        with self.db.tx() as c:
            row = c.execute("SELECT chat_id, step FROM team_replies WHERE message_id = ?", (sent_id,)).fetchone()
        return (row["chat_id"], row["step"]) if row else None

    def not_delivered(self, chat_id, step, code, message_id=None):
        """Record that the person's reply at step never reached the customer. message_id: marked done."""
        with self.db.tx() as c:
            self._add(c, chat_id, "event", content=json.dumps({"not_delivered": step, "code": code}))
            self._done(c, message_id)

    def _add(self, c, chat_id, role, content=None, tool_calls=None, tool_call_id=None, name=None, media=None):
        n = c.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM steps WHERE chat_id = ?", (chat_id,)).fetchone()[0]
        c.execute("INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            chat_id, n, role, content,
            json.dumps(tool_calls) if tool_calls else None,
            tool_call_id, name,
            json.dumps(media) if media else None,
            time.time()))
        return n

    def steps(self, chat_id, upto=None):
        sql = "SELECT * FROM steps WHERE chat_id = ?"
        args = [chat_id]
        if upto is not None:
            sql += " AND n <= ?"
            args.append(upto)
        with self.db.tx() as c:
            rows = c.execute(sql + " ORDER BY n", args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tool_calls"] = json.loads(d["tool_calls"]) if d["tool_calls"] else None
            d["media"] = json.loads(d["media"]) if d["media"] else None
            out.append(d)
        return out

    def messages(self, chat_id, upto=None, last=40):
        """The chat as OpenAI-style messages, to resume it. Events are left out.

        Keeps the last `last` messages and never starts on a tool reply cut off
        from its call. Media that was sent earlier shows as a short note.
        """
        msgs = []
        for s in self.steps(chat_id, upto):
            if s["role"] == "event":
                continue
            m = {"role": s["role"], "content": s["content"]}
            if s["media"]:
                notes = [MEDIA_NOTE.get(x.get("kind"), "") for x in s["media"]]
                m["content"] = " ".join([n for n in notes if n] + [s["content"] or ""]).strip()
            if s["tool_calls"]:
                m["tool_calls"] = s["tool_calls"]
            if s["role"] == "tool":
                m["tool_call_id"] = s["tool_call_id"]
            msgs.append(m)
        msgs = msgs[-last:]
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        return msgs

    # branch and replay

    def branch(self, chat_id, at_step):
        """Copy the chat up to and including step `at_step` into a new chat.

        The original is left untouched. The copy's stage, failed-check count and
        model error count are rebuilt from the event steps it carries.
        """
        src = self.get(chat_id)
        steps = self.steps(chat_id, upto=at_step)
        stage, failed, model_errors = FIRST_STAGE, 0, 0
        for s in steps:
            if s["role"] == "event":
                ev = json.loads(s["content"])
                if "stage" in ev:
                    stage = ev["stage"]
                if "check_failed" in ev:
                    failed += 1
                if "checks_reset" in ev:
                    failed = 0
                if "model_error" in ev:
                    model_errors += 1
                if "model_errors_reset" in ev:
                    model_errors = 0
        with self.db.tx() as c:
            new_id = self._new(c, src["channel"], src["customer_id"], stage, failed, chat_id, at_step,
                               model_errors)
            for s in steps:
                c.execute("INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    new_id, s["n"], s["role"], s["content"],
                    json.dumps(s["tool_calls"]) if s["tool_calls"] else None,
                    s["tool_call_id"], s["name"],
                    json.dumps(s["media"]) if s["media"] else None,
                    s["at"]))
        return new_id

    # webhook retries

    def first_seen(self, message_id, payload=None):
        """True the first time a channel message id is seen, False on every retry.

        The id is kept as pending, with payload (the parsed message), until its step is saved.
        """
        with self.db.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO seen_messages (message_id, at, status, payload) VALUES (?, ?, 'pending', ?)",
                (message_id, time.time(), json.dumps(payload, ensure_ascii=False) if payload is not None else None))
            return cur.rowcount == 1

    def saved(self, message_id):
        """True once the webhook id is done: its step is saved, or it was marked done."""
        with self.db.tx() as c:
            row = c.execute("SELECT status FROM seen_messages WHERE message_id = ?", (message_id,)).fetchone()
        return row is not None and row["status"] == "done"

    def mark_done(self, message_id):
        """Mark a webhook id done when it saves no step (a team reply that could not be sent)."""
        with self.db.tx() as c:
            self._done(c, message_id)

    def _done(self, c, message_id):
        if message_id:
            c.execute("UPDATE seen_messages SET status = 'done', payload = NULL WHERE message_id = ?",
                      (message_id,))

    def forget(self, message_id):
        """Drop a pending id that could not be queued, so Meta's retry is taken."""
        with self.db.tx() as c:
            c.execute("DELETE FROM seen_messages WHERE message_id = ? AND status = 'pending'", (message_id,))

    def pending(self, limit=100):
        """Payloads queued but never saved (the process stopped first), oldest first.

        Each call counts one attempt; a message comes back at most MAX_ATTEMPTS times.
        """
        with self.db.tx() as c:
            rows = c.execute(
                "SELECT message_id, payload FROM seen_messages WHERE status = 'pending' AND payload IS NOT NULL "
                "AND attempts < ? ORDER BY at LIMIT ?", (MAX_ATTEMPTS, limit)).fetchall()
            c.executemany("UPDATE seen_messages SET attempts = attempts + 1 WHERE message_id = ?",
                          [(r["message_id"],) for r in rows])
        return [json.loads(r["payload"]) for r in rows]

    # team notes

    def save_note(self, message_id, chat_id, sent_to):
        """Remember one note part sent to a team member, by its channel message id."""
        if not (isinstance(message_id, str) and message_id):
            raise ValueError("a note needs its message id")
        with self.db.tx() as c:
            c.execute("INSERT OR IGNORE INTO team_notes (message_id, chat_id, sent_to, at) VALUES (?, ?, ?, ?)",
                      (message_id, chat_id, sent_to, time.time()))

    def note_chat(self, message_id, sender):
        """The chat a note belongs to, only if that note went to this sender less than
        NOTE_SECONDS ago. None otherwise."""
        if not (isinstance(message_id, str) and message_id and isinstance(sender, str) and sender):
            return None
        with self.db.tx() as c:
            row = c.execute("SELECT chat_id FROM team_notes WHERE message_id = ? AND sent_to = ? AND at >= ?",
                            (message_id, sender, time.time() - NOTE_SECONDS)).fetchone()
        return row["chat_id"] if row else None


MEDIA_NOTE = {
    "image": "(The customer sent a photo earlier. It is not kept.)",
    "audio": "(The customer sent a voice note.)",
}
