"""A recap must never report on the bot instead of on the group.

Asked for a summary in a private chat, the bot answered:

    Nothing of consequence happened today, just a request for a summary and
    two replies about it.

Two faults, both visible in that one line. The unread window was three
messages long, because last_seen_at moves forward whenever a person speaks
and this person had spoken minutes earlier, so "what did I miss" was read as
"what happened in the last few minutes". And those three messages were
people trying the bot out, which is not something the group discussed.
"""

from datetime import UTC, datetime, timedelta

import catchup
import intent


def _rows(n: int, content: str = "The deadline moved to Thursday."):
    return [{"content": content, "author": "+22300000000"} for _ in range(n)]


def test_a_handful_of_messages_from_today_is_not_a_gap():
    """They never left. The caller hands them the day's digest, which covers
    the same window and the rest of the day with it."""
    ten_minutes_ago = datetime.now(UTC) - timedelta(minutes=10)

    assert catchup._too_thin(_rows(3), ten_minutes_ago)


def test_a_real_backlog_is_still_briefed():
    yesterday = datetime.now(UTC) - timedelta(hours=20)

    assert not catchup._too_thin(_rows(40), yesterday)


def test_a_quiet_week_away_is_still_briefed():
    """Three messages in a week is a week to catch up on, and the day's
    digest would not contain them. Only the recent window is discarded."""
    last_week = datetime.now(UTC) - timedelta(days=7)

    assert not catchup._too_thin(_rows(3), last_week)


def test_chatter_at_the_bot_is_not_group_content():
    for text in [
        "@ask recap",
        "recap",
        "merci",
        "thanks 🙏",
        "test",
        "ok merci",
        "bonjour",
        "👍",
        "Bravo",
        "@ask",
    ]:
        assert intent.is_bot_talk(text), text


def test_what_the_group_actually_said_is_kept():
    """The filter decides what a summary reads, so a false positive here
    deletes a decision from somebody's briefing."""
    for text in [
        "merci, et quelle est la date limite ?",
        "ok Thursday works for me",
        "The submission deadline is Thursday 24 September.",
        "Diane said the testing slot is at 3PM",
        "test event is on Friday at the UniPods lab",
        "recap of the call: we ship on Sunday",
    ]:
        assert not intent.is_bot_talk(text), text


def test_a_window_of_nothing_but_bot_chatter_empties_out():
    rows = [
        {"content": "@ask recap"},
        {"content": "merci"},
        {"content": "👍"},
    ]

    assert intent.worth_summarising(rows) == []


def test_the_citation_numbers_follow_the_filtered_list():
    """The model cites [1], [2] by position in the list it was given, so the
    filter has to run before the list is formatted, not after."""
    rows = [
        {"content": "merci"},
        {"content": "The deadline moved to Thursday."},
        {"content": "ok"},
        {"content": "Diane confirmed the 3PM slot."},
    ]

    kept = intent.worth_summarising(rows)

    assert [row["content"] for row in kept] == [
        "The deadline moved to Thursday.",
        "Diane confirmed the 3PM slot.",
    ]
