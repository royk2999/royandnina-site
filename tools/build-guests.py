#!/usr/bin/env python3
"""
Regenerate the guest list in guestlist/index.html from a Withjoy CSV export.

Reads who is coming (rsvp / reception == Accept) and where they sit (a
"Table N" tag in the tags column), then rewrites the `const guests = [...]`
array. Only first name, last name and table are ever written — contact
details in the export are dropped and never reach the repo.

Usage:
    python3 tools/build-guests.py                     # newest export in ~/Downloads
    python3 tools/build-guests.py path/to/export.csv
    python3 tools/build-guests.py --dry-run           # report only, write nothing

Needs nothing but Python 3 (no pip install).
"""

import csv
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "guestlist", "index.html")

START = "    const guests = ["
END = "    ];"

ACCEPT = "Accept"
RSVP_COL = "rsvp / reception"

# "Table 5", "table  5", " TABLE 5 " -> "5"
TABLE_RE = re.compile(r"\s*table\s*(\d+)\s*$", re.I)
# anything mentioning a table that we could not read as an assignment
TABLEISH_RE = re.compile(r"table", re.I)

PII_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
                    r"|\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")


def newest_export():
    hits = []
    for pat in ("guest-list*.csv", "guestlist*.csv"):
        hits += glob.glob(os.path.join(os.path.expanduser("~"), "Downloads", pat))
    if not hits:
        sys.exit("No guest-list*.csv found in ~/Downloads — pass the path explicitly.")
    return max(hits, key=os.path.getmtime)


def tables_for(row):
    """Every table number tagged on this guest (normally exactly one)."""
    return [m.group(1) for tag in row["tags"].split(",")
            for m in [TABLE_RE.fullmatch(tag)] if m]


def odd_tags(row):
    """Tags that mention a table but aren't a clean 'Table N'."""
    return [t.strip() for t in row["tags"].split(",")
            if TABLEISH_RE.search(t) and not TABLE_RE.fullmatch(t)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv
    src = args[0] if args else newest_export()

    with open(src, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    if RSVP_COL not in (rows[0] if rows else {}):
        sys.exit(f"'{RSVP_COL}' column missing — is this a Withjoy export?")

    accepted = [r for r in rows if r[RSVP_COL].strip() == ACCEPT]

    guests, unseated, conflicts, malformed = [], [], [], []
    for r in accepted:
        first, last = r["first name"].strip(), r["last name"].strip()
        found = tables_for(r)
        if len(found) > 1:
            conflicts.append((f"{last}, {first}", found))
        if odd_tags(r):
            malformed.append((f"{last}, {first}", odd_tags(r)))
        table = found[0] if found else ""
        if not table:
            unseated.append(f"{last}, {first}")
        guests.append({"first": first, "last": last, "table": table})

    guests.sort(key=lambda g: (g["last"].lower(), g["first"].lower()))

    # ---- report -------------------------------------------------------
    print(f"source          : {src}")
    print(f"rows in export  : {len(rows)}")
    print(f"accepted        : {len(accepted)}")
    print(f"seated          : {len(accepted) - len(unseated)}")
    print(f"NOT seated yet  : {len(unseated)}")

    per = {}
    for g in guests:
        if g["table"]:
            per.setdefault(g["table"], []).append(f'{g["last"]}, {g["first"]}')
    if per:
        print("\nheadcount per table")
        for t in sorted(per, key=int):
            print(f"  Table {t:<3} {len(per[t]):>3}")

    seen, dupes = set(), []
    for g in guests:
        key = (g["first"].lower(), g["last"].lower())
        if key in seen:
            dupes.append(f'{g["last"]}, {g["first"]}')
        seen.add(key)
    if dupes:
        print("\n!! same name twice — check they got the right tables:")
        for d in dupes:
            print(f"   {d}")
    if conflicts:
        print("\n!! more than one table tag:")
        for name, ts in conflicts:
            print(f"   {name}: {', '.join(ts)}")
    if malformed:
        print("\n!! table-ish tags that did not parse (fix in Withjoy):")
        for name, ts in malformed:
            print(f"   {name}: {ts}")
    if unseated:
        print(f"\nstill to seat ({len(unseated)}):")
        for n in unseated:
            print(f"   {n}")

    # ---- render -------------------------------------------------------
    body = "\n".join(
        "      " + json.dumps(g, ensure_ascii=False) + ","
        for g in guests
    )
    block = f"{START}\n{body}\n{END}"

    if PII_RE.search(block):
        sys.exit("ABORT: generated block looks like it contains contact details.")

    with open(HTML, encoding="utf-8") as fh:
        html = fh.read()
    if START not in html:
        sys.exit(f"Could not find '{START.strip()}' in {HTML}")
    head, rest = html.split(START, 1)
    _, tail = rest.split("\n" + END, 1)
    updated = head + block + tail

    if dry:
        print(f"\n[dry run] {len(guests)} guests — {HTML} not written")
        return
    if updated == html:
        print(f"\nno change — {HTML} already up to date")
        return
    with open(HTML, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"\nwrote {len(guests)} guests to {HTML}")


if __name__ == "__main__":
    main()
