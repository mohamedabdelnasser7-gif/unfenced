"""The two tab page, Today and Agents (LOCKS.md "Product shape: two tabs" and "Today and agent
page: A"), served by reflection/morning.py. It draws from Morning.view() and answers through the
Morning methods only, so no engine rule lives here.

    /              Today: only what needs the user's yes, one light sage card each, then at most two
                   lines per agent about last night, the most important first (the same agents the
                   Agents tab lists); an empty state when nothing waits (DECISIONS 35).
    /agents        the agents (the plugs in the repo and the agents in the database) and New agent.
                   An agent shows Live when it works on real chats or cases (Morning._live), else
                   Training: only Arena practice.
    /agents/<name> one agent: its status with Pull (the pause switch, Resume when paused) and Roll
                   back, the box for an idea or a correction (Morning.correct, a hotfix), then its
                   lessons and Reflection notes as rows.
    /agents/<name>/rollback  what Roll back would do, lesson by lesson, and its one button.
    /new           New agent, Quick start B screen 1: the Quick start chat (reflection/quickstart.py), its
                   card, at most one question and the second message, the same box, Send and Build.
    /new/build     screen 2: the newest Arena run saved next to the database, as tiles and a path.

A correction sent on an agent's page that is high risk waits for a yes on Today (Morning.correct); its
card says why in one plain sentence (plain_risk), never the engine's word lists, and the Hotfix chip
marks a correction that runs in the chats. With demo days each day shows its own morning (day.json); with --db too a Live tab follows the days and
serves the real database with real answers and the real clock, never marked Sample data.

No count of what is left anywhere (item 35), no trust level and no won and lost total (item 17,
LOCKS Quick start B). No script: Modify is a details element inside its card. Every field is
escaped. With demo days (--demo-days) a Day 1, Day 2, Day 3 switch sits on top, marked Sample
data (Sample on the phone bar, so every label stays on one line at 390); each day is its own throwaway copy, so answers there never touch the sample files.
"""
import base64
import hashlib
import re
import urllib.parse

from engine import lessons as lessons_mod
from reflection import morning as mo
from reflection import quickstart as qs_mod
from reflection import snapshots
from reflection.page_css import CSS

