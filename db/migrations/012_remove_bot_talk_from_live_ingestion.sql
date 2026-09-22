-- Messages that were never the group speaking.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/012_remove_bot_talk_from_live_ingestion.sql
--
-- Two kinds, both stored by live ingestion, which never had the rule the
-- export parser has had since a question typed at a rival bot became the
-- source for somebody else's answer.
--
--   1. Commands given to another team's bot. "@~Jymns Bot Okay provide the
--      session video links" is an instruction to a machine, not something
--      the group said, exactly as "@ask what is the deadline" is not.
--
--   2. A bot's own output, posted into the group by an account whose name
--      gives nothing away. Our bot cited one of these: the link it gave was
--      correct and the message it credited was another bot's summary, so a
--      claim invented elsewhere came back wearing our citation.
--
-- Targeted on the content, never on the author. The two accounts that
-- carried these are real members of this group, with 40 messages between
-- them, arguing about bots in their own words. Deleting by author would
-- have erased people.
--
-- Safe to run twice.

begin;

create temporary table doomed as
select id from utterances
 where content ~* '^\s*@(ask\y|\S{1,30}\s+bot\y)'
    or lower(btrim(content)) like 'here is what i currently know about%'
    or lower(btrim(content)) like 'here''s what i currently know about%'
    or lower(btrim(content)) like 'voici ce que je sais actuellement sur%';

\echo 'Rows to remove:'
select count(*) from doomed;

-- Any answer that leaned on one of them. Not edited, removed: the text was
-- written from a source that is going away, and a stored answer is reused
-- for thirty days and shown to whoever asks next.
--
-- "any missing", not "none survive": an answer citing four messages, one of
-- which was a bot's, is still an answer built partly on a bot.
delete from answers a
 where exists (
   select 1 from unnest(a.cited_ids) as cited(id)
    where cited.id in (select id from doomed)
 );

delete from mentions where utterance_id in (select id from doomed);
delete from utterances where id in (select id from doomed);

commit;
