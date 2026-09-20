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


# --------------------------------------------------------------------------
# The whole group, for somebody who cannot follow it
# --------------------------------------------------------------------------


def test_asking_for_all_of_it_is_not_asking_what_changed():
    """Sent twice, in these words, and answered with "Rien de nouveau depuis
    votre dernier passage". True of the question the bot heard and useless
    for the one asked: a catch-up covers what one person has not read, and
    this person has read none of it."""
    asked = [
        "Fais moi un résumé complet de tous les discussions qui on eu lieu "
        "sur le groupe de manière plus compréhensible claire et détaillé",
        "Un résumé complet de tous les discussions sur le groupe car je "
        "comprends rien et tout est en désordre et trop de message juste "
        "fais moi un grand résumé que je puisse me situer",
        "summarise everything that has been said here",
        "give me a full summary of the group from the start",
        "résumé général du groupe",
    ]
    for question in asked:
        assert intent.wants_a_summary(question), question
        assert intent.wants_an_overview(question), question


def test_what_changed_is_still_what_changed():
    """The overview must not swallow the other two. Somebody asking what
    they missed wants their unread messages, not the history of the group."""
    for question in ["quoi de neuf", "what did I miss", "catch me up",
                     "résumé", "summary", "rattrapage"]:
        assert intent.wants_a_summary(question), question
        assert not intent.wants_an_overview(question), question


def test_an_overview_needs_to_be_a_summary_request_first():
    """"complet" on its own is not a request for anything."""
    assert not intent.wants_an_overview("le dossier est complet")
    assert not intent.wants_an_overview("everything is fine")


# --------------------------------------------------------------------------
# The last call
# --------------------------------------------------------------------------


def test_asking_about_a_call_reaches_the_call_recap():
    """It reached nobody. The worker has no /recap in its API client, so the
    automatic call recap, feature three of the project's own list, existed as
    a curl command and nothing else."""
    for question in ["recap de l'appel", "compte rendu de la réunion",
                     "what happened on the call", "recap of the Open Hour",
                     "ce qui s'est dit pendant le meeting"]:
        assert intent.wants_a_call_recap(question), question


def test_recap_without_a_call_is_the_daily_digest():
    """"Recap" on its own means the digest, which is what people mean nine
    times out of ten. Sending them a call transcript instead would be worse
    than not having the feature."""
    for question in ["recap", "récap du jour", "give me a recap"]:
        assert not intent.wants_a_call_recap(question), question
        assert intent.wants_a_summary(question), question


def test_a_question_about_a_call_is_not_a_recap_request():
    """"When is the next call" is an ordinary question with an ordinary
    answer, and it cites the message that fixed the date."""
    for question in ["when is the next call", "quel est le lien du meeting"]:
        assert not intent.wants_a_call_recap(question), question


def test_a_plain_request_can_be_served_from_a_copy():
    """It costs about 25 cents and a minute of waiting to build. Everybody
    asking for the standard thing should get the same recent text."""
    for question in ["résumé complet", "summarise everything",
                     "un grand résumé, je comprends rien",
                     "Fais moi un résumé complet de tous les discussions sur le groupe"]:
        assert not intent.asks_for_more(question), question


def test_a_request_that_names_something_is_written_for_them():
    """"and the links to the past meeting" adds a section answering exactly
    that. Serving it to the next person would answer a question they never
    put."""
    for question in ["le résumé complet et les liens du meet passé",
                     "résumé complet et les dates importantes",
                     "summary of everything about the MIT course"]:
        assert intent.asks_for_more(question), question


def test_whatsapp_hides_directional_marks_inside_the_trigger():
    """The reason @ask never worked in a group for two days.

    Typing "@ask" makes WhatsApp treat it as a mention and wrap the word in
    U+2068 and U+2069, so the message that arrives is "@\u2068ask\u2069 what
    is ...". Nothing looking for a word matches that: the characters sit
    inside the word, not around it. In a private chat there is no trigger to
    recognise, which is why that half worked perfectly and hid it.
    """
    arrived = "@\u2068ask\u2069 what is this hackathon about ?"

    assert intent.strip_trigger(arrived) == "what is this hackathon about ?"


def test_marks_elsewhere_in_a_question_are_removed_too():
    """A word with an isolate inside it is not the token the index holds, so
    a question carrying them searches badly even once it is routed."""
    assert intent.strip_trigger("quelle est la \u2068date\u2069 limite") == (
        "quelle est la date limite"
    )


def test_words_the_group_actually_used_during_the_other_team_test():
    """Asked in the group on 20 September and matched by nothing, so they
    went to retrieval and searched for messages about being new."""
    for question in ["what is new today?", "what's new", "du nouveau ?"]:
        assert intent.wants_a_summary(question), question
        assert not intent.wants_an_overview(question), question


def test_asking_what_the_bot_knows_is_asking_for_everything():
    """"Describe everything you know about METI AI Innovation Program",
    asked the same day. Somebody asking what the bot knows wants the whole
    picture, not six retrieved messages."""
    question = "Describe everything you know about METI AI Innovation Program"

    assert intent.wants_a_summary(question)
    assert intent.wants_an_overview(question)


def test_asking_about_one_subject_is_still_a_question():
    """The distinction has to survive: "what do you know about Wadhwani" is
    answered with the messages about Wadhwani, and cites them."""
    assert not intent.wants_a_summary("what do you know about Wadhwani")
    assert not intent.wants_a_summary("tu sais quelque chose sur le visa ?")
