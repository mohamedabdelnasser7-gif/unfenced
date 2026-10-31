"""Risk: is a lesson high or low risk for this agent's business?

The risk list in the agent's plug is written by a person for their business. The code
check runs first: any listed word, pattern or tool name in the lesson makes it high.
When the code finds none, the judge reads the lesson beside the plug's two about lines
and answers high, low or unsure. Unsure, any other answer and a judge that fails all
count as high, so a lesson is low only on the judge's clear low.

The judge is a stub by default: it always answers unsure, so every lesson counts as high
and waits for a person's yes. An agent can pass a real judge with the same shape.

Four marks are high for every plug, whatever its own list says; code_check names them
"core: ...". A link (http, www, a bare domain such as x.com, or one spelled out: x dot com,
x[.]com, x(dot)com, a middle dot, bullet, black circle, dot above or Arabic full stop for
the dot, a spaced dot before com, net or org, or the dot spelled in Arabic letters before
an ending in either script). A phone number: seven or more digits in a row, with anything
but letters and digits between them (spaces, dashes, dots, commas, brackets, slashes,
stars). A handle: @ and a name. Text copied from the sources, the texts of the cases the lesson came from: a run of
COPY_RUN words in a row, word for word, read in the normal form, so case, marks,
punctuation and hidden characters do not hide it. A copy shorter than the run is not
caught, and the judge never sees the sources, so a short copy (a name, a street) passes
unless a word or mark on the lists catches it.

COPY_RUN is five. The cost is uneven: a false high only asks a person for a yes, while a
missed copy puts one source's own words (a name, a place, a line someone typed) in front
of every case the lesson reaches. Four words in a row turn up by chance between any two
texts on the same work, so most lessons would wait for a yes; six lets a copied five word
line through. Five can still trip on a common phrase such as "at the end of the"; that
lesson waits for a yes, the safe side.

Matching runs on a normal form of the text (normalize), so a disguised letter cannot hide
a word: a numeral sign (a Roman twelve, a Tamil ten) becomes its digits; the text is taken
apart into base letters and marks (Unicode NFKD, which also turns wide and styled forms
into plain ones), and every mark goes, so an accent or a short vowel hides nothing; a
letter from another script that looks Latin (a Cyrillic e, a Greek o, a small capital, a
Lisu or Cherokee letter) becomes that Latin letter; case is folded; every digit in any
script becomes 0 to 9; every dash becomes "-"; Arabic letter forms are joined, Persian
yeh, keheh and heh forms included; a blank letter (a Hangul filler, a blank Braille cell)
counts as hidden. Every text is read in four forms: hidden characters dropped or read as
spaces, and numeral signs read as digits or as the letters they look like (a small Roman
one is an i, a Roman fifty an l), so a numeral sign inside a word cannot hide it either.
A word in Latin letters matches as a
whole word, with an English ending (s, es, ed, d, ing, ly; a final l or p may double before
ed or ing, as in cancelled and swapped); a word in another script
matches anywhere, since letters join on to it there. The plug's words take the same
form, so a look alike in the list matches the plain word too. Patterns are regular
expressions over the same normal form.
"""
import functools
import re
import unicodedata

HIGH, LOW, UNSURE = "high", "low", "unsure"
_ENDING = r"(?:s|es|ed|d|ing|ly)?"
_JOINED = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": None,
                         "\N{ARABIC LETTER FARSI YEH}": "ي", "\N{ARABIC LETTER KEHEH}": "ك",
                         "\N{ARABIC LETTER HEH GOAL}": "ه", "\N{ARABIC LETTER HEH DOACHASHMEE}": "ه",
                         "\N{ARABIC LETTER AE}": "ه", "\N{ARABIC LETTER HEH WITH YEH ABOVE}": "ه"})
# Letters with no ink: read like a hidden format character.
_BLANKS = frozenset("\N{HANGUL FILLER}\N{HALFWIDTH HANGUL FILLER}\N{HANGUL CHOSEONG FILLER}"
                    "\N{HANGUL JUNGSEONG FILLER}\N{BRAILLE PATTERN BLANK}")

