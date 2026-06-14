"""
Run once to insert example invite documents into MongoDB.
Usage:  python seed_example.py
"""
from pymongo import MongoClient
import secrets, string

client  = MongoClient("mongodb://localhost:27017")
invites = client["wedding"]["invites"]

def gen_key(n=8):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))

examples = [
    {"name": "Marie Dupont"},
    {"name": "Jean & Claire Martin"},
    {"name": "Alexandru Ionescu"},
]

for guest in examples:
    key = gen_key()
    invites.update_one(
        {"name": guest["name"]},
        {"$setOnInsert": {
            "key":                  key,
            "name":                 guest["name"],
            "attending":            None,
            "dietary_restrictions": "",
            "notes":                "",
            "responded_at":         None,
        }},
        upsert=True,
    )
    print(f"{guest['name']:30s}  key: {key}")
