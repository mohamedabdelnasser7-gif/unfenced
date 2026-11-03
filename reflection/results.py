"""The Sales agent's result log. Every agent turn is recorded with its outcome.

Outcomes today: replied, check_failed (one row per blocked reply, with the check's
feedback), no_safe_reply (no safe reply could be sent, so nothing went out and the agent
kept the chat; it counts as harm and the chat as lost), limited (over a model call limit,
no model call made), model_error (the model did not answer; the customer was asked to write
again) and turn_failed (the code crashed during the turn; the same line went out, and a second
in a row is no safe reply). person_replied comes only from imported past chats (a team
member's reply; its step is the example the reflection reads). Orders: order_drafted (draft_order
made a summary, with its total) and order_created (the customer said yes and the store took
the order, with its number, total and COD risk). chat_closed comes from sales/quiet.py when a
chat closes after quiet with no order (DECISIONS item 54): the case is lost at once. delivered
and refused are the Sales plug's second signal (DECISIONS item 66): they come from Bosta's
delivery webhook (channels/bosta.py), matched to the chat through the order number its
order_created row names (chat_for_order), from Bosta's API on the night run (reflection/late.py)
or from a person on the morning page, each through late(), once a talk. The night study reads
this log.

late() is for any agent, not only Sales: it adds a result that came later to a case of the plug
it is given, when that result is one of the plug's late results (engine/plug.py Plug.late: a slow
deciding result, or a second signal).

Rows live in the engine's log (engine/log.py) under the Sales agent plug
(sales/plug.json); a case is one customer on a channel and an outcome is a result. Each chat is
one talk of its case (DECISIONS item 65, kit/chats.py talk): the case id is the id of the chat that
opened the case, and a chat they open after one closed is saved under the same case id as talk 2,
talk 3, each talk with its own result, read by the night study and the fast notes as a case of its
own.
Every method here takes a chat id and saves or reads that chat's talk; a chat id the chats table
does not hold (or a database made before talks) is its own case, talk 1. A row's source is the
customer, so the log keeps the case id as it. The engine keeps no
list of its own and refuses an outcome the plug did not declare. An outcome the plug says
ends an action (replied ends a reply, order_created an order) is saved with that action and
the ids of the lessons it was given; the rest (a team member's reply in an imported chat,
delivered, refused) attach to the chat on their own.

Before the engine the log was one results table keyed by chat_id. The first Results(db)
on such a database moves every row into the engine's log under the same id and drops
the old table, in one transaction. A row the plug cannot place (another agent, an
undeclared outcome) stops the move and leaves the old table as it was.
"""
import json
import time

from engine.log import TALK, Log, is_history, talk_key
from kit.db import Db
from reflection import PLUG

MAX_BY = 60  # who marked a result, as saved in its detail


class Results(Log):
    def __init__(self, db=None):
        super().__init__(db if db is not None else Db(), PLUG)
        _move_old_rows(self.db)
        self.fill_sources()  # a moved row's source is its chat, as for every new row

    def record(self, chat_id, outcome, *, agent=PLUG.agent, step=None, stage=None, lessons=(), detail=None, at=None):
        """Add one row to the chat's talk. lessons: ids of the lessons the reply was given; at: its
        time, now when left out."""
        if agent != self.plug.agent:
            raise ValueError(f"this log writes for {self.plug.agent}, not {agent!r}")
        case, talk = self.talk_of(chat_id)
        after = self.plug.result(outcome).after
        if after is not None:
            return self.act(case, after, result=outcome, lessons=lessons, stage=stage, step=step, detail=detail,
                            at=at, talk=talk)
        if lessons:
            raise ValueError(f"lessons go with an action; {outcome!r} comes on its own")
        return self.result(case, outcome, stage=stage, step=step, detail=detail, at=at, talk=talk)

    def for_chat(self, chat_id):
        """The rows of the chat's talk, oldest first, with the names the Sales agent uses."""
        case, talk = self.talk_of(chat_id)
        return [_sales_row(r, chat_id) for r in self.query(case=case, talk=talk or 1)]

    def talk_of(self, chat_id):
        """(case id, talk) the chat's rows are saved under (kit/chats.py talk): (chat_id, None)
        when the chats table does not hold it or was made before talks."""
        with self.db.tx() as c:
            if "talk" not in {r["name"] for r in c.execute("PRAGMA table_info(chats)")}:
                return chat_id, None
            row = c.execute("SELECT COALESCE(case_id, id) AS case_id, COALESCE(talk, 1) AS talk FROM chats "
                            "WHERE id = ?", (chat_id,)).fetchone()
        return (row["case_id"], row["talk"]) if row else (chat_id, None)

    def chat_for_order(self, *names):
        """The talk whose order_created row names one of these orders (its detail's "order", as
        the store gave it, for example "#1001"), as its window key (engine/log.py talk_key: the
        case id for talk 1), or None when no talk does or more than one does, so a slow result
        never lands on the wrong talk. Only orders the Shopify store took count: Bosta ships
        those, and the demo store's numbers also start at #1001."""
        names = [n for n in names if isinstance(n, str) and n]
        if not names:
            return None
        marks = ", ".join("?" for _ in names)
        with self.db.tx() as c:
            rows = c.execute(
                f"SELECT DISTINCT case_id, {TALK} AS talk FROM trace WHERE agent = ? AND result = 'order_created' "
                "AND json_valid(detail) AND json_extract(detail, '$.store') = 'shopify' "
                f"AND json_extract(detail, '$.order') IN ({marks})",
                (self.plug.agent, *names)).fetchall()
        return talk_key(rows[0]["case_id"], rows[0]["talk"]) if len(rows) == 1 else None


