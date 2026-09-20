-- Remove other teams' bots from the searchable history.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/006_remove_bot_messages.sql
--
-- A stored message is a message that can be cited. On the day a rival bot
-- was tested in the group, ours answered "Per the bot's reply in the group:
-- yes, you can still move forward..." and cited it, relaying another bot's
-- invention as something the group had said. Asked who the community admin
-- was, it read out a coordinator's phone number in full, taken from the
-- same bot's message.
--
-- Nothing a bot says belongs in a record of what the group said. Ours
-- included: a bot that can cite itself will eventually agree with itself
-- about something it invented.
--
-- Safe to run twice.

begin;

select count(*) as bot_messages_found
from utterances u
join sources s on s.id = u.source_id
where s.kind = 'chat'
  and (u.author ~* '(^|[^a-z])bot([^a-z]|$)' or u.author ilike 'meti\_bot' or
       u.author ilike '%podpal%' or u.author ilike '%uniconnect%');

delete from utterances u
using sources s
where s.id = u.source_id
  and s.kind = 'chat'
  and (u.author ~* '(^|[^a-z])bot([^a-z]|$)' or u.author ilike 'meti\_bot' or
       u.author ilike '%podpal%' or u.author ilike '%uniconnect%');

-- Answers that cited one of them are now citing rows that no longer exist,
-- and a citation pointing at nothing is worse than no citation. They were
-- our own test answers from the same day; the group has not seen them.
delete from answers
where cited_ids is not null
  and not exists (
    select 1 from utterances u where u.id = any(cited_ids)
  );

select count(*) as utterances_remaining from utterances;

commit;
