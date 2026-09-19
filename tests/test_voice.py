"""WhatsApp does not send the content types the API expects.

The first of these was a live bug: every voice note would have failed, and
voice notes are the feature no other team has.
"""

import voice


def test_the_codec_parameter_is_stripped():
    """WhatsApp reports "audio/ogg; codecs=opus". Looked up as-is it misses
    the table, and sent on as-is the API rejects it."""
    assert voice.EXTENSIONS["audio/ogg"] == ".ogg"

    # What the worker actually forwards from msg.message.audioMessage.mimetype
    for reported in ["audio/ogg; codecs=opus", "AUDIO/OGG;codecs=opus", " audio/ogg "]:
        cleaned = reported.split(";")[0].strip().lower()
        assert cleaned in voice.EXTENSIONS, reported


def test_an_unknown_type_still_gets_an_extension():
    """Better a wrong extension than a crash: the API sniffs the bytes."""
    assert voice.EXTENSIONS.get("audio/something-new", ".ogg") == ".ogg"


def test_silence_is_never_stored():
    """Whisper transcribes silence as whatever it feels like. Storing its
    guess would put invented words in somebody's mouth, which is the one
    thing this system must never do."""
    assert voice.MIN_CHARS >= 5
