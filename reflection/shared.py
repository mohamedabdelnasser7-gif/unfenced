"""The shared pool: patterns learned across owners (new, 2026-11-04; DECISIONS items 24, 51, 62, 79, 83).

A kept lesson or a lost case of any agent kind becomes one general pattern. The model writes it
(Writer, on Muse Spark Open as the fit check and the adapter are), then code checks that it is
clean (check), leaning strict, since a wrong refusal only drops one pattern: one English sentence
that starts with a listed opener (OPENERS), English letters only (no Arabic script), no capital
letter after its first word, no name of a person, shop, brand, page or place (the listed places,
PLACES, too, in any case), no platform or handle word (PLATFORMS), no word glued to or standing
before a shop word that reads as a shop's name, no digit in any script, no number word in English
or Franco (a lone "one" aside), glued forms included (a ب or b before it, a currency, k, grand,
bucks, quid or percent after it), no amount, price or currency, no Franco word, no phone, email,
link or handle, no quoted words and no run of COPY_RUN words copied from what it was written from
(the lesson's line, the customer's turns), no line that hands a chat to a person, MIN_CHARS to
MAX_CHARS characters and MIN_WORDS to MAX_WORDS words. Every word must be an English word
(english: the bundled list reflection/words_en.xz, built by reflection/make_words.py from
/usr/share/dict/words, Webster's Second International of 1934, in the public domain), or one of the
openers or SAFE words, so a made-up brand, a first name, a misspelled or split number and a word of
another language are refused without being listed one by one; the list holds no capitalised
entry, no first name the cleaner knows and no NUMBERISH word (number words, ordinals, fractions and
money slang). Number words and their sound alikes (won too tree) are folded to digits before the
digit test (_folded). The checks reuse arena/clean.py (names,
phones, emails, links, places and addresses), engine/risk.py (the normal form, links, phones,
handles and the copy runs), kit/send_check.py (currency, spelled amounts, the Franco tens and words)
and reflection/quickstart.py names_a_person. A pattern that fails is dropped, never stored: only a
hash of where it came from is kept, so the same lesson or chat is not written again.

There is one pool per kind across owners, patterns-<kind>.json in the install's shared folder
(root_for: the folder named "shared" beside the agents' database, inside the repo only under
data/), written under a fresh name and moved into place (arena/personas.py _write), under a lock
so two owners' nights never lose each other's patterns. Each pattern keeps which owners it was
seen at as keyed hashes (owner_hash: HMAC with the folder's own random key), never an owner's name
or id. An owner is counted by an id the system writes once into its state folder (owner_id,
OWNER_ID_FILE), never by the name owner.json gives, so a renamed owner stays one owner. A pattern
written at a second owner joins the first when it is near equal: the same kind of pattern (lesson
or lost) and, on their content words (casefolded, marks and small words out), an overlap of at
least SAME. A pattern is shared only once it is seen at MIN_OWNERS (2) distinct owners. An agent
whose owner.json does not name the owner its plug names gives nothing (its folder alone never says
who the owner is, as in arena/grow.py); it still reads the pool. Within one install, whoever can
make owner folders can still make owners; the id only stops one owner counting twice by a new name.
What was given is kept by the lesson's or chat's own id and its database (key_hash, Link db), never
by the owner, so a lesson is written up once whatever id its owner has. A kept lesson the writer
gives no line for never holds back the ones after it: it is kept as missed and asked again another
night, and after a second night with no line it is kept as given (Pool.miss). A lost chat is given
only the night it is added (arena/grow.py). Each pool also keeps, sealed, which owner id each owner
name (owner.json) gave under: a known name with a new id (its owner-id file deleted and made again)
gives nothing until the operator clears that name (clear_owner, or python3 -m reflection.shared
clear-owner --db <the agents' database> <owner name>). The name's next give then puts its new id in
the old one's place on every pattern of that pool, so the owner still counts once.

Where the patterns go, each through the paths siblings already take:
  lessons  engine/study.py step 6 reads the shared lesson patterns of its kind beside its siblings,
           after them, for a new agent's first night and every night of a running one. Each goes
           through the fit check and the adapter like a sibling's kept lesson, and on trial only
           through the agent's eval gate and the Canary; with no gate it waits for a yes. A pattern
           seen at this agent's own owner is not read back. The lesson's source line names the
           pattern and "learned from N owners", which the console shows (reflection/console.py).
  lost     arena/grow.py turns each shared lost pattern into a fresh practice customer for every
           owner's Arena (practice_cards): the card holds the pattern and nothing else of any
           chat, so one owner's practice customers never cross (item 51 holds).
"""
import contextlib
import fcntl
import functools
import hashlib
import hmac
import json
import lzma
import os
import re
import secrets
import time
from pathlib import Path

from arena import clean as clean_mod
from arena import paths
from engine import risk as risk_mod
from engine.plug import AGENT_NAME
from engine.study import SMALL_WORDS
from kit import send_check
from reflection import study as parts

LESSON, LOST = "lesson", "lost"
WHATS = (LESSON, LOST)
MIN_OWNERS = 2       # a pattern is shared only once seen at this many distinct owners (item 83)
SAME = 0.6           # the content word overlap at which two owners' patterns are one
MIN_SAME_WORDS = 3   # fewer content words than this: only the very same words are one pattern
MIN_CHARS, MAX_CHARS = 20, 240
MIN_WORDS, MAX_WORDS = 4, 40
MAX_PATTERNS = 500   # per kind; the oldest seen at one owner only go first
MAX_OWNERS = 1000    # owner hashes a pattern keeps
MAX_KEYS = 20_000    # hashes of where patterns came from
MAX_CARDS = 20       # fresh practice customers from shared lost patterns, most owners first
GIVE = 5             # kept lessons a night may send to the writer
GIVE_LOST = 5        # lost chats a night may send to the writer
POOL_FILE = "patterns-{kind}.json"
KEY_FILE = "owner-key"
OWNER_ID_FILE = "owner-id"  # in an owner's state folder: the id the pool counts it by
SHARED_DIR = "shared"
POOL_AGENT = "shared_pool"  # the name the study's notes and links give the pool
MAX_FILE = 32_000_000  # MAX_PATTERNS rows of MAX_OWNERS sealed owners (48 hex) and MAX_KEYS keys fit
HASH = re.compile(r"[0-9a-f]{32}")
SEALED = re.compile(r"([0-9a-f]{32})([0-9a-f]{16})")  # an owner in the file: its hash, then its seal
NAMED = re.compile(r"([0-9a-f]{32})([0-9a-f]{32})([0-9a-f]{16})")  # an owner name, its owner, the seal
BROKEN = ("the pool file could not be read, or none of its patterns was sealed by the shared folder's key, or the "
          "English word list could not be read")
HELD = "the owner's id changed since its name last gave; nothing is given until the operator clears the name"
PID = re.compile(r"[0-9a-f]{12}")
LABEL = re.compile(r"[a-z]+(?: [a-z]+){0,3}")


class Refused(ValueError):
    pass


# ---- the clean check

_EXTRA_MONEY = (r"dollars?|usd|\$|€|euros?|riyals?|sar|aed|dirhams?|ريال|ريالات|دولار|دولارات|درهم|يورو"
                r"|dolar|dollar|riyal|dirham")
CURRENCY = re.compile(r"(?<![^\W\d_])(?:" + send_check.CURRENCY + "|" + _EXTRA_MONEY + r")(?![^\W\d_])",
                      re.IGNORECASE)
