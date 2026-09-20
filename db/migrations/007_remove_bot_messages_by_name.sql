-- Remove other teams' bots, looking where their names actually are.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/007_remove_bot_messages_by_name.sql
--
-- 006 tried this and deleted nothing. It matched on utterances.author,
-- which for a message ingested live holds the sender's phone number, not
-- their name: "+234...". The name arrives separately, as a WhatsApp
-- pushName, and lands in people.display_name, which is what a citation
-- prints. So the rows were there, the citations said "Nexus Bot", and the
-- delete matched nothing at all.
--
-- Messages read from an export are the other way round: there the author
-- column does hold the displayed name. Both have to be covered.
--
-- Safe to run twice, and safe to run after 006.

begin;

-- Anything whose name is, or resolves to, a bot. A word boundary on "bot"
-- so that Talbot and Robert are people.
create temporary view bot_utterances as
select u.id
from utterances u
join sources s on s.id = u.source_id
left join people p
  on p.group_id = s.group_id and p.handle_norm = u.author_norm
where s.kind = 'chat'
  and (
        u.author ~* '(^|[^[:alnum:]])bot([^[:alnum:]]|$)'
     or u.author ilike '%podpal%'
     or p.display_name ~* '(^|[^[:alnum:]])bot([^[:alnum:]]|$)'
     or p.display_name ilike '%podpal%'
  );

select count(*) as bot_messages_found from bot_utterances;

delete from utterances where id in (select id from bot_utterances);

-- Any answer that cited one of them. ANY missing source is enough: an
-- answer citing one bot and one member is exactly what this is here to
-- remove, and duplicate detection would serve it for thirty days.
delete from answers a
where a.cited_ids is not null
  and exists (
    select 1 from unnest(a.cited_ids) as cited
    where not exists (select 1 from utterances u where u.id = cited)
  );

-- And the names themselves, so nothing can resolve to them again. Live
-- ingestion no longer stores a bot's messages, so these are not recreated.
delete from people
where display_name ~* '(^|[^[:alnum:]])bot([^[:alnum:]]|$)'
   or display_name ilike '%podpal%';

select count(*) as utterances_remaining from utterances;
select count(*) as answers_remaining from answers;

commit;
