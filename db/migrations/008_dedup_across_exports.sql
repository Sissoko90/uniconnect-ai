-- Remove the copy of a message that carries a phone number as its author,
-- when the same words are also stored under a real name.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/008_dedup_across_exports.sql
--
-- Two exports of the same group, taken from two phones, do not
-- de-duplicate against each other. The unique index compares author and
-- timestamp, and an iOS export writes seconds and real names where an
-- Android one writes neither: "Stanley Ojika" at 10:51:00 and
-- "+234 909 369 6284" at 10:51 are two rows to the index and one message to
-- everybody else. Loading the second export added 2279 rows, none of which
-- matched.
--
-- The named copy is the one to keep. It is the same text, and a citation
-- that says "Stanley Ojika" is worth more than one that says "+234…84".
--
-- Matched on identical text within five minutes, not on timestamp: the two
-- phones disagree by seconds, and a message repeated days apart is a
-- different message that both copies should keep.
--
-- Safe to run twice.

begin;

create temporary view redundant as
select numbered.id
from utterances numbered
join sources s on s.id = numbered.source_id
where s.kind = 'chat'
  and numbered.author like '+%'
  and exists (
    select 1
    from utterances named
    where named.source_id = numbered.source_id
      and named.author not like '+%'
      and named.content = numbered.content
      and named.said_at between numbered.said_at - interval '5 minutes'
                            and numbered.said_at + interval '5 minutes'
  );

select count(*) as duplicates_found from redundant;

-- Answers citing a row about to go would be left pointing at nothing.
delete from answers a
where a.cited_ids is not null
  and exists (select 1 from unnest(a.cited_ids) as cited
              where cited in (select id from redundant));

delete from utterances where id in (select id from redundant);

select count(*) as utterances_remaining from utterances;

commit;
