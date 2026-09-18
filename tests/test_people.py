"""Names are what turn a citation from "+229 90 00 00 42 said" into
"Awa said". Getting them wrong attributes somebody's words to someone else,
which is worse than printing a number.
"""

import people

# Exactly how WhatsApp writes it: the cards run together with no newline
# between END:VCARD and the next BEGIN:VCARD.
WHATSAPP_VCF = """BEGIN:VCARD
VERSION:3.0
N:;Ada Mensah;;;
FN:Ada Mensah
TEL;type=Mobile;waid=256700000001:+256 70 000 001
END:VCARDBEGIN:VCARD
VERSION:3.0
N:;Bruno Okafor;;;
FN:Bruno Okafor
TEL;type=Mobile;waid=256700000002:+256 70 000 002
END:VCARDBEGIN:VCARD
VERSION:3.0
FN:Chidi Eze
TEL;type=Mobile;waid=256700000003:+256 70 000 003
TEL;type=Mobile;waid=256700000004:+256 70 000 004
END:VCARD"""


def test_run_together_cards_keep_their_own_names(tmp_path):
    """Regression: a line-by-line reader never sees a card boundary here, and
    silently gives every number in the file the last contact's name."""
    path = tmp_path / "contacts.vcf"
    path.write_text(WHATSAPP_VCF, encoding="utf-8")

    pairs = dict(people.parse_vcards(str(path)))

    assert pairs["+256 70 000 001"] == "Ada Mensah"
    assert pairs["+256 70 000 002"] == "Bruno Okafor"


def test_one_person_can_have_several_numbers(tmp_path):
    path = tmp_path / "contacts.vcf"
    path.write_text(WHATSAPP_VCF, encoding="utf-8")

    pairs = people.parse_vcards(str(path))

    same_person = [handle for handle, name in pairs if name == "Chidi Eze"]
    assert len(same_person) == 2


def test_csv_skips_comments_and_blanks(tmp_path):
    path = tmp_path / "names.csv"
    path.write_text(
        "# handle,name\n+223 70 00 00 00,Makan\n\n+250 70 00 00 55,Steven\n",
        encoding="utf-8",
    )

    pairs = people.parse_csv(str(path))

    assert pairs == [("+223 70 00 00 00", "Makan"), ("+250 70 00 00 55", "Steven")]
