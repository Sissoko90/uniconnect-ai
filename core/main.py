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
  POST /voice     a voice note, transcribed and made searchable
  GET  /alerts/.. who was named in the group and has not come back to it
  GET  /recap/... decisions and action items from a transcribed call
  GET  /digest/.. five lines on the last 24 hours
  GET  /timeline/ the group's schedule, drawn from what it actually said
  GET  /metrics   usage, as JSON
  GET  /metrics/page  the same, as a page for the judges
  GET  /          the web fallback page
  GET  /health    is this thing alive
"""

import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

import alerts
import answer as answer_engine
import auth
import catchup as catchup_engine
import ingest
import intent
import limits
import metrics as metrics_engine
import recap
import timeline as timeline_engine
import voice
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
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
def ask(req: AskRequest, trusted: bool = Depends(auth.is_worker)) -> AskResponse:
    # /ask is the one endpoint open to the internet, because the web page
    # needs it. Everything it can reach must therefore be safe for a stranger
    # to reach, and `user` and `private` are whatever the caller typed.
    #
    # Routing a summary to catch-up broke that: an unauthenticated request
    # naming somebody else returned that person's personal briefing and moved
    # their bookmark, so they would silently lose everything they had not read
    # yet. Both of those endpoints are behind the worker token precisely to
    # prevent that, and this was a side door into them.
    #
    # Callers who prove they are the worker are trusted about who is asking.
    # Everyone else gets an ordinary sourced answer, which is what the page
    # was for.
    # Clients that mirror the WhatsApp trigger send it through. The worker
    # strips it; the web page has nothing to mention, so it does not.
    question = intent.strip_trigger(req.question)

    # Somebody saying hello. Answering it by quoting a message that happens to
    # contain "bonjour" is the worst thing this bot does: it looks like it
    # understood, and it looks stupid. Costs nothing, calls nothing.
    if intent.is_greeting(question):
        return AskResponse(
            answer=intent.HELLO_BACK[intent.greeting_language(question)],
            sources=[],
            meta={"duplicate": False, "greeting": True},
        )

    personal = req.private and trusted

    # The schedule, for anybody on any client. It is built from dates the
    # group itself wrote and it names nobody privately, so it is exactly as
    # public as an ordinary answer, which this endpoint already serves to
    # strangers. It used to be reachable only from a private WhatsApp chat,
    # which meant the group and the web page could not use a feature the
    # usage guide lists without qualification.
    if intent.wants_the_timeline(question) and not limits.over_spend_cap(pool):
        try:
            drawn = timeline_engine.build(pool, req.group_id)
            if drawn.get("timeline"):
                return AskResponse(
                    answer=drawn["timeline"],
                    sources=[],
                    meta={"duplicate": False, "timeline": True,
                          "preformatted": True, "events": drawn.get("events")},
                )
        except Exception as exc:  # noqa: BLE001
            # Same reasoning as the summary below: on the public page an
            # ordinary answer beats a well-worded error.
            print(f"timeline failed, answering as a question: {exc}", flush=True)

    if intent.wants_a_summary(question) and not limits.over_spend_cap(pool):
        # An overview is about the group, not about the reader, so it is not
        # the personal briefing even when it is asked for in a direct chat.
        whole_group = intent.wants_an_overview(question)
        try:
            if whole_group:
                # The whole group explained, for somebody who cannot follow
                # it. Checked first because neither of the other two helps
                # this person: a digest shows them one day out of months,
                # and a catch-up shows them nothing once their bookmark is
                # current. It needs no identity, so it works everywhere.
                whole = recap.overview(pool, req.group_id, lang=None, question=question)
                text, covering, count = (
                    whole.get("overview"), whole.get("covering"),
                    whole.get("message_count"),
                )
            elif personal:
                # In a direct message, "summarise" means "what did I miss",
                # and we can answer that for this person specifically rather
                # than handing them the same group digest as everybody else.
                # It also moves their bookmark, which is what they want: the
                # next one starts where this ended.
                brief = catchup_engine.catch_up(
                    pool, user=req.user, group_id=req.group_id, question=question
                )
                text, covering, count = (
                    brief.get("summary"), brief.get("since"), brief.get("message_count")
                )
            else:
                # Everybody else, the web page included, gets the group
                # digest. It is the same five lines the bot posts in the
                # group every morning, so there is nothing in it that its
                # members have not already been shown, and it needs no
                # identity to be correct.
                #
                # Only the personal briefing above stays behind the token.
                # That one is one member's unread history and it moves their
                # bookmark, so serving it to an unauthenticated caller
                # naming somebody else would hand over their briefing and
                # silently lose them everything they had not read.
                digest = recap.daily_digest(pool, req.group_id, lang=None)
                text, covering, count = (
                    digest.get("digest"), digest.get("since"), digest.get("message_count")
                )
        except Exception as exc:  # noqa: BLE001
            # Falling through beats a 503 here. This endpoint is the public
            # page, and somebody asking for a summary should get the ordinary
            # answer rather than an error, even a well-worded one.
            print(f"summary failed, answering as a question: {exc}", flush=True)
            text = None

        if text:
            return AskResponse(
                answer=text,
                sources=[],
                meta={"duplicate": False, "summary": True,
                      "overview": whole_group,
                      "personal": personal and not whole_group,
                      "covering": covering, "messages": count},
            )
        # Quiet period, or no model: answer it as an ordinary question.

    result = answer_engine.answer_question(
        pool,
        question=question,
        user=req.user,
        group_id=req.group_id,
        # An untrusted caller cannot claim a question was asked privately:
        # that flag decides what duplicate detection may repeat in front of
        # the group, and it is not theirs to set.
        private=personal,
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


@app.post("/catchup", dependencies=[Depends(auth.require_worker)])
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
    # JIDs of anyone named in this message, from contextInfo.mentionedJid.
    # This is what lets the bot tell somebody, privately, that the group is
    # waiting on them.
    mentions: list[str] = []


class MessagesRequest(BaseModel):
    group_id: str
    messages: list[IncomingMessage] = Field(max_length=500)


@app.post("/messages", dependencies=[Depends(auth.require_worker)])
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
            "mentions": m.mentions,
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


class VoiceNote(BaseModel):
    group_id: str
    author: str
    said_at: str | int | float
    audio_base64: str
    mime_type: str = "audio/ogg"     # what WhatsApp sends
    author_name: str | None = None
    permalink: str | None = None


@app.post("/voice", dependencies=[Depends(auth.require_worker)])
def ingest_voice(note: VoiceNote, background: BackgroundTasks) -> dict:
    """A voice note, transcribed and stored as an ordinary message.

    The most invisible thing in a WhatsApp group: unsearchable, unskimmable,
    and gone if you did not listen in the hour. Afterwards it is searched and
    cited like any other message - and unlike a call transcript it is
    attributed to the person who recorded it, because we know who that is.
    """
    limits.assert_budget(pool)
    result = voice.store_voice_note(
        pool,
        group_id=note.group_id,
        author=note.author,
        author_name=note.author_name,
        said_at=ingest.parse_time(note.said_at),
        audio_b64=note.audio_base64,
        mime_type=note.mime_type,
        permalink=note.permalink,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    if result.get("stored"):
        background.add_task(ingest.embed_pending, pool)
    return result


# --------------------------------------------------------------------------
# Mention alerts
# --------------------------------------------------------------------------


@app.get("/alerts/{group_id}", dependencies=[Depends(auth.require_worker)])
def pending_alerts(group_id: str, limit: int = 50) -> dict:
    """Who has been named in the group and has not come back to it.

    The worker polls this and sends each one as a direct message. Nothing is
    posted in the group. Only people who have already used the bot appear
    here - writing to somebody who never asked for anything is how a number
    gets blocked - and only after a grace period, because somebody reading
    the chat right now does not need to be told.
    """
    return {"alerts": alerts.pending(pool, group_id, limit)}


class AlertsSent(BaseModel):
    ids: list[str]


@app.post("/alerts/sent", dependencies=[Depends(auth.require_worker)])
def alerts_sent(req: AlertsSent) -> dict:
    """Confirm delivery, so nobody is told the same thing twice."""
    return {"marked": alerts.mark_sent(pool, req.ids)}


# --------------------------------------------------------------------------
# Who is who
# --------------------------------------------------------------------------


class Person(BaseModel):
    handle: str          # phone number or WhatsApp JID
    display_name: str


class PeopleRequest(BaseModel):
    group_id: str
    people: list[Person]


@app.post("/people", dependencies=[Depends(auth.require_worker)])
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


@app.post("/feedback", dependencies=[Depends(auth.require_worker)])
def feedback(req: FeedbackRequest) -> dict:
    """Rate the last answer this person got.

    Keyed on the person rather than an answer id, because a thumbs-up on
    WhatsApp is a reaction to the message just above - there is no id for the
    worker to send back.

    The rating also lands on the original when the answer was a reused one.
    What the person is rating is the text, and the text belongs to the answer
    it was copied from: that is the row duplicate detection will serve again,
    so rating only the copy left a rejected answer in circulation.
    """
    with pool.connection() as conn:
        row = conn.execute(
            """with last as (
                 select id, reused_from from answers
                 where asked_by = %s and group_id = %s
                 order by asked_at desc limit 1
               )
               update answers set rating = %s
               where id in (select id from last)
                  or id in (select reused_from from last where reused_from is not null)
               returning id""",
            (req.user, req.group_id, 1 if req.helpful else -1),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="no answer to rate yet")
    return {"rated": str(row[0])}


class RatingRequest(BaseModel):
    helpful: bool


@app.post("/feedback/{answer_id}")
def rate_answer(answer_id: str, req: RatingRequest) -> dict:
    """Rate one specific answer, by its id.

    This is how the web page rates, and it is deliberately not behind the
    worker token: the page is public and has to be usable, and the id is the
    proof. Every answer carries its own in `meta.answer_id`, so the only
    answers a visitor can rate are the ones they were actually given. A
    random uuid is not guessable, and nothing here reveals one.

    The name-keyed endpoint above cannot be used from the page. It rates the
    last answer a given person got, and on a public page the name is whatever
    the visitor typed, so anybody could mark anybody else's answers.

    As there, the rating also lands on the original when the answer was a
    reused one, because that is the row duplicate detection will serve again.
    """
    try:
        with pool.connection() as conn:
            row = conn.execute(
                """with target as (
                     select id, reused_from from answers where id = %s
                   )
                   update answers set rating = %s
                   where id in (select id from target)
                      or id in (select reused_from from target
                                where reused_from is not null)
                   returning id""",
                (answer_id, 1 if req.helpful else -1),
            ).fetchone()
    except Exception:  # noqa: BLE001
        # A malformed id is a 404, not a 500. The page sends whatever it was
        # given and an invalid uuid must not read as a server fault.
        raise HTTPException(status_code=404, detail="no such answer") from None

    if row is None:
        raise HTTPException(status_code=404, detail="no such answer")
    return {"rated": str(row[0])}


# --------------------------------------------------------------------------
# Recaps and the daily digest
# --------------------------------------------------------------------------


def _needs_a_model(build):
    """Run something that cannot work without the model, and fail readably.

    /ask and /catchup degrade: past a failure they quote a sourced message
    instead. A digest, a recap or a timeline has no such half-measure, so
    these stop. What they must not do is stop with a 500 and a stack trace:
    the usual cause is an expired key or an empty credit balance, and the
    caller can fix either in a minute if the message says which.
    """
    try:
        return build()
    except Exception as exc:  # noqa: BLE001
        print(f"model call failed: {exc}", flush=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "This needs the answering model and it is not responding. "
                "Check the API key and the credit balance on the account. "
                "Questions are still answered from search in the meantime."
            ),
        ) from exc
#
# The only two things the bot says without being asked. Both are generated
# here and posted by the worker, never sent from here: the rule about when the
# bot may speak in the group lives in one place, and it is not this one.


@app.get("/recap/{source_id}", dependencies=[Depends(auth.require_worker)])
def call_recap(source_id: str) -> dict:
    """Decisions, action items and open questions from one transcribed call."""
    limits.assert_budget(pool)
    result = _needs_a_model(lambda: recap.call_recap(pool, source_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/recap/latest/{group_id}", dependencies=[Depends(auth.require_worker)])
def latest_call_recap(group_id: str) -> dict:
    """The most recent call, for a worker that does not track call ids."""
    limits.assert_budget(pool)
    source_id = recap.latest_call(pool, group_id)
    if source_id is None:
        raise HTTPException(status_code=404, detail="no transcribed call for this group")
    return _needs_a_model(lambda: recap.call_recap(pool, source_id))


@app.get("/digest/{group_id}", dependencies=[Depends(auth.require_worker)])
def daily_digest(group_id: str, day: str | None = None, lang: str | None = None) -> dict:
    """Five lines on the last 24 hours, or on `day` (YYYY-MM-DD, UTC).

    `quiet` true means nothing happened worth posting. That is a result, not
    an error: the worker should post nothing rather than announce silence.
    """
    limits.assert_budget(pool)
    return _needs_a_model(lambda: recap.daily_digest(pool, group_id, day, lang))


@app.get("/timeline/{group_id}", dependencies=[Depends(auth.require_worker)])
def group_timeline(group_id: str) -> dict:
    """The schedule, as monospace text the worker can send in the thread.

    The model extracts dated facts and the message each came from; the
    drawing is done in code. Nothing reaches the timeline that was not in a
    message, and every line keeps its citation - which an image could not do.

    `empty` true means the group has not fixed any dates worth showing.
    """
    limits.assert_budget(pool)
    result = _needs_a_model(lambda: timeline_engine.build(pool, group_id))
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


# --------------------------------------------------------------------------
# Metrics and health
# --------------------------------------------------------------------------


@app.get("/metrics")
def metrics() -> dict:
    return metrics_engine.summary(pool)


@app.get("/metrics/page", response_class=HTMLResponse)
def metrics_page() -> str:
    return metrics_engine.page(pool)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """The web fallback: the same bot, for anyone not on WhatsApp.

    Served by the API rather than hosted separately. It is one file with no
    build step, it deploys with everything else, and it calls the API on its
    own origin - so there is no second deployment to keep in sync two days
    before shipping. The file is plain HTML and can be moved to Vercel as is
    if we ever want it there.
    """
    return (pathlib.Path(__file__).parent / "static" / "index.html").read_text()


@app.get("/logo.png", include_in_schema=False)
def logo() -> FileResponse:
    """The bot's face, on the page and as its favicon.

    Served from here so the page, the README and the WhatsApp avatar are all
    the same image. Cached hard: it changes about once a project.
    """
    return FileResponse(
        pathlib.Path(__file__).parent / "static" / "logo.png",
        media_type="image/png",
        headers={"cache-control": "public, max-age=86400"},
    )


@app.get("/health")
def health():
    """Used by the bot, the web page and anyone debugging the VPS at 2am."""
    try:
        # A short timeout on purpose: a health check that hangs for thirty
        # seconds before admitting the database is down is useless to the
        # person watching it, and to anything polling it.
        with pool.connection(timeout=2) as conn:
            n = conn.execute("select count(*) from utterances").fetchone()[0]
            # How current the bot is, which is the question people actually
            # have. A count says nothing: 829 messages could all be from last
            # week. If the newest message is hours old while the group is
            # talking, the worker has stopped feeding us.
            latest = conn.execute(
                "select max(said_at) from utterances"
            ).fetchone()[0]
            pending = conn.execute(
                "select count(*) from utterances where embedding is null"
            ).fetchone()[0]
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"database unreachable: {exc}"
        ) from exc

    return {
        "status": "ok",
        "utterances": n,
        "latest_message": latest.isoformat().replace("+00:00", "Z") if latest else None,
        "awaiting_embedding": pending,
        # So a glance at /health says which half of the pipeline is degraded.
        "generation": answer_engine.generation_available(),
        "embeddings": answer_engine.embeddings.available(),
        # And what it has cost today, so nobody has to open a billing console
        # to find out why answers suddenly got blunter.
        "spend_today_usd": round(limits.spend_today_usd(pool), 4),
        "spend_cap_usd": limits.DAILY_SPEND_CAP_USD,
        "capped": limits.over_spend_cap(pool),
        # So a deploy that forgot the token says so instead of quietly
        # refusing every call the worker makes.
        "worker_auth": auth.configured(),
    }
