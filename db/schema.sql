-- UniConnect AI schema.
-- Applied automatically by docker compose on a fresh database volume
-- (mounted into /docker-entrypoint-initdb.d). On an existing volume it does
-- NOT re-run: drop the volume or apply changes by hand.
--
-- Schema changes go through Makan.

-- Vector similarity search. Must be enabled before any vector column.
create extension if not exists vector;

-- The same person reaches us under several spellings: "+229 97 42 65 40" in a
-- chat export, "22997426540@s.whatsapp.net" from the bot at runtime. This
-- reduces both to the bare digits so they match. Names that are not phone
-- numbers ("Steven") are lowercased instead - the 7-digit floor keeps a
-- nickname containing a couple of digits from being mangled into nothing.
--
-- Declared IMMUTABLE because the generated columns below cannot use it
-- otherwise. It only looks at its argument, so that is honest.
create function normalize_handle(h text) returns text
language sql immutable strict parallel safe as $$
  select case
    when length(regexp_replace(h, '\D', '', 'g')) >= 7
      then regexp_replace(h, '\D', '', 'g')
    -- WhatsApp marks people outside your address book with a leading "~" and
    -- a narrow no-break space (U+202F). Strip both, or "~ Steven" from the
    -- bot and "Steven" from the export become two different people.
    else lower(btrim(h, ' ~' || chr(8239)))
  end
$$;

-- A "source" is one origin of content: a chat export, a call, a document.
-- It lets us say where an answer came from and filter by origin.
create table sources (
  id uuid primary key default gen_random_uuid(),
  kind text not null,          -- 'chat' | 'call' | 'document'
  platform text,               -- 'whatsapp' | 'zoom' | 'meet'
  group_id text,               -- which WhatsApp group this came from
  title text,                  -- e.g. "Weekly call, 12 Sept"
  occurred_at timestamptz,     -- when it happened, not when we ingested it
  created_at timestamptz default now()
);

-- One chat source per group, reused on every re-ingest.
-- Without this, re-running the parser on a fresh export would create a second
-- source, and the de-duplication index on utterances - which is scoped to a
-- source - would happily insert the whole history a second time.
-- Calls and documents are deliberately excluded: each one is its own source.
create unique index sources_chat_key
  on sources (platform, group_id) where kind = 'chat';

-- An "utterance" is one atomic piece of content: a chat message or one
-- segment of a transcript. This is the unit we search over and cite.
-- Same table for chats and calls on purpose: one search covers both.
create table utterances (
  id uuid primary key default gen_random_uuid(),
  -- not null so the de-duplication index below actually bites: in a unique
  -- index NULLs count as distinct, so a nullable column would let duplicates
  -- through on every re-run of the parser.
  source_id uuid not null references sources(id) on delete cascade,
  author text not null,        -- exactly as the export spelled it
  -- Join key to people below, so a citation can print a name instead of a
  -- phone number without re-normalising on every query.
  author_norm text generated always as (normalize_handle(author)) stored,
  content text not null,
  said_at timestamptz not null,
  permalink text,              -- link back to the original message if any
  lang text,                   -- 'en' | 'fr', used to answer in the right language

  -- 1024 dimensions = the default output of voyage-4-lite, the embedding
  -- model we ingest with. Changing the model means changing this number and
  -- re-embedding everything, so it is fixed before the first ingestion.
  embedding vector(1024),

  -- Full text index, generated automatically by Postgres on insert.
  -- 'simple' config on purpose: the group mixes English and French,
  -- and a language-specific config would mangle one of the two.
  fts tsvector generated always as (to_tsvector('simple', content)) stored
);

-- Re-running the parser on the same export must not duplicate the history.
-- Indexed on md5(content) rather than content itself: a btree entry is capped
-- at ~2.7 kB and a long pasted message would blow past it.
create unique index utterances_dedup
  on utterances (source_id, author, said_at, md5(content));

-- Two indexes because we run hybrid search:
-- vector search finds meaning, full text search finds exact names,
-- acronyms and project names that embeddings routinely miss.
--
-- HNSW, not ivfflat: an ivfflat index built on an empty table has no
-- centroids to cluster around and stays useless no matter what we insert
-- afterwards. HNSW builds incrementally and is correct from row one.
create index utterances_embedding_idx
  on utterances using hnsw (embedding vector_cosine_ops);
create index utterances_fts_idx on utterances using gin (fts);

-- Time filtering for the "what did I miss since Tuesday" feature.
create index utterances_said_at_idx on utterances (said_at);

