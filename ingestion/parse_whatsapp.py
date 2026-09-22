"""Parse a WhatsApp chat export into sources + utterances.

Usage:
    python parse_whatsapp.py chat.txt --group-id meti-cohort-1 [--tz Africa/Bamako] [--dry-run]

The export is the .txt file from WhatsApp's "Export chat / Without media".
Re-running it on the same file is safe: the unique index on
(source_id, author, said_at, md5(content)) drops the duplicates.

Embeddings are NOT written here. Parsing must stay free and instant so we can
re-run it; embedding costs money and is a separate pass (embed.py).
"""

import argparse
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Two export layouts in the wild:
#   iOS      [12/09/2026, 10:04:32] Steven: hello
#   Android  12/09/2026, 10:04 - Steven: hello
# WhatsApp also sprinkles invisible LTR/RTL marks around the brackets.
IOS = re.compile(
    r"^‎?\[(?P<date>\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>[APap][Mm])?\]\s*"
    r"(?P<rest>.*)$"
)
ANDROID = re.compile(
    r"^‎?(?P<date>\d{1,2}[/.]\d{1,2}[/.]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>[APap][Mm])?\s+-\s+"
    r"(?P<rest>.*)$"
)

# Lines WhatsApp writes itself. They have a timestamp but no real author, and
# citing "Messages are end-to-end encrypted" as a source would be absurd.
NOISE = re.compile(
    r"(end-to-end encrypted|a été ajouté|added|left$|joined using|"
    r"changed the subject|a changé|created group|a créé|"
    r"<Media omitted>|<Médias omis>|image omitted|sticker omitted|"
    r"This message was deleted|Ce message a été supprimé|"
    # The same notices in French. WhatsApp writes them in the language of
    # the phone that exported the chat, and only the English wording was
    # listed, so a French export filed seven of them as things the group
    # had said, attributed to the group's own name. One of them recites
    # the encryption notice; another lists the phone numbers of people
    # somebody added.
    r"chiffrés de bout en bout|a rejoint le groupe|"
    r"utilisé un lien pour rejoindre|a ajouté|a retiré|est parti|"
    # \s, not a space: WhatsApp writes "256\u00a0membres" with a
    # non-breaking space, which a literal space never matches.
    r"inclut plus de \d+\s*membres|a modifié|a supprimé ce message|"
    r"image absente|vidéo absente|audio absent|document absent|"
    r"sticker absent|GIF absent|autocollant absent)",
    re.IGNORECASE,
)

# Invisible characters WhatsApp puts inside message text: the LTR mark it
# writes around the brackets, and the directional isolates it wraps a mention
# in. Typing "@ask" makes it a mention candidate, so what is written to the
# export is "@\u2068ask\u2069", and a word with one of these inside it is not
# the word the index holds.
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

# Traffic between the group and the bot, which is not group content.
#
# Seen in a private chat the morning after launch: "what is the submission
# deadline?" was answered with 'According to Is any of it real: "@ask give me
# a summary"'. A question put to the bot is a command, and the bot's own reply
# is something the bot already said, so quoting either back is a loop. The
# worker applies the same rule to live messages (adapters/whatsapp/index.js);
# this is the same rule for an export, which is written after the fact and so
# contains both sides of every exchange.
ADDRESSED_TO_BOT = re.compile(r"^\s*@ask\b", re.IGNORECASE)

# The bot's display name in the export, as WhatsApp writes it. Configurable
# because the name follows whichever number the team paired.
BOT_AUTHOR = os.environ.get("BOT_AUTHOR", "Uniconnect-IA")

FRENCH_MARKERS = {
    "je", "tu", "nous", "vous", "est", "les", "des", "une", "pour", "avec",
    "dans", "pas", "que", "qui", "c'est", "bonjour", "merci", "oui", "non",
}


def detect_lang(text: str) -> str:
    words = {w.strip("?!.,;:").lower() for w in text.split()}
    return "fr" if words & FRENCH_MARKERS else "en"


def day_first(raw_dates: list[str]) -> bool:
    """Decide whether 9/8/26 means 8 September or 9 August.

    WhatsApp writes the exporter's phone locale with no marker of which it
    used, and getting this wrong silently shifts the whole history by months,
    which would wreck "what did I miss since Tuesday". So we read the answer
    off the file itself: a component above 12 cannot be a month.

    Our own METI export is month-first (it contains 9/18/26), even though
    nobody on the team writes dates that way. Do not assume.
    """
    firsts, seconds = [], []
    for d in raw_dates:
        a, b, _ = re.split(r"[/.]", d)
        firsts.append(int(a))
        seconds.append(int(b))

    first_is_day = any(v > 12 for v in firsts)
    second_is_day = any(v > 12 for v in seconds)

    if first_is_day and second_is_day:
        raise SystemExit("Dates are inconsistent - both fields exceed 12. Check the export.")
    if first_is_day:
        return True
    if second_is_day:
        return False

    # Every date in the file is ambiguous (a short export inside one
    # fortnight). Say so out loud instead of guessing quietly.
    print(
        "Warning: no date above the 12th in this export, so day/month order "
        "cannot be read from the file. Assuming day-first; pass a longer "
        "export to settle it.",
        file=sys.stderr,
    )
    return True


