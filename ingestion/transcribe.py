"""Turn a call recording into searchable, citable messages.

    export DATABASE_URL=... GROQ_API_KEY=...
    python transcribe.py call.mp4 --group-id meti-cohort-1 \
        --title "Weekly call, 22 Sept" --occurred-at 2026-09-22T18:00:00Z

Transcript segments land in the same utterances table as chat messages, on
purpose: one search then covers what was said in a call and what was typed in
the chat, and an answer can cite either without knowing the difference.

Whisper gives us no speaker labels, so a segment is attributed to the call
itself ("Weekly call, 22 Sept"), never guessed at a person. Citing the wrong
member would be worse than citing none.
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = os.environ.get("WHISPER_MODEL", "whisper-large-v3-turbo")

# Groq rejects uploads past 25 MB. We aim well under it, because the limit is
# on the encoded file and our estimate of the encoded size is approximate.
MAX_UPLOAD_MB = 20

# One chunk of audio per request when a recording is too big. Ten minutes of
# 16 kHz mono FLAC is roughly 10 MB, comfortably inside the limit.
CHUNK_SECONDS = 600

# Whisper emits a segment every few seconds, which is far too short to be a
# useful unit of retrieval - "yes, exactly" is not a citable answer. Segments
# are merged up to roughly this long, which reads like a paragraph and gives
# the embedding enough to work with.
BLOCK_SECONDS = 45
BLOCK_CHARS = 700


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def to_audio(path: str, workdir: str) -> str:
    """Normalise anything (mp4, m4a, ogg, wav) to 16 kHz mono FLAC.

    Whisper downsamples to 16 kHz anyway, so sending anything richer is
    upload time we pay for nothing. A one-hour call drops from hundreds of
    megabytes of video to a few tens of megabytes of audio.
    """
    out = os.path.join(workdir, "audio.flac")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", path,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", out],
        check=True,
    )
    return out


def split(path: str, workdir: str, seconds: int = CHUNK_SECONDS) -> list[tuple[str, float]]:
    """Cut into chunks. Returns (file, offset in seconds from the start)."""
    size_mb = os.path.getsize(path) / 1_000_000
    if size_mb <= MAX_UPLOAD_MB:
        return [(path, 0.0)]

    pattern = os.path.join(workdir, "chunk%03d.flac")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", path,
         "-f", "segment", "-segment_time", str(seconds), "-c", "copy", pattern],
        check=True,
    )
    files = sorted(f for f in os.listdir(workdir) if f.startswith("chunk"))
    print(f"  {size_mb:.0f} MB, split into {len(files)} chunks")
    # Offsets are computed rather than measured: -segment_time cuts on the
    # nearest frame boundary, so a chunk can be a fraction off. Over a call
    # that is well under the precision a citation needs.
    return [(os.path.join(workdir, f), i * float(seconds)) for i, f in enumerate(files)]


def transcribe_chunk(path: str, offset: float, api_key: str) -> list[dict]:
    import requests

    with open(path, "rb") as fh:
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(path), fh, "audio/flac")},
            data={
                "model": MODEL,
                # verbose_json is what carries the timestamps. Without them a
                # transcript cannot be placed on the group's timeline and the
                # catch-up feature cannot see it.
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            },
            timeout=600,
        )
    response.raise_for_status()

    segments = response.json().get("segments", [])
    return [
        {"start": float(s["start"]) + offset, "text": s["text"].strip()}
        for s in segments
        if s.get("text", "").strip()
    ]


def to_blocks(segments: list[dict]) -> list[dict]:
    """Merge short Whisper segments into paragraph-sized, citable blocks."""
    blocks: list[dict] = []
    for seg in segments:
        if (
            blocks
            and seg["start"] - blocks[-1]["start"] < BLOCK_SECONDS
            and len(blocks[-1]["text"]) + len(seg["text"]) < BLOCK_CHARS
        ):
            blocks[-1]["text"] += " " + seg["text"]
        else:
            blocks.append({"start": seg["start"], "text": seg["text"]})
    return blocks


def load(blocks: list[dict], group_id: str, title: str, occurred_at: datetime, dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Unlike a chat export, every call is its own source: two calls
            # are two different events, not two exports of the same thread.
            cur.execute(
                """insert into sources (kind, platform, group_id, title, occurred_at)
                   values ('call', %s, %s, %s, %s) returning id""",
                ("recording", group_id, title, occurred_at),
            )
            source_id = cur.fetchone()[0]

            cur.executemany(
                """insert into utterances (source_id, author, content, said_at)
                   values (%s, %s, %s, %s)
                   on conflict (source_id, author, said_at, md5(content)) do nothing""",
                [
                    (
                        source_id,
                        title,  # no diarisation: the call is the speaker
                        b["text"],
                        occurred_at + timedelta(seconds=math.floor(b["start"])),
                    )
                    for b in blocks
                ],
            )
            written = cur.rowcount
        conn.commit()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="audio or video recording")
    ap.add_argument("--group-id", required=True)
    ap.add_argument("--title", required=True, help='e.g. "Weekly call, 22 Sept"')
    ap.add_argument("--occurred-at", help="ISO 8601; defaults to the file's timestamp")
    ap.add_argument("--dry-run", action="store_true", help="transcribe, print, write nothing")
    args = ap.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY is not set.", file=sys.stderr)
        return 1
    if not have_ffmpeg():
        print("ffmpeg is not installed: apt install ffmpeg", file=sys.stderr)
        return 1

    if args.occurred_at:
        occurred_at = datetime.fromisoformat(args.occurred_at.replace("Z", "+00:00"))
    else:
        # Better than now(): a recording processed on Wednesday still belongs
        # on the timeline at the hour the call actually happened.
        occurred_at = datetime.fromtimestamp(os.path.getmtime(args.file), tz=UTC)
        print(
            "No --occurred-at given, using the file's timestamp: "
            f"{occurred_at:%Y-%m-%d %H:%M} UTC"
        )

    with tempfile.TemporaryDirectory() as workdir:
        print("Converting to 16 kHz mono audio...")
        audio = to_audio(args.file, workdir)

        segments: list[dict] = []
        for chunk, offset in split(audio, workdir):
            print(f"  transcribing from {int(offset)//60:02d}:{int(offset)%60:02d}...", flush=True)
            segments.extend(transcribe_chunk(chunk, offset, api_key))

    blocks = to_blocks(segments)
    if not blocks:
        print("Nothing was transcribed. Is there speech on this recording?", file=sys.stderr)
        return 1

    minutes = blocks[-1]["start"] / 60
    print(f"{len(segments)} segments merged into {len(blocks)} blocks, {minutes:.0f} minutes")

    if args.dry_run:
        for b in blocks[:3]:
            stamp = occurred_at + timedelta(seconds=math.floor(b["start"]))
            print(f"  {stamp:%H:%M:%S}  {b['text'][:90]}")
        return 0

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    written = load(blocks, args.group_id, args.title, occurred_at, dsn)
    print(f"{written} blocks written. Run embed.py to make them searchable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
