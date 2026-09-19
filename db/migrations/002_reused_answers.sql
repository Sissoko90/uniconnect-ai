-- Add answers.reused_from, so a reused answer stops being reusable itself.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/002_reused_answers.sql
--
-- Why. When a question is recognised as one already asked, the earlier answer
-- is served and the reuse is recorded as its own row, so that it counts
-- against the hourly limit and shows in the usage figures. That row was
-- indistinguishable from a fresh answer, which broke two things.
--
-- A copy is younger than the answer it came from, so each reuse minted a
-- fresher copy and the thirty-day age limit never applied to anything: one
-- answer stayed in circulation forever, including after the group's facts
-- moved on.
--
-- And feedback rates the last answer a person got, which for a reused answer
-- is the copy. A thumbs-down marked a row nobody would ever be served again
-- and left the original in circulation, which is exactly what the rating
-- filter was written to prevent.
--
-- Safe to run twice.

alter table answers
  add column if not exists reused_from uuid references answers(id) on delete set null;

-- Existing copies cannot be linked back with certainty, and guessing would
-- put ratings on the wrong rows. They are left unlinked: they age out on
-- their own within thirty days, and the behaviour is correct from here on.

select count(*) as answers_total from answers;
