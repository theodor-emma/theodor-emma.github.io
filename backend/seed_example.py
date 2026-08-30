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


# (invite_type, guest names, label, extra guests the invitees may add, language)
examples = [
    ("single",   ["Marie Pichard"],                                   "",                 0, "fr"),
    ("plus_one", ["Alexandru Ionescu"],                               "",                 1, "ro"),
    ("couple",   ["Jean Martin", "Claire Martin"],                    "",                 0, "fr"),
    ("family",   ["Paul Duval", "Sophie Duval", "Léa Duval"],         "Famille Duval",    2, "fr"),
    ("family",   ["Andrei Popescu", "Ioana Popescu"],                 "Familia Popescu",  3, "ro"),
    ("single",   ["Sarah Whitfield"],                                 "",                 0, "en"),
]

for i in range(20):
    examples.append(("single", [f"Sample #{i}"], "", 0, "en"))

for invite_type, names, label, extra, language in examples:
    invite = new_invite(
        invite_type=invite_type,
        guest_names=names,
        label=label,
        extra_guests_allowed=extra,
        language=language,
    )
    # Idempotent on the first guest's name so re-running does not duplicate people
    existing = invites.find_one({"guests.0.name": names[0]}) or invites.find_one({"name": names[0]})
    if existing:
        print(f"{display_label(invite):34s}  exists, skipped")
        continue

    invites.insert_one(dict(invite))
    print(f"{display_label(invite):34s}  {invite_type:9s}  key: {invite['key']}")
