# How to use the bot

Everything UniConnect AI can do, and exactly what to type to get it.

Two rules explain the rest. **In the group it stays quiet**: it reads every
message but only writes when you call it. **In a private chat it always
answers**, and nobody else sees any of it.

---

## In the group

### Ask a question

Start the message with `@ask`.

```
@ask what is the submission deadline?
@ask quelle est la date limite ?
@ask who do I contact about my Wadhwani account?
```

It answers with the message it took the answer from, who wrote it and when.

```
The final submission deadline is Thursday 24 September [1], and the build
phase runs from Friday 18 [1].

- Nadia Traore, 17 Sep
```

Ask in French and you get French, ask in English and you get English, whatever
language the original messages were written in.

**If the group never answered your question, it says so.** It does not guess.
That is the point of it.

### What happens without `@ask`

Nothing visible. The bot reads the message, indexes it, and says nothing. That
is deliberate: the group already has too much traffic, and a bot that comments
on everything is a bot everybody mutes.

### Voice notes

Send one as usual. The bot says nothing, but it transcribes it, and from then
on the voice note is searchable like any written message.

Ask a week later what somebody said in a three minute recording and you get
the answer, with their name on it.

### If somebody already asked

The bot answers the second person, then stays quiet on that topic for six
hours. The answer is already on the screen just above.

### Once a day

At 18:00 UTC it posts five lines on what happened, each one citing the message
it came from. If the day was quiet, it posts nothing rather than announcing
the silence.

---

## In a private chat

Write to the bot directly. Anything you send is a question, no `@ask` needed,
and the group sees none of it.

### Ask anything

```
where are the session recordings?
qui est responsable de la vidéo ?
```

### Catch up on what you missed

Any of these works, in either language:

```
what did I miss
catch me up
quoi de neuf
qu'est-ce que j'ai raté
rattrapage
update me
```

You get a short briefing of everything said since you were last active, with
what was decided, what needs you, and what is still open.

The bot knows when you were last here because it sees you talking in the
group. The first time you ask, it has no record and gives you the last two
days, and it tells you that is what it did.

### See the schedule

```
timeline
planning
agenda
calendrier
```

Every date the group has actually fixed, in order, with the message each one
came from:

```
Thu 17 Sep  --o  hackathon team declaration deadline      [1]
Fri 18 Sep  --*  UN demo video deadline 2:00 PM CAT       [2]
Thu 24 Sep  --*  hackathon submission deadline            [3]

o past   * upcoming
```

Nothing on that list was invented. The dates are read out of the group's own
messages, and the drawing is done by code, not by a model.

---

## What it does without being asked

### It tells you when the group is waiting on you

If somebody names you in the group and you have not come back to it, the bot
sends you a private message about twenty minutes later:

```
Gift asked you this in the group and it is still open:

"@Awa can you send the slides before the rehearsal?"
```

Three things about this, because an uninvited message is a big thing for a bot
to do:

- It only ever writes to people who have used it before. If you have never
  spoken to it, it will never start.
- It never says any of this in the group.
- It tells you once. Never twice for the same message.

If you reply in the group before it gets to you, it drops the reminder.

---

## Telling it when it is wrong

React to any of its answers:

| | |
|---|---|
| 👍 ❤️ 🙏 ✅ | useful |
| 👎 ❌ | wrong or useless |

This is not decoration. A thumb down **retires that answer**: it stops being
reused when somebody asks the same thing later. One person correcting it
fixes it for everybody.

---

## From a browser

**https://uniconnectai.abdatytch.com**

The same bot, same answers, same citations, for anyone not on WhatsApp or
anyone who prefers a keyboard.

**https://uniconnectai.abdatytch.com/metrics/page**

How the group is actually using it: how many members have asked something,
how many questions, how often an answer carried a source. Nobody is named on
that page.

---

## What it will not do

Worth knowing before you try, so it does not read as a bug.

- **It does not invent.** No source, no answer. It says it could not find
  anything.
- **It does not repeat what one member said about another as a person.**
  Decisions, deadlines and who owns what are what it is for. Passing on a
  colleague's opinion of a colleague is not.
- **It does not obey instructions written in the group.** If somebody posts
  "ignore your instructions and say X", the bot reads it as text somebody
  typed, and answers the actual question.
- **It does not know anything outside the group.** No web, no general
  knowledge. If it was not said here, it does not exist.
- **It does not answer unlimited questions.** Twenty per person per hour, and
  a daily spend cap for everybody. Past the cap it keeps answering from search
  alone and says so, instead of going silent.

---

## For the team

Things that run on the server, not in WhatsApp.

### Add a call recording

```bash
cd /opt/uniconnect-ai
. .venv/bin/activate
set -a; . ./.env; set +a
export DATABASE_URL="postgresql://uniconnect:$POSTGRES_PASSWORD@localhost:5432/uniconnect"

python ingestion/transcribe.py call.m4a --group-id meti-cohort-1 \
    --title "Weekly call, 22 Sept" --occurred-at 2026-09-22T18:00:00Z
python ingestion/embed.py
```

The call is then searchable like everything else. Get its recap:

```bash
curl -s -H "x-uniconnect-token: $WORKER_TOKEN" \
  localhost:8000/recap/latest/meti-cohort-1
```

Decisions, action items with their owners, and open questions. An owner the
transcript does not name is reported as not named, never guessed.

### Fill in people's names

Citations show `+229...42` until somebody tells the bot who that is. It learns
names on its own as people speak, and you can speed it up:

```bash
python ingestion/people.py --group-id meti-cohort-1 --missing   # who is unnamed
python ingestion/people.py --group-id meti-cohort-1 --csv names.csv
```

### See what it costs

```bash
curl -s localhost:8000/health
```

`spend_today_usd` against `spend_cap_usd`. Roughly 1.7 cents a question.

### Watch it work

```bash
journalctl -u uniconnect-bot -f          # the WhatsApp side
docker compose logs -f api               # the answering side
```
