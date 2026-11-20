"""
Run once to insert example invite documents into MongoDB.
Usage:  uv run seed_example.py
"""

import os

from dotenv import load_dotenv
from pymongo import MongoClient

from invite_model import display_label, new_invite

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
invites = client[os.getenv("MONGODB_DB", "wedding")]["invites"]


def adults(*names):
    return [(name, False) for name in names]


def child(name):
    return [(name, True)]


# (guests, label, extra guests the invitees may add, language)
examples = [
    (adults("Marie Pichard"),                                        "",                0, "fr"),
    (adults("Alexandru Ionescu"),                                    "",                1, "ro"),
    (adults("Jean Martin", "Claire Martin"),                         "",                0, "fr"),
    (adults("Paul Duval", "Sophie Duval") + child("Léa Duval"),      "Famille Duval",   2, "fr"),
    (adults("Andrei Popescu", "Ioana Popescu"),                      "Familia Popescu", 3, "ro"),
    (adults("Sarah Whitfield"),                                      "",                0, "en"),
]

for i in range(20):
    examples.append((adults(f"Sample #{i}"), "", 0, "en"))

for guests, label, extra, language in examples:
    invite = new_invite(
        guests=guests,
        label=label,
        extra_guests_allowed=extra,
        language=language,
    )
    first_name = guests[0][0]
    # Idempotent on the first guest's name so re-running does not duplicate people
    existing = invites.find_one({"guests.0.name": first_name}) or invites.find_one({"name": first_name})
    if existing:
        print(f"{display_label(invite):34s}  exists, skipped")
        continue

    invites.insert_one(dict(invite))
    print(f"{display_label(invite):34s}  key: {invite['key']}")