# Letters that look like a Latin letter, by their Unicode names, so no look alike sits in
# this file as a raw character. A capital and its small letter can look like different
# Latin letters (Greek capital eta is H, small eta is n), so the table is read before case
# is folded; it is read once more after, for a capital left out that folds to a small one.
_LOOK_ALIKES = (
    ("a", "CYRILLIC SMALL LETTER A", "GREEK SMALL LETTER ALPHA", "LATIN SMALL LETTER ALPHA",
     "LATIN LETTER SMALL CAPITAL A"),
    ("A", "CYRILLIC CAPITAL LETTER A", "GREEK CAPITAL LETTER ALPHA"),
    ("b", "CYRILLIC SMALL LETTER VE", "LATIN LETTER SMALL CAPITAL B"),
    ("B", "CYRILLIC CAPITAL LETTER VE", "GREEK CAPITAL LETTER BETA"),
    ("c", "CYRILLIC SMALL LETTER ES", "LATIN LETTER SMALL CAPITAL C"),
    ("C", "CYRILLIC CAPITAL LETTER ES"),
    ("d", "CYRILLIC SMALL LETTER KOMI DE", "LATIN LETTER SMALL CAPITAL D"),
    ("e", "CYRILLIC SMALL LETTER IE", "GREEK SMALL LETTER EPSILON", "LATIN LETTER SMALL CAPITAL E"),
    ("E", "CYRILLIC CAPITAL LETTER IE", "GREEK CAPITAL LETTER EPSILON"),
    ("f", "LATIN LETTER SMALL CAPITAL F"),
    ("g", "LATIN SMALL LETTER SCRIPT G", "LATIN LETTER SMALL CAPITAL G"),
    ("h", "CYRILLIC SMALL LETTER SHHA", "CYRILLIC SMALL LETTER EN", "ARMENIAN SMALL LETTER HO",
     "LATIN LETTER SMALL CAPITAL H"),
    ("H", "CYRILLIC CAPITAL LETTER EN", "CYRILLIC CAPITAL LETTER SHHA", "GREEK CAPITAL LETTER ETA"),
    ("i", "CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I", "GREEK SMALL LETTER IOTA",
     "LATIN SMALL LETTER DOTLESS I", "LATIN LETTER SMALL CAPITAL I"),
    ("I", "CYRILLIC CAPITAL LETTER BYELORUSSIAN-UKRAINIAN I", "GREEK CAPITAL LETTER IOTA"),
    ("j", "CYRILLIC SMALL LETTER JE", "GREEK LETTER YOT", "LATIN SMALL LETTER DOTLESS J",
     "LATIN LETTER SMALL CAPITAL J"),
    ("J", "CYRILLIC CAPITAL LETTER JE"),
    ("k", "CYRILLIC SMALL LETTER KA", "GREEK SMALL LETTER KAPPA", "LATIN LETTER SMALL CAPITAL K"),
    ("K", "CYRILLIC CAPITAL LETTER KA", "GREEK CAPITAL LETTER KAPPA"),
    ("l", "CYRILLIC SMALL LETTER PALOCHKA", "CYRILLIC LETTER PALOCHKA", "LATIN LETTER SMALL CAPITAL L"),
    ("m", "CYRILLIC SMALL LETTER EM", "LATIN LETTER SMALL CAPITAL M"),
    ("M", "CYRILLIC CAPITAL LETTER EM", "GREEK CAPITAL LETTER MU"),
    ("n", "GREEK SMALL LETTER ETA", "LATIN LETTER SMALL CAPITAL N"),
    ("N", "GREEK CAPITAL LETTER NU"),
    ("o", "CYRILLIC SMALL LETTER O", "GREEK SMALL LETTER OMICRON", "ARMENIAN SMALL LETTER OH",
     "LATIN LETTER SMALL CAPITAL O"),
    ("O", "CYRILLIC CAPITAL LETTER O", "GREEK CAPITAL LETTER OMICRON"),
    ("p", "CYRILLIC SMALL LETTER ER", "GREEK SMALL LETTER RHO", "LATIN LETTER SMALL CAPITAL P"),
    ("P", "CYRILLIC CAPITAL LETTER ER", "GREEK CAPITAL LETTER RHO"),
    ("q", "CYRILLIC SMALL LETTER QA"),
    ("Q", "CYRILLIC CAPITAL LETTER QA"),
    ("r", "LATIN LETTER SMALL CAPITAL R"),
    ("s", "CYRILLIC SMALL LETTER DZE", "LATIN LETTER SMALL CAPITAL S"),
    ("S", "CYRILLIC CAPITAL LETTER DZE"),
    ("t", "CYRILLIC SMALL LETTER TE", "GREEK SMALL LETTER TAU", "LATIN LETTER SMALL CAPITAL T"),
    ("T", "CYRILLIC CAPITAL LETTER TE", "GREEK CAPITAL LETTER TAU"),
    ("u", "GREEK SMALL LETTER UPSILON", "ARMENIAN SMALL LETTER SEH", "LATIN LETTER SMALL CAPITAL U"),
    ("v", "GREEK SMALL LETTER NU", "LATIN LETTER SMALL CAPITAL V"),
    ("w", "CYRILLIC SMALL LETTER WE", "GREEK SMALL LETTER OMEGA", "LATIN LETTER SMALL CAPITAL W"),
    ("W", "CYRILLIC CAPITAL LETTER WE"),
    ("x", "CYRILLIC SMALL LETTER HA", "GREEK SMALL LETTER CHI"),
    ("X", "CYRILLIC CAPITAL LETTER HA", "GREEK CAPITAL LETTER CHI"),
    ("y", "CYRILLIC SMALL LETTER U", "CYRILLIC SMALL LETTER STRAIGHT U", "GREEK SMALL LETTER GAMMA",
     "LATIN LETTER SMALL CAPITAL Y"),
    ("Y", "CYRILLIC CAPITAL LETTER U", "CYRILLIC CAPITAL LETTER STRAIGHT U", "GREEK CAPITAL LETTER UPSILON"),
    ("z", "LATIN LETTER SMALL CAPITAL Z"),
    ("Z", "GREEK CAPITAL LETTER ZETA"),
    ("-", "MINUS SIGN"),
    (".", "IDEOGRAPHIC FULL STOP"),
    # Not a letter: a dot above alone breaks into a space and a mark under NFKD, so it is read
    # first as the middle dot it stands for.
    ("\N{MIDDLE DOT}", "DOT ABOVE"),
)
# More look alikes, from Unicode's confusables data (ICU copy, read 29 Oct 2026): Lisu and
# Cherokee capitals, rarer Latin, Greek, Cyrillic and Armenian letters. A letter the table
# above already reads stays as it is there.
_MORE_LOOK_ALIKES = (
    ("A", "CHEROKEE LETTER GO", "LISU LETTER A"),
    ("b", "CHEROKEE LETTER SI", "CYRILLIC CAPITAL LETTER SOFT SIGN", "LATIN CAPITAL LETTER TONE SIX"),
    ("B", "CHEROKEE LETTER YV", "LATIN CAPITAL LETTER BETA", "LISU LETTER BA"),
    ("c", "CHEROKEE SMALL LETTER TLI", "GREEK LUNATE SIGMA SYMBOL"),
    ("C", "CHEROKEE LETTER TLI", "GREEK CAPITAL LUNATE SIGMA SYMBOL", "LISU LETTER CA"),
    ("d", "CHEROKEE LETTER TSU", "LISU LETTER PHA"),
    ("D", "CHEROKEE LETTER A", "LISU LETTER DA"),
    ("e", "CYRILLIC SMALL LETTER ABKHASIAN CHE", "LATIN SMALL LETTER BLACKLETTER E"),
    ("E", "CHEROKEE LETTER GV", "LISU LETTER E"),
    ("f", "ARMENIAN SMALL LETTER KEH", "LATIN SMALL LETTER F WITH STROKE", "LATIN SMALL LETTER LENIS F",
     "LATIN SMALL LETTER LONG S WITH HIGH STROKE"),
    ("F", "GREEK LETTER DIGAMMA", "LATIN CAPITAL LETTER F WITH STROKE", "LISU LETTER TSA"),
    ("g", "ARMENIAN SMALL LETTER CO", "LATIN SMALL LETTER G WITH PALATAL HOOK", "LATIN SMALL LETTER TURNED DELTA"),
    ("G", "CHEROKEE LETTER NAH", "CHEROKEE LETTER YU", "CYRILLIC CAPITAL LETTER KOMI SJE", "LISU LETTER GA"),
    ("h", "CHEROKEE LETTER NI"),
    ("H", "CHEROKEE LETTER MI", "LISU LETTER XA"),
    ("i", "CHEROKEE LETTER V", "CHEROKEE SMALL LETTER V", "CYRILLIC SMALL LETTER IOTA", "LATIN SMALL LETTER IOTA"),
    ("I", "LATIN CAPITAL LETTER IOTA", "LISU LETTER I"),
    ("J", "CHEROKEE LETTER GU", "LATIN CAPITAL LETTER J WITH CROSSED-TAIL", "LISU LETTER JA"),
    ("K", "CHEROKEE LETTER TSO", "LISU LETTER KA"),
    ("l", "LATIN LETTER DENTAL CLICK"),
    ("L", "CHEROKEE LETTER TLE", "LISU LETTER LA"),
    ("M", "CHEROKEE LETTER LU", "GREEK CAPITAL LETTER SAN", "LISU LETTER MA"),
    ("n", "ARMENIAN SMALL LETTER RA", "ARMENIAN SMALL LETTER VO"),
    ("N", "LISU LETTER NA"),
    ("o", "GREEK SMALL LETTER SIGMA", "LATIN SMALL LETTER BLACKLETTER O", "LATIN SMALL LETTER SIDEWAYS O"),
    ("O", "LISU LETTER O"),
    ("P", "CHEROKEE LETTER TLV", "LISU LETTER PA"),
    ("q", "ARMENIAN SMALL LETTER GIM", "ARMENIAN SMALL LETTER ZA"),
    ("r", "CHEROKEE SMALL LETTER HU", "CYRILLIC SMALL LETTER GHE", "GREEK LETTER SMALL CAPITAL GAMMA",
     "LATIN SMALL LETTER DOUBLE R", "LATIN SMALL LETTER R WITHOUT HANDLE"),
    ("R", "CHEROKEE LETTER E", "CHEROKEE LETTER SV", "LISU LETTER ZHA"),
    ("s", "CHEROKEE SMALL LETTER DU", "LATIN SMALL LETTER TONE FIVE"),
    ("S", "ARMENIAN CAPITAL LETTER TIWN", "CHEROKEE LETTER DE", "CHEROKEE LETTER DU", "LISU LETTER SA"),
    ("T", "CHEROKEE LETTER I", "LISU LETTER TA"),
    ("u", "LATIN SMALL LETTER U WITH LEFT HOOK", "LATIN SMALL LETTER U WITH SHORT RIGHT LEG",
     "LATIN SMALL LETTER V WITH HOOK", "LATIN SMALL LETTER VOLAPUK UE"),
    ("U", "LISU LETTER U"),
    ("v", "CHEROKEE SMALL LETTER DO", "CYRILLIC SMALL LETTER IZHITSA"),
    ("V", "CHEROKEE LETTER DO", "CYRILLIC CAPITAL LETTER IZHITSA", "LISU LETTER HA"),
    ("w", "ARMENIAN SMALL LETTER AYB", "CHEROKEE SMALL LETTER LA", "CYRILLIC SMALL LETTER OMEGA",
     "LATIN SMALL LETTER TURNED M"),
    ("W", "CHEROKEE LETTER LA", "CHEROKEE LETTER TA", "LISU LETTER WA"),
    ("X", "LATIN CAPITAL LETTER CHI", "LISU LETTER SHA"),
    ("y", "LATIN SMALL LETTER GAMMA", "LATIN SMALL LETTER V WITH PALATAL HOOK", "LATIN SMALL LETTER Y WITH LOOP",
     "LATIN SMALL LETTER Y WITH SHORT RIGHT LEG"),
    ("Y", "CHEROKEE LETTER GI", "CHEROKEE LETTER MU", "LISU LETTER YA"),
    ("z", "CHEROKEE SMALL LETTER NO"),
    ("Z", "CHEROKEE LETTER NO", "LISU LETTER DZA"),
)
_PAIRS = {unicodedata.lookup(name): latin for latin, *names in _LOOK_ALIKES + _MORE_LOOK_ALIKES for name in names}
_LATIN = str.maketrans(_PAIRS)
# After case is folded: Cherokee folds small letters to capitals, so a capital there must
# still come out small.
_LATIN_SMALL = str.maketrans({ch: latin.lower() for ch, latin in _PAIRS.items()})


