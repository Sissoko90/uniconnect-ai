# Changelog

Notable changes to UniConnect AI. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Live ingestion** (`POST /messages`): every message the worker sees, so
  the bot knows what was said today rather than what was in the last export.
  De-duplicated, embedded immediately in the background, and it fills in real
  names from WhatsApp pushNames as a side effect.
- **Daily digest** (`GET /digest/<group>`): five lines on the last 24 hours,
  each under 25 words, each cited, language pinnable for a bilingual group.
- **Call recaps** (`GET /recap/latest/<group>`): decisions, action items with
  owners, and open questions from a transcribed call. An action item whose
  owner the transcript does not name says so instead of guessing.
- **Prompt-injection defences.** Retrieved messages are fenced in
  `<group_messages>`, closing tags inside a message are defanged so nobody can
  end the block early, the system prompt states that nothing inside can change
  the rules, and the question is labelled as the only instruction to follow.
- **Guardrails** (`core/limits.py`): twenty questions per person per hour, a
  daily spend cap computed from the token counts the API reports, and an
  identical repeat within thirty seconds answered from the database for
  nothing. Reaching the cap degrades to search without generation rather than
  silencing the bot, and says so on `meta.degraded`.
- **A rule against relaying personal judgements.** Decisions, deadlines and
  ownership are what the bot is for; repeating what one colleague said about
  another to a third is not.
- **Question answering** (`POST /ask`) over the group's own history, with
  mandatory citations and a refusal when nothing matches.
- **Hybrid retrieval**: pgvector cosine similarity and Postgres full text
  search, fused with reciprocal rank fusion.
- **Answer generation** with Claude Opus 5, grounded strictly in the
  retrieved messages, replying in the language of the question.
- **Private catch-up** (`POST /catchup`): what one member missed since their
  last visit, with the bookmark advanced on read.
- **Duplicate detection**: a question already answered returns the earlier
  answer and its citations, with no model call.
- **Name resolution** (`POST /people`, `ingestion/people.py`): phone numbers
  and WhatsApp JIDs resolve to names from vCards, pushNames or a CSV.
- **Call transcription** (`ingestion/transcribe.py`): audio and video through
  Whisper on Groq, merged into citable blocks on the group's timeline.
- **WhatsApp export parser** (`ingestion/parse_whatsapp.py`): iOS and Android
  layouts, multi-line messages, system-message filtering, idempotent re-runs.
- **Usage metrics** (`GET /metrics`, `GET /metrics/page`) for the judges.
- **Feedback** (`POST /feedback`) rating the last answer a member received.
- CI: lint, 23 tests, schema applied from scratch against pgvector, API image
  built and smoke-tested.
- Security workflow: TruffleHog over the full history, `pip-audit --strict`,
  Bandit, CodeQL, weekly Dependabot.
- Documentation: [ARCHITECTURE](docs/ARCHITECTURE.md),
  [SETUP](docs/SETUP.md), [INTEGRATION](docs/INTEGRATION.md),
  [SECURITY](SECURITY.md).

### Fixed

- **Date order was assumed, not read.** Our WhatsApp exports are month-first
  (`9/18/26`); the parser assumed day-first, which would have shifted the
  entire history by months and broken every "since Tuesday" question. The
  order is now determined from the file, and an ambiguous file warns.
- **vCards gave every number the same name.** WhatsApp writes cards with no
  newline between them (`END:VCARDBEGIN:VCARD`), so a line-by-line reader
  never saw a card boundary and attributed all four numbers to the last
  contact.
- **Re-running the parser duplicated the entire history.** Each run created a
  new source, so the de-duplication index — scoped to a source — never fired.
  A group now has exactly one chat source.
- **`ivfflat` on an empty table.** Replaced with HNSW, which is correct from
  the first row.
- **Eight known vulnerabilities in Starlette**, pulled in by the initial
  FastAPI pin. Dependencies upgraded; `pip-audit` now reports clean.
- **SQL assembled by string concatenation** in `embed.py`, replaced with a
  fully parameterised query.
- **The group's chat exports and the Baileys session keys were not
  git-ignored.**
- **Direct messages would never have worked.** The integration notes told the
  worker to send `msg.key.remoteJid` as `group_id`, which in a direct message
  is the person, not the group — so every private question would have searched
  an empty history and answered "I could not find anything". `group_id` is now
  documented as always being the group's JID, with a separate `private` flag.
- **A private question could have been announced to the group.** Duplicate
  detection matched across the boundary, so `meta.original_question` could
  have revealed in public what somebody asked in a direct message. Matching is
  now scoped by `asked_privately`.
- **Answers that found no source were never recorded**, which made the
  coverage metric a meaningless 100% and let the hourly limit be bypassed
  entirely by asking questions that match nothing. Measured coverage on real
  traffic dropped from a flattering 100% to an honest 13%.
- **Reciprocal rank fusion buried anything found by only one search arm.** A
  message that arrived seconds ago has no vector yet, so it could only be
  found by its words - and sat at rank 1 of the full text arm while never
  reaching the model. "When is the rehearsal?", asked a minute after somebody
  answered it, found nothing. Each arm's top two now always survive.
- **An answer marked unhelpful was reused for thirty days**, so a bad answer
  was served to everybody who asked the same thing and the thumbs-down did
  nothing at all.
- **Generation failures returned 500.** An overloaded model, a rate limit or
  an expired key took the bot off the air instead of degrading to a quoted
  source, which is what the rest of the system already did.
- **Transcription demanded ffmpeg for files that did not need it.** A voice
  note in an accepted format under 20 MB is now uploaded untouched.
- **The API crash-looped when the database was unreachable.** Startup waited
  on the connection pool and raised, so with `restart: unless-stopped` the
  container restarted forever with no way in to diagnose it — the opposite of
  what the code comment claimed. It now always starts, reports 503 from
  `/health` within two seconds while the database is down, and recovers on
  its own without a restart. Caught by CI, not by reading the code.
- `--dry-run` on the parser no longer requires a database driver.

### Security

- Unresolved phone numbers are masked (`+229…40`) rather than printed into
  the group.
- `.env`, `*.zip`, `WhatsApp Chat with *`, `auth_info*/` and `*.session` are
  git-ignored.
- Postgres and the API are bound to `127.0.0.1`.
