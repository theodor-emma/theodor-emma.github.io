"""
Run once to insert example invite documents into MongoDB.
Usage:  uv run seed_example.py
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
import secrets

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
invites = client[os.getenv("MONGODB_DB", "wedding")]["invites"]


# Unambiguous alphabet — excludes easily confused characters (I, L, O, 0, 1)
KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gen_key(n=8):
    return "".join(secrets.choice(KEY_ALPHABET) for _ in range(n))


examples = [
    {"name": "Marie Pichard"},
    {"name": "Jean & Claire Martin"},
    {"name": "Alexandru Ionescu"},
]

for i in range(100):
    examples.append({"name": f"Sample #{i}"})

for guest in examples:
    key = gen_key()
    invites.update_one(
        {"name": guest["name"]},
        {
            "$setOnInsert": {
                "key": key,
                "name": guest["name"],
                "attending": None,
                "dietary_restrictions": "",
                "notes": "",
                "plus_one": False,
                "plus_one_name": "",
                "plus_one_dietary": "",
                "responded_at": None,
            }
        },
        upsert=True,
    )
    print(f"{guest['name']:30s}  key: {key}")