def _numeral(ch):
    """A numeral sign with no digit of its own (a Roman twelve, a Tamil ten) as its digits.
    A fraction stays, since NFKD writes it with digits."""
    if unicodedata.category(ch) in ("Nl", "No") and unicodedata.digit(ch, None) is None:
        value = unicodedata.numeric(ch, None)
        if value is not None and value >= 0 and value == int(value):
            return str(int(value))
    return ch


def normalize(text, hidden="", letters=False):
    """The one form every check reads. hidden: what a hidden format character becomes.
    letters: a numeral sign reads as the letters NFKD gives it (a small Roman one is i),
    not as its digits. The table is read before NFKD too, since NFKD turns some look alikes
    into a letter that is not one (a lunate sigma into a final sigma)."""
    text = text or ""
    if not letters:
        text = "".join(_numeral(ch) for ch in text)
    text = unicodedata.normalize("NFKD", text.translate(_LATIN)).translate(_LATIN)
    text = text.casefold().translate(_LATIN_SMALL)
    out = []
    for ch in text:
        kind = unicodedata.category(ch)
        if kind == "Cf" or ch in _BLANKS:  # hidden format characters and blank letters
            out.append(hidden)
            continue
        if kind.startswith("M"):  # accents, short vowels and every other mark
            continue
        if kind == "Pd":  # every dash
            out.append("-")
            continue
        digit = unicodedata.digit(ch, None)
        if digit is not None:
            out.append(str(digit))
        elif kind.startswith("N"):  # any other number sign (a fraction, a numeral letter) reads as a digit
            out.append("0")
        else:
            out.append(ch)
    return "".join(out).translate(_JOINED)


