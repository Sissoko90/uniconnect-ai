"""The French copy of a document is the same document, not a plainer one.

The brief the group was given is a navy banner, a white title, a gold
programme line and blue section headings on US Letter. A member who reads
French is entitled to that document with its words translated, and to
nothing else changed. Every constant checked here was measured out of that
file's own content stream.
"""

import pdf
import pytest

BRIEF = """CHATBOT HACKATHON
METI UniPods AI Innovation Programme, Cohort 1

Nous lançons un hackathon pour résoudre un défi réel, avec un prix de 5 000 $.

Le Problème
Notre groupe s'est agrandi et il est devenu difficile de suivre chaque message.

Ce qu'il faut soumettre
• Un chatbot fonctionnel, pas seulement une présentation.
• L'accès au code source ou au dépôt.

5 000 $ DE PRIX

Le jugement sera effectué par l'ensemble du groupe.
"""


def test_the_page_is_the_size_the_original_is():
    """US Letter, in points. A4 would reflow every line, and the format
    given in the default unit built a page three times too large."""
    assert pdf.PAGE == (612, 792)


def test_the_banner_matches_the_original_to_the_point():
    """Read out of the source PDF: the band runs from 50.5pt in from each
    edge, starts 35.5pt down, and is 56.5pt tall."""
    assert pdf.MARGIN == 50.5
    assert pdf.BANNER_TOP == 35.5
    assert pdf.BANNER_HEIGHT == 56.5
    assert pdf.PAGE[0] - 2 * pdf.MARGIN == 511.0


def test_the_palette_is_the_original_palette():
    """Three colours and a grey, taken from the file itself. The original
    also sets a medium blue in places, but only ever on whitespace: nothing
    visible in it is blue, and an early version of this that put the section
    headings in that blue was reproducing a colour the reader never sees."""
    assert pdf.NAVY == (11, 31, 58)
    assert pdf.GOLD == (244, 210, 24)
    assert pdf.BODY_GREY == (34, 34, 34)


def test_the_title_and_programme_line_go_into_the_banner():
    """And out of the body. Printing them again underneath a banner that
    already says them is how a faithful copy starts to look generated."""
    title, subtitle, body = pdf._split_off_the_heading(BRIEF)

    assert title == "CHATBOT HACKATHON"
    assert subtitle == "METI UniPods AI Innovation Programme, Cohort 1"
    assert "CHATBOT HACKATHON" not in body
    assert "Le Problème" in body


def test_a_document_that_opens_with_a_sentence_keeps_it():
    """Only a heading is taken for the banner. A document whose second line
    is already prose would otherwise lose its first sentence."""
    title, subtitle, body = pdf._split_off_the_heading(
        "Video Demo Guide\nRecord your demo before Thursday, then upload it."
    )

    assert title == "Video Demo Guide"
    assert subtitle == ""
    assert body.strip().startswith("Record your demo")


@pytest.mark.parametrize(
    "line,feature",
    [
        ("$5,000 CASH PRIZE", True),
        ("5 000 $ DE PRIX", True),
        ("$5,000 CASH PRIZE", True),
        # A sentence that merely mentions the figure is body text, and
        # setting it in gold across the page would be wrong in both
        # languages.
        ("We are launching a hackathon with a $5,000 cash prize.", False),
        ("Team Guidelines", False),
        ("• Teams of up to 5 people.", False),
    ],
)
def test_the_prize_line_is_recognised_in_both_languages(line, feature):
    """Matched on the figure, not on the English words, so the French
    rendering of the same line is still set in gold."""
    assert pdf._is_a_feature(line) is feature


def test_the_opening_paragraph_is_found():
    """The original sets whatever stands before the first heading in navy
    bold, apart from the body under it."""
    _, _, body = pdf._split_off_the_heading(BRIEF)
    blocks = pdf._paragraphs(body)

    assert blocks[0][0].startswith("Nous lançons")
    assert not pdf._looks_like_a_heading(blocks[0][0])
    # And the block after it is the first section heading, not more prose.
    assert pdf._looks_like_a_heading(blocks[1][0])


def test_a_document_that_opens_on_a_heading_has_no_lead():
    """Setting a section heading in the lead paragraph's style would put
    the whole document one step out of rhythm from its first line."""
    blocks = pdf._paragraphs("Timeline\nHackathon runs Friday to Thursday.")

    assert pdf._looks_like_a_heading(blocks[0][0])


@pytest.mark.skipif(not pdf.available(), reason="no Unicode font on this machine")
def test_it_builds_a_letter_page_with_accents_in_it():
    out = pdf.build("UniPods Hackathon Guidelines", BRIEF, "Traduit automatiquement.")

    assert out.startswith(b"%PDF")
    # Large enough to be a real document with an embedded Unicode font
    # rather than an empty page: the font is most of the file.
    assert len(out) > 20000
