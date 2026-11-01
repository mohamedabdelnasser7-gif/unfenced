"""A scripted model for the persona tags (new, 2026-10-30), with the same chat() shape as
kit.model.Model, so tests and the public demo cards make no model call. It answers from
plain word rules, the way sim/scripted.py answers from each scenario's script, and the same
strict reader (arena/tag.py read_tags) and the same call cap still run on its answers.

The rules, on the cleaned customer turns it is sent:
  worry        the last customer line that holds a worry's words (the recipe's words, its
               worries in order), else the recipe's fallback
  no_budget    a line that says there is no money (مفيش فلوس, مش معايا, can't afford)
  want         name printing on boots (checked first, a printing chat names the boots too),
               football boots, a football kit, or something from the shop, by the words used
  buy_trigger  one fixed line for each worry of the example recipe, else a plain one
  patience     the customer's questions that got another customer line before any answer

PracticePersona and PracticeAgent (2026-11-01): a scripted customer and Sales agent for the small
practice run the three sample days save each night (sim/three_days.py), so that run makes no model
call either. The Arena's own play, verdict and saving code run on their lines.
"""
import copy
import json
import re

NO_MONEY = re.compile(r"(?<!\w)(?:مفيش\s+فلوس|مش\s+معايا|معيش|ماعنديش\s+فلوس|ميزانيتي|can'?t\s+afford|no\s+budget"
                      r"|ma3ish|mafish\s+feloos|msh\s+m3aya)(?!\w)", re.IGNORECASE)
BOOTS = re.compile(r"(?<!\w)(?:جزم[ةه]|الجزم[ةه]|جزم|حذاء|كوتشي|الكوتشي|boots?|shoes|stud|ستاد|ترتان|gazma|el\s?gazma)(?!\w)",
                   re.IGNORECASE)
PRINTING = re.compile(r"(?<!\w)(?:(?:ال)?طباع[ةه]?|(?:ب?[اأتني]|ب)طبع\w*|print(?:ing|ed)?|dtf)(?!\w)", re.IGNORECASE)
KIT = re.compile(r"(?<!\w)(?:طقم|الطقم|تيشيرت|التيشيرت|فانل[ةه]|kit|jersey|t-?shirt|tshirt)(?!\w)", re.IGNORECASE)
TRIGGERS = {"size": "a clear size answer", "price": "a lower price or a bundle",
            "cash on delivery": "paying cash on delivery", "trust": "proof it is original",
            "delivery time": "a firm delivery date", "just browsing": "nothing yet, only looking"}
PLAIN_TRIGGER = "a quick clear answer"


def tags_for(data, recipe):
    """The scripted tags for one request's data ({ended, turns})."""
    turns = data.get("turns") or []
    lines = [t.get("text") or "" for t in turns if t.get("from") == "customer"]
    worry = recipe.fallback
    for line in lines:
        for name in recipe.worries:
            rx = recipe.words.get(name)
            if rx is not None and rx.search(line):
                worry = name
                break
    text = "\n".join(lines)
    want = ("name printing on boots" if PRINTING.search(text) else "football boots" if BOOTS.search(text)
            else "a football kit" if KIT.search(text) else "something from the shop")
    patience = 0
    for a, b in zip(turns, turns[1:]):
        if a.get("from") == "customer" and b.get("from") == "customer" and re.search(r"[?؟]", a.get("text") or ""):
            patience += 1
    return {"want": want, "worry": worry, "buy_trigger": TRIGGERS.get(worry, PLAIN_TRIGGER), "patience": patience,
            "no_budget": bool(NO_MONEY.search(text))}


class ScriptedModel:
    """chat(messages, ...): the scripted tags as the model's JSON answer. calls keeps each request."""
    label = "scripted (no model call)"

    def __init__(self, recipe):
        self.recipe = recipe
        self.calls = []

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        self.calls.append(copy.deepcopy(messages))
        data = json.loads(messages[-1]["content"])
        return {"role": "assistant", "content": json.dumps(tags_for(data, self.recipe))}


class PracticePersona:
    """A scripted made-up customer for a small practice run (sim/three_days.py): one first line about
    its worry, then it leaves. No model call."""
    label = "scripted (no model call)"
    FIRST = {"size": "Are these boots true to size?", "price": "How much are the Vapor boots?",
             "delivery time": "When would the boots reach me?", "cash on delivery": "Can I pay when they arrive?",
             "trust": "Are these boots original?"}

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        if len(messages) > 2:
            return {"role": "assistant", "content": "[leave]"}
        system = messages[0]["content"]
        worry = system.split("Your worry is ", 1)[-1].split(".", 1)[0]
        return {"role": "assistant", "content": self.FIRST.get(worry, "Hi, do you have football boots?")}


class PracticeAgent:
    """A scripted Sales agent for a small practice run (sim/three_days.py) that answers around the
    question, so the customer leaves and the run has lost matches to show. No model call."""
    label = "scripted (no model call)"

    def chat(self, messages, tools=None, effort="medium", max_tokens=1500, whole=False):
        said = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "").casefold()
        if "size" in said:
            return {"role": "assistant", "content": "Which colour would you like?"}
        if "much" in said:
            return {"role": "assistant", "content": "These are one of our most loved boots this season."}
        return {"role": "assistant", "content": "Thanks for writing to us. Which model do you like?"}
