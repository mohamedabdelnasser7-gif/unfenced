"""The morning page in the locked A3 look (_system/hackathon/design/morning/r1/opt-a3.html):
the tabs are links to the page's own parts, with no count on the tabs or beside the waiting
heading and no numbers row (DECISIONS item 35), what needs no answer sits in one closed fold, a
day with no answers changes nothing, the open card holds the first waiting lesson's Yes and No,
every time is Cairo time, and a study's counts are named from the pattern's own words, never "with it" (where
"it" read as the lesson). No raw case id is on the page. Made-up plugs, in-memory database."""
import re
import unittest

from reflection import morning as mod
from tests import test_morning as tm

NOW, DAY = tm.NOW, tm.DAY  # NOW is 2027-01-15 08:00 UTC, a Friday: 10:00 in Cairo
TABS = ("today", "lessons", "ideas", "facts", "agents")
LANDMARK = "The agent never asked for a landmark before the order."
STUDY = ('night study of waterer, cases from 2027-01-01 to 2027-01-14: "' + LANDMARK + '" helps; with it 42 of 81 '
         'ended grew, without it 12 of 60; 3 and 4 sources; chance it is better 97%; cases with it: bed1, bed2, bed3 '
         'and 39 more')
ADAPTED = ('adapted fully from fan cases fan7, fan8 and 3 more: "Spun before noon" helps; there with it 5 of 9 ended '
           'cooled, without it 2 of 8; chance it is better 88%')


def body(page):
    """The page after its style, so a CSS selector never counts as markup."""
    return page.split("</style>", 1)[1]


class Tabs(tm.Base):
    def test_each_tab_is_a_link_to_its_own_part_of_the_page(self):
        self.high("Water bed 1 twice.")
        page = body(self.page())
        for anchor in TABS:
            self.assertEqual(page.count(f'href="#{anchor}"'), 2, anchor)  # the top island and the bottom bar
            self.assertEqual(page.count(f'id="{anchor}"'), 1, anchor)
        self.assertNotIn("<script", page)
        self.assertNotIn("<link", page)

    def test_the_lessons_tab_carries_no_count(self):
        for n in (1, 2, 3):
            self.high(f"Water bed {n} twice.")
        page = body(self.page())
        self.assertEqual(page.count(f'href="#lessons">{mod._icon("list")}Lessons</a>'), 2)  # the island and the bar
        self.assertNotIn('class="bdg"', page)

    def test_nothing_waiting_shows_a_calm_line(self):
        page = body(self.page())
        self.assertNotIn('class="bdg"', page)
        self.assertNotIn('class="hcount', page)
        self.assertIn("Nothing waits for a yes.", page)


class Count(tm.Base):
    def test_the_heading_has_no_count_and_there_is_no_numbers_row(self):
        self.high("Water bed 1 twice.")
        self.high("Water bed 2 twice.")
        page = body(self.page())
        self.assertIn('<h2 id="w-h">Waiting for your yes</h2>', page)
        self.assertNotIn('class="hcount', page)
        self.assertNotIn('class="counts"', page)
        top = page.split('id="today"', 1)[1].split("</section>", 1)[0]
        top = re.sub(r'<p class="num">[^<]*Cairo</p>', "", top)
        self.assertNotRegex(re.sub(r"<[^>]+>", "", top), r"\d", "a number above the cards besides the date")

    def test_a_yes_names_its_trial_level_share_and_days(self):
        self.high("Water bed 1 twice.")
        self.assertRegex(body(self.page()), r"A yes means a <strong>careful trial</strong>: [^<]+ for \d+ days")

    def test_the_cards_past_the_five_shown_are_never_counted(self):
        for n in range(1, 8):
            self.high(f"Water bed {n} twice.")
        view = self.morning.view(NOW)
        self.assertEqual((len(view["cards"]), view["more"]), (5, 2))
        page = body(mod.render(view, token="t"))
        self.assertNotIn("more wait", page)
        self.assertNotIn("at a time", page)
        self.assertNotIn("7 waiting", page)


def open_part(page):
    """The page outside the fold "What happened overnight", as words, tags taken out."""
    before, rest = page.split('<details class="overnight"', 1)
    after = rest.split("</details></section>", 1)[1]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", before + after))


