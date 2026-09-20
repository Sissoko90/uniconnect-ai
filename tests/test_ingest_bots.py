"""No bot's words go into a record of what the group said.

A stored message is a message that can be cited. On the day a rival bot was
tested in the group, ours answered "Per the bot's reply in the group: yes,
you can still move forward..." and cited it, relaying another bot's
invention as something the group had said. Asked who the community admin
was, it read out a coordinator's phone number in full, taken from the same
bot's message.

Ours is on the list too. A bot that can cite itself will eventually agree
with itself about something it invented.
"""

import ingest
import pytest


@pytest.mark.parametrize(
    "name",
    ["meti_bot", "Nexus Bot", "PodPal", "UniConnect-BOT", "nexus bot", "METI_BOT"],
)
def test_known_bots_are_refused(name):
    assert ingest.written_by_a_bot({"author_name": name})


@pytest.mark.parametrize("name", ["Swift Agents BOT", "ASKBACK-BOT", "wise_bot"])
def test_anything_named_like_a_bot_is_refused(name):
    """Every team was asked to name its bot "<TEAM> BOT", so the suffix is
    the rule the organiser herself set. Waiting to learn each new bot's JID
    means blocking it the day after it has been cited."""
    assert ingest.written_by_a_bot({"author_name": name})


@pytest.mark.parametrize(
    "name",
    ["Diane", "Steven IRINGIRA", "Abdulmajid Haruna Saeed", "Robert", "Talbot"],
)
def test_people_are_not_refused(name):
    """"Talbot" and "Robert" end in the letters but are not bots. The test
    is on a word boundary for that reason."""
    assert not ingest.written_by_a_bot({"author_name": name})


def test_a_message_with_no_name_is_kept():
    """Most messages arrive without a pushName. Refusing those would empty
    the history."""
    assert not ingest.written_by_a_bot({"author": "+22370000000@s.whatsapp.net"})
