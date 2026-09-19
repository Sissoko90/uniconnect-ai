"""Query embeddings, for the vector half of hybrid search.

Documents are embedded by ingestion/embed.py, not here: the API must never
pay for an embedding pass in the middle of answering someone.

Both sides read the same two env vars, so the model and the dimension are
configured in exactly one place (.env) and cannot drift apart.
"""

import os
import re
import unicodedata
from collections import OrderedDict

MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-4-lite")
DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

_client = None

# How often embedding has refused, and what it last said.
#
# The refusal is deliberately survivable: the bot falls back to full text
# search and keeps answering. That is the right behaviour and it is also
# completely silent, so a rate limit looks exactly like the bot getting worse
# for no reason. On a free Voyage account the limit is three requests a
# minute, which 153 people reach in seconds, so this is the difference
# between knowing and guessing on the day the group votes.
#
# Reported by /health and on the metrics page. Counted since the process
# started; a restart resets it, which is what you want after a fix.
refusals = 0
last_refusal: str | None = None


def _refused(exc: Exception) -> None:
    global refusals, last_refusal
    refusals += 1
    last_refusal = str(exc)[:200]


def available() -> bool:
    """False means no key: callers fall back to full text search alone."""
    return bool(os.environ.get("VOYAGE_API_KEY"))


def _client_once():
    global _client
    if _client is None:
        import voyageai

        _client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    return _client


# Questions already embedded, keyed on the question with its punctuation,
# accents and capitals removed.
#
# On launch day the same handful of questions is asked by dozens of people
# in the same hour: the deadline, the MIT link, who to contact. Each one was
# a separate request to Voyage, which on a free account means three a minute
# for the whole group. Twenty people asking the deadline is now one request.
#
# In memory and lost on restart, which is right: it is a cache, the vectors
# that matter are in the database, and a stale one would be a subtler
# problem than the one it solves. The question text is the key, so nothing
# here can return somebody else's answer.
QUERY_CACHE_SIZE = int(os.environ.get("QUERY_CACHE_SIZE", "500"))
_cache: OrderedDict[str, list[float]] = OrderedDict()

cache_hits = 0


def _cache_key(text: str) -> str:
    """Same question, however it was typed.

    "Quelle est la date limite ?" and "quelle est la date limite" are one
    question. Accents are folded too, because half the group types them and
    half does not, and both deserve the same vector.
    """
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", folded))


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

    global cache_hits
    key = _cache_key(text)
    if key in _cache:
        cache_hits += 1
        _cache.move_to_end(key)
        return _cache[key]

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
        vector = result.embeddings[0]
        _cache[key] = vector
        # Oldest out first, so a burst of one-off questions cannot push the
        # ones being asked over and over out of the cache.
        while len(_cache) > QUERY_CACHE_SIZE:
            _cache.popitem(last=False)
        return vector
    except Exception as exc:  # noqa: BLE001 - any failure degrades, none kills
        _refused(exc)
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
        _refused(exc)
        print(f"document embedding failed, leaving rows for the next pass: {exc}", flush=True)
        return None


def to_pgvector(vector: list[float]) -> str:
    """pgvector's text input format, e.g. '[0.1,0.2]'.

    Passed as a string and cast in SQL with ::vector, which avoids a separate
    adapter package for the two queries that need it.
    """
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"
