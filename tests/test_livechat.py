"""The live chats of a running Arena run (Mohamed 2026-11-05: "i need to see the live chats happening even the
losing ones so i can correct with hotfix"): match play's on_turn hook (arena/match.py and arena/practice.py),
the live file per playing match (arena/live.py), removed when the match is saved or dropped, Morning.arena_so_far
handing them, the tiles with the chat and Correct this, and the poll that never wipes a correction being typed.
Every agent: the Sales agent's run and a built agent's practice alike. Fake models only; every text is made up."""
import json
import os
import unittest
from unittest import mock

from arena import live, match, practice, run
from reflection import console, morning as mo, page_css, pages
from tests.fake_model import Buyer, Seller
from tests.test_arena_match import CARD, checker
from tests.test_arena_run import Agent as tap_agent, Base as RunBase, Customer, card
import tests.test_arena_practice as tap
import tests.test_any_agent as taa  # the module, never its classes: their tests would run here twice

RUN = "20261105T120000"


class Hook(unittest.TestCase):
    def setUp(self):
        from tests.fake_model import clean_env
        clean_env(self)

    def test_on_turn_is_called_after_each_turn_with_the_turns_so_far(self):
        seen = []
        m = match.play(CARD, agent_model=Seller(), customer_model=Buyer(), checker=checker,
                       on_turn=lambda turns: seen.append([t["customer"] for t in turns]))
        self.assertEqual(len(seen), len(m["turns"]))
        self.assertEqual(seen, [[t["customer"] for t in m["turns"][:k]] for k in range(1, len(m["turns"]) + 1)])

    def test_an_on_turn_that_raises_never_changes_the_match(self):
        def boom(turns):
            raise RuntimeError("live view broke")
        plain = match.play(CARD, agent_model=Seller(), customer_model=Buyer(), checker=checker)
        hooked = match.play(CARD, agent_model=Seller(), customer_model=Buyer(), checker=checker, on_turn=boom)
        self.assertEqual(json.dumps(hooked, sort_keys=True), json.dumps(plain, sort_keys=True))

    def test_on_turn_gets_a_copy_so_it_cannot_cut_the_match(self):
        def cut(turns):
            turns.clear()
        m = match.play(CARD, agent_model=Seller(), customer_model=Buyer(), checker=checker, on_turn=cut)
        self.assertTrue(m["turns"])


