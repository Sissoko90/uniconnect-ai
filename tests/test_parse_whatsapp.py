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


def test_directional_isolates_around_a_mention_are_stripped(tmp_path):
    """WhatsApp treats "@ask" as a mention and writes it wrapped in U+2068
    and U+2069. The export then carries a word nothing matches: not the bot
    filter below, and not the search index either."""
    export = (
        "[19/09/2026, 09:32:08] Steven: @\u2068ask\u2069 what is the deadline\n"
        "[19/09/2026, 09:34:00] Makan: the \u2068deadline\u2069 is Thursday\n"
    )

    messages = parse(tmp_path, export)

    # The first is a question put to the bot and is dropped, which only works
    # once the isolates are gone.
    assert [m["content"] for m in messages] == ["the deadline is Thursday"]


def test_french_system_notices_are_not_group_content(tmp_path):
    """WhatsApp writes its own notices in the language of the phone that
    exported the chat, and only the English wording was listed. A French
    export filed seven of them as things the group had said, attributed to
    the group's own name, including one that recites the encryption notice
    and one that lists the phone numbers of people somebody added."""
    export = (
        "[04/09/2026, 08:27:00] UniPods METI: Les messages et les appels sont "
        "chiffrés de bout en bout.\n"
        "[04/09/2026, 10:45:00] UniPods METI: Vous avez utilisé un lien pour "
        "rejoindre le groupe\n"
        "[05/09/2026, 09:00:00] UniPods METI: ~ Diane a ajouté +250 796 592 274\n"
        # A non-breaking space inside the number, which is how WhatsApp
        # writes it and which a literal space never matches.
        "[05/09/2026, 09:01:00] UniPods METI: Comme ce groupe inclut plus de "
        "256 membres, seulement les admins peuvent modifier\n"
        "[05/09/2026, 10:00:00] Steven: the deadline is Thursday\n"
    )

    messages = parse(tmp_path, export)

    assert [m["content"] for m in messages] == ["the deadline is Thursday"]


def test_any_bot_in_the_export_is_dropped(tmp_path):
    """A fresh export re-imported a rival bot's whole testing day an hour
    after it had been deleted from the database, and the bot went back to
    citing it. The parser knew one configurable name, and one name is never
    enough. The suffix rule is the organiser's own: every team was told to
    name its bot "<TEAM NAME> BOT"."""
    export = (
        "[20/09/2026, 10:56:15] Nexus Bot: Sure! Here are the recordings.\n"
        "[20/09/2026, 11:00:00] meti_bot: Good morning, I have no team today.\n"
        "[20/09/2026, 11:01:00] Swift Agents BOT: Hello everyone.\n"
        "[20/09/2026, 11:02:00] UniConnect-BOT: According to Steven: hello\n"
        "[20/09/2026, 11:03:00] Talbot Mensah: the deadline is Thursday\n"
    )

    messages = parse(tmp_path, export)

    # Talbot is a person. The boundary is what makes the difference.
    assert [m["author"] for m in messages] == ["Talbot Mensah"]
