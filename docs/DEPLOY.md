# Deploying UniConnect AI, from nothing to a running bot

A complete walkthrough for a fresh Ubuntu server. Follow it top to bottom and
the bot ends up answering in the group.

Roughly 45 minutes, most of which is waiting for downloads. The only step that
cannot be done ahead of time is scanning the QR code, which needs the bot's
phone in your hand.

[SETUP.md](SETUP.md) is the shorter version for running this on a laptop. This
file is the production procedure.

---

## Before you start

You need four things. Get them now, not halfway through.

| | |
|---|---|
| A server | Ubuntu 22.04 or newer, 2 GB RAM, root or sudo access |
| A phone number for the bot | **Not** your personal one. A second SIM or a spare number — the account gets linked to it |
| Three API keys | Anthropic, Voyage, Groq |
| A domain name (optional) | Only needed for the web page over HTTPS |

Get the keys:

- **Anthropic** — console.anthropic.com → API Keys. Starts `sk-ant-`. Put a
  spend limit on it in the console. This is the only one that costs real money.
- **Voyage** — dash.voyageai.com → API Keys. Starts `pa-`. Add a payment
  method: the first 200M tokens are free either way, but without one you are
  capped at 3 requests a minute and ingestion crawls.
- **Groq** — console.groq.com → API Keys. Starts `gsk_`. For voice notes and
  call recordings.

---

## 1. Prepare the server

```bash
ssh root@your-server-ip

# Everything below runs as a normal user, not root.
adduser uniconnect
usermod -aG sudo uniconnect
su - uniconnect
```

Install Docker:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

**Log out and back in** — the group change only applies to a new session.

```bash
exit
ssh uniconnect@your-server-ip
docker ps        # should print an empty table, not a permission error
```

Install Node 22 for the WhatsApp worker, and git:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs git
node --version   # must be v22 or newer
```

Close the server off:

```bash
sudo ufw allow 22,80,443/tcp
sudo ufw enable
sudo ufw status
```

Only SSH, HTTP and HTTPS. The database and the API never leave the machine.

---

## 2. Get the code

```bash
sudo mkdir -p /opt && sudo chown "$USER" /opt
cd /opt
git clone https://github.com/Sissoko90/uniconnect-ai.git
cd uniconnect-ai
```

---

## 3. Configure the API

```bash
cp .env.example .env
nano .env
```

Fill in five values. Leave the rest at their defaults.

```bash
POSTGRES_PASSWORD=<a long random string>
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
GROQ_API_KEY=gsk_...
WORKER_TOKEN=<generate one, see below>
```

Generate the two secrets:

```bash
openssl rand -hex 32     # for POSTGRES_PASSWORD
openssl rand -hex 32     # for WORKER_TOKEN
```

`WORKER_TOKEN` is the shared secret between the worker and the API. Most
endpoints read or write the group's private messages and are refused without
it. Keep it — you will paste the same value into the worker in step 8.

`.env` is git-ignored. Never commit it, never paste it into a chat.

---

## 4. Start the database

The database first, alone, so that a schema error surfaces on its own instead
of in a pile of three containers.

```bash
docker compose up -d db
docker compose logs -f db      # ctrl-c when you see "ready to accept connections"
```

Check the tables landed:

```bash
docker compose exec db psql -U uniconnect -d uniconnect -c "\dt"
```

Six tables: `sources`, `utterances`, `answers`, `people`, `mentions`,
`user_state`.

> `db/schema.sql` is applied **once**, when the data volume is created. If you
> edit it later, nothing happens on a running database — see *Resetting* at the
> end.

---

## 5. Start the API

```bash
docker compose up -d --build api
curl -s localhost:8000/health
```

Expected:

```json
{"status":"ok","utterances":0,"generation":true,"embeddings":true,
 "spend_today_usd":0.0,"spend_cap_usd":10.0,"capped":false,"worker_auth":true}
