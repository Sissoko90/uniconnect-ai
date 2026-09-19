"""Asking for a summary is not a question retrieval can answer.

The bot looks for messages about the subject asked, and nobody has ever
written a message titled "summary of the group". It answered "I could not
find anything", which is honest and reads as broken, and it is the first
thing almost anybody types.
"""

import intent


def test_a_request_for_the_whole_picture_is_recognised():
    for question in [
        "Give me a summary of the group.",
        "Summarise the group",
        "summarize what has been going on",
        "quoi de neuf",
        "resume moi le groupe",
        "what's happening",
        "give me an overview",
    ]:
        assert intent.wants_a_summary(question), question


def test_a_question_about_a_subject_is_not_a_summary():
    """"A summary of the deadline decision" is a real question about a real
    thing, and retrieval answers it well. Routing it to the digest would
    replace a precise cited answer with a general one."""
    for question in [
        "give me a summary about the deadline",
        "what is the deadline",
        "who do I contact about my Wadhwani account",
        "what was decided on the submission format",
    ]:
        assert not intent.wants_a_summary(question), question


def test_the_whatsapp_trigger_is_stripped():
    """The worker removes @ask before sending; the web page has nothing to
    mention, so it does not, and the prefix ends up inside the question where
    it is noise in the search."""
    assert intent.strip_trigger("@ask what is the deadline?") == "what is the deadline?"
    assert intent.strip_trigger("@ask: what is the deadline?") == "what is the deadline?"
    assert intent.strip_trigger("@Ask  what is the deadline?") == "what is the deadline?"

    # Not a trigger, part of the question.
    assert intent.strip_trigger("who should I @ask about this") == (
        "who should I @ask about this"
    )

    # A bare trigger is not an empty question.
    assert intent.strip_trigger("@ask") == "@ask"
