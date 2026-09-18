"""Rate limits and a spend cap.

153 people, roughly one and a half cents a question, and nothing in WhatsApp
that stops somebody asking five hundred times overnight - or two bots
answering each other in a loop until the month's budget is gone.

Everything here is measured against the answers table rather than kept in
memory, so the limits survive a restart and are visible in the same place as
the metrics. Postgres does the counting; there is no second piece of
infrastructure to run.

The design choice worth knowing: when the cap is reached the API does not go
silent. It drops to search without generation and says so. On the day the
group votes, a blunter answer is worth far more than no answer.
"""

import os

# Per person. Generous for somebody genuinely using the bot, low enough that
# one member cannot spend the group's budget on their own.
MAX_QUESTIONS_PER_HOUR = int(os.environ.get("MAX_QUESTIONS_PER_HOUR", "20"))

# The same person sending the same words twice in a few seconds is a double
# tap, a retry, or a loop - never a second question.
REPEAT_WINDOW_SECONDS = int(os.environ.get("REPEAT_WINDOW_SECONDS", "30"))

# Dollars per day, across everybody. Past it, generation is switched off and
# the bot falls back to search alone until midnight UTC.
DAILY_SPEND_CAP_USD = float(os.environ.get("DAILY_SPEND_CAP_USD", "10"))

# Catalogue prices for the model in CLAUDE_MODEL, per million tokens. Kept in
# the environment so a model or price change does not need a code change.
PRICE_INPUT_PER_MTOK = float(os.environ.get("PRICE_INPUT_PER_MTOK", "5"))
PRICE_OUTPUT_PER_MTOK = float(os.environ.get("PRICE_OUTPUT_PER_MTOK", "25"))

TOO_MANY = {
    "fr": (
        "Tu as posé beaucoup de questions dans la dernière heure. "
        "Réessaie dans un moment — je suis toujours là."
    ),
    "en": (
        "That is a lot of questions in the last hour. "
        "Try again shortly, I am not going anywhere."
    ),
}


def questions_last_hour(pool, user: str) -> int:
    with pool.connection() as conn:
        return conn.execute(
            """select count(*) from answers
               where asked_by = %s and asked_at > now() - interval '1 hour'""",
            (user,),
        ).fetchone()[0]


def rate_limited(pool, user: str) -> bool:
    return questions_last_hour(pool, user) >= MAX_QUESTIONS_PER_HOUR


def recent_identical(pool, user: str, question: str) -> dict | None:
    """The same person, the same words, seconds ago.

    Catches a double tap, a worker retry, and the beginning of a loop between
    two bots. Returned straight from the table, so it costs nothing: no
    embedding, no model call.
    """
    with pool.connection() as conn:
        row = conn.execute(
            """select answer, cited_ids from answers
               where asked_by = %s
                 and question = %s
                 and asked_at > now() - make_interval(secs => %s)
               order by asked_at desc limit 1""",
            (user, question, REPEAT_WINDOW_SECONDS),
        ).fetchone()

    return {"answer": row[0], "cited_ids": row[1]} if row else None


def spend_today_usd(pool) -> float:
    """What generation has cost since midnight UTC, from reported usage."""
    with pool.connection() as conn:
        row = conn.execute(
            """select coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0)
               from answers
               where asked_at >= date_trunc('day', now() at time zone 'utc')""",
        ).fetchone()

    input_tokens, output_tokens = row
    return (
        input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK
    ) / 1_000_000


def over_spend_cap(pool) -> bool:
    if DAILY_SPEND_CAP_USD <= 0:
        return False  # 0 or less disables the cap entirely
    return spend_today_usd(pool) >= DAILY_SPEND_CAP_USD


def assert_budget(pool) -> None:
    """Refuse an endpoint that has no cheaper mode to fall back to.

    /ask degrades: past the cap it answers from search alone. A digest, a
    recap or a timeline has no such half-measure - there is no useful version
    of them without a model - so they stop until midnight instead.

    Applying this everywhere matters more than it looks. The cap was written
    for /ask and every endpoint added afterwards could call a paid model with
    no limit at all, which meant the guardrail could simply be walked around
    by asking for a digest in a loop.
    """
    from fastapi import HTTPException

    if over_spend_cap(pool):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Daily spend cap of ${DAILY_SPEND_CAP_USD} reached. "
                "Questions are still answered from search; this resumes at midnight UTC."
            ),
        )
