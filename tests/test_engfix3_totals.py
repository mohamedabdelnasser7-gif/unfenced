"""Arena run 20261104T143545, cause 3: the send check's amounts rule lets a total through when it adds up
amounts the tools gave in this chat (a tier plus its printing, 3 of one item plus the delivery fee), for the
Sales agent, any built agent and the exam; a made-up total still fails. Made-up data only, no network."""
import json
import types
import unittest
from unittest import mock

from kit import send_check, turn
from sales import loop


class FakeChats:
    def __init__(self, steps):
        self._steps = steps

    def steps(self, chat_id):
        return self._steps

    def add_step(self, chat_id, role, **kw):
        return len(self._steps) + 1

    def add_failed_check(self, chat_id, feedback):
        return 99

    def reset_failed_checks(self, chat_id):
        pass

    reset_model_errors = reset_failed_checks


def tool_step(n, name, out):
    return {"n": n, "role": "tool", "name": name, "content": json.dumps(out)}


CHAT = [
    {"n": 1, "role": "user", "name": None, "content": "how much in total"},
    tool_step(2, "store", {"ok": True, "items": [{"title": "Kit", "price": 7500}, {"title": "Printing", "price": 400}]}),
    tool_step(3, "delivery", {"ok": True, "fee": 60, "days_min": 1, "days_max": 2}),
    tool_step(4, "voice_note", {"ok": True, "price": 999}),  # not a tool that gives amounts
]


def amounts_problem(reply, totals, amounts=(7500, 400, 60)):
    return [n for n, _ in send_check.named_problems(reply, "", amounts, totals=totals) if n == "amounts"]


class Totals(unittest.TestCase):
    def test_a_sum_of_tool_amounts_passes(self):
        for reply in ("The total is 7900 EGP.", "With delivery it comes to 7960 EGP.",
                      "Three kits come to 22500 EGP.", "Three kits and delivery: 22560 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(amounts_problem(reply, [7500, 400, 60]), [])

    def test_a_made_up_total_still_fails(self):
        for reply in ("The total is 8000 EGP.", "The total is 7899 EGP.", "Four kits come to 30000 EGP."):
            with self.subTest(reply=reply):
                self.assertEqual(amounts_problem(reply, [7500, 400, 60]), ["amounts"])
        self.assertEqual(amounts_problem("The total is 7900 EGP.", []), ["amounts"])  # no tool gave the parts

    def test_limits(self):
        self.assertTrue(send_check.is_total(10 + 20 + 30 + 40, send_check.sum_parts([10, 20, 30, 40])))
        five = [101, 1003, 10007, 100003, 1000033]
        self.assertFalse(send_check.is_total(sum(five), send_check.sum_parts(five)))  # 5 kinds
        self.assertFalse(send_check.is_total(40, send_check.sum_parts([10])))  # 4 of one
        self.assertFalse(send_check.is_total(10, send_check.sum_parts([10])))  # one amount once is a price
        many = list(range(1000, 1000 + 20 * 7, 7))
        self.assertFalse(send_check.is_total(many[0] + many[1], send_check.sum_parts(many)))  # only the latest 12

    def test_tool_amounts_reads_the_chat(self):
        self.assertEqual(sorted(loop.tool_amounts(FakeChats(CHAT), "c")), [60, 400, 7500])
        with self.assertLogs(loop.log, "ERROR"):
            self.assertEqual(loop.tool_amounts(object(), "c"), [])  # never raises

    def test_a_built_agent_check_gets_the_chat_totals(self):
        agent = types.SimpleNamespace(full_check=True, priced_only=True, stock=False)
        passed, feedback = turn._check(agent, "The total is 7900 EGP.", "", {7500, 400, 60}, frozenset(),
                                       frozenset(), frozenset(), FakeChats(CHAT), "c")
        self.assertTrue(passed, feedback)
        passed, _ = turn._check(agent, "The total is 7905 EGP.", "", {7500, 400, 60}, frozenset(),
                                frozenset(), frozenset(), FakeChats(CHAT), "c")
        self.assertFalse(passed)

    def test_the_sales_answer_gets_the_chat_totals(self):
        chats, sent = FakeChats(CHAT), []
        ctx = types.SimpleNamespace(chat_id="c", chats=chats, stage=types.SimpleNamespace(name="s"))
        t = types.SimpleNamespace(ctx=ctx, customer_text="how much in total", amounts={7500, 400, 60},
                                  lesson_ids=[], tool_steps=0)
        results = types.SimpleNamespace(record=lambda *a, **k: None)
        msg = types.SimpleNamespace(customer_id="u")
        for reply, kind in (("The total is 7900 EGP.", "replied"), ("The total is 7905 EGP.", "no_safe_reply")):
            with self.subTest(reply=reply), mock.patch.object(loop, "_draft", return_value=reply), \
                    mock.patch.object(loop, "_no_safe_reply", return_value=loop.TurnResult("c", "no_safe_reply", None)):
                out = loop._answer(t, [], msg, frozenset(), frozenset(), results=results,
                                   send=lambda to, text: sent.append(text))
                self.assertEqual(out.outcome, kind)
        self.assertEqual(sent, ["The total is 7900 EGP."])


if __name__ == "__main__":
    unittest.main()
