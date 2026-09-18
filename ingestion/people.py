"""Fill the people table, so citations say a name instead of a number.

    # Load the vCards WhatsApp bundles with an export.
    python people.py --group-id meti-cohort-1 --vcf "3 contacts.vcf"

    # Load a hand-written list: one "handle,name" per line.
    python people.py --group-id meti-cohort-1 --csv names.csv

    # Who is still unnamed, busiest first? Fill these in by hand.
    python people.py --group-id meti-cohort-1 --missing

The bot fills this table too, at runtime, through POST /people: WhatsApp hands
the Baileys worker a pushName for anyone who speaks, which is the only source
that keeps working for members who join after the export was taken.
"""

import argparse
import csv
import os
import re
import sys

# vCard is a line-oriented format; a real parser would be overkill for the
# two fields we want. TEL and FN can both carry parameters after a ';'.
VCARD_FN = re.compile(r"^FN[;:](?:.*:)?(.+)$", re.IGNORECASE)
VCARD_TEL = re.compile(r"^TEL[;:](?:.*:)?(.+)$", re.IGNORECASE)


def parse_vcards(path: str) -> list[tuple[str, str]]:
    """Returns (handle, display_name) pairs.

    One card can hold several numbers (mobile, work). Each gets its own row:
    the same person under two handles is exactly what the table is for.

    The cards are split on the BEGIN marker rather than read line by line,
    because WhatsApp writes them back to back with no newline in between -
    "END:VCARDBEGIN:VCARD" arrives as one line. A line-by-line reader never
    sees a card end, and quietly gives every number in the file the name of
    the last contact.
    """
    text = open(path, encoding="utf-8", errors="replace").read()

    pairs: list[tuple[str, str]] = []
    for block in text.split("BEGIN:VCARD")[1:]:
        card = block.split("END:VCARD")[0]
        name: str | None = None
        tels: list[str] = []

        for line in card.splitlines():
            line = line.strip()
            if m := VCARD_FN.match(line):
                name = m.group(1).strip()
            elif m := VCARD_TEL.match(line):
                tels.append(m.group(1).strip())

        if name:
            pairs.extend((t, name) for t in tels)

    return pairs


def parse_csv(path: str) -> list[tuple[str, str]]:
    pairs = []
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) >= 2 and row[0].strip() and not row[0].startswith("#"):
                pairs.append((row[0].strip(), row[1].strip()))
    return pairs


def upsert(pairs: list[tuple[str, str]], group_id: str, origin: str, dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """insert into people (group_id, handle, display_name, origin)
                   values (%s, %s, %s, %s)
                   on conflict (group_id, handle_norm)
                   do update set display_name = excluded.display_name,
                                 origin = excluded.origin,
                                 updated_at = now()""",
                [(group_id, handle, name, origin) for handle, name in pairs],
            )
            written = cur.rowcount
        conn.commit()
    return written


def show_missing(group_id: str, dsn: str) -> None:
    """The people worth naming first are the ones who talk most."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """select u.author, count(*) as n
               from utterances u
               join sources s on s.id = u.source_id
               left join people p
                 on p.group_id = s.group_id and p.handle_norm = u.author_norm
               where s.group_id = %s and p.id is null
               group by u.author
               order by n desc
               limit 30""",
            (group_id,),
        ).fetchall()

    if not rows:
        print("Everyone who has spoken has a name. Nothing to do.")
        return

    print(f"{len(rows)} unnamed authors, busiest first.")
    print("Paste into a CSV as  handle,Name  and load it with --csv:\n")
    for author, n in rows:
        print(f"{author},          # {n} messages")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group-id", required=True)
    ap.add_argument("--vcf", help="vCard file from a WhatsApp export")
    ap.add_argument("--csv", help="handle,name per line")
    ap.add_argument("--missing", action="store_true", help="list unnamed authors")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    if args.missing:
        show_missing(args.group_id, dsn)
        return 0

    if args.vcf:
        pairs, origin = parse_vcards(args.vcf), "vcard"
    elif args.csv:
        pairs, origin = parse_csv(args.csv), "manual"
    else:
        print("Give one of --vcf, --csv or --missing.", file=sys.stderr)
        return 1

    if not pairs:
        print("No names found in that file.", file=sys.stderr)
        return 1

    written = upsert(pairs, args.group_id, origin, dsn)
    print(f"{written} names written for {args.group_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
