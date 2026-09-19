"""How a document is cut into citable pieces.

The hackathon asks for a bot that makes sense of "calls, chats, and more". The
"and more" is the briefs and schedules that were shared once and scrolled
past, and a badly cut document answers worse than no document at all: too
coarse and every answer quotes three sections, too fine and a heading is
retrieved on its own.

These tests are the shape of a real brief pulled out of a PDF.
"""

import document
import pytest

BRIEF = """CHATBOT HACKATHON

The Problem

Our group has grown large, and it has become hard to keep up with every
message. Due to high chat traffic people miss messages and end up asking
questions that have already been addressed.

Timeline

- Hackathon runs: Friday 18 September to Thursday 24 September 2026.
"""


def test_a_heading_stays_with_what_it_introduces():
    """The failure this was written for. "The Problem" was being merged into
    the end of the chunk before it, so the section title was filed under the
    previous section and the words a searcher would use were in the wrong
    place."""
    chunks = document.to_chunks(BRIEF)

    problem = [c for c in chunks if "grown large" in c]
    assert len(problem) == 1
    assert problem[0].startswith("The Problem")

    timeline = [c for c in chunks if "18 September" in c]
    assert timeline[0].startswith("Timeline")


def test_a_chunk_can_be_quoted_whole():
    """With no model credit the bot quotes its best hit and truncates it. A
    chunk longer than that budget loses its last line, which in a brief is
    where the dates live."""
    for chunk in document.to_chunks(BRIEF):
        assert len(chunk) <= document.CHUNK_CHARS


def test_a_wall_of_text_is_still_split():
    """pdftotext often returns a whole page with no blank line anywhere.
    Without a sentence-level fallback the entire document becomes one chunk
    and every answer quotes all of it."""
    wall = " ".join(f"This is sentence number {i} of the document." for i in range(60))

    chunks = document.to_chunks(wall)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= document.CHUNK_CHARS
    # Nothing may be dropped on the way through.
    assert "sentence number 59" in " ".join(chunks)


def test_an_empty_document_yields_nothing():
    assert document.to_chunks("") == []
    assert document.to_chunks("\n\n   \n") == []


@pytest.mark.parametrize(
    "line, heading",
    [
        ("The Problem", True),
        ("What to Submit", True),
        ("- Teams of up to 5 people.", False),
        ("We are launching a hackathon to solve a real challenge.", False),
        # Long enough to be a sentence even without a full stop.
        ("A sentence that runs on well past the length any section title would", False),
    ],
)
def test_is_heading(line, heading):
    assert document.is_heading(line) is heading
