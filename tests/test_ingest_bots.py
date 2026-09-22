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


# --------------------------------------------------------------------------
# What live ingestion had never learned
# --------------------------------------------------------------------------


def test_a_command_to_another_teams_bot_is_not_group_content():
    """The export parser has had this rule since a question typed at a rival
    bot became the source for somebody else's answer. Live ingestion never
    got it, so it kept storing them."""
    for content in [
        "@~Jymns Bot Okay provide the session video links",
        "@~Jymns Bot I need an email to submit my team member list",
        "@Nexus Bot what is the deadline",
        "@ask what is the deadline",
    ]:
        assert ingest.written_by_a_bot({"author_name": "N", "content": content}), content


def test_a_bots_own_output_pasted_into_the_group_is_not_either():
    """Our bot cited one of these. The link it gave was correct and the
    message it credited was another bot's summary, so a claim invented
    elsewhere came back wearing our citation."""
    assert ingest.written_by_a_bot(
        {
            "author_name": "N",
            "content": "Here is what I currently know about the *UniPods METI AI Programme*",
        }
    )


def test_the_people_behind_those_accounts_keep_their_messages():
    """Both accounts belong to real members, with forty messages between
    them, arguing about bots in their own words. An earlier reading of this
    took them for bots, and deleting by author would have erased people."""
    for content in [
        "Dude that was not automated, it's manually typed can't you see dude",
        "If my bot performed like that, I'd be glad to take the removal sacrifice.",
        "Nexus is back - Inbox (DM). You can ask anything from now on.",
        "Ask Nexus Bot in inbox u get a reliable info.",
        "It's completely wrong",
    ]:
        assert not ingest.written_by_a_bot(
            {"author_name": "N", "content": content}
        ), content
