import os
import unittest
from unittest import mock

from kit.db import Db
from kit.limits import DAY, Limits, OverLimit
from tests.fake_model import FakeModel, say


class LimitsTest(unittest.TestCase):
    def setUp(self):
        self.db = Db(":memory:")
        self.addCleanup(self.db.close)
        self.now = [5000.0]

    def make(self, **kw):
        return Limits(self.db, clock=lambda: self.now[0], **kw)

    def test_defaults_and_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            lim = self.make()
        self.assertEqual((lim.per_customer, lim.window, lim.daily, lim.customer_daily), (20, 600, 1000, 150))
        env = {"LIMIT_CUSTOMER_CALLS": "5", "LIMIT_CUSTOMER_SECONDS": "60", "LIMIT_DAILY_CALLS": "50",
               "LIMIT_CUSTOMER_DAILY": "7"}
        with mock.patch.dict(os.environ, env, clear=True):
            lim = self.make()
        self.assertEqual((lim.per_customer, lim.window, lim.daily, lim.customer_daily), (5, 60, 50, 7))
        with mock.patch.dict(os.environ, {"LIMIT_CUSTOMER_CALLS": "lots"}, clear=True):
            self.assertEqual(self.make().per_customer, 20)

    def test_twenty_calls_per_ten_minutes(self):
        lim = self.make()
        for _ in range(20):
            lim.take("whatsapp:a")
        self.assertEqual(lim.over("whatsapp:a"), "customer")
        self.assertIsNone(lim.over("whatsapp:b"))
        with self.assertRaises(OverLimit):
            lim.take("whatsapp:a")
        self.now[0] += 601
        self.assertIsNone(lim.over("whatsapp:a"))

    def test_daily_ceiling_counts_everyone(self):
        lim = self.make(daily=3)
        for who in "abc":
            lim.take(who)
        self.assertEqual(lim.over("d"), "daily")
        self.now[0] += DAY + 1
        self.assertIsNone(lim.over("d"))

    def test_one_customer_cannot_use_up_the_daily_ceiling(self):
        lim = self.make(per_customer=2, customer_daily=3)
        lim.take("a")
        lim.take("a")
        self.assertEqual(lim.over("a"), "customer")  # the 10 minute window is checked first
        self.now[0] += 601
        lim.take("a")
        self.assertEqual(lim.over("a"), "customer_daily")
        self.now[0] += 601
        self.assertEqual(lim.over("a"), "customer_daily")
        with self.assertRaises(OverLimit) as cm:
            lim.take("a")
        self.assertEqual(cm.exception.which, "customer_daily")
        self.assertIsNone(lim.over("b"))
        self.now[0] += DAY
        self.assertIsNone(lim.over("a"))

    def test_counts_live_in_sqlite(self):
        self.make(per_customer=1).take("a")
        self.assertEqual(self.make(per_customer=1).over("a"), "customer")

    def test_notice_once_per_window(self):
        lim = self.make()
        self.assertEqual([lim.notice_due("a", "customer") for _ in range(2)], [True, False])
        self.now[0] += 601
        self.assertTrue(lim.notice_due("a", "customer"))
        self.assertTrue(lim.notice_due("b", "daily"))
        self.now[0] += 601
        self.assertFalse(lim.notice_due("b", "daily"))
        self.assertTrue(lim.notice_due("c", "customer_daily"))
        self.now[0] += 601
        self.assertFalse(lim.notice_due("c", "customer_daily"))
        self.now[0] += DAY
        self.assertTrue(lim.notice_due("c", "customer_daily"))

    def test_each_limit_has_its_own_notice(self):
        lim = self.make()
        self.assertTrue(lim.notice_due("a", "customer"))
        self.assertTrue(lim.notice_due("a", "customer_daily"))  # same 10 minutes, a different limit
        self.assertFalse(lim.notice_due("a", "customer_daily"))
        self.assertTrue(lim.notice_due("b", "daily"))
        self.assertTrue(lim.notice_due("b", "customer"))
        self.assertFalse(lim.notice_due("b", "customer"))
        self.now[0] += 601
        self.assertTrue(lim.notice_due("b", "customer"))
        self.assertFalse(lim.notice_due("b", "daily"))

    def test_old_notice_table_is_migrated(self):
        self.db.script("CREATE TABLE limit_notices (customer TEXT PRIMARY KEY, at REAL NOT NULL);"
                       "INSERT INTO limit_notices VALUES ('a', 4990.0);")
        lim = self.make()
        with self.db.tx() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(limit_notices)")]
            pk = [r[1] for r in c.execute("PRAGMA table_info(limit_notices)") if r[5]]
        self.assertEqual(cols, ["customer", "which", "at"])
        self.assertEqual(pk, ["customer", "which"])
        self.assertTrue(lim.notice_due("a", "customer"))
        self.assertTrue(lim.notice_due("a", "daily"))
        self.assertFalse(lim.notice_due("a", "customer"))
        self.make()  # a second start keeps the new table and its rows
        self.assertFalse(lim.notice_due("a", "daily"))

    def test_metered_model_counts_before_calling(self):
        lim = self.make(per_customer=1)
        model = FakeModel(say("hi"), say("never"))
        metered = lim.meter(model, "a")
        metered.chat([])
        with self.assertRaises(OverLimit):
            metered.chat([])
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()
