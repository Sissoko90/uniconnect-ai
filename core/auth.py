"""A shared secret between the worker and the API.

Most of this API is not public. `/alerts` says who was named in a private
group and quotes what was said to them; `/catchup` is one member's personal
briefing; `/messages` and `/voice` write to the history everything else is
read from; `/digest`, `/recap` and `/timeline` each cost real money per call.

None of that was protected, and our own nginx configuration proxies the whole
API - so the day we deployed, all of it would have been on the open internet.
The worker and the API share a host, but "on the same host" stops being a
boundary the moment a reverse proxy is put in front.

One token, sent as a header. Not sophisticated: it is a hackathon, the two
processes are ours, and a bearer token closes the hole completely. What it is
not is optional - an unset token disables the protected endpoints rather than
opening them, because a default that fails safe is the only kind worth having.
"""

import hmac
import os

from fastapi import Header, HTTPException

HEADER = "x-uniconnect-token"

NOT_CONFIGURED = (
    "This endpoint is disabled because WORKER_TOKEN is not set on the API. "
    "Set it in .env, restart, and send it as the x-uniconnect-token header."
)


def configured() -> bool:
    return bool(os.environ.get("WORKER_TOKEN", "").strip())


def require_worker(x_uniconnect_token: str = Header(default="")) -> None:
    """FastAPI dependency. Raises unless the caller knows the token."""
    expected = os.environ.get("WORKER_TOKEN", "").strip()

    if not expected:
        # Refusing is the safe failure. It is loud, it is immediate, and the
        # message says exactly how to fix it - unlike silently serving a
        # private group's messages to anybody who guesses the group id.
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)

    # Anything that is not a string counts as no token. FastAPI resolves the
    # header into one, but called any other way the default is the Header
    # marker object - and a missing header must fail closed rather than raise
    # an AttributeError that reads as a server fault.
    given = x_uniconnect_token.strip() if isinstance(x_uniconnect_token, str) else ""

    # compare_digest, not ==: string comparison returns early on the first
    # wrong byte, which leaks the token one character at a time to anybody
    # patient enough to measure.
    if not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="bad or missing worker token")
