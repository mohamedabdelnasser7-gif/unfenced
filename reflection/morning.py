"""The morning page: what the engine learned for every agent, on one local page, and a
person's answers to it.

    python3 -m reflection.morning [--db PATH] [--html OUT]

It opens the agents' database (data/ascent.db unless --db names another) and the night
reports saved next to it (reflection/night.py), and serves one page on 127.0.0.1 only, on
MORNING_PORT (default 8082). With --html OUT it writes the page once as a static file with
no buttons, for a screenshot, and serves nothing. It is not scheduled: a person runs it, and
Ctrl+C stops it.

For every agent in the database, read from the lessons, trials and trial marks tables:
1. The night's notes, from the newest saved night report of that agent, and the latest
   snapshot of its lessons with the command that rolls back to it (reflection/snapshots.py).
   A note the night handed over to another agent (engine/handover.py) is one quiet line under
   them: where it went and what it says, no case id, no count and no button; it asks nothing
   (DECISIONS items 19 and 35).
   When the Arena got stuck (arena/run.py), the newest stuck item saved next to the database
   (arena-<agent>-<run>.json): its line and the held-out matches it lost, each quoting a turn.
   For the personal assistant, the open new mode card the night wrote next to the database
   (assistant/newmode.py, mode-assistant-<run>.json): the mode's name, the user's words behind
   it and the Arena's counts, with Yes, Rename and Drop. An answer goes through
   newmode.answer_card to the assistant's folder (--assistant-state, data/assistant unless
   named); the card is found by its file name among the open cards only, never by a path from
   the form. A card with no answer changes nothing (DECISIONS item 35).
   A run with Reflection between its rounds (arena/rounds.py) writes such an item too, stuck or
   not: each round's gate wins and the lessons proposed, passed, refused and handed on after it.
2. New in the last day: each lesson added since a day ago, on trial, waiting for a yes or
   waiting its turn, with why.
3. Live: the kept lessons and the lessons on trial, each with Stop and Edit.
4. Waiting: the lessons waiting for a yes or for their turn.
5. Trials: each trial's outcome (kept, pulled, unclear, paused, still running with its days
   left), its pings, and the cases on each side with the row that settled each one, by how
   each ended, not by id.
6. Pulled, with why, each with Bring back, or the lesson its line is back as already.
Every link is shown: how many cases are behind a lesson (from the saved night report, which
names them), the lesson it was adapted from, the lesson it was edited from or into, the lesson
it was brought back from or as, the lessons a "replace it?" card names, each trial side's
cases with the rows that settled them, and the verdict, unclear, longer, pause and ping marks.
No raw case id is on the page: the ids stay in the saved night report. A study lesson's source
line names its two sides from the pattern's own words (sides()), never "with it", so "it" never
reads as the lesson.

The look. The locked A3 design (_system/hackathon/design/morning/r1/opt-a3.html): a greeting
with the day in Cairo time, the waiting stack (the first card open in light sage mist with Yes
and No, the next ones under it as white passes that open), the first lesson on trial as a dark
sage card, then Ideas, Facts and each agent's switches as white rows that open, and every
agent's lessons below. The tabs (a bar on the bottom edge on a phone, one top island on a wide
screen) are links to those parts, #today, #lessons, #ideas, #facts and #agents; no numbers row up
top. No script: the tabs are anchors and every part opens with details and summary. Every time
is Cairo time (Africa/Cairo).

Light (DECISIONS item 35). The page is never a chore: what is open on it is only what needs the
user (the cards that wait for a yes, the unclear cards, a new mode card, a paused trial with its
Stop, the switches) and what the agents are trying now (the trial card, with its days left,
which is the trial's own clock, not the user's). Nothing counts what is left to answer: no badge
on the Lessons tab, no count beside "Waiting for your yes", no word of the cards behind the five
on the page. The gate's fixed and broke counts stay (item 27): they are evidence, not chores.
Everything that needs no answer (each agent's night notes, the Arena, the snapshot, every
lesson, the trials, the pulled lessons and any report that could not be read) sits in one fold,
"What happened overnight", closed until opened. A day with no answers changes nothing: a lesson
with no yes stays off, and the page reads the same the next morning.

The cards. Every lesson that waits for a person's first yes is a card with Yes, No and Edit:
high risk, a "replace it?" card, or a line close to a pulled one or to one that failed the eval
gate. At most CARDS (5) show on the page, across agents, ranked by what they could gain:
    gain = the chance it is better x the gap between the two sides' good rates,
each side's rate read as (1 + good) / (2 + cases), the study's even start. The chance and the
case counts come from the study's card in the saved night reports. Ties go to the card with
more cases, then the older lesson. A card with no numbers (adapted from a kept lesson, or with
no saved report) comes after every card with numbers, the oldest first. A "replace it?" card
shows its own line and each live line it would pull. An agent with no plug in the repo is
shown without buttons, and its lessons are not cards. A card whose lesson took the gate with its
counts (engine/exam.py, DECISIONS item 27) says in one line how many cases it fixed and broke,
and McNemar's p-value in words only (likely a real gain, likely real harm, could be chance, or
nothing changed); it ranks nothing and asks nothing (item 35).

The unclear cards. A trial that ended with too few settled cases or sources on a side to
tell is unclear (engine/trial.py): the lesson is given in no case and waits for a person.
Each one is a card of its own, every one shown, with its numbers (the settled cases and
good ones on each side, the sources, the chance it is better), whose idea it was, and two
buttons: Keep on trial longer (whole days, 1 to LONGER_DAYS, from now; the same share, the
numbers so far still count) and Drop (pulled, its why "unclear, dropped by <who>"). Keep
longer is refused while another lesson is on trial on its stages.

The ideas. An idea is a lesson with no past cases behind it (kind "idea" in engine/lessons.py):
the night study's idea part writes some, and a person types some here. Every idea waiting or
on trial, of an agent with a plug, shows in its own part of the page with its card
(engine/study.py idea_card): whose idea it is, the result it must move and the days that
result takes to show, about how many days after its trial starts we know, what must not get
worse, how sure today ("no past cases: this is a try") and its trial level. An idea that
waits for a yes is a card above too, with these lines in place of the study numbers. With
buttons, each agent with a plug has a Try an idea form: one line and a stage.

Answers. Yes: Lessons.approve, or Lessons.replace when the card names live lessons; the
lesson goes on trial or waits its turn. The Yes form carries the lines the card named, and a
card that names other lines by then is refused. No: pulled, its why "no from the user". Stop on a
live lesson: pulled, with a one line why. Edit: a lesson is never rewritten, so Edit adds the
new line and pulls the old one; the new line's source line names the old lesson, and the old
one's why names the new lesson. What the new line becomes is decided in one place,
person_line(): a trial like any other, or its turn when its stage has a trial; once the old
lesson is pulled, the lessons waiting their turn start when their stages are free. Bring back
on a pulled lesson: Lessons.bring_back; the pulled one stays pulled and a new lesson with its
line, linked to it and signed by the person, goes on trial or waits its turn. A pulled lesson
whose line is back already shows that lesson instead. Try an idea: Morning.idea, a person's own
line (Lessons.add, kind idea), so no yes and no skip: a trial at the level that applies, the
same share and days as an agent's idea, or its turn. Refused for a line that is a live or
waiting lesson already, or a pulled one (Bring back is the way back for that line). For an agent
the page has an examiner for (the Sales agent, when its plug names an exam), the idea takes the
exam first (engine.lessons.takes_exam), run before the answer's transaction opens so its model
calls never hold the write lock; a fail holds it with its line shown, and Yes on its card starts
it anyway. Edit, Bring back and Yes run no exam.

The switches (call 16, engine/switches.py). Each agent with a plug shows its two switches,
who flipped each and when, and every flip. The trial level, fast or careful (careful until a
person flips it), is the level new trials take; a trial keeps the level it started with.
Accept high risk is off until a person turns it on: on, a high risk lesson goes on trial with
no yes and is still watched, studied each night and judged by its verdict. Under it a check
mark turns it off by itself after the days the person picks, 1 to switches.MOST_DAYS; the
page shows when it ends. The locks that hold whatever the switches say are listed under it
(call 20: a lesson that copies words from its cases always waits for a yes). A lesson that
waits for a yes or waits its turn shows the level its trial will take, and a person can pick
fast or careful for that lesson alone until its trial starts. Every flip goes through
engine/switches.py, from the page's own forms only, and the next night report names the
switches (night.switches_line).

The fact cards (call 10, reflection/facts.py). Facts worked out from an agent's results only,
each with the numbers behind it, Keep and Dismiss. An answer is saved with who and when; a
kept fact is shown under Kept facts. Nothing acts on a fact by itself.

Safety. The server listens on 127.0.0.1 only. Every request needs a Host of 127.0.0.1 or
localhost on the page's port. Every POST also needs an Origin of the same, and the token made
when the page starts and put in its forms; anything else is refused and changes nothing.
Every field is escaped, since lessons, notes and case ids come from models and customers. The
page loads no outside font, script or image, and its Content-Security-Policy allows only its
own inline style.

Not built yet (Mohamed's open calls): cards for a person's fixes.
"""
import argparse
import base64
import hashlib
import hmac
import html
import json
import math
import re
import secrets
import sqlite3
import sys
import threading
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import exam as exam_mod
from engine import lessons as lessons_mod
from engine import plug as plug_mod
from engine import risk as risk_mod
from engine import study as study_mod
from engine import switches as switches_mod
from engine import trial as trial_mod
from engine.lessons import KEPT, MAX_LEN, PULLED, TRYING, WAITING, Lessons
from kit import env
from kit import switch as switch_mod
from kit.db import DEFAULT_PATH, Db
from reflection import PLUG as SALES
from reflection import facts as facts_mod
from reflection import night as night_mod
from reflection import snapshots

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
PORT_DEFAULT = "8082"
DAY = 86400.0
CAIRO = ZoneInfo("Africa/Cairo")  # every time on the page is Cairo time, never UTC
CARDS = 5                       # cards on the page at a time, across agents; an answered card makes room
BY = "the user"                 # who answers on this page (DECISIONS item 34)
MAX_BODY = 16384                # bytes in one POST
MAX_REPORT = 50 * 1024 * 1024   # bytes; a bigger saved report is skipped
EDITED = "edited by "
_EDITED_FROM = re.compile(r"^edited by .+? from lesson (\d+)")
_EDITED_INTO = re.compile(r"^edited by .+? into lesson (\d+)")
_REPLACED_BY = re.compile(r"^replaced by lesson (\d+)$")
# reflection/importer.py saves past chats on "history:whatsapp" or "history:instagram"; no agent answered them
_REAL_CHANNEL = "substr(chats.channel, 1, 8) != 'history:'"


def _has_table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