MAGNITUDE = re.compile(r"(?<![^\W\d_])" + send_check.MAGNITUDE_WORDS + r"(?![^\W\d_])", re.IGNORECASE)
QUOTES = re.compile("[\"“”„‟«»‹›〝〞「」『』]|(?<![^\\W\\d_])['‘’]|['‘’](?![^\\W\\d_])")
CAPITAL = re.compile(r"[A-Z]")
LINE_BREAK = re.compile(r"[\r\n  ]")
BRACKET = re.compile(r"\[[^\]]*\]")


# English only: the writer is asked for one English sentence
NOT_ENGLISH = re.compile(r"[^\W\d_]")
# the first word of the one sentence a pattern is: an advice line (When, If, Offer, Ask) or how a
# customer behaves (Customers, The customer, Asks); anything else, a shop's name first, is refused
OPENERS = frozenset("""
when whenever if once after before while as until unless even during instead rather only for with without
on in at during throughout from
a an the this that these those such each every any some most many few several all both either neither
customers customer buyers buyer shoppers shopper clients client people someone anyone visitors visitor
users user readers reader callers caller guests guest newcomers returning repeat new first hesitant quiet
students student members member followers follower patients patient subscribers subscriber tenants tenant
learners learner parents parent fans fan viewers viewer diners diner travellers traveller travelers traveler
passengers passenger donors donor attendees attendee applicants applicant candidates candidate residents
resident renters renter tourists tourist listeners listener players player athletes athlete trainees
trainee leads prospects prospect owners owner audiences audience everyone anybody somebody nobody
unsure busy price agents agent replies reply messages message questions question they it there
offer ask tell say share give show suggest explain answer respond confirm check keep let avoid never always
do don try mention remind thank greet follow wait stay use repeat admit apologise apologize acknowledge
treat listen lead start end close stop help point note agree recommend describe clarify reassure send list
compare match mirror be make put move focus slow hold skip drop add include open invite welcome accept
frame highlight raise ease steer guide nudge prompt read look find pick choose bring return restate
summarise summarize prefer expect double name
asks says goes leaves wants compares hesitates writes returns comes doubts worries pushes questions stops
expects needs insists waits refuses disappears ignores sends replies complains haggles negotiates delays
postpones cancels changes keeps repeats tests checks rejects mentions seems sounds starts opens requests
demands prefers likes browses looks shows threatens gets loses drops walks tends usually often sometimes
rarely mostly gives answers argues trusts distrusts follows reads hears sees thinks feels believes
""".split())
# English and Franco number words (the Franco tens are kit/send_check.py FRANCO_TENS), whole words
# only, glued forms included; "one" alone is a word ("no one", "the one"), so only "one" beside
# another digit word counts
_EN_NUM = (r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen"
           r"|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fourty|fifty|sixty|seventy|eighty|ninety"
           r"|hundreds?|thousands?|millions?|billions?|dozens?|half|halves|nil|nought|naught")
_FR_UNIT = (r"wa[h7]?[ei]d|wa[h7]?da|we[h7]da|[ei]?th?n[ae]?[ei]{1,2}n|tnein|tneen|th?alath?a|ta?lata?h?|talat"
            r"|arba[a3]?[ah]?|khamsa?h?|khamas|5amsa|s[ei]tt?a|sab[a3]a?h?|tamany?[ae]?h?|tamnya|taman|tamaneya"
            r"|t[ei]s[a3]a?|3?ashr?a|3?ashar|nos|noss|tolt|tult")
_FR_TEEN = (r"(?:h[ei]da?|[ei]?tn|talat|tal[a]?t|arba[a3]?|arbaat|khamas|khams|s[ei]tt?|saba[a3]?|sabaat|taman"
            r"|t[ei]sa[a3]?|t[ei]saat)t?ashar")
_FR_HUNDRED = (r"(?:t[ou]lt|talat|rob[3]?|arba[a3]?|kh?oms|kh?ams|5oms|5ams|sot|sett?|sob[3]?|sab[3]?|tomn|taman|tos[3]?"
               r"|tes[3]?)?[aeiou]?(?:m[iey]{1,2}y?a|m[iey]{1,2}t[ae]?[iey]{1,2}n|m[iy]t|myt)")
_FR_THOUSAND = (r"(?:talat|tlat|arba[a3]?|arbaat|khamas|khamast|khams|s[ei]tt|sab[a3]?|sabaat|taman|tes[a3]?|tesaat"
                r"|ashar|3ashar)?t?(?:alaf|aalaf|alf|elf|alfein|alfeen|talaf|tlaf)|mal[ae]?y[ou]{1,2}n|milyon|melyon"
                r"|malayeen")
_FR_NUM = rf"(?:{_FR_UNIT}|{_FR_TEEN}|{send_check.FRANCO_TENS}|{_FR_HUNDRED}|{_FR_THOUSAND})"
_MONEY_TAIL = (r"geneh|genih|gneh|gnih|ginih|gnyh|gineh|gineeh|geneeh|ginee|gnieh|guineh|pounds?|egp|le|dollars?|usd"
               r"|euros?|riyals?|sar|aed|dirhams?|bucks?|quid|k|grand|percent|pct")
MONEY_WORD = re.compile(rf"(?:{_MONEY_TAIL}|percentage|cents?|piasters?|pt|pence)")
NUMBER_TOKEN = re.compile(rf"(?:(?:{_EN_NUM})+(?:and)?)*(?:{_EN_NUM})(?P<en_money>{_MONEY_TAIL})?"
                          rf"|(?:b|be|bi|bel|bil|w|we|wel|el|il|l|le|lel)?(?:{_FR_NUM})+(?P<fr_money>{_MONEY_TAIL})?")
DIGIT_WORDS = frozenset("zero oh o one two three four five six seven eight nine double triple nil nought".split())
# Franco words a customer writes (kit/send_check.py FRANCO_WORDS, the ones that are English words too
# aside) and more of them: unquoted, they are still the customer's words
FRANCO = (frozenset(send_check.FRANCO_WORDS) - send_check.ENGLISH_TOO) | frozenset("""
ghali ghaly ghalya ghalia rekhees rkhis rakhis mafeesh mafish mafesh yalla habibi habibti akhi basha ostaz ustaz
tayeb tayyeb mashy mashi maashy inshallah insha allah wallahi walahi wallah shokran shukran afwan sabah masa
kheir khair lessa lesa kwayes kwayyes helw helwa gamed gamda zbon zabon zboon zobon zbayen felous fulus flous
se3r ezzay keda kda bardo bardu tab3an aked akeed sa7 ma3lesh maalesh maalish hader hadr
""".split())
# platforms, apps and handles: a pattern names none
PLATFORMS = frozenset("""
instagram insta ig gmail hotmail yahoo outlook icloud whatsapp watsapp whats wa facebook fb messenger tiktok
snapchat telegram twitter youtube linkedin pinterest jumia amazon shopify talabat careem uber vodafone
etisalat fawry instapay paypal valu souq olx dubizzle bosta aramex dhl fedex google username usernames
hashtag hashtags dm dms handle handles snap tele
""".split()) - {"handle"}  # "handle" is a verb too (handle the doubt); the shapes after a platform word catch the rest
# places the cleaner (arena/clean.py) leaves, in any case
PLACES = frozenset("""
zamalek dokki mohandessin mohandeseen mohandesin agouza imbaba shubra shoubra abbasiya abbassia abbasia helwan
mokattam moqattam katameya kattameya rehab madinaty shorouk sherouk obour maadi heliopolis tagamo tagamoa
sahel gouna hurghada sharm dahab sokhna alamein ismailia suez mansoura tanta zagazig fayoum faiyum minya
assiut asyut sohag luxor aswan damietta cairo giza alex alexandria egypt egyptian egyptians masr maser
eskendereya iskandariya saudi riyadh jeddah jedda dammam mecca makkah medina madinah dubai sharjah ajman
emirates emirati uae ksa qatar doha kuwait bahrain manama oman muscat jordan amman lebanon beirut iraq
baghdad morocco casablanca tunisia tunis algeria libya sudan khartoum yemen syria damascus palestine gaza
gcc nasr zayed sheikh
""".split())
# shop words: a word glued to one (zorvexstore) or standing right before one (zorvex sports) reads as
# a shop's, brand's or page's name, unless it is an English word listed here
SHOP_TAIL = re.compile(r"(?P<stem>[a-z]{3,})(?:stores?|shops?|official|online|eg|egypt|wear|sports?|fashion"
                       r"|boutique|mall|outlet|brands?|co|inc|ltd|llc|group|market|mart)")
