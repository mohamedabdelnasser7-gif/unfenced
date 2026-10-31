# Known limits
*Created: 2026-10-31. Last updated: 2026-11-01.*

The fact check and the hotfix note check read text our own agent writes. They catch the common ways a wrong price or a customer's name slips into a reply or a note, and every lesson still has to pass the eval gate before it reaches a live agent. These are the shapes they still miss, found in review, and what replaces them next.

## Price check (arena/factcheck.py)
- A wrong boot price can pass when the boot and the add-on are joined by a phrase the check does not list, for example "printed with your name" or "inclusive of".
- "400 EGP more, roughly" and "400 EGP more, or less" still count as an add-on, because the clause ends at the comma.
- A few true lines are refused, for example a boot price followed by "with the name printing" and the add-on price.

Next: every amount in a sentence that names a boot must be that boot's price, an add-on's price or a sum of them. No word lists.

## Hotfix note names (engine/fast.py)
- A customer who gives a full name ("Ahmed Hassan") can still have the first name open a note.
- A name the note writes in small letters, in mixed case or in Arabic is not checked against the customer's words.
- Rare hidden characters (combining marks, filler letters) can join or split words past the check.

A hotfix note only reaches the same customer's next chat and expires after it.

Next: a note may use only the agent's own words, the catalogue and common words. Any other word from the customer's text is refused.

## Names in practice customers (arena/clean.py)
Lost real chats are cleaned before they become practice customers: a name a customer gives (my name is, I am, a signature) is masked in every turn of the chat, and so is a surname right beside a masked name. These still pass:
- A surname written alone, with no cue anywhere in the chat.
- A lower case Franco surname beside a name ("Karim eskandar"), because lower case words beside a name stay readable so product words like "black boots" are kept.
- A name that is also an everyday word after a weak cue, for example منى after انا, where منى also reads as "from me".

The pool file is written whole and checked on load, but two night runs at the same moment are not locked against each other.

Next: mask any word the store's catalogue and common words do not explain, instead of growing name rules.
