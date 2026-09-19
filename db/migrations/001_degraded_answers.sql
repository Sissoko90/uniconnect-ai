-- Add answers.degraded, and retire the degraded answers already stored.
--
-- schema.sql only runs when the database volume is created, so a database
-- that is already carrying the group's history needs this applied by hand:
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/001_degraded_answers.sql
--
-- Why. With the Anthropic balance empty the bot falls back to quoting the
-- closest message it found. That is a reasonable thing to do for one request
-- and a bad thing to keep: the quote was stored like any other answer, so
-- duplicate detection served it back for thirty days to everybody who asked
-- the same question, including after the balance was topped up.
--
-- Safe to run twice.

alter table answers
  add column if not exists degraded boolean not null default false;

-- The answers already stored from the outage. They are recognisable by the
-- sentence the fallback appends, in either language, and they are marked
-- rather than deleted so they still count in the usage metrics and in the
-- spend ledger. Marking is enough: find_duplicate skips them.
update answers
   set degraded = true
 where degraded = false
   and (answer like '%Quoting the closest message%'
     or answer like '%Je cite le message le plus proche%');

select count(*) as degraded_answers_retired from answers where degraded;
