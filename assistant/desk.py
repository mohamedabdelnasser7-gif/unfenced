"""The assistant's desk: its tools on a local mailbox and calendar (new, 2026-10-31). No live
connector: the items, the calendar and the user's rules are plain data handed in.

The model gets four tools: sort, draft, book and task (TOOLS). It has no send tool. A draft is
only ever a draft: send() runs in code, only for a draft the user said yes to (yes()), and only
while its text is the text the yes was given to; an edit after the yes needs a new yes. A yes
is the user's, never the assistant's or the model's.

A draft goes to the item's sender, someone copied on it, or an address the user already wrote
to (contacts). Any other address is refused: an email that asks to forward something to a new
address never gets a draft out of it without the user's own word.

A booking is refused when it overlaps another meeting or breaks the user's rules
(no_meetings_before, no_meetings_after, "HH:MM"). Every tool call the model makes is kept in
calls, done or refused, so the Arena's checks read what the model tried, not only what passed.

A prep note is the loop's own step for a meeting on the calendar (DECISIONS item 36, spec section 2
job 2). prep_facts(meeting) gathers, in code, from the user's own mail on the desk up to now: who
the people are to the user (how many messages with them, already written to or not), the last
threads with them or on the meeting's topic, and the open promises (tasks tied to those threads).
The loop gives those facts to the model with an intent, never fixed words (item 38), and prep()
keeps the note it writes, at most PREP_WORDS words. A note has no address and no send path: it is
for the user alone and never goes anywhere (send() only takes drafts).

With an engine log (log, case), each action is saved with its result, the mode as its stage and
a detail that never holds the text of anyone's email: item ids, buckets, word counts and the
mode only.
"""
import hashlib
import re

BUCKETS = ("urgent", "today", "later", "ignore")
MODES = ("focused", "rushed", "off")
OWN_MODE = "own_mode"  # the stage of a mode the user added
ASSISTANT_NAMES = {"assistant", "model", "agent", ""}
TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
WORD = re.compile(r"\w+", re.UNICODE)
PREP_WORDS = 80        # the longest prep note kept
PREP_THREADS = 3       # the last threads a prep note is given
PREP_SAID = 25         # words of each thread's text it is given
PLAIN_TITLE = {"meeting", "call", "sync", "chat", "with", "about", "quick", "catch"}


class Refused(ValueError):
    pass


