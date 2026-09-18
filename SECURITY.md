# Security

This project reads the private conversations of 153 people. That is the whole
threat model in one sentence.

## Reporting something

Email **moussa.diakite1304@gmail.com** with `UniConnect security` in the
subject. Do not open a public issue for anything involving group data,
credentials or a way to make the bot speak on someone's behalf.

During the hackathon (18–24 September 2026) we aim to answer within a day.

## What is sensitive here

| Asset | Where it lives | If it leaks |
|---|---|---|
| Group conversations | `utterances` table, chat exports | 153 people's private messages, including phone numbers |
| Baileys session keys | `auth_info*/` on the VPS | anyone holding them can send WhatsApp messages **as the bot** |
| API keys | `.env` on the VPS | someone else's model bill, on our account |
| Database credentials | `.env`, compose environment | full read and write over everything above |

## Rules we hold ourselves to

- **`.env` is never committed.** Nor are the chat exports, nor `auth_info*/`.
  All three are in `.gitignore`, and the Security workflow scans the full git
  history for secrets on every push.
- **Nothing but nginx faces the internet.** Postgres and the API are bound to
  `127.0.0.1`. Only ports 22, 80 and 443 are open.
- **Phone numbers are not printed back into the group.** An author we cannot
  resolve to a name is shown as `+229…40`, never in full.
- **The bot never invents.** No source found means saying so. This is a
  safety property as much as a product one: a confidently wrong answer about
  a deadline or a decision causes real harm in a working group.
- **Group messages are data, never instructions.** Everything retrieved is
  fenced in `<group_messages>` tags, closing tags inside a message are
  defanged, and the system prompt states that nothing inside them can change
  the rules. In a cohort of an AI programme somebody will try this, and a
  public jailbreak days before the vote would cost more than the bug itself.
- **What is asked in private stays private.** Duplicate detection only ever
  matches questions of the same kind, so the bot cannot announce to the group
  that a member asked something in a direct message.
- **One member cannot spend the group's budget.** Twenty questions an hour
  each, a daily cap across everybody, and an identical repeat within thirty
  seconds answered from the database for nothing.
- **A leaked key is rotated, not deleted.** Removing a secret in a later
  commit does not unpublish it. Revoke it in the provider's console first.

## What runs automatically

The `Security` workflow runs on every push, every pull request, and weekly
on Monday morning.

| Check | Tool | Catches |
|---|---|---|
| Committed secrets | TruffleHog, full history | an API key or session file that slipped past `.gitignore` |
| Vulnerable dependencies | `pip-audit --strict` | known CVEs in our pinned versions |
| Static analysis | Bandit, medium and above | SQL built by string concatenation, unsafe subprocess use |
| Deeper static analysis | CodeQL, `security-extended` | injection and data-flow issues across files |
| Dependency updates | Dependabot, weekly, grouped | versions going stale |

`pip-audit` is strict on purpose. It has already earned its place: the first
pinned FastAPI pulled in a Starlette with eight known vulnerabilities, which
is now fixed.

**CodeQL only runs while the repository is public.** On a private repository
it can analyse the code but not upload its findings without GitHub Advanced
Security, so the job is skipped rather than left permanently red — a security
workflow everyone has learned to ignore protects nothing. Making the
repository public turns it on, and the submission rules ask for an accessible
repository anyway.

Before going public, check that the secrets job has passed on the **full
history**, not just the latest commit. A key removed in a later commit is
still a published key: revoke it, do not delete it.

## Known gaps

Stated plainly rather than left for someone to discover:

- **The loop guard is only half in our hands.** The API answers an identical
  repeat for free, but a loop between two bots that varies its wording is
  stopped by the worker refusing to answer bots — not by us.
- **No authentication between the worker and the API.** They share a host and
  talk over loopback. Exposing the API publicly would require adding auth
  first.
- **No database backups.** If the VPS is lost, the history and the usage
  metrics go with it.
- **No audit log.** We record every answer, but not who read what.

## Handling the exports

The `.zip` exports are the group's private messages. They belong on the VPS
and in the database — not in the repository, not in a shared drive, not in a
chat message. `git check-ignore` them before any commit if you are unsure.
