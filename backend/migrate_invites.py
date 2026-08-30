"""
Rewrite invite documents from the old one-row-per-invitation format
(name / dietary_restrictions / plus_one…) into the current guest-list format.

The API tolerates both shapes, so this is only about tidying the database.

Usage:
    uv run migrate_invites.py           # dry run, prints what would change
    uv run migrate_invites.py --apply   # write the changes
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

from invite_model import display_label, normalize_invite

load_dotenv()

APPLY = "--apply" in sys.argv

client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
invites = client[os.getenv("MONGODB_DB", "wedding")]["invites"]

LEGACY_FIELDS = [
    "name",
    "dietary_restrictions",
    "plus_one",
    "plus_one_name",
    "plus_one_dietary",
]

converted = 0
skipped = 0

for doc in invites.find({}):
    if isinstance(doc.get("guests"), list) and "invite_type" in doc:
        skipped += 1
        continue

    invite = normalize_invite(doc)
    update = {
        "invite_type":          invite["invite_type"],
        "label":                invite["label"],
        "language":             invite["language"],
        "guests":               invite["guests"],
        "extra_guests_allowed": invite["extra_guests_allowed"],
        "notes":                invite["notes"],
        "responded_at":         invite["responded_at"],
    }

    people = ", ".join(f"{g['name'] or '(unnamed)'} [{g['source']}]" for g in invite["guests"])
    print(f"{invite['key']:10s} {invite['invite_type']:9s} {display_label(invite):28s} → {people}")

    if APPLY:
        invites.update_one(
            {"_id": doc["_id"]},
            {"$set": update, "$unset": {f: "" for f in LEGACY_FIELDS}},
        )
    converted += 1

print()
print(f"{converted} invitation(s) {'converted' if APPLY else 'to convert'}, {skipped} already current")
if converted and not APPLY:
    print("Re-run with --apply to write the changes.")
