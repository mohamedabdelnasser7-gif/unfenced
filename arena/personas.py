"""Persona cards for the Arena from a store's old chats (new, 2026-10-30).

    python3 -I arena/personas.py --source EXPORT --out FOLDER [--limit N] [--cap N]
        --recipe FILE [--team NAME]... [--tz Africa/Cairo] [--quiet-hours 48] [--max-files N]
        [--scripted] [--json]

Run it by its path: under -I, "python3 -I -m arena.personas" cannot import the repo's packages.

EXPORT is a folder or a .zip: an Instagram data download (JSON, not HTML), a folder of WhatsApp
.txt exports, or both (whatsapp/ and instagram/ inside it). Every file goes through
reflection/history.py: untrusted, capped, no link followed. A zip's entries are read under the
same caps; a link, an encrypted entry or a zip inside the zip is refused and counted.
--max-files raises the file count cap for this build only (default reflection/history.py's
MAX_FILES, at most MOST_FILES): a whole chat export can hold more files than an upload may,
and every other reader keeps the cap.

1. Read every chat. The team is --team, or found: a sender in at least 3 chats and in at least
   3 in 10 of the chats with two senders or more.
2. Label every chat won, lost or unclear from the chat itself (arena/label.py).
3. Clean the won and lost chats (arena/clean.py): names, numbers and places out, in code.
4. Tag up to --limit of them, spread over time, with Muse Spark Open (arena/tag.py), at most
   --cap model calls, 1000 at most and by default. The prompt and the worry list come from the
   recipe (arena/recipe.py), which is required and private: a file outside this repo given with
   --recipe. demo/personas/recipe.example.json shows its shape.
5. Group the tagged chats into persona cards (arena/cards.py).

It writes into FOLDER, which must be outside this repo and new, empty or an earlier run's
output: cards/persona-NN.json, replay.jsonl (every won and lost chat, cleaned, for the Arena
replay) and summary.json (counts). Folders 0700, files 0600, no link followed. It prints
counts only, never a message, a name, a phone or a path.

--scripted: arena/scripted.py answers instead of the model; no call and no key. For tests and
the demo cards in demo/personas.
"""
import argparse
import json
import math
import os
import re
import secrets
import stat
import sys
import zipfile
import zlib
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__" and str(ROOT) not in sys.path:  # run by its path under -I, as reflection/importer.py is
    sys.path.insert(0, str(ROOT))

from kit import env  # noqa: E402
from reflection import history as hist  # noqa: E402
from reflection import importer as imp  # noqa: E402
from arena import cards as cards_mod  # noqa: E402
from arena import label as label_mod  # noqa: E402
from arena import recipe as recipe_mod  # noqa: E402
from arena import tag as tag_mod  # noqa: E402
from arena.clean import Cleaner  # noqa: E402
from arena.scripted import ScriptedModel  # noqa: E402

MAX_MEMBERS = 500_000
MOST_FILES = 20_000       # the most --max-files may raise the file count cap to
TEAM_MIN_CHATS = 3
TEAM_SHARE = 0.3
OUT_FILES = ("summary.json", "replay.jsonl")
CARD_FILE = re.compile(r"persona-\d{2,4}\.json")
IG_MEMBER = re.compile(r"(?:^|/)(messages/inbox/([^/]{1,255}))/message_(\d{1,4})\.json$")
IG_HTML = re.compile(r"(?:^|/)messages/inbox/[^/]{1,255}/message_\d{1,4}\.html$")
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError, OSError, ValueError)
ZIP = "zip"


# ---- the out folder

def check_out(out):
    """Refused unless out is outside the repo and is new, or a folder holding only an earlier
    run's files."""
    if hist.within(out, hist.REPO):
        raise hist.Refused("the out folder is inside the repo; give a folder outside it")
    raw = os.fspath(out)
    out = raw.rstrip(os.sep) or raw  # "link/" would follow the link in lstat and scandir
    try:
        st = os.lstat(out)
    except FileNotFoundError:
        parent = os.path.dirname(os.path.abspath(out))
        if not os.path.isdir(parent):
            raise hist.Refused("the out folder's parent is not a folder") from None
        return
    except OSError:
        raise hist.Refused("the out folder cannot be read") from None
    if stat.S_ISLNK(st.st_mode):
        raise hist.Refused("the out folder is a link")
    if not stat.S_ISDIR(st.st_mode):
        raise hist.Refused("the out folder is not a folder")
    foreign = "the out folder holds other files; give a new or empty folder"
    with os.scandir(out) as it:
        for e in it:
            if e.name in OUT_FILES and e.is_file(follow_symlinks=False):
                continue
            if e.name == "cards" and e.is_dir(follow_symlinks=False):
                with os.scandir(e.path) as inner:
                    if all(CARD_FILE.fullmatch(c.name) and c.is_file(follow_symlinks=False) for c in inner):
                        continue
            raise hist.Refused(foreign)


