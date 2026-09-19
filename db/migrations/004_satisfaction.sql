-- How members rate the bot itself, not one of its answers.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/004_satisfaction.sql
--
-- After somebody has asked five questions they know what the thing is, and
-- that is when their opinion is worth having. The bot asks them once, in
-- private, and never again.
--
-- Its own table rather than a row in answers: a rating on an answer says
-- whether that answer was right, and this says whether the bot is worth
-- having. Mixing them would corrupt duplicate detection, which retires
-- answers that were rated down.
--
-- Safe to run twice.

create table if not exists satisfaction (
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
create unique index if not exists satisfaction_once
  on satisfaction (group_id, asked_by);

-- Resolving a reaction to the survey it belongs to.
create index if not exists satisfaction_message_idx
  on satisfaction (message_id) where message_id is not null;
