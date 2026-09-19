"""Load a document into the same table as the chats and the calls.

    export DATABASE_URL=...
    python document.py brief.txt --group-id meti-cohort-1 \
        --title "Chatbot Hackathon brief" --dated 2026-09-15

The hackathon asks for a bot that makes sense of "calls, chats, and more".
The "and more" is this: the rules, the briefs, the schedules that were shared
as a file or pasted once and scrolled past. They hold the answers people ask
for most and they are the hardest thing in a group to find again.

A document becomes utterances like everything else, so one search covers a
chat message, a call and a PDF's text without the retrieval code knowing the
difference. It is attributed to the document itself, never to a person:
nobody said it, it was written.

Accepts plain text or markdown. For a PDF, extract the text first:
    pdftotext -layout brief.pdf brief.txt
"""

import argparse
import os
import re
import sys
from datetime import UTC, datetime, timedelta

# A chunk has to be large enough to answer a question on its own and small
# enough to be quoted whole. The ceiling is set just under answer.py's
# QUOTE_CHARS: with no model credit the bot quotes its best hit verbatim and
# truncates at 400 characters, and a 700-character chunk holding the deadline
# in its last line loses exactly the part that was asked for.
#
# The floor matters as much. A brief is full of one-line headings and bullets,
# and a chunk holding only "The Challenge" answers nothing while taking a slot
# in the prompt, so short pieces are merged into their neighbours.
CHUNK_CHARS = 380
MIN_CHARS = 120

SOURCE_SQL = """
insert into sources (kind, platform, group_id, title, occurred_at)
values ('document', 'file', %s, %s, %s)
returning id
"""

INSERT_SQL = """
insert into utterances (source_id, author, content, said_at)
values (%s, %s, %s, %s)
on conflict (source_id, author, said_at, md5(content)) do nothing
"""


def is_heading(paragraph: str) -> bool:
    """A section title rather than a sentence.

    One short line, no sentence-ending punctuation, no bullet: "The Problem",
    "What to Submit". They have to open a chunk instead of being swallowed by
    the one before, or the title of a section ends up filed under the previous
    section and stops helping the search find it.
    """
    if "\n" in paragraph or len(paragraph) > 60:
        return False
    if paragraph[:1] in "-*•":
        return False
    # "1. Name your file: Country_SolutionName_YourName" is a step, not a
    # title. It is short and it ends on a word, so everything else about it
    # looks like a heading, and treating it as one orphaned the real heading
    # above it.
    if re.match(r"^\d+[.)]\s", paragraph):
        return False
    return not paragraph.rstrip().endswith((".", "!", "?", ":", ","))


def split_long(paragraph: str) -> list[str]:
    """Break a paragraph that is too long to be one chunk, at sentence ends.

    Text pulled out of a PDF often arrives as a single wall with no blank
    lines anywhere, so without this the whole document becomes one chunk and
    every answer quotes the entire brief.
    """
    if len(paragraph) <= CHUNK_CHARS:
        return [paragraph]

    # Split after . ! ? or a bullet, keeping the punctuation with its sentence.
    pieces = re.split(r"(?<=[.!?])\s+|\n(?=[•\-*]\s)", paragraph)

    out: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if out and len(out[-1]) + len(piece) + 1 <= CHUNK_CHARS:
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


def to_chunks(text: str) -> list[str]:
    """Split on blank lines, then merge until the pieces are worth searching.

    Merging matters more than splitting here. A brief is full of one-line
    headings and bullet points, and a chunk holding only "The Challenge"
    answers nothing while taking a slot in the prompt.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    # Whether the chunk being built is still nothing but heading lines. A
    # document that opens with its own title followed by a section title had
    # the title left alone in a chunk of its own, which is a chunk that
    # answers nothing and a title detached from what it names.
    open_is_heading = False

    for paragraph in paragraphs:
        paragraph = re.sub(r"[ \t]+", " ", paragraph)
        heading = is_heading(paragraph)

        for piece in split_long(paragraph):
            if chunks and (
                # A heading joins the chunk above only when that chunk is
                # itself nothing but headings. Otherwise it starts a section
                # and belongs at the top of one.
                open_is_heading
                or (not heading and len(chunks[-1]) < MIN_CHARS)
                or (not heading and len(chunks[-1]) + len(piece) + 1 <= CHUNK_CHARS)
            ):
                chunks[-1] += "\n" + piece
                open_is_heading = open_is_heading and heading
            else:
                chunks.append(piece)
                open_is_heading = heading

    return [c for c in chunks if c.strip()]


def load(chunks: list[str], group_id: str, title: str, dated: datetime, dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Every load of a document is its own source. Unlike a chat
            # export, a document is not something that accumulates: a second
            # version is a second document, and keeping both is usually right
            # since the group may have acted on either.
            cur.execute(SOURCE_SQL, (group_id, title, dated))
            source_id = cur.fetchone()[0]

            cur.executemany(
                INSERT_SQL,
                [
                    # said_at spaces the chunks one second apart so they keep
                    # their order on the timeline, and sits them at the date
                    # the document is from rather than the date it was loaded.
                    (source_id, title, chunk, dated + timedelta(seconds=i))
                    for i, chunk in enumerate(chunks)
                ],
            )
            written = cur.rowcount
        conn.commit()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="a text or markdown file")
    ap.add_argument("--group-id", required=True)
    ap.add_argument("--title", required=True, help='e.g. "Chatbot Hackathon brief"')
    ap.add_argument("--dated", help="ISO date the document is from; defaults to the file's")
    ap.add_argument("--dry-run", action="store_true", help="show the chunks, write nothing")
    args = ap.parse_args()

    text = open(args.file, encoding="utf-8", errors="replace").read()
    chunks = to_chunks(text)

    if not chunks:
        print("Nothing to load: the file is empty.", file=sys.stderr)
        return 1

    if args.dated:
        dated = datetime.fromisoformat(args.dated.replace("Z", "+00:00"))
        if not dated.tzinfo:
            dated = dated.replace(tzinfo=UTC)
    else:
        # The file's own timestamp, not now: a brief written last week belongs
        # on the timeline last week, or "what did I miss since Tuesday" starts
        # reporting documents somebody loaded rather than things that happened.
        dated = datetime.fromtimestamp(os.path.getmtime(args.file), tz=UTC)
        print(f"No --dated given, using the file's date: {dated:%Y-%m-%d}")

    print(f'{len(chunks)} chunks from "{args.title}"')

    if args.dry_run:
        for i, chunk in enumerate(chunks, 1):
            preview = chunk.replace("\n", " ")[:90]
            print(f"  {i:2}. [{len(chunk):4} chars] {preview}")
        return 0

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    written = load(chunks, args.group_id, args.title, dated, dsn)
    print(f"{written} chunks written. Run embed.py to make them searchable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
