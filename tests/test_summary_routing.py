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


def test_a_summary_of_the_group_is_a_summary_however_it_is_phrased():
    """Sent to the bot in the group and answered with "je ne trouve rien dans
    l'historique du groupe sur ce sujet", to a request to summarise the group
    history.

    The sentence contains " sur ", which marks a summary about a topic, so it
    went to retrieval, which looked for messages on the subject of "the group"
    and found none. Naming the group is not naming a topic.
    """
    assert intent.wants_a_summary(
        "Fais moi un résumé complet de tous les discussions qui on eu lieu "
        "sur le groupe de manière plus compréhensible claire et détaillé"
    )
    assert intent.wants_a_summary("résumé de la discussion")
    assert intent.wants_a_summary("summary of everything on the group")
    assert intent.wants_a_summary("recap sur tout ce qui s'est dit")


def test_a_summary_about_a_topic_is_still_an_ordinary_question():
    """The distinction has to survive the fix, or every question containing
    the word "résumé" turns into a digest and stops citing anything."""
    assert not intent.wants_a_summary("résumé sur le projet de Steven")
    assert not intent.wants_a_summary("summary about the Wadhwani programme")
    assert not intent.wants_a_summary("un récapitulatif concernant les visas")


def test_surtout_is_not_the_word_tout():
    """Substring matching would have made this a whole-group summary."""
    assert not intent.wants_a_summary("résumé sur le projet, surtout la partie technique")


# --------------------------------------------------------------------------
# The schedule
# --------------------------------------------------------------------------


def test_the_documented_catchup_words_are_matched():
    """USAGE.md lists these as the way to ask for a catch-up. The worker had
    its own list and the API did not share it, so every one of them reached
    retrieval as an ordinary question and found nothing."""
    for question in ["what did I miss", "qu'est-ce que j'ai raté", "rattrapage",
                     "update me", "what have I missed?"]:
        assert intent.wants_a_summary(question), question


def test_the_schedule_is_asked_for_in_either_language():
    for question in ["timeline", "planning", "agenda", "calendrier",
                     "quelles dates sont fixées", "show me the schedule"]:
        assert intent.wants_the_timeline(question), question


def test_a_question_about_an_agenda_is_not_the_schedule():
    """"What is on the agenda for the call about visas" is a question about
    that call, and retrieval answers it with the message it came from."""
    assert not intent.wants_the_timeline("what is on the agenda about visas")
    assert not intent.wants_the_timeline("un planning sur la formation")


def test_the_schedule_wins_over_the_summary():
    """"planning" and "agenda" are the words people reach for when they want
    the list of dates. A digest of the last day is not that, and /ask checks
    the timeline first for exactly this reason."""
    assert intent.wants_the_timeline("planning")
    assert not intent.wants_a_summary("planning")