def _forms(text):
    """The four forms of a text every check reads: hidden characters dropped or read as
    spaces, numeral signs read as digits or as letters. Equal forms are read once."""
    return tuple(dict.fromkeys(normalize(text, hidden, letters)
                               for letters in (False, True) for hidden in ("", " ")))


@functools.lru_cache(maxsize=4096)
def _word(word):
    w = normalize(word)
    if w.isascii():
        body = r"\s+".join(re.escape(part) for part in w.split())
        # a final l or p doubles before ed and ing: cancelled, swapped (red team round 2, R2-4)
        ending = _ENDING if not w.endswith(("l", "p")) else r"(?:" + w[-1] + r"(?:ed|ing)|s|es|ed|d|ing|ly)?"
        return re.compile(r"(?<![a-z0-9_])" + body + ending + r"(?![a-z0-9_])")
    return re.compile(re.escape(w))


@functools.lru_cache(maxsize=1024)
def _pattern(p):
    return re.compile(p, re.IGNORECASE)


# The core marks, read on the normal form (see the top of this file).
# A link spelled out: a letter or digit, a stand in for the dot, then a common ending. A
# plain dot with spaces around it counts only before com, net or org, so a sentence that
# ends before a word such as "me" or "us" is not a link. The dot spelled in Arabic letters
# (dot) counts before an ending in Latin or Arabic letters, and so does a Latin "dot" before
# an Arabic ending. The word for a point (its closing letter reads as heh in the normal form)
# counts only before com, net, org, info or an Arabic ending, since Arabic writing puts it
# before Latin words such as "online" or "me"; before any other word it is plain writing.
_DOT_SIGNS = ("\N{MIDDLE DOT}\N{BULLET}\N{HYPHENATION POINT}\N{BULLET OPERATOR}\N{DOT OPERATOR}"
              "\N{KATAKANA MIDDLE DOT}\N{WORD SEPARATOR MIDDLE DOT}\N{BLACK CIRCLE}\N{ARABIC FULL STOP}")
