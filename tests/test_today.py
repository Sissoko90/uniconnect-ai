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


# --------------------------------------------------------------------------
# The same words are not always the same question
# --------------------------------------------------------------------------


def test_a_question_about_tomorrow_is_never_reused():
    """Asked twice ninety seconds apart, "what session are we having
    tomorrow" came back identical both times: the second was served from
    the stored answer, so the fix deployed in between could not reach it.

    The visible symptom. The quiet one is an answer about Tuesday, reused on
    Thursday, with nothing about it to suggest it is stale."""
    import intent

    for question in [
        "What session are we having tomorrow and what's the time?",
        "what's on today",
        "quelle session avons-nous demain ?",
        "c'est quoi le programme cette semaine",
        "what is coming up next week",
        "y a-t-il une réunion ce soir",
    ]:
        assert intent.is_time_sensitive(question), question


def test_a_question_with_a_fixed_answer_is_still_reused():
    """Reuse is worth keeping. A deadline is a date: the answer is the same
    today, tomorrow and in a fortnight, and paying for it twice is waste."""
    import intent

    for question in [
        "what is the submission deadline",
        "quelle est la date limite",
        "who do I contact about Wadhwani",
        "what is the prize",
        "how many people can be on a team",
    ]:
        assert not intent.is_time_sensitive(question), question
