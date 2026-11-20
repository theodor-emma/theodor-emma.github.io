"""Shared fixtures: the real API wired to an in-memory MongoDB.

`mongomock` stands in for the database, so the tests exercise the actual routes,
pydantic models and pymongo calls — only the server is replaced.
"""

import os

import mongomock
import pytest

# Set before importing main: it reads the environment at import time, and a
# developer's .env must not decide what the tests authenticate with.
ADMIN_SECRET = "test-admin-secret"
os.environ["ADMIN_SECRET"] = ADMIN_SECRET
os.environ["MONGODB_URI"] = "mongodb://mongomock.invalid:27017"

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN = {"admin_key": ADMIN_SECRET}


def adults(*names):
    return [{"name": name, "is_child": False} for name in names]


def child(name):
    return {"name": name, "is_child": True}


@pytest.fixture
def collection(monkeypatch):
    """A fresh, empty invites collection for each test."""
    coll = mongomock.MongoClient()["wedding"]["invites"]
    monkeypatch.setattr(main, "invites", coll)
    return coll


# Every test request comes from this (documentation-range) IPv4 address
TEST_IP = "203.0.113.5"


@pytest.fixture
def client(collection):
    main.guess_limiter.reset()
    return TestClient(main.app, client=(TEST_IP, 50000))


class Api:
    """Thin wrapper over the HTTP routes, so tests read like guest actions."""

    def __init__(self, client, collection):
        self.client = client
        self.collection = collection

    # ── Admin ──
    def create(self, **body):
        return self.client.post("/admin/invites", params=ADMIN, json=body)

    def edit(self, key, **body):
        return self.client.patch(f"/admin/invites/{key}", params=ADMIN, json=body)

    def delete(self, key):
        return self.client.delete(f"/admin/invites/{key}", params=ADMIN)

    def responses(self, **params):
        return self.client.get("/admin/responses", params={**ADMIN, **params})

    # ── Guest ──
    def invite(self, key):
        return self.client.get(f"/invite/{key}")

    def rsvp(self, key, guests, notes=""):
        return self.client.post(f"/invite/{key}/rsvp", json={"guests": guests, "notes": notes})

    # ── Convenience for setting a test up ──
    def new(self, **body):
        """Create an invitation and return it, failing loudly if that did not work."""
        res = self.create(**body)
        assert res.status_code == 200, res.text
        return res.json()

    def answer(self, key, guests, notes=""):
        """Submit an RSVP and return the updated invitation."""
        res = self.rsvp(key, guests, notes)
        assert res.status_code == 200, res.text
        return res.json()

    def stored(self, key):
        """The raw document, to check what actually reached the database."""
        return self.collection.find_one({"key": key}, {"_id": 0})


@pytest.fixture
def api(client, collection):
    return Api(client, collection)


@pytest.fixture
def family(api):
    """A household of three who may bring two more — the richest shape."""
    return api.new(
        guests=adults("Paul Duval", "Sophie Duval") + [child("Léa Duval")],
        label="Famille Duval",
        extra_guests_allowed=2,
        language="fr",
    )


@pytest.fixture
def single(api):
    return api.new(guests=adults("Marie Pichard"), language="fr")


@pytest.fixture
def plus_one(api):
    return api.new(guests=adults("Alexandru Ionescu"), extra_guests_allowed=1, language="ro")


def guest_ids(invite):
    return [g["id"] for g in invite["guests"]]


def added(name, is_child=False, **fields):
    """One entry of an RSVP payload for someone the invitees bring themselves."""
    return {"id": None, "name": name, "is_child": is_child, "attending": True, **fields}


def answer_for(invite, index, **fields):
    """Build one entry of an RSVP payload for an already-named guest."""
    guest = invite["guests"][index]
    return {
        "id": guest["id"],
        "name": guest["name"],
        "attending": True,
        "diet": "none",
        "allergies": "",
        "choir": False,
        **fields,
    }