class LiveFile(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_watch_writes_whole_files_and_removes_them(self):
        w = live.Watch(self.dir, f"{RUN}-r1-t01", card(1, "size")).start()
        p = self.dir / live.LIVE_DIR / f"{RUN}-r1-t01.json"
        self.assertEqual(json.loads(p.read_text())["status"], "playing")
        w([{"n": 1, "customer": "hi", "replies": ["hello"]}])
        got = live.read(self.dir)
        self.assertEqual([(x["id"], x["status"], len(x["turns"])) for x in got], [(f"{RUN}-r1-t01", "playing", 1)])
        self.assertEqual(got[0]["who"], live.WHO)
        self.assertIn("size", got[0]["about"])
        self.assertNotIn("persona-01", json.dumps(got))  # the card's id is never shown
        self.assertEqual([n for n in os.listdir(p.parent) if n.startswith(".")], [])  # no temp file left
        w.finish(False, "it guessed")
        self.assertEqual((live.read(self.dir)[0]["status"], live.read(self.dir)[0]["won"]), ("finished", False))
        w.remove()
        self.assertEqual(live.read(self.dir), [])

    def test_a_bad_id_writes_nothing_and_a_stale_file_is_not_read(self):
        live.Watch(self.dir, "../x", card(1, "size")).start()
        self.assertFalse((self.dir / live.LIVE_DIR).exists() and os.listdir(self.dir / live.LIVE_DIR))
        live.Watch(self.dir, f"{RUN}-r1-t02", card(1, "size"), now=lambda: 1000.0).start()
        self.assertEqual(live.read(self.dir, now=1000.0 + live.STALE + 1), [])
        self.assertEqual(len(live.read(self.dir, now=1000.0 + 5)), 1)

    def test_a_write_that_fails_never_raises(self):
        with mock.patch.object(live, "_write", side_effect=OSError("disk full")):
            w = live.Watch(self.dir, f"{RUN}-r1-t01", card(1, "size")).start()
            w([{"n": 1}])
            w.finish(True)
        w.remove()


class SalesRun(RunBase):
    """The Sales agent's Arena (arena/run.py Arena): one live file per playing match, gone once saved."""

    def spy(self):
        writes, real = [], live._write

        def record(p, data):
            writes.append((p.name, data["status"], len(data["turns"])))
            return real(p, data)
        return writes, mock.patch.object(live, "_write", record)

    def test_every_match_writes_its_turns_live_and_leaves_no_file(self):
        writes, patch = self.spy()
        with patch, mock.patch.object(run, "PARALLEL", 1):
            rep = self.arena([card(1, "size"), card(2, "price")], Customer(), matches=2, rounds=1).run()
        self.assertTrue(rep["rounds"])
        names = {n for n, _, _ in writes}
        self.assertGreaterEqual(len(names), 2)
        self.assertTrue(any(k > 0 for _, s, k in writes if s == "playing"))  # the chat turn by turn
        self.assertEqual(os.listdir(self.dir / live.LIVE_DIR), [])
        saved = [json.loads(x) for x in (self.dir / run.MATCHES_FILE).read_text().splitlines()]
        self.assertTrue(saved)
        self.assertFalse(any("status" in m for m in saved))  # the matches file is unchanged in shape

    def test_five_at_once_each_has_its_own_live_chat_and_none_is_left(self):
        writes, patch = self.spy()
        cards = [card(i, "size") for i in range(1, 6)]
        with patch, mock.patch.object(run, "PARALLEL", 5):
            run.Arena(cards, agent_model=tap_agent(), customer_model=Customer(), state=self.dir, matches=5, rounds=1,
                      calls=run.Calls(self.dir / "calls.json", 300, day="2026-10-30"),
                      trust={"matches": 5, "wins": 5, "zero_failed_checks": True}, now=lambda: 1_790_000_000.0).run()
        playing = {n for n, s, _ in writes if s == "playing" and "-t" in n}
        self.assertEqual(len(playing), 5)
        self.assertTrue(any(s == "finished" for _, s, _ in writes))  # judged, waiting to be folded in
        self.assertEqual(os.listdir(self.dir / live.LIVE_DIR), [])

    def test_the_live_file_goes_even_when_the_match_raises(self):
        a = self.arena([card(i, "size") for i in range(1, 4)], Customer(), matches=1, rounds=1)
        mid = f"{a.run_id}-r1-t01"

        def bad(self_, card_, match_id, *, on_turn=None, **kw):
            on_turn([{"n": 1, "customer": "hi", "replies": []}])
            self.assertTrue((self.dir / live.LIVE_DIR / f"{match_id}.json").exists())
            raise RuntimeError("the agent broke")
        with mock.patch.object(run.Arena, "_play_match", bad):
            with self.assertRaises(RuntimeError):
                a.play(card(1, "size"), mid)
        self.assertEqual(os.listdir(self.dir / live.LIVE_DIR), [])

    def test_a_dropped_match_and_the_ones_beside_it_leave_no_file(self):
        a = self.arena([card(i, "size") for i in range(1, 4)], Customer(), matches=3, rounds=1)

        def play(self_, card_, match_id, *, on_turn=None, **kw):
            on_turn([{"n": 1, "customer": "hi", "replies": ["hello"]}])
            if match_id.endswith("-t01"):
                return None  # the cap: dropped
            return ({"id": match_id}, {"won": False, "why": "it guessed"})
        jobs = [(card(i, "size"), f"{a.run_id}-r1-t0{i}", {}) for i in range(1, 4)]
        with mock.patch.object(run.Arena, "_play_match", play):
            out = a._together(jobs)
        self.assertEqual(out, [None])
        self.assertEqual(os.listdir(self.dir / live.LIVE_DIR), [])


class BuiltAgent(tap.Base):
    """A built agent's practice (arena/practice.py Practice) writes the same live chat."""

    def test_practice_matches_write_turns_live_and_leave_no_file(self):
        writes, real = [], live._write

        def record(p, data):
            writes.append((p.name, data["status"], [t.get("customer") for t in data["turns"]]))
            return real(p, data)
        self.assertNotIn("play", vars(practice.Practice))  # it plays through run.Arena.play, the live wrapper
        with mock.patch.object(live, "_write", record):
            code, rep = self.main("--matches", "2", "--json")
        self.assertEqual(code, 0, self.err)
        self.assertTrue(any(c == [tap.OPENING] for _, s, c in writes if s == "playing"))
        self.assertEqual(os.listdir(self.folder / live.LIVE_DIR), [])

    def test_practice_play_calls_on_turn_each_turn(self):
        from kit import turn
        self.main("--quick")
        agent = turn.load(self.folder)
        from arena import madeup
        c = madeup.read(self.folder / madeup.FOLDER, agent.name, agent.card)[0]
        seen = []
        world = tap.World()
        m = practice.play(agent, c, agent_model=world, customer_model=world, on_turn=lambda t: seen.append(len(t)))
        self.assertEqual(seen, list(range(1, len(m["turns"]) + 1)))


def tile_data():
    return {"played": 2, "won": 1, "live": [
        {"id": f"{RUN}-r1-t03", "who": "Practice case", "about": "Made up for the Arena, worry: size",
         "status": "playing", "turns": [{"n": 1, "customer": "<script>alert(1)</script> عايز مقاس 43",
                                          "replies": ["Size 43 is <b>in</b> stock."]}]}],
        "rows": [
            {"id": f"{RUN}-r1-t02", "won": False, "why": "it guessed the stock", "who": "Practice case",
             "about": "Made up for the Arena", "turns": [{"n": 1, "customer": "Is it in stock?", "replies": []}]},
            {"id": f"{RUN}-r1-t01", "won": True, "why": "a clear answer", "who": "Practice case",
             "about": "Made up for the Arena", "turns": [{"n": 1, "customer": "Price?", "replies": ["900 EGP."]}]}]}


class Tiles(unittest.TestCase):
    def ctx(self):
        return {"token": "t", "path": "/agents/stock_watch", "q": "?tab=arena"}

    def test_playing_on_top_then_lost_open_and_won_closed_all_escaped(self):
        html = pages.so_far_tiles(tile_data(), "stock_watch", self.ctx())
        order = [html.index(f'data-match="{RUN}-r1-t0{k}"') for k in (3, 2, 1)]
        self.assertEqual(order, sorted(order))  # playing first, then newest first
        self.assertIn(pages.PLAYING_BADGE, html)
        self.assertIn('<article class="tile live"', html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; عايز مقاس 43", html)
        self.assertIn("Size 43 is &lt;b&gt;in&lt;/b&gt; stock.", html)
        self.assertIn('<p class="said me" dir="auto">', html)
        self.assertIn('<p class="said ag" dir="auto">', html)
        self.assertIn(f'<details class="lc" data-chat="{RUN}-r1-t02" open>', html)  # lost: open
        self.assertIn(f'<details class="lc" data-chat="{RUN}-r1-t01">', html)  # won: closed
        self.assertIn('<p class="said nil">No reply', html)  # .no is the round button's class
        self.assertNotIn("—", html)
        self.assertNotIn("–", html)

    def test_every_tile_has_correct_this_to_the_page_correction_with_the_match_as_context(self):
        html = pages.so_far_tiles(tile_data(), "stock_watch", self.ctx())
        self.assertEqual(html.count('action="/correct"'), 3)
        for k in (1, 2, 3):
            mid = f"{RUN}-r1-t0{k}"
            self.assertIn(f'<details class="fix" data-keep="{mid}">', html)
            self.assertIn(f'<input type="hidden" name="match" value="{mid}">', html)
        self.assertIn('<input type="hidden" name="agent" value="stock_watch">', html)
        self.assertIn('name="line"', html)
        # with no token (a read only view) there is no form
        self.assertNotIn("<form", pages.so_far_tiles(tile_data(), "stock_watch", None))

    def test_the_correction_handler_is_the_page_box_one_and_ignores_the_match(self):
        seen = []
        m = mock.Mock()
        m.correct = lambda agent, line, now=None: seen.append((agent, line)) or "ok"
        mo.ACTIONS["/correct"](m, {"agent": ["stock_watch"], "line": ["Say the stock first"],
                                   "match": [f"{RUN}-r1-t02"]})
        self.assertEqual(seen, [("stock_watch", "Say the stock first")])

    def test_bubbles_have_the_page_chat_look(self):
        for rule in (".lc .said.me{", ".lc .said.ag{", ".lc .thread{"):
            self.assertIn(rule, page_css.CSS)


class Poll(unittest.TestCase):
    def test_the_poll_keeps_an_open_or_typed_correction_and_the_chat_folds(self):
        s = pages.ARENA_SCRIPT
        self.assertIn("swap(el,n)", s)
        self.assertNotIn("el.innerHTML=n.innerHTML;if", s)  # never a plain swap
        self.assertIn("querySelectorAll('[data-keep]')", s)
        self.assertIn("t.value", s)  # text typed
        self.assertIn("o.open", s)  # Correct this opened
        self.assertIn("document.activeElement", s)  # the focus
        self.assertIn("replaceWith(keep[j])", s)  # the very same node, typed text and all, goes back
        self.assertIn("details[data-chat]", s)
        self.assertIn(pages._sha(s), pages.AGENT_CSP)  # the policy allows this script

    def test_the_script_runs_in_node_and_keeps_the_typed_text(self):
        import shutil
        import subprocess
        if shutil.which("node") is None:
            self.skipTest("no node here")
        # a tiny DOM: enough of querySelectorAll, getAttribute and replaceWith for swap()
        src = pages.ARENA_SCRIPT
        body = src[src.index("function byKey"):src.index("function poll")]
        js = DOM_JS + body + """
var old=new El('div');var keep=new El('details');keep.attrs['data-keep']='m1';keep.open=true;
var ta=new El('textarea');ta.value='typed by hand';keep.kids.push(ta);old.kids.push(keep);
var chat=new El('details');chat.attrs['data-chat']='m2';chat.open=false;old.kids.push(chat);
var fresh=new El('div');var nk=new El('details');nk.attrs['data-keep']='m1';var nt=new El('textarea');nt.value='';
nk.kids.push(nt);fresh.kids.push(nk);var nc=new El('details');nc.attrs['data-chat']='m2';nc.open=true;fresh.kids.push(nc);
old.setNew(fresh);swap(old,fresh);
var k=byKey(old,'data-keep','m1');var c=byKey(old,'data-chat','m2');
console.log(JSON.stringify({text:k.querySelector('textarea').value,same:k===keep,chat:c.open}));
"""
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), {"text": "typed by hand", "same": True, "chat": False})