GLUED_OK = frozenset("""
bookstore bookstores drugstore drugstores superstore megastore workshop workshops barbershop coffeeshop
sportswear footwear outerwear menswear womenswear underwear swimwear sleepwear activewear eyewear knitwear
streetwear loungewear nightwear rainwear beachwear partywear kidswear babywear transport transports passport
passports motorsport motorsports watersports supermarket supermarkets hypermarket aftermarket upmarket
downmarket subgroup subgroups firebrand disco tobacco fiasco fresco alfresco nutmeg
""".split())
SHOP_NOUNS = frozenset("""
store stores shop shops brand brands boutique boutiques sports wear fashion outlet outlets mall malls page pages
account accounts company group market official
""".split())
SHOP_BEFORE_OK = frozenset("""
the a an this that these those our your their its his her my same other another any every each no one online
local physical main official new old big small large nearest nearby own rival competing competitor sports sport
clothing clothes shoe shoes fashion retail web app chat of at from to in on into and or whole entire which what
real actual store brand social media business product products checkout home order orders landing contact
payment details size sizes help policy returns return shipping delivery faq price prices pricing catalogue
catalog menu cart outdoor team water winter summer casual formal evening kids men women baby everyday daily
grocery electronics furniture beauty gift flagship partner trusted favourite favorite usual right wrong first
last next previous single only such shared customer customers buyer buyers seller sellers department
convenience corner discount premium luxury cheap cheaper expensive popular known unknown original fake genuine
authorised authorized licensed profile review reviews rating ratings user personal family who they we you i
""".split())


# number words, ordinals, fractions and money slang: never English words to the word list
# (reflection/make_words.py leaves them out), whatever else they mean ("one" stays: see _numbers)
_NUMBERISH = """
zero two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen
eighteen nineteen twenty thirty forty fourty fifty sixty seventy eighty ninety hundred thousand million billion
trillion lakh crore second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth
fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth thirtieth fortieth fiftieth
sixtieth seventieth eightieth ninetieth hundredth thousandth millionth billionth half halve halved halving
quarter quartered thrice twain dozen score fiver tenner grand quid buck pence penny cent couple pair nil
nought naught zilch triple quadruple tenfold hundredfold twofold threefold
"""
NUMBERISH = frozenset(w for b in _NUMBERISH.split() for w in (b, b + "s", b + "es")) | {"halves", "pennies"}
# the letters of the alphabet spelled out: never English words to the word list either (make_words.py
# leaves them out too), so a short brand or handle spelled in them (dee jay, em tee) is refused
LETTER_NAMES = frozenset("""
bee cee dee ee ef eff gee aitch haitch jay kay el ell em en pee cue kew ar ess tee vee ex wye zee zed
""".split())
WORDS_FILE = Path(__file__).with_name("words_en.xz")
# common English words that are also first names the cleaner knows (arena/words.py): kept
NAME_WORDS = frozenset("body may mark said shady sandy".split())
# words a plain pattern may use that the 1934 list does not hold, and the glued shop words it knows
SAFE = frozenset("""
email emails online offline app apps website websites webpage login logins logout signup checkout inbox ok
okay emoji emojis chatbot chatbots bot bots smartphone laptop wifi password passwords upload uploads download
downloads voicemail promo promos restock restocked preorder preorders followup refundable unsubscribe faq
screenshot screenshots blog blogs influencer influencers livestream reschedule rescheduled rebook onboarding
workout workouts skincare haircut sneakers hoodies feedback reorder subscription subscriptions prioritize
customize personalize
""".split()) | GLUED_OK
# and the common words the 1934 list misses (review crossowner round 3, item 2): modern words, the
# irregular forms its endings cannot reach, and British spellings its UK rules cannot; no name of a
# brand, a person or a place
SAFE = SAFE | frozenset("""
timeline upsell upsize upsold underperform outsold undersold resold cardio warmup cooldown physio carb carbs
podcast webinar vlog selfie wishlist bestseller backorder cashback chargeback payout paywall freebie reboot
uninstall roadmap workflow troubleshoot bootcamp burnout mindset wellbeing lifestyle weeknight earbud earbuds
smartwatch touchscreen takeaway takeout meetup ebook ecommerce autoreply meme rewatch copywriting upcycle vegan
playlist haircare makeover hairstyle telehealth walkthrough rideshare carpool babysitter daycare homeschool
dropoff timeslot anytime anymore info intro pricey customization personalization offboarding
paid prepaid repaid overpaid held began became befell blew awoken woken forgave forgiven foresaw foreseen forsook
mislaid misspelt overcame overdid overran oversaw overslept overtook overtaken overthrew outgrew outdid rewrote
rewritten undergone undertaken withdrew women feet knives scarves selves box boxes fax
practise programme jewellery licence fibre kerb kerbside fulfil fulfilment offence pretence storey sceptical
paediatric paediatrician orthopaedic orthopaedics anaesthetic oestrogen manoeuvre moustache tonne postcode
""".split())
CONTRACTIONS = frozenset("""
don't doesn't didn't isn't aren't wasn't weren't won't wouldn't shouldn't couldn't can't haven't hasn't
hadn't mustn't needn't it's they're you're we're they've you've we've i'm i've i'll i'd they'll you'll we'll
it'll he's she's let's that's there's what's who's here's
""".split())
_ENDS = (("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"), ("ily", "y"), ("es", ""), ("s", ""),
         ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""), ("ing", "e"), ("er", ""), ("er", "e"), ("est", ""),
         ("est", "e"), ("ly", ""), ("bly", "ble"), ("ness", ""), ("ment", ""), ("ful", ""), ("less", ""))
_UK = (("isation", "ization"), ("ise", "ize"), ("yse", "yze"), ("tre", "ter"), ("our", "or"), ("ogue", "og"))
# number words and the words that sound like them, as the digits they stand for (_folded)
SOUNDS = {"zero": 0, "oh": 0, "o": 0, "nil": 0, "nought": 0, "naught": 0, "one": 1, "won": 1, "wun": 1,
          "two": 2, "too": 2, "to": 2, "tu": 2, "tew": 2, "three": 3, "tree": 3, "thre": 3, "four": 4,
          "for": 4, "fore": 4, "fo": 4, "five": 5, "fife": 5, "fiv": 5, "six": 6, "sicks": 6, "siks": 6,
          "seven": 7, "sevn": 7, "eight": 8, "ate": 8, "ait": 8, "eit": 8, "nine": 9, "nein": 9, "nyne": 9,
          "nain": 9}
