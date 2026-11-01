"""The two tab page, Today and Agents (LOCKS.md "Product shape: two tabs" and "Today and agent
page: A"), served by reflection/morning.py. It draws from Morning.view() and answers through the
Morning methods only, so no engine rule lives here.

    /              Today: only what needs the user's yes, one light sage card each, then one line
                   per agent about last night; an empty state when nothing waits (DECISIONS 35).
    /agents        the agents (the plugs in the repo and the agents in the database) and New agent.
    /agents/<name> one agent: its status with Pull and Roll back, the box for an idea or a
                   correction (Morning.correct), then its lessons and Reflection notes as rows.
    /new           New agent, Quick start B screen 1; ?ask= routes to a plug or says not yet.
    /new/build     screen 2: the newest Arena run saved next to the database, as tiles and a path.

No count of what is left anywhere (item 35), no trust level and no won and lost total (item 17,
LOCKS Quick start B). No script: Modify is a details element inside its card. Every field is
escaped. With demo days (--demo-days) a Day 1, Day 2, Day 3 switch sits on top, marked Sample
data; each day is its own throwaway copy, so answers there never touch the sample files.
"""
import base64
import hashlib
import re
import urllib.parse

from reflection import morning as mo
from reflection.page_css import CSS

CSP = ("default-src 'none'; style-src 'sha256-" + base64.b64encode(hashlib.sha256(CSS.encode("utf-8")).digest()).decode()
       + "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
h = mo.h
NAMES = {"sales": "Sales agent", "assistant": "Personal assistant", "marketing": "Marketing agent"}
CORRECTED = "sent on the agent page"   # in the source line of a correction (Morning.correct)
ASKS = (("sales", ("sales", "sell", "store", "shop", "order", "customer", "boots")),
        ("assistant", ("assistant", "personal", "calendar", "inbox", "email", "remind", "schedule")))
_AGENT = re.compile(r"^[a-z][a-z_]{0,30}$")
_BACK = re.compile(r"^/(?:agents(?:/[a-z][a-z_]{0,30})?|new(?:/build)?)?$")
ICON = dict(mo.ICONS, pen='<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
            loop='<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
            undo='<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>', pause='<path d="M9 6v12M15 6v12"/>',
            check='<path d="M5 12.5l4.5 4.5L19 7.5"/>', arrow='<path d="M5 12h14M13 6l6 6-6 6"/>',
            back='<path d="M15 6l-6 6 6 6"/>', note='<path d="M6 4h12v16H6z"/><path d="M9 9h6M9 13h6M9 17h3"/>',
            plus='<path d="M12 6v12M6 12h12"/>')


def name(agent):
    return NAMES.get(agent, agent.replace("_", " ").capitalize())


def icon(n, cls="i"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true">{ICON[n]}</svg>'


def route_ask(ask, plugs):
    """The plug a Quick start ask goes to, or None for a kind of agent not built yet."""
    words = set(re.findall(r"[a-z]+", (ask or "").lower()))
    for agent, keys in ASKS:
        if agent in plugs and words & set(keys):
            return agent
    return None


class Pages:
    """The page for one Morning, or for demo days {1: Morning, 2: ..., 3: ...} (sample copies)."""

    def __init__(self, morning=None, *, days=None):
        self.days = dict(days or {})
        self.demo = bool(self.days)
        self.morning = morning if morning is not None else (self.days[min(self.days)] if self.days else None)
        self.csp = CSP

    def back(self, value):
        """Where an answer returns to: one of the page's own paths, with the demo day; else /."""
        parts = urllib.parse.urlsplit(str(value or ""))
        path = parts.path if _BACK.match(parts.path or "") and not parts.netloc and not parts.scheme else "/"
        day = self._day(urllib.parse.parse_qs(parts.query))
        return path + (f"?day={day}" if self.demo else "")

    def morning_for(self, back):
        if not self.demo:
            return self.morning
        return self.days[self._day(urllib.parse.parse_qs(urllib.parse.urlsplit(back).query))]

    def _day(self, query):
        if not self.demo:
            return None
        try:
            d = int((query.get("day") or [""])[0])
        except ValueError:
            d = min(self.days)
        return d if d in self.days else min(self.days)

    def get(self, path, query, token, flash=None):
        """The page for a GET path, or None for an unknown path."""
        day = self._day(query)
        m = self.days[day] if self.demo else self.morning
        q = f"?day={day}" if self.demo else ""
        ctx = {"token": token, "q": q, "day": day, "path": path, "m": m}
        if path == "/":
            return self.shell(today(m.view(), ctx), "today", ctx, flash)
        if path == "/agents":
            return self.shell(agents(m, m.view(), ctx), "agents", ctx, flash)
        if path.startswith("/agents/") and _AGENT.match(path[8:]):
            body = agent_page(m, m.view(), path[8:], ctx)
            return None if body is None else self.shell(body, "agents", ctx, flash)
        if path == "/new":
            return self.shell(new_agent(m, (query.get("ask") or [""])[0], ctx), "agents", ctx, flash)
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
        right = '<span class="sample">Sample data</span>' if self.demo else ""
        days = ""
        if self.demo:
            days = '<nav class="days" aria-label="Sample day">' + "".join(
                f'<a class="{"on" if d == ctx["day"] else ""}" href="{h(ctx["path"])}?day={d}">Day {d}</a>'
                for d in sorted(self.days)) + "</nav>"
        logo = f'<span class="logo">{mo.LOGO}</span><span class="word">Unfenced</span>'
        return "\n".join([
            '<!doctype html><html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
            f'<title>Unfenced</title><style>{CSS}</style></head><body><div class="page">',
            f'<nav class="tisl sq" aria-label="Main"><div class="left">{logo}</div><div class="tnav">{top}</div>'
            f'<div class="right">{days}{right}</div></nav>',
            f'<header class="bar"><div class="brand">{logo}</div><div class="bar-r">{days}{right}</div></header>',
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
    small = "Your line, held by the exam" if item.get("exam") else "New lesson from Reflection"
    out = [f'<article class="yc sq" id="c{h(item["id"])}">', _yc_head(item["agent"], small, risk)]
    out.append(f'<p class="lesson" dir="auto">{h(item["text"])}</p>')
    for r in item["replaces"]:
        out.append(f'<p class="why" dir="auto">A yes takes the place of: {h(r["text"])}</p>')
    out.append(f'<p class="why">{h(item["why"])}</p>')
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


def night_line(a, now):
    """One plain line about an agent's last night, from its lessons; never a count of what is left."""
    day = mo.DAY
    new = [i for i in a["new"] if i.get("origin") != "person"]
    kept = [t for t in a["live"] if t["state"] == mo.KEPT and (t.get("decided_at") or 0) >= now - day]
    pulled = [i for i in a["pulled"] if (i["pulled_at"] or 0) >= now - day and not str(i.get("pulled_why") or "").startswith(mo.EDITED)]
    bits = []
    if new:
        bits.append("Reflection wrote a new lesson." if len(new) == 1 else f"Reflection wrote {len(new)} new lessons.")
    if kept:
        bits.append("A trial ended and its lesson is kept.")
    if pulled:
        bits.append("A lesson was pulled.")
    if any(CORRECTED in (i.get("source") or "") for i in a["live"]):
        bits.append("Your correction runs in its chats now.")
    if a.get("arena"):
        bits.append("It practised in the Arena.")
    return " ".join(bits) or "A quiet night. Nothing changed."


def status_of(m, agent):
    return "Live" if agent in m._live() else "Training"


def night_html(m, view):
    rows = []
    for a in view["agents"]:
        st = status_of(m, a["agent"])
        rows.append(f'<div class="nl"><span class="av">{mo._agent_icon(a["agent"])}</span><div><b>{h(name(a["agent"]))} '
                    f'<span class="st{" live" if st == "Live" else ""}">{st}</span></b>'
                    f'<p>{h(night_line(a, view["at"]))}</p></div></div>')
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
    names = sorted(set(m.plugs) | {a["agent"] for a in view["agents"]})
    rows = "".join(f'<a class="agl" href="/agents/{h(a)}{ctx["q"]}"><span class="av">{mo._agent_icon(a)}</span>'
                   f'<b>{h(name(a))}</b><span class="st{" live" if status_of(m, a) == "Live" else ""}">'
                   f'{status_of(m, a)}</span></a>' for a in names)
    return ('<section class="top"><h1>Agents</h1><p>Each one learns from its own chats.</p></section><div class="col">'
            f'<a class="yes" href="/new{ctx["q"]}">{icon("plus")}New agent</a>'
            f'<section class="grp sq" aria-label="Your agents">{rows}</section></div>')


def _chip(i):
    if i["state"] == mo.TRYING and CORRECTED in (i.get("source") or ""):
        return "hot", "Hotfix", f'From your correction, {mo._date(i["added_at"])}. Reflection checks it tonight.'
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
    plan = m.rollback_plan(agent) if a["buttons"] else None
    if tok and plan is not None:
        snap, steps, code = plan
        roll = _post(ctx, "rollback", f'{icon("undo")}Roll back', "gb", agent=agent, code=code)
    elif a["buttons"]:
        roll = f'<button class="gb" type="button" disabled>{icon("undo")}Roll back</button>'
    out = [f'<div class="colhead"><a class="back" href="/agents{ctx["q"]}">{icon("back")}Agents</a>'
           f'<section class="top ag-top"><h1>{h(name(agent))}</h1></section></div><div class="col">',
           f'<section class="status sq" aria-label="Status"><div class="st-l"><span class="states" role="img" '
           f'aria-label="Status: {st}">{states}</span><small>{"Answering chats" if st == "Live" else "Practising in the Arena"}'
           f'</small></div><div class="st-r">{roll}<button class="gb" type="button" disabled title="Not built yet">'
           f'{icon("pause")}Pull</button></div></section>']
    if tok:
        out.append(f'<section class="say sq" aria-label="Send an idea or a correction"><form method="post" action="/correct">'
                   f'{_hidden(ctx, agent=agent)}<span class="lab">Send an idea or a correction</span><div class="box">'
                   f'<textarea name="line" aria-label="Your idea or correction" maxlength="{mo.MAX_LEN}" dir="auto" required>'
                   f'</textarea></div><div class="say-f"><p class="quiet">{icon("loop")}Goes to a hotfix now and to '
                   f'Reflection tonight.</p><button class="send" type="submit">Send{icon("arrow")}</button></div></form></section>')
    rows = []
    for i in a["live"] + a["waiting"] + a["pulled"][:5]:
        cls, chip, small = _chip(i)
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
            notes.append(f'<div class="nr"><span class="to">{icon("bulb")}Your idea, {h(mo._date(i["added_at"]))}</span>'
                         f'<p dir="auto">{h(i["text"])}</p></div>')
    if a.get("arena"):
        notes.append(f'<div class="nr"><span class="to">{icon("note")}From the Arena</span>'
                     f'<p dir="auto">{h(a["arena"]["line"])}</p></div>')
    out.append('<section class="grp sq" aria-labelledby="r-h"><h3 id="r-h">Reflection notes</h3>'
               + ("".join(notes) or '<div class="nr"><p>Nothing yet.</p></div>') + "</section></div>")
    return "".join(out)


# ---- New agent (Quick start B) -----------------------------------------------------------------

def new_agent(m, ask, ctx):
    agent = route_ask(ask, m.plugs) if ask else None
    q = ctx["q"]
    day = f'<input type="hidden" name="day" value="{h(ctx["day"])}">' if ctx["day"] else ""
    if ask and agent is None:
        verdict = ('<p class="no-yet">Not yet. Quick start builds a sales agent or a personal assistant today. '
                   'For any other kind of agent, Brainstorm is coming soon.</p>')
    elif agent:
        verdict = f'<p class="no-yet">It heard: {h(name(agent))}.</p>'
    else:
        verdict = ""
    go = (f'<a class="yes" href="/new/build?agent={h(agent)}{"&day=" + str(ctx["day"]) if ctx["day"] else ""}">'
          f'Start the build{icon("arrow")}</a>' if agent else
          f'<button class="yes" type="submit">Start the build{icon("arrow")}</button>')
    return ('<div class="qs"><section class="top s1-top"><div><h1>New agent</h1><p>Say what you want it to do. It '
            'practises in the Arena before it meets a real customer.</p></div></section>'
            '<div class="mode" role="tablist" aria-label="How to build"><span class="on" role="tab" aria-selected="true">'
            'Quick start</span><span class="off" role="tab" aria-selected="false" aria-disabled="true">Brainstorm '
            '<i>Soon</i></span></div><div class="s1"><article class="ask sq" aria-label="Quick start">'
            f'<form method="get" action="/new">{day}<span class="lab">What agent do you want?</span><div class="field">'
            f'<textarea class="typed" name="ask" rows="2" maxlength="300" aria-label="What agent do you want?" '
            f'style="width:100%;border:0;background:transparent;resize:none;outline:0" '
            f'placeholder="I want a sales agent for my store on WhatsApp.">{h(ask)}</textarea></div>{verdict}'
            '<div class="needs"><span class="lab">What it needs to know</span><div class="file"><span class="fi">'
            f'{icon("note")}</span><div><b>Brand file</b><small>Voice, prices, sizes, delivery areas</small></div><span></span>'
            '</div></div><div class="act"><p>It starts from zero and earns every lesson in the <b>Arena</b>.</p>'
            f'{go}</div></form></article><aside class="side1"><section class="bs" aria-label="Brainstorm, coming soon">'
            f'<div class="bs-h"><b>{icon("chat")}Brainstorm</b><span class="vchip">Coming soon</span></div><p>Talk the '
            'idea through with the AI and agree on the plan first. Then the build starts.</p></section></aside></div></div>')


CLIMB = ('<svg class="climb" viewBox="0 0 400 130" role="img" aria-label="On its way to its trust level">'
         '<path d="M210 74 C 280 54, 340 30, 384 18" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2" '
         'stroke-linecap="round" stroke-dasharray="1 7"/><path d="M8 118 C 70 116, 120 100, 210 74" fill="none" '
         'stroke="#fff" stroke-width="2.5" stroke-linecap="round"/><circle cx="210" cy="74" r="6" fill="#fff"/>'
         '<circle cx="384" cy="18" r="3.5" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.5"/></svg>')


def build(m, agent, ctx):
    """Screen 2: the newest Arena run saved next to the database for this agent: the climb as a
    path, the matches it lost as tiles with why. No total of won and lost (the trust level stays
    private, DECISIONS item 17)."""
    arena, _ = m.read_arena()
    run = arena.get(agent) if agent else None
    title = f"Building your {name(agent).lower()}" if agent else "Building your agent"
    tiles = []
    for x in (run or {}).get("lost") or []:
        quote = f'<p class="out" dir="auto">"{h(x["text"])}"</p>' if x["text"] else ""
        tiles.append(f'<article class="tile lost"><div class="t-h"><span class="pav">{h((x["card"] or "?")[:1].upper())}'
                     f'</span><div><b dir="auto">{h(x["card"] or "Practice customer")}</b><small>Practice customer</small>'
                     f'</div><span class="res">Lost</span></div><p class="persona" dir="auto">{h(x["why"])}</p>{quote}</article>')
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
