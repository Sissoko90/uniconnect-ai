"""Query embeddings, for the vector half of hybrid search.

Documents are embedded by ingestion/embed.py, not here: the API must never
pay for an embedding pass in the middle of answering someone.

Both sides read the same two env vars, so the model and the dimension are
configured in exactly one place (.env) and cannot drift apart.
"""

import os

MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-4-lite")
DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

_client = None


def available() -> bool:
    """False means no key: callers fall back to full text search alone."""
    return bool(os.environ.get("VOYAGE_API_KEY"))


def _client_once():
    global _client
    if _client is None:
        import voyageai

        _client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return _client


def embed_query(text: str) -> list[float] | None:
    """The question as a vector, or None when that is not possible.

    None is a supported answer, not a failure: the caller falls back to full
    text search, which still finds names, acronyms and exact phrases. A rate
    limit, an expired key or a provider outage therefore makes the bot
    blunter for a moment instead of taking it off the air in front of 153
    people - which is what a raised exception here used to do, as a 500.

    The error is printed rather than swallowed, so `docker compose logs api`
    says why answers suddenly got worse.
    """
    if not available():
        return None

    try:
        result = _client_once().embed(
            [text],
            model=MODEL,
            # "query" and "document" are embedded differently by Voyage, and
            # mixing them up quietly costs retrieval quality.
            input_type="query",
            # Pinned rather than left to the model default, so a change
            # upstream cannot silently produce vectors the column rejects.
            output_dimension=DIM,
        )
        return result.embeddings[0]
    except Exception as exc:  # noqa: BLE001 - any failure degrades, none kills
        print(f"embedding unavailable, falling back to full text search: {exc}", flush=True)
        return None


def embed_documents(texts: list[str]) -> list[list[float]] | None:
    """Vectors for stored messages, or None when that is not possible.

    None rather than an exception, for the same reason as embed_query: the
    caller is a background pass that must leave the rows alone and try again,
    not crash the API it runs inside.
    """
    if not available() or not texts:
        return None

    try:
        result = _client_once().embed(
            texts,
            model=MODEL,
            # "document", not "query": these are the messages being searched,
            # not the question asked about them.
            input_type="document",
            output_dimension=DIM,
        )
        return result.embeddings
    except Exception as exc:  # noqa: BLE001 - the next pass picks them up
        print(f"document embedding failed, leaving rows for the next pass: {exc}", flush=True)
        return None


def to_pgvector(vector: list[float]) -> str:
    """pgvector's text input format, e.g. '[0.1,0.2]'.

    Passed as a string and cast in SQL with ::vector, which avoids a separate
    adapter package for the two queries that need it.
    """
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"