class Light(tm.Base):
    """DECISIONS item 35: the page is light. No count of what is left to answer, nothing that needs
    no answer outside the fold, and a day with no answers changes nothing."""

    LEFT = re.compile(r"\b\d+\s+(?:more|waiting|left to|to go|remaining|unanswered|still wait)\b|\bmore wait\b|"
                      r"\boverdue\b|\breminder\b|\bskipped\b|\byou missed\b", re.I)

    def test_no_count_of_what_is_left_anywhere_on_the_page(self):
        for n in range(1, 9):
            self.high(f"Water bed {n} twice.")
        page = body(self.page())
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", page), self.LEFT)
        self.assertNotIn('class="bdg"', page)
        self.assertNotIn('class="hcount', page)
        self.assertNotIn('class="meta more-wait"', page)
        self.assertNotRegex(open_part(page), r"\b8\b", "the eight waiting are never counted outside the fold")

    def test_a_skipped_day_changes_nothing(self):
        ids = [self.high(f"Water bed {n} twice.") for n in range(1, 7)]
        self.report("waterer", NOW, notes=["One note from the night."])
        before = {i: dict(self.lessons.get(i)) for i in ids}
        first = self.morning.view(NOW)
        later = self.morning.view(NOW + 3 * DAY)  # three mornings with no answer
        self.assertEqual({i: dict(self.lessons.get(i)) for i in ids}, before)  # each one stays off, waiting
        self.assertEqual([c["id"] for c in later["cards"]], [c["id"] for c in first["cards"]])
        stack = [body(mod.render(v, token="t")).split('id="lessons"', 1)[1].split("</section>", 1)[0]
                 for v in (first, later)]
        self.assertEqual(stack[0], stack[1])  # the waiting stack reads the same, no age, no nag
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", body(mod.render(later, token="t"))), self.LEFT)

    def test_what_needs_no_answer_sits_in_one_closed_fold(self):
        self.high("Water bed 1 twice.")
        self.report("waterer", NOW, notes=["One note from the night."])
        (self.dir / "night-waterer-bad.json").write_text("{", encoding="utf-8")
        page = body(self.page())
        self.assertEqual(page.count('<details class="overnight" id="overnight">'), 1)  # no open attribute: closed
        self.assertIn("What happened overnight", page)
        fold = page.split('<details class="overnight"', 1)[1]
        for part in ("One note from the night.", "The night's notes", "New in the last day", "Trials", "Pulled",
                     "A saved night report could not be read"):
            self.assertIn(part, fold, part)
            self.assertNotIn(part, open_part(page), part)

    def test_a_paused_trial_stays_open_with_its_stop(self):
        lid = self.lessons.propose("Water the seedlings at dawn.", ["seedling"], sources=[], now=NOW - DAY)
        with self.db.tx() as c:
            c.execute("INSERT INTO trial_marks (agent, lesson_id, kind, value, detail, at) VALUES (?, ?, 'paused', 1, "
                      "'{}', ?)", ("waterer", lid, NOW - 60))
        page = body(self.page())
        outside = page.split('<details class="overnight"', 1)[0]
        self.assertIn(f'id="p{lid}"', outside)
        self.assertIn("waterer, paused", outside)
        self.assertIn(f'action="/stop"><input type="hidden" name="token" value="t0ken"><input type="hidden" '
                      f'name="lesson" value="{lid}">', outside)

    def test_the_page_says_user_never_owner_or_operator(self):
        kept = tm.kept_lesson(self.lessons, "Water the grown beds deeply.", ["grown"], yes_by=mod.BY, now=NOW)
        self.morning.stop(kept, "It drowned the roots.", now=NOW)
        self.high("Water bed 1 twice.")
        words = re.sub(r"<[^>]+>", " ", body(self.page())).lower()
        self.assertIn("stopped by the user", words)
        for bad in ("owner", "operator", "learning", "fast reflection"):
            self.assertNotIn(bad, words, bad)


class Stack(tm.Base):
    def test_the_open_card_holds_the_first_waiting_lessons_yes_and_no(self):
        low, top = self.high("Water bed 1 twice."), self.high("Water bed 2 twice.")
        self.report("waterer", NOW, cards=[tm.card(low, 0.6, 20, 10, 20, 9), tm.card(top, 0.95, 20, 18, 20, 8)])
        view = self.morning.view(NOW)
        self.assertEqual([c["id"] for c in view["cards"]], [top, low])
        page = body(mod.render(view, token="t0ken"))
        open_card = page.split('<article class="pass sq"', 1)[1].split("</article>", 1)[0]
        self.assertIn(f'id="c{top}"', open_card[:40])
        self.assertIn('<form method="post" action="/yes" class="yes"><input type="hidden" name="token" value="t0ken">'
                      f'<input type="hidden" name="lesson" value="{top}">', open_card)
        self.assertIn(f'<form method="post" action="/no" class="no" id="no-{top}">', open_card)
        self.assertIn(f'form="no-{top}"', open_card)  # the why for No, under More on this lesson
        self.assertNotIn(f'name="lesson" value="{low}"', open_card)
        peek = page.split(f'<details class="peek p1 sq" id="c{low}">', 1)[1].split("</details>\n", 1)[0]
        self.assertIn(f'<input type="hidden" name="lesson" value="{low}"><input type="hidden" name="shown" value="">'
                      '<button type="submit">Yes</button>', peek)
        self.assertEqual(page.count('action="/yes"'), 2)

    def test_the_static_copy_has_the_stack_and_no_forms(self):
        self.high("Water bed 1 twice.")
        page = body(mod.render(self.morning.view(NOW), token=None))
        self.assertIn('<article class="pass sq"', page)
        self.assertNotIn("<form", page)
        self.assertIn("A static copy", page)
        self.assertNotIn("On this computer only", page)


