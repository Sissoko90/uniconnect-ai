"""Live ingestion: the messages arriving now, not an export from last week.

Without this the database is frozen at the moment somebody last exported the
chat. The bot would answer Monday's "what did I miss since Friday" from a
history that stops on Friday afternoon, and get more wrong every day it runs -
which is exactly the week the group is voting.

The worker posts every message it sees here, whether or not the bot was
mentioned. That is the "silent in the group" rule doing real work: reading
everything, writing almost nothing.

Three things happen per message, all of them idempotent:
  - the message is stored, de-duplicated by the unique index
  - if WhatsApp gave us the sender's name, it fills in the people table
  - the sender's last_seen_at moves forward, because somebody who is talking
    has by definition seen the group
"""

import re
from datetime import datetime

import embeddings

# A WhatsApp JID: "22997426540@s.whatsapp.net", or "…@lid" on newer accounts.
JID = re.compile(r"^(\d{6,20})@")

# One chat source per group, shared with the export parser, so a message that
# arrives live and the same message in a later export land in the same place
# and de-duplicate against each other.
SOURCE_SQL = """
insert into sources (kind, platform, group_id, title, occurred_at)
values ('chat', 'whatsapp', %(group_id)s, %(title)s, %(occurred_at)s)
on conflict (platform, group_id) where kind = 'chat'
do update set
  -- Never overwrite a title the parser gave this group with our placeholder.
  title = coalesce(sources.title, excluded.title),
  occurred_at = least(sources.occurred_at, excluded.occurred_at)
returning id
"""

INSERT_SQL = """
insert into utterances (source_id, author, content, said_at, permalink, lang)
values (%s, %s, %s, %s, %s, %s)
on conflict (source_id, author, said_at, md5(content)) do nothing
"""

PEOPLE_SQL = """
insert into people (group_id, handle, display_name, origin)
values (%s, %s, %s, 'pushname')
on conflict (group_id, handle_norm)
do update set display_name = excluded.display_name,
              origin = excluded.origin,
              updated_at = now()
"""

# Normalised here rather than by the caller, so a mention written as a JID and
# the same person seen in an export as a phone number are one person.
MENTION_SQL = """
insert into mentions (utterance_id, user_norm)
values (%(utterance_id)s, normalize_handle(%(handle)s))
on conflict (utterance_id, user_norm) do nothing
"""

SEEN_SQL = """
insert into user_state (user_id, display_name, last_seen_at, updated_at)
values (%s, %s, %s, now())
on conflict (user_id) do update set
  -- greatest, not excluded: messages can arrive out of order after a
  -- reconnect, and a bookmark must never travel backwards or the member is
  -- told they missed things they have already read.
  last_seen_at = greatest(user_state.last_seen_at, excluded.last_seen_at),
  display_name = coalesce(excluded.display_name, user_state.display_name),
  updated_at = now()
"""


def readable_author(handle: str) -> str:
    """Store a JID the way the chat export spells the same person.

    "22997426540@s.whatsapp.net" becomes "+22997426540". Without this the raw
    JID would be printed in citations - the masking that hides phone numbers
    does not recognise it - and the same person would look like two people
    depending on whether they were seen live or in an export.
    """
    handle = (handle or "").strip()
    match = JID.match(handle)
    return f"+{match.group(1)}" if match else handle


def store(pool, group_id: str, messages: list[dict]) -> dict:
    """Returns how many were new. Safe to call with messages already stored."""
    if not messages:
        return {"received": 0, "stored": 0}

    times = [m["said_at"] for m in messages]

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                SOURCE_SQL,
                {"group_id": group_id, "title": group_id, "occurred_at": min(times)},
            )
            source_id = cur.fetchone()[0]

            cur.executemany(
                INSERT_SQL,
                [
                    (
                        source_id,
                        readable_author(m["author"]),
                        m["content"],
                        m["said_at"],
                        m.get("permalink"),
                        m.get("lang"),
                    )
                    for m in messages
                ],
            )
            stored = cur.rowcount

            # Names, for free, as people speak. This is the only source that
            # covers members who joined after the export was taken.
            named = [m for m in messages if m.get("author_name")]
            if named:
                cur.executemany(
                    PEOPLE_SQL,
                    [(group_id, m["author"], m["author_name"]) for m in named],
                )

            # Talking means having seen the group.
            cur.executemany(
                SEEN_SQL,
                [(m["author"], m.get("author_name"), m["said_at"]) for m in messages],
            )

            # Who was named in what. Looked up rather than returned by the
            # insert, so a message we already had still registers its
            # mentions - a worker replaying history after a reconnect must
            # not lose the fact that somebody was called on.
            mentioned = 0
            for m in messages:
                if not m.get("mentions"):
                    continue
                cur.execute(
                    """select id from utterances
                       where source_id = %s and author = %s
                         and said_at = %s and md5(content) = md5(%s)""",
                    (source_id, readable_author(m["author"]), m["said_at"], m["content"]),
                )
                row = cur.fetchone()
                if row:
                    cur.executemany(
                        MENTION_SQL,
                        [{"utterance_id": row[0], "handle": h} for h in m["mentions"]],
                    )
                    mentioned += len(m["mentions"])

    return {"received": len(messages), "stored": stored, "mentions": mentioned}


PENDING_SQL = """
select id, content from utterances
where embedding is null
order by said_at desc
limit %s
"""


def embed_pending(pool, batch: int = 64) -> int:
    """Give vectors to messages that arrived since the last pass.

    Newest first, deliberately: a question about what was just said is the
    most likely one to be asked, and a message with no vector is still
    findable by full text search in the meantime.

    Returns how many were embedded. Any failure returns 0 and leaves the rows
    for the next pass - embedding is never worth an outage.
    """
    if not embeddings.available():
        return 0

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(PENDING_SQL, (batch,))
                rows = cur.fetchall()

                if not rows:
                    return 0

                vectors = embeddings.embed_documents([content for _, content in rows])
                if vectors is None:
                    return 0

                cur.executemany(
                    "update utterances set embedding = %s::vector where id = %s",
                    [
                        (embeddings.to_pgvector(vec), row_id)
                        for (row_id, _), vec in zip(rows, vectors, strict=True)
                    ],
                )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - a failed pass retries in a minute
        print(f"background embedding pass failed: {exc}", flush=True)
        return 0


def parse_time(value) -> datetime:
    """WhatsApp gives seconds since the epoch; JSON may carry either that or
    an ISO string. Both end up as an aware UTC datetime."""
    from datetime import UTC

    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
