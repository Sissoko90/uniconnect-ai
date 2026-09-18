# Setup

How to run UniConnect AI from nothing, on a fresh Ubuntu server or on a
laptop. Steps 1 to 5 and 7 have been run end to end as written. Steps 6 and 8
need API keys, and step 9 (nginx, TLS, firewall) is the intended deployment
and still needs a pass on the real VPS.

## What you need

- Ubuntu 22.04 or later, 2 GB RAM minimum, with Docker and the compose plugin
- A phone number for the bot, separate from your own
- API keys: Anthropic (answers), Voyage (embeddings), Groq (transcription)

Install Docker if it is not there:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out and back in for this to take effect
```

## 1. Get the code

```bash
cd /opt
git clone https://github.com/Sissoko90/uniconnect-ai.git
cd uniconnect-ai
```

`/opt` is the conventional place for deployed applications. On a laptop,
anywhere is fine.

## 2. Configure

```bash
cp .env.example .env
nano .env
```

Three values matter before anything starts:

| Variable | What to put |
|---|---|
| `POSTGRES_PASSWORD` | Any long random string. Compose refuses to start without it. |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `VOYAGE_API_KEY` | From dash.voyageai.com |

`EMBEDDING_MODEL` and the `vector(1024)` column in `db/schema.sql` must agree.
Changing the model means changing the schema and re-embedding everything, so
leave it alone unless you mean it.

`.env` is git-ignored. Never commit it.

## 3. Start the database first

```bash
docker compose up -d db
docker compose logs -f db     # ctrl-c once you see "ready to accept connections"
```

The database alone, on purpose: if the schema has an error you find out now
instead of debugging three containers at once.

`db/schema.sql` is applied **once**, when the data volume is created. Editing
it later changes nothing on a running database — see *Resetting* below.

Check it landed:

```bash
docker compose exec db psql -U uniconnect -d uniconnect -c "\dt"
```

Five tables: `sources`, `utterances`, `answers`, `people`, `user_state`.

> **Port 5432 already in use?** Something else on the machine is running
> Postgres. Set `DB_PORT=5433` in `.env` — it moves only the host side, the
> containers still talk to each other on 5432.

## 4. Start the API

```bash
docker compose up -d --build api
curl localhost:8000/health
```

Expected: `{"status":"ok","utterances":0}`.

The API is bound to `127.0.0.1` and is not reachable from outside the
machine. That is deliberate — nginx puts it on the internet, nothing else.

## 5. Load a conversation

Export the group from WhatsApp (*Export chat → Without media*), copy the
`.txt` onto the server, then:

```bash
# Ubuntu refuses to pip install system-wide, so use a virtualenv.
python3 -m venv .venv && . .venv/bin/activate
pip install -r ingestion/requirements.txt

# Check what the parser sees before writing anything.
# --dry-run needs no database and no dependencies at all.
python ingestion/parse_whatsapp.py "chat.txt" --group-id meti-cohort-1 \
    --tz Africa/Bamako --dry-run

# Then load it.
export DATABASE_URL="postgresql://uniconnect:<password>@localhost:5432/uniconnect"
python ingestion/parse_whatsapp.py "chat.txt" --group-id meti-cohort-1 \
    --title "METI Cohort 1 group" --tz Africa/Bamako
```

`--tz` is the timezone of the phone the export came from; timestamps are
stored in UTC. Running the same export twice is safe — the second run reports
`0 new` and changes nothing.

Ask it something:

```bash
curl -s -X POST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"recordings link","user":"makan","group_id":"meti-cohort-1"}'
```

It answers without the next two steps, but on full text search alone. The
search gets substantially better once the messages are embedded.

## 6. Make it searchable

```bash
python ingestion/embed.py                       # everything not yet embedded
python ingestion/embed.py --limit 50            # try it on 50 first
```

Costs money, so it is a separate pass from parsing and only ever touches rows
with no vector. Safe to interrupt: each batch is committed as it completes, and
re-running picks up where it stopped.

Check it worked — `embeddings` should be `true` and the count should match:

```bash
curl -s localhost:8000/health
```

## 7. Give people names

A WhatsApp export identifies anyone outside the exporter's address book by
phone number, so without this step citations read *"+229 90 00 00 42 said…"*.
Unresolved numbers are masked to `+229…42` rather than printed in full.

```bash
# The vCards WhatsApp bundles with the export.
python ingestion/people.py --group-id meti-cohort-1 --vcf "3 contacts.vcf"

# Who is still unnamed, busiest first. Fill these in and load them back.
python ingestion/people.py --group-id meti-cohort-1 --missing
python ingestion/people.py --group-id meti-cohort-1 --csv names.csv
```

The bot also posts names to `POST /people` as it sees people speak, which is
the only source that covers members who joined after the export was taken.

## 8. Add a call recording

```bash
sudo apt install ffmpeg      # required, for audio conversion and splitting

python ingestion/transcribe.py call.mp4 --group-id meti-cohort-1 \
    --title "Weekly call, 22 Sept" --occurred-at 2026-09-22T18:00:00Z
python ingestion/embed.py    # transcripts need embedding too
```

Video is converted to 16 kHz mono audio and split automatically if it is over
the upload limit. Whisper does not label speakers, so a transcript block is
cited as the call itself, never attributed to a member by guesswork.

## The endpoints

| Endpoint | What it is for |
|---|---|
| `POST /ask` | answer a question, with citations. The frozen contract. |
| `POST /catchup` | what one person missed; moves their bookmark forward |
| `POST /people` | tell the API someone's name |
| `POST /feedback` | rate the last answer a person got |
| `GET /metrics` | usage figures, as JSON |
| `GET /metrics/page` | the same as a page, for the judges |
| `GET /health` | liveness, plus which half of the pipeline is degraded |
| `GET /docs` | interactive API browser, generated by FastAPI |

## 9. Put it on the internet

Only three ports are open. Everything else stays on loopback.

```bash
sudo ufw allow 22,80,443/tcp
sudo ufw enable
```

nginx in front of the API:

```nginx
server {
    server_name uniconnect.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 120s;   # answers can take a while to generate
    }
}
```

```bash
sudo certbot --nginx -d uniconnect.example.com
```

## Resetting the database

`db/schema.sql` only runs on a fresh volume. To apply a schema change while
the data is still disposable:

```bash
docker compose down -v      # -v deletes the volume, and every message in it
docker compose up -d db
```

Then re-run the parser. Once we are on real data that the group depends on,
stop doing this and write a migration instead.

## When something is wrong

| Symptom | Cause |
|---|---|
| `required variable POSTGRES_PASSWORD is missing` | No `.env`, or the line is empty. |
| `address already in use` | Another Postgres on 5432. Set `DB_PORT` in `.env`. |
| `/health` returns 503 | The database is not up. `docker compose logs db`. |
| Schema change had no effect | The volume already existed. See *Resetting*. |
| `could not create extension "vector"` | Wrong image. It must be `pgvector/pgvector:pg16`. |
| Parser prints 0 messages | Not a WhatsApp export, or media-only. Check with `--dry-run`. |
| Dates look months off | Wrong `--tz`, or an ambiguous export — the parser warns when it cannot tell. |