_ENDINGS = "com|net|org|info|biz|io|co|me|app|online|site|xyz|link|eg|sa|ae|uk|us|ly|tv|gg"
_AR_DOT = "دوت|دات"
_AR_POINT = "نقطه"
_AR_ENDINGS = "كوم|نت|نيت|اورج|اورغ|انفو"
_SPELLED = (r"[^\W_](?:[" + _DOT_SIGNS + r"]|\s*[\[({]\s*(?:\.|dot)\s*[\])}]\s*|\s+dot\s+)(?:" + _ENDINGS
            + r")(?![\w-])|[^\W_]\s*[." + _DOT_SIGNS + r"]\s*(?:com|net|org)(?![\w-])"
            + r"|(?<![^\W_])(?:" + _AR_DOT + r")\s*(?:" + _ENDINGS + "|" + _AR_ENDINGS + r")(?![\w-])"
            + r"|(?<![^\W_])" + _AR_POINT + r"\s*(?:com|net|org|info|" + _AR_ENDINGS + r")(?![\w-])"
            + r"|(?:(?<![a-z0-9])dot\s*|[^\W_][" + _DOT_SIGNS + r"])(?:" + _AR_ENDINGS + r")(?![\w-])")
_LINK = re.compile(r"https?:/|www\.|[^\W_](?:[\w-]*[^\W_])?(?:\.[^\W_](?:[\w-]*[^\W_])?)*\.[^\W\d_]{2,}(?![\w-])|"
                   + _SPELLED)
