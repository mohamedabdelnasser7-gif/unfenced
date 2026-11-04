"""Builds reflection/words_en.xz, the English word list the shared pool's clean check reads
(reflection/shared.py check; new, 2026-11-04, crossowner round 2).

Source: /usr/share/dict/words as macOS and the BSDs ship it, Webster's Second International
Dictionary (1934), which is in the public domain. Kept: the lower case entries of 2 to 14
letters a to z. Left out: every entry the dictionary writes with a capital (a name of a person,
a place, a month or a day), and every number word, ordinal, fraction and money slang word
(shared.NUMBERISH: fiver, tenner, score, quarter, half, dozen, couple, pair, grand and the rest).
The first names the cleaner knows (arena/words.py) are taken out when the list is read, not here.

The file is the sorted words front coded (each line: how many letters it shares with the word
before it, 0 to 9, then the rest), lzma compressed; its first lines say the source.

    python3 -m reflection.make_words [path to the dictionary]
"""
import lzma
import re
import sys
from pathlib import Path

from reflection.shared import NUMBERISH, WORDS_FILE

SOURCE = Path("/usr/share/dict/words")
HEADER = ("# English words for the shared pool's clean check (reflection/shared.py)\n"
          "# Source: /usr/share/dict/words, Webster's Second International Dictionary (1934), public domain\n"
          "# Lower case entries of 2 to 14 letters; capitalised entries, number words, ordinals, fractions\n"
          "# and money slang left out (reflection/make_words.py)\n")


def build(source=SOURCE):
    raw = Path(source).read_text(encoding="utf-8", errors="replace").split()
    kept = sorted({w for w in raw if re.fullmatch(r"[a-z]{2,14}", w)} - NUMBERISH)
    lines, prev = [], ""
    for w in kept:
        n = 0
        while n < min(len(w), len(prev), 9) and w[n] == prev[n]:
            n += 1
        lines.append(f"{n}{w[n:]}")
        prev = w
    return HEADER.encode("ascii") + "\n".join(lines).encode("ascii"), len(kept)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text, n = build(argv[0] if argv else SOURCE)
    WORDS_FILE.write_bytes(lzma.compress(text, preset=9 | lzma.PRESET_EXTREME))
    print(f"{n} words written to {WORDS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
