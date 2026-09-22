"""Answering a question about an image somebody posted.

Asked in the group "can you view images and listen to audio messages?", the
honest answer was half no: voice notes have been transcribed since the first
day, images were read for their caption and nothing else.

The model can see. What was missing was the plumbing, and the reason it was
missing is that this system's unit of work is text. Search, citations, the
digest and the daily briefing are all built on messages, and a transcript
becomes a message while a photograph does not.

So this deliberately does not index anything. An image is looked at when
somebody asks about that image, and the answer is not stored as a message
the group said, because the group did not say it. One image, one question,
one call, and nothing left behind.

That also keeps the cost where it belongs. Describing every picture in a
busy group would pay for every meme and every screenshot on the chance that
one of them mattered later; this pays only for the ones somebody actually
asks about.
"""

import base64
import os

import answer as answer_engine
import limits

# What Anthropic accepts, and what WhatsApp actually sends. WhatsApp
# recompresses photographs to JPEG, so the first entry covers nearly
# everything; the rest are for forwarded files.
ACCEPTED = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Anthropic refuses an image above 5 MB. WhatsApp's own compression puts a
# photograph well under 1 MB, so this rejects a forwarded original rather
# than anything somebody took with a phone.
MAX_BYTES = int(os.environ.get("VISION_MAX_BYTES", str(5 * 1024 * 1024)))

SYSTEM = """You are UniConnect, answering a question about an image somebody \
posted in a WhatsApp group.

Answer from what is actually in the image. Read any text in it exactly as it \
is written: a date, a time, a room, a link, an amount. Those are what people \
photograph and those are what they are asking about.

Never guess at anything the image does not show. If it is blurred, cropped \
or too small to read, say which part you cannot make out rather than \
filling it in. A confident wrong date is worse here than anywhere else, \
because nobody will re-check a picture they have already seen.

If the question needs something outside the image, the group's history for \
instance, answer what the image gives you and say plainly what it does not.

Keep it to a few lines. This is read on a phone, under the picture.

Reply in the language of the question.

Never use a long dash, em or en. A comma, a full stop or a plain hyphen \
instead."""

CANNOT = {
    "en": {
        "type": "I can read a photo, but not this kind of file.",
        "size": "That image is too large for me to open. A screenshot of it "
                "would work.",
        "off": "I cannot look at images at the moment.",
    },
    "fr": {
        "type": "Je sais lire une photo, mais pas ce type de fichier.",
        "size": "Cette image est trop lourde pour moi. Une capture d'écran "
                "passerait.",
        "off": "Je ne peux pas regarder les images en ce moment.",
    },
}


def refusal(reason: str, lang: str) -> str:
    return CANNOT.get(lang, CANNOT["en"])[reason]


def look(pool, question: str, image: bytes, mime: str, lang: str) -> dict:
    """What the image says, for this question. One call, nothing stored."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime not in ACCEPTED:
        return {"error": "type"}
    if len(image) > MAX_BYTES:
        return {"error": "size"}
    if not answer_engine.generation_available() or limits.over_spend_cap(pool):
        return {"error": "off"}

    response = answer_engine.anthropic_client().messages.create(
        model=answer_engine.MODEL,
        # Room for the picture, the thinking and a few lines of answer. An
        # image costs around 1500 tokens of input and nothing of this
        # budget, which is shared with the thinking.
        max_tokens=4000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        # Reading a date off a poster is not hard. The effort that matters
        # here is the model looking carefully rather than reasoning long.
        output_config={"effort": "low"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": base64.b64encode(image).decode(),
                        },
                    },
                    {"type": "text", "text": question},
                ],
            }
        ],
    )
    limits.record_usage(pool, "vision", None, getattr(response, "usage", None))

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        return {"error": "off"}
    return {"answer": answer_engine.safe_to_send(text)}
