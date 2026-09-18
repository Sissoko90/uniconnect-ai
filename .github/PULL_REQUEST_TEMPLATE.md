## What this changes

<!-- One or two sentences. What behaviour is different after this? -->

## Why

<!-- The problem, not the solution. Link an issue if there is one. -->

## How it was checked

<!-- What you actually ran. "Tests pass" on its own is not a check. -->

- [ ] `ruff check .` and `pytest` pass locally
- [ ] Tried it against real data, not only fixtures
- [ ] A bug fix here comes with a test that fails without the fix

## Before merging

- [ ] No `.env`, chat export, recording or `auth_info*/` in the diff
- [ ] `POST /ask` still accepts `question`, `user`, `group_id` and returns
      `answer` and `sources` — the contract is frozen, fields may be added
      but never renamed or removed
- [ ] Schema changed? Say so here, and tell Makan — the schema applies only
      to a fresh database volume
- [ ] Docs updated if behaviour changed (`docs/SETUP.md` is graded)
