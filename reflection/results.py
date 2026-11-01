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
and refused come from Bosta's delivery webhook (channels/bosta.py), matched to the chat through
the order number its order_created row names (chat_for_order). The night study reads this log.

Rows live in the engine's log (engine/log.py) under the Sales agent plug
(sales/plug.json); a case is one chat and an outcome is a result. A row's source is
the person writing in, in that chat, so the log keeps the chat id as it; their next chat after
one closes is a new case (the fast note follows them there, reflection/fast.py). The engine keeps no
list of its own and refuses an outcome the plug did not declare. An outcome the plug says
ends an action (replied ends a reply, order_created an order) is saved with that action and
the ids of the lessons it was given; the rest (a team member's reply in an imported chat,
delivered, refused) attach to the chat on their own.

Before the engine the log was one results table keyed by chat_id. The first Results(db)
on such a database moves every row into the engine's log under the same id and drops
the old table, in one transaction. A row the plug cannot place (another agent, an
undeclared outcome) stops the move and leaves the old table as it was.
"""
from engine.log import Log
from kit.db import Db
from reflection import PLUG


class Results(Log):
    def __init__(self, db=None):
        super().__init__(db if db is not None else Db(), PLUG)
        _move_old_rows(self.db)
        self.fill_sources()  # a moved row's source is its chat, as for every new row

    def record(self, chat_id, outcome, *, agent=PLUG.agent, step=None, stage=None, lessons=(), detail=None):
        """Add one row. lessons: ids of the lessons the reply was given."""
        if agent != self.plug.agent:
            raise ValueError(f"this log writes for {self.plug.agent}, not {agent!r}")
        after = self.plug.result(outcome).after
        if after is not None:
            return self.act(chat_id, after, result=outcome, lessons=lessons, stage=stage, step=step, detail=detail)
        if lessons:
            raise ValueError(f"lessons go with an action; {outcome!r} comes on its own")
        return self.result(chat_id, outcome, stage=stage, step=step, detail=detail)

    def for_chat(self, chat_id):
        """The chat's rows, oldest first, with the names the Sales agent uses."""
        return [_sales_row(r) for r in self.case(chat_id)]

    def chat_for_order(self, *names):
        """The chat whose order_created row names one of these orders (its detail's "order", as
        the store gave it, for example "#1001"), or None when no chat does or more than one
        does, so a slow result never lands on the wrong chat. Only orders the Shopify store took
        count: Bosta ships those, and the demo store's numbers also start at #1001."""
        names = [n for n in names if isinstance(n, str) and n]
        if not names:
            return None
        marks = ", ".join("?" for _ in names)
        with self.db.tx() as c:
            rows = c.execute(
                "SELECT DISTINCT case_id FROM trace WHERE agent = ? AND result = 'order_created' "
                "AND json_valid(detail) AND json_extract(detail, '$.store') = 'shopify' "
                f"AND json_extract(detail, '$.order') IN ({marks})",
                (self.plug.agent, *names)).fetchall()
        return rows[0]["case_id"] if len(rows) == 1 else None


def _sales_row(r):
    d = dict(r)
    d["chat_id"] = d.pop("case_id")
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
