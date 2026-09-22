"""Turn a document's text into a PDF the group can open on a phone.

Built on the server and sent through WhatsApp as a file, not as a link:
asked for the hackathon guidelines in French, people want the document, and
a link is one more thing to tap on a phone with a bad connection.

fpdf2 rather than anything that renders HTML: no system libraries, no
headless browser, and the output is the same on the server as it is
nowhere else. The one thing it needs is a Unicode font, because the whole
point of this is French and the built-in fonts cannot write "é".
"""

import os
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# DejaVu ships with fonts-dejavu-core, installed in the API image. Listed
# in fallback order so the module still works on a laptop that has neither.
FONT_CANDIDATES = (
    os.environ.get("PDF_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)

BOLD_CANDIDATES = (
    os.environ.get("PDF_FONT_BOLD", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
)


def _first_that_exists(paths) -> str | None:
    return next((p for p in paths if p and os.path.exists(p)), None)


def available() -> bool:
    """False when no Unicode font is installed, which makes French unusable."""
    return _first_that_exists(FONT_CANDIDATES) is not None


def _looks_like_a_heading(line: str) -> bool:
    """A short line with no sentence punctuation, the way the parser reads one."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or stripped[0] in "-*•":
        return False
    return not stripped.endswith((".", "!", "?", ":", ",", ";"))


def build(title: str, text: str, footer: str = "") -> bytes:
    """The document as PDF bytes.

    Deliberately plain. This is a programme document being made readable in
    another language, not a designed artefact, and anything clever here is
    something that can render differently on somebody's phone.
    """
    regular = _first_that_exists(FONT_CANDIDATES)
    if not regular:
        raise RuntimeError(
            "No Unicode font found. Install fonts-dejavu-core, or set PDF_FONT "
            "to a .ttf: the built-in fonts cannot write an accented character, "
            "which is the entire point of this."
        )

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("body", "", regular)

    bold = _first_that_exists(BOLD_CANDIDATES)
    pdf.add_font("body", "B", bold or regular)

    pdf.add_page()
    pdf.set_font("body", "B", 16)
    pdf.multi_cell(0, 9, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    for block in text.split("\n"):
        line = block.rstrip()
        if not line:
            pdf.ln(3)
            continue
        if _looks_like_a_heading(line):
            pdf.ln(2)
            pdf.set_font("body", "B", 12)
        else:
            pdf.set_font("body", "", 11)
        # Width 0 means "to the right margin", which is what wraps a long
        # line instead of running it off the page. The cursor has to be
        # sent back to the left margin each time, or the next cell starts
        # where the last one ended and has no width left to render into.
        pdf.multi_cell(0, 6, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if footer:
        pdf.ln(6)
        pdf.set_font("body", "", 9)
        pdf.multi_cell(0, 5, footer, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()
