"""Two rules the bot must never break, checked here because both are easy to
regress and neither fails loudly: it must not print a member's full phone
number into the group, and it must answer in the language it was asked in.
"""

from datetime import UTC

import answer


def test_unknown_numbers_are_masked():
    """A citation goes into a group of 153 people. Until somebody tells us
    this person's name, we show enough to recognise them and no more."""
    assert answer.display_author("+229 90 00 00 42") == "+229…42"
    assert answer.display_author("+250 70 00 00 55") == "+250…55"


def test_known_names_are_left_alone():
    assert answer.display_author("Awa") == "Awa"
    assert answer.display_author("Nadia Traoré") == "Nadia Traoré"


def test_a_name_containing_digits_is_not_mistaken_for_a_number():
    assert answer.display_author("kofi.ai") == "kofi.ai"


def test_language_follows_the_question():
    assert answer.detect_lang("Quel est le lien du call ?") == "fr"
    assert answer.detect_lang("What is the link to the call?") == "en"


def test_the_no_source_reply_exists_in_both_languages():
    """The bot refusing to invent an answer is the feature. It has to be able
    to refuse in the language it was asked in."""
    assert set(answer.NO_SOURCE) == {"fr", "en"}
    assert all(text.strip() for text in answer.NO_SOURCE.values())


def test_messages_are_numbered_for_citation():
    """Claude cites by number, and the numbers have to line up with the list
    we hand it, or every citation points at the wrong message."""
    from datetime import datetime

    hits = [
        {
            "author": "Awa",
            "said_at": datetime(2026, 9, 18, 9, 35, tzinfo=UTC),
            "content": "the recordings are here",
        },
        {
            "author": "+229 90 00 00 42",
            "said_at": datetime(2026, 9, 18, 9, 36, tzinfo=UTC),
            "content": "thanks",
        },
    ]

    formatted = answer.format_messages(hits)

    assert formatted.startswith("[1] Awa,")
    assert "[2] +229…42," in formatted
