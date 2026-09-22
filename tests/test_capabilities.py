"""The bot did not know what it could do.

From the group:

    Victor:  @ask can you view images and listen to audio messages?
    the bot: I work only from the text messages in this group, so I can't
             view images or listen to audio.

It has transcribed every voice note in this group since the day it joined.

The mistake was structural rather than a wrong fact. Every other question is
answered from the group's messages, which is the rule that keeps the bot
honest, and nobody has ever posted a message describing what the bot can do.
So it searched the history, found nothing about audio, and reported that
faithfully. It answered a question about itself with evidence about the
group.
"""

import capabilities
import intent


def test_the_question_that_started_this():
    assert intent.asks_what_it_can_do("can you view images and listen to audio messages?")


def test_asking_about_the_bot_in_either_language():
    for question in [
        "what can you do",
        "what can you do?",
        "how do you work",
        "what are your features",
        "can you read images",
        "do you listen to voice notes",
        "peux-tu écouter les notes vocales ?",
        "que sais-tu faire",
        "tu peux voir les photos ?",
        "tes fonctionnalités c'est quoi",
    ]:
        assert intent.asks_what_it_can_do(question), question


def test_an_ordinary_question_is_not_hijacked():
    """"Can you tell me the deadline" is a question about the programme. A
    medium has to be named, or this swallows half of what people ask."""
    for question in [
        "can you tell me the deadline",
        "can you find the meeting link",
        "peux-tu me donner la date limite",
        "what do you know about the judging criteria",
        "how do I submit my video",
    ]:
        assert not intent.asks_what_it_can_do(question), question


def test_voice_notes_are_claimed_only_when_transcription_is_configured(monkeypatch):
    """A bot with no transcription key must not tell the group it listens to
    voice notes. That is the same failure as the one this fixes, pointing
    the other way."""
    monkeypatch.setattr(capabilities.voice, "available", lambda: True)

    assert "voice notes" in capabilities.describe("en")

    monkeypatch.setattr(capabilities.voice, "available", lambda: False)

    assert "voice notes" not in capabilities.describe("en")


def test_looking_at_a_photo_says_how_to_ask_for_it(monkeypatch):
    """The bot never looks at a picture on its own, so the list has to say
    what the person must do. "I can read images" would be true and would
    leave everybody waiting for something that never happens."""
    monkeypatch.setattr(capabilities.answer_engine, "generation_available", lambda: True)

    assert "@ask" in capabilities.describe("en")
    assert "point me at it" in capabilities.describe("en")
    assert "si tu me la montres" in capabilities.describe("fr")


def test_nothing_is_claimed_without_the_key_behind_it(monkeypatch):
    """A deployment with no generation key must not tell the group it reads
    photos. That is the failure this module exists to fix, pointing the
    other way."""
    monkeypatch.setattr(capabilities.answer_engine, "generation_available", lambda: False)
    monkeypatch.setattr(capabilities.voice, "available", lambda: False)

    said = capabilities.describe("en")

    assert "photo" not in said
    assert "voice notes" not in said
    # And still answers something useful, because reading the group's
    # messages needs no key of its own.
    assert "Read every message" in said


def test_an_unknown_language_still_gets_an_answer():
    assert capabilities.describe("sw").startswith(capabilities.LINES["en"]["intro"])