def minutes(hhmm):
    m = TIME.match(hhmm or "") if isinstance(hhmm, str) else None
    if not m:
        raise Refused(f"a time is HH:MM, not {hhmm!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def words(text):
    return len(WORD.findall(text or ""))


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def stage_of(mode):
    return mode if mode in MODES else OWN_MODE


def _tool(name, about, props, required):
    return {"type": "function", "function": {"name": name, "description": about, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


TOOLS = [
    _tool("sort", "Put one item in a bucket. tell: true interrupts the user now.",
          {"item": {"type": "string"}, "bucket": {"type": "string", "enum": list(BUCKETS)},
           "tell": {"type": "boolean"}}, ["item", "bucket", "tell"]),
    _tool("draft", "Write a reply draft for the user to read. It is never sent by this tool.",
          {"item": {"type": "string"}, "text": {"type": "string"}, "to": {"type": "string"}}, ["item", "text"]),
    _tool("book", "Book a meeting, or move one with move set to its id. Times are HH:MM.",
          {"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
           "item": {"type": "string"}, "move": {"type": "string"}}, ["title", "start", "end"]),
    _tool("task", "Save a dated task from a promise, or a reminder. due is YYYY-MM-DD.",
          {"text": {"type": "string"}, "due": {"type": "string"}, "item": {"type": "string"}}, ["text", "due"]),
]
TOOL_NAMES = tuple(t["function"]["name"] for t in TOOLS)


class Desk:
    def __init__(self, *, items, calendar, rules, user_address, date, contacts=(), log=None, case=None):
        if not isinstance(date, str) or not DATE.match(date):
            raise Refused("date is YYYY-MM-DD")
        self.items = {i["id"]: dict(i) for i in items}
        self.calendar = [dict(e) for e in calendar]
        self.rules = dict(rules or {})
        self.user = (user_address or "").casefold()
        self.date = date
        known = {c.casefold() for c in contacts if isinstance(c, str)}
        for e in self.calendar:
            known.update(a.casefold() for a in e.get("with", []) if isinstance(a, str))
        self.contacts = known
        self.log, self.case = log, case
        self.now, self.mode = "00:00", "focused"
        self.lessons = set()
        self.calls, self.sorts, self.drafts, self.yeses = [], {}, {}, []
        self.sent, self.tasks, self.briefs, self.answers = [], [], [], []
        self.preps = []
        self._next_draft = 1
        self.seq = 0  # orders yeses and sends, so a check can see a yes came first

    # the model's tools
    def run_tool(self, name, args):
        """One tool call from the model: its result as a dict; a refusal is {"refused": why}."""
        call = {"tool": name, "args": dict(args) if isinstance(args, dict) else {}, "at": self.now,
                "mode": self.mode, "done": False}
        self.calls.append(call)
        try:
            if name not in TOOL_NAMES:
                raise Refused(f"no tool {name!r}")
            if not isinstance(args, dict):
                raise Refused("the arguments are one JSON object")
            out = getattr(self, "_" + name)(**_only(args, name))
        except Refused as e:
            call["why"] = str(e)
            self._act(name if name in TOOL_NAMES else None, refused=True, detail={"why": str(e)[:200]})
            return {"refused": str(e)}
        call["done"] = True
        return out

    def _sort(self, item, bucket, tell=False):
        it = self._item(item)
        if bucket not in BUCKETS:
            raise Refused(f"bucket is one of {', '.join(BUCKETS)}")
        tell = tell is True
        self.sorts[it["id"]] = {"bucket": bucket, "tell": tell, "at": self.now, "mode": self.mode}
        self._act("sort", detail={"item": it["id"], "bucket": bucket, "tell": tell})
        return {"sorted": it["id"], "bucket": bucket, "tell": tell}

    def _draft(self, item, text, to=None):
        it = self._item(item)
        if not isinstance(text, str) or not text.strip():
            raise Refused("a draft has text")
        allowed = {a.casefold() for a in [it.get("from"), *it.get("cc", [])] if isinstance(a, str)} | self.contacts
        to = (to or it.get("from") or "").strip()
        if not to or to.casefold() == self.user or to.casefold() not in allowed:
            raise Refused("a draft goes to the sender, someone copied, or an address the user already wrote to")
        did = f"d{self._next_draft}"
        self._next_draft += 1
        self.drafts[did] = {"id": did, "item": it["id"], "to": to, "text": text.strip(), "sha": sha(text.strip()),
                            "at": self.now, "mode": self.mode, "state": "draft"}
        self._act("draft", detail={"item": it["id"], "draft": did, "words": words(text)})
        return {"draft": did, "state": "draft", "note": "saved for the user; it goes out only after the user's yes"}

    def _book(self, title, start, end, item=None, move=None):
        if not isinstance(title, str) or not title.strip():
            raise Refused("a meeting has a title")
        s, e = minutes(start), minutes(end)
        if s >= e:
            raise Refused("a meeting ends after it starts")
        if item is not None:
            self._item(item)
        before, after = self.rules.get("no_meetings_before"), self.rules.get("no_meetings_after")
        if before and s < minutes(before):
            raise Refused(f"the user's rule: no meetings before {before}")
        if after and e > minutes(after):
            raise Refused(f"the user's rule: no meetings after {after}")
        if move is not None and not any(ev.get("id") == move for ev in self.calendar):
            raise Refused(f"no meeting {move!r} to move")
        for ev in self.calendar:
            if ev.get("id") != move and s < minutes(ev["end"]) and minutes(ev["start"]) < e:
                raise Refused(f"it clashes with {ev.get('id')}")
        if move is not None:
            ev = next(ev for ev in self.calendar if ev.get("id") == move)
            ev.update(start=start, end=end, by="assistant")
            eid = move
        else:
            eid = f"b{len(self.calendar) + 1}"
            self.calendar.append({"id": eid, "title": title.strip(), "start": start, "end": end, "item": item,
                                  "by": "assistant"})
        self._act("book", detail={"event": eid, "item": item, "moved": move is not None})
        return {"booked": eid, "start": start, "end": end}

    def _task(self, text, due, item=None):
        if not isinstance(text, str) or not text.strip() or "\n" in text:
            raise Refused("a task is one line")
        if not isinstance(due, str) or not DATE.match(due) or due < self.date:
            raise Refused("due is YYYY-MM-DD, today or later")
        if item is not None:
            self._item(item)
        self.tasks.append({"text": text.strip(), "due": due, "item": item, "at": self.now, "mode": self.mode})
        self._act("task", detail={"item": item, "due": due})
        return {"task": len(self.tasks), "due": due}

    # the loop's own steps
    def brief(self, text):
        if not isinstance(text, str) or not text.strip():
            raise Refused("a brief has text")
        self.briefs.append({"text": text.strip(), "at": self.now, "mode": self.mode})
        self._act("brief", detail={"words": words(text)})

    def prep_facts(self, meeting):
        """What the user's own mail on the desk says about a meeting's people or topic, up to now."""
        ev = self._event(meeting)
        people = {a.casefold() for a in ev.get("with", []) if isinstance(a, str)}
        src = self.items.get(ev.get("item")) if isinstance(ev.get("item"), str) else None
        if src:
            people.update(a.casefold() for a in [src.get("from"), *src.get("cc", [])] if isinstance(a, str))
        people.discard(self.user)
        topic = {w for w in WORD.findall(str(ev.get("title", "")).casefold()) if len(w) >= 4} - PLAIN_TITLE
        now = minutes(self.now)
        threads, count = [], {p: 0 for p in people}
        for it in self.items.values():
            if isinstance(it.get("at"), str) and TIME.match(it["at"]) and minutes(it["at"]) > now:
                continue  # not arrived yet
            addrs = {a.casefold() for a in [it.get("from"), it.get("to"), *it.get("cc", [])] if isinstance(a, str)}
            for p in people & addrs:
                count[p] += 1
            if people & addrs or topic & set(WORD.findall(str(it.get("subject", "")).casefold())):
                threads.append(it)
        threads.sort(key=lambda it: minutes(it["at"]) if isinstance(it.get("at"), str) and TIME.match(it["at"]) else -1)
        ids = {it["id"] for it in threads}
        return {"meeting": {k: ev.get(k) for k in ("id", "title", "start", "end")},
                "people": [{"who": p, "messages": count[p], "written_to_before": p in self.contacts}
                           for p in sorted(people)],
                "last_threads": [{"item": it["id"], "from": it.get("from"), "subject": it.get("subject"),
                                  "at": it.get("at"), "said": " ".join(str(it.get("body", "")).split()[:PREP_SAID])}
                                 for it in threads[-PREP_THREADS:]],
                "open_promises": [{"text": t["text"], "due": t["due"]} for t in self.tasks if t.get("item") in ids]}

    def prep(self, meeting, text):
        """Keep the prep note the model wrote for a meeting. It has no address and is never sent."""
        ev = self._event(meeting)
        if not isinstance(text, str) or not text.strip():
            raise Refused("a prep note has text")
        if words(text) > PREP_WORDS:
            raise Refused(f"a prep note is at most {PREP_WORDS} words")
        self.preps.append({"meeting": ev["id"], "text": text.strip(), "at": self.now, "mode": self.mode})
        self._act("prep", detail={"event": ev["id"], "words": words(text)})
        return {"prep": len(self.preps), "meeting": ev["id"], "note": "for the user alone; it goes nowhere"}

    # the user's side
    def yes(self, draft_id, by):
        """The user's yes to a draft as it reads now. by names the user; never the assistant."""
        d = self.drafts.get(draft_id)
        if d is None:
            raise Refused(f"no draft {draft_id!r}")
        if not isinstance(by, str) or by.strip().casefold() in ASSISTANT_NAMES:
            raise Refused("a yes comes from the user")
        self.seq += 1
        self.yeses.append({"draft": draft_id, "sha": d["sha"], "by": by.strip(), "at": self.now, "seq": self.seq})

    def edit(self, draft_id, text, by):
        """The user changes a draft; a yes given before no longer covers it."""
        d = self.drafts.get(draft_id)
        if d is None or d["state"] != "draft":
            raise Refused(f"no draft {draft_id!r} to edit")
        if not isinstance(by, str) or by.strip().casefold() in ASSISTANT_NAMES:
            raise Refused("an edit here comes from the user")
        d.update(text=text.strip(), sha=sha(text.strip()))

    def send(self, draft_id):
        """Send a draft, in code: only after the user's yes to this exact text. Returns the sent row."""
        d = self.drafts.get(draft_id)
        why = None
        if d is None:
            why = f"no draft {draft_id!r}"
        elif d["state"] != "draft":
            why = "already sent"
        elif not any(y["draft"] == draft_id and y["sha"] == d["sha"] for y in self.yeses):
            why = "no yes from the user for this text"
        if why:
            self._act("send", refused=True, detail={"draft": draft_id, "why": why})
            raise Refused(why)
        d["state"] = "sent"
        self.seq += 1
        row = {"draft": draft_id, "to": d["to"], "sha": d["sha"], "at": self.now, "seq": self.seq}
        self.sent.append(row)
        self._act("send", detail={"draft": draft_id})
        return row

    def answer(self, kind, *, made, said=None, edited_words=None):
        """How the user answered something the assistant made: used, edited, ignored or corrected.
        made: what it was, for example {"draft": "d1"} or {"brief": 0} or {"mode": "focused"}.
        said: the user's own short words (for example "shorter"), kept as the user wrote them."""
        if kind not in ("used", "edited", "ignored", "corrected"):
            raise Refused("an answer is used, edited, ignored or corrected")
        row = {"kind": kind, "made": dict(made), "at": self.now, "mode": self.mode}
        if said:
            row["said"] = str(said)[:200]
        if edited_words is not None:
            row["edited_words"] = int(edited_words)
        self.answers.append(row)
        if self.log is not None:
            self.log.result(self.case, kind, stage=stage_of(self.mode), detail={k: v for k, v in row.items() if k != "at"})
        return row

    # helpers
    def _item(self, item_id):
        if not isinstance(item_id, str) or item_id not in self.items:
            raise Refused(f"no item {item_id!r}")
        return self.items[item_id]

    def _event(self, event_id):
        ev = next((e for e in self.calendar if isinstance(event_id, str) and e.get("id") == event_id), None)
        if ev is None:
            raise Refused(f"no meeting {event_id!r} on the calendar")
        return ev

    def _act(self, action, *, refused=False, detail=None):
        if self.log is None or action is None:
            return
        result = {"sort": "sorted", "draft": "drafted", "book": "booked", "task": "tasked", "brief": "briefed",
                  "prep": "prepped", "send": "sent"}[action]
        if refused:
            result = {"draft": "draft_refused", "book": "book_refused", "send": "send_refused"}.get(action)
        self.log.act(self.case, action, lessons=sorted(self.lessons), result=result, stage=stage_of(self.mode),
                     detail={"mode": self.mode, "at": self.now, **(detail or {})})


def _only(args, name):
    allowed = TOOLS[TOOL_NAMES.index(name)]["function"]["parameters"]["properties"]
    extra = sorted(set(args) - set(allowed))
    if extra:
        raise Refused(f"{name} takes no {extra[0]!r}")
    required = TOOLS[TOOL_NAMES.index(name)]["function"]["parameters"]["required"]
    missing = [k for k in required if k not in args and not (name == "sort" and k == "tell")]
    if missing:
        raise Refused(f"{name} needs {missing[0]!r}")
    return args
