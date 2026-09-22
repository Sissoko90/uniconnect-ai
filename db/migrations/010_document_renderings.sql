-- A document, translated once and kept.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/010_document_renderings.sql
--
-- The hackathon guidelines exist in the group as an English PDF. Half this
-- group works in French and has said, in this group, that they cannot
-- follow. Translating the brief costs a model call and about a minute; it
-- must not cost that again for the second person who asks.
--
-- Keyed on the source and the language. The English rendering is stored
-- too, so the page serves both from one place and the second reader waits
-- for nothing.
--
-- Safe to run twice.

create table if not exists document_renderings (
  source_id uuid not null references sources(id) on delete cascade,
  lang text not null,
  text text not null,
  built_at timestamptz not null default now(),
  primary key (source_id, lang)
);
