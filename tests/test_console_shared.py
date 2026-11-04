"""The console names a lesson from the shared pool (reflection/console.py, reflection/shared.py;
DECISIONS item 83): "learned from N owners" in the lessons table and in its side panel, read off the
lesson's source line, read only. Any other lesson shows its source as before, and the same words
quoted inside another lesson's source are not read as a lesson from the pool."""
import unittest

from engine import lessons as lessons_mod
from engine import risk as risk_mod
from reflection import console
from reflection import shared
from tests.test_console import Base

PID = "0123456789ab"
POOLED = "Offer a smaller size when the customer goes quiet after the cost."
OTHER = "Greet the customer warmly before you answer."
QUOTED = "Say the delivery time when asked."


class LearnedFromOwners(Base):
    def setUp(self):
        super().setUp()
        les = lessons_mod.Lessons(self.db, self.m.plugs["sales"], judge=lambda *a: risk_mod.LOW)
        line = shared.source_line("sales", PID, 3)
        self.pooled = les.propose(POOLED, ["all"], source=f'adapted fully from the {line}: "{POOLED}"', sources=[])
        self.other = les.propose(OTHER, ["all"], source="night study", sources=[])
        # a sibling's lesson whose own text quotes the words: its source is not a pool source
        self.quoted = les.propose(QUOTED, ["all"], sources=[],
                                  source=f'adapted fully from store_a lesson 4: "{QUOTED} {shared.source_line("sales", PID, 99)}"')

    def rows(self):
        with self.db.tx() as c:
            return [tuple(r) for r in c.execute("SELECT * FROM lessons ORDER BY id")]

    def test_the_table_and_the_side_panel_say_learned_from_n_owners(self):
        before = self.rows()
        rows = {x["id"]: x for x in console.collect(self.m, "sales")["lessons"]}
        self.assertEqual((rows[self.pooled]["owners"], rows[self.other]["owners"], rows[self.quoted]["owners"]),
                         (3, None, None))
        table = self.page(view="reflect")
        self.assertIn('<td class="dim">shared pool, learned from 3 owners</td>', table)
        self.assertNotIn("learned from 99 owners</td>", table)
        self.assertIn('<td class="dim">night study</td>', table)
        saw = self.page(view="reflect", row=f"l.{self.pooled}", pane="saw").split('class="drawer"')[1]
        self.assertIn("<h4>From</h4><div>learned from 3 owners\n", saw)
        other = self.page(view="reflect", row=f"l.{self.other}", pane="saw").split('class="drawer"')[1]
        self.assertNotIn("learned from", other)
        quoted = self.page(view="reflect", row=f"l.{self.quoted}", pane="saw").split('class="drawer"')[1]
        self.assertNotIn("<h4>From</h4><div>learned from", quoted)
        self.assertEqual(self.rows(), before)  # read only

    def test_the_source_line_is_read_only_where_the_study_writes_it(self):
        line = shared.source_line("sales", PID, 2)
        self.assertEqual(shared.owners_in(f'adapted partly from the {line}: "{POOLED}"'), 2)
        self.assertEqual(shared.pattern_in(f'adapted partly from the {line}: "{POOLED}"'), PID)
        self.assertEqual(shared.owners_in(line), 2)
        for source in (f'adapted fully from store_a lesson 4: "{line}"', f"night study, {line}", f"{line}0 more",
                       None, 7, ""):
            with self.subTest(source=source):
                self.assertIsNone(shared.owners_in(source))
                self.assertIsNone(shared.pattern_in(source))


if __name__ == "__main__":
    unittest.main()
