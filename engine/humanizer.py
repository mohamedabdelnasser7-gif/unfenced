"""The humanizer step: texts a business sent in the past come in as candidates, and a humanizer
writes each one in our tone or rejects it. The business's data gives what to say; our layer
gives how it is said.

A candidate is one text the business sent, already masked by whoever adds it, with its case
and source.
Its status is one of three:
  waiting   not run yet, or the humanizer failed or gave no clear answer; it can run again;
  refined   the humanizer wrote it in our tone; only a refined candidate could ever be used;
  rejected  the humanizer said no, with its reason, or the caller's check refused the result.
A candidate leaves waiting once. The database refuses any change to a refined or rejected
candidate and any change to a candidate's text, so a later run never rewrites one.

A humanizer is any callable humanizer(text) that answers {"refined": text} or {"rejected":
reason}; anything else, or an error, leaves the candidate waiting. run() is the hook for new
data: the history import calls it after adding candidates, and the live loop would call it
the same way. Nothing here reads a prompt or sends anything, and no agent uses candidates yet.
Pairs is a humanizer from fixed pairs, with no model, for a demo; the real one comes later,
and inside the product only Meta models may run it.
"""
import time
from collections import Counter

WAITING, REFINED, REJECTED = "waiting", "refined", "rejected"
NOT_YET = "not refined yet"
MAX_LEN = 500   # characters of a refined text

SCHEMA = """
CREATE TABLE IF NOT EXISTS reply_candidates (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  key TEXT NOT NULL,
  case_id TEXT,
  text TEXT NOT NULL,
  source TEXT NOT NULL,
  at REAL NOT NULL,
  added_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'refined', 'rejected')),
  refined TEXT,
  why TEXT,
  by TEXT,
  done_at REAL,
  UNIQUE (agent, key),
  CHECK (status != 'refined' OR refined IS NOT NULL)
);
CREATE TRIGGER IF NOT EXISTS reply_candidates_settled BEFORE UPDATE ON reply_candidates
WHEN OLD.status != 'waiting'
BEGIN SELECT RAISE(ABORT, 'a refined or rejected candidate never changes'); END;
CREATE TRIGGER IF NOT EXISTS reply_candidates_text_fixed BEFORE UPDATE OF agent, key, text ON reply_candidates
BEGIN SELECT RAISE(ABORT, 'a candidate keeps its text'); END;
"""


def refine(text, humanizer, check=None):
    """(status, refined text or None, why) for one candidate. check(refined): None when the
    refined text may stand, else the reason it is rejected."""
    try:
        answer = humanizer(text)
    except Exception as e:  # a failing humanizer leaves it waiting
        return WAITING, None, f"the humanizer failed ({type(e).__name__})"
    if isinstance(answer, dict) and set(answer) == {"refined"}:
        out = answer["refined"]
        if not isinstance(out, str) or not out.strip() or len(out.strip()) > MAX_LEN:
            return WAITING, None, f"no clear answer: a refined text has 1 to {MAX_LEN} characters"
        why = check(out.strip()) if check is not None else None
        if why:
            return REJECTED, None, f"the refined text was refused: {why}"
        return REFINED, out.strip(), None
    if isinstance(answer, dict) and set(answer) == {"rejected"} and isinstance(answer["rejected"], str) \
            and answer["rejected"].strip():
        return REJECTED, None, answer["rejected"].strip()[:300]
    return WAITING, None, "no clear answer"


class Candidates:
    """One agent's candidates and their status."""

    def __init__(self, db, agent):
        if not isinstance(agent, str) or not agent:
            raise ValueError("an agent name is text")
        self.db, self.agent = db, agent
        self.db.script(SCHEMA)

    def add(self, key, text, *, case_id, source, at, now=None):
        """A new candidate, waiting. False when this agent already has one with this key."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("a candidate is text")
        with self.db.tx() as c:
            cur = c.execute("INSERT OR IGNORE INTO reply_candidates (agent, key, case_id, text, source, at, added_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (self.agent, key, case_id, text.strip(), source, float(at),
                             time.time() if now is None else float(now)))
            return cur.rowcount == 1

    def count(self):
        with self.db.tx() as c:
            return c.execute("SELECT COUNT(*) FROM reply_candidates WHERE agent = ?", (self.agent,)).fetchone()[0]

    def mine(self, status=None):
        """This agent's candidates, oldest first, of one status when named."""
        sql, args = "SELECT * FROM reply_candidates WHERE agent = ?", [self.agent]
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        with self.db.tx() as c:
            return [dict(r) for r in c.execute(sql + " ORDER BY id", args)]

    def run(self, humanizer, *, check=None, by=None, now=None):
        """Run the humanizer on every waiting candidate. Returns how many ended in each status."""
        out = Counter()
        by = by or getattr(humanizer, "label", None) or type(humanizer).__name__
        for cand in self.mine(WAITING):
            status, refined, why = refine(cand["text"], humanizer, check)
            out[status] += 1
            if status == WAITING:
                continue
            with self.db.tx() as c:  # only a candidate still waiting moves
                c.execute("UPDATE reply_candidates SET status = ?, refined = ?, why = ?, by = ?, done_at = ? "
                          "WHERE id = ? AND status = 'waiting'",
                          (status, refined, why, str(by)[:100], time.time() if now is None else float(now), cand["id"]))
        return out


def _key(text):
    return " ".join(str(text).split())


class Pairs:
    """A humanizer from fixed pairs, (their text, our text), with no model: for a demo. A text it
    has no pair for is rejected as not refined yet."""

    label = "demo pairs"

    def __init__(self, pairs):
        self.pairs = {_key(theirs): ours for theirs, ours in pairs}

    def __call__(self, text):
        ours = self.pairs.get(_key(text))
        return {"refined": ours} if ours else {"rejected": NOT_YET}
