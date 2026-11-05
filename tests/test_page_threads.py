"""The page's server answers while a long action runs (reflection/morning.py make_server): a correction's exam,
Train or a page chat turn used to hold the one-thread server, so the Arena's poll and every other tab were
refused until it ended. Actions still run one at a time. No model call, no network."""
import http.client
import threading
import time
import unittest
import urllib.parse

from reflection import morning as mo


class StubPages:
    """The least the handler reads from a Pages: one page and one slow action."""
    csp = mo.CSP

    def __init__(self):
        self.go, self.inside, self.running, self.most = threading.Event(), threading.Event(), 0, 0
        self.lock = threading.Lock()
        self.actions = {"/slow": self.slow}

    def slow(self, m, form, now=None):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        self.inside.set()
        self.go.wait(5)
        with self.lock:
            self.running -= 1
        return "done"

    def get(self, path, query, token, flash):
        return "<p>page</p>" if path == "/today" else None

    def csp_for(self, path):
        return self.csp

    def back(self, value):
        return value

    def morning_for(self, back):
        return None

    def now_for(self, back):
        return None


class PageThreads(unittest.TestCase):
    def setUp(self):
        self.pages = StubPages()
        self.server = mo.make_server(None, port=0, pages=self.pages)
        self.port = self.server.server_address[1]
        self.here = f"127.0.0.1:{self.port}"
        t = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        t.start()
        self.addCleanup(lambda: (self.pages.go.set(), self.server.shutdown(), self.server.server_close(), t.join(5)))

    def get(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.request("GET", "/today", headers={"Host": self.here, "X-Poll": "1"})
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()

    def post(self, out):
        form = urllib.parse.urlencode({"token": self.server.token, "back": "/today"})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/slow", form, {"Host": self.here, "Origin": f"http://{self.here}",
                                                 "Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            r.read()
            out.append(r.status)
        finally:
            conn.close()

    def test_the_page_answers_while_an_action_runs_and_actions_run_one_at_a_time(self):
        done = []
        posts = [threading.Thread(target=self.post, args=(done,)) for _ in range(2)]
        posts[0].start()
        self.assertTrue(self.pages.inside.wait(3))
        posts[1].start()
        for _ in range(5):  # the Arena's poll, every 2 seconds on the real page
            self.assertEqual(self.get(), (200, "<p>page</p>"))
        time.sleep(0.2)
        self.assertEqual(self.pages.running, 1)  # the second action waits for the first
        self.pages.go.set()
        for p in posts:
            p.join(10)
        self.assertEqual(done, [303, 303])
        self.assertEqual(self.pages.most, 1)

    def test_it_is_the_threading_server_with_daemon_threads(self):
        self.assertIsInstance(self.server, mo.ThreadingHTTPServer)
        self.assertTrue(self.server.daemon_threads)


if __name__ == "__main__":
    unittest.main()
