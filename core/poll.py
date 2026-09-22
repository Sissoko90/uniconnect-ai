"""The nightly poll: does the group want this bot.

Distinct from satisfaction.py, which asks one person once, in private, after
they have asked five questions. This asks everybody, every evening, in the
group, and WhatsApp itself shows the running tally to all 390 members.

That visibility is the point rather than a side effect. The hackathon is
decided by a vote of the whole group, so the group should be able to see what
it thinks before it is asked to vote, and we should have to live with the
answer in public. A survey only we can read would be worth less to them and
more to us, which is the wrong way round.

Nothing here sends anything. The worker posts the poll and forwards the
votes; this records them and counts them.
"""

from psycopg.rows import dict_row

# What a vote can say. The poll is written in both languages and somebody
# tapped a button spelled in one of them, so the worker resolves the button
# to a meaning before it gets here and this rejects anything else.
CHOICES = ("yes", "no")

RECORD_SQL = """
insert into poll_votes (group_id, poll_id, poll_day, voter, choice)
values (%(group_id)s, %(poll_id)s, %(day)s, %(voter)s, %(choice)s)
-- Changing your mind is allowed, and WhatsApp sends the whole new selection
-- when you do. The last thing somebody said is what they think.
on conflict (poll_id, voter)
do update set choice = excluded.choice, voted_at = now()
"""

RESULTS_SQL = """
select poll_day,
       count(*) filter (where choice = 'yes') as yes,
       count(*) filter (where choice = 'no') as no,
       count(*) as votes
from poll_votes
where group_id = %(group_id)s
group by poll_day
order by poll_day desc
limit %(limit)s
"""


def record(pool, group_id: str, poll_id: str, day: str, voter: str, choice: str) -> bool:
    """Save one vote. False means the choice was not one of ours."""
    if choice not in CHOICES:
        return False

    with pool.connection() as conn:
        conn.execute(
            RECORD_SQL,
            {
                "group_id": group_id,
                "poll_id": poll_id,
                "day": day,
                "voter": voter,
                "choice": choice,
            },
        )
    return True


def withdraw(pool, poll_id: str, voter: str) -> None:
    """Somebody untapped their answer.

    WhatsApp sends an empty selection for this, and it has to delete the row
    rather than be ignored. Left in place, a person who changed their mind to
    "no opinion" would still be counted as having said yes.
    """
    with pool.connection() as conn:
        conn.execute(
            "delete from poll_votes where poll_id = %s and voter = %s",
            (poll_id, voter),
        )


VOTES_SQL = """
select v.poll_day, v.voter, v.choice, v.voted_at,
       -- The name the group knows them by, when we have it. A column of
       -- phone numbers is unreadable, and this is the one page where
       -- knowing who said what is the point.
       coalesce(p.display_name, v.voter) as voter_name
from poll_votes v
left join people p
  on p.group_id = v.group_id and p.handle_norm = normalize_handle(v.voter)
where v.group_id = %(group_id)s
  and (%(day)s::date is null or v.poll_day = %(day)s::date)
order by v.poll_day desc, v.voted_at desc
limit %(limit)s
"""


def votes(pool, group_id: str, day: str | None = None, limit: int = 500) -> list[dict]:
    """Every vote, one row each, most recent first.

    Named voters and not just a count, because a WhatsApp poll already shows
    the group who tapped what. Hiding it here would protect nothing and would
    leave us unable to answer the one question worth asking the morning
    after: which of the people who tested it said no.
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                VOTES_SQL, {"group_id": group_id, "day": day, "limit": limit}
            )
            rows = cur.fetchall()

    for row in rows:
        row["poll_day"] = row["poll_day"].isoformat()
        row["voted_at"] = row["voted_at"].isoformat().replace("+00:00", "Z")
    return rows


def results(pool, group_id: str, limit: int = 14) -> dict:
    """Each evening's tally, most recent first.

    By day rather than in total, because the answer to "does the group want
    this" is a trend and not a number. One good evening proves nothing and
    one bad one is not a verdict either.
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(RESULTS_SQL, {"group_id": group_id, "limit": limit})
            days = cur.fetchall()

    for row in days:
        row["poll_day"] = row["poll_day"].isoformat()
        # Computed over the people who voted, never over the group. Most of
        # 390 people will not vote, and dividing by all of them would read as
        # though the group disliked the bot when in fact it scrolled past.
        row["yes_share"] = round(row["yes"] / row["votes"], 3) if row["votes"] else None

    return {
        "days": days,
        "votes": sum(row["votes"] for row in days),
        "yes": sum(row["yes"] for row in days),
    }