class CairoTime(tm.Base):
    def test_every_time_on_the_page_is_cairo_time_never_utc(self):
        self.high("Water bed 1 twice.")
        page = body(self.page())
        self.assertIn('<p class="num">Fri 15 Jan, 10:00 Cairo</p>', page)  # the greeting
        self.assertIn("added Fri 15 Jan 2027, 10:00 Cairo", page)
        self.assertNotIn("UTC", page)

    def test_the_words_for_a_time(self):
        self.assertEqual(mod._when(NOW), "Fri 15 Jan 2027, 10:00 Cairo")
        self.assertEqual(mod._today(NOW), "Fri 15 Jan, 10:00 Cairo")
        self.assertEqual(mod._date(NOW + 14 * DAY), "Fri 29 Jan")

    def test_what_is_not_a_time_reads_unknown_and_never_raises(self):
        for bad in (None, "soon", True, float("nan"), float("inf"), 1e20, -1e20):
            self.assertEqual(mod._when(bad), "an unknown time", bad)
            self.assertEqual(mod._date(bad), "an unknown day", bad)
            self.assertEqual(mod._today(bad), "An unknown time", bad)


class Sides(unittest.TestCase):
    def test_a_pattern_that_says_never_names_the_thing_and_the_act(self):
        self.assertEqual(mod.sides(LANDMARK), ("landmark not asked", "landmark asked"))
        self.assertEqual(mod.sides("The agent never offered free delivery."), ("free delivery not offered",
                                                                         "free delivery offered"))

    def test_any_other_pattern_is_named_by_its_own_words(self):
        self.assertEqual(mod.sides("Customer sent a voice note."), ("customer sent a voice note", "the other cases"))
        self.assertEqual(mod.sides("The agent never confirmed address phone number zone."),  # too long to name
                         ("the agent never confirmed address phone number zone", "the other cases"))
        self.assertEqual(mod.sides(""), ("cases with the pattern", "the other cases"))
        self.assertEqual(mod.sides(None), ("cases with the pattern", "the other cases"))

    def test_the_source_line_names_its_sides_and_shows_no_case_id(self):
        self.assertEqual(mod.source_text(STUDY),
                         'night study of waterer, cases from 2027-01-01 to 2027-01-14: "' + LANDMARK + '" helps; '
                         'landmark not asked: 42 of 81 ended grew; landmark asked: 12 of 60; 3 and 4 sources; chance it '
                         'is better 97%')
        self.assertEqual(mod.source_text(ADAPTED),
                         'adapted fully from fan cases: "Spun before noon" helps; there spun before noon: 5 of 9 ended '
                         'cooled; the other cases: 2 of 8; chance it is better 88%')
        self.assertEqual(mod.source_text("edited by the user from lesson 4"), "edited by the user from lesson 4")
        self.assertEqual(mod.source_text(None), "")


class Wording(tm.Base):
    def test_a_page_with_a_study_card_never_says_with_it(self):
        lid = self.lessons.propose("Water bed 1 twice and ask for a landmark.", ["seedling"], source=STUDY, sources=[],
                                   now=NOW)
        self.report("waterer", NOW, cards=[tm.card(lid, 0.97, 81, 42, 60, 12)])
        page = body(self.page())
        self.assertIn(f'id="c{lid}"', page)
        self.assertNotRegex(page, r"\bwith(out)? it\b")
        for case_id in ("bed1", "bed2", "bed3"):
            self.assertNotIn(case_id, page)
        self.assertIn('<b class="num">42<small>of</small>81</b><span>landmark not asked</span>', page)
        self.assertIn('<b class="num">12<small>of</small>60</b><span>landmark asked</span>', page)
        self.assertIn("landmark not asked: 42 of 81 ended grew; landmark asked: 12 of 60", page)  # the Source line

    def test_an_adapted_card_names_the_result_its_counts_ended_in(self):
        lid = self.lessons.propose("Water bed 1 twice before noon.", ["seedling"], source=ADAPTED, sources=[], now=NOW)
        self.report("waterer", NOW, cards=[tm.card(lid, 0.88, 9, 5, 8, 2)])  # the card's own result is grew
        page = body(self.page())
        self.assertIn('<span class="lab">Ended cooled, night study</span>', page)
        self.assertIn("in 100 cases ending cooled;", page)
        self.assertNotIn("Ended grew", page)
        self.assertNotIn("fan7", page)


if __name__ == "__main__":
    unittest.main()