def late(db, plug, case_id, outcome, *, detail=None, by=None, now=None):
    """Add one result that came later to a case of this plug, to one talk of it: case_id is a
    window key (engine/log.py talk_key, read by Log.unit), so "<case id> talk 2" is that case's
    second talk and a plain case id its first. From a tool's webhook
    (channels/bosta.py), a tool's API on the night run (reflection/late.py) or a person on the
    morning page or in an uploaded sheet. outcome must be one of the plug's late results
    (Plug.late): a deciding result when one of them is slow, or a second signal result. Once a
    case for each of the two groups: when the case already has a result of the outcome's group,
    nothing is saved and None comes back; else the new row's id. Once a talk, when the case has more. The check and the write are one
    SQL statement, so two writers at the same moment (the webhook and a person) still save one.
    A case with no row, or one imported from the past, is refused (ValueError): a late result
    never starts a case. by: who brought it (a person's name, "api" or "sheet"), saved in the
    detail; now: its time, the clock when left out."""
    deciding, second = plug.late()
    group = deciding if outcome in deciding else second if outcome in second else ()
    if not group:
        raise ValueError(f"{plug.agent} takes no late result {outcome!r}")
    if plug.result(outcome).after is not None:
        raise ValueError(f"{outcome!r} ends an action; it never comes on its own")
    log = Log(db, plug)
    case, talk = log.unit(case_id)
    rows = log.query(case=case, talk=talk)
    if not rows:
        raise ValueError("no such case")
    if any(is_history(r) for r in rows):
        raise ValueError("a case imported from the past takes no late result")
    d = dict(detail or {})
    if by is not None:
        d["by"] = str(by)[:MAX_BY]
    source = next((r["source"] for r in reversed(rows) if r["source"] is not None), None)
    at = time.time() if now is None else float(now)
    marks = ", ".join("?" for _ in group)
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO trace (agent, case_id, action, result, cause, lessons, stage, step, detail, at, source, talk) "
            "SELECT ?, ?, NULL, ?, NULL, '[]', NULL, NULL, ?, ?, ?, ? "
            f"WHERE NOT EXISTS (SELECT 1 FROM trace WHERE agent = ? AND case_id = ? AND {TALK} = ? "
            f"AND result IN ({marks}))",
            (plug.agent, case, outcome, json.dumps(d, ensure_ascii=False) if d else None, at, source,
             rows[-1]["talk"], plug.agent, case, talk, *group))
        return cur.lastrowid if cur.rowcount == 1 else None


def _sales_row(r, chat_id):
    d = dict(r)
    d.pop("case_id")
    d["chat_id"] = chat_id
    d["outcome"] = d.pop("result")
    return d


def _move_old_rows(db):
    """Move the rows of the old results table (keyed by chat_id) into the engine's log, same ids."""
    with db.tx() as c:
        columns = {r["name"] for r in c.execute("PRAGMA table_info(results)")}
        if "chat_id" not in columns:
            return
        for r in c.execute("SELECT * FROM results ORDER BY id").fetchall():
            if r["agent"] != PLUG.agent:
                raise ValueError(f"results row {r['id']}: no plug here for agent {r['agent']!r}; nothing moved")
            try:
                after = PLUG.result(r["outcome"]).after
            except ValueError as e:
                raise ValueError(f"results row {r['id']}: {e}; nothing moved") from None
            c.execute(
                "INSERT INTO trace (id, agent, case_id, action, result, lessons, stage, step, detail, at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["id"], r["agent"], str(r["chat_id"]), after, r["outcome"], r["lessons"] or "[]", r["stage"],
                 r["step"], r["detail"], r["at"]))
        c.execute("DROP TABLE results")
