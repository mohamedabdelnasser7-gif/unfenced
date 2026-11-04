# Red team merge-all round 2
*Created: 2026-11-02. Last updated: 2026-11-02.*

f52819d..465404b, paper only. Verdict PASS, no high or critical. Scripts in the session scratchpad pack review-merge-all.

1. Send check set: ruled out; every card key that maps to an amount tool is in FULL_CHECK_TOOLS. Low: a card connecting nothing gets the house check only (practice and exam only).
2. nights.log: links ruled out. Low, unconfirmed: a FIFO named nights.log blocks os.open (scheduler.py:170, :228). Fix: O_NONBLOCK and fstat S_ISREG, st_nlink 1.
3. names_a_person: low, confirmed: "Label it urgent so a human picks up from here", "Tag it as needs-review and the team joins right away" pass (quickstart.py:188). Fix: invert, the tag exception allows only handle, deal with, see, review.
4. Exam exchange days: low, confirmed (exam.py:238-239): 14 passes anywhere once exchange talk appears, and bare بدل (instead) counts as exchange talk. Fix: allow only in the sentence with the exchange talk; drop bare بدل.
5. Demo lock: low, unconfirmed: held a whole match with no timeout; the page's exam waits behind Build's practice. Fix: acquire with a timeout on the page path.
6. live_hotfixes: ruled out (read only, pulled excluded, dedupe by text).
7. RunNotes losing reply: low, confirmed: lower case or Arabic names pass the guard's name check (engine/fast.py:443-447). Fix: refuse an answer with any word of the card's who.
