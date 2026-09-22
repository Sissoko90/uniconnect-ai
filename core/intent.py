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

# Invisible characters WhatsApp puts inside message text: bidirectional
# isolates and embeddings, zero width spaces, the byte order mark.
#
# Typing "@ask" makes WhatsApp treat it as a mention and wrap the word in
# U+2068 and U+2069, so what arrives is "@\u2068ask\u2069 what is ...". The
# trigger above does not match that, and neither would anything else looking
# for a word: the characters sit inside words, not around them.
#
# Stripped here as well as in the worker, because the web page and any other
# client can paste the same text, and because a question carrying them
# searches badly: "hackathon" with an isolate in the middle is not the token
# the index holds.
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

SUMMARY_PHRASES = (
    "summary", "summarise", "summarize", "sum up", "overview", "recap",
    "what's happening", "whats happening", "what is happening", "catch me up",
    "résumé", "resume", "resume-moi", "recapitulatif", "récapitulatif",
    # With the accent, which is how anybody typing French properly spells it.
    # Only the bare "recap" was listed, so "récap du jour" matched nothing.
    "récap",
    "quoi de neuf", "que se passe", "ce qui se passe",
    # Promised in USAGE.md and matched by nothing, so the documented way to
    # ask for a catch-up was answered as an ordinary question and found
    # nothing. The worker had its own list and the API did not share it.
    "what did i miss", "what have i missed", "update me", "bring me up",
    "j'ai raté", "j'ai rate", "ai-je raté", "rattrapage", "rattraper",
    # "What is new today" was asked in the group during another team's
    # testing day and matched nothing here, so it went to retrieval and
    # searched for messages on the subject of being new. The worker knew
    # these words and the API did not, again.
    "what's new", "whats new", "what is new", "anything new", "du nouveau",
    # "Describe everything you know about the programme", also asked that
    # day. Somebody asking what the bot knows is asking for the whole
    # picture, and COMPLETENESS then routes it to the overview.
    "everything you know", "all you know", "tout ce que tu sais",
)

# The group's schedule, drawn from the dates in its own messages. Same words
# the worker matches on, kept here so that every client gets it: it was in a
# private WhatsApp chat only, and neither the group nor the web page could
# reach a feature the usage guide lists without qualification.
TIMELINE_PHRASES = (
    "timeline", "schedule", "roadmap", "planning", "calendrier", "agenda",
    "les dates", "quelles dates", "prochaines dates", "echeancier",
    "échéancier",
)

# A summary *of something* is an ordinary question about that thing, and
# retrieval answers it better than a digest would: it cites the messages.
ABOUT_SOMETHING = (" about ", " on the ", " sur ", " de la ", " concernant ")

# Except when the something is the group itself. "Fais moi un résumé complet
# de toutes les discussions qui ont eu lieu sur le groupe" contains " sur "
# and was read as a question about a topic, so it went to retrieval, which
# looked for messages on the subject of "the group" and found none. The bot
# answered "je ne trouve rien dans l'historique du groupe", to a request to
# summarise the group history.
#
# Matched on whole words, because "surtout" contains "tout".
WHOLE_GROUP = frozenset(
    {
        "group", "groupe", "discussion", "discussions", "conversation",
        "conversations", "chat", "chats", "everything", "tout", "tous",
        "toute", "toutes",
    }
)


def strip_trigger(question: str) -> str:
    """Remove a leading @ask and any invisible marks, leaving the question."""
    question = INVISIBLE.sub("", question)
    stripped = TRIGGER.sub("", question).strip()
    return stripped or question


def wants_a_summary(question: str) -> bool:
    """A request for the whole picture rather than a question about a thing."""
    lowered = question.lower()
    if not any(phrase in lowered for phrase in SUMMARY_PHRASES):
        return False
    # Naming the group, the discussion or everything is still asking for the
    # whole picture, however the sentence is built around it.
    if set(re.findall(r"[\w']+", lowered)) & WHOLE_GROUP:
        return True
    return not any(marker in lowered for marker in ABOUT_SOMETHING)


# Asking for all of it, not for what changed.
#
# "Un résumé complet de tous les discussions sur le groupe car je comprends
# rien et tout est en désordre et trop de message juste fais moi un grand
# résumé que je puisse me situer" was answered with "nothing new since your
# last visit". True of the question the bot heard, useless for the one asked:
# a catch-up covers what one person has not read, and this person has read
# none of it and is not asking what changed.
COMPLETENESS = (
    "complet", "complète", "complete", "entier", "entière", "intégral",
    "general", "général", "globale", "global", "grand résumé", "grand resume",
    "tout ce qui", "tout ce que", "toutes les discussions",
    "tous les discussions", "toute la discussion", "depuis le début",
    "depuis le debut", "everything", "whole", "full", "all of it",
    "from the start", "from the beginning", "big picture", "me situer",
    "comprends rien", "comprend rien", "perdu", "lost",
)