def _write(path, data):
    """Writes a new file under a fresh name, then moves it onto path: a link or a hard link
    left at path is replaced, never written through, so the file it points to keeps its text."""
    folder, name = os.path.split(os.fspath(path))
    temp = os.path.join(folder, f".{name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _folder(path):
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise hist.Refused("the out folder changed while it ran")
    os.chmod(path, 0o700)


def write_out(out, cards, replay, summary):
    check_out(out)  # again: it may have changed while the chats were read
    _folder(out)
    where = os.path.join(out, "cards")
    _folder(where)
    with os.scandir(where) as it:
        stale = [e.path for e in it if CARD_FILE.fullmatch(e.name) and e.is_file(follow_symlinks=False)]
    for path in stale:
        os.unlink(path)
    for c in cards:
        _write(os.path.join(where, c["id"] + ".json"), _json(c))
    _write(os.path.join(out, "replay.jsonl"),
           "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in replay).encode("utf-8"))
    _write(os.path.join(out, "summary.json"), _json(summary))


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---- reading the source

def read_source(src, reader, team, tz, counts):
    """Every chat in the source folder or zip."""
    try:
        st = os.lstat(src)
    except OSError:
        raise hist.Refused("the source: not found") from None
    if stat.S_ISLNK(st.st_mode):
        raise hist.Refused("the source: a link")
    if stat.S_ISDIR(st.st_mode):
        return read_folder(src, reader, team, tz, counts)
    if stat.S_ISREG(st.st_mode) and str(src).casefold().endswith(".zip"):
        return read_zip(src, reader, team, tz, counts)
    raise hist.Refused("the source: not a folder or a .zip")


def _real_dir(reader, path, kind):
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        reader.refuse(kind, "a link")
        return False
    return stat.S_ISDIR(st.st_mode)


def read_folder(src, reader, team, tz, counts):
    base = hist.folder(src)
    chats = []
    for where in (base, base / "whatsapp"):
        if _real_dir(reader, where, hist.WHATSAPP):
            chats += imp.read_all(reader, whatsapp=where, team=team, tz=tz, counts=counts)[0]
    for where in (base, base / "instagram"):
        if _real_dir(reader, where, hist.INSTAGRAM):
            chats += imp.read_all(reader, instagram=where, team=team, tz=tz, counts=counts)[0]
    return chats


def read_member(reader, z, info):
    """One zip entry's text under the reader's caps."""
    if reader.files >= reader.max_files:
        raise hist.Refused("over the file count cap")
    if info.file_size > hist.MAX_FILE_BYTES:
        raise hist.Refused("over the size cap of one file")
    if reader.bytes + info.file_size > hist.MAX_TOTAL_BYTES:
        raise hist.Refused("over the size cap of the whole import")
    data = None
    try:
        with z.open(info) as f:
            data = f.read(hist.MAX_FILE_BYTES + 1)
    except ZIP_ERRORS:  # raised below, outside this block, so no error keeps the entry
        pass
    if data is None:
        raise hist.Refused("a zip entry that cannot be read")
    if len(data) > hist.MAX_FILE_BYTES or reader.bytes + len(data) > hist.MAX_TOTAL_BYTES:
        raise hist.Refused("over the size cap")
    reader.bytes += len(data)
    reader.files += 1
    return data.decode("utf-8-sig", errors="replace")


def _members(reader, z):
    """(WhatsApp entries, {thread path: (folder name, [entries by number])})."""
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS:
        raise hist.Refused("the source: a zip with too many entries")
    whatsapp, threads = [], {}
    for info in infos:
        name = info.filename
        if info.is_dir():
            continue
        parts = name.split("/")
        if "__MACOSX" in parts or parts[-1].startswith("._"):
            continue
        ig, low = IG_MEMBER.search(name), name.casefold()
        kind = hist.INSTAGRAM if ig or IG_HTML.search(name) else hist.WHATSAPP if low.endswith(".txt") else \
            ZIP if low.endswith(".zip") else None
        if kind is None:
            continue
        if kind == ZIP:
            reader.refuse(ZIP, "a zip inside the zip")
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            reader.refuse(kind, "a link")
            continue
        if info.flag_bits & 1:
            reader.refuse(kind, "encrypted")
            continue
        if ig is None and kind == hist.INSTAGRAM:
            reader.refuse(kind, "an HTML download; ask Instagram for JSON")
        elif ig is not None:
            threads.setdefault(name[:ig.end(1)], (ig.group(2), []))[1].append((int(ig.group(3)), info))
        else:
            whatsapp.append(info)
    return sorted(whatsapp, key=lambda i: i.filename), threads


def read_zip(src, reader, team, tz, counts):
    hist.check_place(src)
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        fd = None
    if fd is None:
        raise hist.Refused("the source: a link, or not readable")
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise hist.Refused("the source: not a plain file")
        z = None
        try:
            z = zipfile.ZipFile(f)
        except ZIP_ERRORS:
            pass
        if z is None:
            raise hist.Refused("the source: a zip that cannot be read")
        with z:
            whatsapp, threads = _members(reader, z)
            chats = []
            for place, info in enumerate(whatsapp, 1):
                try:
                    chat = hist.parse_whatsapp(read_member(reader, z, info), team, file_name=info.filename.split("/")[-1],
                                               tz=tz, place=place, counts=counts)
                    reader.count(len(chat.messages))
                except hist.Refused as e:
                    reader.refuse(hist.WHATSAPP, str(e))
                    continue
                chats.append(chat)
            for place, path in enumerate(sorted(threads), 1):
                folder, files = threads[path]
                try:
                    docs = [hist.load_json(read_member(reader, z, info)) for _, info in sorted(files, key=lambda x: x[0])]
                    chat = hist.parse_instagram(docs, team, key=folder, place=place, counts=counts)
                    reader.count(len(chat.messages))
                except hist.Refused as e:
                    reader.refuse(hist.INSTAGRAM, str(e))
                    continue
                chats.append(chat)
    return chats


# ---- the team

def find_team(chats):
    """The senders found in at least TEAM_MIN_CHATS chats and TEAM_SHARE of the chats with two
    senders or more."""
    multi = [{m.sender for m in c.messages} for c in chats]
    multi = [s for s in multi if len(s) >= 2]
    seen = Counter(name for senders in multi for name in senders)
    need = max(TEAM_MIN_CHATS, math.ceil(TEAM_SHARE * len(multi)))
    return {name for name, n in seen.items() if n >= need}


def set_team(chats, team):
    for c in chats:
        for m in c.messages:
            m.team = m.sender in team


# ---- one run

def spread(items, n):
    """n of the items, evenly over their order."""
    if n >= len(items):
        return list(items)
    return [items[i * len(items) // n] for i in range(n)]


def turns_of(chat, cleaner):
    first = chat.messages[0].at if chat.messages else 0
    out = []
    for m, text in zip(chat.messages, cleaner.texts(chat.messages)):
        t = {"from": "store" if m.team else "customer"}
        if m.text:
            t["text"] = text
        if m.media:
            t["media"] = m.media
        t["min"] = int((m.at - first) // 60)
        out.append(t)
    return out


def run(source, out, *, model=None, cap=tag_mod.MAX_CALLS, limit=None, recipe=None, team=(), tz=hist.TZ,
        quiet_hours=label_mod.QUIET_HOURS, max_files=None):
    """One run: read, label, clean, tag, group and write. Returns the summary (counts only).
    max_files: the file count cap of this build, 1 to MOST_FILES (None: reflection/history.py's)."""
    if max_files is not None and (isinstance(max_files, bool) or not isinstance(max_files, int)
                                  or not 1 <= max_files <= MOST_FILES):
        raise hist.Refused(f"--max-files is 1 to {MOST_FILES}")
    check_out(out)
    recipe = recipe if recipe is not None else recipe_mod.load()
    tagger = tag_mod.Tagger(model=model, cap=cap, recipe=recipe)
    reader, counts = hist.Reader(max_files=max_files), Counter()
    chats = read_source(source, reader, team, tz, counts)
    if team:
        found = "given"
        team_names = {hist.name_key(t) for t in team}
    else:
        found = "found"
        team_names = find_team(chats)
        if not team_names:
            raise hist.Refused("no team found; give --team")
    set_team(chats, team_names)
    newest = max((m.at for c in chats for m in c.messages), default=0)
    cleaner = Cleaner({n for c in chats for n in c.names})
    labels, whys, items, replay = Counter(), Counter(), [], []
    for chat in chats:
        lab, why = label_mod.label(chat, newest, quiet_hours)
        labels[lab] += 1
        whys[f"{lab}: {why}"] += 1
        if lab not in (label_mod.WON, label_mod.LOST):
            continue
        users = [re.sub(r"_\d+$", "", chat.key)] if chat.source == hist.INSTAGRAM else []
        chat_cleaner = cleaner.chat(chat.names, users)
        entry = {"id": f"c{len(replay) + 1:04d}", "label": lab, "why": why, "source": chat.source, "worry": None,
                 "turns": turns_of(chat, chat_cleaner)}
        replay.append(entry)
        items.append({"label": lab, "turns": entry["turns"], "chat": chat, "entry": entry,
                      "first": chat.messages[0].at, "cleaner": chat_cleaner})
    items.sort(key=lambda i: i["first"])
    picked = spread(items, min(limit or len(items), cap, len(items)))
    tagged, not_tagged = [], 0
    for item in picked:
        if not tagger.can_ask():
            not_tagged += 1
            continue
        tags = tagger(item["turns"], item["label"], cleaner=item["cleaner"])
        if tags is None:
            continue
        item["entry"]["worry"] = tags["worry"]
        tagged.append({"label": item["label"], "tags": tags, "style": cards_mod.style_of(item["chat"]),
                       "turns": item["turns"]})
    cards, info = cards_mod.build(tagged, recipe)
    summary = {
        "recipe": "example" if recipe.example else "own", "recipe_sha256": recipe.sha, "model": tagger.label,
        "read": {"whatsapp_chats": sum(c.source == hist.WHATSAPP for c in chats),
                 "instagram_chats": sum(c.source == hist.INSTAGRAM for c in chats),
                 "messages": sum(len(c.messages) for c in chats)},
        "not_read": [{"kind": k, "why": w, "files": n} for (k, w), n in sorted(reader.refused.items())],
        "team": {"from": found, "names": len(team_names)},
        "labels": {k: labels[k] for k in (label_mod.WON, label_mod.LOST, label_mod.UNCLEAR)},
        "why": {k: whys[k] for k in sorted(whys)},
        "tagging": {"cap": cap, "limit": limit, "picked": len(picked), "calls": tagger.calls, "failed": tagger.failed,
                    "bad_answers": tagger.refused, "tagged": len(tagged), "not_tagged": not_tagged,
                    "stopped": tagger.stopped, "last_error": tagger.last_error},
        "cards": info,
        "replay_chats": len(replay),
    }
    write_out(out, cards, replay, summary)
    return summary


# ---- the report

def text(s):
    """The summary in plain lines: counts only."""
    r, lab, t, c = s["read"], s["labels"], s["tagging"], s["cards"]
    lines = [f'Read: {r["whatsapp_chats"]} WhatsApp chats, {r["instagram_chats"]} Instagram chats, '
             f'{r["messages"]} messages; team {s["team"]["from"]} ({s["team"]["names"]} names)']
    for n in s["not_read"]:
        lines.append(f'Not read: {n["files"]} {n["kind"]} file(s), {n["why"]}')
    lines.append(f'Labels: {lab["won"]} won, {lab["lost"]} lost, {lab["unclear"]} unclear (skipped)')
    lines += [f"  {k}: {n}" for k, n in s["why"].items()]
    lines.append(f'Tagging ({s["model"]}, recipe {s["recipe"]}): {t["calls"]} calls of a cap of {t["cap"]}, '
                 f'{t["tagged"]} tagged, {t["failed"]} failed calls, {t["bad_answers"]} bad answers, '
                 f'{t["not_tagged"]} not tagged')
    if t["stopped"]:
        lines.append(f'Stopped asking: {t["stopped"]}')
    if t["last_error"]:
        lines.append(f'Last model error: {t["last_error"]}')
    share = c["unwinnable_share_real"]
    lines.append(f'Cards: {c["cards"]} ({c["unwinnable_cards"]} unwinnable) from {c["tagged_chats"]} tagged chats; '
                 f'unwinnable weight {c["unwinnable_share_used"]}'
                 + (f' (the real share)' if share is not None else
                    f' (fewer than {cards_mod.MIN_FOR_SHARE} tagged chats: the set share)' if c["unwinnable_chats"] else
                    ' (no unwinnable chat, so no unwinnable card)'))
    for w in c.get("capped_wants", []):
        lines.append(f'Capped want {w["name"]}: weight {w["share_used"]}, most {w["most"]}'
                     + (f' (cut from {w["share_real"]})' if w["share_used"] != w["share_real"] else '')
                     + ('; no card under no capped want to take the rest, so not held' if w.get("held") is False
                        else ''))
    lines.append(f'Replay: {s["replay_chats"]} won and lost chats, cleaned')
    return "\n".join(lines)


def main(argv=None, *, model=None):
    ap = argparse.ArgumentParser(prog="arena/personas.py", description="Persona cards for the Arena from old chats.")
    ap.add_argument("--source", required=True, help="an export folder or .zip (Instagram JSON, WhatsApp .txt)")
    ap.add_argument("--out", required=True, help="the folder to write, outside this repo")
    ap.add_argument("--limit", type=int, help="tag at most this many chats, spread over time")
    ap.add_argument("--cap", type=int, default=tag_mod.MAX_CALLS,
                    help=f"model calls at most (default and most {tag_mod.MAX_CALLS})")
    ap.add_argument("--recipe", help="the persona recipe file, required and private (kept outside this repo; "
                                     "demo/personas/recipe.example.json shows the shape)")
    ap.add_argument("--team", action="append", default=[], help="a display name of the store's side; repeat it")
    ap.add_argument("--tz", default=hist.TZ, help="the time zone of the WhatsApp exports (default Africa/Cairo)")
    ap.add_argument("--quiet-hours", type=int, default=label_mod.QUIET_HOURS,
                    help="hours of quiet after the store's answer that make a chat lost (default 48)")
    ap.add_argument("--max-files", type=int, default=hist.MAX_FILES,
                    help=f"files read at most, for this build only (default {hist.MAX_FILES}, most {MOST_FILES})")
    ap.add_argument("--scripted", action="store_true", help="the scripted model: no call, no key")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args(argv)
    if not 1 <= args.max_files <= MOST_FILES:
        ap.error(f"--max-files is 1 to {MOST_FILES}")
    if args.cap > tag_mod.MAX_CALLS:
        ap.error(f"the cap can only be lowered (most {tag_mod.MAX_CALLS})")
    if args.cap < 1:
        ap.error("--cap is at least 1")
    if args.limit is not None and args.limit < 1:
        ap.error("--limit is at least 1")
    if not 1 <= args.quiet_hours <= 720:
        ap.error("--quiet-hours is 1 to 720")
    try:
        ZoneInfo(args.tz)
    except (ValueError, KeyError):
        ap.error("--tz is a time zone name such as Africa/Cairo")
    try:
        check_out(args.out)
        recipe = recipe_mod.load(args.recipe)
        if args.scripted:
            model = ScriptedModel(recipe)
        elif model is None:
            env.load()
            if not env.get("BASETEN_API_KEY"):
                raise hist.Refused("BASETEN_API_KEY is not set (or give --scripted)")
        summary = run(args.source, args.out, model=model, cap=args.cap, limit=args.limit, recipe=recipe,
                      team=args.team, tz=args.tz, quiet_hours=args.quiet_hours, max_files=args.max_files)
    except hist.Refused as e:
        print(f"Refused, nothing written: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # any other error, named by its type only: its text could hold a message
        print(f"Stopped: {type(e).__name__}", file=sys.stderr)
        return 3
    print(json.dumps(summary, indent=1) if args.json else text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
