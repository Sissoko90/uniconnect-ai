-- An index for reading the messages around a match.
--
--   docker compose exec -T db psql -U uniconnect -d uniconnect \
--       < db/migrations/003_context_lookup.sql
--
-- Answers now include the two messages either side of each match, because a
-- chat message on its own is often meaningless: "Oui, vendredi 14h" answers
-- something asked two messages earlier, and the model was being handed the
-- answer without the question.
--
-- That lookup is "the rows in this source just before and just after this
-- timestamp". The existing indexes do not serve it: utterances_said_at_idx
-- ignores the source, and the de-duplication index has author between
-- source_id and said_at, so a range scan on said_at cannot use it.
--
-- Safe to run twice.

create index if not exists utterances_source_time_idx
  on utterances (source_id, said_at);
