"""The lost list of an agent made here (arena/practice.py Practice, review levels r2 items 2 and 4): its
Arena item keeps the last round's lost practice matches a customer could have won, plus a never customer
whose loss failed a safety check, so the tiles, Correct this and Try again never work on a chat that
cannot be won. The three agents of tests/three_agents.json. No model: play and the judge are faked."""
import json
from unittest import mock

from arena import good, practice, run
from tests.test_customers_shape import Base, Writer


class LostList(Base):
    def go(self, name, lose):
        """A run of 20 customers, 10 test, 2 rounds of 10 practice matches; lose(round, card) -> the why
        of a loss, or None for a win."""
        cards = {}

        def play(agent, card, *, seed=0, **kw):
            cards[card["id"]] = card
            return {"card": card["id"], "ended": "done", "turns": [], "round": seed.rsplit("-", 2)[-2]}

        def judge(self, m):
            why = lose(m["round"], cards[m["card"]])
            return {"won": why is None, "why": why or "won", "quote": {"turn": 1, "who": "agent", "text": "x"}}

        with mock.patch.object(practice, "play", play), mock.patch.object(practice.Practice, "_judge", judge):
            rep = practice.practise(self.folders[name], agent_model=None, customer_model=Writer(), judge_model=None,
                                    rounds=2, matches=10, customers=20, gate_size=10)
        saved = json.loads((self.root / rep["item"]["file"]).read_text(encoding="utf-8"))
        return rep, cards, saved

    def test_it_keeps_the_last_rounds_winnable_losses_and_a_never_that_failed_a_check(self):
        for name in self.folders:
            with self.subTest(name=name):
                picked = {}

                def lose(r, card):
                    if r == "r1":
                        return "lost in round 1"
                    if card["unwinnable"]:  # one never customer breaks a never line, the rest just do not buy
                        first = picked.setdefault("never", card["id"])
                        return f"{good.BROKE}: it promised" if card["id"] == first else "it will not buy"
                    winnable = picked.setdefault("win", [])  # the first two it meets lose, the rest win
                    if card["id"] not in winnable and len(winnable) < 2:
                        winnable.append(card["id"])
                    return "not reached" if card["id"] in winnable else None
                rep, cards, saved = self.go(name, lose)
                self.assertEqual(rep["rounds"][0]["training"]["played"], 10)
                self.assertEqual(sorted(x["card"] for x in saved["lost"]), sorted(picked["win"] + [picked["never"]]))
                self.assertFalse(set(x["card"] for x in saved["lost"]) & set(rep["held_out_cards"]))
                self.assertTrue(all(x["why"] != "it will not buy" for x in saved["lost"]))
                self.assertTrue(all(x["why"] != "lost in round 1" for x in saved["lost"]))  # the last round only
                for path in self.folders[name].glob("arena-*"):
                    path.unlink()
                (self.folders[name] / practice.TEST_FILE).unlink()
