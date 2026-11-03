"""The two tab page, Today and Agents (LOCKS.md "Product shape: two tabs" and "Today and agent
page: A"), served by reflection/morning.py. It draws from Morning.view() and answers through the
Morning methods only, so no engine rule lives here.

    /              Today: only what needs the user's yes, one light sage card each, then at most two
                   lines per agent about last night, the most important first (the same agents the
                   Agents tab lists); an empty state when nothing waits (DECISIONS 35). Under the
                   cards, the cases waiting on a result only a person can bring, with a button per
                   result and a sheet upload (reflection/morning.py, Late results; DECISIONS 66).
    /agents        the agents (the plugs in the repo and the agents in the database) and New agent.
                   An agent shows Live while the user has it connected on a channel (Morning._live,
                   DECISIONS item 77), else Training; real chats are history, never the switch.
    /agents/<name> one agent: its status with Pull and Roll back, then Connections: each channel it
                   asks for with one line, and Connect to WhatsApp, greyed out with the reason until
                   its latest Arena gate passed (Morning.gate). Pull takes a live agent off its
                   channels; an agent no channel runs keeps Pull as the pause switch, Resume when
                   paused. Then the box for an idea or a correction (Morning.correct, a hotfix), its
                   lessons and Reflection notes as rows.
    /agents/<name>/rollback  what Roll back would do, lesson by lesson, and its one button.
    /new           New agent, the build page (LOCKS "App pages", 2A): a centred thread with the box pinned
                   at the bottom; the Quick start chat (reflection/quickstart.py), its card, at most one
                   question and the second message, Build; then the build's steps ticking off and Go to
                   the Arena with a countdown that Stay here stops. A message sent while it builds
                   changes the card before its files are written, and is a correction through the exam
                   after (Pages._say); it never starts a new agent.
    /new/build     screen 2: the newest Arena run saved next to the database, as tiles and a path. When
                   it lost matches, Try again plays only those again with the corrections that passed
                   (Morning.try_again, arena/retry.py); each retried tile then says Won again or Still lost.

A correction sent on an agent's page that is high risk waits for a yes on Today (Morning.correct); its
card says why in one plain sentence (plain_risk), never the engine's word lists, and the Hotfix chip
marks a correction that runs in the chats. With demo days each day shows its own morning (day.json); with --db too a Live tab follows the days and
serves the real database with real answers and the real clock, never marked Sample data.

No count of what is left anywhere (item 35), no trust level and no won and lost total (item 17,
LOCKS Quick start B). No script, except the build page's one hashed script (NEW_SCRIPT, its poll and
countdown) and, on the page of an agent made here, Run the Arena's poll (ARENA_SCRIPT): Modify is a details element inside its card. Every field is
escaped. With demo days (--demo-days) a Day 1, Day 2, Day 3 switch sits on top, marked Sample
data (Sample on the phone bar, so every label stays on one line at 390); each day is its own throwaway copy, so answers there never touch the sample files.
"""
import base64
import hashlib
import re
import threading
import time
import urllib.parse

from engine import lessons as lessons_mod
from kit import sample as sample_mod
from reflection import console as console_mod
from reflection import morning as mo
from reflection import quickstart as qs_mod
from reflection import snapshots
from reflection import try_sales as try_mod
from reflection.page_css import CSS

