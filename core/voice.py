"""Voice notes, transcribed and made searchable.

In this group a large share of what gets said is said out loud. A voice note
is the most invisible thing on WhatsApp: you cannot search it, you cannot
skim it, and if you do not listen within the hour it is gone. People re-ask
questions that were answered in a three-minute recording nobody replayed.

So the worker sends us the audio and we turn it into an ordinary message.
From then on it is searched, cited and summarised like anything else - the
answer does not care that it was spoken.

One difference from a call recording: we know exactly who sent a voice note,
so unlike a transcript block it is attributed to its author by name. That is
the whole reason this is worth more than call transcription.

The Groq call is duplicated from ingestion/transcribe.py rather than shared:
the two run in different containers with no common parent, and thirty lines
of duplication is cheaper than a package to install in both.
"""

import base64
import os
import tempfile

import ingest

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = os.environ.get("WHISPER_MODEL", "whisper-large-v3-turbo")

# WhatsApp voice notes are ogg/opus and small - a ten minute one is about
# 2 MB. The cap is here to refuse a forwarded film, not a long ramble.
MAX_BYTES = 25_000_000

# Whisper transcribes silence as whatever it feels like; below this there is
# nothing worth indexing and we would be storing an invention.
MIN_CHARS = 8

EXTENSIONS = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
}


def available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def transcribe(audio: bytes, mime_type: str) -> str:
    """The spoken words, or an empty string when there are none."""
    import requests

    extension = EXTENSIONS.get(mime_type, ".ogg")
    with tempfile.NamedTemporaryFile(suffix=extension) as fh:
        fh.write(audio)
        fh.flush()

        with open(fh.name, "rb") as upload:
            response = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                files={"file": (os.path.basename(fh.name), upload, mime_type)},
                # json, not verbose_json: a voice note is one utterance by one
                # person, so there is nothing to place on a timeline within it.
                data={"model": MODEL, "response_format": "json"},
                timeout=180,
            )

    response.raise_for_status()
    return (response.json().get("text") or "").strip()


def store_voice_note(
    pool,
    group_id: str,
    author: str,
    said_at,
    audio_b64: str,
    mime_type: str = "audio/ogg",
    author_name: str | None = None,
    permalink: str | None = None,
) -> dict:
    """Transcribe and store as an ordinary message. Idempotent by content."""
    if not available():
        return {"error": "no transcription key configured"}

    try:
        audio = base64.b64decode(audio_b64, validate=True)
    except Exception:  # noqa: BLE001
        return {"error": "audio is not valid base64"}

    if len(audio) > MAX_BYTES:
        return {"error": f"audio is larger than {MAX_BYTES // 1_000_000} MB"}

    text = transcribe(audio, mime_type)

    if len(text) < MIN_CHARS:
        # Nothing was said, or nothing intelligible. Storing Whisper's guess
        # at silence would put words in somebody's mouth, which is the one
        # thing this system must never do.
        return {"stored": 0, "transcript": text, "empty": True}

    result = ingest.store(
        pool,
        group_id,
        [
            {
                "author": author,
                "author_name": author_name,
                # Marked as spoken so a reader of the citation knows why the
                # wording is loose - transcripts are not written sentences.
                "content": f"[voice note] {text}",
                "said_at": said_at,
                "permalink": permalink,
                "lang": None,
            }
        ],
    )
    return {"stored": result["stored"], "transcript": text, "empty": False}
