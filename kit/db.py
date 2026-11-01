"""One SQLite file for chats, results and lessons (data/ascent.db, gitignored)."""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "ascent.db"


class Db:
    """A single connection shared by threads, guarded by one lock.

    Pass ":memory:" for tests.
    """

    def __init__(self, path=None):
        path = DEFAULT_PATH if path is None else path
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._depth = 0  # how many tx() blocks this lock's holder is inside

    @contextmanager
    def tx(self):
        """One transaction: commits on success, rolls back on any error. A tx() inside another is a
        savepoint: its error undoes only its own writes, and only the outer block commits, so the
        outer block's writes land together or not at all."""
        with self._lock:
            if self._depth:
                yield from self._savepoint()
                return
            self._depth = 1
            try:
                yield self.conn
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise
            finally:
                self._depth = 0

    def _savepoint(self):
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN")  # else the savepoint would open its own transaction and commit it
        name = f"tx{self._depth}"
        self.conn.execute(f"SAVEPOINT {name}")
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            if self.conn.in_transaction:  # some errors end the whole transaction in SQLite itself
                self.conn.execute(f"ROLLBACK TO {name}")
                self.conn.execute(f"RELEASE {name}")
            raise
        else:
            self.conn.execute(f"RELEASE {name}")
        finally:
            self._depth -= 1

    def script(self, sql):
        with self._lock:
            self.conn.executescript(sql)

    def close(self):
        with self._lock:
            self.conn.close()
