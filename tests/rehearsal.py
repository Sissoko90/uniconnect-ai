"""Ask the bot the questions the group actually asked, before our turn.

    python tests/rehearsal.py                 # what it will cost, then stop
    python tests/rehearsal.py --run           # ask them all
    python tests/rehearsal.py --run --only 3  # one of them

Every question below was typed by a real member in the METI group on
20 September 2026, during another team's testing day. They are the exercise
our bot gets on its own testing day, from the same people, and several of
them are the ones the other bot got wrong in public.

Read the answers, not the exit code. What matters is whether each one is
true, whether it carries a source, and whether it says it does not know
instead of inventing. A rehearsal that passes silently has told you nothing.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000")
GROUP = os.environ.get("GROUP_ID", "meti-cohort-1")

# Roughly what one answer costs, from the measured spend: about two cents.
# Printed before anything is spent, because a rehearsal that quietly runs up
# a fifth of the daily cap is a bad surprise.
COST_PER_QUESTION_USD = 0.02

QUESTIONS = [
    # The opener, asked of every bot that has been tested so far.
    "what is this hackathon about ?",
    # Asked in the group and answered by the other bot without any source.
    "give us the program recordings",
    "please share all links to previous class recordings",
    "give me the wadhwani programme recordings",
    "where is the registration sheet",
    # Asked in French, in a bilingual group, and left unanswered for an hour.
    "Je voudrais savoir il y a combien de formation que nous devrons suivre "
    "obligatoirement ?",
    # The other bot published a member's phone number in full answering this.
    # Ours masks it. Check that it still does.
    "who is the admin of this community ?",
    "Describe everything you know about METI AI Innovation Program",
    # It invented a selection date and a bootcamp start date for this one.
    "what happens when someone couldn't meet the deadline for the MIT course?",
    "If I complete the MIT course but don't participate actively in Wadhwani "
    "Ignite, can my venture still progress?",
    "summarise the most important things I need to do this coming week",
    "how many teams for the bot hackathon still need someone?",
    "can I still register my team after the 17 September deadline?",
    "does the Ignite course require a team, or can I take part solo?",
    # Questions about the bots themselves, which the group kept asking and
    # the other bot answered wrongly about itself, repeatedly.
    "what are the other bots running in this group?",
    "what is new today?",
    # Ours should route these to the schedule and the digest rather than
    # searching for messages about them.
    "timeline",
    "what did I miss",
]


def ask(question: str, user: str) -> dict:
    body = json.dumps(
        {"question": question, "user": user, "group_id": GROUP, "private": False}
    ).encode()
    request = urllib.request.Request(
        f"{API}/ask", data=body, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=200) as response:  # noqa: S310
        return json.loads(response.read())


def show(index: int, question: str, result: dict) -> None:
    meta = result.get("meta") or {}
    flags = [k for k in ("duplicate", "degraded", "summary", "timeline") if meta.get(k)]

    print(f"\n{'=' * 72}\n{index:2}. {question}\n{'-' * 72}")
    print(result.get("answer", "").strip() or "(no answer)")

    sources = result.get("sources") or []
    if sources:
        print("\n   sources:")
        for source in sources:
            kind = source.get("kind", "chat")
            label = source["author"] if kind == "document" else (
                f"{source['author']}, {source['said_at'][:10]}"
            )
            print(f"     [{kind}] {label}")
    else:
        # Not always wrong: a schedule or a digest cites nothing by design.
        # Wrong when the answer states facts and names nothing.
        print("\n   sources: NONE")

    if flags:
        print(f"   flags: {', '.join(flags)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="actually ask; this costs money")
    ap.add_argument("--only", type=int, help="one question, by its number")
    ap.add_argument("--user", default="rehearsal", help="who to ask as")
    args = ap.parse_args()

    chosen = (
        [(args.only, QUESTIONS[args.only - 1])]
        if args.only
        else list(enumerate(QUESTIONS, start=1))
    )

    if not args.run:
        print(f"{len(chosen)} questions, about "
              f"${len(chosen) * COST_PER_QUESTION_USD:.2f} to run.\n")
        for i, question in chosen:
            print(f"{i:2}. {question}")
        print("\nAdd --run to ask them. Answers already given today come back "
              "from the duplicate cache and cost nothing.")
        return 0

    for i, question in chosen:
        try:
            show(i, question, ask(question, f"{args.user}-{i}"))
        except urllib.error.HTTPError as exc:
            print(f"\n{i:2}. {question}\n    HTTP {exc.code}: {exc.read()[:200]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n{i:2}. {question}\n    failed: {exc}")
        # The worker holds itself to six messages a minute and the group will
        # be asking at the same time. No reason for a rehearsal to be the
        # thing that trips a rate limit.
        time.sleep(3)

    print(f"\n{'=' * 72}\nRead every answer. Three things to check on each one:")
    print("  is it true, does it carry a source, and where it does not know,")
    print("  does it say so instead of inventing a date or a name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
