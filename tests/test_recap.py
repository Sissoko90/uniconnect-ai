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


# --------------------------------------------------------------------------
# Not paying twice for the same overview
# --------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params=()):
        return self

    def fetchone(self):
        return self.row

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


def cached(utterances):
    return {"text": "the group explained", "built_at": None, "utterances": utterances}


def test_a_cached_overview_is_reused_while_the_history_has_barely_moved():
    """It costs about 25 cents and a minute of waiting, and its subject is
    months of history. A hundred and fifty members asking once each would be
    forty dollars for a hundred and fifty near-identical texts."""
    pool = FakePool(row=cached(900))

    assert recap._cached_overview(pool, "meti-cohort-1", "fr", 905) is not None


def test_enough_new_messages_make_it_stale():
    """Staleness is measured in messages, not minutes: what makes this text
    wrong is the group having said things it does not mention. A quiet week
    should not expire an accurate overview, and a busy hour should."""
    pool = FakePool(row=cached(900))

    assert recap._cached_overview(pool, "meti-cohort-1", "fr", 1000) is None


def test_nothing_cached_yet():
    assert recap._cached_overview(FakePool(row=None), "meti-cohort-1", "fr", 900) is None