_PHONE = re.compile(r"[0-9](?:[\W_]*[0-9]){6,}")
_HANDLE = re.compile(r"@\w")
CORE = (("link", _LINK), ("phone number", _PHONE), ("handle", _HANDLE))
COPIED = "core: copied from source"
COPY_RUN = 5
_WORDS = re.compile(r"\w+")


def _texts(sources):
    """The sources as a tuple of texts; ValueError when they are not a list of texts."""
    if sources is None:
        return ()
    if not isinstance(sources, (list, tuple)) or not all(isinstance(s, str) for s in sources):
        raise ValueError("sources is a list of texts")
    return tuple(sources)


def _runs(text):
    """Every run of COPY_RUN words in a row, in every form of the text."""
    runs = set()
    for form in _forms(text):
        words = _WORDS.findall(form)
        runs.update(tuple(words[i:i + COPY_RUN]) for i in range(len(words) - COPY_RUN + 1))
    return runs


def code_check(text, risk, sources=()):
    """The high risk marks found in the text, as "group: mark" lines; [] when none. The core
    marks come first, then the plug's list. sources: the texts of the cases the lesson came
    from. The text is read in its four forms (_forms), so a hidden character inside a word or
    between two words, or a numeral sign standing in for a letter, cannot hide either."""
    sources = _texts(sources)
    forms = _forms(text)

    def seen(rx):
        return any(rx.search(t) for t in forms)

    found = [f"core: {name}" for name, rx in CORE if seen(rx)]
    if sources:
        mine = _runs(text)
        found += [f"{COPIED} {n}" for n, src in enumerate(sources, 1) if mine & _runs(src)]
    found += [f"{group}: {w}" for group, w in risk.words if seen(_word(w))]
    found += [f"{group}: /{p}/" for group, p in risk.patterns if seen(_pattern(p))]
    found += [f"tool: {name}" for name in risk.tools if seen(_word(name))]
    return found


def no_judge(text, high_about, low_about):
    """The judge until a real one is built: never sure."""
    return UNSURE


def classify(text, risk, judge=no_judge, *, sources=()):
    """(HIGH or LOW, the lines that decided it). Code check first, then the judge.
    sources: the texts of the cases the lesson came from, when known."""
    found = code_check(text, risk, sources)
    if found:
        return HIGH, found
    try:
        answer = judge(text, risk.high_about, risk.low_about)
    except Exception as e:  # a judge that fails is not sure
        return HIGH, [f"judge failed ({type(e).__name__}), counted as high"]
    if answer == LOW:
        return LOW, ["judge: low"]
    if answer == HIGH:
        return HIGH, ["judge: high"]
    return HIGH, [f"judge: {UNSURE if answer == UNSURE else 'no clear answer'}, counted as high"]