-- Reading the messages around a match: the rows in one source just before
-- and just after a timestamp. Neither of the indexes above serves it, one
-- ignores the source and the other has author between source_id and said_at.
create index utterances_source_time_idx on utterances (source_id, said_at);

create table model_usage (
  id uuid primary key default gen_random_uuid(),
  -- 'digest' | 'overview' | 'call_recap' | 'timeline' | 'catchup'
  kind text not null,
  group_id text,
  input_tokens int,
  output_tokens int,
  used_at timestamptz not null default now()
);

create index model_usage_day_idx on model_usage (used_at);

-- The whole-group overview, kept so it is not rebuilt for every person who
-- asks. It takes over a minute and reads the entire history, and that
-- history grows by a few messages an hour: two members asking within the
-- same morning should not pay for it twice.
create table overview_cache (
  group_id text not null,
  lang text not null,
  text text not null,
  -- How much history it was built from. The count moving is what says the
  -- cached text is out of date, and it is cheaper and more honest than a
  -- timer: a quiet week should not expire a still-accurate overview, and a
  -- busy hour should.
  utterances int not null,
  built_at timestamptz not null default now(),
  primary key (group_id, lang)
);

-- How members rate the bot itself, not one of its answers.
--
-- Its own table rather than a column on answers: a rating on an answer says
-- whether that answer was right, and this says whether the bot is worth
-- having. Mixing them would corrupt duplicate detection, which retires
-- answers that were rated down.
create table satisfaction (
  id uuid primary key default gen_random_uuid(),
  asked_by text not null,
  group_id text not null,

  -- The WhatsApp id of the message the bot sent. A reaction arrives carrying
  -- the id of the message it is on and nothing else, so this is what tells
  -- a thumb on the survey apart from a thumb on an ordinary answer. Without
  -- it, rating the survey would silently retire the last answer the person
  -- happened to receive.
  message_id text,

  asked_at timestamptz not null default now(),
  -- 1 or -1, null until they answer. Most people will not, and that is fine:
  -- the row is what stops us asking them a second time.
  rating int,
  rated_at timestamptz
);

-- One survey per person per group, ever. The unique index is the guard, not
-- the code: two worker restarts in the same minute would otherwise ask the
-- same person twice.
create unique index satisfaction_once
  on satisfaction (group_id, asked_by);

-- Resolving a reaction to the survey it belongs to.
create index satisfaction_message_idx
  on satisfaction (message_id) where message_id is not null;

-- Every answer we produce is stored. Two reasons:
-- 1. detect repeated questions and reuse the previous answer
-- 2. produce the usage metrics we show to the judges on Thursday
create table answers (
  id uuid primary key default gen_random_uuid(),
  question text not null,
  answer text not null,
  cited_ids uuid[],            -- which utterances backed this answer
  asked_by text,
  group_id text,               -- so a group only ever sees its own answers
  asked_at timestamptz default now(),
  rating int,                  -- 1 = helpful, -1 = not helpful, null = no feedback

  -- Asked in a direct message rather than in the group.
  --
  -- What a member asks privately is private, even though the answer is built
  -- from messages the whole group can already read. Duplicate detection only
  -- ever matches questions of the same kind, so the bot can never announce to
  -- the group that somebody asked something in private.
  asked_privately boolean not null default false,

  -- What the answer actually cost, as reported by the API rather than
  -- estimated. This is what the daily spend cap is measured against.
  input_tokens int,
  output_tokens int,

  -- Written without a model: the search ran, the model did not, and the bot
  -- quoted its closest message instead of composing an answer.
  --
  -- Recorded because a degraded answer must never be reused as a duplicate.
  -- On the first morning, with the Anthropic balance empty, "what is the
  -- submission deadline?" was answered with a quote, that quote was stored,
  -- and every later phrasing of the question was served the same quote as an
  -- already-answered question. The stopgap would have outlived the outage
  -- that caused it by thirty days.
  degraded boolean not null default false,

  -- Set when this row is a reused answer rather than a new one: the question
  -- was recognised as one already asked, and the earlier answer was served.
  --
  -- The copy is recorded so that reused answers still count against the
  -- hourly limit and still appear in the usage figures. It must not itself be
  -- reusable, though. A copy is younger than the answer it came from, so a
  -- popular question kept minting fresher and fresher copies of one answer and
  -- the thirty-day age limit never applied to anything.
  --
  -- It also carries a rating back to where it belongs. Feedback rates the last
  -- answer a person got, which for a reused answer is the copy, so without
  -- this a thumbs-down marked a row nobody would ever be served again and left
  -- the original in circulation.
  reused_from uuid references answers(id) on delete set null,

  -- The question, embedded. Duplicate detection is a similarity search over
  -- this column. Added now rather than Tuesday because altering a populated
  -- table mid-hackathon is how we lose an evening.
  question_embedding vector(1024)
);

