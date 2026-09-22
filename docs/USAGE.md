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
| A shared document, as a PDF, in your language | `@ask envoie le brief en français` | same | no |
| What was decided on the last call | `@ask recap de l'appel` | `recap de l'appel` | yes |
| Your own catch-up | not applicable | `what did I miss` | no, see below |
| Say an answer was wrong | react 👍 👎 | react 👍 👎 | the buttons under the answer |
| Voice notes, transcribed and searchable | yes | yes | no |
| Ask about a photo | reply to it with `@ask …` | same | no |
| Told when the group is waiting on you | arrives privately | arrives privately | no |
| The morning digest | posted at 05:00 Bamako | no | ask for a summary |
| The evening poll | posted at 23:00 Bamako | no | no |
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

It answers anyway. Everybody who asks gets an answer, every time.

It used to go quiet on a topic for six hours after answering it, on the
grounds that the answer was already on the screen just above. That is true
and it reads as being ignored: "@ask What session are we having tomorrow and
what's the time?" got no reply at all, because a similar question had been
asked earlier that day. Nobody who has just been ignored concludes that the
bot was being considerate.

Answering costs almost nothing. A repeated question is recognised as one
already asked and comes back from the stored answer without calling the
model, so the saving was never money, only messages.

`TOPIC_QUIET_MINUTES` brings the quiet window back, in minutes, for a group
that is living with the bot rather than testing it.

### Every morning

**The first morning is different.** The very first thing the bot posts
introduces itself in both languages, says which team built it and how to
talk to it, and then explains the whole group from its entire history: what
this group is for, the threads of activity and where each stands, the dates
that matter, who does what, and what is still open. It ends by saying that
from tomorrow it will only post what changed.

The name it gives is `BOT_NAME` and the team is `TEAM_NAME`, both in the
worker's `.env`. `BOT_NAME` is also what `npm run avatar` writes to the
WhatsApp profile, so the message and the contact card agree.

That happens once. Posting the full history every morning would repeat
itself daily and be muted by the end of the week.

Every morning after that, at **05:00 in Bamako**, it posts what happened the
day before, morning to evening, each line citing the message it came from. Up
to eight lines, fewer when there is less to say, and nothing at all on a quiet
day rather than an announcement of the silence.

It covers a calendar day, not the last 24 hours. Those two windows look alike
at five in the morning and are not: a rolling window would drop everything
said between midnight and dawn the day before.

Mali is UTC+0 all year, so the server clock and Bamako's are the same one.
Further east the group wakes up to it a little later.

| | |
|---|---|
| Mali, Senegal | 05:00 |
| Benin, Nigeria | 06:00 |
| Rwanda, Zimbabwe, South Africa | 07:00 |
| Uganda, Kenya | 08:00 |

Change it with `DIGEST_HOUR_UTC`, and its length with `MORNING_DIGEST_LINES`.

### Ask about a photo

```
(reply to an image)  @ask what time does this say?
(caption an image)   @ask is this the right room?
```

Reply to a photo with `@ask` and your question, or post a photo with `@ask`
in its caption. The bot reads what is in the picture: a date on a poster, a
time on a screenshot, a room number, an amount.

Only an image somebody pointed at is ever looked at. Nothing in the group is
described or indexed on its own, so the bot costs nothing for the memes and
the screenshots, and about a cent for the one picture somebody actually
asked about.

It is told never to guess at what the image does not show. A blurred or
cropped date comes back as "I cannot make that part out", because nobody
re-checks a picture they have already seen.

### Reactions, without being asked

The bot marks a few messages a day with a reaction:

| | |
|---|---|
| 📌 | a link somebody will want again: a recording, a document, a form |
| ⏰ | a date somebody has to act on |
| 😄 | a joke the sender has already flagged as one |

A reaction is not a message. It does not appear in the thread, it does not
notify anybody, and it cannot be the bot replying to every message, which is
the complaint this group has already made out loud. It is the quietest thing
the bot can do, and it is useful rather than decorative: afterwards, the
things worth keeping can be found by scrolling for the bot's own mark.

Eight a day at most, of which three jokes, and never twice inside twenty
minutes. It never marks another team's bot, and it never puts a grin on a
message that mentions bots, spam or flooding, however many laughing faces
that message carries.

`REACT_TO_GROUP=false` turns it off. The ceilings are `REACT_MAX_PER_DAY`,
`REACT_MAX_FUN_PER_DAY` and `REACT_QUIET_MINUTES`.

### The evening poll

At **23:00 in Bamako**, at the end of the day it is asking about, the bot
posts one WhatsApp poll:

> Do you find UniConnect useful? / Trouvez-vous UniConnect utile ?
>
> - Yes / Oui 👍
> - No / Non 👎

A real poll, not a message asking for a reply: two buttons, one choice,
nothing to type, and WhatsApp shows the running tally to everybody. That
visibility is the point. The group should be able to see what it thinks
before it is asked to vote, and we should have to live with the answer in
public.

One answer each, not both: the poll is sent as a single choice poll, which
is what phones render as the familiar card with round buttons.

The votes are also recorded, by evening, so the trend can be read back:

```
GET /poll/<group_id>                 each evening's yes, no and share
GET /poll/<group_id>?detail=true     every vote, with the name behind it
GET /poll/<group_id>?detail=true&day=2026-09-22
```

The detail listing names the voters. It hides nothing that is not already
visible, because a WhatsApp poll shows the group who tapped what, and it
answers the question worth asking the morning after: which of the people
who tested it said no.

Votes are end to end encrypted like everything else. The bot can read them
only because it created the poll and kept the key; if that key is ever lost,
the poll still works and the group still sees its tally, and only our own
copy of the numbers goes missing.

`POLL_HOUR_UTC` moves it, `POLL_QUESTION`, `POLL_YES` and `POLL_NO` change
the wording, and `DIGEST_ENABLED=false` turns off both this and the morning
post. Do not change the wording while a poll is open: a vote arrives as a
hash of the button text, so renaming an option makes every vote on it
unreadable.

These two posts are the whole of what the bot says uninvited. What happened,
in the morning; one question, at night.

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

### Get a document in your language

```
envoie moi le brief du hackathon en français
send me the hackathon guidelines in French
share the video demo guide pdf
```

The bot builds a PDF and sends it as a file, not as a link. The programme's
documents arrived here in English; half this group works in French and has
said in this group that it cannot follow. A document is translated the
first time somebody asks for it in a language and kept, so the second
person waits for nothing.

The translation keeps every date, number, name, email and link exactly as
they are, and says on the last line that it was machine translated from the
original shared in the group.

**The design is the original's, not ours.** The PDF carries the same navy
banner, white title, gold programme line, navy serif headings and gold
panel around the prize, on the same US Letter page, measured out of the
document the group was given. Somebody who reads French gets that document
with its words translated and nothing else changed, rather than a plainer
one that happens to be readable.

Asking what a document *says* is a different thing and stays a question:
"what do the guidelines say about teams" is answered from the text, with a
citation.

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

## It reacts rather than replies

Thank it and it reacts 🙏 instead of writing back. In a group that has asked
for fewer bot messages, an answer to a thank-you is one more message nobody
needed.

Ask it something in the group and it reacts 👀 the moment it starts working.
A whole-group summary takes the better part of a minute, and that reaction
is how you know it heard you.

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
noise this whole bot exists to remove. It asks in the language you ask your
questions in, worked out from those five. The result is on the metrics page
as a share of the people who answered.

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
