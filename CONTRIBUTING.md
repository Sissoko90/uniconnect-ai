# Contributing

Five people, five countries, one week. These rules exist so that nobody
blocks anybody else.

## The two rules that are not negotiable

1. **Nobody holds code more than four hours without pushing to `main`.**
   Unpushed work is work the rest of the team cannot build on, and a laptop
   that dies on Saturday takes the project with it.
2. **Never commit `.env`, a chat export, or `auth_info*/`.** They are
   git-ignored and the Security workflow scans for them, but check before you
   push. A leaked key must be rotated in the provider's console, not deleted
   in a later commit.

## Who owns what

| Area | Owner | Touch it only after asking |
|---|---|---|
| `db/schema.sql` | Makan | yes — everything depends on its shape |
| `ingestion/` | Makan | no |
| `core/` | Jediel | no |
| `adapters/whatsapp/`, `web/` | Liza | yes |
| `docker-compose.yml`, deployment | Sanassi | yes |
| `docs/` | whoever changed the behaviour | no |

`POST /ask` is **frozen**: `question`, `user`, `group_id` in; `answer` and
`sources` out. Adding a field is fine. Renaming or removing one breaks two
other people's work in another timezone.

## Running it

```bash
cp .env.example .env         # fill in POSTGRES_PASSWORD at minimum
docker compose up -d db api
curl localhost:8000/health
```

Full instructions, including loading a conversation, are in
[docs/SETUP.md](docs/SETUP.md).

## Before you push

```bash
python -m venv .venv && . .venv/bin/activate
pip install ruff pytest -r core/requirements.txt -r ingestion/requirements.txt

ruff check .
pytest
```

Both run in CI on every push and pull request, along with the schema applied
from scratch and the API image built. If CI is red, fix it before starting
the next thing — a red pipeline that everyone has learned to ignore is worse
than no pipeline.

## Writing code here

- **Comment the why, not the what.** Four other people will read this under
  time pressure, and two of them will open files they did not write. Say why
  HNSW and not ivfflat; do not say "create an index".
- **Comments and code in English**, conversation in whatever language suits.
- **A bug you fix gets a test**, named after the failure rather than the
  function. Three of the tests in `tests/` are regressions of bugs that
  reached real data.
- **Never invent an answer** — in code or in prompts. If the sources do not
  support it, say so.

## Commits

Conventional-commit prefixes, because the changelog is assembled from them:

```
feat: private catch-up endpoint
fix: read the date order from the export instead of assuming it
docs: setup notes for the ingestion scripts
chore: bump fastapi past the vulnerable starlette
```

One concern per commit. A commit that changes the schema and the parser and
the README is a commit nobody can revert.
