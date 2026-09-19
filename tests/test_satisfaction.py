"""Asking members what they think of the bot, once each.

Distinct from the thumb on an answer, and the distinction is the fragile
part: a reaction carries the id of the message it sits on and nothing else.
Read the wrong way, a thumb meant for the bot as a whole retires whatever
answer that person last received, which is the one thing the rating on
answers must never say by accident.
"""

import satisfaction


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.sql = None
        self.params = None

    def execute(self, sql, params=()):
        self.sql, self.params = sql, params
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row else []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePool:
    def __init__(self, row=None):
        self.cur = FakeCursor(row)

    def connection(self):
        return self

    def cursor(self, row_factory=None):
        return self.cur

    def execute(self, sql, params=()):
        return self.cur.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_thumb_on_a_survey_is_recognised():
    pool = FakePool(row=("some-uuid",))

    assert satisfaction.record(pool, "WA-MESSAGE-ID", helpful=True) is True
    assert pool.cur.params == (1, "WA-MESSAGE-ID")


def test_a_thumb_on_an_ordinary_answer_is_not_a_survey():
    """False is the signal that tells the worker to go and rate the answer
    instead. An exception or a 404 here would make an ordinary reaction look
    like a failure."""
    pool = FakePool(row=None)

    assert satisfaction.record(pool, "SOME-OTHER-MESSAGE", helpful=False) is False


def test_a_thumb_down_is_stored_as_minus_one():
    pool = FakePool(row=("some-uuid",))

    satisfaction.record(pool, "WA-MESSAGE-ID", helpful=False)

    assert pool.cur.params[0] == -1


def test_the_share_is_over_the_people_who_answered():
    """Most people never react. Dividing by everybody asked would report a
    group that ignored the survey as a group that disliked the bot."""
    pool = FakePool(row={"asked": 40, "answered": 10, "positive": 9})

    out = satisfaction.summary(pool)

    assert out["positive_share"] == 0.9
    assert out["asked"] == 40


def test_no_answers_yet_is_not_zero_percent():
    """Nobody has answered, which is not the same as nobody liking it, and
    the metrics page must not print 0% on the day it launches."""
    pool = FakePool(row={"asked": 3, "answered": 0, "positive": 0})

    assert satisfaction.summary(pool)["positive_share"] is None


def test_asked_is_recorded_with_the_message_it_was_sent_as():
    """The id is what makes the reaction resolvable later. Without it the
    survey can be sent and never answered."""
    pool = FakePool(row=None)

    satisfaction.mark_asked(pool, "meti-cohort-1", "22370000000@s.whatsapp.net", "WA-ID")

    assert pool.cur.params == ("meti-cohort-1", "22370000000@s.whatsapp.net", "WA-ID")
    assert "on conflict" in pool.cur.sql, "asking the same person twice must be impossible"