# Words that are part of asking for a summary rather than part of what is
# being asked about. What is left after removing them is the caller's own
# subject, if they had one.
REQUEST_FILLER = frozenset(
    {
        "fais", "faire", "donne", "donner", "donnes", "peux", "pourrais",
        "veux", "voudrais", "moi", "me", "un", "une", "le", "la", "les",
        "des", "du", "de", "et", "que", "qui", "quoi", "est", "sur", "dans",
        "pour", "avec", "ce", "cette", "ces", "je", "tu", "il", "elle",
        "nous", "vous", "puisse", "situer", "stp", "svp", "merci", "please",
        "give", "get", "make", "want", "would", "could", "can", "the", "a",
        "an", "of", "on", "in", "for", "and", "that", "this", "about", "up",
        "some", "thanks", "hi", "hello", "bonjour", "salut",
    }
)


def asks_for_more(question: str) -> bool:
    """Does this request name a subject of its own, beyond "summarise"?

    "Résumé complet" asks for the standard thing and any recent copy answers
    it. "Le résumé complet et les liens du meet passé" asks for something
    extra, so it has to be written for them and must never be served from a
    copy made for somebody else.

    Biased towards saying yes. Treating a plain request as a specific one
    costs money and still answers correctly; the other way round answers a
    question the person never asked.
    """
    words = set(re.findall(r"[\w']+", question.lower()))
    for phrase in (*SUMMARY_PHRASES, *COMPLETENESS):
        words -= set(re.findall(r"[\w']+", phrase))
    return bool(words - REQUEST_FILLER - WHOLE_GROUP)


def wants_an_overview(question: str) -> bool:
    """The whole group explained, rather than what has changed.

    Checked before the catch-up and the digest, because somebody asking this
    gets nothing useful from either: a digest shows them one day out of
    months, and a catch-up shows them nothing at all once their bookmark is
    up to date, which is exactly what happened.
    """
    lowered = question.lower()
    if not any(phrase in lowered for phrase in SUMMARY_PHRASES):
        return False
    return any(marker in lowered for marker in COMPLETENESS)


# What happened on the call. Distinct from every other summary here, and it
# was reachable by nobody: the worker has no client for /recap, so the
# automatic call recap, feature three of the project's own list, existed as a
# curl command and nothing else.
#
# A call word is required. "recap" on its own is in SUMMARY_PHRASES and means
# the daily digest, which is what people mean nine times out of ten.
RECAP_PHRASES = (
    "recap", "récap", "compte rendu", "compte-rendu", "what happened",
    "qu'est-ce qui s'est dit", "ce qui s'est dit", "minutes",
)

CALL_WORDS = (
    "call", "appel", "réunion", "reunion", "meeting", "open hour",
    "session", "visio", "teams", "zoom",
)


def wants_a_call_recap(question: str) -> bool:
    """Decisions and action items from the last call that was transcribed."""
    lowered = question.lower()
    return any(p in lowered for p in RECAP_PHRASES) and any(
        w in lowered for w in CALL_WORDS
    )


# Asking for a document itself, rather than for something it says.
#
# "Send me the hackathon guidelines in French" is not a question about the
# rules, it is a request for the file. Half this group works in French and
# the guidelines reached it as an English PDF, which is the complaint its
# own history records.
DOCUMENT_WORDS = (
    "document", "documents", "pdf", "brief", "guidelines", "guideline",
    "règlement", "reglement", "fichier", "le guide", "the guide",
)

WANTS_THE_FILE = (
    "send", "give", "share", "download", "envoie", "envoyer", "donne",
    "partage", "télécharge", "telecharge", "version", "copy", "copie",
    "en pdf", "in pdf", "en français", "en francais", "in french",
    "in english", "en anglais", "traduit", "translated", "traduis",
)


def wants_a_document(question: str) -> bool:
    """A request for the file, not for a fact inside it.

    Both halves are required. "What do the guidelines say about teams" is a
    question, answered from the text with a citation; "send me the
    guidelines in French" is a request for the document.
    """
    lowered = question.lower()
    return any(w in lowered for w in DOCUMENT_WORDS) and any(
        w in lowered for w in WANTS_THE_FILE
    )


def document_language(question: str) -> str | None:
    """Which language they asked for, or None when they did not say."""
    lowered = question.lower()
    if any(w in lowered for w in ("français", "francais", "french", "fr)")):
        return "fr"
    if any(w in lowered for w in ("anglais", "english", "en)")):
        return "en"
    return None


def wants_the_timeline(question: str) -> bool:
    """A request for the group's dates rather than a question about one.

    Checked before the summary, because "planning" and "agenda" are the words
    people reach for when they want the list of dates, and a digest of the
    last day is not that.
    """
    lowered = question.lower()
    if not any(phrase in lowered for phrase in TIMELINE_PHRASES):
        return False
    # "what is on the agenda for the call about visas" is a question about the
    # call, and retrieval answers it with the message it came from.
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
