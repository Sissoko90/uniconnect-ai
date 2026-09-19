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
  -- Voice notes are the thing nobody else made searchable, so they are worth
  -- counting separately rather than hiding inside the message total.
  (select count(*) from utterances where content like '[voice note]%')
                                                                   as voice_notes,
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
    where asked_at > now() - interval '24 hours')                  as questions_today,
  (select count(*) from answers
    where asked_at > now() - interval '7 days')                    as questions_this_week,
  -- Somebody told privately that the group was waiting on them. The one
  -- place the bot goes looking for people instead of waiting to be asked.
  (select count(*) from mentions where notified_at is not null)     as people_reminded,
  -- How many citations an answer carries on average. One is a quote; three
  -- means it pulled a fact out of several conversations.
  (select round(avg(array_length(cited_ids, 1)), 1) from answers
    where cited_ids is not null and array_length(cited_ids, 1) > 0) as sources_per_answer,
  (select count(distinct date_trunc('day', asked_at)) from answers) as days_used
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




# One self-contained page: no build step, no framework, nothing extra to
# deploy. It is opened on a phone, by people deciding how to vote, so it has
# to say something true in the first three seconds.
#
# The palette is the logo's: cream, ink, terracotta.
PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UniConnect AI, usage</title>
<link rel="icon" href="/logo.png" type="image/png">
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f7f4ee; --fg: #14181d; --muted: #6b6b6b;
    --line: #e2ddd3; --card: #fffdf9; --accent: #c0551d;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #14181d; --fg: #ece9e3; --muted: #9a9a9a;
      --line: #2a2f36; --card: #1b2026; --accent: #e07a42;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0 16px 64px; background: var(--bg); color: var(--fg);
    font: 16px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif;
  }}
  main {{ max-width: 720px; margin-inline: auto; padding-block: 28px 0; }}
  .back {{
    display: inline-flex; align-items: center; gap: 7px; color: var(--muted);
    text-decoration: none; font-size: .9rem; margin-bottom: 26px;
  }}
  .back:hover {{ color: var(--accent); }}
  header {{ display: flex; align-items: center; gap: 14px; margin-bottom: 6px; }}
  header img {{ width: 44px; height: 44px; border-radius: 11px; flex: none; }}
  h1 {{ font-size: 1.45rem; margin: 0; letter-spacing: -0.01em; }}
  p.sub {{ color: var(--muted); margin: 0 0 30px; font-size: .92rem; }}
  h2 {{
    font-size: .78rem; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); font-weight: 600; margin: 34px 0 12px;
  }}
  .grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(146px, 1fr));
    gap: 11px;
  }}
  .tile {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 15px 16px;
  }}
  .n {{ font-size: 1.75rem; font-weight: 650; font-variant-numeric: tabular-nums;
        line-height: 1.15; }}
  .n.hl {{ color: var(--accent); }}
  .l {{ font-size: .79rem; color: var(--muted); margin-top: 3px; }}
  .chart {{
    display: flex; align-items: flex-end; gap: 6px; height: 120px;
    padding: 14px 16px; background: var(--card);
    border: 1px solid var(--line); border-radius: 12px;
  }}
  .bar {{ flex: 1; display: flex; flex-direction: column; justify-content: flex-end;
          align-items: center; gap: 5px; height: 100%; min-width: 0; }}
  .bar i {{
    display: block; width: 100%; background: var(--accent); border-radius: 3px;
    min-height: 2px; opacity: .85;
  }}
  .bar b {{ font-size: .7rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .bar span {{ font-size: .65rem; color: var(--muted); white-space: nowrap;
               overflow: hidden; text-overflow: ellipsis; max-width: 100%; }}
  .empty {{ color: var(--muted); font-size: .9rem; }}
  footer {{
    margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: .83rem;
  }}
</style></head><body>
<main>
  <a class="back" href="/">&#8592; Ask the bot</a>

  <header>
    <img src="/logo.png" alt="" width="44" height="44">
    <h1>UniConnect AI</h1>
  </header>
  <p class="sub">What the group actually used. Read live from the database.</p>

  <h2>People</h2>
  <div class="grid">{people}</div>

  <h2>Questions per day</h2>
  {chart}

  <h2>What it has read</h2>
  <div class="grid">{knows}</div>

  <h2>How well it answers</h2>
  <div class="grid">{quality}</div>

  <footer>{footer}</footer>
</main>
</body></html>
"""


def _tiles(items):
    return "".join(
        f'<div class="tile"><div class="n{" hl" if hl else ""}">{value}</div>'
        f'<div class="l">{label}</div></div>'
        for label, value, hl in items
    )


def _chart(by_day):
    """Questions per day, as bars.

    Deliberately simple: no chart library on a page whose whole point is that
    it opens instantly on a phone. Bars are scaled against the busiest day,
    with the count printed above each, so the shape and the number are both
    readable without a tooltip.
    """
    if not by_day:
        return '<p class="empty">No questions yet.</p>'

    recent = by_day[-14:]
    peak = max(d["questions"] for d in recent) or 1

    bars = []
    for day in recent:
        height = max(2, round(100 * day["questions"] / peak))
        label = day["day"][5:]  # MM-DD, the year is not the interesting part
        bars.append(
            f'<div class="bar"><b>{day["questions"]}</b>'
            f'<i style="height:{height}%"></i><span>{label}</span></div>'
        )
    return f'<div class="chart">{"".join(bars)}</div>'


def page(pool) -> str:
    data = summary(pool)
    t = data["totals"]

    # Adoption first. The judges are the users, so "how many of us used it" is
    # the figure that actually decides anything.
    people = _tiles([
        ("Members who asked", t["people_served"], True),
        ("Questions answered", t["questions_answered"], True),
        ("Asked in the last 24h", t["questions_today"], False),
        ("Reminded privately", t["people_reminded"], False),
    ])

    knows = _tiles([
        ("Messages indexed", f'{t["messages_indexed"]:,}'.replace(",", " "), False),
        ("Voice notes transcribed", t["voice_notes"], t["voice_notes"] > 0),
        ("Calls transcribed", t["calls_ingested"], False),
        ("People known by name", t["people_named"], False),
    ])

    coverage = t["source_coverage_pct"]
    quality = _tiles([
        ("Answers carrying a source", f"{coverage or 0}%", True),
        ("Sources per answer", t["sources_per_answer"] or 0, False),
        ("Rated helpful", t["rated_helpful"], False),
        ("Days in use", t["days_used"], False),
    ])

    footer = (
        "Every answer this bot gives cites the message it came from, and it "
        "says so when the group never answered the question. "
        "The percentage above is how often it found a source, not how often "
        "it replied."
    )

    return PAGE.format(
        people=people,
        chart=_chart(data["by_day"]),
        knows=knows,
        quality=quality,
        footer=footer,
    )