DOM_JS = """
var document={activeElement:null};
function El(tag){this.tag=tag;this.attrs={};this.kids=[];this.open=false;this.value='';this.parent=null}
El.prototype.all=function(){var r=[];this.kids.forEach(function(k){r.push(k);r=r.concat(k.all())});return r};
El.prototype.matches=function(s){var m=s.match(/^(\\w+)?\\[([\\w-]+)\\]$/);if(m)return(!m[1]||m[1]===this.tag)&&(m[2] in this.attrs);
if(s[0]==='.')return false;return this.tag===s};
El.prototype.querySelectorAll=function(s){return this.all().filter(function(e){return e.matches(s)})};
El.prototype.querySelector=function(s){return this.querySelectorAll(s)[0]||null};
El.prototype.getAttribute=function(a){return a in this.attrs?this.attrs[a]:null};
El.prototype.contains=function(x){return x!==null&&(x===this||this.all().indexOf(x)>=0)};
El.prototype.appendChild=function(x){this.kids.push(x)};
El.prototype.setNew=function(f){var self=this;Object.defineProperty(this,'innerHTML',{set:function(){self.kids=f.kids.slice();
self.all().forEach(function(k){k.kids.forEach(function(c){c.parent=k})});self.kids.forEach(function(c){c.parent=self})}})};
El.prototype.replaceWith=function(x){var p=this.parent,i=p.kids.indexOf(this);p.kids[i]=x;x.parent=p};
"""


