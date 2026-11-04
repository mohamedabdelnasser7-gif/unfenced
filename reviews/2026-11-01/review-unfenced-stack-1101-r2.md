# Review round 2: unfenced, stack fix diff 180d599..d6c4517
*Created: 2026-11-01. Last updated: 2026-11-01.*

Reviewer at max, saved by root from the hand-back. Stopped at 60 tool calls; 25 of 60 mutants run (24 killed, 1 equivalent). Suite 2557 OK. Probes: session scratchpad rvstack2-s1/ (cards.py, builds.py); note PROGRESS-review-stack-r2.md.

Verdict: FIX FIRST (1 medium, 3 low).

Round 1 findings 1, 2, 4, 5, 6 fixed and proven by killed reverts; 3 phrases all refused. Rate-then-lock race ruled out (single thread server, plugs fixed at start, changed line fails closed). WhatsApp full check keeps QuickStartFit and Sales; only untooled prices refused. No slow regex.

1. MEDIUM. reflection/quickstart.py:89-110, 216-219, 452: names_a_person refuses ordinary store lines and the whole card: 5 of 9 realistic cards ("يجاوب على الأسئلة حول المنتجات، وينبه صاحب المحل", "تحويل فودافون كاش على رقم صاحب المحل", "فريقنا بيتابع شحنتك", "transfer to the owner", "our team takes over packing"); also "بيوصل", "سلمى", "Never hand off a chat to a person". Arabic verbs match without word edges. Fix: need a chat, customer or conversation object next to the verb; whole-word Arabic; skip negated lines; add these to NOT_HAND_OFF.
2. LOW. Misses: "Hand the chat to the owner", "Forward the chat to the owner", "Someone from our team will get back to you", "The owner will answer you shortly", "هبعت الشات للمسؤول", Franco ("ha7awlak le wa7ed mn el team").
3. LOW. quickstart.py:380: after 3 presses the refusal says change the card, but only Start over resets it. Fix the wording or reset on a card change.
4. LOW, unconfirmed. quickstart.py:164: BUILD_PROMPT lacks "leave that subject out", so "never pass a chat to a person" instructions get refused and burn a press.
