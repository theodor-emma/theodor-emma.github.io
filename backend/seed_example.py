"""
Run once to insert example invite documents into MongoDB.
Usage:  uv run seed_example.py
"""

from pymongo import MongoClient
from dotenv import load_dotenv
import os
import secrets
import string

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
invites = client[os.getenv("MONGODB_DB", "wedding")]["invites"]


def gen_key(n=8):
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n)
    )


examples = [
    {"name": "Marie Pichard"},
    {"name": "Jean & Claire Martin"},
    {"name": "Alexandru Ionescu"},
]

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
