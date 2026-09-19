"""Telling somebody, privately, that the group is waiting on them.

The brief opens with "people miss messages". Everything else in this system
answers that passively: you have to remember the bot exists and think to ask.
This is the one place it comes to you.

Three rules make it safe to do that at all, and they are not negotiable:

  - Only in a direct message. The group never hears any of this.
  - Only to people who have already spoken to the bot. Messaging somebody who
    never asked for anything is how a WhatsApp number gets blocked, and it is
    also just rude.
  - Only once per mention, and only after a grace period. Somebody who is
    reading the group right now does not need to be told they were mentioned.
"""

import os

from psycopg.rows import dict_row

# Long enough that somebody actually in the chat sees it themselves first.
GRACE_MINUTES = int(os.environ.get("ALERT_GRACE_MINUTES", "20"))

# Past this the moment has gone; telling them two days later is noise.
MAX_AGE_HOURS = int(os.environ.get("ALERT_MAX_AGE_HOURS", "36"))

RECORD_SQL = """
insert into mentions (utterance_id, user_norm)
select %(utterance_id)s, normalize_handle(%(handle)s)
on conflict (utterance_id, user_norm) do nothing
"""

# The whole policy, in one statement.
PENDING_SQL = """
select m.id,
       m.user_norm,
       u.said_at,
       u.content,
       coalesce(author_p.display_name, u.author) as from_author,
       coalesce(target_p.display_name, m.user_norm) as to_name,
       target_p.handle as to_handle
from mentions m
join utterances u on u.id = m.utterance_id
join sources s on s.id = u.source_id
left join people author_p
  on author_p.group_id = s.group_id and author_p.handle_norm = u.author_norm
left join people target_p
  on target_p.group_id = s.group_id and target_p.handle_norm = m.user_norm
where m.notified_at is null
  and s.group_id = %(group_id)s
  -- Old enough that they have had a chance to see it themselves.
  and u.said_at < now() - make_interval(mins => %(grace)s)
  -- Recent enough to still matter.
  and u.said_at > now() - make_interval(hours => %(max_age)s)
  -- They have used the bot before. This is the opt-in: we only write to
  -- people who have already started a conversation with us.
  and exists (
      select 1 from answers a
      where normalize_handle(a.asked_by) = m.user_norm
  )
  -- And they have not spoken since, which would mean they saw it.
  and not exists (
      select 1
      from utterances later
      join sources ls on ls.id = later.source_id
      where ls.group_id = s.group_id
        and later.author_norm = m.user_norm
        and later.said_at > u.said_at
  )
order by u.said_at
limit %(limit)s
"""


def record(pool, utterance_id: str, handles: list[str]) -> int:
    """Note that these people were named in this message."""
    if not handles:
        return 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                RECORD_SQL,
                [{"utterance_id": utterance_id, "handle": h} for h in handles],
            )
            return cur.rowcount


def pending(pool, group_id: str, limit: int = 50) -> list[dict]:
    """Who should be told, and about what. The worker polls this."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                PENDING_SQL,
                {
                    "group_id": group_id,
                    "grace": GRACE_MINUTES,
                    "max_age": MAX_AGE_HOURS,
                    "limit": limit,
                },
            )
            rows = cur.fetchall()

    return [
        {
            "id": str(r["id"]),
            # Digits only, always. The worker turns this into a JID, and
            # people.handle is whatever spelling we were first given: a vCard
            # writes "+256 787 004799", which would have produced
            # "+256 787 004799@s.whatsapp.net" and failed on every alert to
            # anybody whose name came from an export.
            "to": r["user_norm"],
            "to_name": r["to_name"],
            "from_author": r["from_author"],
            "said_at": r["said_at"].isoformat().replace("+00:00", "Z"),
            "excerpt": r["content"].strip()[:280],
        }
        for r in rows
    ]


def mark_sent(pool, ids: list[str]) -> int:
    """Called by the worker once it has actually delivered them."""
    if not ids:
        return 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update mentions set notified_at = now() where id = any(%s::uuid[])",
                (ids,),
            )
            return cur.rowcount
