"""UniConnect AI - the HTTP surface.

POST /ask is the contract the whole team codes against and it does not
change: question, user, group_id in; answer and sources out. Everything else
here is additive, so the Baileys worker and the web page keep working while
features land behind them.

  POST /ask       answer a question from the group's own history
  POST /catchup   what one person missed, sent to them privately
  POST /people    tell us someone's name, so citations stop printing numbers
  POST /feedback  was that answer useful
  POST /messages  every message the worker sees, so the bot stays current
  GET  /recap/... decisions and action items from a transcribed call
  GET  /digest/.. five lines on the last 24 hours
  GET  /metrics   usage, as JSON
  GET  /metrics/page  the same, as a page for the judges
  GET  /health    is this thing alive
"""

import asyncio
import os
from contextlib import asynccontextmanager

import answer as answer_engine
import catchup as catchup_engine
import ingest
import limits
import metrics as metrics_engine
import recap
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]

pool: ConnectionPool | None = None


# How often the background pass looks for messages that arrived without a
# vector. Long enough not to hammer the embedding API, short enough that a
# question about something said two minutes ago still finds it by meaning -
# and until it does, full text search finds it by its words.
EMBED_INTERVAL_SECONDS = int(os.environ.get("EMBED_INTERVAL_SECONDS", "60"))


async def embed_loop():
    """Give vectors to live messages, without a cron job to forget to set up.

    Runs inside the API rather than as a separate service because it is four
    lines of work and one more container to deploy, monitor and restart is
    four lines too many two days before shipping.
    """
    while True:
        await asyncio.sleep(EMBED_INTERVAL_SECONDS)
        # to_thread: the pool and the embedding client are both synchronous,
        # and blocking the event loop here would stall every request.
        n = await asyncio.to_thread(ingest.embed_pending, pool)
        if n:
            print(f"embedded {n} live messages", flush=True)


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

    embedder = asyncio.create_task(embed_loop())
    yield
    embedder.cancel()
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
    # Capped: a pasted document is not a question, and the cost of reading one
    # scales with its length.
    question: str = Field(min_length=1, max_length=2000)
    user: str
    group_id: str
    # True when the question arrived in a direct message. group_id stays the
    # GROUP's id either way - that is what is being searched - and this says
    # where the answer is going. It keeps private questions out of the
    # duplicate detection that speaks in front of the group.
    private: bool = False


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
        pool,
        question=req.question,
        user=req.user,
        group_id=req.group_id,
        private=req.private,
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
# Live ingestion
# --------------------------------------------------------------------------


class IncomingMessage(BaseModel):
    author: str                       # WhatsApp JID, or a phone number
    content: str = Field(min_length=1, max_length=20000)
    said_at: str | int | float        # ISO 8601, or seconds since the epoch
    author_name: str | None = None    # pushName, when WhatsApp provides one
    permalink: str | None = None
    lang: str | None = None


class MessagesRequest(BaseModel):
    group_id: str
    messages: list[IncomingMessage] = Field(max_length=500)


@app.post("/messages")
def ingest_messages(req: MessagesRequest, background: BackgroundTasks) -> dict:
    """Every message the worker sees, mentioned or not.

    This is what keeps the bot current. Without it the history stops at the
    last chat export, and by Wednesday the bot is answering questions about
    last Friday.

    Safe to call repeatedly with the same messages: the unique index drops
    the duplicates, so a worker that reconnects and replays does no harm.
    """
    messages = [
        {
            "author": m.author,
            "author_name": m.author_name,
            "content": m.content,
            "said_at": ingest.parse_time(m.said_at),
            "permalink": m.permalink,
            "lang": m.lang,
        }
        for m in req.messages
    ]
    result = ingest.store(pool, req.group_id, messages)

    # Embed straight away rather than waiting for the periodic pass. Until a
    # message has a vector it can only be found by its exact words, and it
    # loses every ranking contest against messages that appear in both search
    # arms - so "when is the rehearsal", asked a minute after somebody said
    # it, would find nothing. The reply to the worker does not wait for this.
    if result["stored"]:
        background.add_task(ingest.embed_pending, pool)

    return result


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
# Recaps and the daily digest
# --------------------------------------------------------------------------
#
# The only two things the bot says without being asked. Both are generated
# here and posted by the worker, never sent from here: the rule about when the
# bot may speak in the group lives in one place, and it is not this one.


@app.get("/recap/{source_id}")
def call_recap(source_id: str) -> dict:
    """Decisions, action items and open questions from one transcribed call."""
    result = recap.call_recap(pool, source_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/recap/latest/{group_id}")
def latest_call_recap(group_id: str) -> dict:
    """The most recent call, for a worker that does not track call ids."""
    source_id = recap.latest_call(pool, group_id)
    if source_id is None:
        raise HTTPException(status_code=404, detail="no transcribed call for this group")
    return recap.call_recap(pool, source_id)


@app.get("/digest/{group_id}")
def daily_digest(group_id: str, day: str | None = None, lang: str | None = None) -> dict:
    """Five lines on the last 24 hours, or on `day` (YYYY-MM-DD, UTC).

    `quiet` true means nothing happened worth posting. That is a result, not
    an error: the worker should post nothing rather than announce silence.
    """
    return recap.daily_digest(pool, group_id, day, lang)


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
        # And what it has cost today, so nobody has to open a billing console
        # to find out why answers suddenly got blunter.
        "spend_today_usd": round(limits.spend_today_usd(pool), 4),
        "spend_cap_usd": limits.DAILY_SPEND_CAP_USD,
        "capped": limits.over_spend_cap(pool),
    }
