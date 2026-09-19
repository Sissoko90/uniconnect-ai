"""Embedding refusals are counted, because they are otherwise invisible.

A refusal is survivable by design: the bot falls back to full text search and
keeps answering. That is the right behaviour and it is completely silent, so
a rate limit looks exactly like the bot getting worse for no reason.

On a Voyage account with no payment method the limit is three requests per
minute. Measured on the server the night before launch: three calls passed
and the next three were refused. With 153 people asking at once that is the
normal state, not an edge case.
"""

import embeddings


def test_a_refusal_is_counted_and_kept(monkeypatch):
    monkeypatch.setattr(embeddings, "refusals", 0)
    monkeypatch.setattr(embeddings, "last_refusal", None)
    monkeypatch.setenv("VOYAGE_API_KEY", "a-key-that-exists")

    def refuse(*args, **kwargs):
        raise RuntimeError("You have not yet added your payment method")

    monkeypatch.setattr(embeddings, "_client_once", lambda: type("C", (), {"embed": refuse})())

    assert embeddings.embed_query("anything") is None, "a refusal degrades, never raises"
    assert embeddings.refusals == 1
    assert "payment method" in embeddings.last_refusal


def test_the_message_is_capped(monkeypatch):
    """Voyage's refusal is a paragraph with two URLs in it, and /health is
    read on a phone."""
    monkeypatch.setattr(embeddings, "refusals", 0)
    embeddings._refused(RuntimeError("x" * 500))

    assert len(embeddings.last_refusal) == 200


def test_no_key_is_not_a_refusal(monkeypatch):
    """Nothing was asked of the provider, so nothing was refused. Counting it
    would hide a real rate limit behind a configuration mistake."""
    monkeypatch.setattr(embeddings, "refusals", 0)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    assert embeddings.embed_query("anything") is None
    assert embeddings.refusals == 0
