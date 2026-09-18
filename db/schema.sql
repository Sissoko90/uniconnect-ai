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

  -- The question, embedded. Duplicate detection is a similarity search over
  -- this column. Added now rather than Tuesday because altering a populated
  -- table mid-hackathon is how we lose an evening.
  question_embedding vector(1024)
);

create index answers_embedding_idx
  on answers using hnsw (question_embedding vector_cosine_ops);
create index answers_group_idx on answers (group_id, asked_at desc);

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

-- Powers the catch-up feature: everything said after a user's last_seen_at
-- is what they missed.
create table user_state (
  user_id text primary key,    -- WhatsApp JID, e.g. '223XXXXXXXX@s.whatsapp.net'
  display_name text,
  last_seen_at timestamptz,
  updated_at timestamptz default now()
);
