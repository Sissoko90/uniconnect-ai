-- Remove one bot's messages, found by its number rather than its name.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       -v bot=2290149486256 \
--       < db/migrations/009_remove_a_bot_by_number.sql
--
-- 007 removed the bots whose displayed name says so. This one never had a
-- name in our data: it arrived live, where a message is stored under the
-- sender's number, and its pushName was absent. So it sat in the corpus as
-- an ordinary member and became the single most prolific author in it,
-- 139 messages, and the most cited source in our answers.
--
-- It is a bot: its messages include "/pause", "/goodbye", and "The bot
-- currently active in the group is meti_bot". Everything it says is another
-- team's model talking, and some of it is invented. Citing it as the group
-- speaking is the worst thing this bot can do.
--
-- Pass the number as :bot, digits only, no plus sign. normalize_handle
-- makes the match work whether the row was written as "+229 01 49 48 62 56"
-- by an export or "+2290149486256" by the live worker.
--
-- Safe to run twice.

begin;

create temporary view bot_rows as
select u.id
from utterances u
join sources s on s.id = u.source_id
where s.kind = 'chat'
  and u.author_norm = normalize_handle(:'bot');

select count(*) as messages_found from bot_rows;

delete from answers a
where a.cited_ids is not null
  and exists (select 1 from unnest(a.cited_ids) as cited
              where cited in (select id from bot_rows));

delete from utterances where id in (select id from bot_rows);

-- And the name, if one was ever recorded for it.
delete from people where handle_norm = normalize_handle(:'bot');

select count(*) as utterances_remaining from utterances;

commit;
