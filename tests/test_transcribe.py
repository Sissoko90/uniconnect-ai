"""Whisper emits a segment every few seconds. "Yeah, exactly." is not a
citable answer, so segments are merged into paragraph-sized blocks before
they reach the database."""

import transcribe


def segments(*pairs):
    return [{"start": start, "text": text} for start, text in pairs]


def test_short_segments_are_merged():
    blocks = transcribe.to_blocks(
        segments(
            (0.0, "Let's start with the deadline."),
            (4.2, "Yeah."),
            (6.0, "We agreed Sunday for the first version."),
        )
    )

    assert len(blocks) == 1
    assert "Yeah." in blocks[0]["text"]


def test_a_block_closes_after_the_time_limit():
    blocks = transcribe.to_blocks(
        segments((0.0, "first"), (10.0, "still first"), (transcribe.BLOCK_SECONDS + 1.0, "second"))
    )

    assert [b["start"] for b in blocks] == [0.0, transcribe.BLOCK_SECONDS + 1.0]


def test_a_long_monologue_is_split():
    """Without a character limit, one uninterrupted speaker would produce a
    single block too long to embed usefully."""
    blocks = transcribe.to_blocks(segments(*[(i * 2.0, "x" * 100) for i in range(12)]))

    assert len(blocks) > 1
    assert all(len(b["text"]) <= transcribe.BLOCK_CHARS + 100 for b in blocks)


def test_block_start_is_the_first_segment_start():
    """The block's timestamp places it on the group's timeline, so it has to
    be when the passage started, not when it ended."""
    blocks = transcribe.to_blocks(segments((12.5, "a"), (14.0, "b")))

    assert blocks[0]["start"] == 12.5
