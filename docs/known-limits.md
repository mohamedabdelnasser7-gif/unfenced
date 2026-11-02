# Known limits
*Created: 2026-10-31. Last updated: 2026-11-02.*

The fact check and the hotfix note check read text our own agent writes. They catch the common ways a wrong price or a customer's name slips into a reply or a note, and every lesson still has to pass the eval gate before it reaches a live agent. These are the shapes they still miss, found in review, and what replaces them next.

## Price check (arena/factcheck.py)
- A wrong boot price can pass when the boot and the add-on are joined by a phrase the check does not list, for example "printed with your name" or "inclusive of".
- "400 EGP more, roughly" and "400 EGP more, or less" still count as an add-on, because the clause ends at the comma.
- A few true lines are refused, for example a boot price followed by "with the name printing" and the add-on price.

Next: every amount in a sentence that names a boot must be that boot's price, an add-on's price or a sum of them. No word lists.

## Send check numbers and script (kit/send_check.py)
The send check is the last gate before a reply reaches the customer. Shapes it still lets through, found in the round 2 and round 3 reviews and red teams:
- A price in k with no store word right before it: "The Elite runs 17k.", "Elite around 17.5k" and "It comes to 17k." The k rule refuses k next to a currency or a price word, and "1.5k" alone passes ("Hoodie 1.5k"); a k right after a product, tier or model number, with or without a sign ("Elite 17.5k", "Phantom 6: 8.5k", "Elite (17.5k)"), is refused.
- A model number then a comma and a blank as wide as a space (plain, no break, ideographic, tab), or a line break, reads as a list: "Vapor 17, 400 EGP" reads 17 and 400, so a store amount after it passes. A carriage return is a line break.
- "Only Superfly 11 in stock." and "Only Vapor 17 available." pass, because "available" and "in stock" after a model number name the boot.
- Counts said without a count shape: "N pieces in 43" alone, "عندنا 3 بس", "3 mawgood bs" (the singular mawgod is "available"), "There are 3 pieces in 43" (there are and has name an order as often as stock), and the plural "remain" before a word outside its short list ("3 remain at the store").
- حبات (pieces) is not read as a count word.
- Franco built only on shop words (tawsil, fel, youm), a doubled digit word ("ba22a") or "el" beside a title word reads as English; so do "w/" and a clock time beside a time word inside Franco ("aywa w/ 16,500 EGP.", "3am and el price is 16,500 EGP."). This touches the script only, never money.
- A few true lines are refused, for example "The Superfly 11 is left-footed friendly." reads as a count, "Nike 2k reviews" reads as a k price.

Next: read every number the customer sees as one number, whatever sits between the digits, and every count as a count, with no word lists.

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

The pool file is written whole and checked on load. Scheduled nights never run at the same moment (reflection/scheduler.py holds one lock), but a night started by hand while a scheduled one runs is not locked against it.

Next: mask any word the store's catalogue and common words do not explain, instead of growing name rules.

## Names in the assistant's practice days (assistant/arena.py)
A finished day the user lived is cleaned before it can join the assistant's Arena. Nothing feeds real days in yet: the live day runner is not built, so this step reads an empty file. Shapes it still misses or over-masks:
- A name only the text carries, with no display name and not on the first name list, for example "lunch with Bahaa Shalaby".
- A single long line right after a sign off is kept.
- A display name made of ordinary capitalised words ("Report Meeting") masks those words for the whole day.

Next: the same allow-list rule as the practice customers, before the live day runner is wired.

## The Arena's own copy (arena/run.py, engine/rounds.py)
The Arena practises on a copy of the database and hands only gate-passed lessons to the live one. Left after review:
- Nothing stops two Arena runs on the same database at once; the second deletes the first run's copy, and both can hand the same lesson live.
- The old copy is removed before the new one is built, so if the live file cannot be read, the remembered failed lessons are lost.
- Any database error on hand over is reported as "live busy".
- A very narrow race, between the copy's file check and its reopen by name, could let a planted link redirect the carry of failed lessons.

Next: a lock held for the whole run, the new copy built under a temporary name and then moved into place, and the carry written through the checked file.

## Late results and the night schedule (reflection/late.py, reflection/scheduler.py)
A result that shows days later, such as a delivery, settles a case only when it arrives: from the courier's webhook, from the courier's API on the night run, or from a person on the Morning page. No timer closes a case, and each agent's night runs by itself once a night. What is left:
- The courier's API cannot see a refusal at the door. Its view says delivered, or returned to the business (saved as refused); a door refusal comes only from the webhook or a person.
- The Sales agent's order rows carry the store's order number and no tracking number, so the API check reaches only orders the courier's webhook already named. Sales late results come from the webhook or a person.
- One case kind per agent. A Sales case is a chat, and its order and delivery are results of that chat; an agent cannot also count each parcel as a case of its own.
- With no webhook, no API answer and no person, a case stays pending. It is never a loss, and a lesson on trial with that case waits for its verdict with no day limit.
- The Morning page lists a waiting case only when it has a row in the last 90 days (LATE_DAYS). An older one still waits, unseen.
- A made reference (c- and ten letters, for a case with no order number) now comes from a key kept in the database, so one already shown changes once; a sheet made with the old one is skipped and named.
- The scheduled night runs only while the WhatsApp server runs. A server that was down at NIGHT_HOUR runs that night once when it is back; older missed nights are not made up.
- A night that is refused (a missing key, no database) or fails is recorded for that agent and night, and is not tried again until the next night.
- Each scheduled night runs in its own process with 5 hours to finish; one still running then is killed and recorded failed (timeout), and that agent's night is not tried again until the next night. The night also ends itself at 5 hours, and at once when the server stops mid night.
- A server that stops mid night leaves that night's record running and its lock behind. After 6 hours (STALE) the record reads stopped and the lock is free; until then no night runs on that database, and the stopped agent's night is not tried again until the next night.

Next: the tracking number saved on the Sales order row when the store ships it, so the API check reaches every order.
