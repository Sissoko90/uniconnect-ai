"""The parser is the one component that touches the group's real history.

A bug here is silent: messages land with the wrong date, or the wrong author,
and nobody notices until an answer cites something absurd. These tests exist
because two of these cases were real bugs, not hypotheticals.
"""

import parse_whatsapp as p

IOS = """[15/09/2026, 09:12:03] Messages and calls are end-to-end encrypted.
[15/09/2026, 09:14:21] Steven: Bonjour, le call est à 18h
[15/09/2026, 10:04:00] ~ Makan: The contract is frozen
and takes three fields
[15/09/2026, 10:06:11] Liza: <Media omitted>
"""

ANDROID_US = """9/8/26, 3:49 PM - Messages and calls are end-to-end encrypted.
9/8/26, 3:49 PM - You were added
9/15/26, 10:04 AM - Steven: month-first export
9/18/26, 11:00 PM - Makan: still month-first
"""

ANDROID_EU = """18/09/2026, 22:00 - Steven: day-first export
15/09/2026, 10:04 - Makan: second message
"""


def parse(tmp_path, text, name="chat.txt", tz="UTC"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return p.parse(str(path), tz)


def test_ios_format(tmp_path):
    messages = parse(tmp_path, IOS)

    # The encryption notice and the media placeholder are not things a person
    # said, and citing them would be nonsense.
    assert [m["author"] for m in messages] == ["Steven", "Makan"]


def test_multiline_message_is_kept_whole(tmp_path):
    messages = parse(tmp_path, IOS)

    # A pasted agenda or code block loses its meaning if split into one
    # message per line.
    assert messages[1]["content"] == "The contract is frozen\nand takes three fields"


def test_tilde_is_stripped_from_author(tmp_path):
    """WhatsApp marks non-contacts with "~". Left in place, "~ Makan" and
    "Makan" become two different people."""
    messages = parse(tmp_path, IOS)

    assert messages[1]["author"] == "Makan"


def test_month_first_export_is_detected(tmp_path):
    """Our own METI export is month-first: it contains 9/18/26.

    Reading it as day-first would place the whole history in the wrong
    months and break every "since Tuesday" question.
    """
    messages = parse(tmp_path, ANDROID_US)

    assert messages[0]["said_at"].month == 9
    assert messages[0]["said_at"].day == 15
    assert messages[1]["said_at"].day == 18


def test_day_first_export_is_detected(tmp_path):
    messages = parse(tmp_path, ANDROID_EU)

    assert messages[0]["said_at"].day == 18
    assert messages[0]["said_at"].month == 9


def test_am_pm_is_applied(tmp_path):
    messages = parse(tmp_path, ANDROID_US)

    assert messages[0]["said_at"].hour == 10   # 10:04 AM
    assert messages[1]["said_at"].hour == 23   # 11:00 PM


def test_timezone_is_converted_to_utc(tmp_path):
    """Timestamps are stored in UTC so a call in Kigali and a chat in Bamako
    sit on the same timeline."""
    kigali = parse(tmp_path, ANDROID_EU, tz="Africa/Kigali")  # UTC+2
    utc = parse(tmp_path, ANDROID_EU, tz="UTC")

    assert kigali[0]["said_at"].hour == 20
    assert utc[0]["said_at"].hour == 22


def test_ambiguous_dates_warn_but_do_not_crash(tmp_path, capsys):
    """Every day under the 13th: the file cannot tell us its own format."""
    messages = parse(tmp_path, "5/6/26, 10:00 - Steven: ambiguous\n")

    assert len(messages) == 1
    assert "day/month order" in capsys.readouterr().err


def test_inconsistent_dates_are_refused(tmp_path):
    """Both fields above 12 means the file is not what we think it is.
    Guessing here would corrupt the whole history."""
    import pytest

    with pytest.raises(SystemExit):
        parse(tmp_path, "13/14/26, 10:00 - Steven: impossible\n")


def test_the_conversation_with_the_bot_is_not_group_content(tmp_path):
    """Found in a private chat the morning after launch: "what is the
    submission deadline?" was answered with 'According to Is any of it real:
    "@ask give me a summary"'.

    An export made after the bot went live contains both sides of every
    exchange with it. A question put to the bot is a command and its reply is
    something the bot already said, so indexing either turns one person's
    question into the source for the next person's.
    """
    export = (
        "[19/09/2026, 09:32:08] Steven: @ask give me a summary\n"
        "[19/09/2026, 09:32:11] ~Uniconnect-IA: According to Makan: the call is at 18h\n"
        "[19/09/2026, 09:33:00] Steven: @Ask what is the deadline\n"
        "[19/09/2026, 09:34:00] Makan: the deadline is Thursday\n"
    )

    messages = parse(tmp_path, export)

    assert [m["content"] for m in messages] == ["the deadline is Thursday"]


def test_language_detection():
    assert p.detect_lang("Bonjour, je cherche le lien du call") == "fr"
    assert p.detect_lang("Where is the recording") == "en"