WEAK_SOUNDS = frozenset({"one", "to", "for"})  # plain words alone: count only in a run with strong ones
# a digit wherever they stand: no plain word, or one a pattern has no need of (review crossowner round 3)
ALWAYS_SOUNDS = frozenset({"fife", "sicks", "siks", "fiv", "sevn", "nein", "nyne", "wun", "tew", "thre",
                           "ate", "ait", "tree", "won", "oh", "fore", "nain"})
STRONG_ANYWHERE = 3  # this many strong sound alikes (not WEAK_SOUNDS) anywhere in a line are a number
TOKEN = re.compile(r"[a-z]+(?:['’-][a-z]+)*")


_READ = {}  # the word list as last read, with the file's inode, size and change time


def english():
    """The bundled English words (WORDS_FILE), less the first names the cleaner knows (but NAME_WORDS),
    NUMBERISH and LETTER_NAMES. A list that cannot be read is empty, so every word outside the openers and SAFE
    is refused, and the pool reads as broken (Pool.ready, Pool.add). The list is kept as read only
    while the file is the same one: a file moved away, put back or mended is read again."""
    try:
        st = WORDS_FILE.stat()
    except OSError:
        return frozenset()
    at = (st.st_ino, st.st_size, st.st_mtime_ns)
    if _READ.get("at") == at:
        return _READ["words"]
    try:
        raw = lzma.decompress(WORDS_FILE.read_bytes()).decode("ascii")
    except (OSError, lzma.LZMAError, UnicodeDecodeError):
        raw = ""
    out, prev = set(), ""
    for line in raw.split("\n"):
        if not line or line.startswith("#") or not line[0].isdigit():
            continue
        prev = prev[:int(line[0])] + line[1:]
        out.add(prev)
    words = frozenset(out - (first_names() - NAME_WORDS) - NUMBERISH - LETTER_NAMES) if out else frozenset()
    _READ.update(at=at, words=words)  # an empty list stays only while this same file is there
    return words


@functools.lru_cache(maxsize=1)
def first_names():
    from arena import words as name_words
    return frozenset(w for w in name_words.FIRST | name_words.CUE if w.isascii() and w.isalpha())


@functools.lru_cache(maxsize=1)
def governorates():
    """The Latin spellings of the governorates (demo/governorates.json, as arena/clean.py reads it),
    each as a tuple of its words."""
    try:
        data = json.loads(clean_mod.GOVERNORATES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(tuple(t) for g in data.get("governorates", []) for s in g.get("spellings", [])
                     if (t := re.findall(r"[a-z]+", s.casefold())) and s.isascii())


def _bases(w):
    """The forms a word may be listed under: itself, a few endings off, British spellings as American."""
    out = {w}
    for end, back in _ENDS:
        if w.endswith(end) and len(w) - len(end) >= 2:
            b = w[:-len(end)] + back
            out.add(b)
            if end in ("ed", "ing", "er", "est") and not back and len(b) >= 3 and b[-1] == b[-2]:
                out.add(b[:-1])  # stopped, bigger
    for b in list(out):
        for uk, us in _UK:
            if uk in b:
                out.add(b.replace(uk, us, 1))
    return out


def _english_word(w):
    w = w.replace("’", "'")
    if w in CONTRACTIONS:
        return True
    if w.endswith("'s"):
        w = w[:-2]
    if "'" in w:
        return False
    if "-" in w:
        return _english_word(w.replace("-", "")) or all(_english_word(p) for p in w.split("-"))
    if w in NUMBERISH or w in first_names() and w not in NAME_WORDS:
        return False
    if w in ("a", "i") or w in OPENERS or w in SAFE:
        return True
    words_en = english()
    return any(b in words_en or b in SAFE for b in _bases(w))


def _not_english(plain):
    """The words of a line that are not English words (_english_word), casefolded."""
    return [w for w in TOKEN.findall(plain.casefold()) if not _english_word(w)]


def _folded(toks):
    """The line's words with number words and their sound alikes as digits: a run of three or more
    of them with at least two that are not plain words alone (one, to, for), STRONG_ANYWHERE strong
    ones anywhere in the line, a sound alike in ALWAYS_SOUNDS (fife, won, tree), and double or triple
    before one. The first part of a contraction (won in won't, split by _tokens) is no sound alike.
    Any digit in it is a number."""
    out, i, n = list(toks), 0, len(toks)
    sound = [t in SOUNDS and not (k + 1 < n and toks[k + 1] == "t" and f"{t}'t" in CONTRACTIONS)
             for k, t in enumerate(toks)]
    while i < n:
        j = i
        while j < n and sound[j]:
            j += 1
        run = toks[i:j]
        strong = [t for t in run if t not in WEAK_SOUNDS]
        if len(run) >= 3 and len(strong) >= 2:
            out[i:j] = [str(SOUNDS[t]) for t in run]
        i = max(j, i + 1)
    strong_at = [k for k, t in enumerate(toks) if sound[k] and t not in WEAK_SOUNDS]
    for k, t in enumerate(toks):
        if sound[k] and (t in ALWAYS_SOUNDS or len(strong_at) >= STRONG_ANYWHERE and k in strong_at):
            out[k] = str(SOUNDS[t])
        if t in ("double", "triple") and k + 1 < n and sound[k + 1] and toks[k + 1] not in WEAK_SOUNDS:
            out[k + 1] = str(SOUNDS[toks[k + 1]]) * (2 if t == "double" else 3)
    return " ".join(out)


def _governorate(toks):
    n = len(toks)
    return any(tuple(toks[i:i + len(g)]) == g for g in governorates() for i in range(n - len(g) + 1))


def _tokens(text):
    """The words of a line as the number, place and shop tests read them: look alikes as letters,
    casefolded, apostrophes splitting (don't is don, t)."""
    return re.findall(r"[a-z]+", risk_mod.normalize(text, letters=True).casefold())


def _numbers(toks):
    """(money, number): a number word glued to money or a money word (fifty bucks, khamsingeneh, five
    k), and any number word at all (see NUMBER_TOKEN)."""
    money = number = False
    for i, t in enumerate(toks):
        if MONEY_WORD.fullmatch(t):
            money = True
        m = NUMBER_TOKEN.fullmatch(t)
        if not m:
            continue
        if t == "one" and not ({toks[i - 1] if i else "", toks[i + 1] if i + 1 < len(toks) else ""} & DIGIT_WORDS):
            continue
        number = True
        money = money or bool(m.group("en_money") or m.group("fr_money"))
    return money, number


def _shop_like(toks):
    """A word that reads as a shop's, brand's or page's name: glued to a shop word, or right before one
    and not an English word that goes there (see SHOP_TAIL)."""
    for i, t in enumerate(toks):
        if t not in GLUED_OK and SHOP_TAIL.fullmatch(t):
            return True
        if i and t in SHOP_NOUNS and toks[i - 1] not in SHOP_BEFORE_OK and toks[i - 1] not in SHOP_NOUNS:
            return True
    return False


def check(text, sources=()):
    """Why the pattern is not clean, as plain reasons; [] when it is. sources: the texts it was
    written from (the lesson's line, the customer's turns); a run of risk.COPY_RUN words from one is
    quoted words."""
    if not isinstance(text, str) or not text.strip():
        return ["not a line"]
    out = []
    plain = clean_mod.normalize(text).strip()  # NFKC, hidden marks out, Eastern digits as 0 to 9
    norm = risk_mod.normalize(text)    # every numeral sign as a digit, look alikes as letters
    words = re.findall(r"[^\W_]+", plain)
    toks = _tokens(text)
    if not MIN_CHARS <= len(text.strip()) <= MAX_CHARS or not MIN_WORDS <= len(words) <= MAX_WORDS:
        out.append(f"length: {MIN_CHARS} to {MAX_CHARS} characters and {MIN_WORDS} to {MAX_WORDS} words")
    if LINE_BREAK.search(text):
        out.append("more than one line")
    if send_check.ARABIC.search(text) or send_check.ARABIC.search(plain):
        out.append("Arabic script: a pattern is written in English")
    elif any(not ("a" <= ch.casefold() <= "z") for ch in NOT_ENGLISH.findall(plain)):
        out.append("letters other than English")
    body = re.sub(r"[.!?]\s*$", "", plain)
    if re.search(r"[.!?;:]", body):
        out.append("more than one sentence")
    first = re.match(r"[A-Za-z]+", body)
    if first is None or first.group(0).casefold() not in OPENERS:
        out.append("does not start with a listed opener")
    if any(ch.isdigit() for ch in text) or re.search(r"\d", norm) or re.search(r"\d", plain):
        out.append("a digit")
    # a word split by a mark (gen-eh, fif'ty) is read joined too
    joined = [re.sub(r"['’-]", "", w) for w in TOKEN.findall(plain.casefold()) if re.search(r"['’-]", w)]
    money, number = _numbers(toks + joined)
    if money or "%" in plain or any(rx.search(t) for rx in (CURRENCY, send_check.SPELLED_AMOUNT)
                                    for t in (plain, norm)):
        out.append("a currency or an amount")
    elif any(MAGNITUDE.search(t) for t in (plain, norm)):
        out.append("an amount in words")
    elif number or re.search(r"\d", _folded(toks)):
        out.append("a number in words")
    if any(t in FRANCO for t in toks + joined):
        out.append("a Franco word: the customer's own words")
    if any(t in PLATFORMS for t in toks):
        out.append("a platform or handle word")
    if any(t in PLACES for t in toks) or _governorate(toks):
        out.append("a place")
    if any(w in first_names() and w not in NAME_WORDS for w in TOKEN.findall(plain.casefold())):
        out.append("a first name")
    if _not_english(plain):
        out.append("a word not in the English word list")
    if _shop_like(toks):
        out.append("a shop, brand or page name")
    if QUOTES.search(plain):
        out.append("quoted words")
    if BRACKET.search(plain):
        out.append("a masked word")
    cleaned = clean_mod.clean(plain)
    masked = sorted(set(clean_mod.PLACEHOLDER.findall(cleaned)) - set(clean_mod.PLACEHOLDER.findall(plain)))
    if masked:
        out.append("a name, phone, email, link, place or address (" + ", ".join(masked) + ")")
    if any(rx.search(norm) for _, rx in risk_mod.CORE):
        out.append("a link, phone or handle")
    if _proper(plain):
        out.append("a capitalised name")
    if sources:
        mine = risk_mod._runs(text)
        if any(mine & risk_mod._runs(s) for s in sources if isinstance(s, str)):
            out.append("quoted words: a run of words copied from what it was written from")
    from reflection.quickstart import names_a_person  # late: quickstart imports much of the repo
    if names_a_person(plain):
        out.append("hands a chat to a person")
    return out


def _proper(text):
    """A Latin word with a capital letter that is not the first word (a name, a shop, a place, a
    brand), or a capital inside a word; I alone is a word, not a name."""
    for n, m in enumerate(re.finditer(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text)):
        w = m.group(0)
        if not CAPITAL.search(w) or w in ("I", "I'm", "I’m"):
            continue
        if CAPITAL.search(w[1:]) or n:
            return True
    return False


# ---- near equal patterns

_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})


