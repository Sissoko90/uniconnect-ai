"""A citation under "I could not find it", and a bot that does not know you.

From the group, on the testing day:

    Victor:  @ask My name isn't Shinzii 👀
             What's my name?
    the bot: I could not find your name in the group messages.
             • Edwin A, 16 Sept
    Victor:  @ask Edwin A, 16 Sept
             Edwin is this your birthday?🤣

Two faults in four lines. The bot searched the group's history for the
asker's name, which is the one question whose answer was never in the
history. And having found nothing, it printed a source anyway, so the
member read "Edwin A, 16 Sept" as the answer and replied to it.
"""

import answer as answer_engine
import identity
import intent


def hits(n: int) -> list[dict]:
    return [{"id": f"id-{i}", "content": f"message {i}"} for i in range(1, n + 1)]


# --------------------------------------------------------------------------
# A source under an answer that found nothing
# --------------------------------------------------------------------------


def test_an_answer_that_cites_nothing_shows_nothing():
    """The fault itself. An uncited answer is nearly always an answer that
    found nothing, and the nearest message is not evidence for it."""
    assert answer_engine.cited_hits(hits(6), []) == []


def test_an_answer_keeps_the_messages_it_cited():
    used = answer_engine.cited_hits(hits(6), [2, 4])

    assert [h["id"] for h in used] == ["id-2", "id-4"]


def test_a_citation_past_the_end_is_dropped_not_crashed():
    """A number beyond the list is the model miscounting. Dropping it loses
    one citation; indexing on it would turn a good answer into an exception
    and a fallback quote."""
    assert answer_engine.cited_hits(hits(3), [1, 9]) == hits(3)[:1]


# --------------------------------------------------------------------------
# Who is asking
# --------------------------------------------------------------------------


def test_the_message_that_started_this_is_recognised():
    assert intent.asks_their_own_name("My name isn't Shinzii 👀\nWhat's my name?")


def test_asking_who_you_are_in_either_language():
    for question in [
        "what's my name",
        "what is my name?",
        "who am I",
        "do you know my name",
        "comment je m'appelle ?",
        # The curly apostrophe a phone keyboard actually produces.
        "comment je m’appelle ?",
        "c'est quoi mon nom",
        "qui suis-je",
        "tu connais mon nom ?",
    ]:
        assert intent.asks_their_own_name(question), question


def test_telling_the_bot_your_name_is_not_asking_it():
    """"My name is Awa, where do I send the video?" is somebody introducing
    themselves before a real question. Answering it with their own name back
    would be a non sequitur."""
    for question in [
        "my name is Awa, where do I send the video?",
        "what is the name of the winning team",
        "who is the organiser",
    ]:
        assert not intent.asks_their_own_name(question), question


# --------------------------------------------------------------------------
# The answer
# --------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, sql, params=()):
        return self

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePool:
    def __init__(self, row=None):
        self.cur = FakeCursor(row)

    def connection(self):
        return self

    def cursor(self, row_factory=None):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_name_from_a_whatsapp_profile_says_where_it_came_from():
    """The one fact that makes a wrong answer fixable by the person rather
    than argued with: they can change it, and nobody else can."""
    pool = FakePool({"display_name": "Akpan, Victor D.", "origin": "pushname"})

    said = identity.answer(pool, "meti-cohort-1", "234@s.whatsapp.net", "en", True)

    assert "Akpan, Victor D." in said
    assert "WhatsApp profile" in said


def test_a_name_from_the_group_is_given_plainly():
    """From the export or a contact card, which the person cannot change
    from their phone, so sending them there would be wrong."""
    pool = FakePool({"display_name": "Diane", "origin": "vcard"})

    said = identity.answer(pool, "meti-cohort-1", "223@s.whatsapp.net", "fr", True)

    assert "Diane" in said
    assert "WhatsApp" not in said


def test_not_knowing_is_said_rather_than_guessed():
    pool = FakePool(None)

    said = identity.answer(pool, "meti-cohort-1", "223@s.whatsapp.net", "en", True)

    assert "do not know your name" in said


def test_the_public_page_has_no_identity_to_read():
    """`user` is whatever the caller typed there, so answering with a name
    would answer a question about somebody they had merely named."""
    pool = FakePool({"display_name": "Diane", "origin": "vcard"})

    said = identity.answer(pool, "meti-cohort-1", "Diane", "en", False)

    assert "Diane" not in said
    assert "WhatsApp" in said


def test_a_failed_lookup_is_not_knowing_rather_than_an_error():
    class Broken(FakePool):
        def connection(self):
            raise RuntimeError("database gone")

    said = identity.answer(Broken(), "meti-cohort-1", "223@s.whatsapp.net", "en", True)

    assert "do not know your name" in said


def test_who_am_i_only_when_the_question_ends_there():
    """"Who am I supposed to email about the visa?" is a question about the
    programme. Answering it with the asker's own name would be the same
    failure in a new place."""
    assert intent.asks_their_own_name("who am I?")
    assert not intent.asks_their_own_name("who am I supposed to email about the visa?")
    assert not intent.asks_their_own_name("qui suis-je censé contacter pour Wadhwani ?")
