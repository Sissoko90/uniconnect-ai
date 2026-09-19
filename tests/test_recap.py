"""Trimming messages for the overview without losing what people ask for.

Nine hundred messages have to fit in one prompt, so the long ones get cut.
Cutting them blindly threw away exactly the thing the group cannot find on
its own: a Teams meeting link runs past two hundred characters and sits at
the end of the message announcing the session, so it was always the part that
went. Somebody asked for a summary "et les liens du meet passé" and the links
had been dropped before the model ever saw them.
"""

import recap

LINK = (
    "https://teams.microsoft.com/l/meetup-join/19%3ameeting_ABC/0"
    "?context=%7b%22Tid%22%3a%22aaa%22%2c%22Oid%22%3a%22bbb%22%7d"
)


def test_a_short_message_is_untouched():
    assert recap.shorten_keeping_links("Open Hour at 3PM") == "Open Hour at 3PM"


def test_a_link_past_the_cut_is_kept():
    message = "Open Hour today. " + "x" * 700 + " Join here: " + LINK

    out = recap.shorten_keeping_links(message)

    assert LINK in out
    assert out.startswith("Open Hour today.")


def test_a_link_straddling_the_cut_is_kept_whole():
    """Half a URL is worse than no URL: it looks like an answer and does
    not work."""
    padding = "x" * (recap.OVERVIEW_CHARS_PER_MESSAGE - 20)
    message = padding + " " + LINK

    out = recap.shorten_keeping_links(message)

    assert LINK in out
    assert out.count("meetup-join") == 1, "the truncated half must not survive too"


def test_several_links_are_all_kept():
    message = "agenda " + "x" * 700 + f" {LINK} and also https://forms.gle/abc123"

    out = recap.shorten_keeping_links(message)

    assert LINK in out
    assert "https://forms.gle/abc123" in out


def test_a_long_message_without_links_is_just_cut():
    message = "x" * 900

    out = recap.shorten_keeping_links(message)

    assert out.endswith("...")
    assert len(out) == recap.OVERVIEW_CHARS_PER_MESSAGE + 3