def _stem(w):
    if w.startswith("ال") and len(w) > 4:
        w = w[2:]
    for end in ("ing", "ed", "es", "ly", "s"):
        if w.endswith(end) and len(w) - len(end) >= 4:
            return w[:-len(end)]
    return w


# words that turn a pattern around (negation, order, how often, more or less): they stay content
# words, and two patterns that differ in one are never one (review crossowner round 1, item 4)
_POLAR = frozenset("""
not no never nor without cannot don doesn didn isn aren wasn weren won wouldn shouldn nothing none neither
before after until first last then next once again earlier later early late sooner
always often ever sometimes rarely seldom usually twice only
more most less least fewer
""".split())
POLAR = frozenset(_stem(w) for w in _POLAR)


def words(text):
    """The pattern's content words: casefolded, marks out, Arabic letter forms joined, small words
    (but not the POLAR ones) and one letter words out, a few endings off; a sorted list."""
    plain = risk_mod.normalize(text, letters=True).translate(_FOLD)
    return sorted({_stem(w) for w in re.findall(r"[^\W\d_]+", plain)
                   if len(w) > 1 and (w not in SMALL_WORDS or w in _POLAR)})


def same(a, b):
    """Two patterns' content words (words) are one pattern: the very same words, or both at least
    MIN_SAME_WORDS long with an overlap (shared over all) of at least SAME, and no POLAR word in one
    only."""
    a, b = set(a), set(b)
    if not a or not b or (a ^ b) & POLAR:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < MIN_SAME_WORDS:
        return False
    return len(a & b) / len(a | b) >= SAME


# ---- the pool

def root_for(db_path):
    """The install's shared folder: "shared" beside the agents' database."""
    return Path(db_path).expanduser().resolve().parent / SHARED_DIR


def check_root(root):
    root = Path(root).expanduser()
    if root.is_symlink():
        raise Refused("the shared folder is a link")
    root = root.resolve()
    if paths.inside_repo(root) and not paths.within(root, paths.DATA):
        raise Refused("the shared folder sits inside the repo outside data/")
    return root