class SoFar(unittest.TestCase):
    """Morning.arena_so_far hands the playing matches of the running run and each saved row's chat."""

    def setUp(self):
        taa.RunTheArena.setUp(self)

    tab = taa.RunTheArena.tab

    def add(self, *rows):
        with open(self.folder / run.MATCHES_FILE, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    def test_playing_matches_and_saved_rows_with_their_chat(self):
        self.m.run_arena("stock_watch", full=True)
        w = live.Watch(self.folder, f"{RUN}-r1-t02", {"worry": "the size", "want": ["a boot"]}).start()
        w([{"n": 1, "customer": "Is 43 in stock?", "replies": ["Yes, 43 is in stock."]}])
        live.Watch(self.folder, f"{RUN}-r1-t01", {}).start()  # saved below: never twice
        self.add({"id": f"{RUN}-r1-t01", "won": False, "why": "it guessed", "persona": {"worry": "price"},
                  "turns": [{"n": 1, "customer": "Price?", "replies": ["Maybe 900."]}]})
        got = self.m.arena_so_far("stock_watch")
        self.assertEqual([x["id"] for x in got["live"]], [f"{RUN}-r1-t02"])
        self.assertEqual(got["live"][0]["turns"][0]["replies"], ["Yes, 43 is in stock."])
        self.assertEqual(got["rows"][0]["turns"][0]["customer"], "Price?")
        self.assertIn("price", got["rows"][0]["about"])
        page = self.tab()
        tiles = page.split('<div class="tiles">')[1]
        self.assertIn(pages.PLAYING_BADGE, tiles)
        self.assertIn("Yes, 43 is in stock.", tiles)
        self.assertIn("Maybe 900.", tiles)
        self.assertIn('data-live="tiles" data-running', page)  # the poll refreshes these tiles
        self.assertIn(f'data-keep="{RUN}-r1-t02"', tiles)
        self.assertIn('action="/correct"', tiles)
        # the page's own box stays outside the swapped part
        self.assertNotIn('id="say"', page.split('data-live="tiles"')[1].split('class="ar-r"')[0])

    def test_the_console_shows_each_playing_match_latest_turn(self):
        self.m.run_arena("stock_watch", full=True)
        w = live.Watch(self.folder, f"{RUN}-r1-t02", {}).start()
        w([{"n": 1, "customer": "Hi", "replies": ["Hello"]}, {"n": 2, "customer": "Is 43 in stock?",
                                                               "replies": ["Yes, 43 is in stock."]}])
        out, rec = {}, mock.Mock()
        console._so_far(self.m, "stock_watch", out, rec)
        self.assertEqual(out["playing"][0]["last"], "turn 2: customer: Is 43 in stock? | agent: Yes, 43 is in stock.")
        self.assertEqual(console.latest_turn([]), "first line on the way")


if __name__ == "__main__":
    unittest.main()