def parse_stamp(date: str, time: str, ampm: str | None, tz: ZoneInfo, dayfirst: bool) -> datetime:
    a, b, y = re.split(r"[/.]", date)
    day, month = (a, b) if dayfirst else (b, a)
    year = int(y) + 2000 if len(y) == 2 else int(y)

    parts = time.split(":")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    if ampm:
        upper = ampm.upper()
        if upper == "PM" and hour != 12:
            hour += 12
        elif upper == "AM" and hour == 12:
            hour = 0

    local = datetime(year, int(month), int(day), hour, minute, second, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC"))


def parse(path: str, tz_name: str) -> list[dict]:
    tz = ZoneInfo(tz_name)
    lines = open(path, encoding="utf-8-sig", errors="replace").read().splitlines()

    heads = []
    for line in lines:
        m = IOS.match(line) or ANDROID.match(line)
        heads.append(m)
    dayfirst = day_first([m.group("date") for m in heads if m])

    messages: list[dict] = []
    # strict: heads is built one entry per line just above, so a length
    # mismatch would mean the file was read twice differently.
    for line, m in zip(lines, heads, strict=True):
        if m is None:
            # A continuation line of the previous message. Keep the newline:
            # pasted agendas and code snippets lose their meaning without it.
            if messages:
                messages[-1]["content"] += "\n" + line
            continue

        # Invisible marks WhatsApp scatters through message text: the LTR
        # mark it puts around the brackets, and the directional isolates it
        # wraps a mention in. "@ask" arrives as "@\u2068ask\u2069", and a
        # word with one of these inside it is not the word the index holds.
        rest = INVISIBLE.sub("", m.group("rest")).strip()
        author, sep, content = rest.partition(": ")
        if not sep or NOISE.search(rest):
            continue  # system line, not something a person said

        # WhatsApp prefixes people who are not in your contacts with "~" and
        # a narrow no-break space. Both would end up printed in citations.
        author = author.lstrip("~").replace(" ", " ").strip()

        messages.append(
            {
                "author": author,
                "content": content,
                "said_at": parse_stamp(
                    m.group("date"), m.group("time"), m.group("ampm"), tz, dayfirst
                ),
            }
        )

    # Attachments and deleted messages leave an empty body once stripped.
    return [
        m
        for m in messages
        if m["content"].strip()
        and not NOISE.search(m["content"])
        and not ADDRESSED_TO_BOT.match(m["content"])
        and m["author"].casefold() != BOT_AUTHOR.casefold()
    ]


def load(messages: list[dict], group_id: str, title: str, dsn: str) -> tuple[str, int]:
    # Imported here, not at the top: --dry-run has to work on a laptop with
    # nothing installed, so you can check an export before touching the VPS.
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Upsert, not insert: a group has exactly one chat source, so a
            # second export of the same group lands in the same source and
            # the de-duplication index below can see the existing messages.
            # occurred_at keeps the earliest message we have ever seen.
            cur.execute(
                """insert into sources (kind, platform, group_id, title, occurred_at)
                   values ('chat', 'whatsapp', %s, %s, %s)
                   on conflict (platform, group_id) where kind = 'chat'
                   do update set title = excluded.title,
                                 occurred_at = least(sources.occurred_at, excluded.occurred_at)
                   returning id""",
                (group_id, title, messages[0]["said_at"]),
            )
            source_id = cur.fetchone()[0]

            cur.executemany(
                """insert into utterances (source_id, author, content, said_at, lang)
                   values (%s, %s, %s, %s, %s)
                   on conflict (source_id, author, said_at, md5(content)) do nothing""",
                [
                    (source_id, m["author"], m["content"], m["said_at"], detect_lang(m["content"]))
                    for m in messages
                ],
            )
            written = cur.rowcount
        conn.commit()
    return source_id, written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="WhatsApp export .txt")
    ap.add_argument("--group-id", required=True, help="stable id for this group")
    ap.add_argument("--title", default=None, help="defaults to the file name")
    ap.add_argument("--tz", default="UTC", help="timezone the export was written in")
    ap.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    args = ap.parse_args()

    messages = parse(args.file, args.tz)
    if not messages:
        print("No messages parsed. Is this a WhatsApp export?", file=sys.stderr)
        return 1

    authors = {m["author"] for m in messages}
    print(f"{len(messages)} messages, {len(authors)} authors")
    print(
        f"from {messages[0]['said_at']:%Y-%m-%d %H:%M} "
        f"to {messages[-1]['said_at']:%Y-%m-%d %H:%M} UTC"
    )

    if args.dry_run:
        for m in messages[:3]:
            print(f"  {m['said_at']:%Y-%m-%d %H:%M} {m['author']}: {m['content'][:70]}")
        return 0

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    source_id, written = load(
        messages, args.group_id, args.title or os.path.basename(args.file), dsn
    )
    print(f"source {source_id}: {written} new, {len(messages) - written} already there")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
