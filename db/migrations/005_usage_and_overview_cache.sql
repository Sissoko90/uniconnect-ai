-- Count what every model call costs, and stop rebuilding the same overview.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/005_usage_and_overview_cache.sql
--
-- Two problems, one migration, because they are the same problem seen twice:
-- the expensive calls were neither measured nor reused.
--
-- The daily spend cap is measured from answers.input_tokens, so it only ever
-- saw questions. The digest, the call recap, the timeline, the catch-up and
-- the whole-group overview recorded nothing at all, and the overview is the
-- most expensive call in the project: it sends nine hundred messages to the
-- model, about 25 cents a time. A hundred and fifty members asking for one
-- each would cost forty dollars and the ten dollar cap would not notice.
--
-- Safe to run twice.

create table if not exists model_usage (
  id uuid primary key default gen_random_uuid(),
  -- 'digest' | 'overview' | 'call_recap' | 'timeline' | 'catchup'
  kind text not null,
  group_id text,
  input_tokens int,
  output_tokens int,
  used_at timestamptz not null default now()
);

create index if not exists model_usage_day_idx on model_usage (used_at);

-- The whole-group overview, kept so it is not rebuilt for every person who
-- asks. It takes over a minute and reads the entire history, and that
-- history grows by a few messages an hour: two members asking within the
-- same morning should not pay for it twice.
create table if not exists overview_cache (
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