class Pool:
    """One kind's patterns across owners. Read on open; add() takes the lock, reads again, adds and
    writes."""

    def __init__(self, kind, root):
        if not isinstance(kind, str) or not AGENT_NAME.fullmatch(kind):
            raise Refused("a kind is lowercase letters, digits and _, starting with a letter")
        self.kind, self.root = kind, check_root(root)
        self.path = self.root / POOL_FILE.format(kind=kind)
        self._key, self._holding = None, False
        self._read()

    # the owner key and the hashes

    def _secret(self, make=True):
        if self._key is not None:
            return self._key
        path = self.root / KEY_FILE
        if path.is_symlink():
            raise Refused("the shared folder's key is a link")
        if not path.exists():
            if not make:
                return None
            from arena.personas import _write
            os.makedirs(self.root, mode=0o700, exist_ok=True)
            with contextlib.nullcontext() if self._holding else self._locked():
                if not path.exists():
                    _write(path, secrets.token_hex(32).encode("ascii"))
        raw = path.read_bytes()[:200].strip()
        if not re.fullmatch(rb"[0-9a-f]{64}", raw):
            raise Refused("the shared folder's key is out of shape")
        self._key = bytes.fromhex(raw.decode("ascii"))
        return self._key

    def owner_hash(self, owner):
        """The owner as the pool keeps it: a keyed hash, never the name or id itself."""
        if not isinstance(owner, str) or not owner:
            raise Refused("an owner is a name")
        return hmac.new(self._secret(), b"owner\x00" + owner.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def seal(self, p, oh):
        """The 16 hex the file keeps after an owner's hash: a keyed hash over the pattern (kind, id,
        what, text, worry) and that owner, so an owner added or moved by hand to another pattern,
        or a pattern's words changed, fails on the next read."""
        raw = "\x00".join([self.kind, p["id"], p["what"], p["text"], p.get("worry") or "", oh]).encode("utf-8")
        return hmac.new(self._secret(), b"seal\x00" + raw, hashlib.sha256).hexdigest()[:16]

    def key_hash(self, key):
        """Where a pattern came from (a lesson's or a chat's own id in the install's database, the same
        whichever owner id gave it), as a keyed hash."""
        return hmac.new(self._secret(), b"from\x00" + key.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def name_hash(self, name):
        return hmac.new(self._secret(), b"name\x00" + name.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def name_seal(self, nh, oh, what=b"named"):
        """The seal of an owner name and the owner hash it gave under (what: b"named"), or the hash it
        gave under before the operator cleared it (b"cleared")."""
        raw = "\x00".join([self.kind, nh, oh]).encode("utf-8")
        return hmac.new(self._secret(), what + b"\x00" + raw, hashlib.sha256).hexdigest()[:16]

    def held(self, name, owner):
        """True when the owner name gave before under another owner id (see the module lines)."""
        if not name:
            return False
        nh = self.name_hash(name)
        return nh in self.names and self.names[nh] != self.owner_hash(owner)

    # reading and writing

    def _read(self):
        data, failed = {}, False
        if self.path.is_symlink():
            raise Refused("the pool file is a link")
        if self.path.exists():  # there but oversize, unreadable or out of shape: a broken read
            try:
                failed = not self.path.is_file() or self.path.stat().st_size > MAX_FILE
                data = {} if failed else json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, RecursionError):
                data, failed = {}, True
            if not isinstance(data, dict) or not isinstance(data.get("patterns", []), list):
                data, failed = {}, True
        if data.get("kind", self.kind) != self.kind:
            raise Refused("the pool file is for another kind of agent")
        raw = data.get("patterns") or []
        rows = [p for p in raw[:MAX_PATTERNS] if _pattern_ok(p)]
        # rows but none of them good (an older file format, or rows the clean check now refuses), no
        # key, or a key none of them was sealed with (a new key after the old was lost): the read is
        # broken, and add() writes nothing rather than wipe the pool. The raw rows count, not the good
        key = self._secret(make=False)
        self.patterns = [p for p in (self._unsealed(p) for p in rows) if p is not None] if key else []
        self.broken = failed or bool(raw) and not self.patterns
        for p in self.patterns:
            p["words"] = words(p["text"])
        keys = data.get("keys")
        self.keys = [k for k in keys if isinstance(k, str) and HASH.fullmatch(k)][-MAX_KEYS:] \
            if isinstance(keys, list) else []
        missed = data.get("missed")  # the writer gave no line for these once (miss)
        self.missed = [k for k in missed if isinstance(k, str) and HASH.fullmatch(k)][-MAX_KEYS:] \
            if isinstance(missed, list) else []
        named = data.get("names")
        named = [m for m in (NAMED.fullmatch(n) for n in named[:MAX_KEYS] if isinstance(n, str)) if m] \
            if isinstance(named, list) else []
        self.names = {m.group(1): m.group(2) for m in named
                      if key and hmac.compare_digest(m.group(3), self.name_seal(m.group(1), m.group(2)))}
        # the owner hash a cleared name gave under before: its next add() puts the new one in its place
        was = data.get("cleared")
        was = [m for m in (NAMED.fullmatch(n) for n in was[:MAX_KEYS] if isinstance(n, str)) if m] \
            if isinstance(was, list) else []
        self.cleared = {m.group(1): m.group(2) for m in was if key and hmac.compare_digest(
            m.group(3), self.name_seal(m.group(1), m.group(2), b"cleared"))}
        self.broken = self.broken or bool(named) and not self.names or bool(was) and not self.cleared

    def _unsealed(self, p):
        """The row with its owners as hashes, or None when any owner's seal fails (_pattern_ok has
        already refused an owner written twice)."""
        owners = []
        for o in p["owners"]:
            m = SEALED.fullmatch(o)
            if not hmac.compare_digest(m.group(2), self.seal(p, m.group(1))):
                return None
            owners.append(m.group(1))
        return dict(p, owners=owners)

    @contextlib.contextmanager
    def _locked(self):
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        fd = os.open(self.root / f".patterns-{self.kind}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._holding = True  # a key made under it does not take the lock again
            yield
        finally:
            self._holding = False
            os.close(fd)

    def _save(self):
        from arena.personas import _write
        os.makedirs(self.root, mode=0o700, exist_ok=True)
        if not self.root.is_symlink():
            os.chmod(self.root, 0o700)
        kept = [dict({k: p[k] for k in ("id", "what", "text", "worry", "at")},
                     owners=[oh + self.seal(p, oh) for oh in p["owners"]]) for p in self.patterns]
        names = [nh + oh + self.name_seal(nh, oh) for nh, oh in self.names.items()]
        was = [nh + oh + self.name_seal(nh, oh, b"cleared") for nh, oh in self.cleared.items()]
        _write(self.path, json.dumps({"kind": self.kind, "patterns": kept, "keys": self.keys[-MAX_KEYS:],
                                      "missed": self.missed[-MAX_KEYS:], "names": names[-MAX_KEYS:],
                                      "cleared": was[-MAX_KEYS:]}, ensure_ascii=False).encode("utf-8"))

    def given(self, key):
        """True when this lesson or chat (its own id in the install's database) was written up before,
        kept or dropped, by any owner id."""
        return self.key_hash(key) in self.keys

    def ready(self, key, owner, name=None):
        """Read under the lock before the writer is asked: BROKEN, "given before" or HELD when this
        owner's lesson or chat is not to be written up, None when it is. Makes no key."""
        with self._locked():
            self._read()
            if self.broken or not english():  # no word list: every line would be refused
                return BROKEN
            if self._secret(make=False) is None:  # a fresh pool: nothing given, no name known
                return None
            if self.given(key):
                return "given before"
            if self.held(name, owner):
                return HELD
        return None

    def miss(self, key):
        """The writer gave no line for this lesson or chat: the first time it is kept as missed, so it
        is asked again another night (the study asks each lesson once a night); the second time it is
        kept as given and never asked again. True when it is now kept as given."""
        with self._locked():
            self._read()
            if self.broken:
                raise Refused(BROKEN + "; nothing is written")
            kh = self.key_hash(key)
            if kh in self.keys:
                return True
            gone = kh in self.missed
            if gone:
                self.missed.remove(kh)
                self.keys.append(kh)
            else:
                self.missed.append(kh)
            self._save()
            return gone

    def clear(self, name):
        """The operator's step after an owner's id was made again: the name may give under its new id.
        The hash it gave under before is kept (cleared), so its next add() puts the new hash in its
        place on every pattern and one owner never counts as two."""
        with self._locked():
            self._read()
            if self.broken:
                raise Refused("the pool file could not be read; nothing is written")
            if self._secret(make=False) is None:
                return False
            nh = self.name_hash(name)
            old = self.names.pop(nh, None)
            if old is not None:
                self.cleared[nh] = old
                self._save()
                return True
        return False

    def add(self, what, text, owner, key, *, worry=None, sources=(), now=None, name=None):
        """One owner's pattern into the pool: (the pattern, []) when it was added or joined a near
        equal one, (None, reasons) when the clean check dropped it. Either way only a hash of the
        owner and of where it came from is written; a dropped pattern's words never are. name: the
        owner's name (owner.json); one that gave under another owner id gives nothing (HELD)."""
        if what not in WHATS:
            raise Refused("a pattern is a lesson or a lost case")
        reasons = check(text, sources)
        worry = _label(worry) if what == LOST else None
        if worry and check(f"The customer worries about the {worry} here."):
            worry = None
        with self._locked():
            self._read()  # read under the lock before any key is made: a broken pool makes none
            if self.broken or not english():
                raise Refused(BROKEN + "; nothing is written")
            oh, kh = self.owner_hash(owner), self.key_hash(key)
            if name:
                if self.held(name, owner):
                    return None, [HELD]
                nh = self.name_hash(name)
                self.names[nh] = oh
                old = self.cleared.pop(nh, None)
                if old is not None and old != oh:  # the same owner under its new id: one owner
                    for p in self.patterns:
                        if old in p["owners"]:  # in the old hash's place, never twice
                            p["owners"] = [oh if x == old else x for x in p["owners"] if x != oh]
            if kh not in self.keys:
                self.keys.append(kh)
            if kh in self.missed:
                self.missed.remove(kh)
            if reasons:
                self._save()
                return None, reasons
            text = " ".join(text.split())
            mine = words(text)
            best, score = None, -1.0
            for p in self.patterns:
                if p["what"] != what or not same(mine, p["words"]):
                    continue
                a, b = set(mine), set(p["words"])
                s = len(a & b) / len(a | b)
                if s > score:
                    best, score = p, s
            if best is None:
                pid = hashlib.sha256(f"{what}\x00{text}".encode("utf-8")).hexdigest()[:12]
                best = next((p for p in self.patterns if p["id"] == pid), None)
            if best is None:
                best = {"id": pid, "what": what, "text": text, "worry": worry, "owners": [],
                        "at": float(time.time() if now is None else now), "words": mine}
                self.patterns.append(best)
            if oh not in best["owners"] and len(best["owners"]) < MAX_OWNERS:
                best["owners"].append(oh)
            if len(self.patterns) > MAX_PATTERNS:  # the oldest seen at one owner only go first
                lone = [p for p in self.patterns if len(p["owners"]) < MIN_OWNERS and p is not best]
                drop = {id(p) for p in lone[:len(self.patterns) - MAX_PATTERNS]}
                self.patterns = [p for p in self.patterns if id(p) not in drop][-MAX_PATTERNS:]
            self._save()
            return dict(best), []

    def shared(self, what, but=None):
        """The patterns of this kind (lesson or lost) seen at MIN_OWNERS or more distinct owners, most
        owners first. but: an owner whose own patterns are left out (an agent never reads back what
        its own owner gave)."""
        if not self.patterns:  # nothing to read: no key is made for it
            return []
        mine = self.owner_hash(but) if but else None
        out = [p for p in self.patterns if p["what"] == what and len(set(p["owners"])) >= MIN_OWNERS
               and (mine is None or mine not in p["owners"])]
        return sorted(out, key=lambda p: (-len(set(p["owners"])), p["at"], p["id"]))


def _pattern_ok(p):
    """A pattern as add() writes it, its text clean by check() again (a hand edited file gains
    nothing), its owners sealed hashes (Pool._unsealed checks each seal against the key)."""
    return (isinstance(p, dict) and isinstance(p.get("id"), str) and PID.fullmatch(p["id"])
            and p.get("what") in WHATS and isinstance(p.get("text"), str) and not check(p["text"])
            and (p.get("worry") is None or isinstance(p["worry"], str) and LABEL.fullmatch(p["worry"]))
            and isinstance(p.get("owners"), list) and 0 < len(p["owners"]) <= MAX_OWNERS
            and all(isinstance(o, str) and SEALED.fullmatch(o) for o in p["owners"])
            and len(set(p["owners"])) == len(p["owners"])
            and isinstance(p.get("at"), (int, float)) and not isinstance(p["at"], bool))


def _label(v):
    """A worry as a short plain label (arena/madeup.py: a few lower case words), else None."""
    v = " ".join(v.casefold().split()) if isinstance(v, str) else ""
    return v if LABEL.fullmatch(v) else None


# ---- the writer

PROMPT = """You turn one {what} of a {kind} agent into one general pattern that an agent of the same
kind at another business could learn from. {about}
Write one plain sentence in common English words that starts with When, If, Offer, Ask, Customers or Asks. Never
write a name of a person, a shop, a brand, a page, an app or a place, a number in digits or words, a
price, an amount or a currency, a phone number, an email or a link, and never quote anyone's words or
use the customer's own words. Say what happens or what to do, in general terms.
Answer with JSON only: {{"pattern": "the sentence"}}"""
ABOUT = {LESSON: "The data holds the lesson the agent kept after its trial.",
         LOST: "The data holds a practice chat the agent lost, cleaned, and the customer's worry; write how "
               "this kind of customer behaves, so a practice customer can play it."}


class Writer(parts._Part):
    """writer(what, kind, data): the pattern line, or None for anything odd. check() decides if it
    is kept."""

    def __call__(self, what, kind, data):
        said = self.ask(PROMPT.format(what="kept lesson" if what == LESSON else "lost case", kind=kind,
                                      about=ABOUT[what]), data)
        got = parts.read_json(said)
        line = got.get("pattern") if isinstance(got, dict) else None
        return line.strip() if isinstance(line, str) and line.strip() else None


# ---- the link the night study and the night's practice step read

def owner_id(folder):
    """The owner of an agent's folder as the pool counts it: a random id the system writes once into
    the owner's state folder (OWNER_ID_FILE beside owner.json, arena/grow.py owner_of), never the name
    owner.json gives, so renaming an owner, or naming one owner two ways in its plugs, stays one owner.
    "" when owner.json names no owner for this agent (it then gives nothing)."""
    from arena import grow  # late: grow reads this module inside its night
    if folder is None:
        return ""
    home, plug = grow.owner_of(folder), grow._plug_at(folder)
    name = grow.owner_name(home)
    if name is None or plug is None or plug.owner != name:
        return ""
    path = home / OWNER_ID_FILE
    if path.is_symlink():
        raise Refused("the owner's id file is a link")
    if not path.exists():
        tmp = home / f".{OWNER_ID_FILE}.{secrets.token_hex(8)}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, secrets.token_hex(16).encode("ascii"))
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)  # the first night's id wins; a second night at once reads it
        except FileExistsError:
            pass
        finally:
            os.unlink(tmp)
    raw = path.read_bytes()[:100].strip()
    if not HASH.fullmatch(raw.decode("ascii", "replace")):
        raise Refused("the owner's id file is out of shape")
    return "owner-id:" + raw.decode("ascii")


class Link:
    """One agent's way into its kind's pool. owner: the owner's id (owner_id), or "" (gives nothing).
    writer: Writer or a test's stand in. give, give_lost: the writer's calls a night at most. A give
    whose writer raised, or whose pool reads broken or refused it, says failed, and the night then
    asks the writer nothing more. A writer that gives no line is not failed: the night goes on to the
    next lesson or chat, and a lesson is asked again another night, once (Pool.miss). The pool is
    read before the writer is asked."""

    def __init__(self, kind, owner, writer, root, give=GIVE, give_lost=GIVE_LOST, name=None, db=None):
        self.kind, self.owner, self.writer, self.name = kind, owner or "", writer, name or None
        # the database the lesson and chat ids are of: two databases beside one shared folder never
        # share an id
        self.db = str(Path(db).expanduser().resolve()) if db is not None and str(db) != ":memory:" else ""
        self.root, self.give, self.give_lost = root, int(give), int(give_lost)
        self._pool = None

    @classmethod
    def for_agent(cls, plug, folder, writer, root, **kw):
        """The link of the agent whose plug sits in folder: its kind, and its owner's id (owner_id)
        and name when owner.json names the owner its plug names, else no owner. db (in kw): the
        agents' database its lesson and chat ids are of."""
        oid = owner_id(folder)
        name = None
        if oid:
            from arena import grow  # late, as in owner_id
            name = grow.owner_name(grow.owner_of(folder))
        return cls(getattr(plug, "kind", "") or plug.agent, oid, writer, root, name=name, **kw)

    @property
    def pool(self):
        if self._pool is None:
            self._pool = Pool(self.kind, self.root)
        return self._pool

    def lessons(self):
        """The shared lesson patterns this agent may take: [{id, text, owners}] (owners: how many)."""
        pool = self.pool
        pool._read()  # what other owners' nights added since this link opened it
        return [{"id": p["id"], "text": p["text"], "owners": len(set(p["owners"]))}
                for p in pool.shared(LESSON, but=self.owner or None)]

    def source(self, pid, owners):
        """The source line a lesson taken from pattern pid carries (the console reads owners off it)."""
        return source_line(self.kind, pid, owners)

    @staticmethod
    def pattern_of(source):
        """The pattern a lesson's source line names, or None for a lesson not from the pool."""
        return pattern_in(source)

    def _give(self, what, key, data, sources, worry=None):
        if not self.owner:
            return {"pattern": None, "why": "this agent names no owner, so it gives nothing"}
        why = self.pool.ready(key, self.owner, self.name)
        if why == BROKEN:  # counted as failed: nothing more is asked of the writer tonight
            return {"pattern": None, "why": why, "failed": True}
        if why:
            return {"pattern": None, "why": why}
        try:
            line = self.writer(what, self.kind, data)
        except Exception as e:  # a failing writer gives nothing tonight; asked again another night
            return {"pattern": None, "why": f"the writer failed ({type(e).__name__})", "asked": True, "failed": True}
        if not line:  # no line (nothing, or not the JSON asked for): the night goes on (Pool.miss)
            try:
                done = self.pool.miss(key)
            except Refused as e:  # broken since it was read: failed
                return {"pattern": None, "why": f"the pool refused it ({e})", "asked": True, "failed": True}
            return {"pattern": None, "asked": True,
                    "why": "the writer gave no line" + ("; not asked again" if done else "; asked again another night")}
        try:
            got, reasons = self.pool.add(what, line, self.owner, key, worry=worry, sources=sources, name=self.name)
        except Refused as e:  # broken since it was read: failed, as above
            return {"pattern": None, "why": f"the pool refused it ({e})", "asked": True, "failed": True}
        if got is None:
            return {"pattern": None, "why": "dropped: " + "; ".join(reasons), "asked": True}
        return {"pattern": got["id"], "owners": len(set(got["owners"])), "why": None, "asked": True}

    def give_lesson(self, agent, lesson):
        """One kept lesson ({id, text}) of this owner's agent into the pool, once: kept by the lesson's
        own id in the install's database, whichever agent or owner id gives it."""
        return self._give(LESSON, f"{self.db}\x00lesson:{lesson['id']}", {"lesson": lesson["text"]},
                          [lesson["text"]])

    def give_chat(self, chat_key, turns, worry):
        """One lost chat, already cleaned (arena/grow.py), into the pool, once. Its customer turns are
        the copy check's sources."""
        said = [t.get("text", "") for t in turns if isinstance(t, dict) and isinstance(t.get("text"), str)]
        return self._give(LOST, f"{self.db}\x00chat:{chat_key}", {"lost case": turns, "worry": _label(worry) or "other"},
                          said, worry=worry)


def left_out(e):
    """The note a night gives when the shared pool could not be opened for an agent (a Refused
    says why in plain words; an OSError by its kind only, never a path)."""
    why = str(e) if isinstance(e, Refused) else type(e).__name__
    return f"the shared pool was left out tonight ({why})"


def practice_cards(kind, root, but=None):
    """Fresh practice customers from the shared lost patterns of this kind, for any owner's Arena:
    at most MAX_CARDS, most owners first. but: the Arena's own owner id (owner_id), whose own
    patterns are left out, as an agent's lessons are (an owner never practises on what it gave). A card holds the pattern as how the customer behaves and
    nothing of any chat (no want, example or line), training only (a grown- id, arena/grow.py decks)."""
    if root is None:
        return []
    try:
        pool = Pool(kind, root)
        lost = pool.shared(LOST, but=but)[:MAX_CARDS]
    except (Refused, OSError):  # a folder or key that cannot be read gives no card
        return []
    out = []
    for p in lost:
        arabic = bool(send_check.ARABIC.search(p["text"]))
        out.append({"id": f"grown-shared-{p['id']}", "worry": p["text"], "unwinnable": False,
                    "why_unwinnable": None, "want": [], "buy_trigger": [], "patience": {"median": 3.0, "most": 4},
                    "style": {"length": {"short": 1.0}, "language": {"arabic" if arabic else "english": 1.0},
                              "voice_notes": 0.0, "opening": {"greeting": 1.0}},
                    "chats": 1, "won": 0, "lost": 0, "examples": [], "arena_weight": 1.0,
                    "shared": {"owners": len(set(p["owners"])), "worry": p["worry"]}})
    return out


# read only at the start of a source, where the study writes it (adapted <fit> from the <line>: "...");
# the same words quoted inside another lesson's source are not a lesson from the pool
SOURCE = re.compile(r"(?:adapted [a-z]+ from the )?shared pool of [a-z][a-z0-9_]* agents, pattern ([0-9a-f]{12}), "
                    r"learned from (\d+) owners(?=:|$)")


def source_line(kind, pid, owners):
    return f"shared pool of {kind} agents, pattern {pid}, learned from {int(owners)} owners"


def owners_in(source):
    """How many owners a lesson from the pool was learned from, read off its source line; None for
    any other lesson."""
    m = SOURCE.match(source) if isinstance(source, str) else None
    return int(m.group(2)) if m else None


def pattern_in(source):
    m = SOURCE.match(source) if isinstance(source, str) else None
    return m.group(1) if m else None


def clear_owner(root, name):
    """Lets an owner name give again under its owner's new id, in every kind's pool of the shared
    folder: the operator's step once they know the owner-id file was made again on purpose. The
    kinds whose pool held the name."""
    root = check_root(root)
    out = []
    for path in sorted(root.glob(POOL_FILE.format(kind="*"))):
        kind = path.name[len("patterns-"):-len(".json")]
        if AGENT_NAME.fullmatch(kind) and Pool(kind, root).clear(name):
            out.append(kind)
    return out


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="The shared pool's operator steps.")
    sub = ap.add_subparsers(dest="step", required=True)
    c = sub.add_parser("clear-owner", help="let an owner name give again after its owner id was made again")
    c.add_argument("--db", required=True, help="the agents' database; its shared folder sits beside it")
    c.add_argument("name", help="the owner's name as its owner.json gives it")
    args = ap.parse_args(argv)
    try:
        kinds = clear_owner(root_for(args.db), args.name)
    except Refused as e:
        print(f"Not cleared: {e}.", file=sys.stderr)
        return 2
    print("cleared in: " + ", ".join(kinds) if kinds else "the name was not held in any pool")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
