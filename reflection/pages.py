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
                   DECISIONS item 77), else In practice; real chats are history, never the switch.
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

    /try/<agent>   the page chat on the Live tab of every agent with an agent folder (built here or by /new, an
                   example, the personal assistant), cloned from Try Sales (reflection/try_sales.py TryAgent): its
                   real turn and tools on sample data, nothing sent; /try/<agent>/clear starts over and
                   /try/<agent>/correct (Use my version) sends the user's rewrite of a draft through Morning.correct.

A correction sent on an agent's page that is high risk waits for a yes on Today (Morning.correct); its
card says why in one plain sentence (plain_risk), never the engine's word lists, and the Hotfix chip
marks a correction that runs in the chats. With demo days each day shows its own morning (day.json); with --db too a Live tab follows the days and
serves the real database with real answers and the real clock, never marked Sample data.

No count of what is left anywhere (item 35), no trust level and no won and lost total (item 17,
LOCKS Quick start B), apart from the Arena tab's summary card, which names the last run's wins of its matches (DECISIONS 104). No script, except the build page's one hashed script (NEW_SCRIPT, its poll and
countdown) and, on an agent's page, the one poll (ARENA_SCRIPT) that follows Run the Arena, Train and Run reflection
while they run: Modify is a details element inside its card. Every field is
escaped. With demo days (--demo-days) a Day 1, Day 2, Day 3 switch sits on top, marked Sample
data (Sample on the phone bar, so every label stays on one line at 390); each day is its own throwaway copy, so answers there never touch the sample files.
"""
import base64
import hashlib
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

from arena import levels as levels_mod
from engine import lessons as lessons_mod
from kit import sample as sample_mod
from reflection import console as console_mod
from reflection import morning as mo
from reflection import quickstart as qs_mod
from reflection import reflect_now
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
# The page chat of an agent with an agent folder (Pages.action_for, try_mod.TryAgent): send, Start over, Use my version
_TRY = re.compile(r"^/try/([a-z][a-z_]{0,30})(/clear|/correct)?$")
MINE = "The user rewrote your draft as: {text}"  # Use my version, the correction it sends (Morning.correct)
MINE_ROOM = mo.MAX_LEN - len(MINE.format(text=""))  # characters of the user's own version a correction holds
CHAT_LINE = "Write to it, or paste what it works on, and it answers with its own tools on sample data. Nothing is sent."
MINE_NOTE = (f"Your version goes to the agent as a correction, at most {MINE_ROOM} characters. It takes the short exam "
             "first, the same way as the box on Overview.")
MINE_HINT = f"This draft is longer than {MINE_ROOM} characters. Write the line you would change."
MINE_SAME = "Change the draft first, then press Use my version."
# Bytes in one POST to /try/<agent> (morning.py do_POST): a message of MAX_PASTE characters of 3 bytes each, which
# the form sends as 9 (%E2%80%9C), and room for the other fields, so a long paste gets the chat's own refusal
MAX_TRY_BODY = try_mod.MAX_PASTE * 9 + 4096
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


# The agent page's one script (Run the Arena and Run reflection), allowed by its hash in the /agents/<name>
# policy only: while a run goes it fetches the page again with the X-Poll header, as the build page does, and
# swaps each part marked data-live (arena, reflect) and data-running until its run is over; when that part is
# gone (Overview once an Arena run is saved), and when a reflection ends (its lessons show elsewhere on the
# page too), it loads the page again. A swap keeps each Correct this (data-keep) that is open, holds text or has
# the focus, as it is, and each chat (details data-chat) open or closed as the user left it.
ARENA_SCRIPT = """(function(){
var T=2000;function q(d,s){return d.querySelector(s)}
function byKey(el,a,v){var xs=el.querySelectorAll('['+a+']');for(var i=0;i<xs.length;i++)if(xs[i].getAttribute(a)===v)return xs[i];return null}
function swap(el,n){var keep=[],ks=el.querySelectorAll('[data-keep]'),op={},cs=el.querySelectorAll('details[data-chat]'),j,o,t;
for(j=0;j<ks.length;j++){o=ks[j];t=o.querySelector('textarea');if(o.open||(t&&t.value)||o.contains(document.activeElement))keep.push(o)}
for(j=0;j<cs.length;j++)op[cs[j].getAttribute('data-chat')]=cs[j].open;
el.innerHTML=n.innerHTML;
for(j=0;j<keep.length;j++){o=byKey(el,'data-keep',keep[j].getAttribute('data-keep'));if(o)o.replaceWith(keep[j]);else(el.querySelector('.tiles')||el).appendChild(keep[j])}
cs=el.querySelectorAll('details[data-chat]');for(j=0;j<cs.length;j++){t=cs[j].getAttribute('data-chat');if(op.hasOwnProperty(t))cs[j].open=op[t]}}
function poll(){var els=document.querySelectorAll('[data-live][data-running]');if(!els.length)return;
fetch(location.href,{headers:{'X-Poll':'1'},credentials:'same-origin',cache:'no-store'}).then(function(r){return r.ok?r.text():null}).then(function(t){if(!t)return;
var d=new DOMParser().parseFromString(t,'text/html');for(var i=0;i<els.length;i++){var el=els[i],k=el.getAttribute('data-live'),n=q(d,'[data-live="'+k+'"]');
if(!n||(k==='reflect'&&!n.hasAttribute('data-running'))){location.reload();return}
swap(el,n);if(!n.hasAttribute('data-running'))el.removeAttribute('data-running')}}).catch(function(){}).then(function(){
if(q(document,'[data-live][data-running]'))setTimeout(poll,T)})}
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
        self.level = None             # the risk level picked on the card (arena/levels.py), None: its suggestion

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
              "amount": "it states an amount of money", "discount": "it offers a discount or something free",
              "payment": "it changes how the customer pays",
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
    MAX_TRY_BODY = MAX_TRY_BODY  # the server's cap on a POST to /try/<agent> (morning.py do_POST)

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
        # the same chat on the page of every agent with an agent folder (try_mod.TryAgent, cloned from Try Sales):
        # one per agent, made the first time that agent's chat is used (chat), never for a name the page lacks
        self.try_model = try_model
        self.try_agents = {}
        # the page's own answers, taken by the server next to morning.TWO_TAB_ACTIONS
        self.actions = {"/quickstart": lambda m, f, now=None: self._say(m, mo._field(f, "text"), now),
                        "/quickstart/build": lambda m, f, now=None: self._build(m, now, _level(f)),
                        "/quickstart/clear": lambda m, f, now=None: self._clear(m, now),
                        # Try Sales on the Sales agent's page (reflection/try_sales.py): the demo store, never counts
                        "/try/sales": lambda m, f, now=None: self._try(self.try_sales.say, m, now, mo._field(f, "text")),
                        "/try/sales/clear": lambda m, f, now=None: self._try(self.try_sales.clear, m, now),
                        # the console's Operator correction: the same path as the agent page's (Morning.correct)
                        "/console/correct": lambda m, f, now=None: m.correct(mo._field(f, "agent"), mo._field(f, "line"),
                                                                             now=now, by=console_mod.OPERATOR),
                        # Run the Arena on an agent's page (Morning.run_arena), always the full run (DECISIONS
                        # 104), refused while it builds
                        ARENA_PATH: lambda m, f, now=None: self._arena(m, mo._field(f, "agent"), now),
                        # Train on the Arena tab (Morning.run_train, DECISIONS 104), refused as Run the Arena is
                        mo.TRAIN_PATH: lambda m, f, now=None: self._arena(m, mo._field(f, "agent"), now, train=True),
                        # Stop a running Train or Run reflection (Morning.stop_run, DECISIONS 98)
                        mo.STOP_PATH: lambda m, f, now=None: m.stop_run(mo._field(f, "agent"), now=now),
                        # Edit an existing lesson as a new version that replaces it only on a pass (DECISIONS 100)
                        mo.REVISE_PATH: lambda m, f, now=None: m.revise(mo._field(f, "lesson"), mo._field(f, "line"),
                                                                       now=now),
                        # Run reflection on the Overview (Morning.run_reflection), with the same refusals
                        REFLECT_PATH: lambda m, f, now=None: self._reflect(m, mo._field(f, "agent"), now)}

    def action_for(self, path):
        """The answer for a POST path the actions table does not hold: /try/<agent>, /try/<agent>/clear and
        /try/<agent>/correct (Use my version), the page chat of an agent with an agent folder (chat). None for any
        other path and for a name no agent on the page has (the server says Not found); Sales keeps its own routes."""
        hit = _TRY.match(path or "")
        if hit is None or hit.group(1) == mo.SALES.agent:
            return None
        agent, what = hit.group(1), hit.group(2) or ""
        if not any(agent in getattr(x, "plugs", {}) for x in self._mornings()):
            return None
        if what == "/clear":
            return lambda m, f, now=None: self._try(lambda mm, now=None: self.chat(mm, agent).clear(mm, now), m, now)
        if what == "/correct":
            return lambda m, f, now=None: self._mine(m, agent, mo._field(f, "text"), now)
        return lambda m, f, now=None: self._try(lambda mm, text, now=None: self.chat(mm, agent).say(mm, text, now),
                                                m, now, mo._field(f, "text"))

    def _mornings(self):
        return [x for x in (self.morning, self.live, *self.days.values()) if x is not None]

    def chat(self, m, agent):
        """The page chat of agent on m (try_mod.TryAgent), made the first time: only for an agent on m, other than
        Sales, with an agent folder (Morning.agent_folder: built here or by /new, an example, or a repo agent on
        the built path); else Refused."""
        if not self.has_chat(m, agent):
            raise try_mod.Refused(try_mod.NOT_HERE.format(agent=agent if _AGENT.match(str(agent)) else "that"))
        got = self.try_agents.get(agent)
        if got is None:
            got = self.try_agents[agent] = try_mod.TryAgent(agent, self.try_model)
        return got

    @staticmethod
    def has_chat(m, agent):
        """Does agent get the page chat on m: any agent on it, other than Sales (Try Sales), with an agent folder."""
        if not isinstance(agent, str) or agent == mo.SALES.agent or agent not in getattr(m, "plugs", {}):
            return False
        return hasattr(m, "agent_folder") and m.agent_folder(agent) is not None

    def _mine(self, m, agent, text, now):
        """Use my version: the user's rewrite of a draft in the page chat, a correction down the same exam and
        hotfix path as the box on Overview (Morning.correct, by the user)."""
        box = self._try(lambda mm, now=None: self.chat(mm, agent), m, now)
        words = " ".join(str(text or "").split())
        if not words:
            raise mo.Refused("Write your version first.")
        if words in {" ".join(str(r).split()) for t in box.thread() for r in t["replies"]}:
            raise mo.Refused(MINE_SAME)  # the agent's own draft unchanged is not the user's version
        line = MINE.format(text=words)
        if len(line) > mo.MAX_LEN:
            raise mo.Refused(f"Your version is {len(words)} characters. A correction holds at most {MINE_ROOM}, so "
                             "keep the part that matters.")
        return m.correct(agent, line, now=now, by=mo.BY)

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
        if path.startswith("/agents/") and _AGENT.match(path[8:]) and (self.made_here(path[8:])
                                                                     or self.reflects(path[8:])):
            return AGENT_CSP  # the page of an agent made here or one Run reflection serves: the poll
        return console_mod.csp() if path == "/console" else NEW_CSP if path == "/new" else self.csp

    def made_here(self, agent):
        """Is agent one Quick start made, on the page's own morning (its folder beside the database)? Only
        its page carries Run the Arena, so only its page is sent the policy that allows ARENA_SCRIPT."""
        for m in (self.morning, self.live):
            folder = getattr(m, "agent_folder", None)
            if folder is not None and folder(agent) is not None:
                return True
        return False

    def reflects(self, agent):
        """Does the page's own morning (or Live) carry Run reflection for agent: an agent on it, with the
        database folder? Its page is then sent the policy that allows ARENA_SCRIPT too."""
        for m in (self.morning, self.live):
            if hasattr(m, "run_reflection") and getattr(m, "db_path", None) is not None and agent in m.plugs:
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

    def _build(self, m, now, level=None):
        """Build (LOCKS "App pages", 2A): the cheap refusals at once, then the build in a thread whose
        steps the thread on /new ticks off; inline with a test's model, returning the flash as before.
        The new agent joins the running page (Morning.add_built) on the server's thread (settle)."""
        run = self.run
        if run is not None and run.m is m and run.running:
            raise mo.Refused("It is building already. The steps tick off below.")
        self._quick(lambda mm, now=None: self.quick.check_build(mm), m, now)
        run = self.run = BuildRun(m)
        run.level = level
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
            run.said = self.quick.build(run.m, now, step=run.step, lock=run.lock, level=run.level)
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

    def _arena(self, m, agent, now, train=False):
        """Run the Arena, always the full run (Morning.run_arena full, DECISIONS 104), or Train (Morning.run_train),
        refused while a build on this page may be writing the agent and while the first Arena run Build started
        for it still runs."""
        run = self.run
        then = mo.TRAIN_BUTTON if train else "Run the Arena"
        if run is not None and run.m is m and run.running and run.agent in (None, agent):
            raise mo.Refused(f"It is building. {then} once the build is done.")
        if self.quick.practising(agent):
            raise mo.Refused(f"{qs_mod.FIRST_RUNNING} {then} once it ends.")
        if not hasattr(m, "run_arena"):
            raise mo.Refused(mo.ARENA_NOT_HERE)
        if train:
            return m.run_train(agent, now=now)
        return m.run_arena(agent, now=now, full=True)

    def _reflect(self, m, agent, now):
        """Run reflection (Morning.run_reflection), refused as Run the Arena is: while a build on this page
        may be writing the agent and while the first Arena run Build started for it still runs."""
        run = self.run
        if run is not None and run.m is m and run.running and run.agent in (None, agent):
            raise mo.Refused("It is building. Run reflection once the build is done.")
        if self.quick.practising(agent):
            raise mo.Refused(f"{qs_mod.FIRST_RUNNING} Run reflection once it ends.")
        if not hasattr(m, "run_reflection"):
            raise mo.Refused(mo.REFLECT_NOT_HERE)
        return m.run_reflection(agent, now=now)

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
               "chat": self.chat_html, "look": looked_at(m, path, query), "query": query}
        if path == "/":
            return self.shell(today(m.view(now=now), ctx), "today", ctx, flash)
        if path == "/agents":
            return self.shell(agents(m, m.view(now=now), ctx), "agents", ctx, flash)
        if path.startswith("/agents/") and _AGENT.match(path[8:]):
            body = agent_page(m, m.view(now=now), path[8:], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash,
                                                        script=ARENA_SCRIPT if 'data-live="' in body
                                                        and (self.made_here(path[8:]) or self.reflects(path[8:]))
                                                        else None)
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

    def chat_html(self, ctx, agent):
        """The page chat of an agent with an agent folder (TryAgent, cloned from try_html): the thread as written,
        each reply with the tools it used and Edit this draft (Use my version, a correction), the box, Send and
        Start over, and what it runs on. Empty for an agent with no chat here."""
        m = ctx["m"]
        if not self.has_chat(m, agent):
            return ""
        t = self.try_agents.get(agent)  # made the first time the chat is used (chat)
        kit = m.case_kit(agent) if hasattr(m, "case_kit") else None
        who = name(agent)
        rows = []
        for turn in (t.thread() if t is not None else []):
            rows.append(f'<p class="said me" dir="auto">{h(turn["said"])}</p>')
            for r in turn["replies"]:
                rows.append(f'<p class="said ag" dir="auto">{h(r)}</p>')
                if ctx["token"]:
                    draft = " ".join(str(r).split())  # as Use my version reads it; empty with a hint when too long
                    fill, hint = (draft, "") if len(draft) <= MINE_ROOM else ("", f' placeholder="{h(MINE_HINT)}"')
                    rows.append(f'<details class="mine"><summary>Edit this draft</summary><form method="post" '
                                f'action="/try/{h(agent)}/correct">{_hidden(ctx)}<div class="box"><textarea name="text" '
                                f'aria-label="Your version of the draft" maxlength="{MINE_ROOM}" dir="auto" required'
                                f'{hint}>{h(fill)}</textarea></div>'
                                f'<div class="say-f"><p class="quiet">{icon("loop")}{MINE_NOTE}</p><button class="send" '
                                f'type="submit">Use my version{icon("arrow")}</button></div></form></details>')
            if turn.get("tools"):
                rows.append(f'<p class="used">Tools used: {h(", ".join(turn["tools"]))}.</p>')
            if not turn["replies"]:
                rows.append(f'<p class="said no">No reply ({h(turn["outcome"].replace("_", " "))}).</p>')
        thread = f'<div class="thread">{"".join(rows)}</div>' if rows else ""
        note = try_mod.AGENT_NOTE.format(name=who) + (f" {kit.CHAT_NOTE}" if getattr(kit, "CHAT_NOTE", None) else "")
        hint = getattr(kit, "CHAT_HINT", None) or "Write to it the way the person it works for would."
        form = ""
        ready = t.ready() if t is not None else try_mod.can_answer(self.try_model)
        if ctx["token"] and ready:
            over = _post(ctx, f"try/{h(agent)}/clear", "Start over", "over") if rows else ""
            form = (f'<form id="try-say" method="post" action="/try/{h(agent)}">{_hidden(ctx)}<div class="box"><textarea '
                    f'name="text" aria-label="Your message to {h(who)}" maxlength="{try_mod.MAX_PASTE}" dir="auto" '
                    f'required placeholder="{h(hint)}"></textarea></div></form><div class="say-f"><p class="quiet">'
                    f'{icon("chat")}{h(note)}</p>{over}<button class="send" type="submit" form="try-say">Send'
                    f'{icon("arrow")}</button></div>')
        elif not ready:
            form = f'<p class="quiet">{try_mod.AGENT_NO_KEY}</p>'
        return (f'<section class="say try sq" aria-label="Talk to {h(who)}"><span class="lab">Talk to {h(who)}</span>'
                f'{thread}{form}</section>')

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


def _taken_agent(flash):
    """The agent a Quick start name clash line names: "There is an agent called X already", or a built-in
    agent's own line (qs_mod.BUILT_IN); None for any other line."""
    taken = _TAKEN.match(flash)
    if taken:
        return taken.group(1)
    return next((agent for agent, (said, _) in qs_mod.BUILT_IN.items() if flash.startswith(said.split(". ")[0] + ".")),
                None)


def flash_html(flash, ctx):
    """The one-time message, escaped. Quick start's "There is an agent called X already" refusal gets
    a link to X's page when X is an agent on this page, so the user can see the one that has the name."""
    if not flash:
        return ""
    link = ""
    agent = _taken_agent(str(flash))
    m = ctx.get("m")
    if agent and _AGENT.match(agent) and m is not None and agent in getattr(m, "plugs", {}):
        link = f' <a href="/agents/{h(agent)}{ctx["q"]}">Open {h(name(agent))}</a>'
    return f'<p class="flash" role="status">{h(flash)}{link}</p>'


# ---- Today -------------------------------------------------------------------------------------

def _hidden(ctx, **kv):
    kv = {"token": ctx["token"], "back": ctx["path"] + ctx["q"], **kv}  # back may be given
    return "".join(f'<input type="hidden" name="{h(k)}" value="{h(v)}">' for k, v in kv.items())


def _level(form):
    """The risk level a form posted: None when it sent none, else one of the three (any other is refused)."""
    if "level" not in form:
        return None
    level = mo._field(form, "level")
    if not levels_mod.valid(level):
        raise mo.Refused("Pick low, medium or high.")
    return level


def _post(ctx, action, button, cls, **kv):
    return (f'<form method="post" action="/{action}">{_hidden(ctx, **kv)}'
            f'<button class="{cls}" type="submit">{button}</button></form>')


def level_picker(ctx, card):
    """The Build form with the risk level picker (decision 84): three choices, one plain line each, the
    level the card suggests picked and marked. Build posts the choice; level.json keeps it."""
    tip = levels_mod.suggest(card)
    rows = []
    for lv in levels_mod.ORDER:
        mark = '<i class="tip">Suggested</i>' if lv == tip else ""
        rows.append(f'<label class="lv"><input type="radio" name="level" value="{lv}"{" checked" if lv == tip else ""}>'
                    f'<span><b>{levels_mod.NAMES[lv]}{mark}</b><small>{h(levels_mod.WORDS[lv])}</small></span></label>')
    return (f'<form method="post" action="/quickstart/build" class="lvlf">{_hidden(ctx)}<fieldset class="lvl">'
            f'<legend>Risk level: how careful it must be before it goes live</legend>{"".join(rows)}</fieldset>'
            f'<button class="yes" type="submit">Build{icon("arrow")}</button></form>')


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
    """Paused while its pause switch is on (Morning.paused), else Live or In practice."""
    if m.paused(agent):
        return "Paused"
    return "Live" if agent in m._live() else "In practice"


# The line under the status on an agent's page.
STATUS_SAID = {"Live": "Working on real cases", "In practice": "Practising in the Arena",
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
                     for s in ("In practice", "Live", "Paused"))
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
    kit = getattr(m, "case_kit", lambda a: None)(agent) if folder is not None else None
    if kit is not None:  # a repo agent on the built path (decision 109): its own data line, no rows box, no offers
        left.append(f'<section class="grp sq" aria-labelledby="sd-h"><h3 id="sd-h">{h(kit.DATA_HEAD)}</h3>'
                    f'<div class="lr"><b>{h(kit.DATA_LINE)}</b></div></section>')
    elif folder is not None:  # an agent made here: its sample data and the box that adds to it
        data = m.sample_data(agent)
        line = sample_mod.words(data) or "No sample data yet. Add rows it can work from."
        using = f"<small>{USING_SAMPLE}</small>" if using_sample(folder, data) else ""
        left.append(f'<section class="grp sq" aria-labelledby="sd-h"><h3 id="sd-h">Sample data</h3><div class="lr">'
                    f'<b dir="auto">{h(line)}</b>{using}<small>Made up for practice until a real connection is set.</small>'
                    '</div></section>')
        if tok:
            left.append(data_form(ctx, agent))
        own = m.offers(agent) if hasattr(m, "offers") else None
        body = (offers_list(own["offers"]) + f'<small>{OFFERS_SAID}</small>' if own and own["offers"]
                else f'<b>{OFFERS_NONE}</b>')
        left.append(f'<section class="grp sq" aria-labelledby="of-h"><h3 id="of-h">{OFFERS_HEAD}</h3><div class="lr">'
                    f'{body}</div></section>')
        if tok:
            left.append(offers_form(ctx, agent))
    if folder is not None and agent not in m.read_arena()[0]:  # no saved run yet: Run the Arena here too, polled
        go = run_arena(m, agent, ctx, ctx["path"] + ctx["q"])
        if go:
            left.append(f'<section class="grp sq" aria-labelledby="ra-h"{arena_live(m, agent)}><h3 id="ra-h">'
                        f'The Arena</h3><small class="quiet">No practice run saved yet.</small>{go}</section>')
    if tok and folder is not None and Pages.has_chat(m, agent):  # the page chat is on Live (Pages.chat_html)
        left.append(f'<section class="grp sq" aria-labelledby="tk-h"><div class="grp-h"><h3 id="tk-h">Talk to '
                    f'{h(name(agent))}</h3><a class="lk" href="{tab_href(ctx, agent, "live")}">Open the chat</a></div>'
                    f'<small class="quiet">{CHAT_LINE}</small></section>')
    learn = run_reflection(m, a, agent, ctx, ctx["path"] + ctx["q"])
    if learn:  # Run reflection beside it, for any agent on the page
        left.append(f'<section class="grp sq" aria-labelledby="rf-h"{reflect_live(m, agent)}><h3 id="rf-h">'
                    f'Reflection</h3>{learn}</section>')
    if tok:
        left.append(f'<section class="say sq" id="say" aria-label="Send an idea or a correction"><form method="post" action="/correct">'
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
    """Arena (DECISIONS 99, 100 and 104). On top: the status line and the track (Run the Arena, Train, Connect)
    with one next step lit, or Ready to connect with Connect; Run the Arena, always the full run, and while it
    runs how many matches it played; the stuck card's next step. Then the card of a newest full run that did
    not pass (train_card): won N of M, the main reasons it lost and what its quick notes did, with Train (and,
    while Train runs, each lesson as it takes its exam, with Stop) and the correction box right under it; before
    any run the box stands alone. Then the practice matches of its newest run, a lost one with Correct this (into
    the exam), and Try again, beside the climb; and its lessons with Edit. While a run or a Train goes the poll
    swaps each part marked data-live; the correction box sits outside them, so typing is never lost. Answers
    come back to this tab."""
    c = tab_ctx(ctx, agent, "arena")
    able = arena_able(m, agent)
    running = able and m.arena_running(agent)
    so = m.arena_so_far(agent) if running and hasattr(m, "arena_so_far") else None
    now = None
    if running:  # the dark card says the run is going, never "No saved run yet" while it plays
        now = so if so is not None else {"played": m.arena_played(agent), "won": 0}
    glow, tiles, retry = arena_parts(m, agent if agent in m.plugs else None, c, back=c["path"] + c["q"],
                                     fix_ctx=c, so_far=now)
    go = run_arena(m, agent, c, c["path"] + c["q"]) if able else ""
    track = arena_track(m, agent, c) if able else ""
    learn = ""
    if agent in m.plugs and hasattr(m, "next_step") and not (hasattr(m, "training") and m.training(agent)):
        learn = mo.next_step_html(m.next_step(agent), agent)  # the one next step under a run that did not pass
    item = m.read_arena()[0].get(agent)
    level = level_card(m, agent, item, c, c["path"] + c["q"])
    said = mo.offer_lines(item) if item else []
    if said:  # the store team's real rate and the wins as sales and closes (decision 105): report only
        level = "".join(f'<p class="quiet" role="note">{h(x)}</p>' for x in said) + level
    card = train_card(m, a, agent, c) if able else ""
    top = arena_live(m, agent) if able else ""
    low = arena_live(m, agent, "tiles") if able else ""
    side = arena_live(m, agent, "side") if able else ""
    sub = "Where it slipped"
    if running and hasattr(m, "arena_so_far"):  # the matches as they land, polled
        fix = c if c["token"] and agent in getattr(m, "lessons", {}) else None  # Correct this, as arena_parts
        tiles, retry, sub = so_far_tiles(so, agent, fix), "", SO_FAR_SUB
    # one grid (page_css .arg): the correction box and the practice matches in the main column, the risk level
    # and the dark card in the side column, both from the same top line; one column on a phone
    return (f'<div class="qs arq"><div{top}>{track}{go}{learn}</div><div class="arg"><div class="arg-c">{card}</div>'
            f'<div class="arg-m"{low}><section class="ar-l" '
            f'aria-labelledby="m-h"><div class="sec-h"><h2 id="m-h">Practice matches</h2><small>{sub}'
            f'</small></div><div class="tiles">{tiles}</div>{retry}</section></div>'
            f'<div class="arg-s"{side}>{level}{glow}</div></div></div>')


def arena_able(m, agent):
    """True when Run the Arena is for this agent here: an agent made here, or the Sales agent with the
    database folder (Morning.run_arena)."""
    if not hasattr(m, "run_arena"):
        return False
    sales = agent == mo.SALES.agent and agent in m.plugs and getattr(m, "db_path", None) is not None
    return m.agent_folder(agent) is not None or sales


def arena_track(m, agent, ctx):
    """The status line and the track (Morning.arena_status, DECISIONS 104): Run the Arena, Train, Connect, the
    next one lit and the others ticked when done, with Ready to connect and Connect on a pass. Empty once the
    agent is live, or with no status."""
    status = m.arena_status(agent) if hasattr(m, "arena_status") else None
    if status is None:
        return ""
    steps, shown = [], status.get("steps") or ("arena", "train", "connect")  # no Connect with no live channel
    for key, word, done in (("arena", mo.ARENA_BUTTON, status["ran"]), ("train", mo.TRAIN_BUTTON, status["trained"]),
                            ("connect", mo.CONNECT_WORD, False)):
        if key not in shown:
            continue
        cls = "next" if status["next"] == key else "done" if done else ""
        steps.append(track_step(len(steps) + 1, word, cls))
    kit = m.case_kit(agent) if hasattr(m, "case_kit") else None
    connect = getattr(kit, "CONNECT_STEP", None)
    if connect:  # a repo agent on the built path whose channel is next (the assistant's email): a step, no button
        steps.append(track_step(len(steps) + 1, connect, "soon"))  # next to build, so never lit as the next step
    out = [f'<p class="stl" role="status">{h(status["line"])}</p>',
           f'<ol class="trk" aria-label="Arena steps">{"".join(steps)}</ol>']
    if connect:
        out.append(f'<p class="trkc"><b>{h(connect)}.</b> {h(kit.CONNECT_LINE)}</p><p class="trkl"><a class="lk" '
                   f'href="{tab_href(ctx, agent, "live")}">Open the chat</a></p>')
    if status["ready"] and agent in m.plugs:
        conns = m.connection_view(agent)
        if conns:
            out.append(connections_html(agent, conns, ctx, ctx["token"]))
    return f'<div class="trkw">{"".join(out)}</div>'


def track_step(n, word, cls=""):
    """One step of the track, read as a step and never as a button: its number in a small circle (a tick when
    done), its word, and Next or Done in words for a screen reader; the line between steps is the style's."""
    mark = icon("check") if cls == "done" else str(n)
    said = {"next": "Next", "done": mo.DONE_WORD, "soon": "Later"}.get(cls)
    tail = f'<small class="vh">, {said}</small>' if said else ""
    attr = f' class="{cls}"' if cls else ""
    return (f'<li{attr}><span class="n" aria-hidden="true">{mark}</span>'
            f'<span class="w">{h(word)}</span>{tail}</li>')


def summary_html(s):
    """The summary of a newest full run that did not pass (Morning.arena_summary): won N of M, each main
    reason it lost with its count, and the quick notes line when its report has notes. Counts only."""
    out = [f'<p class="stl">{h(mo.SUMMARY_HEAD.format(won=s["won"], played=s["played"]))}</p>']
    if s["reasons"]:
        rows = "".join(f"<li>{h(words)}: {n}</li>" for words, n in s["reasons"])
        out.append(f'<ul class="rsn" aria-label="{h(mo.SUMMARY_LABEL)}">{rows}</ul>')
    notes = s.get("notes")
    if notes is not None:
        line = mo.HOTFIX_LINE.format(written=_plural(notes["written"], "quick note"), stopped=notes["stopped"])
        out.append(f'<p class="quiet">{h(line)}</p>')
    return "".join(out)


def train_card(m, a, agent, ctx):
    """The card under the top of the Arena tab (DECISIONS 100 and 104). Its part the poll swaps (data-live
    train): the summary of a newest full run that did not pass (summary_html) with Train, lit when it is the next
    step, and its line; while Train runs, the Reflecting line with each lesson as it takes its exam and Stop
    (live_view); what the last Train did. Nothing of it while Run the Arena runs. Right under it, outside the
    swapped part so typing is never lost, the correction box (Morning.correct, the hotfix with its exam first),
    open any time; then the agent's live lessons, each with Edit (Morning.revise: a new version that replaces it
    only if it passes the exam). With no token: the summary only."""
    if agent not in m.plugs:
        return ""
    inner = []
    step = m.training(agent) if hasattr(m, "training") else None
    if step is not None:
        summary = m.arena_summary(agent) if hasattr(m, "arena_summary") else None
        if summary is not None:
            inner.append(summary_html(summary))
        inner.append(f'<div class="act">{reflect_running(step)}</div>{live_view(m, agent, ctx)}')
    elif not m.arena_running(agent):
        summary = m.arena_summary(agent) if hasattr(m, "arena_summary") else None
        if summary is not None:
            inner.append(summary_html(summary))
        done = m.trained(agent) if hasattr(m, "trained") else None
        if done is not None:
            inner.append(trained_html(done))
        if summary is not None and summary["lost"] and ctx["token"]:  # Train only on a run that lost matches
            nxt = (m.arena_status(agent) or {}).get("next") if hasattr(m, "arena_status") else None
            inner.append('<div class="act stk">' + _post(ctx, mo.TRAIN_PATH[1:], f'{icon("flask")}{mo.TRAIN_BUTTON}',
                                                     "yes" if nxt == "train" else "gb", agent=agent,
                                                     back=ctx["path"] + ctx["q"])
                         + f'<p class="quiet nt">{h(mo.TRAIN_SAID)}</p></div>')
    part = f'<div{arena_live(m, agent, "train")}>{"".join(inner)}</div>'
    box = ""
    if ctx["token"]:
        box = (f'<form method="post" action="/correct">{_hidden(ctx, agent=agent)}<span class="lab">Send an idea or a '
               f'correction</span><div class="box"><textarea name="line" aria-label="Your idea or correction" '
               f'maxlength="{mo.MAX_LEN}" dir="auto" required></textarea></div><div class="say-f"><p class="quiet">'
               f'{icon("loop")}{SAY_NOTE}</p><button class="send" type="submit">Send{icon("arrow")}</button></div></form>')
    if not inner and not box:
        return part
    rows = []
    for i in (a.get("live") or []) if ctx["token"] else []:
        rows.append(f'<div class="lr"><b dir="auto">{h(i["text"])}</b><details class="mx"><summary class="mod">'
                    f'{icon("pen")}{mo.REVISE_BUTTON}</summary><div class="edit"><form method="post" '
                    f'action="{mo.REVISE_PATH}">{_hidden(ctx, lesson=i["id"])}<textarea name="line" '
                    f'aria-label="{mo.REVISE_FIELD}" maxlength="{mo.MAX_LEN}" dir="auto" required>{h(i["text"])}'
                    f'</textarea><button class="yes" type="submit">{mo.REVISE_SAVE}</button></form>'
                    f'<p class="quiet">{h(mo.REVISE_SAID)}</p></div></details></div>')
    edits = (f'<section class="grp sq" aria-labelledby="ed-h"><h3 id="ed-h">{mo.EDITS_HEAD}</h3>{"".join(rows)}</section>'
             if rows else "")
    return (f'<div class="trc"><section class="say sq" aria-label="Send an idea or a correction">{part}{box}</section>'
            f'{edits}</div>')


LEVEL_HELP = "Correct a lost reply and press Try again, add sample data on the Overview, or lower the level."
# the help when the wins reached the level and a broken never line held it: no level allows one (decision 110)
SAFETY_HELP = "Correct a lost reply and press Try again, or add sample data on the Overview."


def level_card(m, agent, run, ctx, back):
    """The risk level of an agent made here on its Arena tab (decision 84): its newest run's test wins
    against what its level needs ("N of 10, your level needs M"), each round's score, what holds it below
    the level (the item's blocks) with what the owner can do, and Keep, Lower and Raise (Morning
    set_risk_level, which never starts a run). Empty for any other agent."""
    folder = m.agent_folder(agent) if hasattr(m, "set_risk_level") else None
    if folder is None:
        return ""
    level = levels_mod.read(folder)
    rule = levels_mod.LEVELS[level]
    out = [f'<div class="grp-h"><h3 id="lv-h">Risk level: {levels_mod.NAMES[level]}</h3></div>']
    size = (run or {}).get("gate_size") or (run or {}).get("gate_played")
    if run and run.get("gate_won") is not None and size:
        need = levels_mod.needs(level, size)
        if size < rule["gate"]:  # a smaller run than the level's gate: the level asks for a new run (Morning.gate)
            need = f'{levels_mod.needs(level)} of {rule["gate"]}'
        safe = (" with no failed safety check; a broken never line fails it" if rule["no_failed_checks"]
                else "; a broken never line fails it")
        played = run.get("gate_played")
        short = played is not None and played < size  # cut short (the cap, or a match left unjudged)
        unjudged = run.get("unjudged") or 0  # the last round's test matches the judge could not read
        why = (f'{"one test match" if unjudged == 1 else f"{unjudged} test matches"} could not be judged'
               if unjudged else f"the run stopped before all {size}")
        score = (f'<b>{run["gate_won"]} won of {played} played</b> ({why})' if short
                 else f'<b>{run["gate_won"]} of {size}</b>')
        out.append(f'<p class="score">{score}, your level needs {need}{safe}</p>')
        gate = m.gate(agent)
        out.append(f'<p class="calm">{h(gate["said"])}</p>')
        scores = run.get("scores") or []
        rows = "".join(f'<li><span>Round {i}</span><b>{n} of {played if short and i == len(scores) else size}</b></li>'
                       for i, n in enumerate(scores, 1))
        if rows:
            out.append(f'<ol class="rnd" aria-label="Each round">{rows}</ol>')
        if not gate["passed"]:
            blocks = "".join(f'<li dir="auto">{h(b["line"])}</li>' for b in run.get("blocks") or [])
            if blocks:
                out.append(f'<p class="lab">What holds it back</p><ul class="blk">{blocks}</ul>')
            if not unjudged:  # a match left unjudged needs only a new run; the help's steps cannot pass it
                held = levels_mod.safety_only(level, run.get("gate_won"), size, run.get("never_broken"))
                out.append(f'<p class="quiet">{SAFETY_HELP if held else LEVEL_HELP}</p>')
    else:
        out.append(f'<p class="calm">{h(levels_mod.WORDS[level])} Its first Arena run shows the score against it.</p>')
    if ctx["token"]:
        ways = [(level, f"Keep {level}", "lb on")]
        for way, word in (("lower", "Lower to"), ("raise", "Raise to")):
            to = levels_mod.step(level, way)
            if to != level:
                ways.append((to, f"{word} {to}", "lb"))
        out.append('<div class="lvb">' + "".join(_post(ctx, mo.LEVEL_PATH[1:], h(label), cls, agent=agent, level=to,
                                                     back=back) for to, label, cls in ways) + '</div>')
    return f'<section class="grp sq lvc" aria-labelledby="lv-h">{"".join(out)}</section>'


ARENA_PATH = "/arena/run"
ARENA_SAID = "Plays its practice matches against made-up customers, with its sample data."


def arena_live(m, agent, key="arena"):
    """The marks the agent page's script polls (ARENA_SCRIPT): data-live key, and data-running while a run or
    a Train goes."""
    running = m.arena_running(agent) or (hasattr(m, "training") and m.training(agent) is not None)
    return f' data-live="{key}"' + (" data-running" if running else "")


def run_arena(m, agent, ctx, back):
    """Run the Arena (Morning.run_arena, always the full run, DECISIONS 104) for an agent made here or the Sales
    agent with the database folder: its button, Run the Arena again after a full run that did not pass, lit when
    it is the next step (Morning.arena_status), with its line, while no run or Train goes and the page has a
    token; while it runs, how many matches it played; and a line when the last run or Train could not finish.
    Empty for any other agent."""
    if not arena_able(m, agent):
        return ""
    sales = agent == mo.SALES.agent
    if m.arena_running(agent):
        n = m.arena_played(agent)
        said = (f"Running the Arena: {n} practice {'match' if n == 1 else 'matches'} played so far." if n
                else "Running the Arena: its first matches are starting.")
        if not ctx["token"]:  # Stop while it runs (Morning.stop_run): it ends before its next matches
            return running_pill(said)
        return running_pill(said) + ('<div class="act">' + _post(ctx, mo.STOP_PATH[1:], mo.STOP_BUTTON, "gb",
                                                                 agent=agent, back=back)
                                     + f'<p class="quiet">{h(mo.ARENA_STOP_SAID)}</p></div>')
    out = []
    note = m.arena_note(agent)
    if note:
        out.append(f'<p class="no-yet" role="status">{h(note)}</p>')
    if note and ctx["token"] and getattr(m, "arena_record", lambda a: None)(agent):  # torn or gone: the one step
        out.append(_post(ctx, mo.NEW_TEST_PATH[1:], "Start a new test set", "yes", agent=agent, back=back))
    training = hasattr(m, "training") and m.training(agent) is not None
    if ctx["token"] and not training:
        status = (m.arena_status(agent) if hasattr(m, "arena_status") else None) or {}
        word = mo.ARENA_AGAIN if status.get("ran") and not status.get("ready") else mo.ARENA_BUTTON
        said = (getattr(m, "arena_said", lambda a: None)(agent) or ARENA_SAID)
        quiet = getattr(m, "no_channel", lambda a: False)(agent)  # no live channel: a pass unlocks nothing
        out.append(("" if sales else f'<p class="quiet">{h(said)}</p>')  # the Sales agent has no sample data
                   + _post(ctx, ARENA_PATH[1:], f'{icon("flask")}{h(word)}',
                           "yes" if status.get("next", "arena") == "arena" else "gb", agent=agent, back=back)
                   + f'<p class="quiet nt">{h(mo.ARENA_RUN_NO_CHANNEL if quiet else mo.ARENA_RUN_SAID)}</p>')
    return f'<div class="act stk">{"".join(out)}</div>' if out else ""


def running_pill(said):
    """A run going, where its button was: a greyed pill with a small turning ring and what it has done so far."""
    return (f'<div class="act"><span class="runp"><span class="spin" aria-hidden="true"></span><span role="status">'
            f'{h(said)}</span></span></div>')


SO_FAR_SUB = "Playing now on top, then played so far, newest first"
PLAYING = "Playing"
PLAYING_BADGE = f'<span class="pulse" aria-hidden="true"></span>{PLAYING}'
CHAT_TURN_ROOM = 1500  # characters of one line shown in a live chat bubble


def chat_bubbles(turns):
    """A match's turns as a chat: the customer's line on one side, each agent reply on the other, escaped,
    dir auto (Arabic and English alike); a turn with no reply says so."""
    rows = []
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        said = t.get("customer") if isinstance(t.get("customer"), str) and t["customer"].strip() else t.get("input")
        if isinstance(said, str) and said.strip():
            rows.append(f'<p class="said me" dir="auto">{h(said[:CHAT_TURN_ROOM])}</p>')
        replies = [r for r in (t.get("replies") or []) if isinstance(r, str) and r.strip()]
        for r in replies:
            rows.append(f'<p class="said ag" dir="auto">{h(r[:CHAT_TURN_ROOM])}</p>')
        if not replies:
            out = str(t.get("outcome") or "").replace("_", " ").strip()
            said_why = f" ({h(out)})" if out and out != "no reply" else ""
            rows.append(f'<p class="said nil">No reply{said_why}.</p>')  # never .no, the round button's class
    return f'<div class="thread">{"".join(rows)}</div>' if rows else ""


def so_far_tiles(so, agent=None, fix_ctx=None):
    """The running Run the Arena's matches (Morning.arena_so_far), for the screen only (the gate reads the saved
    run, never these). On top the matches playing now, a Playing badge and the chat so far, turn by turn; then
    the ones judged, newest first, Won or Lost with the one line why and the chat in a fold (open for Lost,
    closed for Won). Every tile has Correct this (fix_ctx given: the page's token and the agent's lessons), the
    same correction as the page's box (Morning.correct, the hotfix), the match id on it only as context."""
    so = so or {}
    tiles = []

    def fix(mid):
        return correct_this(fix_ctx, agent, fix_ctx, keep=mid) if fix_ctx is not None and agent else ""

    def head(who, about, res):
        return (f'<div class="t-h"><span class="pav">{icon("chat")}</span><div><b>{h(who)}</b><small>'
                f'{h(about)}</small></div><span class="res">{res}</span></div>')

    live = [x for x in so.get("live") or [] if isinstance(x, dict) and isinstance(x.get("id"), str)]
    for x in live:
        if x.get("status") == "finished":
            continue
        chat = chat_bubbles(x.get("turns")) or '<p class="quiet">Its first line is on the way.</p>'
        tiles.append(f'<article class="tile live" data-match="{h(x["id"])}">'
                     f'{head(x.get("who") or "Practice case", x.get("about") or "", PLAYING_BADGE)}'
                     f'<div class="lc">{chat}</div>{fix(x["id"])}</article>')
    done = [x for x in live if x.get("status") == "finished"][::-1]
    for x in done + [r for r in so.get("rows") or [] if isinstance(r, dict) and isinstance(r.get("won"), bool)]:
        mid = str(x.get("id") or "")
        why = x.get("why") if isinstance(x.get("why"), str) else ""
        won = x.get("won") is True
        res, cls = ("Won", "won") if won else ("Lost", "lost")
        line = f'<p class="persona" dir="auto">{h(_cap(" ".join(why.split())[:200]))}.</p>' if why.strip() else ""
        turns = [t for t in x.get("turns") or [] if isinstance(t, dict)]
        chat = chat_bubbles(turns)
        fold = (f'<details class="lc" data-chat="{h(mid)}"{"" if won else " open"}><summary>The chat, '
                f'{_plural(len(turns), "turn")}</summary>{chat}</details>') if chat else ""
        tiles.append(f'<article class="tile {cls}" data-match="{h(mid)}">'
                     f'{head(x.get("who") or "Practice case", x.get("about") or "Made up for the Arena", res)}'
                     f'{line}{fold}{fix(mid) if mid else ""}</article>')
    return "".join(tiles) or ('<div class="ghost"><span class="pav" aria-hidden="true"></span>Its first matches are '
                              'starting.</div>')


def trained_html(done):
    """What the last Train did (Morning.trained), in one line, with the lessons it showed and what waits."""
    when = mo._when(done["at"])
    if not done.get("lost"):
        line = mo.TRAIN_NO_LOSS
    else:
        n = done["lost"]
        line = mo.TRAINED.format(when=when, lost=f"{n} lost {'match' if n == 1 else 'matches'}",
                                 written=_plural(done.get("written") or 0, "lesson"), passed=done.get("passed") or 0)
    out = [f'<div class="nr"><p>{h(line)}</p></div>']
    out += seen_rows(done.get("seen") or [])
    if done.get("queued"):
        out.append(f'<p class="quiet">{h(waiting_line(done["queued"]))}</p>')
    return "".join(out)


def waiting_line(n):
    """N lessons wait for tonight (DECISIONS 98)."""
    return mo.WAIT_ONE if n == 1 else mo.WAIT_MANY.format(n=n)


def seen_rows(seen):
    """Each lesson as it took its exam (reflect_now Steps.seen): its words, then the exam's word."""
    rows = []
    for x in seen:
        who = f"{mo.LIVE_YOURS}. " if x.get("kind") == "correction" else ""
        rows.append(f'<div class="lr"><b dir="auto">{h(x["text"])}</b><small>{h(who)}'
                    f'{h(mo.LIVE_EXAM.get(x.get("exam"), mo.LIVE_EXAM["in exam"]))}</small></div>')
    return rows


def live_view(m, agent, ctx):
    """The live view while Train or Run reflection runs (DECISIONS 99 and 100): each lesson as it is written and
    takes its exam, then the exam's word, refreshed by the page's poll; Stop with its line (Morning.stop_run); and
    how many lessons wait for tonight (Morning.queued)."""
    rows = seen_rows(m.live_seen(agent)) or [f'<div class="nr"><p>{mo.LIVE_NONE}</p></div>']
    out = [f'<span class="lab">{mo.LIVE_HEAD}</span>', *rows]
    if ctx["token"]:
        out.append('<div class="act">' + _post(ctx, mo.STOP_PATH[1:], mo.STOP_BUTTON, "gb", agent=agent,
                                               back=ctx["path"] + ctx["q"])
                   + f'<p class="quiet">{h(mo.STOP_SAID)}</p></div>')
    n = m.queued(agent) if hasattr(m, "queued") else 0
    if n:
        out.append(f'<p class="quiet">{h(waiting_line(n))}</p>')
    return f'<div class="live">{"".join(out)}</div>'


REFLECT_PATH = "/reflect/run"
# What the exam a lesson Run reflection wrote said, by Morning._item exam_result (None: it took none).
REFLECT_EXAM = {"passed": "It passed the full exam.",
                "failed": "It did not pass the exam, so it waits for your yes.",
                "not run": "The exam could not run, so it waits for your yes.",
                None: "It took no exam."}


def reflect_live(m, agent):
    """The marks the agent page's script polls (ARENA_SCRIPT): data-running while a reflection goes."""
    return ' data-live="reflect"' + (" data-running" if m.reflecting(agent) else "")


def reflect_running(step):
    """The running line, the owner's words (mo.REFLECT_RUNNING), with the current step marked."""
    said = ", then ".join(f'<b aria-current="step">{h(w)}</b>' if k == step else h(w) for k, w in mo.REFLECT_STEPS)
    return f'<p class="no-yet" role="status">Reflecting: {said}</p>'


def reflect_result(a, done, no_lost=mo.NO_LOST):
    """What the last Run reflection did, with the lesson rows' own rendering (lesson_rows, _chip): each
    lesson it wrote with its chip (on trial, or waiting for a yes) and what its exam said; else why it
    wrote none (no_lost: the agent's own no lost chats line, Morning.no_lost)."""
    items = {i["id"]: i for i in a["live"] + a["waiting"] + a["pulled"]}
    out = [f'<span class="lab">Last reflection, {h(mo._when(done["at"]))}</span>',
           f'<div class="nr"><p>Reflection read {_plural(done["lost"], "lost chat")}.</p></div>']
    rows = []
    for lid in done["cards"]:
        i = items.get(lid)
        if i is None:
            continue
        cls, chip, small = _chip(i, a)
        exam = REFLECT_EXAM.get(i.get("exam_result"), REFLECT_EXAM[None])
        held = i.get("exam_plain") or i.get("exam") or ""  # the check's why, never its name
        rows.append(f'<div class="lr"><b dir="auto">{h(i["text"])}</b><span class="vchip {cls}">{chip}</span>'
                    f'<small>{h(small)}</small><small>{h(exam)}{" " + h(_cap(held)) + "." if held else ""}</small></div>')
    if rows:
        out += rows
    else:
        if not done["lost"]:
            why = no_lost
        elif done.get("written"):  # the Sales agent's Arena losses: lessons written in its copy, none passed the gate
            why = (f'It wrote {_plural(done["written"], "lesson")} from them; none passed the exam, so none reaches a '
                   "real customer.")
        elif not done["candidates"]:
            why = f'It found no lesson in {_plural(done["lost"], "lost chat")}.'
        else:
            why = (f'It weighed {_plural(done["candidates"], "possible lesson")}; none was clear enough to write, '
                   "so no lesson was written.")
        if done["notes"]:
            why += f' It noted: {" ".join(str(done["notes"][0]).split())[:200]}'
        out.append(f'<div class="nr"><p>No lesson this time. {h(why)}</p></div>')
    return "".join(out)


def run_reflection(m, a, agent, ctx, back):
    """Run reflection (Morning.run_reflection) for any agent on the page with the database folder: the
    button with the line under it while no run goes and the page has a token (greyed out with the reason
    when there is no model key or no lost chat), the steps while one runs, and what the last one did.
    Empty on the sample days (no database folder) and for an agent with no plug here."""
    if not hasattr(m, "run_reflection") or agent not in m.plugs or getattr(m, "db_path", None) is None:
        return ""
    step = m.reflecting(agent)
    if step is not None:
        return f'<div class="act">{reflect_running(step)}</div>{live_view(m, agent, ctx)}'
    out = []
    done = m.reflected(agent)
    if done is not None:
        out.append(reflect_result(a, done, m.no_lost(agent) if hasattr(m, "no_lost") else mo.NO_LOST))
    n = m.queued(agent) if hasattr(m, "queued") else 0
    if n:
        out.append(f'<p class="quiet">{h(waiting_line(n))}</p>')
    note = m.reflect_note(agent)
    if note:
        out.append(f'<p class="no-yet" role="status">{h(note)}</p>')
    if ctx["token"]:
        why = mo.REFLECT_ARENA if m.arena_running(agent) else m.reflect_ready(agent)
        out.append(f'<p class="quiet">{h(mo.REFLECT_SAID)}</p>')
        if why is None:
            out.append(_post(ctx, REFLECT_PATH[1:], f'{icon("loop")}{mo.REFLECT_BUTTON}', "yes", agent=agent, back=back))
        else:
            out.append(f'<button class="yes" type="button" disabled>{icon("loop")}{mo.REFLECT_BUTTON}</button>')
        if why == mo.NO_KEY:
            out.append(f'<p class="no-yet" role="status">{h(why)} <code>{h(mo.REPLAY)}</code></p>')
        elif why is not None:
            out.append(f'<p class="no-yet" role="status">{h(why)}</p>')
    return f'<div class="act stk">{"".join(out)}</div>' if out else ""


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
    elif tok and ctx.get("chat") is not None:  # every other agent with an agent folder: the same chat (Pages.chat_html)
        left.append(ctx["chat"](tab_ctx(ctx, agent, "live"), agent))
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
                    f'rows="4" maxlength="{qs_mod.MAX_TEXT}" aria-label="What agent do you want?" dir="auto" required '
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
    sheet = bool(built and not building and tok and m.agent_folder(built) is not None)  # the Add data box shows
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
                f'<span class="lab">Agent card</span>{plan_card(t["card"], data, sheet)}']
        if t["question"] and not built and not building:
            card.append(f'<p class="uq" dir="auto">{h(t["question"])}</p>')
        if built or building or run is not None and run.error is None:
            card.append(f'<div class="cact"><span class="started">{icon("check")}Build started</span></div>')
        elif tok:
            clash = quick.name_clash(m, t["card"])
            if clash:  # decision 106: said before Build is pressed; Build refuses it too
                card.append(f'<p class="err" role="status" dir="auto">{h(clash)}</p>')
            card.append('<div class="cact">' + level_picker(ctx, t["card"])
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
        if sheet:  # it can take more data
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


USING_SAMPLE = "This agent is using sample data, since nothing is connected yet."  # DECISIONS 107
SAMPLE_STATE = "Sample data for now"            # a need with no real connection, read from the sample data
STORE_SAMPLE = "Sample data until the store is connected"  # the store need with no Shopify keys
# the WhatsApp need with its keys set: a built agent does not run on WhatsApp yet (README, Deployment), so no tick
WHATSAPP_KEYS_SET = "WhatsApp keys are set. Running an agent made in Quick start on WhatsApp comes next."
# A step the case's end needs (reflection/quickstart.py steps) whose need is not connected: the card says,
# before Build, that the agent records it and the user does that part until it is connected.
STEP_WAIT = "Until it is connected, it records the {thing} as {done} and you do that part."
DATA_NOTE = "Paste rows (CSV or JSON) or plain lines, or choose a file. They are added as yours."
DATA_ID = "add-data"  # the Add data box's id, so a need tile's "Use a sheet instead" can point at it
# A need tile that is not connected opens (its +) to how that one connection is made. Page text, never a
# model's. Keys only ever go in .env (docs/judges.md); the page never takes a key.
HOW_STORE = ("Put your Shopify store address (SHOPIFY_STORE, like name.myshopify.com) and its Admin API token "
             "(SHOPIFY_TOKEN) in .env, then start the page again. Until then it works from sample data.")
HOW_WHATSAPP = "Put the values from your WhatsApp Business number ({keys}) in .env, then start the page again. {next}"
HOW_OTHER = "Unfenced cannot connect this yet. Until it can, the agent works from sample data."
HOW_ASK = "Only you can tell it this. Say it in the box before Build. Until you do, it works from sample data."
SHEET = "Use a sheet instead"
SHEET_NOW = ": add your rows or a CSV file in the Add data box."
SHEET_LATER = ": once it is built, add your rows or a CSV file in the Add data box under its steps."
MCP_NEXT = "Connect through MCP: coming next"  # every tile, greyed, never a link


OFFERS_HEAD = "Offers"
OFFERS_NONE = "No offers yet. Add what it may offer a customer who hesitates."
OFFERS_NOTE = "One offer a line: what it is; its terms; when it fits. A percent on the line, like 10%, is that offer's."
OFFERS_SAID = "It offers only these, when their when line fits, and never makes one up."


def offer_text(o):
    """One offer in plain words: what it is, its terms, and when it fits, as the owner or the card wrote them."""
    out = _cap(o["what"]) + "."
    if o.get("terms"):
        out += f" {_cap(o['terms'])}."
    if o.get("when"):
        out += f" When: {o['when'].rstrip('.')}."
    return out


def offers_list(offers):
    return '<ul class="offers">' + "".join(f'<li dir="auto">{h(offer_text(o))}</li>' for o in offers) + "</ul>"


def offers_form(ctx, agent):
    """The box that adds offers to a built agent (Morning.add_offers), cloned from the Add data box."""
    return (f'<section class="say sq" id="add-offers" aria-label="Add offers"><form method="post" action="{mo.OFFERS_PATH}">'
            f'{_hidden(ctx, agent=agent)}<span class="lab">Add offers</span><div class="box"><textarea name="text" '
            f'aria-label="Offers to add, one a line" maxlength="{mo.MAX_OFFERS_TEXT}" dir="auto" '
            'placeholder="Free delivery; on any order; always"></textarea></div><div class="say-f"><span></span>'
            f'<button class="send pill" type="submit">Add{icon("arrow")}</button></div><p class="quiet">{h(OFFERS_NOTE)}'
            '</p></form></section>')


def data_form(ctx, agent):
    """The box that adds rows or a file to a built agent's sample data (Morning.add_data)."""
    return (f'<section class="say sq" id="{DATA_ID}" aria-label="Add sample data"><form method="post" action="{mo.DATA_PATH}" '
            f'enctype="multipart/form-data">{_hidden(ctx, agent=agent)}<span class="lab">Add data</span><div class="box">'
            f'<textarea name="text" aria-label="Rows or text to add" maxlength="{sample_mod.MAX_TEXT}" dir="auto" '
            'placeholder="name, price, stock"></textarea></div><div class="say-f"><label class="quiet pick">'
            f'{icon("plus")}<input type="file" name="file" aria-label="A CSV or JSON file" '
            'accept=".csv,.json,.txt,text/csv,application/json,text/plain"></label><button class="send pill" type="submit">'
            f'Add{icon("arrow")}</button></div><p class="quiet">{DATA_NOTE}</p></form></section>')


def sample_line(data):
    return f'<p class="quiet sdata">{icon("note")}{h(sample_mod.words(data))}</p>' if data else ""


def using_sample(folder, data):
    """True when a built agent works from sample data: no need on its card is connected for real, and it has
    sample rows or a store need (the store answers from sample data with no keys)."""
    try:
        card = json.loads((Path(folder) / "card.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return bool(data)
    needs = [n for n in card.get("needs") or [] if isinstance(n, dict) and "tool" in n and "connected" in n] \
        if isinstance(card, dict) else []
    if any(need_state(n, data)[1] for n in needs):
        return False
    return bool(data) or any(n["tool"] == "store" for n in needs)


def need_keys(tool):
    """The keys a tool needs set before its need reads as connected; () for a tool that needs none."""
    if tool == "store":
        return ("SHOPIFY_STORE", "SHOPIFY_TOKEN")
    if tool == "whatsapp":
        from channels import whatsapp
        return whatsapp.REQUIRED_ENV
    return ()


def need_state(n, data):
    """(words, connected) for one need on the card: Connected only with a real connection, so the store only
    with its keys set. WhatsApp is never Connected here: an agent made here does not run on it yet, so with its
    keys set it says they are set and that running on WhatsApp comes next (the Sales agent's own connection is
    on its page, connections_html). The store with no keys, or a need with no tool while the agent has sample
    data, says sample data; WhatsApp with no keys is not connected yet."""
    from kit import env
    if n["connected"] and not all(env.get(k) for k in need_keys(n["tool"])):
        return (STORE_SAMPLE, False) if n["tool"] == "store" else ("Not connected yet", False)
    if n["connected"] and n["tool"] == "whatsapp":
        return WHATSAPP_KEYS_SET, False
    if n["connected"]:
        return f'Connected: {qs_mod.TOOLS.get(n["tool"], "").split(":")[0]}', True
    return (SAMPLE_STATE if data else "Not connected yet"), False


def how_to_connect(n):
    """The plain steps for one need's connection: the store and WhatsApp by their keys in .env, any
    other need by what it reads from until a connection exists."""
    if n["tool"] == "store":
        return HOW_STORE
    if n.get("ask"):  # only the user can tell it (reflection/quickstart.py ask_once)
        return HOW_ASK
    if n["tool"] == "whatsapp":
        return HOW_WHATSAPP.format(keys=", ".join(need_keys("whatsapp")), next=QUICK_NEXT.format(name="WhatsApp"))
    return HOW_OTHER


def need_tile(n, said, on, waits, sheet):
    """One need on the card. Connected: its check and its line. Not connected: its + opens how to connect
    that one need, and a sheet in its place (the Add data box, Morning.add_data). Every tile says MCP is
    coming next, greyed and not a link. Nothing here holds Build back."""
    text = (f'<div><b dir="auto">{h(n["what"])}</b><small>{h(said)}</small>{waits}'
            f'<small class="mcp" aria-disabled="true">{MCP_NEXT}</small></div>')
    if on:
        return f'<div class="file on"><span class="fi">{icon("check")}</span>{text}<span></span></div>'
    if said == WHATSAPP_KEYS_SET:  # keys set, nothing left to connect here: no tick, no how to connect
        return f'<div class="file"><span class="fi">{icon("loop")}</span>{text}<span></span></div>'
    use = (f'<a href="#{DATA_ID}">{SHEET}</a>{SHEET_NOW}' if sheet else f"<b>{SHEET}</b>{SHEET_LATER}")
    return (f'<details class="need"><summary class="file">'
            f'<span class="fi">{icon("plus")}</span>{text}</summary><div class="how"><p>{h(how_to_connect(n))}</p>'
            f"<p>{use}</p></div></details>")


def plan_card(card, data=None, sheet=False):
    """The model's card as one plain white card, then what it needs, each marked connected or not yet.
    One case is: what arrives, what the agent gives and when it is over, in the model's words under the
    page's labels, and a line when the agent writes first; then the good and the bad result (DECISIONS
    item 68). The user changes any of them by a message in the box; the model writes the card again.
    sheet: the Add data box is on the page, so a need's "Use a sheet instead" links to it."""
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
    if card.get("offers"):  # what it may offer a customer who hesitates (decision 105)
        rows.append((OFFERS_HEAD, offers_list(card["offers"])))
    out = [f'<section class="plan" aria-label="The agent"><h3 dir="auto">{h(card["name"])}</h3><dl>'
           + "".join(f"<div><dt>{t}</dt><dd>{v}</dd></div>" for t, v in rows) + "</dl></section>"]
    if card["needs"]:
        out.append('<div class="needs"><span class="lab">What it needs connected</span>')
        steps = qs_mod.steps(card)
        for n in card["needs"]:
            said, on = need_state(n, data)
            waits = "" if on else "".join(f"<small>{h(STEP_WAIT.format(thing=t, done=d))}</small>" for t, d in steps
                                          if qs_mod.step_need(card, (t, d)) is n)
            out.append(need_tile(n, said, on, waits, sheet))
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


def correct_this(ctx, agent, fix_ctx=None, keep=None):
    """Correct this, under a reply the agent lost a practice match on: the same correction as the box on
    the agent's page (Morning.correct, a hotfix through the short exam), sent from beside the reply it
    is about; the answer shows on the agent's page, on the same demo day or Live tab (ctx["q"]), so the
    correction runs on the database the user was looking at. keep: a live match's id, sent as context only
    (Morning.correct never reads it) and marked data-keep, so the page's poll never wipes it (ARENA_SCRIPT)."""
    mark, more = (f' data-keep="{h(keep)}"', {"match": keep}) if keep else ("", {})
    return (f'<details class="fix"{mark}><summary>{icon("loop")}Correct this</summary><form method="post" action="/correct">'
            f'{_hidden(fix_ctx or dict(ctx, path=f"/agents/{agent}"), agent=agent, **more)}<div class="box"><textarea name="line" '
            f'aria-label="What it should do here" placeholder="What should it do here?" maxlength="{mo.MAX_LEN}" '
            f'dir="auto" required></textarea></div><div class="say-f"><p class="quiet">{SAY_NOTE}</p>'
            f'<button class="send" type="submit">Send{icon("arrow")}</button></div></form></details>')


def arena_parts(m, agent, ctx, back=None, fix_ctx=None, so_far=None):
    """The newest Arena run saved next to the database for this agent, as (the climb card, the match
    tiles, Try again). The matches it lost are tiles with why; no total of won and lost (the trust
    level stays private, DECISIONS item 17). back: where Try again returns; fix_ctx: the ctx Correct
    this sends from (its answer shows there); so_far: a running run's {"played", "won"} (Morning.arena_so_far),
    which the climb card's line says instead of the saved run's."""
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
    end = "Passed the gate" if getattr(m, "no_channel", lambda a: False)(agent) else "Ready to go live"
    calm = f"{h(when)} Nothing to do here while it practises."
    if so_far is not None:
        calm = h(practising_line(so_far))
    glow = ('<section class="a-climb" aria-label="How close it is"><article class="glow sq">'
            '<div class="glow-h"><span class="gchip">In the Arena</span><span class="gsub">practising on made-up '
            f'cases</span></div>{CLIMB}<div class="climb-l"><span>Started</span><span>{end}</span></div>'
            f'<p class="calm">{calm}</p></article></section>')
    return glow, "".join(tiles), retry


def practising_line(so):
    """The dark card's line while Run the Arena plays: how many matches it played and won so far."""
    n, won = int((so or {}).get("played") or 0), int((so or {}).get("won") or 0)
    if not n:
        return "Practising now: its first matches are starting."
    return f"Practising now: {n} played, {won} won so far."


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
    not run or stopped early. The Sales agent and an agent made here (decision 84); any other agent
    shows it greyed out, like Pull."""
    built = hasattr(m, "agent_folder") and agent is not None and m.agent_folder(agent) is not None
    if (agent != mo.SALES.agent and not built) or agent not in m.lessons:
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
