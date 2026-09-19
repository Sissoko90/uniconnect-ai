# How to use the bot

Everything UniConnect AI can do, and exactly what to type to get it.

Two rules explain the rest. **In the group it stays quiet**: it reads every
message but only writes when you call it. **In a private chat it always
answers**, and nobody else sees any of it.

## Where each thing works

| | Group | Private chat | Browser |
|---|---|---|---|
| Ask a question, with citations | `@ask …` | just type it | yes |
| The group's schedule | `@ask timeline` | `timeline` | yes |
| A summary of the group | `@ask résumé` | see below | yes |
| The whole group explained | `@ask résumé complet` | `résumé complet` | yes |
| What was decided on the last call | `@ask recap de l'appel` | `recap de l'appel` | yes |
| Your own catch-up | not applicable | `what did I miss` | no, see below |
| Say an answer was wrong | react 👍 👎 | react 👍 👎 | the buttons under the answer |
| Voice notes, transcribed and searchable | yes | yes | no |
| Told when the group is waiting on you | arrives privately | arrives privately | no |
| The morning digest | posted at 07:00 UTC | no | ask for a summary |
| Asked what you think of the bot | no | once, after 5 questions | no |

Two of those say no, and both for a reason rather than an oversight.

**Your own catch-up is not on the page.** It is one member's unread history,
and asking for it moves their bookmark forward. The page is open to the
internet and the name in it is whatever the visitor typed, so serving a
catch-up there would let a stranger read somebody's briefing and silently
lose them everything they had not read yet. WhatsApp knows who you are; a
public page does not. Ask for a summary on the page and you get the group
digest, which is the same five lines the bot posts in the group each morning.

**Voice notes and being told the group is waiting on you** are things WhatsApp
does and a web page cannot: one is a recording you already send there, the
other is the bot writing to you first.

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

### Every morning

At 07:00 UTC it posts five lines on what happened since the day before, each
one citing the message it came from. If the day was quiet, it posts nothing
rather than announcing the silence.

The hour is chosen for the spread of the group, which runs from UTC+0 to
UTC+3: nobody gets it before 7am their time, nobody after 10am.

| | |
|---|---|
| Mali, Senegal | 07:00 |
| Benin, Nigeria | 08:00 |
| Rwanda, Zimbabwe, South Africa | 09:00 |
| Uganda, Kenya | 10:00 |

Change it with `DIGEST_HOUR_UTC` in the worker's `.env`.

---

## In a private chat

Write to the bot directly. Anything you send is a question, no `@ask` needed,
and the group sees none of it.

### Ask anything

```
where are the session recordings?
qui est responsable de la vidéo ?
```

Asking for a summary in a private chat gives you **your** catch-up, not the
same digest everybody else gets: what happened since you were last active.
The same words in the group give the group's digest, because there is no
"you" there.

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

### Understand the group from scratch

For when you have just joined, or let a few hundred messages pile up and do
not know where to start:

```
résumé complet
un grand résumé, je comprends rien
summarise everything
give me the big picture
```

This is not the same as the two above and it is worth knowing which you are
asking for. A digest is the last day. A catch-up is what you have not read.
This one reads the entire history and explains the group: what it is for,
the main threads and where each stands, the dates that matter, who does
what, and what is still open.

Ask for it once, sitting down, not on the way somewhere. It is longer than
anything else the bot writes, deliberately.

### What was decided on a call

```
recap de l'appel
compte rendu de la réunion
what happened on the call
recap of the Open Hour
```

Decisions, action items with their owner when the call named one, and the
questions left open. Built from the recording's transcript, so it only works
for calls somebody has added; the bot says so plainly when there are none
rather than answering with whatever message happens to mention a call.

The word "recap" on its own means the daily digest, which is what people
usually mean. Name the call and you get the call.

### See the schedule

```
timeline
planning
agenda
calendrier
quelles dates sont fixées
```

The same words work in the group behind `@ask`, and on the web page.

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

React to any of its answers in WhatsApp, or use the two buttons under an
answer on the web page:

| | |
|---|---|
| 👍 ❤️ 🙏 ✅ | useful |
| 👎 ❌ | wrong or useless |

This is not decoration. A thumb down **retires that answer**: it stops being
reused when somebody asks the same thing later. One person correcting it
fixes it for everybody.

### And once, it asks you about itself

After you have asked it five questions, the bot writes to you privately,
once, to ask whether it is worth keeping. Two options, 👍 or 👎, and nothing
else: no form, no follow-up, and it never asks you again whatever you answer.

It waits for five questions because before that you have no opinion worth
giving, and it writes in private because a survey in the group would be the
noise this whole bot exists to remove. The result is on the metrics page as
a share of the people who answered.

---

## From a browser

**https://uniconnectai.abdatytch.com**

The same bot, same answers, same citations, for anyone not on WhatsApp or
anyone who prefers a keyboard.

Type `timeline` for the schedule and `summary` for the group digest, exactly
as in WhatsApp. Under every answer there are two buttons, 👍 and 👎, and they
do the same thing as reacting in WhatsApp: a thumb down retires that answer
so it stops being reused. They work without signing in, because each answer
carries its own identifier and the buttons rate that one answer. Nobody can
rate an answer they were not given.

**https://uniconnectai.abdatytch.com/metrics/page**

How the group is actually using it: how many members have asked something,
how many questions, how often an answer carried a source. Nobody is named on
that page.

---

## How it keeps up with the group

The bot is a member of the group, so it receives every message as you send it.
Each one is stored and indexed within a few seconds. Ask about something said
two minutes ago and it will find it.

Nothing is sent anywhere outside the server. The messages go from WhatsApp to
our own database on our own machine.

**One real limit.** It only sees messages that arrive while it is connected.
If the bot is down for an hour, that hour is missing from what it knows, and
it will not know that it is missing. WhatsApp usually delivers what it queued
once the bot reconnects, which covers a short outage, but do not rely on that
for a long one.

Two things fill a gap: export the chat again and re-run the parser, which is
safe to do as often as you like because nothing is ever stored twice.

Check how current it is at any moment:

```bash
curl -s localhost:8000/health
```

```json
{"utterances": 1204, "latest_message": "2026-09-21T14:03:00Z",
 "awaiting_embedding": 0, "embedding_refusals": 0}
```

`latest_message` is the newest thing it has read. If that is hours old while
the group is busy, the worker has stopped feeding it: `systemctl status
uniconnect-bot`. `awaiting_embedding` above zero for more than a minute or two
means the embedding pass is behind, and those messages are findable by their
exact words but not yet by meaning.

`embedding_refusals` is the one to watch on a busy day. Anything above zero
means questions are being answered by word matching alone, without the half
of the search that understands meaning. The bot does not go quiet when this
happens, it just gets worse, so nothing else would tell you.
`last_embedding_refusal` says why. The usual cause is the rate limit on a
Voyage account with no payment method: three requests a minute, which a
group this size reaches in seconds.

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
