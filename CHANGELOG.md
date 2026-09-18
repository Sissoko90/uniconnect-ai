# Changelog

Notable changes to UniConnect AI. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
- `--dry-run` on the parser no longer requires a database driver.

### Security

- Unresolved phone numbers are masked (`+229…40`) rather than printed into
  the group.
- `.env`, `*.zip`, `WhatsApp Chat with *`, `auth_info*/` and `*.session` are
  git-ignored.
- Postgres and the API are bound to `127.0.0.1`.
