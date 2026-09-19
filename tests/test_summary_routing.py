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


def test_a_bare_greeting_is_recognised():
    """Answering "bonjour" with a message that happens to contain the word
    bonjour is the worst thing the bot can do: it looks like it understood."""
    for question in ["bonjour", "Good morning", "morning", "hi there",
                     "salut tout le monde", "hello everyone"]:
        assert intent.is_greeting(question), question


def test_a_greeting_in_front_of_a_question_is_a_question():
    """"Good morning, what happened last night" is a real question with a
    polite opening, and answering it with a menu would be worse than useless.
    """
    for question in ["hi, what is the deadline?",
                     "Good morning, what happened this night?",
                     "morning session time", "what is the deadline"]:
        assert not intent.is_greeting(question), question


def test_the_greeting_reply_exists_in_both_languages():
    assert set(intent.HELLO_BACK) == {"fr", "en"}
    assert all(len(text) > 40 for text in intent.HELLO_BACK.values())


def test_hello_is_answered_in_the_language_it_was_said_in():
    """The general detector reads sentences and has nothing to go on in one
    word: "bonjour" was answered in English, which reads as not paying
    attention."""
    assert intent.greeting_language("bonjour") == "fr"
    assert intent.greeting_language("salut tout le monde") == "fr"
    assert intent.greeting_language("Good morning") == "en"
    assert intent.greeting_language("hi there") == "en"
