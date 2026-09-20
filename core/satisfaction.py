"""Asking members what they think of the bot, once each.

Distinct from the thumb on an answer. That one says whether an answer was
right; this says whether the thing is worth having, which is the question
the group is voting on.

The timing is the whole design. Ask too early and you are interrupting
somebody who has not formed an opinion; ask everybody at once and it reads
as a broadcast. After five questions a person knows what the bot is, so that
is when they are asked, in private, once, and never again.

Nothing here sends anything. The API answers who is due and records what
came back; the worker decides whether to write to somebody, because the rule
that keeps the group quiet lives in one place.
"""

import os

import answer as answer_engine
from psycopg.rows import dict_row

# Questions asked before somebody is worth surveying.
#
# Five is enough to have an opinion and few enough that most active members
# reach it in the first days, which is when the answer is useful to us.
SURVEY_AFTER = int(os.environ.get("SURVEY_AFTER_QUESTIONS", "5"))

DUE_SQL = """
select a.asked_by, count(*) as questions,
       -- Their questions, run together, so the language can be read off
       -- them. Five questions is a far better sample than any one of them:
       -- a two-word question carries almost no signal, and the marker
       -- counting in detect_lang scales with the text it is given.
       string_agg(a.question, ' ') as asked_in
from answers a
where a.group_id = %(group_id)s
  and a.asked_by is not null
  -- Asked in private. The survey is a direct message, and a direct message
  -- to somebody who has only ever used the bot in the group is a stranger
  -- being contacted out of nowhere: the pattern that got the number
  -- restricted for five hours the day it joined a group of 390 people.
  and a.asked_privately
  -- Reused answers are still questions the person asked, so they count. A
  -- copy is excluded only from being reused, not from the person's history.
  and not exists (
    select 1 from satisfaction s
    where s.group_id = a.group_id and s.asked_by = a.asked_by
  )
group by a.asked_by
having count(*) >= %(threshold)s
order by count(*) desc
limit %(limit)s
"""


def due(pool, group_id: str, limit: int = 5) -> list[dict]:
    """Members who have asked enough to have an opinion and never been asked.

    Capped per call, because the first time this runs on an established
    group everybody qualifies at once, and fifty private messages going out
    in one minute is how a number gets reported and blocked.
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                DUE_SQL,
                {"group_id": group_id, "threshold": SURVEY_AFTER, "limit": limit},
            )
            rows = cur.fetchall()

    # The language they ask in, not a setting on the server. Writing to a
    # French speaker in English to ask whether they like the bot answers its
    # own question, and the same mistake in the summaries this morning sent
    # somebody three hundred words of English they had not asked for.
    #
    # The text itself is not returned: the worker needs the verdict, not
    # five of somebody's questions.
    for row in rows:
        row["lang"] = answer_engine.detect_lang(row.pop("asked_in") or "")
    return rows


def mark_asked(pool, group_id: str, user: str, message_id: str | None) -> None:
    """Record that we asked, so we never ask again.

    Written only once the message has actually gone out. Marking first and
    sending after would lose the survey for good on any failure, which is
    exactly the bug the digest had.

    `on conflict do nothing`: the unique index is what makes a second worker,
    or a restart mid-loop, harmless.
    """
    with pool.connection() as conn:
        conn.execute(
            """insert into satisfaction (group_id, asked_by, message_id)
               values (%s, %s, %s)
               on conflict (group_id, asked_by) do nothing""",
            (group_id, user, message_id),
        )


def record(pool, message_id: str, helpful: bool) -> bool:
    """Save a thumb on a survey. False means it was not one.

    The caller needs the distinction: a reaction carries the id of the
    message it sits on and nothing else, so this is what separates a thumb on
    the survey from a thumb on an ordinary answer. Getting it wrong would
    retire whatever answer the person last received, which is the one thing
    the rating on answers must never say by accident.
    """
    with pool.connection() as conn:
        row = conn.execute(
            """update satisfaction
                  set rating = %s, rated_at = now()
                where message_id = %s
                returning id""",
            (1 if helpful else -1, message_id),
        ).fetchone()
    return row is not None


def summary(pool, group_id: str | None = None) -> dict:
    """What members think, for the metrics page.

    The share is computed over the people who answered, not the people who
    were asked. Most will never react, and dividing by everybody asked would
    read as though half the group disliked the bot when in fact half the
    group scrolled past.

    No group_id means every group, which is how the rest of the metrics are
    counted.
    """
    # One static statement rather than a where clause pasted in. The value
    # was a fixed literal and never user input, but SQL assembled by string
    # formatting is the shape of the bug, and the next person to edit this
    # would have had a template to follow. The null check does the same job
    # with the group id as an ordinary parameter.
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """select count(*) as asked,
                          count(rating) as answered,
                          count(*) filter (where rating > 0) as positive
                     from satisfaction
                    where %(group_id)s::text is null
                       or group_id = %(group_id)s""",
                {"group_id": group_id},
            ).fetchone()

    answered = row["answered"] or 0
    return {
        "asked": row["asked"] or 0,
        "answered": answered,
        "positive": row["positive"] or 0,
        "positive_share": round(row["positive"] / answered, 3) if answered else None,
    }