CSP = ("default-src 'none'; style-src 'sha256-" + base64.b64encode(hashlib.sha256(CSS.encode("utf-8")).digest()).decode()
       + "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
h = mo.h
NAMES = {"sales": "Sales agent", "assistant": "Personal assistant", "marketing": "Marketing agent"}
CORRECTED = lessons_mod.HOTFIX_SOURCE  # the source line of a correction (Morning.correct, Lessons.correct)
_AGENT = re.compile(r"^[a-z][a-z_]{0,30}$")
ROLLBACK = "/rollback"  # /agents/<name>/rollback: the plan a rollback would carry out, and its one button
_BACK = re.compile(r"^/(?:agents(?:/[a-z][a-z_]{0,30})?|new(?:/build)?)?$")
ICON = dict(mo.ICONS, pen='<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
            loop='<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
            undo='<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>', pause='<path d="M9 6v12M15 6v12"/>',
            check='<path d="M5 12.5l4.5 4.5L19 7.5"/>', arrow='<path d="M5 12h14M13 6l6 6-6 6"/>',
            back='<path d="M15 6l-6 6 6 6"/>', note='<path d="M6 4h12v16H6z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
            plus='<path d="M12 6v12M6 12h12"/>')


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
    return NAMES.get(agent, agent.replace("_", " ").capitalize())


def icon(n, cls="i"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true">{ICON[n]}</svg>'


class Pages:
    """The page for one Morning, or for demo days {1: Morning, 2: ..., 3: ...} (sample copies), with
    live: the Morning on the real database, a Live tab after the days (no Sample data label there)."""

    LIVE = "live"

    def __init__(self, morning=None, *, days=None, at=None, live=None, model=None):
        """at: {day: the time that day's page shows}, a sample's own clock; the real clock otherwise
        and always on Live. model: Quick start's model (a fake in tests); None uses kit.model."""
        self.days = dict(days or {})
        self.at = dict(at or {})
        self.live = live if self.days else None  # with no sample days the page has no switch
        self.demo = bool(self.days)
        self.morning = morning if morning is not None else (self.days[min(self.days)] if self.days else None)
        self.csp = CSP
        self.quick = qs_mod.QuickStart(model)
        # the page's own answers, taken by the server next to morning.TWO_TAB_ACTIONS
        self.actions = {"/quickstart": lambda m, f, now=None: self._quick(self.quick.say, m, now, mo._field(f, "text")),
                        "/quickstart/build": lambda m, f, now=None: self._build(m, now),
                        "/quickstart/clear": lambda m, f, now=None: self._quick(self.quick.clear, m, now)}

    def back(self, value):
        """Where an answer returns to: one of the page's own paths, with the demo day; else /."""
        parts = urllib.parse.urlsplit(str(value or ""))
        path = parts.path if _BACK.match(parts.path or "") and not parts.netloc and not parts.scheme else "/"
        day = self._day(urllib.parse.parse_qs(parts.query))
        return path + (f"?day={day}" if self.demo else "")

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

    def _build(self, m, now):
        """Build, then the new agent joins the running page (Morning.add_built): its plug, Pull and exam
        with no restart. The agent is built already when that fails, so the flash says so and asks for a
        restart; an agent with no exam on the page takes no correction (Morning.correct)."""
        said = self._quick(self.quick.build, m, now)
        try:
            m.add_built()
        except Exception as e:
            return f"{said} It could not join this page ({e}). Restart the page to see it."
        return said

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
        ctx = {"token": token, "q": q, "day": day, "path": path, "m": m, "now": now}
        if path == "/":
            return self.shell(today(m.view(now=now), ctx), "today", ctx, flash)
        if path == "/agents":
            return self.shell(agents(m, m.view(now=now), ctx), "agents", ctx, flash)
        if path.startswith("/agents/") and _AGENT.match(path[8:]):
            body = agent_page(m, m.view(now=now), path[8:], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash)
        if path.startswith("/agents/") and path.endswith(ROLLBACK) and _AGENT.match(path[8:-len(ROLLBACK)]):
            body = rollback_page(m, path[8:-len(ROLLBACK)], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash)
        if path == "/new":
            return self.shell(new_agent(m, self.quick, ctx), "agents", ctx, flash)
        if path == "/new/build":
            agent = (query.get("agent") or [""])[0]
            return self.shell(build(m, agent if agent in m.plugs else None, ctx), "agents", ctx, flash)
        return None

    def shell(self, body, on, ctx, flash):
        q = ctx["q"]
        tabs = (("today", "/", "sun", "Today"), ("agents", "/agents", "sliders", "Agents"))
        top = "".join(f'<a class="titem{" on" if t == on else ""}" href="{u}{q}"'
                      f'{" aria-current=page" if t == on else ""}>{icon(i)}{w}</a>' for t, u, i, w in tabs)
        bar = "".join(f'<a class="tab{" on" if t == on else ""}" href="{u}{q}"'
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
            f'<p class="flash" role="status">{h(flash)}</p>' if flash else "",
            body, "</div>", f'<nav class="isl" aria-label="Main">{bar}</nav></body></html>'])


# ---- Today -------------------------------------------------------------------------------------

def _hidden(ctx, **kv):
    kv = dict(token=ctx["token"], back=ctx["path"] + ctx["q"], **kv)
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
    if item.get("second"):  # shown only, deciding nothing (DECISIONS item 67)
        out.append(f'<p class="why">{h(mo.second_words(item["second"]))}</p>')
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
SAY_NOTE = ("Takes a short exam, then starts at once as a hotfix in half the chats. If it is high risk or "
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
        lines.append((8, f"{_plural(n, 'chat')} that ended with no order got a hotfix note for that customer's next chat."))
    if a.get("arena") and a["arena"]["at"] >= now - day:
        lines.append((9, "It practised with made-up customers in the Arena."))
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
STATUS_SAID = {"Live": "Answering chats", "Training": "Practising in the Arena",
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


def today(view, ctx):
    items = waiting(view)
    cards = {"lesson": lesson_card, "unclear": unclear_card, "fact": fact_card}
    html = [f'<section class="top"><h1>Good morning</h1><p class="num">{h(mo._today(view["at"]))}</p></section>']
    if items:
        body = "".join(mode_card(i["agent"], i["mode_card"], ctx) if k == "mode" else cards[k](i, ctx) for k, i in items)
        html.append('<div class="today"><section aria-labelledby="y-h"><div class="sec-h"><h2 id="y-h">Needs your yes'
                    f'</h2></div><div class="cards">{body}</div></section>')
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
    return ('<section class="top"><h1>Agents</h1><p>Each one learns from its own chats.</p></section><div class="col">'
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


def agent_page(m, view, agent, ctx):
    a = next((x for x in view["agents"] if x["agent"] == agent), None)
    if a is None and agent not in m.plugs:
        return None
    a = a or {"agent": agent, "live": [], "waiting": [], "pulled": [], "night": None, "buttons": agent in m.plugs}
    st = status_of(m, agent)
    states = "".join(f'<span class="on"><i></i>{s}</span>' if s == st else f"<span>{s}</span>"
                     for s in ("Training", "Live", "Paused"))
    tok = ctx["token"] if a["buttons"] else None
    roll = ""
    plan = m.rollback_plan(agent, ctx.get("now")) if a["buttons"] else None
    if tok and plan is not None:  # the plan first, on its own screen; the rollback is the button there
        roll = f'<a class="gb" href="/agents/{h(agent)}{ROLLBACK}{ctx["q"]}">{icon("undo")}Roll back</a>'
    elif a["buttons"]:
        roll = f'<button class="gb" type="button" disabled>{icon("undo")}Roll back</button>'
    if tok and m.pausable(agent):  # the real pause switch (DECISIONS 54, Morning.pause and resume)
        pull = (_post(ctx, "resume", f'{icon("loop")}Resume', "gb", agent=agent) if st == "Paused"
                else _post(ctx, "pause", f'{icon("pause")}Pull', "gb", agent=agent))
    else:
        pull = f'<button class="gb" type="button" disabled title="Not built for this agent yet">{icon("pause")}Pull</button>'
    out = [f'<div class="colhead"><a class="back" href="/agents{ctx["q"]}">{icon("back")}Agents</a>'
           f'<section class="top ag-top"><h1>{h(name(agent))}</h1></section></div><div class="col">',
           f'<section class="status sq" aria-label="Status"><div class="st-l"><span class="states" role="img" '
           f'aria-label="Status: {st}">{states}</span><small>{STATUS_SAID[st]}'
           f'</small></div><div class="st-r">{roll}{pull}</div></section>']
    if tok:
        out.append(f'<section class="say sq" aria-label="Send an idea or a correction"><form method="post" action="/correct">'
                   f'{_hidden(ctx, agent=agent)}<span class="lab">Send an idea or a correction</span><div class="box">'
                   f'<textarea name="line" aria-label="Your idea or correction" maxlength="{mo.MAX_LEN}" dir="auto" required>'
                   f'</textarea></div><div class="say-f"><p class="quiet">{icon("loop")}{SAY_NOTE}</p><button class="send" type="submit">Send{icon("arrow")}</button></div></form></section>')
    rows = []
    for i in a["live"] + a["waiting"] + a["pulled"][:5]:
        cls, chip, small = _chip(i, a)
        rows.append(f'<div class="lr"><b dir="auto">{h(i["text"])}</b><span class="vchip {cls}">{chip}</span>'
                    f'<small>{h(small)}</small></div>')
    out.append('<section class="grp sq" aria-labelledby="l-h"><h3 id="l-h">Lessons</h3>'
               + ("".join(rows) or '<div class="lr"><b>No lessons yet.</b></div>') + "</section>")
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
        day = f'&day={ctx["day"]}' if ctx["day"] else ""
        notes.append(f'<div class="nr"><span class="to">{icon("note")}From the Arena, {h(mo._date(a["arena"]["at"]))}</span>'
                     f'<p>It practised with made-up customers. <a class="lk" href="/new/build?agent={h(agent)}{day}">'
                     'See where it slipped</a></p></div>')
    out.append('<section class="grp sq" aria-labelledby="r-h"><h3 id="r-h">Reflection notes</h3>'
               + ("".join(notes) or '<div class="nr"><p>Nothing yet.</p></div>') + "</section></div>")
    return "".join(out)


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


# ---- New agent (Quick start B) -----------------------------------------------------------------

def new_agent(m, quick, ctx):
    """Screen 1, Quick start B: the light sage ask card holds the chat. The card, its one question and
    the second message are the model's words, shown as written (DECISIONS items 58 and 38); the labels,
    chips and buttons are the page's frame. The box sends the first ask, an answer or an edit, and the
    model writes the whole card again; Build writes the plug folder (reflection/quickstart.py)."""
    d = quick.draft(m)
    turns, built = d["turns"], d["built"]
    last = turns[-1] if turns else None
    out = ['<article class="ask sq" aria-label="Quick start"><span class="lab">What agent do you want?</span>']
    if last:
        out.append('<div class="thread">' + "".join(f'<p class="said" dir="auto">{h(t["said"])}</p>' for t in turns)
                   + "</div>")
        out.append(plan_card(last["card"]))
        if last["question"] and not built:
            out.append(f'<p class="uq" dir="auto">{h(last["question"])}</p>')
        if not built:
            out.append(f'<p class="uf" dir="auto">{h(last["follow"])}</p>')
    if built:
        out.append(f'<p class="no-yet">Built. Its files are in agents/{h(built)}, ready for the Arena.</p>')
    if not quick.ready():
        out.append('<p class="no-yet">No model key is set, so Quick start cannot write the card yet. Put '
                   'META_API_KEY or BASETEN_API_KEY in .env and start the page again.</p>')
    elif quick.folder(m) is None:
        out.append('<p class="no-yet">Quick start needs the database folder. Start the page with --db.</p>')
    chat = bool(last) and not built
    if ctx["token"]:
        hint = "" if chat else ' placeholder="I want an agent that answers my store\'s customers on WhatsApp."'
        label = "Your answer, or anything to add or change" if chat else "What agent do you want?"
        out.append(f'<form id="qs-say" method="post" action="/quickstart">{_hidden(ctx)}<div class="field">'
                   f'<textarea class="typed{" sm" if chat else ""}" name="text" rows="{2 if chat else 3}" '
                   f'maxlength="{qs_mod.MAX_TEXT}" aria-label="{label}" dir="auto" required{hint}></textarea></div></form>')
        if chat:
            act = (f'<button class="mod" type="submit" form="qs-say">{icon("chat")}Send</button>'
                   + _post(ctx, "quickstart/build", f'Build{icon("arrow")}', "yes")
                   + _post(ctx, "quickstart/clear", "Start over", "over"))
        else:
            act = ('<p>It starts from zero and earns every lesson in the <b>Arena</b>.</p>'
                   f'<button class="yes" type="submit" form="qs-say">Start the build{icon("arrow")}</button>')
        out.append(f'<div class="act">{act}</div>')
    out.append("</article>")
    return ('<div class="qs"><section class="top s1-top"><div><h1>New agent</h1><p>Say what you want it to do. It '
            'practises in the Arena before it meets a real customer.</p></div></section>'
            '<div class="mode" role="tablist" aria-label="How to build"><span class="on" role="tab" aria-selected="true">'
            'Quick start</span><span class="off" role="tab" aria-selected="false" aria-disabled="true">Brainstorm '
            f'<i>Soon</i></span></div><div class="s1">{"".join(out)}<aside class="side1"><section class="bs" '
            f'aria-label="Brainstorm, coming soon"><div class="bs-h"><b>{icon("chat")}Brainstorm</b><span class="vchip">'
            'Coming soon</span></div><p>Talk the idea through with the AI and agree on the plan first. Then the build '
            'starts.</p></section></aside></div></div>')


def plan_card(card):
    """The model's card as one plain white card, then what it needs, each marked connected or not yet."""
    never = "".join(f'<li dir="auto">{h(x)}</li>' for x in card["never"])
    rows = [("What it does", f'<p dir="auto">{h(card["does"])}</p>'), ("A good result", f'<p dir="auto">{h(card["good"])}</p>')]
    if never:
        rows.append(("It never", f"<ul>{never}</ul>"))
    out = [f'<section class="plan" aria-label="The agent"><h3 dir="auto">{h(card["name"])}</h3><dl>'
           + "".join(f"<div><dt>{t}</dt><dd>{v}</dd></div>" for t, v in rows) + "</dl></section>"]
    if card["needs"]:
        out.append('<div class="needs"><span class="lab">What it needs connected</span>')
        for n in card["needs"]:
            tool = qs_mod.TOOLS.get(n["tool"], "").split(":")[0]
            said = f"Connected: {h(tool)}" if n["connected"] else "Not connected yet"
            out.append(f'<div class="file{" on" if n["connected"] else ""}"><span class="fi">'
                       f'{icon("check" if n["connected"] else "plus")}</span><div><b dir="auto">{h(n["what"])}</b>'
                       f"<small>{said}</small></div><span></span></div>")
        out.append("</div>")
    return "".join(out)


CLIMB = ('<svg class="climb" viewBox="0 0 400 130" role="img" aria-label="On its way to its trust level">'
         '<path d="M210 74 C 280 54, 340 30, 384 18" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2" '
         'stroke-linecap="round" stroke-dasharray="1 7"/><path d="M8 118 C 70 116, 120 100, 210 74" fill="none" '
         'stroke="#fff" stroke-width="2.5" stroke-linecap="round"/><circle cx="210" cy="74" r="6" fill="#fff"/>'
         '<circle cx="384" cy="18" r="3.5" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.5"/></svg>')


def _cap(t):
    t = str(t or "").rstrip(".")
    return t[:1].upper() + t[1:]


def build(m, agent, ctx):
    """Screen 2: the newest Arena run saved next to the database for this agent: the climb as a
    path, the matches it lost as tiles with why. No total of won and lost (the trust level stays
    private, DECISIONS item 17)."""
    arena, _ = m.read_arena()
    run = arena.get(agent) if agent else None
    title = f"Building your {name(agent).lower()}" if agent else "Building your agent"
    tiles, seen = [], set()
    for x in (run or {}).get("lost") or []:  # one tile a practice customer and line; the card's id is never shown
        if (x["card"], x["text"]) in seen:
            continue
        seen.add((x["card"], x["text"]))
        quote = f'<p class="out" dir="auto">"{h(x["text"])}"</p>' if x["text"] else ""
        tiles.append(f'<article class="tile lost"><div class="t-h"><span class="pav">{icon("chat")}</span><div>'
                     '<b>Practice customer</b><small>Made up for the Arena</small></div><span class="res">Lost</span>'
                     f'</div><p class="persona" dir="auto">{h(_cap(x["why"]))}.</p>{quote}</article>')
    if not tiles:
        tiles.append('<div class="ghost"><span class="pav" aria-hidden="true"></span>No saved practice run yet.</div>')
    when = f'Newest run, {mo._when(run["at"])}.' if run else "No saved run yet."
    return (f'<div class="qs"><section class="top"><div><h1>{h(title)}</h1><p class="num">{h(when)}</p></div></section>'
            '<div class="s2"><section class="a-climb" aria-label="How close it is"><article class="glow sq">'
            '<div class="glow-h"><span class="gchip">In the Arena</span><span class="gsub">practising with made-up '
            f'customers</span></div>{CLIMB}<div class="climb-l"><span>Started</span><span>Ready to go live</span></div>'
            '<p class="calm">Nothing to do here. You get one note when it is ready to go live.</p></article></section>'
            '<section class="a-matches" aria-labelledby="m-h"><div class="sec-h"><h2 id="m-h">Practice matches</h2>'
            f'<small>Where it slipped</small></div><div class="tiles">{"".join(tiles)}</div></section></div></div>')
