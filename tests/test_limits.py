"""The spend cap is only as good as its arithmetic.

These check the pricing maths and the switches around it, without a database:
the queries themselves are exercised by the schema job in CI.
"""

import limits


def test_price_is_computed_from_reported_tokens(monkeypatch):
    """One million input tokens at $5 and one million output at $25 is $30.

    Deliberately a round number: if this ever drifts, the cap is protecting
    the wrong amount of money.
    """
    monkeypatch.setattr(limits, "PRICE_INPUT_PER_MTOK", 5.0)
    monkeypatch.setattr(limits, "PRICE_OUTPUT_PER_MTOK", 25.0)

    class FakePool:
        def connection(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return (1_000_000, 1_000_000)

    assert limits.spend_today_usd(FakePool()) == 30.0


def test_a_cap_of_zero_disables_it(monkeypatch):
    """Zero means "no cap", not "cap everything" - which would silently take
    generation offline the moment somebody mistyped the variable."""
    monkeypatch.setattr(limits, "DAILY_SPEND_CAP_USD", 0)

    # No database access at all: the switch short-circuits before querying.
    assert limits.over_spend_cap(None) is False


def test_the_rate_limit_message_exists_in_both_languages():
    assert set(limits.TOO_MANY) == {"fr", "en"}
    assert all(text.strip() for text in limits.TOO_MANY.values())


def test_defaults_are_sane():
    """A limit nobody can reach protects nothing; one everybody hits makes the
    bot useless on the day it is being judged."""
    assert 5 <= limits.MAX_QUESTIONS_PER_HOUR <= 100
    assert 5 <= limits.REPEAT_WINDOW_SECONDS <= 300
