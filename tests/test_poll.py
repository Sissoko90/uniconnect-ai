"""The nightly poll, and the morning digest that covers a whole day.

Two things the bot does uninvited, and the only two. What happened, at 05:00
in Bamako, and one question at 23:00. Mali is UTC+0 all year, so the server
clock and the group's clock are the same one.
"""

from datetime import date

import poll
import recap


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePool:
    def __init__(self, rows=None):
        self.cur = FakeCursor(rows or [])
        self.written = []

    def connection(self):
        return self

    def cursor(self, row_factory=None):
        return self.cur

    def execute(self, sql, params=()):
        self.written.append((sql, params))
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_vote_is_recorded():
    pool = FakePool()

    assert poll.record(pool, "meti-cohort-1", "POLL1", "2026-09-22", "+22300000000", "yes")
    assert pool.written


def test_anything_but_yes_or_no_is_refused():
    """The poll is bilingual and a voter tapped a button spelled in one of
    the two languages. The worker resolves the button to a meaning before it
    gets here, so anything else means the two sides have drifted apart and
    writing it would put nonsense in the table."""
    pool = FakePool()

    assert not poll.record(pool, "meti-cohort-1", "POLL1", "2026-09-22", "+223", "oui")
    assert not pool.written


def test_the_share_is_counted_over_the_people_who_voted():
    """Never over the group. Most of 390 people will not vote, and dividing
    by all of them would read as though the group disliked the bot when in
    fact it scrolled past."""
    pool = FakePool(
        [
            {"poll_day": date(2026, 9, 22), "yes": 18, "no": 2, "votes": 20},
            {"poll_day": date(2026, 9, 21), "yes": 5, "no": 5, "votes": 10},
        ]
    )

    out = poll.results(pool, "meti-cohort-1")

    assert out["days"][0]["yes_share"] == 0.9
    assert out["days"][1]["yes_share"] == 0.5
    assert out["votes"] == 30
    assert out["yes"] == 23
    # Serialised, because this is answered as JSON to the worker.
    assert out["days"][0]["poll_day"] == "2026-09-22"


def test_an_evening_nobody_voted_on_has_no_share():
    """Zero out of zero is not zero per cent, and printing 0% under a poll
    nobody answered would be a lie about what the group thinks."""
    pool = FakePool([{"poll_day": date(2026, 9, 22), "yes": 0, "no": 0, "votes": 0}])

    assert poll.results(pool, "meti-cohort-1")["days"][0]["yes_share"] is None


# --------------------------------------------------------------------------
# The morning digest
# --------------------------------------------------------------------------


def test_the_digest_length_is_a_ceiling_the_caller_sets():
    """The morning post covers a whole day rather than a quiet interval, so
    it is allowed more than the five lines the default gives."""
    five = recap.DIGEST_SYSTEM.format(lines=5)
    eight = recap.DIGEST_SYSTEM.format(lines=8)

    assert "At most 5 lines" in five
    assert "At most 8 lines" in eight
    # "At most", never "exactly": a quiet day still gets one line, and the
    # prompt says so rather than padding to the ceiling.
    assert "padding to 8" in eight


def test_the_prompt_survives_being_formatted():
    """It is a long piece of English with a citation example in it, [7], and
    a stray brace anywhere in it would make format() raise at the moment the
    morning post is being written."""
    assert recap.DIGEST_SYSTEM.format(lines=recap.MORNING_DIGEST_LINES)
