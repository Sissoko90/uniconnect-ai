"""UniConnect AI - the HTTP surface.

POST /ask is the contract the whole team codes against and it does not
change: question, user, group_id in; answer and sources out. Everything else
here is additive, so the Baileys worker and the web page keep working while
features land behind them.

  POST /ask       answer a question from the group's own history
  POST /catchup   what one person missed, sent to them privately
  POST /people    tell us someone's name, so citations stop printing numbers
  POST /feedback  was that answer useful
  GET  /metrics   usage, as JSON
  GET  /metrics/page  the same, as a page for the judges
  GET  /health    is this thing alive
"""

import os
from contextlib import asynccontextmanager

import answer as answer_engine
import catchup as catchup_engine
import metrics as metrics_engine
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]

pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    # The pool opens in the background and is never waited on here. Waiting
    # would mean that a database which is slow to start, or briefly down,
    # kills the API at boot - and with restart: unless-stopped that becomes a
    # crash loop with no way in to diagnose it.
    #
    # Instead the API always comes up, and /health reports 503 for as long as
    # the database is unreachable. It then recovers on its own, with no
    # restart, the moment the database answers again.
    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False)
    pool.open()
    yield
    pool.close()


app = FastAPI(title="UniConnect AI", lifespan=lifespan)


# --------------------------------------------------------------------------
# Asking
# --------------------------------------------------------------------------


class Source(BaseModel):
    author: str
    said_at: str
    excerpt: str
    permalink: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    user: str
    group_id: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    # Additive, so nothing that already reads answer and sources breaks.
    # The bot needs it to apply the "silent in the group" rule: a duplicate
    # is answered once per topic, not every time somebody asks again.
    meta: dict = {}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    result = answer_engine.answer_question(
        pool, question=req.question, user=req.user, group_id=req.group_id
    )
    return AskResponse(**result)


# --------------------------------------------------------------------------
# Catching up
# --------------------------------------------------------------------------


class CatchupRequest(BaseModel):
    user: str
    group_id: str
    # Free text, so "what did I miss about the deadline" narrows the briefing.
    question: str | None = None


@app.post("/catchup")
def catch_up(req: CatchupRequest) -> dict:
    return catchup_engine.catch_up(
        pool, user=req.user, group_id=req.group_id, question=req.question
    )


# --------------------------------------------------------------------------
# Who is who
# --------------------------------------------------------------------------


class Person(BaseModel):
    handle: str          # phone number or WhatsApp JID
    display_name: str


class PeopleRequest(BaseModel):
    group_id: str
    people: list[Person]


@app.post("/people")
def upsert_people(req: PeopleRequest) -> dict:
    """Called by the Baileys worker with the pushNames WhatsApp gives it.

    This is the only source of names that keeps working for members who
    joined after the chat export was taken, so it is worth calling on every
    message the worker sees.
    """
    if not req.people:
        return {"written": 0}

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """insert into people (group_id, handle, display_name, origin)
                   values (%s, %s, %s, 'pushname')
                   on conflict (group_id, handle_norm)
                   do update set display_name = excluded.display_name,
                                 origin = excluded.origin,
                                 updated_at = now()""",
                [(req.group_id, p.handle, p.display_name) for p in req.people],
            )
            written = cur.rowcount
    return {"written": written}


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    user: str
    group_id: str
    helpful: bool


@app.post("/feedback")
def feedback(req: FeedbackRequest) -> dict:
    """Rate the last answer this person got.

    Keyed on the person rather than an answer id, because a thumbs-up on
    WhatsApp is a reaction to the message just above - there is no id for the
    worker to send back.
    """
    with pool.connection() as conn:
        row = conn.execute(
            """update answers set rating = %s
               where id = (
                 select id from answers
                 where asked_by = %s and group_id = %s
                 order by asked_at desc limit 1
               )
               returning id""",
            (1 if req.helpful else -1, req.user, req.group_id),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="no answer to rate yet")
    return {"rated": str(row[0])}


# --------------------------------------------------------------------------
# Metrics and health
# --------------------------------------------------------------------------


@app.get("/metrics")
def metrics() -> dict:
    return metrics_engine.summary(pool)


@app.get("/metrics/page", response_class=HTMLResponse)
def metrics_page() -> str:
    return metrics_engine.page(pool)


@app.get("/health")
def health():
    """Used by the bot, the web page and anyone debugging the VPS at 2am."""
    try:
        # A short timeout on purpose: a health check that hangs for thirty
        # seconds before admitting the database is down is useless to the
        # person watching it, and to anything polling it.
        with pool.connection(timeout=2) as conn:
            n = conn.execute("select count(*) from utterances").fetchone()[0]
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"database unreachable: {exc}"
        ) from exc

    return {
        "status": "ok",
        "utterances": n,
        # So a glance at /health says which half of the pipeline is degraded.
        "generation": answer_engine.generation_available(),
        "embeddings": answer_engine.embeddings.available(),
    }
