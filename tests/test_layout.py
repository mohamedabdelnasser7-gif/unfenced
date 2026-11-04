"""The agent page layout (2026-11-05): the Arena tab as one two column grid, the track's equal steps, the line
under it with Open the chat on its own, the action rows stacked (the line, the button, the note under it) on the
Arena tab and on the Overview, and the dark card saying what a running run did so far. Markup and the style's
own rules only; fake models, no network."""
import unittest
from unittest import mock

from reflection import morning as mo, pages
from reflection.page_css import CSS
from tests.test_assistant_arena_page import ARENA_TAB, Base

OVERVIEW = {"tab": ["overview"]}
SO_FAR = {"played": 3, "won": 2, "rows": [{"won": True, "why": "it kept the draft"}, {"won": False, "why": "it said sent"},
                                          {"won": True, "why": "a clear answer"}]}


def part(page, start, end):
    return page.split(start, 1)[1].split(end, 1)[0]


class Running(Base):
    def running(self):
        return (mock.patch.object(self.m, "arena_running", lambda a: True),
                mock.patch.object(self.m, "arena_so_far", lambda a: SO_FAR),
                mock.patch.object(self.m, "arena_played", lambda a: 3))


class ArenaGrid(Running):
    def test_main_column_holds_the_box_and_the_matches_and_the_side_the_level_and_the_dark_card(self):
        page = self.page()
        grid = page.split('<div class="arg">', 1)[1]
        self.assertLess(grid.index('<div class="arg-c">'), grid.index('<div class="arg-m"'))
        self.assertLess(grid.index('<div class="arg-m"'), grid.index('<div class="arg-s"'))
        self.assertIn('aria-label="Send an idea or a correction"', part(grid, '<div class="arg-c">', '<div class="arg-m"'))
        main = part(grid, '<div class="arg-m"', '<div class="arg-s"')
        self.assertIn('<h2 id="m-h">Practice matches</h2><small>Where it slipped</small>', main)
        side = grid.split('<div class="arg-s"', 1)[1]
        self.assertLess(side.index('class="grp sq lvc"'), side.index('class="a-climb"'))
        self.assertNotIn('<div class="ar">', page)  # no second grid around the box

    def test_the_style_starts_both_columns_on_one_line_and_stacks_them_on_a_phone(self):
        wide = CSS.split(".arg{grid-template-columns:minmax(0,8fr) minmax(0,4fr)", 1)[1].split("}", 1)[0]
        self.assertIn('grid-template-areas:"c s" "m s"', wide)
        self.assertIn("grid-template-rows:auto 1fr", wide)
        self.assertIn('.arg{display:grid; grid-template-columns:minmax(0,1fr); grid-template-areas:"c" "s" "m"', CSS)
        self.assertIn(".arg .tiles > .ghost{grid-column:1 / -1}", CSS)  # the empty tile spans the row
        self.assertIn(".arg .sec-h{justify-content:flex-start", CSS)  # Where it slipped beside the heading

    def test_the_side_column_is_swapped_by_the_poll_while_a_run_goes(self):
        a, b, c = self.running()
        with a, b, c:
            page = self.page()
        self.assertIn('<div class="arg-s" data-live="side" data-running>', page)
        self.assertIn('<div class="arg-m" data-live="tiles" data-running>', page)
        self.assertIn('<div class="arg-s" data-live="side">', self.page())


class DarkCard(Running):
    def glow(self, page):
        return part(page, 'class="a-climb"', "</section>")

    def test_it_says_the_old_line_only_with_nothing_running_and_nothing_saved(self):
        self.assertIn('<p class="calm">No saved run yet. Nothing to do here while it practises.</p>',
                      self.glow(self.page()))

    def test_while_a_run_plays_it_says_how_many_it_played_and_won(self):
        a, b, c = self.running()
        with a, b, c:
            glow = self.glow(self.page())
        self.assertIn('<p class="calm">Practising now: 3 played, 2 won so far.</p>', glow)
        self.assertNotIn("No saved run yet", glow)
        self.assertNotIn("Nothing to do here", glow)

    def test_with_no_match_landed_yet_it_says_the_first_ones_are_starting(self):
        self.assertEqual(pages.practising_line({"played": 0, "won": 0}),
                         "Practising now: its first matches are starting.")
        self.assertEqual(pages.practising_line(None), "Practising now: its first matches are starting.")
        self.assertEqual(pages.practising_line({"played": 1, "won": 0}), "Practising now: 1 played, 0 won so far.")


