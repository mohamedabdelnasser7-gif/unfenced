"""Modes (new, 2026-10-31): Focused, Rushed and Off by default, and any the user added.

The mode is picked from the user's word first, then from what can be seen: the time against the
user's working hours, a focus block or a meeting on the calendar, and how short and fast the
user's last reply was. The current mode is shown (shown()) and the user can correct it
(correct()). What each mode means for this user is never set here: each reply made in a mode and
how the user answered it go to the engine log as a case (assistant/desk.py answer), and the
night study turns them into lessons tagged with the mode's stage.

A moment that fits no mode is noted (unfit): the user names a mode that does not exist, or says
how they are in words that match none. Night reflection reads the notes to propose a new mode
(assistant/newmode.py).
"""
import re

from assistant import desk as desk_mod

DEFAULT = ("focused", "rushed", "off")
WORDS = {  # the user's word for a mode; matched as whole words, case ignored
    "rushed": ("rush", "rushed", "rushing", "busy", "slammed", "hectic", "no time", "in a hurry", "quick replies",
               "keep it short", "short replies", "swamped"),
    "focused": ("focus", "focused", "focusing", "deep work", "heads down", "do not disturb", "dnd", "concentrating"),
    "off": ("off", "done for today", "signing off", "logging off", "day off", "on leave", "vacation", "holiday",
            "out of office", "offline", "off work"),
}
STATE = re.compile(r"\b(i'm|i am|im|today i|this week i|all day|right now)\b", re.IGNORECASE)
SHORT_WORDS, FAST_MINUTES = 8, 5


def _has(text, phrase):
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.IGNORECASE) is not None


class Modes:
    def __init__(self, start=None, added=()):
        """start: the starting modes from the user picture (assistant/mbox.py starting_modes) or None
        for the defaults. added: the user's own modes, each {"name", "words"}."""
        start = dict(start or {})
        self.work_start = start.get("work_start", "09:00")
        self.work_end = start.get("work_end", "18:00")
        self.short_words = int(start.get("short_reply_words", SHORT_WORDS))
        self.added = [{"name": a["name"], "words": tuple(a.get("words", ()))} for a in added]
        self.current, self.why, self.by = "focused", "the quiet mode until something shows another", "default"
        self.unfit = []

    @property
    def names(self):
        return DEFAULT + tuple(a["name"] for a in self.added)

    def from_words(self, text):
        """The mode the user's words name, or None."""
        text = text or ""
        for a in self.added:
            if _has(text, a["name"]) or any(_has(text, w) for w in a["words"]):
                return a["name"]
        for mode in ("off", "rushed", "focused"):
            if any(_has(text, w) for w in WORDS[mode]):
                return mode
        return None

    def from_signals(self, signals):
        """(mode, why) from what can be seen."""
        s = dict(signals or {})
        now = s.get("time")
        if now and not (desk_mod.minutes(self.work_start) <= desk_mod.minutes(now) < desk_mod.minutes(self.work_end)):
            return "off", "outside working hours"
        if s.get("focus_block"):
            return "focused", "a focus block on the calendar"
        if s.get("in_meeting"):
            return "focused", "in a meeting"
        rw, rm = s.get("reply_words"), s.get("reply_minutes")
        if isinstance(rw, (int, float)) and isinstance(rm, (int, float)) and rw <= self.short_words and rm <= FAST_MINUTES:
            return "rushed", "short, fast replies"
        return None

    def pick(self, signals=None, said=None, at=None, date=None):
        """The mode now. The user's word wins and holds until the user says another or working hours
        end; signals move the mode only when the user has not set it. Words that say how the user is
        but match no mode are noted as a moment that fits no mode."""
        if said:
            named = self.from_words(said)
            if named:
                self.current, self.why, self.by = named, "the user said so", "user"
                return self.current
            if STATE.search(said):
                self.note(said, signals, at=at, date=date)
        seen = self.from_signals(signals)
        if seen and (self.by != "user" or seen[0] == "off"):
            self.current, self.why, self.by = seen[0], seen[1], "signals"
        return self.current

    def shown(self):
        """What the user sees: the mode and why it was picked."""
        return {"mode": self.current, "why": self.why, "by": self.by}

    def correct(self, mode, *, desk=None, said=None, at=None, date=None):
        """The user corrects the mode. A known mode becomes current; the correction goes to the log
        as a case through desk.answer. A name that is no mode is a moment that fits no mode: noted,
        and the mode stays as it was."""
        old = self.current
        if desk is not None:
            desk.answer("corrected", made={"mode": old}, said=said or mode)
        if mode in self.names:
            self.current, self.why, self.by = mode, "the user corrected it", "user"
            if desk is not None:
                desk.mode = mode
        else:
            self.note(said or mode, None, at=at, date=date, named=mode)
        return self.current

    def note(self, said, signals, *, at=None, date=None, named=None):
        moment = {"said": str(said)[:200], "at": at, "date": date, "mode_then": self.current}
        if named:
            moment["named"] = str(named)[:40]
        if signals:
            moment["signals"] = {k: v for k, v in dict(signals).items() if k in
                                 ("time", "reply_words", "reply_minutes", "in_meeting", "focus_block")}
        self.unfit.append(moment)
        return moment
