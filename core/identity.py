"""Who is asking.

"What's my name?" went to retrieval, which looked through the group's
history for messages on the subject of names and answered with one it found.
Somebody was told they were called Shinzii and had to write back "My name
isn't Shinzii".

That is the same failure as answering a greeting with a quoted "bonjour":
the bot looks like it understood, and it looks stupid. The answer is not in
the history at all. It is in who sent the message, which the worker already
tells us and which we already store.

The wording says where the name came from, so a wrong one can be corrected
by the person rather than argued with. Nearly every name we have is the one
somebody set on their own WhatsApp profile.
"""

from psycopg.rows import dict_row

NAME_SQL = """
select display_name, origin
from people
where group_id = %(group_id)s and handle_norm = normalize_handle(%(user)s)
limit 1
"""

# Said when the name came from a WhatsApp profile, which is almost always.
# It is the one fact that makes a wrong answer fixable: the person can
# change it, and nobody else can.
FROM_PROFILE = {
    "en": ("The group sees you as {name}. That is the name on your WhatsApp "
           "profile, which is all I have to go on, so if it is wrong you can "
           "change it there and I will follow."),
    "fr": ("Le groupe te voit comme {name}. C'est le nom de ton profil "
           "WhatsApp, la seule chose dont je dispose, donc s'il est faux tu "
           "peux le changer là et je suivrai."),
}

# From the chat export or a contact card: not something the person controls
# from their phone, so the sentence above would send them to the wrong place.
FROM_THE_GROUP = {
    "en": "The group knows you as {name}.",
    "fr": "Le groupe te connaît sous le nom de {name}.",
}

UNKNOWN = {
    "en": ("I do not know your name. I only see the name somebody sets on "
           "their WhatsApp profile, and yours has not reached me, so the "
           "group sees your number where a name would be."),
    "fr": ("Je ne connais pas ton nom. Je ne vois que le nom que chacun "
           "définit sur son profil WhatsApp, et le tien ne m'est pas parvenu, "
           "donc le groupe voit ton numéro à la place."),
}

# On the public page there is no identity to read. The caller sends whatever
# they like as `user`, so answering with a name would be answering a
# question about somebody they had merely named.
NO_IDENTITY = {
    "en": ("I have no way of knowing who you are on this page. Ask me the "
           "same thing from WhatsApp and I will know."),
    "fr": ("Je n'ai aucun moyen de savoir qui tu es sur cette page. Pose-moi "
           "la même question depuis WhatsApp et je le saurai."),
}


def name_of(pool, group_id: str, user: str) -> dict | None:
    """The name the group knows this person by, and where it came from."""
    if not user:
        return None
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(NAME_SQL, {"group_id": group_id, "user": user})
            return cur.fetchone()


def answer(pool, group_id: str, user: str, lang: str, trusted: bool) -> str:
    """What to say to somebody asking who they are."""
    if not trusted:
        return NO_IDENTITY.get(lang, NO_IDENTITY["en"])

    try:
        known = name_of(pool, group_id, user)
    except Exception as exc:  # noqa: BLE001
        # A lookup that fails must not become a 500 on a question this
        # simple. Not knowing is a true answer and an acceptable one.
        print(f"name lookup failed: {exc}", flush=True)
        known = None

    if not known or not (known.get("display_name") or "").strip():
        return UNKNOWN.get(lang, UNKNOWN["en"])

    wording = FROM_PROFILE if known.get("origin") == "pushname" else FROM_THE_GROUP
    return wording.get(lang, wording["en"]).format(name=known["display_name"].strip())
