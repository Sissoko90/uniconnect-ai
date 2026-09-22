"""Looking at a photo somebody pointed at.

The half of Victor's question that was still no. Voice notes have been
transcribed since the first day; images were read for their caption and
nothing else, not because the model cannot see but because nobody had
written the plumbing.

Deliberately on demand. Describing every picture in a busy group would pay
for every meme and every screenshot on the chance that one mattered later,
and this system's unit of work is text, which a photograph does not become.
"""

import pytest
import vision


class FakePool:
    """Never reached: every test here stops before the database does."""

    def connection(self, *a, **k):
        raise AssertionError("should not have got as far as the database")


def test_a_file_that_is_not_a_photo_is_refused_before_anything_is_spent():
    seen = vision.look(FakePool(), "what is this", b"%PDF-1.4", "application/pdf", "en")

    assert seen == {"error": "type"}


def test_the_mime_type_whatsapp_actually_sends(monkeypatch):
    """WhatsApp appends parameters and does not promise lower case, and an
    exact match against "image/jpeg" would refuse a photograph over a
    semicolon.

    Checked by watching it get past the type gate and stop at the next one:
    a "size" refusal here means the type was accepted.
    """
    monkeypatch.setattr(vision, "MAX_BYTES", 10)

    for sent in ["image/jpeg", "IMAGE/JPEG", "image/jpeg; charset=binary"]:
        assert vision.look(FakePool(), "q", b"x" * 500, sent, "en") == {
            "error": "size"
        }, sent


def test_an_image_too_large_is_refused_rather_than_sent(monkeypatch):
    """Anthropic refuses anything above five megabytes, and finding that out
    from the far end costs a round trip and an error nobody can read."""
    monkeypatch.setattr(vision, "MAX_BYTES", 100)

    seen = vision.look(FakePool(), "what is this", b"x" * 500, "image/jpeg", "en")

    assert seen == {"error": "size"}


@pytest.mark.parametrize("reason", ["type", "size", "off"])
@pytest.mark.parametrize("lang", ["en", "fr"])
def test_every_refusal_has_something_to_say_in_both_languages(reason, lang):
    """A refusal that falls back to a KeyError is a 500 in front of the
    group, over a photo."""
    assert vision.refusal(reason, lang)


def test_an_unknown_language_still_gets_a_sentence():
    assert vision.refusal("size", "sw") == vision.CANNOT["en"]["size"]


def test_the_prompt_forbids_guessing_at_what_is_not_shown():
    """The one rule that matters here. A confident wrong date read off a
    poster is worse than anywhere else, because nobody re-checks a picture
    they have already seen."""
    assert "Never guess" in vision.SYSTEM
    assert "blurred" in vision.SYSTEM