CSS = """
:root{--bone:#F4F3EF;--ink:#0B0F12;--ink-2:#4b514f;--ink-3:#5d6360;--mist-ink:#2f3433;
--card:#ffffff;--card-2:#FAF9F6;--card-3:#F6F5F1;--card-4:#F1F0EB;--chip:#EDECE6;--line:rgba(11,15,18,.08);--edge:rgba(11,15,18,.16);
--sage-a:#5f7471;--sage-b:#2f3a39;--sage-c:#141a19;--volt:#d7f24b;
--font:"Outfit",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,Menlo,Consolas,monospace;
--ease:cubic-bezier(.2,.8,.2,1);--t:200ms;--t-press:160ms;--r-card:28px;--r-inner:20px;
--shadow-card:0 1px 2px rgba(11,15,18,.05),0 24px 48px -28px rgba(11,15,18,.22);
--shadow-soft:0 1px 2px rgba(11,15,18,.04),0 12px 28px -18px rgba(11,15,18,.18);
--bubble:radial-gradient(120% 120% at 30% 18%,#fff,rgba(255,255,255,.92) 55%,rgba(246,245,241,.9) 80%);
--bubble-shadow:inset 0 1px 1px #fff,inset 0 -6px 12px rgba(11,15,18,.05),0 10px 22px -12px rgba(11,15,18,.32);
--glass:rgba(250,249,246,.84)}
@supports (corner-shape:squircle){:root{--r-card:44px;--r-inner:32px}.sq{corner-shape:squircle}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--bone);color:var(--ink);font:400 15px/1.5 var(--font);-webkit-font-smoothing:antialiased;
background-image:radial-gradient(90% 60% at 20% -10%,rgba(255,255,255,.75),rgba(255,255,255,0) 70%);background-repeat:no-repeat}
a{color:inherit;text-decoration:underline;text-decoration-color:rgba(11,15,18,.35);text-underline-offset:3px}
a:hover{text-decoration-color:currentColor}
:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.num{font-variant-numeric:tabular-nums}
.vh{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
svg.i{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex:none}
p{margin:0}
ul{list-style:none;margin:0;padding:0}
code,.cases{font-family:var(--mono);font-size:13px;word-break:break-all}
.page{max-width:1232px;margin:0 auto;padding:24px 48px 112px;overflow-wrap:anywhere}
[id]{scroll-margin-top:16px}
.bar{display:flex;align-items:center;justify-content:space-between;gap:12px;height:48px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo,.tlogo{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:var(--bubble);box-shadow:var(--bubble-shadow);color:var(--ink);flex:none}
.logo svg,.tlogo svg{width:24px;height:24px}
.word{font:600 17px/1 var(--font);letter-spacing:-.035em}
.where{font:400 15px/1 var(--font);color:var(--ink-2);padding-left:12px;border-left:1px solid var(--line);white-space:nowrap}
.sample,.tsample{font:500 12px/16px var(--font);letter-spacing:.04em;color:var(--ink-2);padding:4px 12px;border-radius:999px;background:var(--chip);white-space:nowrap}
.top{margin:40px 0 32px}
.hello h1{margin:0;font:300 56px/60px var(--font);letter-spacing:-.035em}
.hello p{margin:8px 0 0;font:400 17px/24px var(--font);color:var(--ink-2)}
.flash{margin-top:16px;padding:12px 20px;border-radius:20px;background:var(--card);box-shadow:var(--shadow-soft);font:400 15px/22px var(--font);color:var(--ink)}
.grid{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:32px;align-items:start}
.col{display:flex;flex-direction:column;gap:40px;min-width:0}
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:0 4px 16px}
.sec-h h2{margin:0;font:500 20px/24px var(--font);letter-spacing:-.01em}
.sec-h small{font:400 14px/20px var(--font);color:var(--ink-2);text-align:right}
.lab{display:flex;align-items:center;gap:8px;font:500 12px/16px var(--font);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}
.meta{font:400 14px/20px var(--font);color:var(--ink-2);margin-top:8px}
.line{font-weight:500;color:var(--ink)}
.old{text-decoration:line-through}
.calm{background:var(--card);border-radius:var(--r-card);box-shadow:var(--shadow-soft);padding:24px 28px}
.calm-h{font:400 20px/28px var(--font);letter-spacing:-.01em}
.calm p+p{margin-top:4px;font-size:14px;line-height:20px;color:var(--ink-2)}
.stack{position:relative;padding-bottom:4px}
.pass{position:relative;z-index:5;border-radius:var(--r-card);padding:28px 32px;
background:radial-gradient(60% 70% at 100% 0%,rgba(95,116,113,.36) 0%,rgba(95,116,113,0) 100%),
radial-gradient(55% 60% at 0% 100%,rgba(143,163,158,.34) 0%,rgba(143,163,158,0) 100%),
linear-gradient(160deg,#e2e8e5 0%,#edefeb 55%,#f4f3ef 100%);
box-shadow:var(--shadow-card),inset 0 1px 0 rgba(255,255,255,.7),inset 0 0 0 1px rgba(42,51,50,.06)}
.pass-h{display:flex;align-items:center;justify-content:space-between;gap:16px}
.agent{display:flex;align-items:center;gap:12px;min-width:0}
.agent .av{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--card-4);color:var(--ink);flex:none}
.pass .agent .av{background:#fff}
.agent strong{display:block;font:500 15px/20px var(--font)}
.agent small{display:block;font:400 13px/16px var(--font);color:var(--ink-2)}
.risk{display:inline-flex;align-items:center;gap:8px;font:500 12px/16px var(--font);padding:6px 12px;border-radius:999px;background:var(--chip);color:var(--ink);white-space:nowrap}
.risk .dot{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.9}
.risk-high{background:var(--ink);color:#fff}
.lesson{margin:24px 0 0;font:400 32px/40px var(--font);letter-spacing:-.022em;text-wrap:pretty}
.why{margin:12px 0 0;font:400 16px/24px var(--font);color:var(--ink-2)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px;padding:20px 24px;border-radius:var(--r-inner);background:var(--card-3)}
.pair .lab{grid-column:1 / -1;margin-bottom:-8px}
.stat{min-width:0}
.stat b{display:block;font:300 32px/40px var(--font);letter-spacing:-.02em;font-variant-numeric:tabular-nums;white-space:nowrap}
.stat b small{font:400 16px/1 var(--font);letter-spacing:0;color:var(--ink-2);margin:0 4px}
.stat span{display:block;margin-top:4px;font:400 14px/20px var(--font);color:var(--ink-2)}
.ilines{margin-top:24px;padding:16px 24px 20px;border-radius:var(--r-inner);background:var(--card-3)}
.gain{margin-top:12px;font:400 14px/20px var(--font);color:var(--ink-2)}
.pass .why,.pass .gain,.pass .trial-l,.pass .lab,.pass .stat span,.pass .stat b small,.pass .agent small,.pass .meta,.pass .more-l summary{color:var(--mist-ink)}
.pass .pair,.pass .ilines{background:rgba(255,255,255,.6)}
.act{display:flex;align-items:center;flex-wrap:wrap;gap:16px;margin-top:24px}
.act form{margin:0}
.trial-l{flex:1 1 200px;min-width:0;font:400 14px/20px var(--font);color:var(--ink-2)}
.trial-l strong{font-weight:500;color:var(--ink)}
.act form.no button{width:56px;height:56px;padding:0;border-radius:50%;display:grid;place-items:center;background:var(--bubble);
box-shadow:var(--bubble-shadow),0 0 0 1px rgba(11,15,18,.06);font:500 16px/1 var(--font);color:var(--ink)}
.act form.no button:hover{box-shadow:inset 0 1px 1px #fff,0 0 0 1px rgba(11,15,18,.1),0 14px 26px -12px rgba(11,15,18,.38);filter:none}
.act form.yes button{height:56px;padding:0 28px 0 22px;border-radius:28px;display:inline-flex;align-items:center;justify-content:center;gap:10px;
background:var(--volt);color:var(--ink);font:600 16px/1 var(--font);box-shadow:inset 0 1px 0 rgba(255,255,255,.6),0 12px 24px -14px rgba(90,110,0,.7)}
.act form.yes button::before{content:"";width:12px;height:7px;border-left:2px solid currentColor;border-bottom:2px solid currentColor;transform:translateY(-2px) rotate(-45deg)}
.act form.yes button:hover{filter:brightness(1.04)}
.peek{position:relative;margin-top:-24px;border-radius:var(--r-card);background:var(--card);box-shadow:var(--shadow-soft)}
.peek summary{list-style:none;display:flex;align-items:center;gap:12px;padding:36px 28px 14px;cursor:pointer;border-radius:var(--r-card);
font:400 15px/20px var(--font);color:var(--ink-2);transition:transform var(--t) var(--ease),color var(--t) var(--ease)}
.peek summary::-webkit-details-marker{display:none}
.peek summary:hover{transform:translateY(2px);color:var(--ink)}
.peek summary:active{transform:translateY(2px) scale(.99)}
.peek .pt{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.peek[open] .pt{white-space:normal;color:var(--ink)}
.peek[open] .chev{transform:rotate(90deg)}
.peek-in{padding:4px 28px 28px}
.peek-in .lesson{font-size:24px;line-height:32px;margin-top:16px}
.peek.p1{z-index:4;width:calc(100% - 24px);margin-left:12px}
.peek.p2{z-index:3;width:calc(100% - 48px);margin-left:24px;opacity:.96}
.peek.p3{z-index:2;width:calc(100% - 72px);margin-left:36px;opacity:.92}
.peek.p4{z-index:1;width:calc(100% - 96px);margin-left:48px;opacity:.92}
.peek[open]{opacity:1}
.more-l{margin-top:20px;border-top:1px solid var(--line);padding-top:4px}
.more-l>summary{list-style:none;display:inline-flex;align-items:center;gap:6px;min-height:40px;cursor:pointer;font:500 14px/20px var(--font);color:var(--ink-2);
transition:color var(--t) var(--ease)}
.more-l>summary::-webkit-details-marker{display:none}
.more-l>summary::after{content:"";width:7px;height:7px;border-right:1.6px solid currentColor;border-bottom:1.6px solid currentColor;transform:translateY(-2px) rotate(45deg);
transition:transform var(--t) var(--ease)}
.more-l[open]>summary::after{transform:translateY(1px) rotate(-135deg)}
.more-l>summary:hover{color:var(--ink)}
.ml-in{padding-bottom:4px}
.fld{display:flex;flex-direction:column;gap:6px;margin-top:12px;font:400 14px/20px var(--font);color:var(--ink-2)}
.glow{position:relative;overflow:hidden;border-radius:var(--r-card);padding:28px 28px 24px;color:#fff;
background:radial-gradient(22% 30% at 100% 0%,rgba(176,192,187,.5),rgba(176,192,187,0) 100%),
radial-gradient(60% 50% at 0% 100%,rgba(8,11,10,.55),rgba(8,11,10,0) 100%),
radial-gradient(55% 45% at 78% 92%,rgba(95,116,113,.55),rgba(95,116,113,0) 100%),
linear-gradient(160deg,var(--sage-a) 0%,var(--sage-b) 45%,var(--sage-c) 100%);
box-shadow:0 30px 56px -30px rgba(20,26,25,.7),inset 0 1px 0 rgba(255,255,255,.18)}
.glow a{color:#fff}
.glow-h{display:flex;align-items:center;justify-content:space-between;gap:12px}
.gl{display:flex;align-items:center;flex-wrap:wrap;gap:4px 12px;min-width:0}
.gchip{font:500 12px/16px var(--font);padding:6px 12px;border-radius:999px;background:rgba(11,15,18,.34);color:#fff;white-space:nowrap}
.gsub{font:400 13px/16px var(--font);color:#fff}
.glass-b{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;color:#fff;flex:none;
background:radial-gradient(120% 120% at 30% 18%,rgba(255,255,255,.42),rgba(255,255,255,.1) 50%,rgba(255,255,255,.06) 75%);
border:1px solid rgba(255,255,255,.3);box-shadow:inset 0 1px 1px rgba(255,255,255,.55),0 10px 20px -10px rgba(0,0,0,.5);
transition:transform var(--t-press) var(--ease),background var(--t) var(--ease)}
.glass-b:hover{background:radial-gradient(120% 120% at 30% 18%,rgba(255,255,255,.52),rgba(255,255,255,.16) 50%,rgba(255,255,255,.1) 75%)}
.glass-b:active{transform:scale(.96)}
.glow .lesson{font-size:24px;line-height:32px;margin-top:20px;letter-spacing:-.015em}
.glow .pair{background:rgba(11,15,18,.3);margin-top:20px;padding:16px 20px;gap:16px}
.glow .lab,.glow .stat span,.glow .stat b small{color:#fff}
.glow .stat b{font-size:28px;line-height:36px}
.prog{margin-top:20px}
.prog-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.prog-row b{font:300 28px/32px var(--font);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.prog-row b small{font:400 15px/1 var(--font);letter-spacing:0;margin-left:6px;color:#fff}
.prog-row span{font:400 13px/16px var(--font);color:#fff}
.track{display:block;width:100%;height:3px;margin-top:12px}
.track .tb{fill:rgba(255,255,255,.22)}
.track .tf{fill:#fff}
.rows{display:flex;flex-direction:column;gap:8px}
.pill{background:var(--card);border-radius:32px;box-shadow:var(--shadow-soft);transition:box-shadow var(--t) var(--ease)}
.pill:hover{box-shadow:0 1px 2px rgba(11,15,18,.05),0 16px 32px -18px rgba(11,15,18,.26)}
.pill>summary{list-style:none;display:grid;grid-template-columns:40px minmax(0,1fr) auto 20px;align-items:center;gap:12px;min-height:64px;padding:8px 16px 8px 12px;cursor:pointer;border-radius:32px;
transition:transform var(--t-press) var(--ease)}
.pill>summary::-webkit-details-marker{display:none}
.pill>summary:active{transform:scale(.99)}
.pill .ic{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--card-3);color:var(--ink)}
.pill .ic svg.i{width:18px;height:18px}
.pill .tx{min-width:0}
.pill .tx strong{display:block;font:500 15px/20px var(--font)}
.pill .tx small{display:block;font:400 13px/18px var(--font);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vchip{display:inline-block;font:500 12px/16px var(--font);padding:4px 10px;border-radius:999px;background:var(--chip);color:var(--ink);white-space:nowrap;font-variant-numeric:tabular-nums}
.chev{color:var(--ink-3);transition:transform var(--t) var(--ease)}
.pill[open]>summary .chev{transform:rotate(90deg)}
.pill[open]{border-radius:var(--r-card)}
.more{padding:4px 20px 20px 64px;font:400 14px/20px var(--font);color:var(--ink-2)}
.more .big{font:400 18px/24px var(--font);color:var(--ink);letter-spacing:-.01em;margin-top:8px}
.mh{font:500 15px/20px var(--font);color:var(--ink);margin:16px 0 0}
.more>.mh:first-child{margin-top:4px}
.sub{margin-top:12px;padding:16px 18px;border-radius:var(--r-inner);background:var(--card-3)}
.sub .vchip{background:var(--card)}
.seg{display:inline-flex;flex-wrap:wrap;padding:4px;border-radius:20px;background:var(--card-3);margin-top:8px}
.seg span{display:flex;flex-direction:column;padding:6px 14px;border-radius:16px;font:400 12px/16px var(--font);color:var(--ink-2)}
.seg span strong{font:500 14px/20px var(--font);color:var(--ink)}
.seg span.on{background:var(--card);color:var(--ink);box-shadow:var(--shadow-soft)}
.sw-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-top:16px}
.toggle{width:44px;height:26px;border-radius:13px;background:#8b908d;position:relative;flex:none;margin-top:2px}
.toggle::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(11,15,18,.25)}
.toggle.on{background:var(--ink)}
.toggle.on::after{left:21px}
.locks{margin:8px 0 0}
.locks li{position:relative;padding-left:16px;margin-top:6px}
.locks li::before{content:"";position:absolute;left:2px;top:8px;width:5px;height:5px;border-radius:50%;background:var(--ink-3)}
.wcard{background:var(--card);border-radius:var(--r-card);box-shadow:var(--shadow-soft);padding:24px 28px}
.wcard+.wcard{margin-top:12px}
.wcard .lesson{font-size:24px;line-height:32px;margin-top:16px}
.wcard .pair{margin-top:20px}
.byagent{margin-top:56px}
.overnight>summary{list-style:none;display:flex;align-items:center;gap:12px;margin:0 4px 16px;border-radius:var(--r-inner)}
.overnight>summary::-webkit-details-marker{display:none}
.overnight>summary h2{margin:0;font:500 20px/24px var(--font);letter-spacing:-.01em}
.overnight>summary small{flex:1;font:400 14px/20px var(--font);color:var(--ink-2);text-align:right}
.overnight[open]>summary .chev{transform:rotate(90deg)}
.agent-sec{background:var(--card);border-radius:var(--r-card);box-shadow:var(--shadow-soft);padding:28px 32px 32px}
.agent-sec+.agent-sec{margin-top:16px}
.agent-sec>h2{display:flex;align-items:center;gap:12px;margin:0;font:500 20px/24px var(--font);letter-spacing:-.01em}
.agent-sec>h2 .av{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--card-3);color:var(--ink);flex:none}
.agent-sec h3,.more h3{margin:28px 0 10px;font:500 12px/16px var(--font);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}
.agent-sec li.meta{margin-top:6px}
li.item{margin:0 0 8px;padding:16px 20px;border-radius:var(--r-inner);background:var(--card-3)}
li.item .line{display:block;margin-top:4px;font:400 17px/24px var(--font);letter-spacing:-.01em}
li.item>.meta:first-child{margin-top:0}
details>summary{cursor:pointer}
li.item details,.ml-in details,.agent-sec>details,.more details{margin-top:10px}
li.item details>summary,.ml-in details>summary,.agent-sec>details>summary,.more details>summary{font:500 14px/20px var(--font);color:var(--ink-2)}
form{display:inline-flex;flex-wrap:wrap;gap:8px;margin:12px 8px 0 0;align-items:center;max-width:100%}
form.wrap{display:flex}
form label{display:inline-flex;align-items:center;gap:8px;font:400 14px/20px var(--font);color:var(--ink)}
input[type=text],select{font:400 15px/20px var(--font);color:var(--ink);height:40px;padding:0 16px;border:0;border-radius:20px;background:var(--card);
box-shadow:inset 0 0 0 1px var(--edge);min-width:0;flex:1 1 220px;max-width:100%}
select{flex:0 1 auto}
input[type=number]{font:400 15px/20px var(--font);color:var(--ink);width:5.5em;height:40px;padding:0 12px;border:0;border-radius:20px;background:var(--card);box-shadow:inset 0 0 0 1px var(--edge)}
input[type=checkbox]{width:18px;height:18px;margin:0;accent-color:var(--ink)}
.fld input[type=text]{flex:none;width:100%}
button{font:inherit;color:inherit;border:0;background:none;padding:0;cursor:pointer}
form button{height:40px;padding:0 18px;border-radius:20px;background:var(--card-3);font:500 14px/40px var(--font);color:var(--ink);box-shadow:inset 0 0 0 1px var(--edge);
white-space:nowrap;transition:transform var(--t-press) var(--ease),filter var(--t) var(--ease),box-shadow var(--t) var(--ease)}
form button.quiet{background:var(--card)}
form button:hover{filter:brightness(.98)}
form button:active{transform:scale(.97)}
.isl{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;align-items:center;gap:4px;padding:8px 8px max(8px,env(safe-area-inset-bottom));
border-radius:28px 28px 0 0;background:var(--glass);backdrop-filter:blur(24px) saturate(160%);-webkit-backdrop-filter:blur(24px) saturate(160%);
box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 -1px 0 rgba(11,15,18,.06),0 -12px 32px -16px rgba(11,15,18,.22)}
.tab{position:relative;flex:1;min-width:0;height:52px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;border-radius:22px;color:var(--ink-2);
font:500 11px/14px var(--font);text-decoration:none;transition:color var(--t) var(--ease),background var(--t) var(--ease),transform var(--t-press) var(--ease)}
.tab:hover{color:var(--ink)}
.tab:active{transform:scale(.96)}
.tab .i{width:22px;height:22px}
body:not(:has(:target)) .tab[href="#today"],body:has(#today:target) .tab[href="#today"],body:has(#lessons:target) .tab[href="#lessons"],
body:has(#ideas:target) .tab[href="#ideas"],body:has(#facts:target) .tab[href="#facts"],body:has(#agents:target) .tab[href="#agents"],
body:not(:has(:target)) .titem[href="#today"],body:has(#today:target) .titem[href="#today"],body:has(#lessons:target) .titem[href="#lessons"],
body:has(#ideas:target) .titem[href="#ideas"],body:has(#facts:target) .titem[href="#facts"],body:has(#agents:target) .titem[href="#agents"]{color:var(--ink);background:rgba(42,51,50,.09)}
.tisl{display:none}
@media (max-width:1023px){
.page{max-width:680px;padding:16px 20px 112px}
.top{margin:24px 0 32px}
.grid{grid-template-columns:minmax(0,1fr);gap:40px}
}
@media (max-width:560px){
.where{display:none}
.hello h1{font-size:40px;line-height:44px}
.hello p{font-size:15px;line-height:20px}
.top{margin:20px 0 24px}
.sec-h{margin-bottom:12px}
.pass{padding:24px}
.lesson{font-size:24px;line-height:30px;margin-top:16px}
.why{font-size:15px;line-height:22px;margin-top:8px}
.pair{padding:16px;gap:16px;margin-top:20px}
.stat b{font-size:26px;line-height:32px}
.stat b small{font-size:14px}
.stat span{font-size:13px;line-height:18px}
.act{gap:12px;margin-top:16px}
.trial-l{flex-basis:100%}
.act form.yes{flex:1}
.act form.yes button{width:100%}
.peek summary{padding:34px 20px 12px;font-size:14px}
.peek-in{padding:4px 20px 20px}
.peek.p1{width:calc(100% - 16px);margin-left:8px}
.peek.p2{width:calc(100% - 32px);margin-left:16px}
.peek.p3{width:calc(100% - 48px);margin-left:24px}
.peek.p4{width:calc(100% - 64px);margin-left:32px}
.glow{padding:24px 24px 20px}
.glow .lesson{font-size:22px;line-height:28px}
.glow .stat b{font-size:24px;line-height:32px}
.more{padding:0 16px 16px}
.wcard,.calm{padding:20px}
.agent-sec{padding:20px}
li.item{padding:14px 16px}
}
@media (max-width:360px){
.page{padding-left:16px;padding-right:16px}
.pass,.peek-in{padding-left:18px;padding-right:18px}
.pair{padding:14px;gap:12px}
.stat b,.glow .stat b{font-size:22px;line-height:28px}
.stat b small{margin:0 3px}
.glow{padding:20px 18px}
.agent-sec,.wcard,.calm{padding:18px 16px}
.pill>summary{grid-template-columns:36px minmax(0,1fr) auto 16px;gap:8px;padding:8px 12px 8px 10px}
.pill .ic{width:36px;height:36px}
.risk{padding:6px 10px}
}
@media (min-width:1024px){
.bar,.isl{display:none}
.page{max-width:1376px;padding:24px 56px 64px}
.grid{gap:40px}
[id]{scroll-margin-top:96px}
.tisl{position:sticky;top:16px;z-index:40;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;height:64px;padding:0 10px;border-radius:32px;
background:var(--glass);backdrop-filter:blur(24px) saturate(160%);-webkit-backdrop-filter:blur(24px) saturate(160%);
box-shadow:inset 0 1px 0 rgba(255,255,255,.9),inset 0 0 0 1px rgba(11,15,18,.05),0 18px 40px -22px rgba(11,15,18,.3)}
.tisl .left,.tisl .right{display:flex;align-items:center;gap:12px}
.tisl .right{justify-content:flex-end}
.tnav{display:flex;align-items:center;gap:4px}
.titem{display:inline-flex;align-items:center;gap:8px;height:44px;padding:0 16px;border-radius:22px;color:var(--ink-2);font:500 15px/1 var(--font);text-decoration:none;
transition:color var(--t) var(--ease),background var(--t) var(--ease),transform var(--t-press) var(--ease)}
.titem:hover{color:var(--ink)}
.titem:active{transform:scale(.97)}
.top{margin-top:40px}
}
@media (prefers-reduced-motion:reduce){
*{transition-duration:1ms !important}
.peek summary:hover,.peek summary:active,.glass-b:active,.pill>summary:active,form button:active,.tab:active,.titem:active{transform:none}
}
"""
CSP = ("default-src 'none'; style-src 'sha256-" + base64.b64encode(hashlib.sha256(CSS.encode("utf-8")).digest()).decode()
       + "'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


STALE_PLAN = "Not rolled back: the lessons changed after the plan was shown. Look at the plan again."
NO_EXAM = "A correction takes a short exam first, and this agent has no exam here yet, so nothing was added."


class Refused(Exception):
    """An answer the page cannot take; the message says why, and nothing changed."""


def person_line(lessons, text, stages, *, by, old, now=None, exam=None, hold_high=True, rated=None):
    """What a person's new line becomes. It follows the engine's rule for a person's own line
    (Lessons.add): it needs no yes, a person wrote it, so it starts a trial like any other
    lesson, or waits its turn when its stage has a trial; its risk is still checked and saved,
    and its origin is "person". hold_high: a high risk line waits for a yes on its card, the same
    as a correction (Lessons.add hold_high), so new words are never a way round that yes. Its
    source line names the lesson it came from: 'edited by <by> from lesson <id>: "<old line>"'.
    rated: the new line's risk, rated before the answer's transaction (Lessons.rate). Returns the new
    lesson's id."""
    source = f'{EDITED}{by} from lesson {old["id"]}: "{old["text"]}"'
    if exam is not None:  # Modify on the two tab page: the new words took the exam first (Morning.modify)
        return lessons.add(text, stages, source, yes_by=by, exam=exam, hold_high=hold_high, rated=rated, now=now)
    return lessons.add(text, stages, source, yes_by=by, skip_exam=True, hold_high=hold_high, rated=rated,
                       now=now)  # Edit runs no exam


def repo_plugs(root=ROOT):
    """Every agent's plug in the repo: <folder>/plug.json."""
    return [plug_mod.load(path) for path in sorted(Path(root).glob("*/plug.json"))]


class _OneTx:
    """The database as the page's Lessons see it. Inside one(), every transaction they open
    joins the answer's one transaction, begun with the write lock, so an answer reads and
    changes the lessons in one go: all of it is saved, or none of it."""

    def __init__(self, db):
        self.db = db
        self._here = threading.local()

    def script(self, sql):
        self.db.script(sql)

    @contextmanager
    def tx(self):
        c = getattr(self._here, "c", None)
        if c is not None:
            yield c
            return
        with self.db.tx() as c:
            yield c

    @contextmanager
    def one(self):
        with self.db.tx() as c:
            if not c.in_transaction:
                c.execute("BEGIN IMMEDIATE")
            self._here.c = c
            try:
                yield c
            finally:
                self._here.c = None


class Morning:
    """The page's data and its answers, for every agent in one database. plugs: the agents
    whose lessons the page may change. reports: the folder of the saved night reports. Each
    answer is one transaction: an answer that fails part way leaves nothing changed."""

    def __init__(self, db, plugs, *, reports=None, by=BY, judge=risk_mod.no_judge, db_file=None, exams=None,
                 modes_state=None, built=(), db_path=None):
        """exams: {agent: examiner(text, stages) -> engine.exam.Result}, the exam a person's idea takes
        (idea_exam); kept off the page's Lessons, so no exam ever runs inside an answer's transaction.
        modes_state: the assistant's folder a mode card's answer goes to (assistant/newmode.py).
        built: the names of the plugs that are agents Quick start built (kit/turn.py built), whose
        turns read the pause switch. db_path: the database's path on the live page (live_morning), where
        add_built finds an agent built while the page runs; None on the sample days."""
        self.db = db
        self.db_path = None if db_path is None else str(db_path)
        self.judge = judge
        self.built = frozenset(built or ())
        self.modes_state = None if modes_state is None else Path(modes_state)
        self.exams = dict(exams or {})
        self.page = _OneTx(db)
        self.by = by
        self.db_file = db_file  # named in the rollback command when it is not the default database
        self.reports = None if reports is None else Path(reports)
        self.plugs = {p.agent: p for p in plugs}
        self.db.script(lessons_mod.SCHEMA)
        self.db.script(switches_mod.SCHEMA)
        exam_mod.ensure(self.db)  # the table, and the gate count columns on an older database
        trial_mod.ready(self.db)
        self.lessons = {a: Lessons(self.page, p, judge=judge) for a, p in self.plugs.items()}
        # made here, not in an answer: making Lessons, Log or the marks table runs a script, which commits
        self.trials = {a: trial_mod.Trials(self.page, p, lessons=self.lessons[a]) for a, p in self.plugs.items()}
        self.facts = facts_mod.Facts(self.page)  # the fact cards' answers table, made here for the same reason

    def add_built(self):
        """Wire each agent Quick start built since the page started into the running page, as
        live_morning and main do at start: its plug (with_built), its Lessons and Trials, its name for
        the pause switch and its exam (page_exams), so a correction, Pull and the exam work with no
        restart. A built agent named like an agent on the page or a repo agent is left out. Run outside
        any answer's transaction (making Lessons commits). Returns the names added; none with no db_path."""
        if self.db_path is None:
            return []
        have = list(self.plugs.values()) + [p for p in repo_plugs() if p.agent not in self.plugs]
        got, _ = with_built(have, self.db_path)
        new = got[len(have):]
        if not new:
            return []
        lessons = {p.agent: Lessons(self.page, p, judge=self.judge) for p in new}
        trials = {p.agent: trial_mod.Trials(self.page, p, lessons=lessons[p.agent]) for p in new}
        # new dicts, not changed in place: a view reading the old ones never sees one half wired
        self.plugs = {**self.plugs, **{p.agent: p for p in new}}
        self.lessons = {**self.lessons, **lessons}
        self.trials = {**self.trials, **trials}
        self.built = self.built | {p.agent for p in new}
        self.exams = {**self.exams, **page_exams(new, self, self.db_path)}
        return [p.agent for p in new]

    # ---- answers -------------------------------------------------------------------------

    def stop(self, lesson_id, why, now=None):
        """Pull a live lesson, with a one line why."""
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            why = _one_line(why, "why")
            if les["state"] not in (KEPT, TRYING):
                raise Refused(f"Lesson {les['id']} is not live, so there is nothing to stop.")
            if not lessons.pull(les["id"], f"stopped by {self.by}: {why}", now=now):
                raise Refused(f"Lesson {les['id']} was pulled already.")
        return f"Lesson {les['id']} stopped. It is never given again."

    def modify(self, lesson_id, line, note="", now=None):
        """Modify on a Today card (the two tab page): the card's new words, with the optional note
        added after them, go the Edit way (person_line, the old lesson pulled) but take the idea
        exam first (idea_exam, outside the transaction), so a fail waits for a yes on Today again. A
        high risk line waits for a yes on Today too: Modify is never the yes (person_line hold_high).
        The cheap refusals (too long, the same words, a card that cannot be edited) come before the exam."""
        text = _one_line(line, "the new line")
        extra = _one_line(note, "the note", required=False)
        text = f"{text} {extra}" if extra else text
        if len(text) > MAX_LEN:
            raise Refused(f"The new line and the note: at most {MAX_LEN} characters together.")
        les, lessons = self._mine(lesson_id)
        self._edit_checked(les, lessons, text, now)  # a refused line takes no exam; edit checks again
        result = self._exam_for(lessons, text, les["stages"])
        rated = lessons.rate(text)  # the judge, outside the transaction (edit)
        return self.edit(lesson_id, text, now=now, exam=result, rated=rated)

    def correct(self, agent, line, now=None):
        """A correction or an idea the user sends on an agent's page: a hotfix (DECISIONS 56,
        Lessons.correct). It takes the short exam first, the one the page already runs (outside the
        transaction); once it passes it starts at once on half the chats, whatever the level, and never
        waits behind a lesson on trial. A high risk one, or one the exam holds, waits for a yes on Today
        (engine.lessons WANTS_YES). An agent with no exam here is refused: a correction never starts
        untested. The night's Reflection reads it like any idea; its source is Lessons.HOTFIX_SOURCE."""
        lessons, text, stage = self._idea_checked(agent, line, plug_mod.ALL)  # a refused line takes no exam
        result = self._correction_exam(lessons, text)
        if result is None:
            raise Refused(NO_EXAM)
        rated = lessons.rate(text)  # the judge is a model call: never inside the write lock
        with self.page.one():
            lessons, text, stage = self._idea_checked(agent, line, plug_mod.ALL)  # again: the lessons may have moved
            try:
                new_id = lessons.correct(text, [stage], yes_by=self.by, exam=result, now=now, rated=rated)
            except ValueError as e:
                raise Refused(f"The correction was refused: {e}.") from None
            state = lessons.get(new_id)["state"]
            held = self._card(lessons.get(new_id), lessons, now)
        from arena import gate  # the past wins the Arena rerun skipped, said in one line
        note = gate.skipped_note(result)
        note = f" {note}" if note else ""
        if state == TRYING:
            return (f"Your correction is lesson {new_id}. It passed the exam and runs now as a hotfix in half the chats. "
                    f"Reflection checks it tonight.{note}")
        if not result.passed:
            return f"Your correction is lesson {new_id}. It waits for your yes on Today: it {result.line()}.{note}"
        if held:
            return (f"Your correction is lesson {new_id}. It passed the exam but is high risk, so it waits for your yes "
                    f"on Today.{note}")
        return f"Your correction is lesson {new_id}. It waits its turn.{note}"

    def _correction_exam(self, lessons, text):
        """The short exam a correction takes, run outside any transaction: always, when the page has an
        examiner for the agent (a hotfix takes it whatever takes_exam says); None with no examiner. An
        examiner that raises fails the correction, so it waits for a yes (fail closed)."""
        examiner = self.exams.get(lessons.agent)
        if examiner is None:
            return None
        try:
            return examiner(text, lessons.plug.stage_tags([plug_mod.ALL]))
        except Exception as e:
            return exam_mod.could_not_run(e)

    def paused(self, agent):
        """True while the agent's pause switch is on (kit/switch.py). Reads only: a database with no
        switch table yet is not paused, and a page view never makes the table."""
        with self.db.tx() as c:
            if not _has_table(c, "agent_switch"):
                return False
        return switch_mod.is_paused(agent, db=self.db)

    def pausable(self, agent):
        """Does Pull stop this agent? It has a plug here and its code reads the switch (switch.honoured:
        a repo agent in HONOURED, or an agent Quick start built, which runs through kit/turn.py)."""
        return agent in self.lessons and switch_mod.honoured(agent, self.built)

    def pause(self, agent, now=None):
        """Pull on an agent's page: the real pause switch (DECISIONS 54, kit/switch.py), signed by the
        page's person. A paused agent sends nothing until Resume; messages are still saved."""
        self._switchable(agent)
        if self.paused(agent):
            return "It is paused already. Resume starts it again."
        switch_mod.pause(agent, db=self.db, now=now, by=self.by)
        return "Paused. It sends nothing until you press Resume; messages that come in are still saved."

    def resume(self, agent, now=None):
        """Resume on a paused agent's page: the switch off, signed by the page's person; quiet counts
        from now (sales/quiet.py)."""
        self._switchable(agent)
        if not self.paused(agent):
            return "It is running already."
        switch_mod.resume(agent, db=self.db, now=now, by=self.by)
        return "Resumed. It answers the next message."

    def _switchable(self, agent):
        if not isinstance(agent, str) or agent not in self.lessons:
            raise Refused("No plug for that agent in this repo, so nothing is changed here.")
        if not self.pausable(agent):
            raise Refused("Pull is not built for this agent yet, so nothing is changed.")

    def rollback_plan(self, agent, now=None):
        """The latest night snapshot of an agent with a plug and what a rollback to it would do now:
        (snapshot, steps, code), or None with no snapshot (reflection/snapshots.py)."""
        self._plugged(agent)
        snap = snapshots.latest(self.db, agent)
        if snap is None:
            return None
        now = time.time() if now is None else float(now)
        with self.db.tx() as c:
            steps = snapshots.plan(c, agent, snap, now)
        return snap, steps, snapshots.plan_code(snap, steps)

    def roll_back(self, agent, code, now=None):
        """Roll back to the latest night snapshot, the plan the page showed (code), through
        snapshots.rollback; refused in plain words when the plan changed meanwhile."""
        lessons = self._plugged(agent)
        snap = snapshots.latest(self.db, agent)
        if snap is None:
            raise Refused(f"No night snapshot of {agent} yet, so there is nothing to roll back to.")
        night = _date(snap["at"])
        try:
            steps, row = snapshots.rollback(self.db, lessons, snap, self.by, now, code=str(code or ""))
        except snapshots.Refused as e:
            stale = str(e).startswith("the plan changed")  # the CLI's words; the page says it plainly
            raise Refused(STALE_PLAN if stale else f"Not rolled back: {e}.") from None
        if row is None:
            return f"Nothing to roll back: the lessons given now were all given the night of {night}."
        return f"Rolled back to the night of {night}."

    def edit(self, lesson_id, line, now=None, exam=None, rated=None):
        """Add the new line (person_line) and pull the old lesson, each naming the other, in one
        transaction: when the pull fails, the new line is not kept either. The new line waits
        its turn behind the old lesson's trial, so once the old one is pulled the turns whose
        stages are free start (Lessons.start_turns). A high risk new line waits for a yes on its card
        (person_line hold_high). The new line's risk is rated before the transaction (rated, from Modify, or
        here after the cheap refusals), so the judge, a model call, never holds the write lock."""
        if rated is None:
            les, lessons = self._mine(lesson_id)
            text = _one_line(line, "the new line")
            self._edit_checked(les, lessons, text, now)  # a refused line costs no judge call
            rated = lessons.rate(text)
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            text = _one_line(line, "the new line")
            self._edit_checked(les, lessons, text, now)
            try:
                new_id = person_line(lessons, text, les["stages"], by=self.by, old=les, now=now, exam=exam,
                                     rated=rated)
            except ValueError as e:
                raise Refused(f"The new line was refused: {e}.") from None
            if not lessons.pull(les["id"], f"{EDITED}{self.by} into lesson {new_id}", now=now):
                raise Refused(f"Lesson {les['id']} changed meanwhile; nothing done.")
            lessons.start_turns(now)
            new = lessons.get(new_id)
            held = new["state"] == WAITING and new["yes_at"] is None and lessons.waits_for(new_id, now) is None
        where = "It is on trial." if new["state"] == TRYING else "It waits its turn."
        if exam is not None and not exam.passed and new["state"] == WAITING:
            where = f"It waits for a yes: it {exam.line()}."
        elif held:
            where = "It is high risk, so it waits for your yes on its card."
        return f"Lesson {les['id']} edited: the new line is lesson {new_id}. {where}"

    def _edit_checked(self, les, lessons, text, now=None):
        """Refused when a lesson is not edited into these words: not live and no card, a card that
        replaces or is named on another card, or the same words."""
        if not (les["state"] in (KEPT, TRYING) or self._card(les, lessons, now)):
            raise Refused(f"Lesson {les['id']} is neither live nor waiting for a yes, so it is not edited here.")
        clash = lessons.clashes(les["id"])["replaces"] if les["state"] == WAITING else []
        if clash:  # an edited line would drop the clash and stand next to the line it goes against
            raise Refused(f"Lesson {les['id']} asks to replace lesson {', '.join(str(i) for i in clash)}, so it "
                          "is not edited here. Answer Yes or No on its card, then edit the line that stays.")
        named = [i for i in lessons.clashes(les["id"])["replaced_by"]
                 if (lessons.get(i) or {}).get("state") == WAITING] if les["state"] != WAITING else []
        if named:  # the edited line would drop the card's clash, and a later yes would pull nothing
            raise Refused(f"Lesson {les['id']} is named on the card of lesson {', '.join(str(i) for i in named)}, "
                          "so it is not edited here. Answer that card first.")
        if text == les["text"]:
            raise Refused("The new line is the same as the old one; nothing changed.")

    def longer(self, lesson_id, days, now=None):
        """Keep an unclear lesson on trial longer: given again in the same share of cases until
        `days` whole days from now (Trials.longer). Refused when it is not unclear, when the days
        are not a whole number from 1 to LONGER_DAYS, or while another lesson is on trial on its
        stages."""
        days = _days(days)
        with self.page.one():
            les, _ = self._mine(lesson_id)
            trials = self.trials[les["agent"]]
            info = trials.unclear(les["id"], now)
            if info is None:
                raise Refused(f"Lesson {les['id']} does not wait after an unclear trial.")
            if info["ahead"]:
                first = self.lessons[les["agent"]].get(info["ahead"][0])
                names = ", ".join(f"lesson {i}" for i in info["ahead"])
                verb = "is" if len(info["ahead"]) == 1 else "are"
                raise Refused(f"Lesson {les['id']} is not kept on trial longer now: {names} {verb} on trial on its stages "
                              f"until {_when(first['ends_at'])}, and one trial runs on a stage at a time.")
            ends_at = trials.longer(les["id"], days, self.by, now=now)
            if ends_at is None:
                raise Refused(f"Lesson {les['id']} changed meanwhile; nothing done.")
        return f"Lesson {les['id']} is on trial again until {_when(ends_at)}; the numbers so far still count."

    def drop(self, lesson_id, now=None):
        """Drop an unclear lesson: pulled, its why "unclear, dropped by <who>" (Trials.drop)."""
        with self.page.one():
            les, _ = self._mine(lesson_id)
            trials = self.trials[les["agent"]]
            if trials.unclear(les["id"], now) is None:
                raise Refused(f"Lesson {les['id']} does not wait after an unclear trial.")
            if not trials.drop(les["id"], self.by, now=now):
                raise Refused(f"Lesson {les['id']} changed meanwhile; nothing done.")
        return f"Lesson {les['id']} dropped. It is never given again."

    def yes(self, lesson_id, shown="", now=None):
        """A yes on a card: on trial, or waiting its turn; a "replace it?" card pulls the lines it names.
        shown: the ids of the lines the card named when the page was drawn ("3,5"; "" for none).
        When the card names other lines now, nothing is done. The answer names only the lines
        this yes pulled."""
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            if not self._card(les, lessons, now):
                raise Refused(f"Lesson {les['id']} does not wait for a yes.")
            replaces = lessons.clashes(les["id"])["replaces"]
            if _ids(shown) != replaces:
                raise Refused(f"Lesson {les['id']}'s card changed after the page was drawn, so nothing was done. "
                              "Look at it again.")
            live = [i for i in replaces if (lessons.get(i) or {"state": PULLED})["state"] != PULLED]
            moved = (lessons.replace(les["id"], self.by, now=now) if replaces
                     else lessons.approve(les["id"], self.by, now=now))
            if not moved:
                raise Refused(f"Lesson {les['id']} changed meanwhile; nothing done.")
            state = lessons.get(les["id"])["state"]
        where = "It is on trial." if state == TRYING else "It waits its turn."
        pulled = f" Pulled: lesson {', '.join(str(i) for i in live)}." if live else ""
        return f"Lesson {les['id']}: yes. {where}{pulled}"

    def no(self, lesson_id, why="", now=None):
        """A no on a card: pulled, never given."""
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            why = _one_line(why, "why", required=False)
            if not self._card(les, lessons, now):
                raise Refused(f"Lesson {les['id']} does not wait for a yes.")
            if not lessons.pull(les["id"], f"no from {self.by}" + (f": {why}" if why else ""), now=now):
                raise Refused(f"Lesson {les['id']} was pulled already.")
        return f"Lesson {les['id']}: no. It is pulled."

    def bring_back(self, lesson_id, now=None):
        """Bring back a pulled lesson: a new lesson with its line, on trial or waiting its turn."""
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            if les["state"] != PULLED:
                raise Refused(f"Lesson {les['id']} is not pulled, so there is nothing to bring back.")
            try:
                new_id = lessons.bring_back(les["id"], self.by, now=now)
            except ValueError as e:
                raise Refused(f"Lesson {les['id']} was not brought back: {e}.") from None
            state = lessons.get(new_id)["state"]
        where = "It is on trial." if state == TRYING else "It waits its turn."
        return f"Lesson {les['id']} is back as lesson {new_id}; lesson {les['id']} stays pulled. {where}"

    def idea(self, agent, line, stage, now=None):
        """A person's idea, typed on the page: a lesson with no past cases behind it, for one
        agent with a plug, on one of its stages or "all". It goes the way of any person's own
        line (Lessons.add): kind idea, origin person, signed by the page's person, no yes
        needed, so it starts a trial at the share and days of the level that applies, the same
        as an agent's idea, or waits its turn. Refused for an agent with no plug, a line that
        is empty, too long or more than one line, a stage the plug does not have, a line with
        the same words as a live or waiting lesson, and a pulled line (Bring back brings that
        one back). It takes the exam first when the page has one for the agent (idea_exam)."""
        lessons, text, stage = self._idea_checked(agent, line, stage)  # a refused idea takes no exam
        result = self.idea_exam(lessons, text, stage)  # before the transaction: no write lock held
        rated = lessons.rate(text)  # the judge too
        with self.page.one():
            lessons, text, stage = self._idea_checked(agent, line, stage)  # again: the lessons may have moved
            try:
                new_id = lessons.add(text, [stage], f"an idea {self.by} typed on the morning page", yes_by=self.by,
                                     exam=result, now=now, rated=rated)
            except ValueError as e:
                raise Refused(f"The idea was refused: {e}.") from None
            row = lessons.get(new_id)
            state = row["state"]
        from arena import gate  # the past wins the Arena rerun skipped, said in one line
        note = "" if result is None else gate.skipped_note(result)
        note = f" {note}" if note else ""
        if result is not None and not result.passed and state == WAITING:
            return (f"Your idea is lesson {new_id}. It waits for a yes: it {result.line()}. Yes on its card starts it "
                    f"anyway.{note}")
        where = "It is on trial." if state == TRYING else "It waits its turn."
        return f"Your idea is lesson {new_id}. {where}{note}"

    def _idea_checked(self, agent, line, stage):
        """An idea's agent, line and stage, or Refused: no plug, a bad line or stage, a known or pulled line."""
        lessons = self.lessons.get(agent) if isinstance(agent, str) else None
        if lessons is None:
            raise Refused(f"No plug for {agent} in this repo, so no idea is added for it.")
        text = _one_line(line, "the idea")
        stage = stage.strip() if isinstance(stage, str) else ""
        stages = lessons.plug.stages
        if stage != plug_mod.ALL and stage not in stages:
            raise Refused(f"Stage: one of {', '.join(stages)} or {plug_mod.ALL}, please.")
        les, why = study_mod.line_known(lessons.mine(), text)
        if why == study_mod.KNOWN:
            raise Refused(f"That idea is lesson {les['id']} already; nothing added.")
        if why == study_mod.PULLED_BEFORE:
            raise Refused(f"That line was lesson {les['id']}, now pulled. Use Bring back on lesson {les['id']}.")
        return lessons, text, stage

    def idea_exam(self, lessons, text, stage):
        """The exam a person's idea takes, run outside any transaction: None when the page has no
        examiner for the agent or the rule says a person's line takes none (engine.lessons.takes_exam).
        An examiner that raises fails the idea, so it waits for a yes (fail closed)."""
        return self._exam_for(lessons, text, [stage])

    def _exam_for(self, lessons, text, stages):
        """idea_exam on a list of stages (Modify keeps the lesson's own stages)."""
        examiner = self.exams.get(lessons.agent)
        if examiner is None or not lessons_mod.takes_exam(lessons_mod.PERSON):
            return None
        try:
            return examiner(text, lessons.plug.stage_tags(stages))
        except Exception as e:
            return exam_mod.could_not_run(e)

    def _mine(self, lesson_id):
        try:
            lesson_id = int(lesson_id)
        except (TypeError, ValueError):
            raise Refused("No such lesson.") from None
        with self.page.tx() as c:
            row = c.execute("SELECT agent FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None:
            raise Refused(f"No lesson {lesson_id}.")
        lessons = self.lessons.get(row["agent"])
        if lessons is None:
            raise Refused(f"No plug for {row['agent']} in this repo, so its lessons are not changed here.")
        return lessons.get(lesson_id), lessons

    @staticmethod
    def _card(les, lessons, now=None):
        """Is it held for a person's yes (engine.lessons WANTS_YES: no yes yet, a person's line its exam
        held, a high risk correction)? Not when it waits its turn."""
        return lessons.wants_yes(les["id"]) and lessons.waits_for(les["id"], now) is None

    # ---- switches and fact cards (calls 16, 20 and 10) -----------------------------------

    def set_level(self, agent, level, now=None):
        """Flip an agent's trial level switch (Switches.set_level), for trials that start from
        now; a trial already running keeps its level. Refused for an unknown level, or the
        level it reads already."""
        lessons = self._plugged(agent)
        level = _level(level)
        with self.page.one():
            if lessons.switches.level()["level"] == level:
                raise Refused(f"The trial level of {agent} is {level} already; nothing changed.")
            got = lessons.switches.set_level(level, self.by, now=now)
        return (f"The trial level of {agent} is {level} now: {_share(got['share'])} for {got['days']} days, for "
                "trials that start from now. A trial already running keeps the level it started with.")

    def set_accept(self, agent, on, auto="", days="", now=None):
        """Turn an agent's Accept high risk on or off (Switches.set_accept_high). on: "on" or
        "off". auto: "1" when the check mark under it is ticked, and then days, 1 to
        switches.MOST_DAYS, after which it reads as off by itself. Days with no tick are refused,
        so a person who typed days but missed the tick is asked, not left with a switch that
        has no end. Turning it off while it is off is refused."""
        lessons = self._plugged(agent)
        if on not in ("on", "off"):
            raise Refused("Accept high risk: on or off, please.")
        n = None
        if on == "on" and auto == "1":
            n = _switch_days(days)
        elif on == "on" and (days or "").strip():
            raise Refused("Tick the check mark to turn it off by itself after those days, or leave the days empty.")
        with self.page.one():
            sw = lessons.switches
            if on == "off":
                if not sw.accept_high(now)["on"]:
                    raise Refused(f"Accept high risk is off already for {agent}; nothing changed.")
                sw.set_accept_high(False, self.by, now=now)
                return f"Accept high risk is off for {agent}. A high risk lesson waits for a person's yes again."
            got = sw.set_accept_high(True, self.by, days=n, now=now)
        ends = (f"until {_when(got['until'])}, then it turns off by itself" if got["until"] is not None
                else "until a person turns it off")
        return f"Accept high risk is on for {agent}, {ends}."

    def lesson_level(self, lesson_id, level, now=None):
        """Pick fast or careful for one lesson that waits for a yes or waits its turn
        (Switches.set_lesson_level); it wins over the switch when the lesson's trial starts.
        Refused once its trial started or it was pulled: a trial keeps its level; and refused
        when the share and days came with its yes."""
        level = _level(level)
        with self.page.one():
            les, lessons = self._mine(lesson_id)
            if (lessons.trial(les["id"]) or {}).get("level") == lessons_mod.GIVEN:
                raise Refused(f"Lesson {les['id']} took its share and days with its yes, so its level is not "
                              "changed.")
            if not lessons.switches.set_lesson_level(les["id"], level, self.by, now=now):
                raise Refused(f"Lesson {les['id']} does not wait any more, so its level is not changed: a trial "
                              "keeps the level it started with.")
            lv = self.plugs[les["agent"]].level(level)
        return (f"Lesson {les['id']} takes the {level} level when its trial starts: {_share(lv.share)} for "
                f"{lv.days} days.")

    def keep_fact(self, agent, key, shown, now=None):
        """Keep a fact card: saved with who and when, and shown under Kept facts."""
        return self._fact(agent, key, shown, facts_mod.KEEP, now)

    def dismiss_fact(self, agent, key, shown, now=None):
        """Dismiss a fact card: saved with who and when, and not shown again this week."""
        return self._fact(agent, key, shown, facts_mod.DISMISS, now)

    def _fact(self, agent, key, shown, answer, now):
        """Save a Keep or Dismiss for the fact card the person saw. Refused when there is no
        such card now (answered already, or too few results now), or when its numbers changed
        after the page was drawn (shown: the card's digest in its form)."""
        self._plugged(agent)
        with self.page.one():
            card = next((c for c in self.facts.cards(agent, now) if c["key"] == key), None)
            if card is None:
                raise Refused("That fact card is not there now: it was answered already, or its results fell under "
                              "the minimum. Look at the page again.")
            if not hmac.compare_digest(card["shown"].encode("utf-8"), (shown or "").encode("utf-8")):
                raise Refused("The fact changed after the page was drawn, so nothing was saved. Look at it again.")
            self.facts.answer(card, answer, self.by, now=now)
        if answer == facts_mod.KEEP:
            return f"Kept: {card['fact']} It is saved with your name under Kept facts; no agent acts on it."
        return f"Dismissed: {card['fact']}"

    def answer_mode(self, agent, card, choice, name="", now=None):
        """The user's Yes, Rename or Drop on a new mode card. card: the card's file name as the page
        drew it; it must name one of the open cards next to the database (newmode.open_cards), so a
        path from the form never reaches a file."""
        from assistant import newmode
        self._plugged(agent)
        if agent != newmode.AGENT or self.reports is None or self.modes_state is None:
            raise Refused("No mode cards for that agent here, so nothing is changed.")
        path = {p.name: p for p in newmode.open_cards(self.reports)}.get(card)
        if path is None:
            raise Refused("That mode card is not there now: it was answered already. Look at the page again.")
        if choice not in newmode.CHOICES:
            raise Refused("A mode card's answer is Yes, Rename or Drop.")
        now_modes = newmode.answer_card(path, self.modes_state, choice, name=name if choice == "rename" else None,
                                        by=self.by)
        if choice == "drop":
            return "Dropped. That mode is not proposed again."
        return f'Added the mode "{now_modes["added"][-1]["name"]}" to the assistant\'s modes.'

    def _plugged(self, agent):
        lessons = self.lessons.get(agent) if isinstance(agent, str) else None
        if lessons is None:
            raise Refused("No plug for that agent in this repo, so nothing is changed here.")
        return lessons

    def _live(self):
        """The agents with a plug here that work on real chats or cases in this database: a chat on a
        real channel in the chats store (the Sales agent's, kit/chats.py), or a log row that is not an
        imported history row (reflection/importer.py). The Arena plays on a copy of the database, so an
        agent with only Arena practice is not live. There is no live switch in the code yet."""
        out = set()
        with self.db.tx() as c:
            if _has_table(c, "trace"):
                out |= {r["agent"] for r in c.execute(
                    "SELECT DISTINCT agent FROM trace WHERE (CASE WHEN json_valid(detail) THEN "
                    "json_extract(detail, '$.history') END) IS NOT 1")}
            if _has_table(c, "chats") and c.execute(
                    f"SELECT 1 FROM chats WHERE {_REAL_CHANNEL} LIMIT 1").fetchone():
                out.add(SALES.agent)
        return out & set(self.plugs)

    def answered_since(self, agent, since):
        """How many real chats (never an imported history chat) the agent answered at or after since,
        from the chats store; 0 for an agent the chats store is not for, or with no chats store."""
        if agent != SALES.agent:
            return 0
        with self.db.tx() as c:
            if not (_has_table(c, "chats") and _has_table(c, "steps")):
                return 0
            return c.execute(f"SELECT COUNT(DISTINCT s.chat_id) FROM steps s JOIN chats ON chats.id = s.chat_id "
                             f"WHERE s.role = 'assistant' AND s.at >= ? AND {_REAL_CHANNEL}", (float(since),)).fetchone()[0]

    def _working(self, c):
        """The agents with a plug here that have worked in this database (a log row, a switch
        flip or a fact answer), so their switches show before their first lesson."""
        out = set()
        for table in ("trace", "trial_switches", "fact_answers"):
            if c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                out |= {r["agent"] for r in c.execute(f"SELECT DISTINCT agent FROM {table}")}
        return out & set(self.plugs)

    def _lesson_level(self, item, k):
        """The level a waiting lesson's trial will take when it starts: its own, picked by a
        person, else the switch's. None for a lesson that does not wait or has no plug here;
        {"given": True} when its share and days were given with its yes."""
        lessons = self.lessons.get(item["agent"])
        if lessons is None or item["state"] != WAITING:
            return None
        if (k.trials.get(item["id"]) or {}).get("level") == lessons_mod.GIVEN:
            return {"given": True}
        own = lessons.switches.lesson_level(item["id"])
        name = own["level"] if own else lessons.switches.level()["level"]
        lv = self.plugs[item["agent"]].level(name)
        return {"given": False, "level": name, "share": lv.share, "days": lv.days, "own": own is not None,
                "by": own["by"] if own else None, "at": own["at"] if own else None}

    def switch_view(self, agent, now):
        """An agent's switches as the page shows them: the level with who and when, the plug's two
        levels, Accept high risk at `now` with who, when and its end, the locks that hold
        whatever they say, and every flip, newest first."""
        sw, plug = self.lessons[agent].switches, self.plugs[agent]
        return {"level": sw.level(), "accept": sw.accept_high(now), "locks": locks(agent),
                "levels": {n: {"share": plug.level(n).share, "days": plug.level(n).days} for n in plug_mod.LEVEL_NAMES},
                "flips": sw.history()[::-1]}

    def fact_view(self, now):
        """The fact cards of every agent with a plug here and a fact (reflection/facts.py), and the
        facts that stand kept."""
        agents = [a for a in sorted(self.plugs) if a in facts_mod.MAKERS]
        return {"facts": [c for a in agents for c in self.facts.cards(a, now)],
                "kept_facts": [dict(r, agent=a) for a in agents for r in self.facts.kept(a)], "fact_agents": agents}

    # ---- the page's data -----------------------------------------------------------------

    def view(self, now=None):
        """Everything the page shows, as plain data."""
        now = time.time() if now is None else float(now)
        with self.db.tx() as c:
            rows = [_lesson(r) for r in c.execute("SELECT * FROM lessons ORDER BY id")]
            trials = {r["lesson_id"]: dict(r) for r in c.execute("SELECT * FROM trials")}
            accepts = {r["id"]: r["by"] for r in c.execute("SELECT id, by FROM trial_switches "
                                                           "WHERE kind = 'accept_high'")}
            for t in trials.values():  # who switched on the Accept high risk row a trial went under
                t["accept_by"] = accepts.get(t.get("accept_high_id"))
            marks = [_mark(r) for r in c.execute("SELECT * FROM trial_marks ORDER BY id")]
            clashes = [dict(r) for r in c.execute("SELECT lesson_id, live_id FROM lesson_clashes "
                                                  "ORDER BY lesson_id, live_id")]
            backs = {r["lesson_id"]: r["from_id"] for r in c.execute("SELECT lesson_id, from_id FROM lesson_returns")}
            exams = {r["lesson_id"]: dict(r) for r in c.execute("SELECT * FROM lesson_exams")}
            wanting = lessons_mod.wants_yes_ids(c)
            working = self._working(c)
        k = _Ctx(now, rows, trials, marks, clashes, self.read_reports(), backs=backs, exams=exams)
        k.wanting = wanting  # the lessons held for a yes, as approve reads them
        arena, bad = self.read_arena()
        modes, bad_modes = self.read_mode_cards()
        k.problems = list(k.problems) + bad + bad_modes
        items = {les["id"]: self._item(les, k) for les in rows}
        for i in items.values():
            i["level"] = self._lesson_level(i, k)
        agents = []
        for agent in sorted({les["agent"] for les in rows} | {m["agent"] for m in marks} | working | set(arena)
                            | set(modes)):
            mine = [items[les["id"]] for les in rows if les["agent"] == agent]
            agents.append({
                "agent": agent, "buttons": agent in self.lessons, "night": k.newest.get(agent),
                "arena": arena.get(agent), "mode_card": modes.get(agent),
                "snapshot": self._snapshot(agent),
                "new": [i for i in mine if i["added_at"] >= now - DAY],
                "live": [i for i in mine if i["state"] in (KEPT, TRYING)],
                "waiting": [i for i in mine if i["state"] == WAITING],
                "trials": [t for t in (_trial(i, k) for i in reversed(mine)) if t is not None],
                "pulled": sorted((i for i in mine if i["state"] == PULLED), key=lambda i: -(i["pulled_at"] or 0)),
            })
        pool = [i for i in items.values() if i["card"] and i["agent"] in self.lessons]
        pool.sort(key=_rank)
        unclear = [self._unclear(items[les["id"]], k) for les in rows if les["agent"] in self.trials
                   and items[les["id"]]["status"] == "unclear"]
        for a in agents:
            a["switches"] = self.switch_view(a["agent"], now) if a["buttons"] else None
        view = {"at": now, "agents": agents, "cards": pool[:CARDS], "more": max(0, len(pool) - CARDS),
                "unclear": [u for u in unclear if u is not None], "problems": k.problems,
                "ideas": self._ideas(rows, items)}
        view.update(self.fact_view(now))
        return view

    def _ideas(self, rows, items):
        """The ideas part of the page: each open idea (waiting or on trial) of an agent with a
        plug, newest first, and the agents a person may type an idea for, with their stages."""
        open_ = [items[les["id"]] for les in reversed(rows) if items[les["id"]]["idea"] is not None
                 and les["state"] in (WAITING, TRYING)]
        return {"open": open_, "agents": [{"agent": a, "stages": list(self.plugs[a].stages)} for a in sorted(self.plugs)]}

    def _unclear(self, item, k):
        """An unclear lesson's card: the numbers its trial ended with (the unclear mark's
        detail), whose idea it was, the lessons on trial on its stages now, and the trial's days
        as the Keep longer field's start. None when it no longer waits."""
        info = self.trials[item["agent"]].unclear(item["id"], k.now)
        if info is None:
            return None
        d = _dict(info["mark"]["detail"])
        sides = {}
        for side in ("with", "without"):
            s = _dict(d.get(side))
            sides[side] = {n: _num(s.get(n)) for n in ("settled", "good", "sources")}
        days = _num((k.trials.get(item["id"]) or {}).get("days"))
        return dict(item, ended=info["ends_at"], mark_id=info["mark"]["id"], sides=sides, chance=_num(d.get("chance")),
                    said=str(_dict(d.get("person")).get("said") or ""), good=self.plugs[item["agent"]].decides.good,
                    ahead=info["ahead"], days=None if days is None else min(max(round(days), 1), trial_mod.LONGER_DAYS))

    def _snapshot(self, agent):
        """The agent's latest night snapshot as one line's data, or None; the rollback command
        only for an agent with a plug in the repo."""
        snap = snapshots.latest(self.db, agent)
        if snap is None:
            return None
        return {"night": snap["night"], "lessons": len(snap["lessons"]), "live": sum(e["live"] for e in snap["lessons"]),
                "hash": snap["hash"][:snapshots.SHORT],
                "command": snapshots.command(agent, snap["night"], self.db_file) if agent in self.lessons else None}

    def _item(self, les, k):
        """One lesson as the page shows it: its state in words, why, and its links."""
        lessons = self.lessons.get(les["agent"])
        t = k.trials.get(les["id"])
        queued = t is not None and t["started_at"] is None and les["state"] == WAITING
        ahead = (lessons.waits_for(les["id"], k.now) if lessons is not None else None) if queued else None
        held = _held(les, k)
        card = les["id"] in k.wanting and not queued
        report = k.cards.get(les["id"]) or {}
        item = dict(les, card=card, exam=held, queued=queued, ahead=ahead or [], numbers=_numbers(report),
                    gate=exam_mod.effect_of(k.exams.get(les["id"])),  # fixed and broke in the gate, or None
                    exam_result=_exam_result(k.exams.get(les["id"])),
                    accept_high=None if t is None else t["accept_by"],
                    replaces=[_short(k.by_id.get(i), i) for i in k.replaces.get(les["id"], [])],
                    cases=list((k.links.get(les["id"]) or {}).get("cases") or []))
        item["status"], item["why"] = _status(les, item, k, report)
        verdict = next((m for m in k.marks.get(les["id"], []) if m["kind"] == "verdict"), None)
        item["decided_at"] = None if verdict is None else verdict["at"]  # when its trial's verdict came
        item["links"] = _links(les, k)
        item["back_as"] = (lessons_mod.back_copy(k.back_from, k.states, les["id"]) if les["state"] == PULLED
                           else None)  # its line is back already as this lesson, so it has no Bring back
        item["idea"] = (study_mod.idea_card(lessons, les) if lessons is not None and les.get("kind") == lessons_mod.IDEA
                        else None)
        return item

    def read_reports(self):
        """The saved night reports next to the database, oldest first: [(file name, report)],
        and the names that could not be read."""
        out, problems = [], []
        if self.reports is None or not self.reports.is_dir():
            return out, problems
        for path in sorted(self.reports.glob("night-*.json")):
            try:
                if path.stat().st_size > MAX_REPORT:
                    raise ValueError("too big")
                rep = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(rep, dict) or not isinstance(rep.get("agent"), str):
                    raise ValueError("not a night report")
            except (OSError, ValueError, UnicodeDecodeError):
                problems.append(f"A saved night report could not be read: {path.name}")
                continue
            out.append((path.name, rep))
        out.sort(key=lambda p: (_until(p[1]) or 0, p[0]))
        return out, problems

    def read_arena(self):
        """The newest Arena item of each agent saved next to the database (arena/run.py stuck_item
        or rounds_item): ({agent: {file, at, line, lost, rounds}}, the names that could not be read)."""
        out, problems = {}, []
        if self.reports is None or not self.reports.is_dir():
            return out, problems
        for path in sorted(self.reports.glob("arena-*-*.json")):
            try:
                if path.stat().st_size > MAX_REPORT:
                    raise ValueError("too big")
                item = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(item, dict) or item.get("kind") not in ("arena_stuck", "arena_rounds") or \
                        not isinstance(item.get("agent"), str) or not isinstance(item.get("line"), str) or \
                        not isinstance(item.get("at"), (int, float)) or path.name != f"arena-{item['agent']}-{item.get('run')}.json":
                    raise ValueError("not an Arena stuck item")
            except (OSError, ValueError, UnicodeDecodeError):
                problems.append(f"A saved Arena item could not be read: {path.name}")
                continue
            lost = []
            for x in item.get("lost") if isinstance(item.get("lost"), list) else []:
                q = _dict(_dict(x).get("quote"))
                lost.append({"card": str(_dict(x).get("card") or ""), "why": str(_dict(x).get("why") or ""),
                             "turn": q.get("turn") if isinstance(q.get("turn"), int) else None,
                             "who": str(q.get("who") or ""), "text": str(q.get("text") or "")})
            seen = out.get(item["agent"])
            if seen is None or (item["at"], path.name) > (seen["at"], seen["file"]):
                out[item["agent"]] = {"file": path.name, "at": float(item["at"]), "line": item["line"], "lost": lost[:3],
                                      "rounds": _arena_rounds(item.get("reflection"))}
        return out, problems

    def read_mode_cards(self):
        """The open new mode card of each agent saved next to the database (assistant/newmode.py
        open_cards; the night writes at most one): ({agent: {file, name, words, moments, days,
        fixed, broken, played}}, the names that could not be read)."""
        out, problems = {}, []
        if self.reports is None or not self.reports.is_dir():
            return out, problems
        from assistant import newmode
        for path in newmode.open_cards(self.reports):
            try:
                if path.stat().st_size > MAX_REPORT:
                    raise ValueError("too big")
                card = json.loads(path.read_text(encoding="utf-8"))
                arena = _dict(card.get("arena"))
                if card.get("agent") != newmode.AGENT or path.name != f"mode-{card['agent']}-{card.get('run')}.json" or \
                        not isinstance(card.get("name"), str) or not isinstance(card.get("at"), (int, float)):
                    raise ValueError("not a mode card")
            except (OSError, ValueError, UnicodeDecodeError):
                problems.append(f"A saved mode card could not be read: {path.name}")
                continue
            words = [w for w in card.get("words") if isinstance(w, str)] if isinstance(card.get("words"), list) else []
            seen = out.get(card["agent"])
            if seen is None or (card["at"], path.name) > (seen["at"], seen["file"]):
                out[card["agent"]] = {"file": path.name, "at": float(card["at"]), "name": card["name"], "words": words[:6],
                                      "moments": _num(card.get("moments")), "days": _num(card.get("days")),
                                      "fixed": _num(arena.get("fixed")), "broken": _num(arena.get("broken")),
                                      "played": _num(arena.get("days"))}
        return out, problems


class _Ctx:
    """What every lesson's item reads: the time, the tables, and the saved reports' cards,
    links, trial entries and the newest report of each agent."""

    def __init__(self, now, rows, trials, marks, clashes, reports, *, backs=None, exams=None):
        self.now = now
        self.exams = dict(exams or {})  # {lesson id: its exam row}
        self.wanting = set()  # the lessons held for a yes (engine.lessons.wants_yes_ids); view fills it
        self.by_id = {les["id"]: les for les in rows}
        self.states = {i: les["state"] for i, les in self.by_id.items()}
        self.back_from = dict(backs or {})  # {lesson id: the pulled lesson it was brought back from}
        self.back_as = {}
        for new, old in sorted(self.back_from.items()):
            self.back_as.setdefault(old, []).append(new)
        self.trials = trials
        self.marks = {}
        for m in marks:
            self.marks.setdefault(m["lesson_id"], []).append(m)
        self.replaces, self.replaced_by = {}, {}
        for c in clashes:
            self.replaces.setdefault(c["lesson_id"], []).append(c["live_id"])
            self.replaced_by.setdefault(c["live_id"], []).append(c["lesson_id"])
        saved, self.problems = reports
        self.cards, self.links, self.entries, self.newest = {}, {}, {}, {}
        for name, rep in saved:  # oldest first, so the newest report wins
            agent = rep["agent"]
            mine = {i for i, les in self.by_id.items() if les["agent"] == agent}
            for key, into, found in (("cards", self.cards, _dicts(rep.get("cards"))),
                                     ("links", self.links, _dicts(_dict(rep.get("links")).get("lessons"))),
                                     ("trials", self.entries, _dicts(_dict(rep.get("trials")).get("trials")))):
                for d in found:
                    lid = d.get("lesson_id")
                    if isinstance(lid, int) and lid in mine:
                        into[lid] = (d, _until(rep)) if key == "trials" else d
            notes = rep.get("notes") if isinstance(rep.get("notes"), list) else []
            self.newest[agent] = {"file": name, "until": _until(rep),
                                  "notes": [str(n) for n in notes if isinstance(n, (str, int, float))],
                                  "switches": _dict(rep.get("switches")) or None,
                                  "handed": _handed(rep), **_night_counts(rep, mine)}


def _night_counts(rep, mine):
    """What a night did, for the two tab page's Last night line: the chats it read, the hotfix notes
    written in its last day (engine/fast.py, a note with text only) and its trials, each {lesson_id,
    status, cases, harm} for a lesson of this agent."""
    until = _until(rep)
    hotfix = sum(1 for n in _dicts(rep.get("fast_notes")) if isinstance(n.get("text"), str) and n["text"]
                 and until is not None and (_num(n.get("written_at")) or 0) >= until - DAY)
    trials = []
    for d in _dicts(_dict(rep.get("trials")).get("trials")):
        lid, side = d.get("lesson_id"), _dict(d.get("with"))
        if isinstance(lid, int) and lid in mine:
            trials.append({"lesson_id": lid, "status": str(d.get("status") or ""), "cases": _num(side.get("cases")),
                           "harm": _num(side.get("harm"))})
    return {"chats": _num(_dict(rep.get("read")).get("cases")), "hotfix": hotfix, "trials": trials}


def _handed(rep):
    """The notes a night report handed over to other agents, each {to, text}; the page shows no more."""
    return [{"to": n["to"], "text": n["text"]} for n in _dicts(_dict(rep.get("hand_over")).get("notes"))
            if isinstance(n.get("to"), str) and isinstance(n.get("text"), str)]


def _exam_result(row):
    """What the exam a lesson took said, from its saved row: "passed", "failed", "not run" (the
    examiner raised, engine.exam.could_not_run), or None when it took no exam."""
    if not row:
        return None
    if row["passed"]:
        return "passed"
    return "not run" if row.get("check_name") == exam_mod.NOT_RUN else "failed"


def _held(les, k):
    """The line of a waiting lesson its exam held and no trial row has since: "failed the exam:
    situation N, check X"; "" for every other lesson."""
    if les["state"] != WAITING or les["id"] in k.trials:
        return ""
    return exam_mod.held_line(k.exams.get(les["id"]))


def _status(les, item, k, report):
    """(the lesson's state in words, why). A lesson under Accept high risk (item accept_high:
    who switched it on) is said to be under it, never to have a person's yes."""
    state = les["state"]
    acc = item.get("accept_high")
    under = f"Accept high risk (switched on by {acc})"
    if state == TRYING:
        paused = any(m["kind"] == "paused" for m in k.marks.get(les["id"], []))
        if paused:
            return "paused", "The stop rule paused it; it is given in no new case and waits for you to keep or stop it."
        if (les["ends_at"] or 0) <= k.now and trial_mod.open_unclear(les, k.marks.get(les["id"], [])) is not None:
            return "unclear", ("Its trial ended with too few results to tell, so it is given in no case and waits for you "
                               "to keep it on trial longer or drop it.")
        if acc:
            after = f", started under {under}"
        elif les.get("origin") == lessons_mod.PERSON:
            after = f" as {trial_mod._whose(les['yes_by'])} own line"
        else:
            after = f" after {les['yes_by']}'s yes" if les["yes_by"] else " with no yes, as a low risk lesson"
        if (les["ends_at"] or 0) > k.now:
            return "on trial", (f"On trial{after}, in {_pct(les['share'])} of cases until {_when(les['ends_at'])}; "
                                f"{_left(les['ends_at'] - k.now)}.")
        return "on trial, ended", "Its days are over; the verdict waits for its cases' results."
    if state == KEPT:
        if les["share"] < 1:
            return "kept", f"Kept by its trial; {_pct(1 - les['share'])} of cases keep the old way."
        if acc:
            return "kept", f"Kept by its trial; it started under {under}."
        return "kept", f"Kept with {les['yes_by']}'s yes." if les["yes_by"] else "Kept."
    if state == PULLED:
        return "pulled", les["pulled_why"] or "Pulled."
    if item["queued"]:
        ahead = ", ".join(f"lesson {i}" for i in item["ahead"]) or "the next free night"
        if acc:
            yes = (f" It waits under {under}: it starts with no yes only if the switch is still on at its turn, "
                   "else it waits for a yes.")
        else:
            yes = f" It has {les['yes_by']}'s yes." if les["yes_by"] else ""
        return "waits its turn", f"One trial runs on a stage at a time; it waits behind {ahead}.{yes}"
    close = _close_sentence(report)
    if item.get("exam"):  # the close sentence stays when the exam fails too (review gatefb round 2, finding 4)
        return "waits for a yes", (f"It {item['exam']}." + (f" {close}" if close else "")
                                  + " Yes on this card starts it anyway.")
    if item["replaces"]:
        names = ", ".join(f'lesson {r["id"]}' for r in item["replaces"])
        return "waits for a yes", f'It goes against {names}; its card asks "replace it?".'
    if close:
        return "waits for a yes", close
    if report.get("held"):
        return "waits for a yes", "The night's trial places were taken, so it waits for a yes."
    if les["risk"] == risk_mod.HIGH:
        return "waits for a yes", f"High risk: {plain_why(les['risk_why'])}."
    return "waits for a yes", "It waits for a person's yes."


def _close_sentence(report):
    """The sentence naming the pulled or failed line a card's lesson comes close to; "" for none."""
    if report.get("close_to_pulled"):
        return f'It comes close to the pulled line "{report["close_to_pulled"]}".'
    if report.get("close_to_failed"):  # DECISIONS item 50: close to a line the eval gate failed
        return f'It comes close to the line "{report["close_to_failed"]}", which failed the eval gate.'
    return ""


def _switches_line(sw):
    """The night report's switches in one line (reflection/night.py switches_line); None for a
    report from before the switches, or one whose switches cannot be read. The report's words,
    with its end day in Cairo time like every time on the page."""
    if not sw:
        return None
    try:
        line = night_mod.switches_line(sw)
        until = _num(sw["accept_high"].get("until"))
        if until:
            line = line.replace(night_mod._when(until), _when(until))
        return line
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def plain_why(risk_why):
    """The saved risk reasons in plain words. The code check saves "group: word", "group:
    /pattern/" or "tool: name" (engine/risk.py code_check), joined by "; "; a pattern is named
    by its group only, since a person reads the page, not the regex. A reason that reads the
    same as one before it shows once (a copy from 15 sources is one line)."""
    if not risk_why:
        return "no reason saved"
    out = []
    for part in risk_why.split("; "):
        group, sep, mark = part.partition(": ")
        if sep and group == "tool":
            out.append(f"it names the tool {mark}")
        elif sep and group == "judge":
            out.append(f"the judge said {mark}")
        elif sep and group == "core":
            out.append("it copies words from the cases it came from" if mark.startswith("copied from source")
                       else f"it has a {mark}")
        elif sep and len(mark) > 1 and mark.startswith("/") and mark.endswith("/"):
            out.append(f"it matches a pattern on the {group} list")
        elif sep:
            out.append(f'the word "{mark}" is on the {group} list')
        else:
            out.append(part)
    return "; ".join(dict.fromkeys(out))


def _links(les, k):
    """Every link of one lesson: [{text, to}], to: a lesson id on this page, or None."""
    out = []
    if les["source_lesson_id"] is not None:
        src = k.by_id.get(les["source_lesson_id"])
        who = src["agent"] if src else "another agent"
        out.append({"text": f"adapted from {who} lesson {les['source_lesson_id']}", "to": les["source_lesson_id"]})
    link = k.links.get(les["id"]) or {}
    if link.get("from_lesson") is not None:
        if link["from_lesson"] != les["source_lesson_id"]:
            out.append({"text": f"adapted from {link.get('from_agent')} lesson {link['from_lesson']}",
                        "to": link["from_lesson"] if link["from_lesson"] in k.by_id else None})
    elif link.get("from_agent") and link.get("from_agent") != les["agent"]:
        out.append({"text": f"learned from {link['from_agent']} cases", "to": None})
    for rx, words, text in ((_EDITED_FROM, "edited from lesson", les["source"]),
                            (_EDITED_INTO, "edited into lesson", les["pulled_why"]),
                            (_REPLACED_BY, "replaced by lesson", les["pulled_why"])):
        m = rx.match(text or "")
        if m:
            out.append({"text": f"{words} {m.group(1)}", "to": int(m.group(1))})
    if les["id"] in k.back_from:
        out.append({"text": f"brought back from lesson {k.back_from[les['id']]}", "to": k.back_from[les["id"]]})
    for i in k.back_as.get(les["id"], []):
        out.append({"text": f"brought back as lesson {i}", "to": i})
    for i in k.replaces.get(les["id"], []):
        out.append({"text": f"would replace lesson {i}", "to": i})
    for i in k.replaced_by.get(les["id"], []):
        out.append({"text": f"lesson {i} asks to replace it", "to": i})
    if _has_trial(les["id"], k):
        out.append({"text": "its trial", "to": f"t{les['id']}"})
    return out


def _has_trial(lesson_id, k):
    """True when the lesson has a trial entry on the page, so a link to it lands somewhere."""
    t = k.trials.get(lesson_id)
    return (t is not None and t["started_at"] is not None) or \
        any(m["kind"] in ("verdict", "paused") for m in k.marks.get(lesson_id, []))


def _trial(item, k):
    """One trial's outcome with its sides and marks; None when the lesson never went on trial."""
    if not _has_trial(item["id"], k):
        return None
    t, marks = k.trials.get(item["id"]), k.marks.get(item["id"], [])
    verdict = next((m for m in marks if m["kind"] == "verdict"), None)
    paused = next((m for m in marks if m["kind"] == "paused"), None)
    unclear = [m for m in marks if m["kind"] == "unclear"]
    detail, sides_from = None, None
    if verdict is not None:
        d = verdict["detail"] or {}
        status, why = str(d.get("status") or item["state"]), str(d.get("why") or "")
        detail, sides_from = d, f"verdict mark {verdict['id']}"
    elif paused is not None and item["state"] == TRYING:
        d = paused["detail"] or {}
        status, why = "paused", str(d.get("why") or "")
        detail, sides_from = d, f"pause mark {paused['id']}"
    elif item["status"] == "unclear":
        d = _dict(unclear[-1]["detail"])
        status, why = "unclear, waits for you", str(d.get("why") or item["why"])
        detail, sides_from = d, f"unclear mark {unclear[-1]['id']}"
    elif unclear and item["state"] == PULLED and (item["pulled_why"] or "").startswith(trial_mod.DROPPED):
        d = _dict(unclear[-1]["detail"])
        status, why = "unclear, then dropped", item["pulled_why"]
        detail, sides_from = d, f"unclear mark {unclear[-1]['id']}"
    elif item["state"] == TRYING and (item["ends_at"] or 0) > k.now:
        status, why = f"still running, {_left(item['ends_at'] - k.now)}", ""
    elif item["state"] == TRYING:
        status, why = "ended, waiting for results", ""
    elif item["state"] == PULLED:
        status, why = "stopped before its verdict", item["pulled_why"] or ""
    else:
        status, why = item["status"], item["why"]
    if detail is None and item["id"] in k.entries:
        entry, until = k.entries[item["id"]]
        detail, sides_from = entry, f"the night of {_when(until)}"
        why = why or str(entry.get("why") or "")
    sides = None
    if isinstance(detail, dict):
        sides = {side: _side(detail.get(side)) for side in ("with", "without")}
    return {"id": item["id"], "line": item["text"], "status": status, "why": why, "started_at": (t or {}).get("started_at"),
            "ends_at": item["ends_at"], "share": (t or {}).get("share"), "sides": sides, "sides_from": sides_from,
            "marks": [m for m in marks if m["kind"] in ("verdict", "unclear", "longer", "paused", "ping", "limit")]}


def _side(side):
    """One side of a trial as the page shows it: its counts and each case with its settling row."""
    if not isinstance(side, dict):
        return None
    cases = []
    for c in _dicts(side.get("list")):
        cases.append({"case": c.get("case"), "status": c.get("status"), "row": c.get("row"),
                      "given": c.get("given") if isinstance(c.get("given"), list) else []})
    return {"cases": side.get("cases"), "settled": side.get("settled"), "good": side.get("good"),
            "pending": side.get("pending"), "list": cases}


def _numbers(card):
    """The study's numbers on a card, and what it could gain; None when the card has none."""
    sure, cases = card.get("sure"), card.get("cases")
    if isinstance(sure, bool) or not isinstance(sure, (int, float)) or not isinstance(cases, dict):
        return None
    try:
        n1, n0, g1, g0 = (int(cases[k]) for k in ("with", "without", "good_with", "good_without"))
    except (KeyError, TypeError, ValueError):
        return None
    if min(n1, n0, g1, g0) < 0 or g1 > n1 or g0 > n0 or not 0 <= sure <= 1:
        return None
    gap = abs((1 + g1) / (2 + n1) - (1 + g0) / (2 + n0))
    good = (card.get("moves") or {}).get("result") if isinstance(card.get("moves"), dict) else None
    return {"chance": float(sure), "gap": gap, "gain": float(sure) * gap, "total": n1 + n0, "with": n1,
            "without": n0, "good_with": g1, "good_without": g0, "good": str(good or "good")}


def _rank(item):
    """Cards with numbers first, the most to gain first, then more cases, then the older."""
    n = item["numbers"]
    if n is None:
        return (1, 0.0, 0, item["id"])
    return (0, -n["gain"], -n["total"], item["id"])


def _short(les, lesson_id):
    if les is None:
        return {"id": lesson_id, "text": "", "state": "unknown"}
    return {"id": les["id"], "text": les["text"], "state": les["state"]}


# ---- the page --------------------------------------------------------------------------------

def h(v):
    """Every field goes through here: escaped, quotes too."""
    return html.escape("" if v is None else str(v), quote=True)


ICONS = {  # 24 by 24 line icons drawn inline, since the page loads no outside image
    "sun": '<path d="M3 18h18"/><path d="M7 18a5 5 0 0 1 10 0"/><path d="M12 6v3M5.6 10.6 7 12M18.4 10.6 17 12"/>',
    "list": '<path d="M10 6h10M10 12h10M10 18h10"/><path d="m4 6 1.2 1.2L7.5 5M4 12l1.2 1.2L7.5 11M4 18l1.2 1.2L7.5 17"/>',
    "bulb": ('<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 '
             '1.1-2.2A6 6 0 0 0 12 3Z"/>'),
    "facts": '<path d="M4 20h16"/><path d="M7 16v-4M12 16V7M17 16v-6"/>',
    "sliders": '<path d="M4 7h9M18 7h2M4 17h2M11 17h9"/><circle cx="15.5" cy="7" r="2.5"/><circle cx="8.5" cy="17" r="2.5"/>',
    "chat": '<path d="M4 12a8 8 0 1 1 3.3 6.5L4 20l1.2-3.6A8 8 0 0 1 4 12z"/>',
    "megaphone": '<path d="M4 10v4h3l7 4V6L7 10H4zM18 9a4 4 0 0 1 0 6"/>',
    "spark": '<path d="M12 4v4M12 16v4M4 12h4M16 12h4M6.5 6.5 9 9M15 15l2.5 2.5M6.5 17.5 9 15M15 9l2.5-2.5"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3"/><path d="M7.5 15h9"/>',
    "chev": '<path d="M9 6l6 6-6 6"/>',
    "out": '<path d="M7 17L17 7M9 7h8v8"/>',
}
AGENT_ICONS = {"sales": "chat", "marketing": "megaphone"}  # any other agent gets "spark"
LOGO = ('<svg viewBox="0 0 64 64" fill="currentColor" aria-hidden="true"><path d="M6 56 L36 56 L46 46 L16 46 Z"/>'
        '<path d="M13 44 L43 44 L53 34 L23 34 Z" opacity=".72"/><path d="M20 32 L50 32 L60 22 L30 22 Z" opacity=".45"/></svg>')
TABS = (("today", "sun", "Today"), ("lessons", "list", "Lessons"), ("ideas", "bulb", "Ideas"), ("facts", "facts", "Facts"),
        ("agents", "sliders", "Agents"))
OTHER_CASES = "the other cases"
_SRC_NUMBERS = re.compile(r'"(?P<p>.+)" (?P<hh>helps|hurts); (?P<there>there )?with it (?P<g1>\d+) of (?P<n1>\d+) ended '
                          r'(?P<good>[^,;]+), without it (?P<g0>\d+) of (?P<n0>\d+)')
_SRC_CASE_IDS = re.compile(r"; cases with it: [^;]*")
_SRC_FROM_IDS = re.compile(r'^(adapted \S+ from \S+ cases) [^"]*?: (?=")')
_NEVER = re.compile(r"\b(?:never|did not|didn't) (?P<verb>[a-z]+ed) (?:(?:for|about) )?(?:(?:a|an|the|any) )?(?P<rest>.+)$")
_STOP = re.compile(r" (?:before|after|in|on|at|with|when|while|during|until|to|from|by|for|of|so|because|and|or|but) .*$")


def _icon(name, cls="i"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def _agent_icon(agent):
    return _icon(AGENT_ICONS.get(agent, "spark"))


def sides(pattern):
    """The two sides of a study's counts, named from the pattern's own words: (the cases the
    pattern describes, the rest). Never "with it" and "without it", which read as the lesson.
    A pattern that says something never happened names the thing and the act: "The agent never
    asked for a landmark before the order." gives ("landmark not asked", "landmark asked").
    Any other pattern is named by its own words, the rest as "the other cases"."""
    words = re.sub(r"\s+", " ", str(pattern or "")).strip().rstrip(".!?").strip()
    if not words:
        return "cases with the pattern", OTHER_CASES
    m = _NEVER.search(words.lower())
    if m:
        thing = _STOP.sub("", " " + m.group("rest")).strip()
        if thing and len(thing.split()) <= 3:
            return f"{thing} not {m.group('verb')}", f"{thing} {m.group('verb')}"
    if len(words) > 1 and words[1:2].islower():
        words = words[:1].lower() + words[1:]
    return words, OTHER_CASES


def _pattern(source):
    """The pattern a study lesson came from, read from its source line; None for any other line."""
    m = _SRC_NUMBERS.search(source or "")
    return m.group("p") if m else None


def source_text(source):
    """A lesson's source line as the page shows it: the study's counts named by the pattern's own
    words (sides), never "with it", and no raw case ids."""
    s = _SRC_FROM_IDS.sub(r"\1: ", _SRC_CASE_IDS.sub("", source or ""))

    def named(m):
        a, b = sides(m.group("p"))
        there = "there " if m.group("there") else ""
        return (f'"{m.group("p")}" {m.group("hh")}; {there}{a}: {m.group("g1")} of {m.group("n1")} ended '
                f'{m.group("good")}; {b}: {m.group("g0")} of {m.group("n0")}')
    return _SRC_NUMBERS.sub(named, s)


def _good_word(item):
    """The result the card's counts ended in: the one its source line names (an adapted lesson's
    counts come from the other agent's cases), else the study card's."""
    m = _SRC_NUMBERS.search(item.get("source") or "")
    return m.group("good") if m else item["numbers"]["good"]


def render(view, *, token=None, flash=None):
    """The page, in the locked A3 look (_system/hackathon/design/morning/r1/opt-a3.html): the
    greeting, the waiting stack, the trial card, then Ideas, Facts and each agent's switches as rows
    that open, and the fold "What happened overnight" below, closed. The tabs are links to those
    parts, with no count on any of them (item 35). token None: a static copy with no forms and no
    buttons."""
    where = "A static copy" if token is None else "On this computer only"
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
           f'<title>Morning summary</title><style>{CSS}</style></head><body><div class="page">',
           f'<nav class="tisl sq" aria-label="Main"><div class="left"><span class="tlogo">{LOGO}</span>'
           f'<span class="word">Ascent</span></div><div class="tnav">{_tabs("titem")}</div>'
           f'<div class="right"><span class="tsample">{h(where)}</span></div></nav>',
           f'<header class="bar"><div class="brand"><span class="logo">{LOGO}</span><span class="word">Ascent</span>'
           f'<span class="where">Reflection, morning</span></div><span class="sample">{h(where)}</span></header>',
           '<section class="top" id="today" aria-label="Today"><div class="hello"><h1>Good morning</h1>',
           f'<p class="num">{h(_today(view["at"]))}</p>']
    if token is None:
        out.append('<p>A static copy: no buttons.</p>')
    out.append("</div>")
    if flash:
        out.append(f'<p class="flash" role="status">{h(flash)}</p>')
    out.append('</section><div class="grid"><div class="col">')
    out.append(_waiting_html(view, token))
    if view["unclear"]:
        out.append('<section class="unclear" aria-labelledby="u-h"><div class="sec-h"><h2 id="u-h">Unclear: too few '
                   'results to tell</h2></div>' + "".join(_unclear_html(u, token) for u in view["unclear"]) + "</section>")
    modes = [a for a in view["agents"] if a.get("mode_card") is not None]
    if modes:  # a new mode needs the user's yes, so it is open on the page, never in the fold
        out.append('<section class="modes" aria-labelledby="m-h"><div class="sec-h"><h2 id="m-h">A new mode?</h2></div>'
                   + "".join(f'<article class="wcard sq" id="mode-{h(a["agent"])}">'
                             + _mode_card_html(a["agent"], a["mode_card"], token if a["buttons"] else None)
                             + "</article>" for a in modes) + "</section>")
    out.append('</div><aside class="col">')
    out.append(_reflection_html(view, token))
    out.append('<div class="rows">')
    if view.get("ideas"):
        out.append(_ideas_html(view["ideas"], token))
    out.append(_facts_html(view, token))
    out.append(_agents_rows(view, token))
    out.append("</div></aside></div>")
    out.append(_overnight_html(view, token))
    out.append("</div>")
    out.append(f'<nav class="isl" aria-label="Main">{_tabs("tab")}</nav>')
    out.append("</body></html>")
    return "\n".join(out)


def _overnight_html(view, token):
    """The fold "What happened overnight", closed until opened: every part that needs no answer,
    each agent's night notes, Arena, snapshot, lessons, trials and pulled lessons, and any saved
    report that could not be read. Its buttons (Stop, Edit, Bring back, a lesson's own level) stay
    inside for whoever wants them; nothing in it waits for the user (DECISIONS item 35)."""
    out = ['<section class="byagent" aria-labelledby="b-h"><details class="overnight" id="overnight">'
           f'<summary><h2 id="b-h">What happened overnight</h2><small>Nothing here waits for you</small>'
           f'{_icon("chev", "i chev")}</summary>']
    for p in view["problems"]:
        out.append(f'<p class="flash">{h(p)}</p>')
    if not view["agents"]:
        out.append('<div class="calm sq"><p class="calm-h">No lessons yet.</p><p>Each agent shows here after its first '
                   'night.</p></div>')
    for a in view["agents"]:
        out.append(_agent_html(a, token))
    out.append("</details></section>")
    return "\n".join(out)


def _tabs(cls):
    """The five tabs, each a link to its part of the page, with no count on any (item 35)."""
    return "".join(f'<a class="{cls}" href="#{anchor}">{_icon(icon)}{name}</a>' for anchor, icon, name in TABS)


def _waiting_html(view, token):
    """The waiting stack: the first card open, in light sage, with Yes and No; the next ones peek
    under it as white passes, titles only, each opening to its own full card and buttons. No count
    beside the heading and no word of the cards behind these (item 35): they show once a card is
    answered, and one left unanswered simply stays off."""
    cards = view["cards"]
    small = "Most to gain first" if cards else ""
    out = ['<section class="lessons" id="lessons" aria-labelledby="w-h">',
           f'<div class="sec-h"><h2 id="w-h">Waiting for your yes</h2><small>{h(small)}</small></div>']
    if not cards:
        out.append('<div class="calm sq"><p class="calm-h">Nothing waits for a yes.</p>'
                   '<p>A lesson that needs your yes shows here.</p></div>')
    else:
        first = cards[0]
        out.append(f'<div class="stack"><article class="pass sq" id="c{h(first["id"])}" aria-label="Lesson '
                   f'{h(first["id"])}, waiting for your yes">{_card_html(1, first, token)}</article>')
        for n, item in enumerate(cards[1:], 1):
            out.append(f'<details class="peek p{min(n, 4)} sq" id="c{h(item["id"])}"><summary><span class="pt" dir="auto">'
                       f'{h(item["text"])}</span>{_icon("chev", "i chev")}</summary>'
                       f'<div class="peek-in">{_card_html(n + 1, item, token)}</div></details>')
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


def _card_html(n, item, token):
    """One card that waits for a yes (n: its place, the most to gain first): the agent, the lesson
    and its risk, why it waits, its numbers, the trial a yes means, Yes and No; under More on this
    lesson a why for No, its own level, Edit and its links."""
    risk = str(item["risk"] or "")
    out = [f'<div class="pass-h"><div class="agent"><span class="av">{_agent_icon(item["agent"])}</span>'
           f'<div><strong>{h(item["agent"])}</strong><small>Lesson {h(item["id"])}, {h(_stages(item["stages"]))}</small></div></div>'
           f'<span class="risk risk-{h(risk)}"><span class="dot"></span>{h(_cap(risk))} risk</span></div>',
           f'<p class="lesson" dir="auto">{h(item["text"])}</p>']
    for r in item["replaces"]:
        out.append(f'<p class="why">Replace it? It would pull lesson {_a(r["id"])}: '
                   f'<span class="old" dir="auto">{h(r["text"])}</span></p>')
    out.append(f'<p class="why">{h(item["why"])}</p>')
    if item.get("gate"):
        out.append(f'<p class="gain">{h(gate_line(item["gate"]))}</p>')
    n_ = item["numbers"]
    if n_:
        good = _good_word(item)
        out.append(_pair(n_, item["source"], f"Ended {good}, night study"))
        out.append(f'<p class="gain">What it could gain: the two sides differ by about {h(round(n_["gap"] * 100))} '
                   f'in 100 cases ending {h(good)}; the chance it is better is {h(_pct(n_["chance"]))}. '
                   f'From {h(n_["total"])} cases.</p>')
    elif item.get("idea"):
        out.append('<div class="ilines">' + _idea_lines(item["idea"]) + "</div>")
    else:
        out.append('<p class="gain">No study numbers for this card, so it comes after the cards that have them.</p>')
    act = [_trial_words(item)]
    if token is not None:
        act.append(_form(token, "no", item["id"], "No", quiet=True, form_id=f'no-{item["id"]}', cls="no"))
        act.append(_form(token, "yes", item["id"], "Yes, replace it" if item["replaces"] else "Yes",
                         hidden=("shown", ",".join(str(r["id"]) for r in item["replaces"])), cls="yes"))
    if "".join(act):
        out.append('<div class="act">' + "".join(act) + "</div>")
    more = []
    if token is not None:
        more.append(f'<label class="fld">A why for No, optional<input type="text" name="why" value="" '
                    f'form="no-{h(item["id"])}" placeholder="Why, optional" maxlength="{MAX_LEN}" dir="auto"></label>')
    more.append(_level_html(item, token))
    if token is not None and not item["replaces"]:  # a "replace it?" card is answered Yes or No, never edited
        more.append(_edit_html(token, item))
    more.append(_links_html(item))
    body = "".join(more)
    if body:
        out.append(f'<details class="more-l"><summary>More on this lesson</summary><div class="ml-in">{body}</div></details>')
    return "\n".join(out)


def gate_line(eff):
    """A card's gate counts in one plain line, the p-value in words, no number to read:
    "Checked before use: fixed 3, broke 0. Could be chance." """
    return f'Checked before use: fixed {eff["fixed"]}, broke {eff["broke"]}. {_cap(eff["words"])}.'


def _trial_words(item):
    """The trial a yes means for a card, in one line: its level, share and days."""
    lv = item.get("level")
    if not lv:
        return ""
    if lv["given"]:
        return '<p class="trial-l">Its share and days came with its yes.</p>'
    return (f'<p class="trial-l">A yes means a <strong>{h(lv["level"])} trial</strong>: {h(_share(lv["share"]))} for '
            f'{h(lv["days"])} days</p>')


def _pair(n_, source, label):
    """The study's two counts side by side, each side named from the pattern's own words."""
    a, b = sides(_pattern(source))
    return (f'<div class="pair"><span class="lab">{h(label)}</span>'
            f'<div class="stat"><b class="num">{h(n_["good_with"])}<small>of</small>{h(n_["with"])}</b><span>{h(a)}</span>'
            f'</div><div class="stat"><b class="num">{h(n_["good_without"])}<small>of</small>{h(n_["without"])}</b>'
            f'<span>{h(b)}</span></div></div>')


def _stages(stages):
    stages = [s for s in stages or [] if s]
    if not stages or stages == [plug_mod.ALL]:
        return "all stages"
    return ("stage " if len(stages) == 1 else "stages ") + ", ".join(stages)


def _reflection_html(view, token=None):
    """The trial card: the first lesson on trial, in dark sage, with the study's counts before it,
    its days left and when it ends. The other lessons on trial follow as rows, then each trial the
    stop rule paused, with Stop: a pause waits for the user, so it is open here, never only in the
    fold. A paused lesson with no answer stays paused, given in no new case."""
    now = view["at"]
    paused = [(a, i) for a in view["agents"] for i in a["live"] if i["status"] == "paused"]
    trials = {t["id"]: t for a in view["agents"] for t in a["trials"]}
    running = sorted((i for a in view["agents"] for i in a["live"] if i["status"] == "on trial"),
                     key=lambda i: (i["ends_at"] or 0, i["id"]))
    pulled = sum(1 for a in view["agents"] for i in a["pulled"] if (i["pulled_at"] or 0) >= now - DAY)
    small = f"{pulled} pulled in the last day" if pulled else "Nothing pulled in the last day"
    out = ['<section class="reflection" aria-labelledby="t-h">',
           f'<div class="sec-h"><h2 id="t-h">Reflection</h2><small>{h(small)}</small></div>']
    if not running:
        out.append('<div class="calm sq"><p class="calm-h">Nothing is on trial.</p>'
                   '<p>A lesson on trial shows here, with its days left.</p></div>')
    else:
        out.append(_glow_html(running[0], trials.get(running[0]["id"]), now))
        if running[1:]:
            out.append('<div class="rows also">')
            for i in running[1:]:
                left = _days_left(i["ends_at"], now)
                body = f'<p class="big" dir="auto">{h(i["text"])}</p><p class="meta">{h(i["why"])}</p>'
                if i["id"] in trials:
                    body += f'<p class="meta"><a href="#t{h(i["id"])}">Its trial</a></p>'
                out.append(_pill("flask", f'{i["agent"]}, also on trial', i["text"],
                                 f'{left} day{"s" if left != 1 else ""} left', body))
            out.append("</div>")
    if paused:
        out.append('<div class="rows also">')
        for a, i in paused:
            body = f'<p class="big" dir="auto">{h(i["text"])}</p><p class="meta">{h(i["why"])}</p>'
            if i["id"] in trials:
                body += f'<p class="meta"><a href="#t{h(i["id"])}">Its trial</a></p>'
            if token is not None and a["buttons"]:
                body += _form(token, "stop", i["id"], "Stop", field=("why", "", "Why, in one line", True))
            out.append(_pill("flask", f'{i["agent"]}, paused', i["text"], "Paused", body, ident=f'p{i["id"]}'))
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


def _glow_html(item, t, now):
    started, ends = (t or {}).get("started_at"), item["ends_at"]
    left = _days_left(ends, now)
    out = ['<article class="glow sq">',
           f'<div class="glow-h"><div class="gl"><span class="gchip">On trial</span><span class="gsub">{h(item["agent"])}, '
           f'{h(_share(item["share"]))}</span></div>'
           + (f'<a class="glass-b" href="#t{h(item["id"])}" aria-label="Open the trial of lesson {h(item["id"])}">'
              f'{_icon("out")}</a>' if t else "") + '</div>',
           f'<p class="lesson" dir="auto">{h(item["text"])}</p>']
    if item["numbers"]:
        out.append(_pair(item["numbers"], item["source"], f"Ended {_good_word(item)}, before the trial"))
    total = (ends - started) if isinstance(started, (int, float)) and ends else None
    if total and total > 0:
        days = max(1, round(total / DAY))
        day = min(days, int(max(0.0, now - started) // DAY) + 1)
        width = max(4.0, min(100.0, round((now - started) / total * 100, 1)))
        track = (f'<svg class="track" viewBox="0 0 100 3" preserveAspectRatio="none" role="img" aria-label="Day {day} '
                 f'of {days}"><rect class="tb" width="100" height="3" rx="1.5"/><rect class="tf" width="{width:g}" '
                 'height="3" rx="1.5"/></svg>')
    else:
        track = ""
    out.append(f'<div class="prog"><div class="prog-row"><b class="num">{left}<small>day{"s" if left != 1 else ""} left'
               f'</small></b><span>Ends {h(_date(ends))}</span></div>{track}</div>')
    out.append("</article>")
    return "\n".join(out)


def _days_left(ends, now):
    return max(1, math.ceil(((ends or now) - now) / DAY))


def _pill(icon, title, sub, chip, body, *, ident=None):
    """One white row that opens: an icon, a title and a short line, a chip, and what it holds."""
    ident = f' id="{h(ident)}"' if ident else ""
    return (f'<details class="pill sq"{ident}><summary><span class="ic">{_icon(icon)}</span><span class="tx"><strong>{h(title)}'
            f'</strong><small dir="auto">{h(sub)}</small></span><span class="vchip">{h(chip)}</span>'
            f'{_icon("chev", "i chev")}</summary><div class="more">{body}</div></details>')


def _unclear_html(u, token):
    """An unclear lesson's card: its numbers, whose idea it was, Keep on trial longer and Drop."""
    w, wo = u["sides"]["with"], u["sides"]["without"]
    out = [f'<article class="wcard sq" id="u{h(u["id"])}"><div class="pass-h"><div class="agent"><span class="av">'
           f'{_agent_icon(u["agent"])}</span><div><strong>{h(u["agent"])}</strong><small>Lesson {_a(u["id"])}, trial ended '
           f'{h(_when(u["ended"]))}</small></div></div></div>',
           f'<p class="lesson" dir="auto">{h(u["text"])}</p>']
    if u["said"]:
        out.append(f'<p class="why">{h(u["said"])}</p>')
    chance = f' The chance it is better is {h(_pct(u["chance"]))}.' if u["chance"] is not None else ""
    out.append(f'<div class="pair"><span class="lab">Settled cases that ended {h(u["good"])}</span>'
               f'<div class="stat"><b class="num">{h(w["good"])}<small>of</small>{h(w["settled"])}</b><span>given the '
               f'lesson, from {h(w["sources"])} sources</span></div><div class="stat"><b class="num">{h(wo["good"])}'
               f'<small>of</small>{h(wo["settled"])}</b><span>the old way, from {h(wo["sources"])} sources</span></div>'
               f'</div>')
    out.append(f'<p class="gain">A verdict needs {h(trial_mod.MIN_CASES)} settled cases from {h(trial_mod.MIN_SOURCES)} '
               f'sources on each side.{chance}</p>')
    out.append('<p class="meta">It is given in no case now. Keep it on trial longer: the same share of cases, and the '
               'numbers so far still count. Drop it: pulled, never given again.</p>')
    if u["ahead"]:
        one = len(u["ahead"]) == 1
        out.append(f'<p class="meta">{"Lesson" if one else "Lessons"} {", ".join(_a(i) for i in u["ahead"])} '
                   f'{"is" if one else "are"} on trial on its stages now, so it is kept on trial longer only once '
                   f'{"that trial ends" if one else "those trials end"}.</p>')
    out.append(_links_html(u))
    if token is not None:
        days = "" if u["days"] is None else str(u["days"])
        out.append(_form(token, "longer", u["id"], "Keep on trial longer",
                         field=("days", days, f"Days, 1 to {trial_mod.LONGER_DAYS}", True)))
        out.append(_form(token, "drop", u["id"], "Drop", quiet=True))
    out.append("</article>")
    return "\n".join(out)


def _ideas_html(ideas, token):
    """The Ideas row: each open idea's card, whose it is and what it must move, then with a token
    one Try an idea form per agent with a plug."""
    open_ = ideas["open"]
    sub = open_[0]["idea"]["idea"] if open_ else "No idea is waiting or on trial"
    body = ['<p class="mh">Ideas: the agent\'s and yours</p>',
            '<p class="meta">An idea is a lesson with no past cases behind it, a path to try. The agent\'s ideas and yours '
            'go on the same trial, at the same share of cases; only the trial decides.</p>']
    if open_:
        body.append('<div class="ideas-list">' + "".join(_idea_html(i) for i in open_) + "</div>")
    else:
        body.append('<p class="meta">No idea is waiting or on trial.</p>')
    if token is not None:
        body.append('<p class="mh">Try an idea</p>')
        for a in ideas["agents"]:
            body.append(_try_html(token, a))
    return _pill("bulb", "Ideas", sub, "Open" if open_ else "None open", "".join(body), ident="ideas")


def _idea_html(item):
    card = item["idea"]
    return "\n".join([
        f'<div class="sub" id="i{h(item["id"])}"><span class="vchip">{h(item["agent"])}, lesson {_a(item["id"])}, '
        f'{h(item["risk"])} risk</span>',
        f'<p class="big" dir="auto">{h(card["idea"])}</p>',
        _idea_lines(card),
        f'<p class="meta">{h(item["why"])}</p>',
        "</div>"])


def _idea_lines(card):
    """An idea's card in plain lines: what it must move and when we know, what must not get
    worse, how sure today, and its trial level."""
    mv, lv, harm = card["moves"], card["level"], card["must_not_worsen"]
    lo, hi = mv["shows_in_days"]
    worse = (", ".join(harm["results"]) + (f' ({harm["about"]})' if harm["about"] else "") if harm["results"]
             else harm["about"] or "nothing named")
    return (f'<p class="meta">{h(_cap(card["whose"]))} idea. It must move {h(mv["result"])}, which shows {h(_n(lo))} to '
            f'{h(_n(hi))} days after a case; we know about {h(_n(card["know_in_days"]))} days after its trial '
            f'starts.</p>'
            f'<p class="meta">Must not get worse: {h(worse)}.</p>'
            f'<p class="meta">How sure today: {h(card["sure"])}.</p>'
            f'<p class="meta">Trial level: {h(lv["name"])}, {h(_pct(lv["share"]))} of cases for {h(_n(lv["days"]))} '
            f'days.</p>')


def _try_html(token, a):
    """One Try an idea form: the agent, a one line idea and its stage."""
    options = '<option value="all">all stages</option>' + "".join(
        f'<option value="{h(s)}">{h(s)}</option>' for s in a["stages"])
    return (f'<form method="post" action="/idea" class="wrap"><input type="hidden" name="token" value="{h(token)}">'
            f'<input type="hidden" name="agent" value="{h(a["agent"])}">'
            f'<input type="text" name="line" value="" placeholder="An idea for {h(a["agent"])}, one line" '
            f'maxlength="{MAX_LEN}" dir="auto" required aria-label="An idea for {h(a["agent"])}, one line">'
            f'<select name="stage" aria-label="Stage">{options}</select>'
            f'<button type="submit">Try an idea</button></form>')


def _cap(s):
    return s[:1].upper() + s[1:]


def _n(x):
    """A number of days as a person reads it: 7, 2.5."""
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:.1f}"


def _agents_rows(view, token):
    """Each agent's switches as a white row that opens (Agents tab)."""
    rows = [a for a in view["agents"] if a.get("switches")]
    out = ['<div class="rows" id="agents" role="group" aria-label="Agents">']
    if not rows:
        out.append('<div class="calm sq"><p class="calm-h">No agent switches yet.</p><p>An agent with a plug in this repo '
                   'shows its switches here once it has worked.</p></div>')
    for a in rows:
        sw = a["switches"]
        acc = "on" if sw["accept"]["on"] else "off"
        out.append(_pill(AGENT_ICONS.get(a["agent"], "spark"), f'{a["agent"]} switches', f"Accept high risk is {acc}",
                         _cap(sw["level"]["level"]), _switches_html(a, token), ident=f'sw-{a["agent"]}'))
    out.append("</div>")
    return "\n".join(out)


def _agent_html(a, token):
    buttons = token is not None and a["buttons"]
    out = [f'<section class="agent-sec sq" aria-labelledby="agent-{h(a["agent"])}"><h2 id="agent-{h(a["agent"])}">'
           f'<span class="av">{_agent_icon(a["agent"])}</span>{h(a["agent"])}</h2>']
    if not a["buttons"]:
        out.append('<p class="meta">No plug for this agent in the repo, so its lessons are shown without buttons.</p>')
    elif a.get("switches"):
        out.append(f'<p class="meta">Its switches: <a href="#sw-{h(a["agent"])}">{h(a["agent"])} switches</a>.</p>')
    night = a["night"]
    out.append("<h3>The night's notes</h3>")
    if night is None:
        out.append('<p class="meta">No saved night report.</p>')
    else:
        out.append(f'<p class="meta">Night of {h(_when(night["until"]))} ({h(night["file"])}).</p>')
        line = _switches_line(night["switches"])
        if line:
            out.append(f'<p class="meta">Switches that night: {h(line)}.</p>')
        out.append("<ul>" + "".join(f'<li class="meta" dir="auto">{h(n)}</li>' for n in night["notes"]) + "</ul>"
                   if night["notes"] else '<p class="meta">No notes.</p>')
        out.extend(f'<p class="meta handed" dir="auto">Note to {h(n["to"])}: {h(n["text"])}</p>'
                   for n in night.get("handed") or [])
    stuck = a.get("arena")
    if stuck is not None:
        out.append("<h3>The Arena</h3>")
        out.append(f'<p class="meta" dir="auto">{h(stuck["line"])} Run of {h(_when(stuck["at"]))} ({h(stuck["file"])}).</p>')
        if stuck["lost"]:
            out.append("<ul>" + "".join(
                f'<li class="meta" dir="auto">Lost {h(x["card"])}: {h(x["why"])}'
                + (f' (turn {h(x["turn"])}, {h(x["who"])}: "{h(x["text"])}")' if x["turn"] is not None else "")
                + "</li>" for x in stuck["lost"]) + "</ul>")
        if stuck.get("rounds"):
            out.append("<ul>" + "".join(f'<li class="meta">{h(x)}</li>' for x in stuck["rounds"]) + "</ul>")
    snap = a["snapshot"]
    if snap is not None:
        back = f' To roll back to it: <code>{h(snap["command"])}</code>' if snap["command"] else ""
        out.append(f'<p class="meta">Latest snapshot: the night of {h(snap["night"])}, '
                   f'{h(snapshots.size(snap["lessons"], snap["live"]))} (hash {h(snap["hash"])}).{back}</p>')
    sections = (("New in the last day", a["new"], False, "Nothing new."),
                ("Live: kept and on trial", a["live"], True, "No live lessons."),
                ("Waiting", a["waiting"], True, "Nothing waits."),
                ("Pulled", a["pulled"], True, "Nothing pulled."))
    for title, items, anchor, empty in sections[:3]:
        out.append(_list_html(title, items, anchor, empty, buttons and title.startswith("Live"), token))
    out.append("<h3>Trials</h3>")
    out.append("<ul>" + "".join(_trial_html(t) for t in a["trials"]) + "</ul>" if a["trials"]
               else '<p class="meta">No trials.</p>')
    title, items, anchor, empty = sections[3]
    out.append(_list_html(title, items, anchor, empty, buttons, token))
    out.append("</section>")
    return "\n".join(out)


def _mode_card_html(agent, mode, token):
    """The open new mode card: the name, the user's words behind it, the Arena's counts, and Yes,
    Rename and Drop when the page has buttons. No answer changes nothing."""
    words = ", ".join(f'"{w}"' for w in mode["words"])
    seen = (f' on {_n(mode["days"])} days' if mode["days"] is not None else "") + \
        (f', {_n(mode["moments"])} times' if mode["moments"] is not None else "")
    out = [f'<div class="pass-h"><div class="agent"><span class="av">{_agent_icon(agent)}</span><div><strong>{h(agent)}'
           '</strong><small>A new mode, no answer changes nothing</small></div></div></div>',
           f'<p class="lesson" dir="auto">{h(mode["name"])}</p>',
           f'<p class="meta" dir="auto">"{h(mode["name"])}": you said {h(words)}{h(seen)}, and it fit no mode.</p>']
    if mode["fixed"] is not None and mode["played"] is not None:
        out.append(f'<p class="meta">On {h(_n(mode["played"]))} of your past days the Arena played it fixed '
                   f'{h(_n(mode["fixed"]))} and broke {h(_n(mode["broken"] or 0))}.</p>')
    if token is not None:
        card = ("card", mode["file"])
        out.append(_agent_form(token, "mode", agent, "Yes", hidden=(card, ("choice", "yes")))
                   + _agent_form(token, "mode", agent, "Rename", hidden=(card, ("choice", "rename")),
                                 extra='<input type="text" name="name" value="" placeholder="Its name, a word or two" '
                                       'maxlength="40" dir="auto" aria-label="Its name, a word or two" required>')
                   + _agent_form(token, "mode", agent, "Drop", hidden=(card, ("choice", "drop")), quiet=True))
    return "\n".join(out)


def _list_html(title, items, anchor, empty, buttons, token):
    if not items:
        return f'<h3>{h(title)}</h3><p class="meta">{h(empty)}</p>'
    out = [f"<h3>{h(title)}</h3><ul>"]
    for i in items:
        ident = f' id="l{h(i["id"])}"' if anchor else ""
        when = f', pulled {_when(i["pulled_at"])}' if i["state"] == PULLED and i["pulled_at"] else ""
        out.append(f'<li class="item"{ident}><span class="meta">lesson {_a(i["id"]) if not anchor else h(i["id"])}, '
                   f'{h(i["status"])}, {h(i["risk"])} risk, stages {h(", ".join(i["stages"]))}, added '
                   f'{h(_when(i["added_at"]))}{h(when)}</span>'
                   f'<p class="line" dir="auto">{h(i["text"])}</p><p class="meta">{h(i["why"])}</p>')
        if i["source"]:
            out.append(f'<p class="meta" dir="auto">Source: {h(source_text(i["source"]))}</p>')
        if anchor and i.get("level"):  # in the Waiting list, not again under New in the last day
            out.append(_level_html(i, token))
        out.append(_links_html(i))
        if buttons and i["state"] == PULLED:
            if i["back_as"] is None:
                out.append(_form(token, "back", i["id"], "Bring back"))
                out.append('<p class="meta">Bring back adds its line again as a new lesson on a new trial, or waiting '
                           'its turn; this one stays pulled.</p>')
            else:
                out.append(f'<p class="meta">Its line is back already as lesson {_a(i["back_as"])}.</p>')
        elif buttons:
            out.append(_form(token, "stop", i["id"], "Stop", field=("why", "", "Why, in one line", True)))
            out.append(_edit_html(token, i))
        out.append("</li>")
    out.append("</ul>")
    return "\n".join(out)


def _links_html(item):
    """A lesson's links, and how many cases are behind it; the case ids stay in the saved night
    report, never on the page."""
    parts = []
    for link in item["links"]:
        to = link["to"]
        if to is None:
            parts.append(h(link["text"]))
        else:
            target = to if isinstance(to, str) else f"l{to}"
            parts.append(f'<a href="#{h(target)}">{h(link["text"])}</a>')
    out = f'<p class="meta">Links: {"; ".join(parts)}.</p>' if parts else ""
    if item["cases"]:
        n = len(item["cases"])
        out += f'<p class="meta">The {h(n)} case{"s" if n != 1 else ""} behind it are named in the saved night report.</p>'
    return out


def _trial_html(t):
    out = [f'<li class="item" id="t{h(t["id"])}"><span class="meta">lesson {_a(t["id"])}, {h(t["status"])}'
           + (f', started {h(_when(t["started_at"]))}' if t["started_at"] else "")
           + (f', in {h(_pct(t["share"]))} of cases' if t["share"] else "") + "</span>",
           f'<p class="line" dir="auto">{h(t["line"])}</p>']
    if t["why"]:
        out.append(f'<p class="meta">{h(t["why"])}</p>')
    for m in t["marks"]:
        out.append(f'<p class="meta">{_mark_text(m)}</p>')
    if t["sides"]:
        for name, words in (("with", "Given the lesson"), ("without", "The old way")):
            side = t["sides"][name]
            if side is None:
                continue
            cases = "; ".join(_case_text(c) for c in side["list"]) or "none"
            out.append(f'<details><summary>{h(words)}: {h(side["cases"])} cases, {h(side["settled"])} settled, '
                       f'{h(side["good"])} good, {h(side["pending"])} pending (from {h(t["sides_from"])})</summary>'
                       f'<p class="cases">{cases}</p></details>')
    out.append("</li>")
    return "\n".join(out)


def _mark_text(m):
    d = m["detail"] if isinstance(m["detail"], dict) else {}
    head = f'{h(m["kind"])} mark {h(m["id"])}, {h(_when(m["at"]))}'
    if m["kind"] == "ping":
        return f'Ping: {head}: row {h(m["row_id"])}, {h(d.get("result"))}. {h(d.get("why"))}'
    if m["kind"] == "verdict":
        chance = f', chance it is better {h(_pct(m["value"]))}' if isinstance(m["value"], (int, float)) else ""
        return f"Verdict: {head}{chance}."
    if m["kind"] == "limit":
        return f'Limit: {head}: worst likely cost {h(m["value"])}, set by {h(m["by"])}.'
    if m["kind"] == "unclear":
        return f'Unclear: {head}: the trial that ended {h(_when(m["value"]))} had too few results to tell.'
    if m["kind"] == "longer":
        return (f'Kept on trial longer: {head}: by {h(m["by"])}, {h(d.get("days"))} days, from '
                f'{h(_when(d.get("from")))} to {h(_when(d.get("to")))}.')
    return f"Pause: {head}."


def _case_text(c):
    """One case of a trial side: how it ended and the rows that settled and gave it, never its id."""
    row = f', settled by row {h(c["row"])}' if c["row"] is not None else ""
    given = f', given in row {h(", ".join(str(g) for g in c["given"]))}' if c["given"] else ""
    return f'{h(c["status"])}{row}{given}'


def _form(token, action, lesson_id, button, *, field=None, hidden=None, quiet=False, form_id=None, cls=None):
    """One small form: the token, the lesson, an optional hidden (name, value), an optional one
    line field, one button. form_id: an id, for a field placed outside it (the why for No);
    cls: a class, for the look of the card's Yes and No."""
    out = [f'<form method="post" action="/{h(action)}"' + (f' class="{h(cls)}"' if cls else "")
           + (f' id="{h(form_id)}"' if form_id else "") + ">",
           f'<input type="hidden" name="token" value="{h(token)}">',
           f'<input type="hidden" name="lesson" value="{h(lesson_id)}">']
    if hidden is not None:
        out.append(f'<input type="hidden" name="{h(hidden[0])}" value="{h(hidden[1])}">')
    if field is not None:
        name, value, hint, required = field
        out.append(f'<input type="text" name="{h(name)}" value="{h(value)}" placeholder="{h(hint)}" '
                   f'maxlength="{MAX_LEN}" dir="auto" aria-label="{h(hint)}"' + (" required" if required else "") + ">")
    out.append(f'<button type="submit"' + (' class="quiet"' if quiet else "") + f">{h(button)}</button></form>")
    return "".join(out)


def _edit_html(token, item):
    return ("<details><summary>Edit</summary>"
            + _form(token, "edit", item["id"], "Save the new line", field=("line", item["text"], "The new line", True))
            + '<p class="meta">The old line is pulled and the new one added, linked to it.</p></details>')


def _a(lesson_id):
    return f'<a href="#l{h(lesson_id)}">{h(lesson_id)}</a>'


# ---- the switches and the fact cards on the page (calls 16, 20 and 10) ----------------------

def locks(agent):
    """The locks that hold whatever the switches say, in plain words, as the page lists them
    under Accept high risk. The Sales agent names its own two checks; another agent's own checks
    are named in general."""
    if agent == SALES.agent:
        out = ["The price check before every reply: a reply with an amount the store data does not have is never sent.",
               "The plain yes lock: no order is placed without the customer's plain yes to its summary."]
        copy = "A lesson that copies a customer's own words from the chats always waits for your yes"
    else:
        out = ["The agent's own checks run on every action, after the lessons."]
        copy = "A lesson that copies words from the cases it came from always waits for your yes"
    return out + ["The auto pause: a trial whose lesson shows about twice the harm pauses itself and waits for you.",
                  f"{copy}, even with Accept high risk on.",
                  "A line close to a pulled one or to one that failed the eval gate, or one that goes against a live one, "
                  "still waits for your yes."]


def _switches_html(a, token):
    """An agent's two switches with who flipped each and when, when Accept high risk ends, the
    locks under it, and every flip. token None: no forms."""
    sw, agent = a["switches"], a["agent"]
    lv, acc = sw["level"], sw["accept"]
    who = (f"switched to {lv['level']} by {lv['by']} on {_when(lv['at'])}" if lv["by"]
           else "careful until a person flips it")
    levels = "; ".join(f"{n}, {_share(x['share'])} for {x['days']} days" for n, x in sw["levels"].items())
    seg = "".join(('<span class="on">' if n == lv["level"] else "<span>")
                  + f'<strong>{h(_cap(n))}</strong>{h(_share(x["share"]))}, {h(x["days"])} days</span>'
                  for n, x in sw["levels"].items())
    out = ['<p class="mh">Trial level</p>', f'<div class="seg" role="img" aria-label="Trial level {h(lv["level"])}">{seg}</div>',
           f'<p class="meta"><span class="line">Trial level: {h(lv["level"])}</span>, {h(_share(lv["share"]))} for '
           f'{h(lv["days"])} days; {h(who)}.</p>',
           f'<p class="meta">New trials take this level ({h(levels)}). A trial keeps the level it started with, so a '
           'flip moves no trial already running. A lesson that waits can take its own level, on its card.</p>']
    if token is not None:
        other = next(n for n in sw["levels"] if n != lv["level"])
        out.append(_agent_form(token, "level", agent, f"Switch to {other}", hidden=(("level", other),)))
    if acc["on"]:
        ends = (f"until {_when(acc['until'])}, then it turns off by itself" if acc["until"] is not None
                else "until a person turns it off")
        state = f"on, turned on by {acc['by']} on {_when(acc['at'])}, {ends}"
    elif acc["ran_out"]:
        state = f"off, its days ran out on {_when(acc['until'])} (turned on by {acc['by']} on {_when(acc['at'])})"
    elif acc["by"]:
        state = f"off, turned off by {acc['by']} on {_when(acc['at'])}"
    else:
        state = "off until a person turns it on"
    on = acc["on"]
    out += [f'<div class="sw-row"><p class="mh">Accept high risk</p><span class="toggle{" on" if on else ""}" role="img" '
            f'aria-label="{"On" if on else "Off"}"></span></div>',
            f'<p class="meta"><span class="line">Accept high risk: {h(state)}</span>.</p>',
            '<p class="meta">While it is on, a high risk lesson goes on trial without your yes, at the trial level, and '
            'it is still watched, studied each night and judged by its verdict. The page names it as started under '
            'Accept high risk, never as your yes.</p>']
    if token is not None and acc["on"]:
        out.append(_agent_form(token, "accept", agent, "Turn off", hidden=(("on", "off"),), quiet=True))
    elif token is not None:
        tick = ('<label><input type="checkbox" name="auto" value="1"> Turn it off by itself after</label>'
                f'<input type="number" name="days" min="1" max="{switches_mod.MOST_DAYS}" step="1" inputmode="numeric" '
                f'aria-label="Days, 1 to {switches_mod.MOST_DAYS}"><span class="meta">days</span>')
        out.append(_agent_form(token, "accept", agent, "Turn on", hidden=(("on", "on"),), extra=tick, wrap=True))
    out.append('<p class="meta">These hold whatever the switches say:</p><ul class="locks">'
               + "".join(f'<li class="meta">{h(x)}</li>' for x in sw["locks"]) + "</ul>")
    if sw["flips"]:
        out.append(f'<details><summary>Every flip, newest first ({h(len(sw["flips"]))})</summary><ul>'
                   + "".join(f'<li class="meta">{h(_flip_text(f))}</li>' for f in sw["flips"]) + "</ul></details>")
    return "\n".join(out)


def _flip_text(f):
    """One switch row in words: who flipped what, and when."""
    when, by = _when(f["at"]), f["by"]
    if f["kind"] == switches_mod.LEVEL:
        return f"{when}: {by} switched the trial level to {f['value']}."
    if f["kind"] == switches_mod.ACCEPT and f["value"] == switches_mod.ON:
        ends = f", to turn off by itself on {_when(f['until'])}" if f["until"] is not None else ", with no end day"
        return f"{when}: {by} turned Accept high risk on{ends}."
    if f["kind"] == switches_mod.ACCEPT:
        return f"{when}: {by} turned Accept high risk off."
    return f"{when}: {by} picked the {f['value']} level for lesson {f['lesson_id']}."


def _level_html(item, token):
    """The level a waiting lesson's trial will take, and a button for the other level for that
    lesson alone. Nothing for a lesson that does not wait."""
    lv = item.get("level")
    if not lv:
        return ""
    if lv["given"]:
        return '<p class="meta">Its share and days were given with its yes, so no level applies to it.</p>'
    whose = f"picked by {lv['by']} on {_when(lv['at'])}" if lv["own"] else "from the trial level switch"
    out = (f'<p class="meta">Its trial will take the {h(lv["level"])} level, {h(_share(lv["share"]))} for '
           f'{h(lv["days"])} days ({h(whose)}). That can change until its trial starts; then the trial keeps it.</p>')
    if token is not None:
        other = next(n for n in plug_mod.LEVEL_NAMES if n != lv["level"])
        out += _form(token, "lesson_level", item["id"], f"Make it {other} for this lesson", hidden=("level", other),
                     quiet=True)
    return out


def _facts_html(view, token):
    """The Facts row: the fact cards with Keep and Dismiss, and the kept facts. With no agent on
    the page that has facts, a calm row that says so."""
    if not view.get("fact_agents"):
        return _pill("facts", "Facts", "No agent here works out facts yet", "None",
                     '<p class="meta">Facts are worked out from an agent\'s own results. No agent on this page has any '
                     'yet.</p>', ident="facts")
    facts = view["facts"]
    body = ['<p class="mh">Facts from the results: keep or dismiss</p>',
            '<p class="meta">Each fact is worked out from results only, with the numbers behind it. Nothing acts on a '
            'fact by itself: Keep saves it with your name and shows it under Kept facts, Dismiss saves your no, and no '
            'agent reads a fact yet.</p>']
    if facts:
        body.append('<div class="facts-list">' + "".join(_fact_html(f, token) for f in facts) + "</div>")
    else:
        body.append(f'<p class="meta">No fact cards now: too few results, or the facts were answered in the last 7 '
                    f'days. The Sales agent\'s delivery days need {h(facts_mod.MIN_RESULTS)} delivered orders for a zone '
                    'in each of the last two weeks.</p>')
    if view["kept_facts"]:
        body.append("<h3>Kept facts</h3><ul>")
        for k in view["kept_facts"]:
            body.append(f'<li class="item"><span class="meta">{h(k["agent"])}, kept by {h(k["by"])} on '
                        f'{h(_when(k["at"]))}</span><p class="line" dir="auto">{h(k["fact"])}</p>'
                        f'<p class="meta">{h(_fact_numbers(k["numbers"]))}</p></li>')
        body.append("</ul>")
    sub = facts[0]["fact"] if facts else ("No new fact cards now" if not view["kept_facts"]
                                          else f'{len(view["kept_facts"])} kept')
    return _pill("facts", "Facts", sub, "New" if facts else "None new", "".join(body), ident="facts")  # no count (item 35)


def _fact_html(f, token):
    out = [f'<div class="sub"><span class="vchip">{h(f["agent"])}, a fact from its results</span>',
           f'<p class="big" dir="auto">{h(f["fact"])}</p>', f'<p class="meta">{h(_fact_numbers(f))}</p>']
    if token is not None:
        hidden = (("key", f["key"]), ("shown", f["shown"]))
        out.append(_agent_form(token, "keep_fact", f["agent"], "Keep", hidden=hidden))
        out.append(_agent_form(token, "dismiss_fact", f["agent"], "Dismiss", hidden=hidden, quiet=True))
    out.append("</div>")
    return "\n".join(out)


def _fact_numbers(n):
    """The numbers behind a delivery days fact, in words; "" when they cannot be read."""
    try:
        t, w = n["this"], n["last"]
        out = (f"This week, the 7 days to {_when(n['until'])}: {t['orders']} orders delivered, usually "
               f"{facts_mod.days_text(t['usual'])} from the order, the fastest {t['fastest']:g}, the slowest "
               f"{t['slowest']:g}. Last week: {w['orders']} orders, usually {facts_mod.days_text(w['usual'])}, the "
               f"fastest {w['fastest']:g}, the slowest {w['slowest']:g}.")
    except (KeyError, TypeError, ValueError):
        return ""
    if n.get("told"):
        out += f" The delivery data tells customers {n['told']} for this zone."
    return out


def _agent_form(token, action, agent, button, *, hidden=(), extra="", quiet=False, wrap=False):
    """One small form for an agent: the token, the agent, hidden (name, value) pairs, extra
    fields (already escaped), one button."""
    out = [f'<form method="post" action="/{h(action)}"' + (' class="wrap"' if wrap else "") + ">",
           f'<input type="hidden" name="token" value="{h(token)}">', f'<input type="hidden" name="agent" value="{h(agent)}">']
    out += [f'<input type="hidden" name="{h(n)}" value="{h(v)}">' for n, v in hidden]
    out.append(extra)
    out.append(f'<button type="submit"' + (' class="quiet"' if quiet else "") + f">{h(button)}</button></form>")
    return "".join(out)


# ---- the server -------------------------------------------------------------------------------

ACTIONS = {"/stop": lambda m, f, now=None: m.stop(_field(f, "lesson"), _field(f, "why"), now=now),
           "/edit": lambda m, f, now=None: m.edit(_field(f, "lesson"), _field(f, "line"), now=now),
           "/yes": lambda m, f, now=None: m.yes(_field(f, "lesson"), _field(f, "shown"), now=now),
           "/no": lambda m, f, now=None: m.no(_field(f, "lesson"), _field(f, "why"), now=now),
           "/back": lambda m, f, now=None: m.bring_back(_field(f, "lesson"), now=now),
           "/longer": lambda m, f, now=None: m.longer(_field(f, "lesson"), _field(f, "days"), now=now),
           "/drop": lambda m, f, now=None: m.drop(_field(f, "lesson"), now=now),
           "/idea": lambda m, f, now=None: m.idea(_field(f, "agent"), _field(f, "line"), _field(f, "stage"), now=now),
           "/level": lambda m, f, now=None: m.set_level(_field(f, "agent"), _field(f, "level"), now=now),
           "/accept": lambda m, f, now=None: m.set_accept(_field(f, "agent"), _field(f, "on"), _field(f, "auto"),
                                                          _field(f, "days"), now=now),
           "/lesson_level": lambda m, f, now=None: m.lesson_level(_field(f, "lesson"), _field(f, "level"), now=now),
           "/keep_fact": lambda m, f, now=None: m.keep_fact(_field(f, "agent"), _field(f, "key"), _field(f, "shown"),
                                                            now=now),
           "/dismiss_fact": lambda m, f, now=None: m.dismiss_fact(_field(f, "agent"), _field(f, "key"),
                                                                  _field(f, "shown"), now=now),
           "/modify": lambda m, f, now=None: m.modify(_field(f, "lesson"), _field(f, "line"),
                                                      _field(f, "note") if "note" in f else "", now=now),
           "/correct": lambda m, f, now=None: m.correct(_field(f, "agent"), _field(f, "line"), now=now),
           "/pause": lambda m, f, now=None: m.pause(_field(f, "agent"), now=now),
           "/resume": lambda m, f, now=None: m.resume(_field(f, "agent"), now=now),
           "/rollback": lambda m, f, now=None: m.roll_back(_field(f, "agent"), _field(f, "code"), now=now),
           "/mode": lambda m, f, now=None: m.answer_mode(_field(f, "agent"), _field(f, "card"), _field(f, "choice"),
                                                         _field(f, "name") if "name" in f else "", now=now)}
# The A3 page's own answers the two tab page never sends: they run no hold and no exam of the two tab kind
# (Modify and the correction box do), so its server does not take them.
A3_ONLY = ("/idea", "/edit")
TWO_TAB_ACTIONS = {k: v for k, v in ACTIONS.items() if k not in A3_ONLY}


def make_server(morning, *, port=int(PORT_DEFAULT), token=None, pages=None):
    """The page's server on 127.0.0.1 (port 0: any free port). Its token is server.token.
    pages: the two tab page (reflection/pages.py, a Pages); None serves the A3 page on / only."""
    token = secrets.token_urlsafe(32) if token is None else token
    server = HTTPServer((HOST, port), _handler(morning, token, pages))
    server.token = token
    return server


def _handler(morning, token, pages=None):
    box = {"flash": None}

    class Handler(BaseHTTPRequestHandler):
        server_version = "morning"
        sys_version = ""
        timeout = 10  # seconds; a client that sends nothing does not hold the page

        def log_message(self, fmt, *args):  # quiet: no request lines on the terminal
            pass

        def _allowed(self, header, scheme=""):
            port = self.server.server_address[1]
            value = (self.headers.get(header) or "").strip().lower()
            return value in {f"{scheme}127.0.0.1:{port}", f"{scheme}localhost:{port}"}

        def _send(self, code, body, *, page=False, location=None, csp=CSP):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8" if page else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")  # no-referrer makes Chrome send Origin null on the page's own POSTs
            self.send_header("Cache-Control", "no-store")
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._allowed("Host"):
                return self._send(403, "Refused: the page answers only on 127.0.0.1 or localhost.\n")
            if pages is not None:
                parts = urllib.parse.urlsplit(self.path)
                flash = box["flash"]
                try:
                    query = urllib.parse.parse_qs(parts.query, max_num_fields=8)
                except ValueError:  # too many fields
                    return self._send(400, "Not a page address.\n")
                got = pages.get(parts.path, query, token, flash)
                if got is None:
                    return self._send(404, "Not found.\n")
                box["flash"] = None
                return self._send(200, got, page=True, csp=pages.csp)
            if urllib.parse.urlsplit(self.path).path != "/":
                return self._send(404, "Not found.\n")
            flash, box["flash"] = box["flash"], None
            self._send(200, render(morning.view(), token=token, flash=flash), page=True)

        def do_POST(self):
            if not self._allowed("Host") or not self._allowed("Origin", "http://"):
                return self._send(403, "Refused: a change comes only from this page on 127.0.0.1 or localhost.\n")
            table = ACTIONS if pages is None else {**TWO_TAB_ACTIONS, **getattr(pages, "actions", {})}  # + Quick start
            act = table.get(urllib.parse.urlsplit(self.path).path)
            if act is None:
                return self._send(404, "Not found.\n")
            try:
                length = int(self.headers.get("Content-Length") or "")
            except ValueError:
                return self._send(411, "A length is needed.\n")
            if not 0 <= length <= MAX_BODY:
                return self._send(413, "Too long.\n")
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/x-www-form-urlencoded"):
                return self._send(415, "A form is needed.\n")
            try:
                form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True,
                                             max_num_fields=8)
            except (UnicodeDecodeError, ValueError):
                return self._send(400, "Not a form.\n")
            given = form.get("token") or [""]
            if len(given) != 1 or not hmac.compare_digest(given[0].encode("utf-8"), token.encode("utf-8")):
                return self._send(403, "Refused: the page's token is missing or wrong. Reload the page.\n")
            try:
                back = pages.back(_field(form, "back")) if pages is not None and "back" in form else "/"
            except Refused:  # more than one back
                return self._send(400, "Not a form.\n")
            m = pages.morning_for(back) if pages is not None else morning  # demo: the throwaway copy of that day
            now = pages.now_for(back) if pages is not None else None  # demo: that day's own clock
            try:
                box["flash"] = act(m, form, now=now)
            except Refused as e:
                box["flash"] = str(e)
            except (ValueError, sqlite3.Error) as e:
                box["flash"] = f"Not done: {e}"
            self._send(303, "Done.\n", location=back)

    return Handler


def write_html(morning, out):
    """The page once as a static file, with no buttons. Returns its path."""
    path = Path(out)
    path.write_text(render(morning.view(), token=None), encoding="utf-8")
    return path


def page_exams(plugs, morning, db=None):
    """The examiners main() gives the page: the Sales agent's (reflection/night.py sales_exam) and each
    built agent's with an exam (night agent_exam, reflection/turn_exam.py), on the page's own lessons and
    the Arena wins next to db or in the agent's folder; none for an agent whose plug names no exam."""
    out = {}
    for p in plugs:
        make = night_mod.agent_exam(p, db)
        if make is not None and p.agent in morning.lessons:
            out[p.agent] = make(morning.lessons[p.agent])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="The morning page: what the engine learned, for every agent.")
    ap.add_argument("--db", default=None, help="the agents' database (default: data/ascent.db)")
    ap.add_argument("--html", metavar="OUT", help="write the page once as a static file with no buttons, and serve nothing")
    ap.add_argument("--demo-days", metavar="DIR", default=None,
                    help="serve the sample days in DIR (day1, day2, day3, from sim/three_days.py), each from a throwaway "
                         "copy; with --db too a Live tab follows them and serves that database")
    ap.add_argument("--assistant-state", default=None,
                    help="the personal assistant's folder a mode card's answer goes to (default: data/assistant)")
    args = ap.parse_args(argv)
    if args.demo_days and args.html:
        print("Not run: --html writes the real page only, not the sample days.", file=sys.stderr)
        return 2
    if args.demo_days and args.db is None:
        return _demo(args.demo_days)
    db_path = str(DEFAULT_PATH) if args.db is None else args.db
    try:
        modes_state = night_mod.assistant_state(args.assistant_state)
    except night_mod.Refused as e:
        print(f"Not run: {e}.", file=sys.stderr)
        return 2
    if not Path(db_path).is_file():
        print(f"Not run: no database at {db_path}. The Sales agent makes it when it first runs.", file=sys.stderr)
        return 2
    plugs = repo_plugs()
    db = Db(db_path)
    try:
        morning = live_morning(db, db_path, plugs, modes_state)
        if args.html:
            print(f"written: {write_html(morning, args.html)}")
            return 0
        env.load()
        morning.exams = page_exams(list(morning.plugs.values()), morning, db_path)  # after env.load(): the model reads its key
        if args.demo_days:
            return _demo(args.demo_days, live=morning)
        try:
            port = int(env.get("MORNING_PORT", PORT_DEFAULT))
        except ValueError:
            print("Not run: MORNING_PORT is not a number.", file=sys.stderr)
            return 2
        from reflection import pages as pages_mod
        server = make_server(morning, port=port, pages=pages_mod.Pages(morning))
        print(f"The morning page: http://127.0.0.1:{server.server_address[1]}/ (Ctrl+C stops it)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        db.close()
    return 0


def live_morning(db, db_path, plugs, modes_state):
    """The Morning on the real database (main's, and the Live tab's next to the sample days)."""
    if any(p.agent == "sales" for p in plugs):  # moves a database made before the engine, as the night does
        from reflection.lessons import Lessons as SalesLessons
        SalesLessons(db)
    other = Path(db_path).resolve() != DEFAULT_PATH.resolve()
    from reflection.judge import Judge  # the live agent's judge (channels/whatsapp.py main); it reads no key until asked
    plugs, built = with_built(plugs, db_path)
    return Morning(db, plugs, reports=Path(db_path).resolve().parent, db_file=db_path if other else None,
                   modes_state=modes_state, judge=Judge(), built=built, db_path=db_path)


def with_built(plugs, db_path):
    """(plugs, built names): the repo's plugs, then the plug of each agent Quick start built next to
    the database (kit/turn.py built, <db folder>/agents/<name>/), so its lessons, its corrections and
    its pause switch are on the page like a repo agent's. A built agent named like a repo agent is left out."""
    from kit import turn as turn_mod
    plugs = list(plugs)
    have = {p.agent for p in plugs}
    built = [a for a in turn_mod.built(Path(db_path).resolve().parent) if a.name not in have]
    return plugs + [a.plug for a in built], [a.name for a in built]


def _demo(folder, live=None):
    """Serve the sample days (sim/three_days.py): each day's folder copied to a throwaway folder,
    so an answer there never touches the sample files; no model call: a correction takes the sample's
    scripted exam (demo_pages).
    live: the Morning on the real database, served on the Live tab with real answers. The .env is read
    so Quick start on New agent finds its model key; the sample days themselves call no model."""
    import tempfile
    env.load()
    with tempfile.TemporaryDirectory(prefix="unfenced-demo-") as tmp:
        try:
            pages, dbs = demo_pages(folder, tmp, live=live)
        except Refused as e:
            print(f"Not run: {e}", file=sys.stderr)
            return 2
        try:
            port = int(env.get("MORNING_PORT", PORT_DEFAULT))
        except ValueError:
            port = int(PORT_DEFAULT)
        server = make_server(pages.morning, port=port, pages=pages)
        first = min(pages.days)
        print(f"Sample days: http://127.0.0.1:{server.server_address[1]}/?day={first}"
              + (" and Live on the same page" if live is not None else "") + " (Ctrl+C stops it)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            for db in dbs:
                db.close()
    return 0


def demo_pages(folder, tmp, live=None):
    """The two tab page over the sample days in folder (day1, day2, ... from sim/three_days.py), each
    copied into tmp first. Each day shows the morning its day.json names (a sample has its own clock).
    live: the Morning on the real database for the Live tab (the caller opens and closes it).
    A correction there takes the scripted exam the sample's own correction took (sim/three_days.py
    examiner, marked a simulated situation, no model call), since a correction never starts untested.
    Returns (Pages, the open sample databases, for the caller to close); Refused when folder has no day."""
    import shutil
    from reflection import pages as pages_mod
    from sim import three_days as sample
    src = Path(folder)
    found = sorted(int(p.name[3:]) for p in src.glob("day[0-9]") if (p / "ascent.db").is_file())
    if not found:
        raise Refused(f"no day1/ascent.db in {folder}. Build them with python3 -I sim/three_days.py {folder}.")
    plugs = repo_plugs()
    dbs, days, at = [], {}, {}
    for d in found:
        dest = Path(tmp) / f"day{d}"
        shutil.copytree(src / f"day{d}", dest)
        db = Db(str(dest / "ascent.db"))
        dbs.append(db)
        days[d] = Morning(db, plugs, reports=dest, db_file=None, modes_state=dest / "assistant",
                          exams={SALES.agent: sample.examiner})
        at[d] = _sample_clock(dest / "day.json")
    return pages_mod.Pages(days=days, at=at, live=live), dbs


def _sample_clock(path):
    """The morning a sample day shows (day.json "at", marked simulated), or None for the real clock."""
    try:
        meta = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if isinstance(meta, dict) and meta.get("simulated") is True and isinstance(meta.get("at"), (int, float)) \
            and not isinstance(meta.get("at"), bool):
        return float(meta["at"])
    return None


# ---- small helpers -----------------------------------------------------------------------------

def _field(form, name):
    values = form.get(name) or [""]
    if len(values) != 1:
        raise Refused(f"One {name}, please.")
    return values[0]


def _ids(text):
    """The lesson ids a card named when the page was drawn, from its form: "3,5", [3, 5]."""
    try:
        return sorted(int(p) for p in (text or "").split(",") if p.strip())
    except ValueError:
        raise Refused("The card's lessons could not be read. Reload the page.") from None


def _days(v):
    """The Keep longer field: a whole number of days from 1 to LONGER_DAYS."""
    if isinstance(v, str) and re.fullmatch(r"\d{1,3}", v.strip()):
        v = int(v.strip())
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= trial_mod.LONGER_DAYS:
        raise Refused(f"Days: a whole number from 1 to {trial_mod.LONGER_DAYS}, please.")
    return v


def _switch_days(v):
    """The days under Accept high risk's check mark: a whole number from 1 to switches.MOST_DAYS."""
    if isinstance(v, str) and re.fullmatch(r"\d{1,3}", v.strip()):
        v = int(v.strip())
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= switches_mod.MOST_DAYS:
        raise Refused(f"Days: a whole number from 1 to {switches_mod.MOST_DAYS}, please.")
    return v


def _level(v):
    if v not in plug_mod.LEVEL_NAMES:
        raise Refused(f"A trial level is {' or '.join(plug_mod.LEVEL_NAMES)}, please.")
    return v


def _share(share):
    """A trial's share in words: "1 in 5 cases", or "80% of cases" when it is not one in a whole number."""
    n = round(1 / share)
    return f"1 in {n} cases" if n > 1 and abs(1 / share - n) < 1e-6 else f"{_pct(share)} of cases"


def _one_line(v, what, *, required=True):
    v = (v or "").strip()
    if "\n" in v or "\r" in v:
        raise Refused(f"{what}: one line, please.")
    if required and not v:
        raise Refused(f"{what}: one line is needed.")
    if len(v) > MAX_LEN:
        raise Refused(f"{what}: at most {MAX_LEN} characters.")
    return v


def _lesson(r):
    d = dict(r)
    d["stages"] = [s for s in (d["stages"] or "").split(",") if s]
    d["fields"] = [s for s in (d["fields"] or "").split(",") if s]
    return d


def _mark(r):
    d = dict(r)
    try:
        d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    except ValueError:
        d["detail"] = None
    return d


def _dicts(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _dict(v):
    return v if isinstance(v, dict) else {}


def _arena_rounds(rows):
    """An Arena item's rounds (arena/run.py reflection_rows), each as one plain line: its gate wins,
    then the Reflection after it (lessons proposed, passed, refused, handed on), whole counts only."""
    def n(v):
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    out = []
    for r in _dicts(rows)[:20]:
        text = f"Round {n(r.get('round'))}: gate {n(r.get('gate_won'))} of {n(r.get('gate_played'))} won"
        got = r.get("reflection")
        if isinstance(got, dict):
            if n(got.get("cases")):
                text += (f"; then Reflection on {n(got.get('cases'))} lost matches: lessons proposed "
                         f"{n(got.get('proposed'))}, passed {n(got.get('passed'))}, refused {n(got.get('refused'))}, "
                         f"handed to the next round {n(got.get('handed'))}")
                if n(got.get("waits_for_yes")):
                    text += f", waiting for a yes {n(got.get('waits_for_yes'))}"
                text += f"; eval gate fixed {n(got.get('fixed'))}, broke {n(got.get('broke'))}"
                if got.get("stopped") == "cap":
                    text += "; stopped at the model call cap"
            else:
                text += "; no lost match to study"
        out.append(text + ".")
    return out


def _until(rep):
    return _num(_dict(rep.get("window")).get("until"))


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _pct(x):
    try:
        n = round(float(x) * 100)
    except (TypeError, ValueError):
        return "?"
    return "over 99%" if n >= 100 and float(x) < 1 else f"{n}%"


def _left(seconds):
    days = seconds / DAY
    if days <= 0:
        return "no days left"
    if days < 1:
        return "under a day left"
    n = round(days)
    return f"about {n} day{'s' if n != 1 else ''} left"


def _cairo(t):
    """A time as a Cairo date, or None for anything that is not a time."""
    t = _num(t)
    if t is None:
        return None
    try:
        return datetime.fromtimestamp(t, CAIRO)
    except (OverflowError, OSError, ValueError):
        return None


def _when(t):
    """A time in Cairo time, as a person reads it: "Fri 30 Oct 2026, 08:00 Cairo"."""
    d = _cairo(t)
    return "an unknown time" if d is None else f"{d:%a} {d.day} {d:%b} {d.year}, {d:%H:%M} Cairo"


def _today(t):
    """The greeting's line: "Fri 30 Oct, 08:00 Cairo"."""
    d = _cairo(t)
    return "An unknown time" if d is None else f"{d:%a} {d.day} {d:%b}, {d:%H:%M} Cairo"


def _date(t):
    """A day in Cairo, with no time: "Fri 13 Nov"."""
    d = _cairo(t)
    return "an unknown day" if d is None else f"{d:%a} {d.day} {d:%b}"


if __name__ == "__main__":
    sys.exit(main())
