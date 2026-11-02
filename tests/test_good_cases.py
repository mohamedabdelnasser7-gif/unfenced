"""The practice judge reads a case, not only a chat (arena/good.py; the live cases work, map items B1
to B3): what one case is from the card and the plug, the plug's good result, each turn's tools and
actions, and a case the agent starts with no answer is judged, not lost by code. Made-up agents and
lines; a fake judge, no network."""
import copy
import json
import unittest
from pathlib import Path

from arena import good
from tests import plugs
from tests.fake_model import say

STOCK = json.loads((Path(__file__).resolve().parent / "agents" / "stock_watch" / "plug.json").read_text())
CARD = {"good": "The ticket gets the right answer and the right tag.", "never": ["Never promise a refund."]}
TICKET_CASE = {"input": "one support ticket with its subject and body", "starts": "person",
               "output": "one answer on the ticket and a tag", "ends": "when the ticket is answered and tagged"}


class Judge:
    def __init__(self, answer=None):
        self.answer = answer or {"reached": True, "broke_never": False, "turn": 1, "why": "tagged right"}
        self.asks, self.systems = [], []

    def chat(self, messages, **kw):
        self.systems.append(messages[0]["content"])
        self.asks.append(json.loads(messages[1]["content"]))
        return say(json.dumps(self.answer))


def ticket_plug(test):
    d = copy.deepcopy(STOCK)
    d.update(agent="tickets", case="One support ticket.",
             actions={"reply": "One answer on the ticket.", "tag": "Tag the ticket, for example needs the team."})
    d["results"]["answered"]["about"] = "The ticket was answered and tagged right."
    return plugs.load(d, test)


def turn(n=1, customer="My order came broken.", replies=("Sorry, a new one goes out today.",), tools=(), actions=()):
    return {"n": n, "customer": customer, "replies": list(replies), "tools": list(tools), "actions": list(actions),
            "failed": []}


class WhatTheJudgeReads(unittest.TestCase):
    def test_the_prompt_says_case_and_a_card_with_no_case_is_a_chat(self):
        j = Judge()
        good.judge({"turns": [turn()]}, CARD, j)
        self.assertIn("practice case", j.systems[0])
        self.assertNotIn("chat between", j.systems[0])
        ask = j.asks[0]
        self.assertEqual(ask["case"], good.CHAT_CASE)
        self.assertNotIn("good_result", ask)
        self.assertEqual((ask["good"], ask["never"]), (CARD["good"], CARD["never"]))

    def test_the_cards_case_and_the_plugs_good_result_and_actions(self):
        j = Judge()
        card = dict(CARD, case=TICKET_CASE)
        good.judge({"turns": [turn(tools=["find_order"], actions=["reply", "tag"])]}, card, j, plug=ticket_plug(self))
        ask = j.asks[0]
        self.assertEqual(ask["case"], dict(TICKET_CASE, one_case_is="One support ticket."))
        self.assertEqual(ask["good_result"], {"name": "answered", "about": "The ticket was answered and tagged right."})
        self.assertEqual(ask["actions"]["tag"], "Tag the ticket, for example needs the team.")
        self.assertEqual(ask["played"], [{"turn": 1, "arrived": "My order came broken.",
                                          "agent": ["Sorry, a new one goes out today."], "tools": ["find_order"],
                                          "actions": ["reply", "tag"]}])

    def test_a_case_of_the_wrong_shape_falls_back_to_the_chat_case(self):
        for bad in ("a ticket", {"input": "x"}, dict(TICKET_CASE, starts="robot"), dict(TICKET_CASE, ends="")):
            with self.subTest(case=bad):
                self.assertEqual(good.case_of(dict(CARD, case=bad)), good.CHAT_CASE)
        long = dict(TICKET_CASE, input="word " * 400)
        self.assertLessEqual(len(good.case_of(dict(CARD, case=long))["input"]), good.CASE_LINE)

    def test_odd_tools_and_actions_are_left_out(self):
        j = Judge()
        good.judge({"turns": [turn(tools=["store", 3, None], actions=[{"x": 1}, "tag"])]}, CARD, j)
        self.assertEqual((j.asks[0]["played"][0]["tools"], j.asks[0]["played"][0]["actions"]), (["store"], ["tag"]))


class AgentOutput(unittest.TestCase):
    """B2: lost by code on no agent output, never on a missing person's line."""

    def test_an_agent_first_case_with_no_answer_goes_to_the_judge(self):
        j = Judge({"reached": False, "broke_never": False, "turn": 1, "why": "the lead never answered"})
        v = good.judge({"turns": [turn(customer=None, replies=["Hi, still thinking about the desk?"])]}, CARD, j)
        self.assertEqual(len(j.asks), 1)
        self.assertEqual(j.asks[0]["played"][0]["arrived"], "")
        self.assertEqual(v["why"], f"{good.NOT_REACHED}: the lead never answered")
        self.assertEqual(v["quote"], {"turn": 1, "who": "agent", "text": "Hi, still thinking about the desk?"})

    def test_a_won_agent_first_case_quotes_the_agent(self):
        v = good.judge({"turns": [turn(customer=None, replies=["A post."])]}, CARD, Judge())
        self.assertTrue(v["won"])
        self.assertEqual(v["quote"]["who"], "agent")

    def test_actions_alone_are_output(self):
        j = Judge()
        v = good.judge({"turns": [turn(replies=[], actions=["tag"])]}, CARD, j)
        self.assertEqual((v["won"], len(j.asks)), (True, 1))
        lost = Judge({"reached": False, "broke_never": False, "turn": 1, "why": "wrong tag"})
        v = good.judge({"turns": [turn(replies=[], actions=["tag"])]}, CARD, lost)
        self.assertEqual(v["quote"], {"turn": 1, "who": "agent", "text": "tag"})

    def test_no_output_at_all_is_lost_with_no_model_call(self):
        j = Judge()
        v = good.judge({"turns": [turn(customer=None, replies=[])]}, CARD, j)
        self.assertEqual((v["won"], v["why"], j.asks), (False, good.SILENT, []))
        self.assertEqual(v["quote"], {"turn": 1, "who": "agent", "text": ""})
        self.assertEqual(good.judge({"turns": []}, CARD, j)["why"], good.NO_TURNS)

    def test_a_failed_check_on_an_agent_first_turn_quotes_the_agent(self):
        t = dict(turn(customer=None, replies=[]), failed=[{"check": "send_check", "why": "No emoji."}])
        v = good.judge({"turns": [t]}, CARD, Judge())
        self.assertEqual((v["why"], v["quote"]["who"]), (f"{good.FAILED}: No emoji.", "agent"))


if __name__ == "__main__":
    unittest.main()