CSP = ("default-src 'none'; style-src 'sha256-" + base64.b64encode(hashlib.sha256(CSS.encode("utf-8")).digest()).decode()
       + "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
h = mo.h
NAMES = mo.AGENT_NAMES
CORRECTED = lessons_mod.HOTFIX_SOURCE  # the source line of a correction (Morning.correct, Lessons.correct)
_AGENT = re.compile(r"^[a-z][a-z_]{0,30}$")
ROLLBACK = "/rollback"  # /agents/<name>/rollback: the plan a rollback would carry out, and its one button
# The build page's one script (LOCKS "App pages", 2A), allowed by its hash in the /new policy only: while a
# build runs it fetches the page again with the X-Poll header (the console's way, so the one-time
# message stays) and swaps the thread; when the build is done it runs the countdown to the Arena, which
# Stay here stops; Enter sends the box.
NEW_SCRIPT = """(function(){
var T=1500;function q(d,s){return d.querySelector(s)}
function count(){var g=q(document,'[data-count]'),go=q(document,'[data-go]');if(!g||!go)return;var n=+g.textContent||5,t,stay=q(document,'[data-stay]');
function tick(){g.textContent=n;var fg=q(document,'.ring .fg');if(fg)fg.style.strokeDashoffset=(56.5*n/5).toFixed(1);if(n<=0){location.href=go.href;return}n--;t=setTimeout(tick,1000)}
if(stay)stay.addEventListener('click',function(){clearTimeout(t);var a=q(document,'.auto');if(a)a.remove();stay.remove()});tick()}
function poll(){var th=q(document,'[data-live="thread"]');if(!th||!th.hasAttribute('data-building'))return;
fetch(location.href,{headers:{'X-Poll':'1'},credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.text():null}).then(function(t){if(!t)return;
var d=new DOMParser().parseFromString(t,'text/html'),n=q(d,'[data-live="thread"]');if(!n)return;th.innerHTML=n.innerHTML;
var a=q(d,'.dock textarea'),b=q(document,'.dock textarea');if(a&&b)b.placeholder=a.placeholder;
if(!n.hasAttribute('data-building')){th.removeAttribute('data-building');var o=q(d,'.dock form[action="/quickstart/clear"]'),k=q(document,'.dock');if(o&&k&&!q(k,'form[action="/quickstart/clear"]'))k.appendChild(document.importNode(o,true));count()}window.scrollTo(0,document.body.scrollHeight)}).catch(function(){}).then(function(){
var x=q(document,'[data-live="thread"]');if(x&&x.hasAttribute('data-building'))setTimeout(poll,T)})}
var ta=q(document,'.dock textarea')||q(document,'.hero textarea');if(ta)ta.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&ta.value.trim()){e.preventDefault();ta.form.requestSubmit()}});
if(q(document,'[data-live="thread"]'))window.scrollTo(0,document.body.scrollHeight);setTimeout(poll,T);count()})();"""


# The agent page's one script (Run the Arena), allowed by its hash in the /agents/<name> policy only: while
# a run goes it fetches the page again with the X-Poll header, as the build page does, and swaps the part
# marked data-live="arena" until the run is over; when that part is gone (Overview once a run is saved),
# it loads the page again.
ARENA_SCRIPT = """(function(){
var T=2000;function q(d,s){return d.querySelector(s)}
function poll(){var el=q(document,'[data-live="arena"][data-running]');if(!el)return;
fetch(location.href,{headers:{'X-Poll':'1'},credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.text():null}).then(function(t){if(!t)return;
var n=q(new DOMParser().parseFromString(t,'text/html'),'[data-live="arena"]');if(!n){location.reload();return}
el.innerHTML=n.innerHTML;if(!n.hasAttribute('data-running'))el.removeAttribute('data-running')}).catch(function(){}).then(function(){
if(q(document,'[data-live="arena"][data-running]'))setTimeout(poll,T)})}
setTimeout(poll,T)})();"""


def _sha(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


NEW_CSP = (f"default-src 'none'; style-src 'sha256-{_sha(CSS)}'; script-src 'sha256-{_sha(NEW_SCRIPT)}'; "
           "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
AGENT_CSP = (f"default-src 'none'; style-src 'sha256-{_sha(CSS)}'; script-src 'sha256-{_sha(ARENA_SCRIPT)}'; "
             "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

# The build's steps as the thread ticks them off: (while it runs, once done). Page words.
BUILD_STEPS = (("card", "Reading the card", "Card read"), ("plug", "Writing the plug", "Plug written and checked"),
               ("exam", "Writing the exam", "Exam written"), ("files", "Saving its files", "Files saved"),
               ("data", "Making sample data", "Sample data"),
               ("ready", "Getting ready", "Ready for the Arena"))
COUNTDOWN = 5     # seconds before Go to the Arena opens by itself
FRESH = 20        # seconds after a build ends that a page still starts the countdown


class BuildRun:
    """One Build on the page (Pages._build): which steps are done, what went wrong, the messages taken
    in while it ran. The build thread writes only here and the agent's folder; the page's Morning is
    touched on the server's own thread (Pages.settle)."""

    def __init__(self, m):
        self.m = m
        self.lock = threading.Lock()  # held by a card change and by the files being written
        self.done = {}                # step: its detail line
        self.again = 0
        self.taken = []               # {"said", "kind": "card" or "correction", "answer"}
        self.error = self.said = self.agent = None
        self.joined = False
        self.join_note = None         # the line when the built agent could not join the running page
        self.base = 0                 # the chat's turns when Build was pressed; later ones came in during it
        self.ended = None

    def step(self, name, detail=""):
        if name == "again":  # the card changed meanwhile: its plug and exam are written again
            self.again += 1
            self.done.pop("plug", None)
            self.done.pop("exam", None)
            return
        if name == "files":
            self.agent = detail
        self.done[name] = detail

    @property
    def running(self):
        return self.ended is None

    @property
    def written(self):
        return "files" in self.done


_BACK = re.compile(r"^/(?:agents(?:/[a-z][a-z_]{0,30})?|new(?:/build)?|console)?$")
ICON = dict(mo.ICONS, pen='<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
            loop='<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
            undo='<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>', pause='<path d="M9 6v12M15 6v12"/>',
            check='<path d="M5 12.5l4.5 4.5L19 7.5"/>', arrow='<path d="M5 12h14M13 6l6 6-6 6"/>',
            back='<path d="M15 6l-6 6 6 6"/>', note='<path d="M6 4h12v16H6z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
            plus='<path d="M12 6v12M6 12h12"/>', code='<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>',
            up='<path d="M12 19V5M6 11l6-6 6 6"/>')


# The high risk reasons in plain words, by the risk list group the code check saved (engine/risk.py):
# a person reads why the card waits, never the engine's word lists.
PLAIN_RISK = {"number": "it talks about a number, like a price, a size or a delivery time",
              "money": "it talks about money", "spend": "it talks about spending money",
              "promise": "it makes a promise to the customer", "policy": "it touches store policy",
              "personal_data": "it touches someone's personal data", "other_brands": "it names other brands",
              "goes_out": "it sends something out in your name", "calendar": "it changes your calendar",
              "tool": "it tells the agent how to use one of its tools", "link": "it has a link in it",
              "phone number": "it has a phone number in it", "handle": "it has an account handle in it",
              "copied": "it copies words from the chats it came from", "judge": "the risk check marked it high"}


def plain_risk(risk_why):
    """Why a high risk card waits, as one plain sentence; at most two reasons, the first ones found."""
    keys = []
    for part in str(risk_why or "").split("; "):
        group, sep, mark = part.partition(": ")
        if group == "core" and mark.startswith("copied"):
            key = "copied"
        elif group == "core":
            key = mark
        elif group.startswith("judge"):
            key = "judge"
        else:
            key = group if sep else ""
        if key in PLAIN_RISK and key not in keys:
            keys.append(key)
    said = [PLAIN_RISK[k] for k in keys[:2]] or [PLAIN_RISK["judge"]]
    return f"It waits for your yes because {' and '.join(said)}."


def name(agent):
    return mo.name_of(agent)


def icon(n, cls="i"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true">{ICON[n]}</svg>'


class Pages:
    """The page for one Morning, or for demo days {1: Morning, 2: ..., 3: ...} (sample copies), with
    live: the Morning on the real database, a Live tab after the days (no Sample data label there)."""

    LIVE = "live"

    def __init__(self, morning=None, *, days=None, at=None, live=None, model=None, try_model=None, background=None):
        """at: {day: the time that day's page shows}, a sample's own clock; the real clock otherwise
        and always on Live. model: Quick start's model (a fake in tests); None uses kit.model.
        try_model: Try Sales's model (a fake in tests); None uses kit.model once a key is set."""
        self.days = dict(days or {})
        self.at = dict(at or {})
        self.live = live if self.days else None  # with no sample days the page has no switch
        self.demo = bool(self.days)
        self.morning = morning if morning is not None else (self.days[min(self.days)] if self.days else None)
        self.csp = CSP
        self.quick = qs_mod.QuickStart(model)
        # Build runs in a thread so the thread can tick its steps off; with a model handed in (a test's) it
        # runs inline unless background says otherwise
        self.background = (model is None) if background is None else bool(background)
        self.run = None
        self.try_sales = try_mod.TrySales(try_model)  # its own database in memory, never the page's
        # the page's own answers, taken by the server next to morning.TWO_TAB_ACTIONS
        self.actions = {"/quickstart": lambda m, f, now=None: self._say(m, mo._field(f, "text"), now),
                        "/quickstart/build": lambda m, f, now=None: self._build(m, now),
                        "/quickstart/clear": lambda m, f, now=None: self._clear(m, now),
                        # Try Sales on the Sales agent's page (reflection/try_sales.py): the demo store, never counts
                        "/try/sales": lambda m, f, now=None: self._try(self.try_sales.say, m, now, mo._field(f, "text")),
                        "/try/sales/clear": lambda m, f, now=None: self._try(self.try_sales.clear, m, now),
                        # the console's Operator correction: the same path as the agent page's (Morning.correct)
                        "/console/correct": lambda m, f, now=None: m.correct(mo._field(f, "agent"), mo._field(f, "line"),
                                                                             now=now, by=console_mod.OPERATOR),
                        # Run the Arena on an agent's page (Morning.run_arena), refused while it builds
                        ARENA_PATH: lambda m, f, now=None: self._arena(m, mo._field(f, "agent"), now)}

    def back(self, value):
        """Where an answer returns to: one of the page's own paths, with the demo day; else /."""
        parts = urllib.parse.urlsplit(str(value or ""))
        path = parts.path if _BACK.match(parts.path or "") and not parts.netloc and not parts.scheme else "/"
        query = urllib.parse.parse_qs(parts.query)
        keep = []
        agent = (query.get("agent") or [""])[0]
        if path == "/new/build" and _AGENT.match(agent):  # the Arena screen of that agent (Try again)
            keep.append(f"agent={agent}")
        tab = (query.get("tab") or [""])[0]
        if path.startswith("/agents/") and tab in TAB_KEYS and tab != "overview":  # the agent page's tab
            keep.append(f"tab={tab}")
        if path == "/console" and _AGENT.match(agent):  # the console, its view and the row that was open
            st = console_mod.state_of(query, agent)
            keep += [f"{k}={st[k]}" for k in ("agent", "view", "sub", "f", "row", "pane") if st[k]]
        if self.demo:
            keep.append(f"day={self._day(query)}")
        return path + ("?" + "&".join(keep) if keep else "")

    def land(self, to, back):
        """Where an answer that names its next page goes (Build: the Arena screen): to, checked as any
        back is, on the demo day back was on."""
        day = urllib.parse.parse_qs(urllib.parse.urlsplit(back).query).get("day")
        if self.demo and day:
            to += ("&" if "?" in to else "?") + "day=" + urllib.parse.quote(day[0])
        return self.back(to)

    def csp_for(self, path):
        """The policy a page is sent with: the console's own (its one script by hash), else the page's."""
        if path.startswith("/agents/") and _AGENT.match(path[8:]) and self.made_here(path[8:]):
            return AGENT_CSP  # the page of an agent made here: Run the Arena's poll
        return console_mod.csp() if path == "/console" else NEW_CSP if path == "/new" else self.csp

    def made_here(self, agent):
        """Is agent one Quick start made, on the page's own morning (its folder beside the database)? Only
        its page carries Run the Arena, so only its page is sent the policy that allows ARENA_SCRIPT."""
        for m in (self.morning, self.live):
            folder = getattr(m, "agent_folder", None)
            if folder is not None and folder(agent) is not None:
                return True
        return False

    def morning_for(self, back):
        if not self.demo:
            return self.morning
        return self._m(self._day(urllib.parse.parse_qs(urllib.parse.urlsplit(back).query)))

    def now_for(self, back):
        """The clock an answer runs on: a sample day's own morning (at), so what it adds is dated that
        day; None (the real clock) on Live and with no sample days."""
        if not self.demo:
            return None
        return self.at.get(self._day(urllib.parse.parse_qs(urllib.parse.urlsplit(back).query)))

    @staticmethod
    def _quick(step, m, now, *args):
        try:
            return step(m, *args, now=now)
        except qs_mod.Refused as e:
            raise mo.Refused(str(e)) from None

    @staticmethod
    def _try(step, m, now, *args):
        try:
            return step(m, *args, now=now)
        except try_mod.Refused as e:
            raise mo.Refused(str(e)) from None

    def _build(self, m, now):
        """Build (LOCKS "App pages", 2A): the cheap refusals at once, then the build in a thread whose
        steps the thread on /new ticks off; inline with a test's model, returning the flash as before.
        The new agent joins the running page (Morning.add_built) on the server's thread (settle)."""
        run = self.run
        if run is not None and run.m is m and run.running:
            raise mo.Refused("It is building already. The steps tick off below.")
        self._quick(lambda mm, now=None: self.quick.check_build(mm), m, now)
        run = self.run = BuildRun(m)
        run.base = len(self.quick.draft(m)["turns"])
        if self.background:
            threading.Thread(target=self._work, args=(run, now), name="quick-build", daemon=True).start()
            return None
        self._work(run, now)
        self.settle(m)
        if run.error:
            raise mo.Refused(run.error)
        return f"{run.said} {run.join_note}" if run.join_note else run.said

    def _work(self, run, now):
        """The build thread's work. Never raises: what went wrong becomes the run's error line."""
        try:
            run.said = self.quick.build(run.m, now, step=run.step, lock=run.lock)
        except qs_mod.Refused as e:
            run.error = str(e)
        except Exception as e:
            run.error = f"Not built: {' '.join(str(e).split())[:200] or type(e).__name__}. Press Build to try again."
        finally:
            run.ended = time.monotonic()

    def settle(self, m):
        """A built agent joins the running page once, on the server's thread, as soon as its files are
        written: its plug, Pull and exam with no restart, so a message sent then can be a correction.
        When that fails the agent is built already, so the line asks for a restart."""
        run = self.run
        if run is None or run.m is not m or not run.written or not run.agent or run.joined:
            return
        run.joined = True
        try:
            m.add_built()
            run.done["ready"] = ""
        except Exception as e:
            run.join_note = f"It could not join this page ({e}). Restart the page to see it."

    def _arena(self, m, agent, now):
        """Run the Arena (Morning.run_arena), refused while a build on this page may be writing the agent
        and while the short practice Build started for it still runs."""
        run = self.run
        if run is not None and run.m is m and run.running and run.agent in (None, agent):
            raise mo.Refused("It is building. Run the Arena once the build is done.")
        if self.quick.practising(agent):
            raise mo.Refused("Its first short practice is still running. Run the Arena once it ends.")
        if not hasattr(m, "run_arena"):
            raise mo.Refused(mo.ARENA_NOT_HERE)
        return m.run_arena(agent, now=now)

    def _say(self, m, text, now):
        """The box on the build page. Before the build writes its files, a message changes the card
        (QuickStart.say: the model writes the card again; the build takes it in before its files are
        written, at most MAX_CARD_CHANGES times). Once the agent is built, during the build or after it
        until Start over, it is a correction through the exam, the same path as Correct this
        (Morning.correct, by the user). A message sent during a build never starts a new agent."""
        self.settle(m)
        run = self.run if self.run is not None and self.run.m is m else None
        if run is not None and run.running and not run.written:
            with run.lock:  # the build waits for this change before it writes its files
                if not run.written:
                    if sum(t["kind"] == "card" for t in run.taken) >= qs_mod.MAX_CARD_CHANGES:
                        raise mo.Refused(f"It took {qs_mod.MAX_CARD_CHANGES} changes to the card while it builds, the "
                                         "most one build takes. Once it is built, send the rest here as corrections.")
                    self._quick(self.quick.say, m, now, text)
                    run.taken.append({"said": text, "kind": "card"})
                    return None
            self.settle(m)
        built = self.quick.draft(m)["built"] or (run.agent if run is not None and run.written else None)
        if run is not None and run.running and not built:
            raise mo.Refused("It is saving its files. Send it again in a moment.")
        if not built:
            return self._quick(self.quick.say, m, now, text)  # no build yet: the chat that writes the card
        if built not in m.plugs:
            raise mo.Refused(f"It is built, in agents/{built}, but it is not on this page, so it takes no correction "
                             "here yet. Restart the page to see it.")
        said = m.correct(built, text, now=now, by=mo.BY)
        if run is not None:
            run.taken.append({"said": text, "kind": "correction", "answer": said})
            return None  # the answer shows in the thread, under the message
        return said

    def _clear(self, m, now):
        run = self.run
        if run is not None and run.m is m and run.running:
            raise mo.Refused("It is building now. Start over once the build is done.")
        if run is not None and run.m is m:
            self.run = None
        return self._quick(self.quick.clear, m, now)

    def _m(self, day):
        return self.live if day == self.LIVE else self.days[day]

    def _day(self, query):
        if not self.demo:
            return None
        got = (query.get("day") or [""])[0]
        if got == self.LIVE and self.live is not None:
            return self.LIVE
        try:
            d = int(got)
        except ValueError:
            d = min(self.days)
        return d if d in self.days else min(self.days)

    def get(self, path, query, token, flash=None):
        """The page for a GET path, or None for an unknown path."""
        day = self._day(query)
        m = self._m(day) if self.demo else self.morning
        q = f"?day={day}" if self.demo else ""
        now = self.at.get(day) if self.demo else None
        self.settle(m)
        ctx = {"token": token, "q": q, "day": day, "path": path, "m": m, "now": now, "try": self.try_html,
               "look": looked_at(m, path, query), "query": query}
        if path == "/":
            return self.shell(today(m.view(now=now), ctx), "today", ctx, flash)
        if path == "/agents":
            return self.shell(agents(m, m.view(now=now), ctx), "agents", ctx, flash)
        if path.startswith("/agents/") and _AGENT.match(path[8:]):
            body = agent_page(m, m.view(now=now), path[8:], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash,
                                                        script=ARENA_SCRIPT if 'data-live="arena"' in body
                                                        and self.made_here(path[8:]) else None)
        if path.startswith("/agents/") and path.endswith(ROLLBACK) and _AGENT.match(path[8:-len(ROLLBACK)]):
            body = rollback_page(m, path[8:-len(ROLLBACK)], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash)
        if path == "/new":
            return self.shell(new_agent(m, self.quick, ctx, self.run), "agents", ctx, flash, script=NEW_SCRIPT)
        if path == "/new/build":
            agent = (query.get("agent") or [""])[0]
            return self.shell(build(m, agent if agent in m.plugs else None, ctx), "agents", ctx, flash)
        if path == "/console":
            agent = (query.get("agent") or [""])[0] or mo.SALES.agent
            if not _AGENT.match(agent):
                return None
            return console_mod.page(m, agent, query, token=token, flash=flash, now=now, day=day if self.demo else None,
                                    agents=agent_names(m, m.view(now=now)))
        return None

    def try_html(self, ctx):
        """Try Sales on the Sales agent's page: the thread (the customer's lines and the agent's replies,
        as written), the box, Send and Start over, and what it runs on."""
        t = self.try_sales
        rows = []
        for turn in t.thread():
            rows.append(f'<p class="said me" dir="auto">{h(turn["said"])}</p>')
            rows += [f'<p class="said ag" dir="auto">{h(r)}</p>' for r in turn["replies"]]
            if not turn["replies"]:
                rows.append(f'<p class="said no">No reply ({h(turn["outcome"].replace("_", " "))}).</p>')
        thread = f'<div class="thread">{"".join(rows)}</div>' if rows else ""
        ready = t.ready()
        form = ""
        if ctx["token"] and ready:
            over = _post(ctx, "try/sales/clear", "Start over", "over") if rows else ""
            form = (f'<form id="try-say" method="post" action="/try/sales">{_hidden(ctx)}<div class="box"><textarea '
                    f'name="text" aria-label="Your message to the Sales agent" maxlength="{try_mod.MAX_TEXT}" dir="auto" '
                    'required placeholder="Ask about a product, a size or delivery, like a customer would."></textarea>'
                    f'</div></form><div class="say-f"><p class="quiet">{icon("chat")}{try_mod.NOTE}</p>{over}'
                    f'<button class="send" type="submit" form="try-say">Send{icon("arrow")}</button></div>')
        elif not ready:
            form = f'<p class="quiet">{try_mod.NO_KEY}</p>'
        return (f'<section class="say try sq" aria-label="Try Sales"><span class="lab">Try Sales</span>{thread}{form}'
                '</section>')

    def shell(self, body, on, ctx, flash, script=None):
        q = ctx["q"]
        console = f'/console?agent={h(ctx["look"])}' + (f'&amp;day={h(ctx["day"])}' if self.demo else "")
        tabs = (("today", "/" + q, "sun", "Today"), ("agents", "/agents" + q, "sliders", "Agents"),
                ("console", console, "code", "Console"))
        top = "".join(f'<a class="titem{" on" if t == on else ""}" href="{u}"'
                      f'{" aria-current=page" if t == on else ""}>{icon(i)}{w}</a>' for t, u, i, w in tabs)
        bar = "".join(f'<a class="tab{" on" if t == on else ""}" href="{u}"'
                      f'{" aria-current=page" if t == on else ""}>{icon(i)}{w}</a>' for t, u, i, w in tabs)
        sample = self.demo and ctx["day"] != self.LIVE  # the phone bar says Sample, so the switch fits on one line
        right = '<span class="sample">Sample data</span>' if sample else ""
        short = '<span class="sample" title="Sample data">Sample</span>' if sample else ""
        days = ""
        if self.demo:
            tabs = [(d, f"Day {d}") for d in sorted(self.days)] + ([(self.LIVE, "Live")] if self.live is not None else [])
            days = '<nav class="days" aria-label="Sample days and live">' + "".join(
                f'<a class="{"on" if d == ctx["day"] else ""}" href="{h(ctx["path"])}?day={d}">{w}</a>'
                for d, w in tabs) + "</nav>"
        logo = f'<span class="logo">{mo.LOGO}</span><span class="word">Unfenced</span>'
        return "\n".join([
            '<!doctype html><html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
            f'<title>Unfenced</title><style>{CSS}</style></head><body><div class="page">',
            f'<nav class="tisl sq" aria-label="Main"><div class="left">{logo}</div><div class="tnav">{top}</div>'
            f'<div class="right">{days}{right}</div></nav>',
            f'<header class="bar"><div class="brand">{logo}</div><div class="bar-r">{days}{short}</div></header>',
            flash_html(flash, ctx),
            body, "</div>", f'<nav class="isl" aria-label="Main">{bar}</nav>',
            f"<script>{script}</script></body></html>" if script else "</body></html>"])


def looked_at(m, path, query):
    """The agent the Console item in the top menu opens on: the one this page is about (its page, its
    rollback, its Arena screen, the console's own), else the Sales agent. Read from the address only,
    no cookie."""
    got = ""
    if path.startswith("/agents/"):
        got = path[8:].split("/")[0]
    elif path in ("/new/build", "/console"):
        got = (query.get("agent") or [""])[0]
    return got if _AGENT.match(got or "") and got in getattr(m, "plugs", {}) else mo.SALES.agent


_TAKEN = re.compile(r"^There is an agent called ([a-z][a-z0-9_]*) already\.")


def flash_html(flash, ctx):
    """The one-time message, escaped. Quick start's "There is an agent called X already" refusal gets
    a link to X's page when X is an agent on this page, so the user can see the one that has the name."""
    if not flash:
        return ""
    link = ""
    taken = _TAKEN.match(str(flash))
    m = ctx.get("m")
    if taken and _AGENT.match(taken.group(1)) and m is not None and taken.group(1) in getattr(m, "plugs", {}):
        agent = taken.group(1)
        link = f' <a href="/agents/{h(agent)}{ctx["q"]}">Open {h(name(agent))}</a>'
    return f'<p class="flash" role="status">{h(flash)}{link}</p>'


# ---- Today -------------------------------------------------------------------------------------

def _hidden(ctx, **kv):
    kv = {"token": ctx["token"], "back": ctx["path"] + ctx["q"], **kv}  # back may be given
    return "".join(f'<input type="hidden" name="{h(k)}" value="{h(v)}">' for k, v in kv.items())


def _post(ctx, action, button, cls, **kv):
    return (f'<form method="post" action="/{action}">{_hidden(ctx, **kv)}'
            f'<button class="{cls}" type="submit">{button}</button></form>')


def _yc_head(agent, small, risk=""):
    r = f'<span class="risk"><i></i>{h(risk)}</span>' if risk else ""
    return (f'<div class="yc-h"><div class="agent"><span class="av">{mo._agent_icon(agent)}</span><div>'
            f'<b>{h(name(agent))}</b><small>{h(small)}</small></div></div>{r}</div>')


def lesson_card(item, ctx):
    """A lesson waiting for the user's yes: its line, why, the exam's counts, No, Modify, Yes."""
    risk = "High risk" if item.get("risk") == "high" else ""
    mine = CORRECTED in (item.get("source") or "")
    small = ("Your line, held by the exam" if item.get("exam") else "Your correction" if mine
             else "New lesson from Reflection")
    why = item["why"]
    if item.get("risk") == "high" and why.startswith("High risk:"):  # the engine's words, said plainly
        why = plain_risk(item.get("risk_why"))
    out = [f'<article class="yc sq" id="c{h(item["id"])}">', _yc_head(item["agent"], small, risk)]
    out.append(f'<p class="lesson" dir="auto">{h(item["text"])}</p>')
    for r in item["replaces"]:
        out.append(f'<p class="why" dir="auto">A yes takes the place of: {h(r["text"])}</p>')
    out.append(f'<p class="why">{h(why)}</p>')
    g = item.get("gate")
    if g:
        out.append('<div class="exam"><span class="lab">In the exam</span>'
                   f'<div class="stat"><b>{h(g["fixed"])}</b><span>situations it fixed</span></div>'
                   f'<div class="stat"><b>{h(g["broke"])}</b><span>situation{"" if g["broke"] == 1 else "s"} '
                   'it broke</span></div></div>')
    act = [mo._trial_words(item).replace('class="trial-l"', 'class="trial"') or '<p class="trial">A yes starts a trial.</p>']
    if ctx["token"]:
        act.append(_post(ctx, "no", "No", "no", lesson=item["id"]))
        if not item["replaces"]:  # a "replace it?" card is answered Yes or No, never edited
            act.append(
                f'<details class="mx"><summary class="mod">{icon("pen")}Modify</summary><div class="edit">'
                f'<form method="post" action="/modify">{_hidden(ctx, lesson=item["id"])}'
                '<span class="lab">Change it or add to it</span><div class="box">'
                f'<textarea name="line" aria-label="Lesson words" maxlength="{mo.MAX_LEN}" dir="auto" required>'
                f'{h(item["text"])}</textarea><textarea class="add" name="note" rows="1" aria-label="Add a note" '
                f'maxlength="{mo.MAX_LEN}" placeholder="Add a note for the agent, optional" dir="auto"></textarea></div>'
                f'<p class="quiet">{icon("loop")}New words go back through the exam before the trial starts.</p>'
                '<button class="mod" type="submit">Send to the exam</button></form></div></details>')
        act.append(_post(ctx, "yes", f'{icon("check")}Yes', "yes", lesson=item["id"],
                         shown=",".join(str(r["id"]) for r in item["replaces"])))
    out.append('<div class="act">' + "".join(act) + "</div></article>")
    return "".join(out)


def unclear_card(u, ctx):
    out = ['<article class="yc sq">', _yc_head(u["agent"], "Its trial ended too close to call"),
           f'<p class="lesson" dir="auto">{h(u["text"])}</p>',
           '<p class="why">Keep it on trial a little longer, or drop it.</p>']
    if ctx["token"]:
        out.append('<div class="act">' + _post(ctx, "drop", "Drop", "mod", lesson=u["id"])
                   + _post(ctx, "longer", f'{icon("check")}Keep trying', "yes", lesson=u["id"], days=u["days"] or 7)
                   + "</div>")
    return "".join(out) + "</article>"


def mode_card(agent, mode, ctx):
    words = ", ".join(f'"{w}"' for w in mode["words"][:3])
    out = ['<article class="yc sq">', _yc_head(agent, "A new mode"),
           f'<p class="lesson" dir="auto">{h(mode["name"].capitalize())}</p>',
           f'<p class="why" dir="auto">You said {h(words)}, and it fit no mode you have.</p>']
    if mode["fixed"] is not None:
        out.append('<div class="exam"><span class="lab">In the Arena, on your past days</span>'
                   f'<div class="stat"><b>{h(mo._n(mode["fixed"]))}</b><span>days it fixed</span></div>'
                   f'<div class="stat"><b>{h(mo._n(mode["broken"] or 0))}</b><span>days it broke</span></div></div>')
    if ctx["token"]:
        card = mode["file"]
        out.append('<div class="act">' + _post(ctx, "mode", "No", "no", agent=agent, card=card, choice="drop")
                   + _post(ctx, "mode", f'{icon("check")}Yes', "yes", agent=agent, card=card, choice="yes") + "</div>")
    return "".join(out) + "</article>"


def fact_card(f, ctx):
    out = ['<article class="yc sq">', _yc_head(f["agent"], "A fact from its results"),
           f'<p class="lesson" dir="auto">{h(f["fact"])}</p>', '<p class="why">Nothing acts on it by itself.</p>']
    if ctx["token"]:
        out.append('<div class="act">' + _post(ctx, "dismiss_fact", "No", "no", agent=f["agent"], key=f["key"],
                                               shown=f["shown"])
                   + _post(ctx, "keep_fact", f'{icon("check")}Keep', "yes", agent=f["agent"], key=f["key"],
                           shown=f["shown"]) + "</div>")
    return "".join(out) + "</article>"


def waiting(view):
    """Everything that needs the user's yes, in page order: lessons first (most to gain first)."""
    out = [("lesson", i) for i in view["cards"]]
    out += [("unclear", u) for u in view["unclear"]]
    out += [("mode", a) for a in view["agents"] if a.get("mode_card") is not None and a["buttons"]]
    out += [("fact", f) for f in view.get("facts") or []]
    return out


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _corrected(i):
    return CORRECTED in (i.get("source") or "")


# Under the box on an agent's page: what a correction does (Morning.correct), and nothing it does not.
SAY_NOTE = ("Takes a short exam, then starts at once as a hotfix in half the cases. If it is high risk or "
            "does not pass, it waits for your yes on Today. Reflection reads it tonight.")
ANSWERED = "Answered chats today. Reflection reads them tonight."


# What the exam a waiting correction took said, by Morning._item exam_result (None: it took none).
EXAM_SAID = {"passed": "Your correction passed the exam and waits for your yes.",
             "failed": "Your correction did not pass the exam and waits for your yes.",
             "not run": "The exam could not run on your correction, so it waits for your yes.",
             None: "Your correction waits for your yes."}
NIGHT_MAX = 2  # lines an agent gets under Last night (LOCKS: one line per agent), the most important first


def night_lines(a, now, answered=0):
    """Plain lines about an agent's last night, at most NIGHT_MAX, the most important first: a
    correction that waits for the user's yes, a trial where chats may have gone worse, the user's
    correction on trial, a lesson pulled or kept, the chats Reflection read and a lesson it wrote, a
    lesson on trial, a new mode, the hotfix notes, the Arena. answered: the real chats it answered
    since the night (Morning.answered_since), said in one line with no count. Never a count of what
    is left; a quiet night only when a night ran and did nothing at all."""
    day = mo.DAY
    rep = a.get("night") or {}
    fresh = (rep.get("until") or 0) >= now - day
    items = {i["id"]: i for i in a["live"] + a["waiting"] + a["pulled"]}
    new = [i for i in a["new"] if i.get("origin") != "person"]
    kept = [t for t in a["live"] if t["state"] == mo.KEPT and (t.get("decided_at") or 0) >= now - day]
    pulled = [i for i in a["pulled"] if (i["pulled_at"] or 0) >= now - day and not str(i.get("pulled_why") or "").startswith(mo.EDITED)]
    lines = []  # (rank, line): the lower rank first
    read = rep.get("chats") if fresh else None
    wrote = ("a new lesson" if len(new) == 1 else f"{len(new)} new lessons") if new else ""
    if read and wrote:
        lines.append((5, f"Reflection read {_plural(read, 'chat')} and wrote {wrote}."))
    elif read:
        lines.append((5, f"Reflection read {_plural(read, 'chat')}."))
    elif wrote:
        lines.append((5, f"Reflection wrote {wrote}."))
    for i in a["waiting"]:
        if _corrected(i) and i["card"] and i["added_at"] >= now - day:
            lines.append((0, EXAM_SAID.get(i.get("exam_result"), EXAM_SAID[None])))
    for t in (rep.get("trials") or []) if fresh else []:
        i = items.get(t["lesson_id"])
        if t["status"] != "on trial" or i is None or not t.get("cases"):
            continue
        who = "Your correction" if _corrected(i) else "A lesson on trial"
        harm = "no harm seen" if not t.get("harm") else f"{_plural(t['harm'], 'chat')} may have gone worse"
        rank = 1 if t.get("harm") else 2 if _corrected(i) else 6
        lines.append((rank, f"{who} ran in {_plural(t['cases'], 'chat')}, {harm}."))
    if pulled:
        lines.append((3, "A lesson was pulled."))
    if kept:
        lines.append((4, "A trial ended and its lesson is kept."))
    if a.get("mode_card") and (a["mode_card"].get("at") or 0) >= now - day:
        lines.append((7, "It found a new mode for you and tried it on your past days in the Arena."))
    if fresh and rep.get("hotfix"):
        n = rep["hotfix"]
        lines.append((8, f"{_plural(n, 'case')} that ended with no order got a hotfix note for that customer's next case."))
    if a.get("arena") and a["arena"]["at"] >= now - day:
        lines.append((9, "It practised on made-up cases in the Arena."))
    if answered:
        lines.append((10, ANSWERED))
    if lines:
        return [line for _, line in sorted(lines, key=lambda r: r[0])[:NIGHT_MAX]]
    return ["A quiet night. Nothing changed."] if rep else ["No night yet."]


def night_line(a, now, answered=0):
    """The night's lines as one string (tests and the old callers)."""
    return " ".join(night_lines(a, now, answered))


def status_of(m, agent):
    """Paused while its pause switch is on (Morning.paused), else Live or Training."""
    if m.paused(agent):
        return "Paused"
    return "Live" if agent in m._live() else "Training"


# The line under the status on an agent's page.
STATUS_SAID = {"Live": "Working on real cases", "Training": "Practising in the Arena",
               "Paused": "Paused: it sends nothing until you press Resume"}


def agent_names(m, view):
    """The agents both tabs list: every plug here and every agent the database knows."""
    return sorted(set(m.plugs) | {a["agent"] for a in view["agents"]})


def night_html(m, view):
    rows, now = [], view["at"]
    known = {a["agent"]: a for a in view["agents"]}
    for agent in agent_names(m, view):
        a = known.get(agent) or {"agent": agent, "live": [], "waiting": [], "pulled": [], "new": [], "night": None}
        st = status_of(m, agent)
        since = max(now - mo.DAY, (a.get("night") or {}).get("until") or 0)
        rows.append(f'<div class="nl"><span class="av">{mo._agent_icon(agent)}</span><div><b>{h(name(agent))} '
                    f'<span class="st{" live" if st == "Live" else ""}">{st}</span></b>'
                    + "".join(f"<p>{h(x)}</p>" for x in night_lines(a, now, m.answered_since(agent, since)))
                    + "</div></div>")
    if not rows:
        rows.append('<div class="nl"><span class="av">' + icon("spark") + '</span><div><b>No agents yet</b>'
                    '<p>Make one under Agents.</p></div></div>')
    return ('<section aria-label="Last night"><div class="sec-h"><h2>Last night</h2>'
            f'<small>{h(mo._date(view["at"] - mo.DAY))}</small></div><div class="night">' + "".join(rows) + "</div></section>")


def late_card(c, ctx):
    """A case waiting on a result only a person can bring (DECISIONS item 66): its reference (an
    order number, never a raw case id), since when, and a button per result it takes."""
    out = ['<article class="yc sq">', _yc_head(c["agent"], mo._ref_words(c["ref"]).capitalize()),
           f'<p class="why">{h(mo.late_case_words(c))}</p>']
    if ctx["token"]:
        out.append('<div class="act">' + "".join(
            _post(ctx, "late_mark", h(mo.late_label(r)), "yes" if n == 0 else "mod", agent=c["agent"], case=c["ref"],
                  result=r) for n, r in enumerate(c["names"])) + "</div>")
    return "".join(out) + "</article>"


def late_html(late, ctx):
    """Today's part for results only a person can bring: the waiting cases, then a sheet upload per
    agent. Nothing counts what is left (item 35)."""
    body = "".join(late_card(c, ctx) for c in late["cases"])
    if ctx["token"]:
        back = f'<input type="hidden" name="back" value="{h(ctx["path"] + ctx["q"])}">'
        body += "".join(f'<div class="yc sq">{mo.sheet_form(ctx["token"], a, back)}</div>' for a in late["agents"])
    return ('<section aria-labelledby="late-h"><div class="sec-h"><h2 id="late-h">Waiting for a result</h2></div>'
            f'<div class="cards">{body}</div></section>')


def today(view, ctx):
    items = waiting(view)
    cards = {"lesson": lesson_card, "unclear": unclear_card, "fact": fact_card}
    html = [f'<section class="top"><h1>Good morning</h1><p class="num">{h(mo._today(view["at"]))}</p></section>']
    late = view.get("late") or {}
    if items or late.get("agents"):
        html.append('<div class="today">')
        if items:
            body = "".join(mode_card(i["agent"], i["mode_card"], ctx) if k == "mode" else cards[k](i, ctx)
                           for k, i in items)
            html.append('<section aria-labelledby="y-h"><div class="sec-h"><h2 id="y-h">Needs your yes'
                        f'</h2></div><div class="cards">{body}</div></section>')
        if late.get("agents"):
            html.append(late_html(late, ctx))
    else:
        html.append('<div class="today empty"><section aria-label="Needs your yes"><div class="sec-h"><h2>Needs your yes'
                    f'</h2></div><div class="calm sq"><span class="ok">{icon("check")}</span><div><b>Nothing needs you '
                    'today</b><p>Your agents keep going. Skip a day and nothing breaks.</p></div></div></section>')
    html.append(night_html(ctx["m"], view) + "</div>")
    return "".join(html)


# ---- Agents ------------------------------------------------------------------------------------

def agents(m, view, ctx):
    names = agent_names(m, view)
    rows = "".join(f'<a class="agl" href="/agents/{h(a)}{ctx["q"]}"><span class="av">{mo._agent_icon(a)}</span>'
                   f'<b>{h(name(a))}</b><span class="st{" live" if status_of(m, a) == "Live" else ""}">'
                   f'{status_of(m, a)}</span></a>' for a in names)
    return ('<section class="top"><h1>Agents</h1><p>Each one learns from its own cases.</p></section><div class="col">'
            f'<a class="yes" href="/new{ctx["q"]}">{icon("plus")}New agent</a>'
            f'<section class="grp sq" aria-label="Your agents">{rows}</section></div>')


def _chip(i, a=None):
    if i["state"] == mo.TRYING and _corrected(i):
        said = f'From your correction, {mo._date(i["added_at"])}. On trial.'
        rep = (a or {}).get("night") or {}
        t = next((t for t in rep.get("trials") or [] if t["lesson_id"] == i["id"] and t["status"] == "on trial"), None)
        if t is not None and t.get("cases"):
            return "hot", "Hotfix", f'{said} Reflection checked it last night: it ran in {_plural(t["cases"], "chat")}.'
        return "hot", "Hotfix", f"{said} Reflection checks it tonight."
    if i["state"] == mo.TRYING:
        return "trial", "On trial", f'Until {mo._date(i["ends_at"])}' if i.get("ends_at") else "On trial"
    if i["state"] == mo.KEPT:
        return "", "Kept", f'Since {mo._date(i.get("decided_at") or i["added_at"])}'
    if i["state"] == mo.WAITING:
        return "", "Waiting", "Waits for your yes on Today" if i["card"] else "Waits its turn"
    return "", "Pulled", f'{mo._date(i["pulled_at"])}'


# The agent page's four tabs (LOCKS "App pages", 1B): links the server renders, ?tab=, no script.
TABS = (("overview", "Overview"), ("arena", "Arena"), ("live", "Live"), ("lessons", "Lessons"))
TAB_KEYS = tuple(k for k, _ in TABS)


def tab_of(query):
    got = ((query or {}).get("tab") or [""])[0]
    return got if got in TAB_KEYS else "overview"


def tab_ctx(ctx, agent, tab):
    """ctx for the forms of one tab: an answer comes back to the same tab, on the same demo day."""
    q = f"?tab={tab}" + (f'&day={ctx["day"]}' if ctx["day"] else "")
    return dict(ctx, path=f"/agents/{agent}", q=q)


def tab_href(ctx, agent, tab):
    day = f'&amp;day={h(ctx["day"])}' if ctx["day"] else ""
    return f"/agents/{h(agent)}?tab={tab}{day}" if tab != "overview" else f'/agents/{h(agent)}{ctx["q"]}'


def lesson_rows(a, limit=None):
    rows = []
    for i in a["live"] + a["waiting"] + a["pulled"][:5]:
        cls, chip, small = _chip(i, a)
        rows.append(f'<div class="lr"><b dir="auto">{h(i["text"])}</b><span class="vchip {cls}">{chip}</span>'
                    f'<small>{h(small)}</small></div>')
    return rows[:limit] if limit else rows


def agent_page(m, view, agent, ctx):
    a = next((x for x in view["agents"] if x["agent"] == agent), None)
    if a is None and agent not in m.plugs:
        return None
    a = a or {"agent": agent, "live": [], "waiting": [], "pulled": [], "night": None, "buttons": agent in m.plugs}
    tab = tab_of(ctx.get("query"))
    st = status_of(m, agent)
    tabs = "".join(f'<a class="on" href="{tab_href(ctx, agent, k)}" aria-current="page">{w}</a>' if k == tab
                   else f'<a href="{tab_href(ctx, agent, k)}">{w}</a>' for k, w in TABS)
    cons = ""
    if agent in m.plugs:  # the technical view of its loop (reflection/console.py)
        day = f'&amp;day={h(ctx["day"])}' if ctx["day"] else ""
        cons = f'<a class="cons" href="/console?agent={h(agent)}{day}">{icon("code")}Open console</a>'
    head = (f'<div class="ahead"><a class="back" href="/agents{ctx["q"]}">{icon("back")}Agents</a>'
            f'<div class="ah-row"><div><h1>{h(name(agent))}</h1><p>{STATUS_SAID[st]}</p></div>{cons}</div></div>'
            f'<nav class="atabs" aria-label="{h(name(agent))}">{tabs}</nav>')
    body = {"overview": overview_tab, "arena": arena_tab, "live": live_tab, "lessons": lessons_tab}[tab](
        m, view, a, agent, st, ctx)
    return f'<div class="agp">{head}{body}</div>'


def overview_tab(m, view, a, agent, st, ctx):
    """Overview: the status with Roll back and Pull (or Resume), the channels and Connect, the box for an
    idea or a correction; beside them since yesterday and the newest lessons."""
    states = "".join(f'<span class="on"><i></i>{s}</span>' if s == st else f"<span>{s}</span>"
                     for s in ("Training", "Live", "Paused"))
    tok = ctx["token"] if a["buttons"] else None
    roll = ""
    plan = m.rollback_plan(agent, ctx.get("now")) if a["buttons"] else None
    if tok and plan is not None:  # the plan first, on its own screen; the rollback is the button there
        roll = f'<a class="gb" href="/agents/{h(agent)}{ROLLBACK}{ctx["q"]}">{icon("undo")}Roll back</a>'
    elif a["buttons"]:
        roll = f'<button class="gb" type="button" disabled>{icon("undo")}Roll back</button>'
    conns = m.connection_view(agent) if agent in m.plugs else []
    if tok and st == "Paused" and m.pausable(agent):
        pull = _post(ctx, "resume", f'{icon("loop")}Resume', "gb", agent=agent)
    elif tok and any(c["works"] for c in conns):  # live on a channel: Pull takes it off (DECISIONS 77)
        pull = (_post(ctx, "disconnect", f'{icon("pause")}Pull', "gb", agent=agent) if any(c["live"] for c in conns)
                else f'<button class="gb" type="button" disabled title="{NOT_LIVE}">{icon("pause")}Pull</button>')
    elif tok and m.pausable(agent):  # the real pause switch (DECISIONS 54, Morning.pause and resume)
        pull = _post(ctx, "pause", f'{icon("pause")}Pull', "gb", agent=agent)
    else:
        pull = f'<button class="gb" type="button" disabled title="Not built for this agent yet">{icon("pause")}Pull</button>'
    left = [f'<section class="status sq" aria-label="Status"><div class="st-l"><span class="states" role="img" '
            f'aria-label="Status: {st}">{states}</span><small>{STATUS_SAID[st]}'
            f'</small></div><div class="st-r">{roll}{pull}</div></section>']
    if conns:
        left.append(connections_html(agent, conns, ctx, tok))
    folder = m.agent_folder(agent) if hasattr(m, "agent_folder") else None
    if folder is not None:  # an agent made here: its sample data and the box that adds to it
        data = m.sample_data(agent)
        line = sample_mod.words(data) or "No sample data yet. Add rows it can work from."
        left.append(f'<section class="grp sq" aria-labelledby="sd-h"><h3 id="sd-h">Sample data</h3><div class="lr">'
                    f'<b dir="auto">{h(line)}</b><small>Made up for practice until a real connection is set.</small>'
                    '</div></section>')
        if tok:
            left.append(data_form(ctx, agent))
        if agent not in m.read_arena()[0]:  # no saved run yet: Run the Arena here too, polled the same way
            go = run_arena(m, agent, ctx, ctx["path"] + ctx["q"])
            if go:
                left.append(f'<section class="grp sq" aria-labelledby="ra-h"{arena_live(m, agent)}><h3 id="ra-h">'
                            f'The Arena</h3><small class="quiet">No practice run saved yet.</small>{go}</section>')
    if tok:
        left.append(f'<section class="say sq" aria-label="Send an idea or a correction"><form method="post" action="/correct">'
                    f'{_hidden(ctx, agent=agent)}<span class="lab">Send an idea or a correction</span><div class="box">'
                    f'<textarea name="line" aria-label="Your idea or correction" maxlength="{mo.MAX_LEN}" dir="auto" required>'
                    f'</textarea></div><div class="say-f"><p class="quiet">{icon("loop")}{SAY_NOTE}</p><button class="send" type="submit">Send{icon("arrow")}</button></div></form></section>')
    now = view["at"]
    since = max(now - mo.DAY, (a.get("night") or {}).get("until") or 0)
    full = dict({"new": [], "night": None}, **a)
    night = "".join(f'<div class="nr"><p>{h(x)}</p></div>' for x in night_lines(full, now, m.answered_since(agent, since)))
    newest = "".join(lesson_rows(a, 3)) or '<div class="lr"><b>No lessons yet.</b></div>'
    right = (f'<section class="grp sq" aria-labelledby="y-h"><h3 id="y-h">Since yesterday</h3>{night}</section>'
             f'<section class="grp sq" aria-labelledby="n-h"><div class="grp-h"><h3 id="n-h">Newest lessons</h3>'
             f'<a class="lk" href="{tab_href(ctx, agent, "lessons")}">All lessons</a></div>{newest}</section>')
    return f'<div class="ov"><div class="ov-l">{"".join(left)}</div><div class="ov-r">{right}</div></div>'


def arena_tab(m, view, a, agent, st, ctx):
    """Arena: the practice matches of its newest run, a lost one with Correct this (into the exam), and
    Try again, beside the climb. Answers come back to this tab."""
    c = tab_ctx(ctx, agent, "arena")
    glow, tiles, retry = arena_parts(m, agent if agent in m.plugs else None, c, back=c["path"] + c["q"],
                                     fix_ctx=c)
    go = run_arena(m, agent, c, c["path"] + c["q"])
    live = arena_live(m, agent) if go else ""
    return (f'<div class="qs"{live}><div class="ar"><section class="ar-l" aria-labelledby="m-h"><div class="sec-h"><h2 id="m-h">Practice '
            f'matches</h2><small>Where it slipped</small></div><div class="tiles">{tiles}</div>{retry}{go}</section>'
            f'<div class="ar-r">{glow}</div></div></div>')


ARENA_PATH = "/arena/run"
ARENA_SAID = "Plays its practice matches against made-up customers, with its sample data. A few minutes."


def arena_live(m, agent):
    """The marks the agent page's script polls (ARENA_SCRIPT): data-running while a run goes."""
    return ' data-live="arena"' + (" data-running" if m.arena_running(agent) else "")


def run_arena(m, agent, ctx, back):
    """Run the Arena (Morning.run_arena) for an agent made here: the button while no run goes and the page
    has a token, how many matches it played while one runs, and a line when the last one could not finish.
    Empty for any other agent (the Sales agent has Try again)."""
    if not hasattr(m, "run_arena") or m.agent_folder(agent) is None:
        return ""
    if m.arena_running(agent):
        n = m.arena_played(agent)
        said = (f"Running the Arena: {n} practice {'match' if n == 1 else 'matches'} played so far." if n
                else "Running the Arena: its first matches are starting.")
        return f'<div class="act"><p class="no-yet" role="status">{h(said)}</p></div>'
    out = []
    note = m.arena_note(agent)
    if note:
        out.append(f'<p class="no-yet" role="status">{h(note)}</p>')
    if ctx["token"]:
        out.append(f'<p class="quiet">{ARENA_SAID}</p>'
                   + _post(ctx, ARENA_PATH[1:], f'{icon("flask")}Run the Arena', "yes", agent=agent, back=back))
    return f'<div class="act">{"".join(out)}</div>' if out else ""


def live_tab(m, view, a, agent, st, ctx):
    """Live: the real chats once it is connected (the console's turns, newest first, each opening its
    row in the console), Try Sales on the Sales agent's page, and a note while it is not live."""
    rows = []
    turns = []
    if agent in m.plugs and agent == mo.SALES.agent:
        try:
            turns = console_mod.collect(m, agent, ctx.get("now"))["turns"]
        except Exception:  # a database with no chats store yet: nothing to list
            turns = []
    day = f'&amp;day={h(ctx["day"])}' if ctx["day"] else ""
    for t in list(reversed(turns))[:20]:
        said = (t["replies"] or [""])[0]
        chip = '<span class="vchip hot">Flagged</span>' if t["flagged"] else '<span class="vchip">Sent</span>'
        rows.append(f'<a class="lrow" href="/console?agent={h(agent)}&amp;view=deploy&amp;row={h(t["key"])}{day}">'
                    f'<span class="who"><b dir="auto">{h(t["customer"])}</b><span class="line" dir="auto">{h(said)}'
                    f'</span></span><span class="meta">{chip}<small class="num">{h(mo._when(t["at"]))}</small></span></a>')
    left = []
    if rows:
        left.append('<section aria-labelledby="lv-h"><div class="sec-h"><h2 id="lv-h">Live chats</h2><small>Newest '
                    f'first</small></div><div class="lrows">{"".join(rows)}</div></section>')
    else:
        word = "It is live and has no chats yet." if st == "Live" else (
            "Not live yet. It answers real customers once its Arena gate passes and you connect it on Overview.")
        left.append(f'<div class="note sq">{icon("chat")}<div><b>No live chats</b><p>{word}</p></div></div>')
    tok = ctx["token"] if a["buttons"] else None
    if tok and agent == mo.SALES.agent and ctx.get("try") is not None:
        left.append(ctx["try"](tab_ctx(ctx, agent, "live")))
    right = ('<section class="grp sq" aria-labelledby="lt-h"><h3 id="lt-h">Every step</h3><div class="nr"><p>'
             f'Each chat, each tool call and each check is in the console. <a class="lk" href="/console?agent='
             f'{h(agent)}&amp;view=deploy{day}">Open console</a></p></div></section>') if agent in m.plugs else ""
    return f'<div class="livetab"><div class="lv-l">{"".join(left)}</div><div class="lv-r">{right}</div></div>'


def lessons_tab(m, view, a, agent, st, ctx):
    """Lessons: every lesson with its chip, then the Reflection notes."""
    rows = lesson_rows(a)
    out = ['<div class="lstab"><section class="grp sq" aria-labelledby="l-h"><h3 id="l-h">Lessons</h3>'
           + ("".join(rows) or '<div class="lr"><b>No lessons yet.</b></div>') + "</section>"]
    notes = []
    for n in ((a.get("night") or {}).get("handed") or []):
        notes.append(f'<div class="nr"><span class="to">{icon("out")}Sent to {h(name(n["to"]))}</span>'
                     f'<p dir="auto">{h(n["text"])}</p></div>')
    for i in a["live"] + a["waiting"]:
        if i.get("kind") == "idea" and i.get("origin") == "person":
            whose = "Your correction" if CORRECTED in (i.get("source") or "") else "Your idea"
            notes.append(f'<div class="nr"><span class="to">{icon("bulb")}{whose}, {h(mo._date(i["added_at"]))}</span>'
                         f'<p dir="auto">{h(i["text"])}</p></div>')
    if a.get("arena"):  # its own words, never the Arena item's line: that line counts matches won
        notes.append(f'<div class="nr"><span class="to">{icon("note")}From the Arena, {h(mo._date(a["arena"]["at"]))}</span>'
                     f'<p>It practised on made-up cases. <a class="lk" href="{tab_href(ctx, agent, "arena")}">'
                     'See where it slipped</a></p></div>')
    out.append('<section class="grp sq" aria-labelledby="r-h"><h3 id="r-h">Reflection notes</h3>'
               + ("".join(notes) or '<div class="nr"><p>Nothing yet.</p></div>') + "</section></div>")
    return "".join(out)


# Deploy on an agent's page (DECISIONS item 77, Morning.connect and disconnect): page text, never a model's.
NOT_LIVE = "Not live on any channel"
LOCKED = "Locked until its latest Arena gate passes."
QUICK_NEXT = "Connecting an agent made in Quick start to {name} is next."


def connection_line(c):
    """The one line under a channel the agent asks for: live since when and the gate result that
    unlocked it, or why Connect waits, or not connected yet."""
    if c.get("setting"):  # no row yet: the server's demo setting keeps it on (kit/connections.py fixed)
        return f'Live on {c["name"]}: the server setting keeps it on. Pull takes it off.'
    if c["live"]:
        return f'Live on {c["name"]} since {mo._when(c["at"])}. {c["why"]}'
    if not c["works"]:
        if c["channel"] == "whatsapp":
            return f'{QUICK_NEXT.format(name=c["name"])} {c["gate"]["said"]}'
        return "Not connected yet."
    pulled = f'Pulled {mo._when(c["at"])}. ' if c["at"] is not None else ""
    if c["gate"]["passed"]:
        return f'{pulled}{c["gate"]["said"]} Connect it when you are ready.'
    return f'{pulled}{LOCKED} {c["gate"]["said"]}'


def connections_html(agent, conns, ctx, tok):
    """Each channel the agent asks for, with its line, and Connect for WhatsApp: a button only after
    the latest Arena gate passed, greyed out with the reason before."""
    rows = []
    for c in conns:
        line = connection_line(c)
        chip = '<span class="vchip trial">Live</span>' if c["live"] else '<span class="vchip">Not connected</span>'
        rows.append(f'<div class="lr"><b>{h(c["name"])}</b>{chip}<small>{h(line)}</small></div>')
        if c["channel"] != "whatsapp" or c["live"]:
            continue
        label = f'Connect to {h(c["name"])}{icon("arrow")}'
        if tok and c["works"] and c["gate"]["passed"]:
            rows.append('<div class="act">' + _post(ctx, "connect", label, "yes", agent=agent, channel=c["channel"])
                        + "</div>")
        else:
            why = LOCKED if c["works"] else QUICK_NEXT.format(name=c["name"])
            rows.append(f'<div class="act"><button class="yes" type="button" disabled title="{h(why)}">{label}'
                        "</button></div>")
    return ('<section class="grp sq conn" aria-labelledby="k-h"><h3 id="k-h">Connections</h3>'
            + "".join(rows) + "</section>")


# What a rollback does to each lesson the plan names (reflection/snapshots.py plan), in plain words:
# (chip, why). A lesson that stays as it is, or is back already as another lesson, is not listed.
ROLL_STEPS = {snapshots.PULL: ("Pulled", "Given now but not that night, so it is pulled."),
              snapshots.BACK: ("Stays pulled", "Given that night and pulled since. It stays pulled."),
              snapshots.CANNOT: ("Stays as it is", "Given that night, but it cannot come back."),
              snapshots.LEFT: ("Waiting", "Added after that night. It still waits for your yes.")}


def rollback_page(m, agent, ctx):
    """The plan a rollback to the latest night snapshot would carry out now, each lesson it changes
    in plain words, then one button that sends the plan's code (Morning.roll_back refuses when the
    lessons changed since). None for an agent with no plug or no snapshot."""
    if agent not in m.plugs:
        return None
    plan = m.rollback_plan(agent, ctx.get("now"))
    if plan is None:
        return None
    snap, steps, code = plan
    q = ctx["q"]
    rows = [f'<div class="lr"><b dir="auto">{h(s["line"] or "A lesson no longer here")}</b>'
            f'<span class="vchip">{ROLL_STEPS[s["do"]][0]}</span><small>{ROLL_STEPS[s["do"]][1]}</small></div>'
            for s in steps if s["do"] in ROLL_STEPS]
    pulls = any(s["do"] == snapshots.PULL for s in steps)
    if not pulls:
        rows.insert(0, '<div class="lr"><b>Nothing to roll back: the lessons given now were all given that night.</b></div>')
    out = [f'<div class="colhead"><a class="back" href="/agents/{h(agent)}{q}">{icon("back")}{h(name(agent))}</a>'
           '<section class="top ag-top"><h1>Roll back</h1></section></div><div class="col">',
           f'<section class="grp sq" aria-labelledby="rb-h"><h3 id="rb-h">Back to the night of {h(mo._date(snap["at"]))}'
           f'</h3>{"".join(rows)}</section>']
    if pulls and ctx["token"]:
        out.append('<div class="act">' + _post(dict(ctx, path=f"/agents/{agent}"), "rollback",
                                               f'{icon("undo")}Roll back now', "yes", agent=agent, code=code) + "</div>")
    return "".join(out) + "</div>"


# ---- New agent: the build page (LOCKS "App pages", 2A) ------------------------------------------

def _greet(now):
    t = mo._cairo(now if now is not None else time.time())
    hour = t.hour if t is not None else 12
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


MK = f'<span class="mk">{mo.LOGO}</span>'


def _who(small=""):
    return f'<div class="who">{MK}<b>Agent builder</b>' + (f"<small>{small}</small>" if small else "") + "</div>"


def steps_html(run, built):
    """The checklist message: each step done so far with its line, the one it is on, and the last one
    big; then Go to the Arena with the countdown, or what went wrong."""
    rows, working = [], run is not None and run.running and not run.error
    done = run.done if run is not None else {k: "" for k, _, _ in BUILD_STEPS}
    for key, doing, did in BUILD_STEPS:
        big = " big" if key == "ready" else ""
        if key in done:
            detail = done[key] if key not in ("card", "files", "ready") else ""
            if key == "files" and done[key]:
                detail = f"agents/{done[key]}"
            p = f'<p dir="auto">{h(detail)}</p>' if detail and not big else ""
            rows.append(f'<div class="step done{big}"><span class="tick">{icon("check")}</span><div><b>{did}</b>{p}'
                        "</div></div>")
        elif working:
            rows.append(f'<div class="step work{big}"><span class="tick">{icon("check")}</span><div><b>{doing}</b>'
                        "</div></div>")
            working = False
    return "".join(rows)


def took(tag, said, state):
    """A message the build took in, under its answer: what it became and where it went."""
    return (f'<div class="took"><span class="tag">{tag}</span><b dir="auto">{h(said)}</b><span class="st"><i></i>{state}'
            '</span></div>')


def ready_html(ctx, built, run):
    href = tab_href(ctx, built, "arena")
    # the countdown only right after the build, and never once the user stayed to send a correction
    fresh = (run is not None and run.ended is not None and time.monotonic() - run.ended < FRESH
             and not any(t["kind"] == "correction" for t in run.taken))
    auto = (f'<span class="auto"><svg class="ring" viewBox="0 0 22 22" aria-hidden="true"><circle class="bg" cx="11" '
            f'cy="11" r="9"/><circle class="fg" cx="11" cy="11" r="9"/></svg><span>Opening in <b class="num" '
            f'data-count>{COUNTDOWN}</b> seconds</span></span><button class="stay" type="button" data-stay>Stay here'
            "</button>") if fresh else ""
    return (f'<div class="ready"><p>Watch its matches and correct any reply it loses.</p><div class="goto">'
            f'<a class="yes" href="{href}" data-go>Go to the Arena{icon("arrow")}</a>{auto}</div></div>')


def new_agent(m, quick, ctx, run=None):
    """The build page: a centred thread, the box pinned at the bottom. The user's messages, the model's
    card, its one question and its follow line, shown as written (DECISIONS items 58 and 38); then the
    build's steps ticking off (BuildRun, the page polls while it runs) and, once done, Go to the Arena
    with a countdown that Stay here stops. Labels, steps and buttons are the page's frame."""
    d = quick.draft(m)
    turns, built = d["turns"], d["built"]
    run = run if run is not None and run.m is m else None
    building = run is not None and run.running
    tok = ctx["token"]
    notes = []
    if not quick.ready():
        notes.append('<p class="no-yet">No model key is set, so Quick start cannot write the card yet. Put '
                     'META_API_KEY or BASETEN_API_KEY in .env and start the page again.</p>')
    elif quick.folder(m) is None:
        notes.append('<p class="no-yet">Quick start needs the database folder. Start the page with --db.</p>')
    if not turns and not built:
        form = ""
        if tok:
            form = (f'<form method="post" action="/quickstart">{_hidden(ctx)}<div class="comp sq"><textarea name="text" '
                    f'rows="2" maxlength="{qs_mod.MAX_TEXT}" aria-label="What agent do you want?" dir="auto" required '
                    'placeholder="I want an agent that answers my support tickets and tags the ones that need the '
                    'team."></textarea><div class="crow"><span class="bmode"><span class="on">Build</span><span>'
                    f'Brainstorm <i>Soon</i></span></span><span class="sp"></span><button class="send go" type="submit" '
                    f'aria-label="Start the build" title="Start the build">{icon("up")}</button></div></div></form>')
        return (f'<div class="bp"><section class="hero"><h1 class="hello"><span>{_greet(ctx.get("now"))}.</span><br>What '
                'should your agent do?</h1><p class="sub">Say it in your own words. Its card comes back here, then you '
                f'press Build. It starts from zero and earns every lesson in the Arena.</p>{form}{"".join(notes)}'
                "</section></div>")
    out = []
    data = m.sample_data(built) if built and not building else None  # made at Build, shown on its card
    split = run is not None and run.error is None  # turns after Build was pressed show under its steps
    head = turns[:min(run.base, len(turns))] if split else turns
    later = iter(turns[len(head):])
    last = len(head) - 1
    for n, t in enumerate(head):
        out.append(f'<div class="you"><span dir="auto">{h(t["said"])}</span></div>')
        if n < last:
            out.append(f'<div class="bot">{_who()}<p class="uf" dir="auto">{h(t["follow"])}</p></div>')
            continue
        card = [f'<div class="bot">{_who()}<p class="uf" dir="auto">{h(t["follow"])}</p><div class="acard sq">'
                f'<span class="lab">Agent card</span>{plan_card(t["card"], data)}']
        if t["question"] and not built and not building:
            card.append(f'<p class="uq" dir="auto">{h(t["question"])}</p>')
        if built or building or run is not None and run.error is None:
            card.append(f'<div class="cact"><span class="started">{icon("check")}Build started</span></div>')
        elif tok:
            card.append('<div class="cact">' + _post(ctx, "quickstart/build", f'Build{icon("arrow")}', "yes")
                        + '<span class="cnote">You can keep typing while it builds.</span></div>')
        out.append("".join(card) + "</div></div>")
    if run is not None or built:
        small = "building" if building else "done" if built else ""
        body = steps_html(run, built)
        if built and not building:
            body += ready_html(ctx, built, run)
        out.append(f'<div class="bot">{_who(small)}<div class="check sq">{body}</div></div>')
        if run is not None and run.error:
            out.append(f'<div class="bot">{_who()}<p class="err" role="status">{h(run.error)}</p></div>')
        if run is not None and run.join_note:
            out.append(f'<div class="bot">{_who()}<p class="err" role="status">{h(run.join_note)}</p></div>')
        practice = quick.practice_line(built) if built else None
        if practice:
            out.append(f'<div class="bot">{_who()}<p role="status">{h(practice)}</p></div>')
        if built and not building and tok and m.agent_folder(built) is not None:  # it can take more data
            out.append(f'<div class="bot">{_who()}{data_form(ctx, built)}</div>')
    for t in run.taken if split else ():
        out.append(f'<div class="you"><span dir="auto">{h(t["said"])}</span></div>')
        if t["kind"] == "card":  # the model wrote the card again: its new follow line, as written
            turn = next(later, None)
            line = f'<p class="uf" dir="auto">{h(turn["follow"])}</p>' if turn else ""
            out.append(f'<div class="bot">{_who()}{line}{took("Card change", t["said"], "Taken into the build")}</div>')
        else:  # a correction: the exam's answer (Morning.correct)
            out.append(f'<div class="bot">{_who()}<p role="status">{h(t["answer"])}</p>'
                       f'{took("Correction", t["said"], "Took the exam")}</div>')
    out += notes
    ph = ("Add or change anything while it builds" if building else "Add anything before its next match" if built
          else "Change anything on the card, or press Build")
    dock = ""
    if tok:
        dock = (f'<div class="dock"><form method="post" action="/quickstart">{_hidden(ctx)}<div class="comp sq"><textarea '
                f'name="text" rows="1" maxlength="{qs_mod.MAX_TEXT}" aria-label="Your answer, or anything to add or change" '
                f'dir="auto" required placeholder="{ph}"></textarea><div class="crow"><span class="sp"></span>'
                f'<button class="send go" type="submit" aria-label="Send" title="Send">{icon("up")}</button></div></div>'
                f'</form>{"" if building else _post(ctx, "quickstart/clear", "Start over", "over")}</div>')
    live = ' data-building=""' if building else ""
    return (f'<div class="bp"><section class="bthread" data-live="thread" aria-label="Build conversation" '
            f'aria-live="polite"{live}>{"".join(out)}</section>{dock}</div>')


_LABEL_WORDS = {"It is over": re.compile(r"^(?:it\s+is\s+|it's\s+|the\s+case\s+is\s+)?over\s+", re.IGNORECASE),
                "Comes in": re.compile(r"^(?:it\s+)?(?:arrives|comes\s+in)\s*:?\s+", re.IGNORECASE),
                "It gives": re.compile(r"^it\s+gives\s*:?\s+", re.IGNORECASE)}


def case_value(label, value):
    """A case line under its label, with the label's own words cut from its start when the model wrote
    them too ("over when the report is sent" under It is over), so no word shows twice."""
    rx = _LABEL_WORDS.get(label)
    v = str(value or "").strip()
    cut = rx.sub("", v, count=1) if rx is not None else v
    return cut or v


SAMPLE_STATE = "Sample data for now"            # a need with no real connection, read from the sample data
STORE_SAMPLE = "Sample data until the store is connected"  # the store need with no Shopify keys
# A step the case's end needs (reflection/quickstart.py steps) whose need is not connected: the card says,
# before Build, that the agent records it and the user does that part until it is connected.
STEP_WAIT = "Until it is connected, it records the {thing} as {done} and you do that part."
DATA_NOTE = "Paste rows (CSV or JSON) or plain lines, or choose a file. They are added as yours."


def data_form(ctx, agent):
    """The box that adds rows or a file to a built agent's sample data (Morning.add_data)."""
    return (f'<section class="say sq" aria-label="Add sample data"><form method="post" action="{mo.DATA_PATH}" '
            f'enctype="multipart/form-data">{_hidden(ctx, agent=agent)}<span class="lab">Add data</span><div class="box">'
            f'<textarea name="text" aria-label="Rows or text to add" maxlength="{sample_mod.MAX_TEXT}" dir="auto" '
            'placeholder="name, price, stock"></textarea></div><div class="say-f"><label class="quiet pick">'
            f'{icon("plus")}<input type="file" name="file" aria-label="A CSV or JSON file" '
            'accept=".csv,.json,.txt,text/csv,application/json,text/plain"></label><button class="send pill" type="submit">'
            f'Add{icon("arrow")}</button></div><p class="quiet">{DATA_NOTE}</p></form></section>')


def sample_line(data):
    return f'<p class="quiet sdata">{icon("note")}{h(sample_mod.words(data))}</p>' if data else ""


def need_keys(tool):
    """The keys a tool needs set before its need reads as connected; () for a tool that needs none."""
    if tool == "store":
        return ("SHOPIFY_STORE", "SHOPIFY_TOKEN")
    if tool == "whatsapp":
        from channels import whatsapp
        return whatsapp.REQUIRED_ENV
    return ()


def need_state(n, data):
    """(words, connected) for one need on the card: Connected only with a real connection, so the store and
    WhatsApp only with their keys set. The store with no keys, or a need with no tool while the agent has
    sample data, says sample data; WhatsApp with no keys is not connected yet."""
    from kit import env
    if n["connected"] and not all(env.get(k) for k in need_keys(n["tool"])):
        return (STORE_SAMPLE, False) if n["tool"] == "store" else ("Not connected yet", False)
    if n["connected"]:
        return f'Connected: {qs_mod.TOOLS.get(n["tool"], "").split(":")[0]}', True
    return (SAMPLE_STATE if data else "Not connected yet"), False


def plan_card(card, data=None):
    """The model's card as one plain white card, then what it needs, each marked connected or not yet.
    One case is: what arrives, what the agent gives and when it is over, in the model's words under the
    page's labels, and a line when the agent writes first; then the good and the bad result (DECISIONS
    item 68). The user changes any of them by a message in the box; the model writes the card again."""
    never = "".join(f'<li dir="auto">{h(x)}</li>' for x in card["never"])
    rows = [("What it does", f'<p dir="auto">{h(card["does"])}</p>')]
    case = card.get("case")
    if case:
        parts = [("Comes in", case["input"]), ("It gives", case["output"]), ("It is over", case["ends"])]
        if case.get("starts") == "agent":
            parts.append(("Who starts", "The agent writes first"))
        lis = "".join(f'<li dir="auto"><b>{t}:</b> {h(case_value(t, v))}</li>' for t, v in parts)
        rows.append(("One case is", f'<ul class="case">{lis}</ul>'))
    rows.append(("A good result", f'<p dir="auto">{h(card["good"])}</p>'))
    if card.get("bad"):
        rows.append(("A bad result", f'<p dir="auto">{h(card["bad"])}</p>'))
    if never:
        rows.append(("It never", f"<ul>{never}</ul>"))
    out = [f'<section class="plan" aria-label="The agent"><h3 dir="auto">{h(card["name"])}</h3><dl>'
           + "".join(f"<div><dt>{t}</dt><dd>{v}</dd></div>" for t, v in rows) + "</dl></section>"]
    if card["needs"]:
        out.append('<div class="needs"><span class="lab">What it needs connected</span>')
        steps = qs_mod.steps(card)
        for n in card["needs"]:
            said, on = need_state(n, data)
            waits = "" if on else "".join(f"<small>{h(STEP_WAIT.format(thing=t, done=d))}</small>" for t, d in steps
                                          if qs_mod.step_need(card, (t, d)) is n)
            out.append(f'<div class="file{" on" if on else ""}"><span class="fi">'
                       f'{icon("check" if on else "plus")}</span><div><b dir="auto">{h(n["what"])}</b>'
                       f"<small>{h(said)}</small>{waits}</div><span></span></div>")
        out.append("</div>")
    out.append(sample_line(data))
    return "".join(out)


CLIMB = ('<svg class="climb" viewBox="0 0 400 130" role="img" aria-label="On its way to its trust level">'
         '<path d="M210 74 C 280 54, 340 30, 384 18" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2" '
         'stroke-linecap="round" stroke-dasharray="1 7"/><path d="M8 118 C 70 116, 120 100, 210 74" fill="none" '
         'stroke="#fff" stroke-width="2.5" stroke-linecap="round"/><circle cx="210" cy="74" r="6" fill="#fff"/>'
         '<circle cx="384" cy="18" r="3.5" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.5"/></svg>')


def _cap(t):
    t = str(t or "").rstrip(".")
    return t[:1].upper() + t[1:]


def correct_this(ctx, agent, fix_ctx=None):
    """Correct this, under a reply the agent lost a practice match on: the same correction as the box on
    the agent's page (Morning.correct, a hotfix through the short exam), sent from beside the reply it
    is about; the answer shows on the agent's page, on the same demo day or Live tab (ctx["q"]), so the
    correction runs on the database the user was looking at."""
    return (f'<details class="fix"><summary>{icon("loop")}Correct this</summary><form method="post" action="/correct">'
            f'{_hidden(fix_ctx or dict(ctx, path=f"/agents/{agent}"), agent=agent)}<div class="box"><textarea name="line" '
            f'aria-label="What it should do here" placeholder="What should it do here?" maxlength="{mo.MAX_LEN}" '
            f'dir="auto" required></textarea></div><div class="say-f"><p class="quiet">{SAY_NOTE}</p>'
            f'<button class="send" type="submit">Send{icon("arrow")}</button></div></form></details>')


def arena_parts(m, agent, ctx, back=None, fix_ctx=None):
    """The newest Arena run saved next to the database for this agent, as (the climb card, the match
    tiles, Try again). The matches it lost are tiles with why; no total of won and lost (the trust
    level stays private, DECISIONS item 17). back: where Try again returns; fix_ctx: the ctx Correct
    this sends from (its answer shows there)."""
    arena, _ = m.read_arena()
    run = arena.get(agent) if agent else None
    tok = ctx["token"] if agent and agent in m.lessons else None
    tried = {r["card"]: r for r in ((run or {}).get("retry") or {}).get("results") or [] if r["result"] != "not_played"}
    tiles, seen = [], set()
    for x in (run or {}).get("lost") or []:  # one tile a practice case and line; the card's id is never shown
        again = tried.get(x["card"])
        key = x["card"] if again else (x["card"], x["text"])  # a retried case: one tile, its newest result
        if key in seen:
            continue
        seen.add(key)
        why, text, res, cls = x["why"], x["text"], "Lost", "lost"
        if again and again["result"] == "won":
            res, cls = "Won again", "won"
        elif again:
            why, text, res = again["why"], again["text"], "Still lost"
        quote = f'<p class="out" dir="auto">"{h(text)}"</p>' if text else ""
        fix = correct_this(ctx, agent, fix_ctx) if tok and text and cls == "lost" else ""
        tiles.append(f'<article class="tile {cls}"><div class="t-h"><span class="pav">{icon("chat")}</span><div>'
                     f'<b>Practice case</b><small>Made up for the Arena</small></div><span class="res">{res}</span>'
                     f'</div><p class="persona" dir="auto">{h(_cap(why))}.</p>{quote}{fix}</article>')
    if not tiles:
        tiles.append('<div class="ghost"><span class="pav" aria-hidden="true"></span>No saved practice run yet.</div>')
    retry = try_again(m, agent, run, ctx, back) if (run or {}).get("lost") else ""
    when = f'Newest run, {mo._when(run["at"])}.' if run else "No saved run yet."
    glow = ('<section class="a-climb" aria-label="How close it is"><article class="glow sq">'
            '<div class="glow-h"><span class="gchip">In the Arena</span><span class="gsub">practising on made-up '
            f'cases</span></div>{CLIMB}<div class="climb-l"><span>Started</span><span>Ready to go live</span></div>'
            f'<p class="calm">{h(when)} Nothing to do here while it practises.</p></article></section>')
    return glow, "".join(tiles), retry


def build(m, agent, ctx):
    """The Arena screen of an agent (/new/build?agent=): the climb as a path, the matches it lost as
    tiles with why. The agent page's Arena tab shows the same parts."""
    arena, _ = m.read_arena()
    run = arena.get(agent) if agent else None
    title = f"Building your {name(agent).lower()}" if agent else "Building your agent"
    glow, tiles, retry = arena_parts(m, agent, ctx)
    when = f'Newest run, {mo._when(run["at"])}.' if run else "No saved run yet."
    glow = glow.replace(f"{h(when)} Nothing to do", "Nothing to do")
    return (f'<div class="qs"><section class="top"><div><h1>{h(title)}</h1><p class="num">{h(when)}</p></div></section>'
            f'<div class="s2">{glow}'
            '<section class="a-matches" aria-labelledby="m-h"><div class="sec-h"><h2 id="m-h">Practice matches</h2>'
            f'<small>Where it slipped</small></div><div class="tiles">{tiles}</div>{retry}</section></div></div>')


TRY_SAID = "Plays only the matches it lost again, with your corrections. A few minutes."


def try_again(m, agent, run, ctx, back=None):
    """Try again under the practice matches (Morning.try_again, arena/retry.py): the button while no try
    runs and the page has a token, "Trying again..." while one runs, and a line when the last one could
    not run or stopped early. The Sales agent only; any other agent shows it greyed out, like Pull."""
    if agent != mo.SALES.agent or agent not in m.lessons:
        return (f'<div class="act"><button class="gb" type="button" disabled title="Not built for this agent yet">'
                f'{icon("loop")}Try again</button></div>') if ctx["token"] else ""
    trying = getattr(m, "trying", None)
    if trying is not None and trying(agent):
        return '<div class="act"><p class="no-yet" role="status">Trying again...</p></div>'
    out = []
    note = getattr(m, "try_note", lambda a: None)(agent)
    if note:
        out.append(f'<p class="no-yet" role="status">{h(note)}</p>')
    elif ((run or {}).get("retry") or {}).get("stopped"):
        out.append('<p class="no-yet">The last try stopped before it played every match; the rest show as they were.</p>')
    if ctx["token"]:
        back = back or f"/new/build?agent={agent}" + (f"&{ctx['q'][1:]}" if ctx["q"] else "")
        out.append(f'<p class="quiet">{TRY_SAID}</p>'
                   + _post(ctx, "tryagain", f'{icon("loop")}Try again', "yes", agent=agent, back=back))
    return f'<div class="act">{"".join(out)}</div>' if out else ""
