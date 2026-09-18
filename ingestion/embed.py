"""Embed every message that does not have a vector yet.

Usage:
    export DATABASE_URL=... VOYAGE_API_KEY=...
    python embed.py [--group-id meti-cohort-1] [--batch 128] [--limit 500]

Separate from the parser on purpose: parsing is free and gets re-run often,
embedding costs money and must only ever touch rows that lack a vector.
Safe to interrupt and safe to re-run - it picks up where it stopped.
"""

import argparse
import os
import sys

MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-4-lite")
DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

# The API accepts up to 1000 texts per call. Smaller batches mean a failure
# costs less and progress is visible on a long run.
BATCH = 128


# Fully parameterised, including the optional group filter and the limit: no
# part of this string is ever built from a variable. A NULL group_id means
# "every group", expressed in SQL rather than by assembling a WHERE clause in
# Python, which is how query-building quietly becomes an injection hole.
PENDING_SQL = """
select u.id, u.content
from utterances u
join sources s on s.id = u.source_id
where u.embedding is null
  and (%(group_id)s::text is null or s.group_id = %(group_id)s)
order by u.said_at
limit %(limit)s
"""


def to_pgvector(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group-id", default=None, help="only this group")
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--limit", type=int, default=None, help="stop after N messages")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1
    if not os.environ.get("VOYAGE_API_KEY"):
        print("VOYAGE_API_KEY is not set.", file=sys.stderr)
        return 1

    import psycopg
    import voyageai

    voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

    done = tokens = 0
    with psycopg.connect(dsn) as conn:
        while True:
            take = args.batch
            if args.limit is not None:
                take = min(take, args.limit - done)
                if take <= 0:
                    break

            with conn.cursor() as cur:
                cur.execute(PENDING_SQL, {"group_id": args.group_id, "limit": take})
                rows = cur.fetchall()

            if not rows:
                break

            result = voyage.embed(
                [content for _, content in rows],
                model=MODEL,
                # These are the stored messages, not the question asked about
                # them. Voyage embeds the two roles differently.
                input_type="document",
                output_dimension=DIM,
            )
            tokens += result.total_tokens

            with conn.cursor() as cur:
                cur.executemany(
                    "update utterances set embedding = %s::vector where id = %s",
                    [
                        (to_pgvector(vec), row_id)
                        # strict: if the API ever returned a different number
                        # of vectors than we sent texts, pairing them by
                        # position would attach embeddings to the wrong
                        # messages and poison every search built on them.
                        # Failing loudly is the only safe behaviour.
                        for (row_id, _), vec in zip(rows, result.embeddings, strict=True)
                    ],
                )
            # Commit each batch: an interrupted run keeps what it paid for.
            conn.commit()

            done += len(rows)
            print(f"  {done} embedded", flush=True)

    print(f"Done: {done} messages, {tokens} tokens with {MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