class Track(Base):
    def test_every_step_has_the_same_markup_and_only_the_next_one_is_marked(self):
        track = part(self.page(), '<ol class="trk"', "</ol>")
        steps = track.split("<li")[1:]
        self.assertEqual(len(steps), 3)
        for s in steps:
            self.assertIn('<span class="n" aria-hidden="true">', s)
            self.assertIn('<span class="w">', s)
        self.assertEqual(sum(s.startswith(' class="next"') for s in steps), 1)

    def test_the_style_gives_no_step_a_pill_and_even_connectors(self):
        rule = CSS.split(".trk li,.trk li.next,.trk li.done,.trk li.soon{", 1)[1].split("}", 1)[0]
        for bit in ("padding:0", "background:none", "box-shadow:none", "border-radius:0"):
            self.assertIn(bit, rule)
        self.assertIn(".trk li.next{font-weight:600", CSS)
        self.assertIn(".trk li + li::before{width:28px; margin:0 4px 0 0}", CSS)
        self.assertIn(".trk{gap:10px 12px}", CSS)  # 12px before each line, 4px plus the 8px gap after it
        phone = CSS.split("@media (max-width: 599px){\n  .trk{", 1)[1].split("\n}", 1)[0]
        self.assertIn("grid-auto-columns:minmax(0,1fr)", phone)  # equal columns on a phone

    def test_the_line_under_it_is_a_short_paragraph_with_open_the_chat_on_its_own(self):
        page = self.page()
        line = part(page, '<p class="trkc">', "</p>")
        self.assertNotIn("Open the chat", line)
        self.assertIn('<p class="trkl"><a class="lk" href="/agents/assistant?tab=live">Open the chat</a></p>', page)
        self.assertIn(".trkc{max-width:65ch", CSS)


class Stacked(Base):
    def act(self, page, after):
        return part(page.split(after, 1)[1], '<div class="act stk">', "</div>")

    def assert_order(self, row, *bits):
        at = [row.index(b) for b in bits]
        self.assertEqual(at, sorted(at), row)

    def test_run_the_arena_on_the_arena_tab_is_the_line_then_the_button_then_the_note(self):
        row = self.act(self.page(), '<ol class="trk"')
        self.assert_order(row, '<p class="quiet">', 'type="submit"', '<p class="quiet nt">')
        self.assertIn(h_(mo.ARENA_RUN_NO_CHANNEL), row.split('<p class="quiet nt">', 1)[1])

    def test_the_arena_card_on_the_overview_is_stacked_the_same_way(self):
        row = self.act(self.page(OVERVIEW), 'id="ra-h"')
        self.assert_order(row, '<p class="quiet">', 'type="submit"', '<p class="quiet nt">')

    def test_reflection_is_the_line_then_the_button_then_the_reason(self):
        row = self.act(self.page(OVERVIEW), 'id="rf-h"')
        self.assert_order(row, h_(mo.REFLECT_SAID), mo.REFLECT_BUTTON, '<p class="no-yet" role="status">')
        self.assertIn('</button><p class="no-yet" role="status">', row)  # the reason right under the button

    def test_the_style_stacks_them_left_at_a_readable_width(self):
        rule = CSS.split(".act.stk{", 1)[1].split("}", 1)[0]
        for bit in ("flex-direction:column", "flex-wrap:nowrap", "align-items:flex-start", "max-width:65ch"):
            self.assertIn(bit, rule)
        self.assertIn(".act.stk .nt,.act.stk > button.yes + .no-yet{margin:0; padding:0;", CSS)


class Head(unittest.TestCase):
    def test_the_head_keeps_clear_of_the_sticky_bar(self):
        wide = CSS.split("@media (min-width: 1024px){\n  html{scroll-padding-top:104px}", 1)
        self.assertEqual(len(wide), 2)
        self.assertIn(".ahead{scroll-margin-top:104px}", wide[1].split("\n}", 1)[0])


def h_(text):
    return pages.h(text)


if __name__ == "__main__":
    unittest.main()
