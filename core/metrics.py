"""Usage metrics, for the people who decide the prize.

The judges are the group members. They vote for what they used, so the honest
argument on Thursday is not a demo, it is a count: this many questions asked,
by this many different people, this many answered from the group's own
history. Numbers that come out of the answers table, not out of a slide.

Every figure here is measured. If something cannot be measured yet it is
absent rather than estimated.
"""

from psycopg.rows import dict_row

SUMMARY_SQL = """
select
  (select count(*) from utterances)                                as messages_indexed,
  (select count(*) from utterances where embedding is not null)    as messages_embedded,
  (select count(*) from sources where kind = 'chat')               as chats_ingested,
  (select count(*) from sources where kind = 'call')               as calls_ingested,
  (select count(*) from people)                                    as people_named,
  (select count(*) from answers)                                   as questions_answered,
  (select count(distinct asked_by) from answers)                   as people_served,
  -- An answer with no citation is an answer we could not source. Tracking it
  -- keeps us honest about coverage instead of counting every reply a win.
  (select count(*) from answers
    where cited_ids is not null and array_length(cited_ids, 1) > 0) as answers_with_sources,
  (select count(*) from answers where rating = 1)                  as rated_helpful,
  (select count(*) from answers where rating = -1)                 as rated_unhelpful,
  (select count(*) from answers
    where asked_at > now() - interval '24 hours')                  as questions_today
"""

BY_DAY_SQL = """
select date_trunc('day', asked_at)::date as day, count(*) as questions
from answers
group by day
order by day
"""

TOP_ASKERS_SQL = """
select asked_by, count(*) as questions
from answers
group by asked_by
order by questions desc
limit 10
"""

# This page is public - it is meant to be, the judges open it. But asked_by is
# a WhatsApp JID in production, which is a member's phone number, and "who
# uses the bot most" is not a fact any of them agreed to publish. The count is
# the interesting part; the identity is not.
SHOW_IDENTITIES = False


def summary(pool) -> dict:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SUMMARY_SQL)
            totals = cur.fetchone()

            cur.execute(BY_DAY_SQL)
            by_day = [{"day": r["day"].isoformat(), "questions": r["questions"]} for r in cur]

            cur.execute(TOP_ASKERS_SQL)
            askers = cur.fetchall()

    if not SHOW_IDENTITIES:
        # Rank without naming: "our busiest member asked 23 questions" is the
        # figure worth showing, and it says nothing about who they are.
        askers = [
            {"rank": i, "questions": row["questions"]}
            for i, row in enumerate(askers, start=1)
        ]

    answered = totals["questions_answered"] or 0
    sourced = totals["answers_with_sources"] or 0
    totals["source_coverage_pct"] = round(100 * sourced / answered, 1) if answered else None

    return {"totals": totals, "by_day": by_day, "top_askers": askers}


# A single self-contained page: no build step, no framework, nothing to
# deploy. It is opened once, by judges, on a phone.
PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UniConnect AI - usage</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; padding: 24px;
         max-width: 720px; margin-inline: auto; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  p.sub {{ margin: 0 0 24px; opacity: .7; font-size: .9rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: 12px; margin-bottom: 28px; }}
  .tile {{ border: 1px solid color-mix(in srgb, currentColor 18%, transparent);
           border-radius: 10px; padding: 14px; }}
  .n {{ font-size: 1.8rem; font-weight: 650; font-variant-numeric: tabular-nums; }}
  .l {{ font-size: .8rem; opacity: .75; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
  th, td {{ text-align: left; padding: 6px 8px;
            border-bottom: 1px solid color-mix(in srgb, currentColor 12%, transparent); }}
  td.n2 {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style></head><body>
<h1>UniConnect AI</h1>
<p class="sub">What the group actually used. Live from the database.</p>
<div class="grid">{tiles}</div>
<h2 style="font-size:1rem">Questions per day</h2>
<table>{days}</table>
</body></html>
"""


def page(pool) -> str:
    data = summary(pool)
    t = data["totals"]

    tiles = [
        ("Questions asked", t["questions_answered"]),
        ("People served", t["people_served"]),
        ("Asked today", t["questions_today"]),
        ("Messages indexed", t["messages_indexed"]),
        ("Answers with a source", f'{t["source_coverage_pct"] or 0}%'),
        ("Rated helpful", t["rated_helpful"]),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="n">{v}</div><div class="l">{k}</div></div>'
        for k, v in tiles
    )

    days_html = "<tr><th>Day</th><th style='text-align:right'>Questions</th></tr>" + "".join(
        f'<tr><td>{d["day"]}</td><td class="n2">{d["questions"]}</td></tr>'
        for d in data["by_day"]
    )

    return PAGE.format(tiles=tiles_html, days=days_html)