```

Check all four flags. `generation` and `embeddings` false means a key is
missing or misspelled. `worker_auth` false means `WORKER_TOKEN` is empty, and
the worker will be refused on every call.

---

## 6. Load the group's history

Export the chat on the phone: **group → ⋮ → More → Export chat → Without
media**. Send yourself the `.zip`, then copy it to the server:

```bash
# On your laptop, not the server:
scp "WhatsApp Chat with METI.zip" uniconnect@your-server-ip:/opt/uniconnect-ai/
```

On the server:

```bash
cd /opt/uniconnect-ai
unzip "WhatsApp Chat with METI.zip" -d /tmp/export

python3 -m venv .venv && . .venv/bin/activate
pip install -r ingestion/requirements.txt

set -a; . ./.env; set +a
export DATABASE_URL="postgresql://uniconnect:$POSTGRES_PASSWORD@localhost:5432/uniconnect"

# Look before you write.
python ingestion/parse_whatsapp.py /tmp/export/*.txt \
    --group-id meti-cohort-1 --tz Africa/Bamako --dry-run

# Then load it.
python ingestion/parse_whatsapp.py /tmp/export/*.txt \
    --group-id meti-cohort-1 --title "METI Cohort 1" --tz Africa/Bamako
```

`--tz` is the timezone of the phone the export came from; everything is stored
in UTC. Running the same export twice is safe: the second run reports `0 new`.

Then delete the export from the server — it is 153 people's private messages
and it has served its purpose:

```bash
rm -rf /tmp/export "WhatsApp Chat with METI.zip"
```

Load the contact names that came with it, if there were any:

```bash
python ingestion/people.py --group-id meti-cohort-1 --vcf /tmp/export/*.vcf
```

---

## 7. Make it searchable

```bash
python ingestion/embed.py
```

A few minutes for a year of history. Safe to interrupt and re-run: each batch
is committed as it completes. If Voyage rate-limits you, it backs off and
keeps going.

Check:

```bash
curl -s localhost:8000/health        # utterances should match the parser's count
curl -s -X POST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"what is the deadline","user":"setup","group_id":"meti-cohort-1"}'
```

If that returns a sourced answer, the whole back end works.

---

## 8. Connect the WhatsApp worker

```bash
cd /opt/uniconnect-ai/adapters/whatsapp
npm install

cp .env.example .env
nano .env
```

```bash
API_URL=http://127.0.0.1:8000
WORKER_TOKEN=<the same value as in the API's .env>
GROUP_JID=          # left empty for now, filled in below
```

### Pair the phone

```bash
npm run groups
```

A QR code appears in the terminal. On the bot's phone: **WhatsApp → Settings →
Linked devices → Link a device**, and scan it.

Once linked, the command prints every group the number is in:

```
  METI UniPods AI Program 2026 Cohort
    GROUP_JID=120363012345678901@g.us
    153 participants
```

Copy that line into `.env`. If no group is listed, the number has not been
added to the group yet — do that first, then re-run.

The session lives in `adapters/whatsapp/auth_info/`. **Treat that directory
like a password**: anyone who has it can send WhatsApp messages as the bot. It
is git-ignored; keep it that way.

### Give it a face

```bash
npm run avatar
```

Sets the bot's WhatsApp profile picture to the project logo. Run it once,
after pairing. It is what 153 people see next to every answer and at the top
of the private chat — a default grey silhouette reads as an unfinished script.

If it fails, set the picture by hand on the bot's phone using
`assets/logo.png`. It is cosmetic; it does not block anything.

### Run it

```bash
npm start
```

You should see:

```
API reachable: 829 messages indexed, generation true, embeddings true
WhatsApp bot is online.
```

Send `@ask what is the deadline?` in the group. It should answer with a
citation. Send it a direct message; it should answer that too.

### Keep it running

`npm start` dies when you close the terminal. Install it as a service:

```bash
sudo tee /etc/systemd/system/uniconnect-bot.service > /dev/null <<'EOF'
[Unit]
Description=UniConnect AI WhatsApp worker
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=uniconnect
WorkingDirectory=/opt/uniconnect-ai/adapters/whatsapp
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now uniconnect-bot
sudo systemctl status uniconnect-bot
```

Watch it:

```bash
journalctl -u uniconnect-bot -f
```

---

## 9. Put the web page online

Only needed if you want the page reachable from a browser. The bot works
without this.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo nano /etc/nginx/sites-available/uniconnect
```

```nginx
server {
    server_name uniconnect.example.com;

    # The four public paths, and nothing else.
    location = /             { include proxy_params; proxy_pass http://127.0.0.1:8000; }
    location = /logo.png     { include proxy_params; proxy_pass http://127.0.0.1:8000; }
    location = /metrics/page { include proxy_params; proxy_pass http://127.0.0.1:8000; }
    location = /health       { include proxy_params; proxy_pass http://127.0.0.1:8000; }

    location = /ask {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
        proxy_read_timeout 120s;    # generating an answer takes a while
    }

    # Everything else stays on loopback: the group's messages, voice notes,
    # mention alerts, catch-up, digests, recaps.
    location / { return 404; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/uniconnect /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d uniconnect.example.com
```

Those endpoints are also behind the worker token, so this is the second lock
rather than the only one.

---

## 10. Check everything

```bash
# The API
curl -s localhost:8000/health

# A question, end to end
curl -s -X POST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"what are the deliverables","user":"check","group_id":"meti-cohort-1"}'

# The worker
sudo systemctl status uniconnect-bot

# Protected endpoints refuse strangers
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/alerts/meti-cohort-1   # 401
```

Then, in WhatsApp:

- `@ask what is the deadline?` in the group → a sourced answer
- anything in a direct message → an answer
- "what did I miss" in a direct message → a briefing
- a voice note in the group → nothing said, but `journalctl` shows it transcribed

---

## Running it day to day

```bash
# Logs
docker compose logs -f api
journalctl -u uniconnect-bot -f

# Restart
docker compose restart api
sudo systemctl restart uniconnect-bot

# What it has cost today
curl -s localhost:8000/health | grep -o '"spend_today_usd":[^,]*'

# Usage, for the judges
curl -s localhost:8000/metrics
```

### Updating

```bash
cd /opt/uniconnect-ai
git pull
docker compose up -d --build api
cd adapters/whatsapp && npm install && sudo systemctl restart uniconnect-bot
```

The WhatsApp session survives a restart. You only rescan the QR if you delete
`auth_info/` or log the device out from the phone.

### Backing up

There is no automatic backup. Take one before anything risky, and once a day
while the group is using it:

```bash
docker compose exec -T db pg_dump -U uniconnect uniconnect | gzip > ~/uniconnect-$(date +%F).sql.gz
```

Restore:

```bash
gunzip -c ~/uniconnect-2026-09-20.sql.gz | docker compose exec -T db psql -U uniconnect -d uniconnect
```

### Resetting the database

`db/schema.sql` only runs on a fresh volume. To apply a schema change while
the data is still disposable:

```bash
docker compose down -v      # -v deletes the volume and every message in it
docker compose up -d db
```

Then redo steps 6 and 7. Once the group depends on the data, stop doing this
and write a migration instead.

---

## When something is wrong

| Symptom | Cause and fix |
|---|---|
| `required variable POSTGRES_PASSWORD is missing` | No `.env`, or the line is empty |
| `permission denied` on docker | You did not log out and back in after `usermod` |
| `/health` returns 503 | The database is down: `docker compose logs db` |
| `"generation": false` | `ANTHROPIC_API_KEY` missing or misspelled in `.env` |
| `"worker_auth": false` | `WORKER_TOKEN` empty in the API's `.env` |
| Worker logs `401` | The two `WORKER_TOKEN` values do not match |
| Worker logs `Cannot reach the API` | The API is not running, or `API_URL` is wrong |
| `npm run groups` lists nothing | The number is not in the group yet |
| QR code asked for again | `auth_info/` was deleted, or the device was unlinked from the phone |
| Bot silent in the group | By design. It answers `@ask`, direct messages, and posts the daily digest |
| Answers say "I could not find anything" | History not loaded (step 6) or not embedded (step 7) |
| Citations show `+229…42` | Nobody has told us that person's name yet; it fills in as people speak |
| `Daily spend cap reached` | Raise `DAILY_SPEND_CAP_USD` in `.env` and restart the API |
| Schema change had no effect | The volume already existed. See *Resetting* |
