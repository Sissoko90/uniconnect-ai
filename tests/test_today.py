"""The bot did not know what day it was.

From the group:

    @ask what session are we having tomorrow and what's the time?

    "Tomorrow" in that message means 15 September 2026, since it was posted
    on 14 September. The Wadhwani session was at 3PM CAT, link: ...

Asked on 22 September. The reasoning is careful and the answer is eight
days stale: the model found a message saying "tomorrow at 3PM", resolved
that word against the message's own date, and reported it. It had no way to
know that the person asking meant the day after today, because nothing in
the prompt said what today was.

Every relative word in this group's vocabulary has the same problem:
tomorrow, this week, next Monday, ce soir, demain.
"""

from datetime import UTC, datetime

import answer as answer_engine
import catchup
import recap


def test_the_date_is_stated_in_a_form_a_reader_would_recognise():
    said = answer_engine.today_line()
    now = datetime.now(UTC)

    assert said.startswith("Today is ")
    assert f"{now:%Y}" in said
    # The weekday matters as much as the date: "next Monday" cannot be
    # resolved from a number alone.
    assert f"{now:%A}" in said


def test_it_is_actually_today():
    """A stale or hardcoded date would be worse than none, because it would
    look authoritative."""
    assert f"{datetime.now(UTC):%d %B %Y}" in answer_engine.today_line()


def test_the_question_decides_what_tomorrow_means():
    """The rule that was missing. Relative words in the question resolve
    against today; the same words inside a message resolve against that
    message's own date."""
    assert "TODAY'S DATE" in answer_engine.SYSTEM
    assert "never to the date of a message you are reading" in answer_engine.SYSTEM


def test_saying_nothing_is_known_beats_answering_about_another_day():
    """The specific failure. Naming a different date's session and letting
    the reader assume it is theirs means they do not check, and they miss
    it."""
    assert "name that date" in answer_engine.SYSTEM


def test_the_digest_and_the_briefing_are_told_too():
    """They read the same messages and carry the same words. A digest that
    repeats "tomorrow" from a message sent last week moves a deadline."""
    assert "Today's date is given with the request" in recap.DIGEST_SYSTEM
    assert "Today's date is given below" in catchup.SYSTEM
