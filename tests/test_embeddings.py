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


def fake_provider(monkeypatch, vector=None, counter=None):
    """A Voyage client that answers, and counts how often it was asked."""
    calls = counter if counter is not None else []

    class Result:
        embeddings = [vector or [0.1] * 4]

    def embed(*args, **kwargs):
        calls.append(kwargs.get("input_type"))
        return Result()

    monkeypatch.setenv("VOYAGE_API_KEY", "a-key")
    monkeypatch.setattr(embeddings, "_client_once", lambda: type("C", (), {"embed": embed})())
    return calls


def test_the_same_question_is_embedded_once(monkeypatch):
    """On launch day dozens of people ask the deadline within the hour. Each
    one was a separate request, and a free Voyage account allows three a
    minute for the whole group."""
    monkeypatch.setattr(embeddings, "_cache", embeddings.OrderedDict())
    calls = fake_provider(monkeypatch)

    for _ in range(20):
        assert embeddings.embed_query("what is the deadline?") is not None

    assert len(calls) == 1


def test_the_same_question_typed_differently_is_the_same_question(monkeypatch):
    """Half the group types accents and half does not, and both deserve the
    same vector."""
    monkeypatch.setattr(embeddings, "_cache", embeddings.OrderedDict())
    calls = fake_provider(monkeypatch)

    embeddings.embed_query("Quelle est la date limite ?")
    embeddings.embed_query("quelle est la date limite")
    embeddings.embed_query("QUELLE EST LA DATE LIMITE")

    assert len(calls) == 1


def test_different_questions_are_not_confused(monkeypatch):
    monkeypatch.setattr(embeddings, "_cache", embeddings.OrderedDict())
    calls = fake_provider(monkeypatch)

    embeddings.embed_query("what is the deadline")
    embeddings.embed_query("who do I contact about Wadhwani")

    assert len(calls) == 2


def test_the_cache_is_bounded(monkeypatch):
    """A burst of one-off questions must not grow without limit inside a
    process that runs for days."""
    monkeypatch.setattr(embeddings, "_cache", embeddings.OrderedDict())
    monkeypatch.setattr(embeddings, "QUERY_CACHE_SIZE", 10)
    fake_provider(monkeypatch)

    for i in range(50):
        embeddings.embed_query(f"question number {i}")

    assert len(embeddings._cache) == 10


def test_a_refusal_is_not_cached(monkeypatch):
    """Caching a failure would turn a passing rate limit into a permanent
    one for that question."""
    monkeypatch.setattr(embeddings, "_cache", embeddings.OrderedDict())
    monkeypatch.setenv("VOYAGE_API_KEY", "a-key")

    def refuse(*args, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(embeddings, "_client_once", lambda: type("C", (), {"embed": refuse})())

    assert embeddings.embed_query("anything") is None
    assert len(embeddings._cache) == 0
