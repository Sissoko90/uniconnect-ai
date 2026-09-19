-- Remove the conversation with the bot from the searchable history.
--
-- Run once on a database loaded from an export made after the bot went live:
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       -f /dev/stdin < db/cleanup_bot_traffic.sql
--
-- Why this exists. The morning after launch, "what is the submission
-- deadline?" was answered with 'According to Is any of it real: "@ask give me
-- a summary"'. Every question people had put to the bot had been indexed as
-- something the group said, so questions were being returned as answers to
-- other questions, and the bot's own replies were available to be quoted back
-- to it. The parser and the worker both refuse these now; this clears what
-- they had already written.
--
-- Deleting rather than flagging: an utterance nobody should ever cite has no
-- second use, and the embedding it carries is the thing doing the damage.
-- mentions cascade, so no orphans are left behind.

begin;

-- Reported before and after so the count is visible in the psql output
-- rather than having to be trusted.
select count(*) as bot_traffic_before
from utterances
where content ~* '^\s*@ask\b' or author ilike 'uniconnect%';

delete from utterances
where content ~* '^\s*@ask\b'
   or author ilike 'uniconnect%';

select count(*) as utterances_remaining from utterances;

commit;
