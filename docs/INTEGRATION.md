# Wiring the WhatsApp worker to the API

For the Baileys worker in `adapters/whatsapp/`. The API runs on
`http://127.0.0.1:8000` on the same machine, so no auth and no TLS between
the two — nginx only exposes what we choose to expose.

Everything below is live today. You can build against it before the keys are
in place: without them the API still answers, from full text search instead of
Claude, with the same response shape.

## The rule that shapes all of it

**Silent in the group, talkative in private.**

In the group, write only when one of these is true:

- the bot was mentioned (`@ask …`, or a reply to one of its messages)
- the question is a duplicate → `meta.duplicate` is `true`, and then **once
  per topic**, not every time somebody asks again
- it is the daily digest

In a private chat, always answer. This is the whole product argument: the
group has a noise problem and we must not add to it.

## Answering a question

```js
const inGroup = msg.key.remoteJid.endsWith("@g.us");

const r = await fetch("http://127.0.0.1:8000/ask", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    question: text,                    // what they typed, minus the @ask
    user: inGroup ? msg.key.participant : msg.key.remoteJid,
    group_id: METI_GROUP_JID,          // ALWAYS the group. See below.
    private: !inGroup,
  }),
});
const { answer, sources, meta } = await r.json();
```

> **`group_id` is always the group's JID, never the chat the message arrived
> in.** It says *which history to search*, not where to reply. In a direct
> message `msg.key.remoteJid` is the person, so sending that would search a
> history with nothing in it and the bot would answer "I could not find
> anything" to every private question — the half of the product that is
> supposed to be the most useful. Put the group's JID in a constant and send
> it every time.
>
> `private: true` on a direct message keeps that question out of the duplicate
> detection that speaks in front of the group. Without it, the bot could
> announce to everyone that somebody asked something in private.

`sources` is an array of `{author, said_at, excerpt, permalink}`. Show at
least the first one — a citation is what separates this from a chatbot that
makes things up. Something like:

```
{answer}

— {sources[0].author}, {date of sources[0].said_at}
```

`meta.duplicate === true` means this was already answered; `meta.answered_at`
and `meta.original_question` say when and to what. In the group that is your
cue to post the earlier answer once and then stay quiet on the topic.

`group_id` must be **the same string** you send to `/catchup` and `/people`,
and the same one used when the history was ingested. Everything is scoped by
it: a wrong value silently returns nothing rather than erroring.

## Catching someone up

Trigger on a private message like "what did I miss", "quoi de neuf",
"catch me up".

```js
POST /catchup  { user, group_id, question? }
→ { summary, since, message_count, truncated, first_time }
```

Same rule as above: `group_id` is the group's JID, `user` is the person's.

Send `summary` as-is. It is written for a phone. `first_time: true` means we
had no bookmark for this person and summarised the last 48 hours — worth
saying so ("here is the last two days") rather than implying we knew.

Calling this **moves their bookmark forward**, so never call it to preview.

## Names instead of phone numbers

This is the one thing only the worker can do. WhatsApp hands you a `pushName`
for anyone who speaks; the export only had numbers. Without it, citations
read `+229…40`.

```js
POST /people {
  group_id,
  people: [{ handle: msg.key.participant, display_name: msg.pushName }]
}
```

Send it whenever you see a name you have not sent before — a small in-memory
set of JIDs you have already posted is enough. Batch them, it takes a list.
The API matches `2239…@s.whatsapp.net` to `+223 9…` in the history by itself.

## Feedback

A 👍 or 👎 reaction on one of the bot's messages:

```js
POST /feedback { user, group_id, helpful: true | false }
```

It rates the last answer that person received. This feeds the numbers we show
the judges, so it is worth wiring even though nothing depends on it.

## What the worker must refuse to do

Three rules the API cannot enforce for you, because they are about messages
it never sees.

**Never answer the bot's own messages, and never answer another bot.** Two
bots in one group will happily talk to each other all night. The API charges
nothing for an exact repeat within 30 seconds, but a loop that varies its
wording is not free. Drop anything where `msg.key.fromMe` is true, and ignore
any sender you have identified as a bot.

**Wait two or three seconds before sending.** A number that replies in 200
milliseconds, every time, at four in the morning, is a number Meta blocks —
and a blocked number ends the project in one move. The delay costs nothing
and makes the bot look like a participant rather than a scraper.

**Never send a message nobody asked for.** No welcome messages, no direct
messages to people who have not written to the bot first. That is the fastest
route to a ban, and the fastest route to the group resenting it.

## The flags on `meta`

| Flag | What it means | What to do |
|---|---|---|
| `duplicate` | already answered; `answered_at` and `original_question` say when and what | in the group, post once per topic and then stay quiet |
| `repeat` | the same person asked the same words seconds ago | say nothing, it was a double tap or a retry |
| `rate_limited` | this person has hit the hourly limit | send `answer` as-is, it is already a polite message in their language |
| `degraded` | the daily spend cap was reached; the answer came from search alone | send it normally — it is still sourced, just blunter |

## Failures

`/ask` can be slow — it calls a model. Allow **30 seconds** before giving up,
and send something human on timeout rather than nothing:

> Je mets plus de temps que prévu, réessaie dans un instant.

On a 5xx, do not retry in a loop: one retry, then give up. The worker going
quiet is recoverable; the worker spamming the group is not.

`GET /health` returns `{status, utterances, generation, embeddings}`. If
`generation` is `false` the API is answering without Claude — still correct,
just blunter. Worth logging at startup so a degraded night is obvious.

## Things the API deliberately does not do

- It never decides whether to speak. That is yours, and it is the design rule.
- It does not know who is an admin.
- It does not send anything. It only answers when asked.