create index answers_embedding_idx
  on answers using hnsw (question_embedding vector_cosine_ops);
create index answers_group_idx on answers (group_id, asked_at desc);

-- Rate limiting counts a person's recent questions on every request, so it
-- gets its own index rather than scanning the table each time.
create index answers_asker_idx on answers (asked_by, asked_at desc);

-- Who is who.
--
-- A WhatsApp export identifies anyone outside the exporter's address book by
-- phone number, and 153 of the 153 authors in our own export are numbers. A
-- bot answering "+229 97 42 65 40 said ..." in front of the whole group is
-- both unreadable and a small privacy leak, so every citation resolves
-- through this table first.
--
-- Names arrive from three places, best last: the vCards bundled in an export,
-- the pushName the Baileys worker sees at runtime, and manual corrections.
create table people (
  id uuid primary key default gen_random_uuid(),
  group_id text not null,
  handle text not null,        -- as seen, e.g. '+229 97 42 65 40'
  handle_norm text generated always as (normalize_handle(handle)) stored,
  display_name text not null,
  origin text,                 -- 'vcard' | 'pushname' | 'manual'
  updated_at timestamptz default now()
);

-- One row per person per group, whatever spelling they arrived under.
create unique index people_key on people (group_id, handle_norm);

-- Somebody was named in a message and has not come back to it.
--
-- The hackathon brief opens with "people miss messages". Everything else here
-- answers that passively - you have to think to ask. This is the one place
-- the bot goes looking for you, and it does it in a direct message so the
-- group hears nothing.
create table mentions (
  id uuid primary key default gen_random_uuid(),
  utterance_id uuid not null references utterances(id) on delete cascade,
  -- Normalised on the way in, so a mention written as a JID matches the same
  -- person seen in an export as a phone number.
  user_norm text not null,
  created_at timestamptz default now(),
  -- Set once the worker confirms it has told them. Never send twice: a bot
  -- that repeats itself in private is a bot people block.
  notified_at timestamptz
);

create unique index mentions_key on mentions (utterance_id, user_norm);
create index mentions_pending_idx on mentions (user_norm) where notified_at is null;

-- Powers the catch-up feature: everything said after a user's last_seen_at
-- is what they missed.
create table user_state (
  user_id text primary key,    -- WhatsApp JID, e.g. '223XXXXXXXX@s.whatsapp.net'
  display_name text,
  last_seen_at timestamptz,
  updated_at timestamptz default now()
);

-- A document, translated once and kept.
--
-- The hackathon guidelines exist in the group as an English PDF. Half this
-- group works in French and has said so, in this group. Translating the
-- brief costs a model call and about a minute; it must not cost that again
-- for the second person who asks. The English rendering is stored too, so
-- both languages are served from one place.
create table document_renderings (
  source_id uuid not null references sources(id) on delete cascade,
  lang text not null,
  text text not null,
  built_at timestamptz not null default now(),
  primary key (source_id, lang)
);

-- The nightly poll: does the group want this bot.
--
-- Distinct from satisfaction, which asks one person once, in private, after
-- five questions. This is a WhatsApp poll posted in the group every evening,
-- so the same person votes again tomorrow and the tally is visible to all
-- 390 members. That visibility is the point: the hackathon is decided by a
-- vote of the group.
create table poll_votes (
  id uuid primary key default gen_random_uuid(),
  group_id text not null,

  -- The WhatsApp id of the poll message. A vote arrives carrying the id of
  -- the poll it belongs to and nothing else, which is also what keeps two
  -- evenings' votes apart.
  poll_id text not null,

  -- The evening the poll was posted, in UTC, which for Mali is local time.
  poll_day date not null,

  voter text not null,
  -- 'yes' or 'no'. Stored as the meaning, not as the button text: the poll
  -- is bilingual and the option somebody tapped was spelled in whichever
  -- language they read.
  choice text not null check (choice in ('yes', 'no')),

  voted_at timestamptz not null default now(),

  -- WhatsApp lets a person change their vote, and sends the whole new
  -- selection when they do. One row per person per poll, overwritten: the
  -- last thing they said is what they think.
  unique (poll_id, voter)
);

create index poll_votes_group_day on poll_votes (group_id, poll_day desc);
