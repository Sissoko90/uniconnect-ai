"""What the bot can do, answered from what is switched on.

Asked in the group "can you view images and listen to audio messages?", the
bot answered that it works only from text and can neither. It has
transcribed every voice note in this group since the day it joined.

The mistake was structural, not a wrong fact. Every other question is
answered from the group's messages, which is the rule that keeps the bot
honest, and nobody has ever posted a message describing what the bot can
do. So it searched the history, found nothing about audio, and reported
that faithfully. It was answering a question about itself with evidence
about the group.

This is the one subject where the history is the wrong source. The answer
is read off the running system instead: a capability appears here only when
the key that powers it is actually configured, so a bot with no
transcription key does not claim to transcribe.
"""

import answer as answer_engine
import voice

# Short enough to read on a phone in one go. A bot that answers "what can
# you do" with twenty lines has answered a different question.
LINES = {
    "en": {
        "intro": "Here is what I can do:",
        "text": "Read every message in the group and answer from it, quoting "
                "the message I got it from.",
        "voice": "Listen to voice notes. Every one is transcribed when it "
                 "arrives, so what was said out loud is searchable like "
                 "anything else.",
        "images": "Read the caption on an image, but not the image itself. "
                  "I cannot see pictures.",
        "documents": "Send you a document the group shared, as a PDF, "
                     "translated into French or English.",
        "catchup": "Tell you what you missed while you were away, in private.",
        "timeline": "List the programme's dates, drawn from the group's own "
                    "messages.",
        "calls": "Summarise a call that has been transcribed: decisions, "
                 "action items, open questions.",
        "outro": "Ask me in private and the group sees nothing.",
    },
    "fr": {
        "intro": "Voici ce que je sais faire :",
        "text": "Lire chaque message du groupe et répondre à partir de là, en "
                "citant le message d'où vient la réponse.",
        "voice": "Écouter les notes vocales. Chacune est transcrite à son "
                 "arrivée, donc ce qui a été dit à l'oral se cherche comme "
                 "le reste.",
        "images": "Lire la légende d'une image, mais pas l'image elle-même. "
                  "Je ne vois pas les photos.",
        "documents": "T'envoyer un document partagé dans le groupe, en PDF, "
                     "traduit en français ou en anglais.",
        "catchup": "Te dire ce que tu as manqué pendant ton absence, en privé.",
        "timeline": "Donner les dates du programme, tirées des messages du "
                    "groupe.",
        "calls": "Résumer un appel qui a été transcrit : décisions, actions, "
                 "questions ouvertes.",
        "outro": "Pose-moi la question en privé et le groupe ne voit rien.",
    },
}


def describe(lang: str = "en") -> str:
    """The list, with only what is actually running on it."""
    said = LINES.get(lang, LINES["en"])

    # Order matters: the two people ask about are first.
    entries = [said["text"]]
    if voice.available():
        entries.append(said["voice"])
    entries.append(said["images"])
    if answer_engine.generation_available():
        entries.extend([said["documents"], said["catchup"], said["timeline"],
                        said["calls"]])

    body = "\n".join(f"- {line}" for line in entries)
    return f"{said['intro']}\n\n{body}\n\n{said['outro']}"
