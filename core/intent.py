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


# Somebody saying hello, not asking anything. Worth catching because the
# answer to a greeting is a message somebody once sent containing "bonjour",
# quoted back at them, which is the single worst thing this bot can do: it
# looks like it understood and it looks stupid.
GREETINGS = (
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "morning", "bonjour", "bonsoir", "salut", "coucou", "slt", "cc",
)

HELLO_BACK = {
    "en": (
        "Hello. Ask me about anything that has been said in the group. "
        'For example: "what is the submission deadline?" or '
        '"who do I contact about Wadhwani?"'
    ),
    "fr": (
        "Bonjour. Pose-moi une question sur ce qui s'est dit dans le groupe. "
        'Par exemple : "quelle est la date limite ?" ou '
        '"qui contacter pour Wadhwani ?"'
    ),
}


FRENCH_GREETINGS = {"bonjour", "bonsoir", "salut", "coucou", "slt", "tout", "monde", "tous"}


def greeting_language(question: str) -> str:
    """Which language to say hello back in.

    The general language detector reads whole sentences and has nothing to go
    on in a one-word message: "bonjour" was answered in English, which is a
    small thing that reads as the bot not paying attention.
    """
    words = set(re.findall(r"[\w']+", question.lower()))
    return "fr" if words & FRENCH_GREETINGS else "en"


def is_greeting(question: str) -> bool:
    """Only when the whole message is a greeting.

    "hi, what is the deadline" is a question with a polite opening, and
    answering it with a menu would be worse than useless.
    """
    words = re.findall(r"[\w']+", question.lower())
    if not words or len(words) > 4:
        return False
    # Every word has to be part of a greeting, so "good morning everyone"
    # passes and "morning session time" does not.
    filler = {"everyone", "all", "there", "tout", "le", "monde", "a", "tous"}
    return all(
        any(word in greeting.split() for greeting in GREETINGS) or word in filler
        for word in words
    )
