"""Serving a document the group shared, in the reader's language.

The hackathon guidelines and the video demo guide reached this group as
English PDFs. Half of it works in French and has said so, in the group,
more than once: that complaint is in the history the bot reads.

So a document is served as a page, in either language, with the browser
doing the printing. No PDF library on the server, no file pushed through
WhatsApp, and the same link works on a phone and on a laptop.

Translated once per language and kept, because the second person to ask
should not wait a minute for a text that has not changed.
"""

import answer as answer_engine
import limits
from psycopg.rows import dict_row

TRANSLATE = """You are translating a document that was shared in a WhatsApp \
group, for members who cannot read the original.

Translate it completely and faithfully. Keep every date, every number, every \
name, every email address and every link exactly as they are: a translated \
link is a broken link, and a date that moves is worse than no translation.

Keep the structure: the same headings, the same lists, the same order. Do \
not summarise, do not explain, do not add a note of your own. If a line is \
already in the target language, leave it as it is.

Output the translated document and nothing else."""

LANGS = {"en": "English", "fr": "French"}

LIST_SQL = """
select s.id, s.title, s.occurred_at,
       count(u.id) as blocks,
       string_agg(u.content, '\n\n' order by u.said_at) as text
from sources s
join utterances u on u.source_id = s.id
where s.group_id = %(group_id)s and s.kind = 'document'
group by s.id, s.title, s.occurred_at
order by s.occurred_at desc nulls last
"""


def listing(pool, group_id: str) -> list[dict]:
    """Every document this group has, newest first, without their text."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(LIST_SQL, {"group_id": group_id})
            rows = cur.fetchall()
    for row in rows:
        row.pop("text", None)
    return rows


def _original(pool, source_id: str) -> dict | None:
    """The document as it was loaded, reassembled from its blocks."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                LIST_SQL.replace(
                    "where s.group_id = %(group_id)s and s.kind = 'document'",
                    "where s.id = %(source_id)s and s.kind = 'document'",
                ),
                {"source_id": source_id},
            )
            return cur.fetchone()


def _cached(pool, source_id: str, lang: str) -> str | None:
    with pool.connection() as conn:
        row = conn.execute(
            "select text from document_renderings where source_id = %s and lang = %s",
            (source_id, lang),
        ).fetchone()
    return row[0] if row else None


def _keep(pool, source_id: str, lang: str, text: str) -> None:
    """Best effort: a cache that fails to write must not lose the text."""
    try:
        with pool.connection() as conn:
            conn.execute(
                """insert into document_renderings (source_id, lang, text)
                   values (%s, %s, %s)
                   on conflict (source_id, lang) do update
                     set text = excluded.text, built_at = now()""",
                (source_id, lang, text),
            )
    except Exception:  # noqa: BLE001
        pass


def render(pool, source_id: str, lang: str) -> dict:
    """The document in `lang`. Translated on first request, kept after.

    The original is served without a model call whatever language it is in:
    somebody asking for the English brief should not wait a minute, and
    should not be handed a translation of a translation.
    """
    lang = lang if lang in LANGS else "en"

    document = _original(pool, source_id)
    if document is None:
        return {"error": "no such document"}

    original = document["text"] or ""
    source_lang = answer_engine.detect_lang(original[:4000])

    if lang == source_lang:
        return {"title": document["title"], "lang": lang, "text": original,
                "translated": False}

    kept = _cached(pool, source_id, lang)
    if kept:
        return {"title": document["title"], "lang": lang, "text": kept,
                "translated": True, "cached": True}

    if not answer_engine.generation_available() or limits.over_spend_cap(pool):
        return {"error": "translation needs the model and it is unavailable"}

    response = answer_engine.anthropic_client().messages.create(
        model=answer_engine.MODEL,
        # A whole document, so the ceiling is the document's own length
        # rather than an answer's. The thinking comes out of this too.
        max_tokens=16000,
        system=TRANSLATE,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
        messages=[
            {
                "role": "user",
                "content": f"Translate into {LANGS[lang]}:\n\n{original}",
            }
        ],
    )
    limits.record_usage(pool, "translation", None, getattr(response, "usage", None))

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        return {"error": "the translation came back empty"}

    _keep(pool, source_id, lang, text)
    return {"title": document["title"], "lang": lang, "text": text,
            "translated": True, "cached": False}
