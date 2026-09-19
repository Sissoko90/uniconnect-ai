"""What is this person actually asking for.

Pure text, no database and no model, so it can be tested without either.

There is only one decision here so far, and it comes from a real failure:
"Give me a summary of the group" was answered with "I could not find anything
about this in the group history". That is honest, it is what the retrieval
genuinely found, and it reads as broken. The bot looks for messages *about*
the subject asked, and nobody has ever written a message titled "summary of
the group".

It is also the first thing almost anybody types.
"""

import re

# Stripped because clients mirror the WhatsApp trigger. The worker removes it
# before sending; the web page has nothing to mention, so it does not, and
# "@ask" ends up inside the question where it is just noise in the search.
TRIGGER = re.compile(r"^\s*@ask\b[:,]?\s*", re.IGNORECASE)

SUMMARY_PHRASES = (
    "summary", "summarise", "summarize", "sum up", "overview", "recap",
    "what's happening", "whats happening", "what is happening", "catch me up",
    "résumé", "resume", "resume-moi", "recapitulatif", "récapitulatif",
    "quoi de neuf", "que se passe", "ce qui se passe",
)

# A summary *of something* is an ordinary question about that thing, and
# retrieval answers it better than a digest would: it cites the messages.
ABOUT_SOMETHING = (" about ", " on the ", " sur ", " de la ", " concernant ")


def strip_trigger(question: str) -> str:
    """Remove a leading @ask, leaving the question itself."""
    stripped = TRIGGER.sub("", question).strip()
    return stripped or question


def wants_a_summary(question: str) -> bool:
    """A request for the whole picture rather than a question about a thing."""
    lowered = question.lower()
    if not any(phrase in lowered for phrase in SUMMARY_PHRASES):
        return False
    return not any(marker in lowered for marker in ABOUT_SOMETHING)
