"""Turn a document's text into a PDF the group can open on a phone.

Built on the server and sent through WhatsApp as a file, not as a link:
asked for the hackathon guidelines in French, people want the document, and
a link is one more thing to tap on a phone with a bad connection.

It carries the original document's design rather than inventing one. The
brief the group was given is a navy banner, a white title, a gold programme
line, navy serif headings and a gold panel around the prize, on US Letter.
A member who reads French is entitled to that document with its words
translated and nothing else changed.

Every measurement below was read out of that file's own content stream, at
the three quarter scale it draws at, and is written here as the result. The
palette, the banner, the margins, the type sizes and the leading are the
original's. What the translation changes is the words.

fpdf2 rather than anything that renders HTML: no system libraries, no
headless browser, and the output is the same on the server as it is
nowhere else. The one thing it needs is a Unicode font, because the whole
point of this is French and the built-in fonts cannot write "é".
"""

import os
import re
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

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

# The original sets its section headings in a serif face. DejaVu Serif ships
# in the same package as the sans, so this costs nothing; where it is
# missing the headings fall back to bold sans, which is a small loss of
# character and no loss of meaning.
SERIF_CANDIDATES = (
    os.environ.get("PDF_FONT_SERIF", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
)

# --------------------------------------------------------------------------
# The original document's design
# --------------------------------------------------------------------------

# US Letter, which is what the original is. A4 would reflow every line and
# move the banner.
PAGE = (612, 792)

NAVY = (11, 31, 58)          # the banner, the lead paragraph, the headings
GOLD = (244, 210, 24)        # the programme line, and the panel round the prize
BODY_GREY = (34, 34, 34)
WHITE = (255, 255, 255)

MARGIN = 50.5                # where the banner starts, and where the text does
BANNER_TOP = 35.5
BANNER_HEIGHT = 56.5

# Where the body begins, measured from the top of the page. Not derived from
# the banner: the original leaves a deliberate gap under it.
BODY_TOP = 120

TITLE_SIZE = 17
SUBTITLE_SIZE = 10
LEAD_SIZE = 10.5             # the opening paragraph, set apart in navy bold
HEADING_SIZE = 11
BODY_SIZE = 10
PRIZE_SIZE = 13
CAPTION_SIZE = 9.5
FOOTNOTE_SIZE = 8

# Baseline to baseline, as a multiple of the type size. The original's body
# runs 13.5pt on 9.9pt type.
LEADING = 1.36

SPACE_BEFORE_HEADING = 16
SPACE_AFTER_HEADING = 4
BULLET_INDENT = 10           # the original indents a bullet by this much

PRIZE_PANEL_PADDING = 9

BULLETS = "-*•"


def _first_that_exists(paths) -> str | None:
    return next((p for p in paths if p and os.path.exists(p)), None)


def available() -> bool:
    """False when no Unicode font is installed, which makes French unusable."""
    return _first_that_exists(FONT_CANDIDATES) is not None


def fonts() -> dict:
    """Which of the three faces this machine actually has.

    Worth being able to ask. Only the regular one is required; without the
    bold the banner and the headings lose their weight, and without the
    serif the headings fall back to bold sans. Both degrade quietly, which
    is the kind of difference that is otherwise noticed by the group and not
    by us.
    """
    return {
        "regular": _first_that_exists(FONT_CANDIDATES),
        "bold": _first_that_exists(BOLD_CANDIDATES),
        "serif": _first_that_exists(SERIF_CANDIDATES),
    }


def _looks_like_a_heading(line: str) -> bool:
    """A short line with no sentence punctuation, the way the parser reads one."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or stripped[0] in BULLETS:
        return False
    return not stripped.endswith((".", "!", "?", ":", ",", ";"))


def _is_a_bullet(line: str) -> bool:
    return line.lstrip()[:1] in BULLETS


# The line the original sets in navy on a gold panel: the prize.
#
# Matched on the figure rather than on the English words, because that is
# exactly what the translation changes about it: English writes "$5,000 CASH
# PRIZE" and French writes "5 000 $ DE PRIX EN ESPÈCES". Only at the start of
# a short line, so a sentence that merely mentions the prize stays body text
# in either language.
FEATURE_LINE = re.compile(r"^\s*(?:[$€£]\s?[\d][\d,. ]*|[\d][\d,. ]*\s?[$€£])\s*\S")


def _is_a_feature(line: str) -> bool:
    return bool(FEATURE_LINE.match(line)) and len(line.strip()) <= 40


class _Document(FPDF):
    """The page furniture, so every page of a long document matches.

    The banner is drawn by the header hook rather than once at the top,
    because a translated document runs longer than its original, French
    being around fifteen per cent longer than English, and a second page
    with no banner would look like a different document.
    """

    title_text = ""
    subtitle_text = ""

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(MARGIN, BANNER_TOP, PAGE[0] - 2 * MARGIN, BANNER_HEIGHT, style="F")

        self.set_y(BANNER_TOP + 10)
        self.set_font("body", "B", TITLE_SIZE)
        self.set_text_color(*WHITE)
        self.cell(0, TITLE_SIZE, self.title_text, align=Align.C,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if self.subtitle_text:
            self.set_font("body", "B", SUBTITLE_SIZE)
            self.set_text_color(*GOLD)
            self.cell(0, SUBTITLE_SIZE * LEADING, self.subtitle_text, align=Align.C,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Clear of the banner before anything else is written. Without it the
        # first paragraph starts inside the navy and is invisible.
        self.set_y(BODY_TOP)
        self.set_text_color(*BODY_GREY)


def _split_off_the_heading(text: str) -> tuple[str, str, str]:
    """The title and programme line the banner carries, and the rest.

    The document's own first two lines, when they are headings, because
    repeating them in the body under a banner that already says them is how
    a faithful copy starts to look like a generated one.
    """
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return "", "", text

    title = lines[first].strip()
    rest = first + 1

    subtitle = ""
    following = next((i for i in range(rest, len(lines)) if lines[i].strip()), None)
    if following is not None and _looks_like_a_heading(lines[following]):
        subtitle = lines[following].strip()
        rest = following + 1

    return title, subtitle, "\n".join(lines[rest:])


def _paragraphs(body: str) -> list[list[str]]:
    """The body as blocks of lines, blank lines dropped.

    Grouped rather than walked line by line, because two of the original's
    features need to see more than one line at a time: the opening paragraph
    is whatever comes before the first heading, and the prize panel holds
    the prize and the sentence under it.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in body.split("\n"):
        line = raw.rstrip()
        if line:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def build(title: str, text: str, footer: str = "") -> bytes:
    """The document as PDF bytes, in the original's colours and proportions."""
    regular = _first_that_exists(FONT_CANDIDATES)
    if not regular:
        raise RuntimeError(
            "No Unicode font found. Install fonts-dejavu-core, or set PDF_FONT "
            "to a .ttf: the built-in fonts cannot write an accented character, "
            "which is the entire point of this."
        )
    bold = _first_that_exists(BOLD_CANDIDATES) or regular
    serif = _first_that_exists(SERIF_CANDIDATES) or bold

    own_title, subtitle, body = _split_off_the_heading(text)

    # Points, not the default millimetres. Every measurement above was read
    # out of the original PDF and is therefore in points; left in
    # millimetres, fpdf built a page 1734 by 2245, which is US Letter
    # measured in the wrong unit and three times too large.
    pdf = _Document(unit="pt", format=PAGE)
    pdf.title_text = own_title or title
    pdf.subtitle_text = subtitle
    pdf.set_margins(MARGIN, BANNER_TOP, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=45)
    pdf.add_font("body", "", regular)
    pdf.add_font("body", "B", bold)
    pdf.add_font("heading", "", serif)

    pdf.add_page()

    width = PAGE[0] - 2 * MARGIN
    blocks = _paragraphs(body)
    # The opening paragraph is whatever stands before the first heading. The
    # original sets it in navy bold, apart from the body that follows.
    lead = 0 if blocks and not _looks_like_a_heading(blocks[0][0]) else -1

    skip = -1
    for index, block in enumerate(blocks):
        if index == skip:
            continue

        if index == lead:
            pdf.set_font("body", "B", LEAD_SIZE)
            pdf.set_text_color(*NAVY)
            pdf.multi_cell(width, LEAD_SIZE * LEADING, " ".join(block),
                           align=Align.L, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(SPACE_BEFORE_HEADING)
            continue

        if _is_a_feature(block[0]):
            # The prize, and the sentence under it, inside one gold panel.
            # The caption is the next block when the prize stands alone,
            # which is how it reads once a translator has reflowed it.
            caption = " ".join(block[1:])
            if not caption and index + 1 < len(blocks):
                caption = " ".join(blocks[index + 1])
                skip = index + 1
            _prize_panel(pdf, block[0].strip(), caption, width)
            continue

        for line in block:
            if _looks_like_a_heading(line):
                pdf.ln(SPACE_BEFORE_HEADING)
                pdf.set_font("heading", "", HEADING_SIZE)
                pdf.set_text_color(*NAVY)
                pdf.multi_cell(width, HEADING_SIZE * LEADING, line.strip(),
                               align=Align.L, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(SPACE_AFTER_HEADING)
                continue

            pdf.set_font("body", "", BODY_SIZE)
            pdf.set_text_color(*BODY_GREY)
            if _is_a_bullet(line):
                # Indented as a block, wrapped lines included, which is what
                # the original does: its second line of a long bullet starts
                # under the bullet and not under the text.
                pdf.set_x(MARGIN + BULLET_INDENT)
                pdf.multi_cell(width - BULLET_INDENT, BODY_SIZE * LEADING,
                               "• " + line.lstrip()[1:].strip(),
                               align=Align.L, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.multi_cell(width, BODY_SIZE * LEADING, line,
                               align=Align.L, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(BODY_SIZE * 0.6)

    if footer:
        pdf.ln(10)
        pdf.set_font("body", "", FOOTNOTE_SIZE)
        # Grey and small, at the end, where a note about the document
        # belongs. It is ours and not the programme's, and it must not read
        # as though it were part of what was announced.
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(width, FOOTNOTE_SIZE * LEADING, footer,
                       align=Align.L, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


def _prize_panel(pdf: FPDF, headline: str, caption: str, width: float) -> None:
    """The gold panel the original puts around the prize.

    Drawn as a filled rectangle with the text placed on it, rather than as
    filled cells, so the panel is one block of colour with no seam between
    its two lines.
    """
    pdf.ln(SPACE_BEFORE_HEADING)

    line_height = PRIZE_SIZE * LEADING
    caption_height = CAPTION_SIZE * LEADING if caption else 0
    height = PRIZE_PANEL_PADDING * 2 + line_height + caption_height

    # Keep the panel whole. Split across two pages it reads as a design
    # accident rather than as the one thing on the page meant to be seen.
    if pdf.get_y() + height > PAGE[1] - 45:
        pdf.add_page()

    top = pdf.get_y()
    pdf.set_fill_color(*GOLD)
    pdf.rect(MARGIN, top, width, height, style="F")

    pdf.set_y(top + PRIZE_PANEL_PADDING)
    pdf.set_font("body", "B", PRIZE_SIZE)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, line_height, headline, align=Align.C,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if caption:
        pdf.set_font("body", "", CAPTION_SIZE)
        pdf.cell(0, caption_height, caption, align=Align.C,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(top + height)
    pdf.ln(SPACE_BEFORE_HEADING)
