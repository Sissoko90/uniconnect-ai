-- The nightly poll: does the group want this bot.
--
-- Distinct from satisfaction, which asks one person once, in private, after
-- five questions. This is a WhatsApp poll posted in the group every evening,
-- so the same person votes again tomorrow and the tally is visible to all
-- 390 members. That visibility is the point: the hackathon is decided by a
-- vote of the group, and a poll everybody can see the result of is the only
-- honest way to ask a question whose answer we would like to be yes.

create table if not exists poll_votes (
  id uuid primary key default gen_random_uuid(),
  group_id text not null,

  -- The WhatsApp id of the poll message. A vote arrives carrying the id of
  -- the poll it belongs to and nothing else, which is also what keeps two
  -- evenings' votes apart.
  poll_id text not null,

  -- The evening the poll was posted, in UTC, which for Mali is local time.
  -- Kept alongside poll_id so results can be read by date without joining
  -- back to a table of polls we do not need.
  poll_day date not null,

  voter text not null,
  -- 'yes' or 'no'. Stored as the meaning, not as the button text, because
  -- the poll is bilingual and the option somebody tapped was spelled in
  -- whichever language they read.
  choice text not null check (choice in ('yes', 'no')),

  voted_at timestamptz not null default now(),

  -- WhatsApp lets a person change their vote, and it sends the whole new
  -- selection when they do. One row per person per poll, overwritten: the
  -- last thing they said is what they think.
  unique (poll_id, voter)
);

create index if not exists poll_votes_group_day on poll_votes (group_id, poll_day desc);
