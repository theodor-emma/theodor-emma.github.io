"""What a guest does: open their invitation and answer for everyone on it."""

import pytest

from conftest import answer_for


# ── Opening an invitation ─────────────────────────────────────────────────────

def test_an_invitation_shows_everyone_it_covers(api, family):
    invite = api.invite(family["key"]).json()
    assert invite["label"] == "Famille Duval"
    assert invite["language"] == "fr"
    assert invite["extra_guests_allowed"] == 2
    assert [g["name"] for g in invite["guests"]] == ["Paul Duval", "Sophie Duval", "Léa Duval"]
    assert invite["responded"] is False


@pytest.mark.parametrize("mangle", [
    str.lower,
    lambda k: f"{k[:4]}-{k[4:]}",
    lambda k: f"  {k}  ",
    lambda k: f"{k[:4]} {k[4:]}",
])
def test_codes_survive_being_typed_by_hand(api, single, mangle):
    assert api.invite(mangle(single["key"])).status_code == 200


@pytest.mark.parametrize("key", ["NOSUCH99", "", "   ", "!!!"])
def test_unknown_codes_are_not_found(api, key):
    assert api.invite(key).status_code == 404


# ── Answering ─────────────────────────────────────────────────────────────────

def test_each_person_answers_for_themselves(api, family):
    invite = api.answer(family["key"], [
        answer_for(family, 0, diet="vegetarian", allergies=" nuts ", choir=True),
        answer_for(family, 1, attending=False),
        answer_for(family, 2, diet="vegan"),
    ], notes="  See you there!  ")

    paul, sophie, lea = invite["guests"]
    assert (paul["attending"], paul["diet"], paul["allergies"], paul["choir"]) \
        == (True, "vegetarian", "nuts", True)
    assert sophie["attending"] is False
    assert lea["diet"] == "vegan"
    assert invite["responded"] is True
    assert invite["notes"] == "See you there!"


def test_the_answer_reaches_the_database(api, family):
    api.answer(family["key"], [answer_for(family, 0, choir=True)])
    stored = api.stored(family["key"])
    assert stored["guests"][0]["choir"] is True
    assert stored["responded_at"] is not None


def test_declining_for_everyone(api, family):
    invite = api.answer(family["key"], [
        answer_for(family, i, attending=False) for i in range(3)
    ], notes="So sorry")
    assert invite["responded"] is True
    assert all(g["attending"] is False for g in invite["guests"])
    assert api.responses().json()[0]["attending"] is False


def test_people_left_out_of_the_reply_count_as_absent(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0)])
    assert [g["attending"] for g in invite["guests"]] == [True, False, False]
    assert [g["name"] for g in invite["guests"]] == ["Paul Duval", "Sophie Duval", "Léa Duval"]


def test_a_guest_may_fix_a_misspelt_name(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, name="Paul Duvall")])
    assert invite["guests"][0]["name"] == "Paul Duvall"


def test_an_empty_name_leaves_ours_alone(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, name="")])
    assert invite["guests"][0]["name"] == "Paul Duval"


def test_an_answer_can_be_changed_later(api, family):
    api.answer(family["key"], [answer_for(family, 0, diet="vegan", choir=True)])
    invite = api.answer(family["key"], [answer_for(family, 0, diet="none", choir=False)])
    assert invite["guests"][0]["diet"] == "none"
    assert invite["guests"][0]["choir"] is False


def test_someone_who_cannot_come_is_not_in_the_choir(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, attending=False, choir=True)])
    assert invite["guests"][0]["choir"] is False
    assert api.responses().json()[0]["choir_count"] == 0


def test_an_unknown_diet_falls_back_to_no_restriction(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, diet="sausages")])
    assert invite["guests"][0]["diet"] == "none"


# ── Guests the invitees bring themselves ──────────────────────────────────────

def test_a_household_may_add_the_people_it_was_offered(api, family):
    invite = api.answer(family["key"], [
        answer_for(family, 0),
        {"id": None, "name": " Mamie Duval ", "attending": True, "diet": "vegan", "choir": True},
    ])
    added = invite["guests"][-1]
    assert added["name"] == "Mamie Duval"
    assert added["source"] == "guest"
    assert (added["diet"], added["choir"]) == ("vegan", True)
    assert api.responses().json()[0]["invited_count"] == 3    # additions are not ours
    assert api.responses().json()[0]["attending_count"] == 2


def test_more_guests_than_offered_is_refused(api, family):
    res = api.rsvp(family["key"], [
        {"id": None, "name": "One", "attending": True},
        {"id": None, "name": "Two", "attending": True},
        {"id": None, "name": "Three", "attending": True},
    ])
    assert res.status_code == 400
    assert "at most 2" in res.json()["detail"]
    assert api.invite(family["key"]).json()["responded"] is False   # nothing was written


def test_a_single_invitation_cannot_grow(api, single):
    res = api.rsvp(single["key"], [
        answer_for(single, 0),
        {"id": None, "name": "Uninvited", "attending": True},
    ])
    assert res.status_code == 400


def test_nameless_or_absent_additions_are_dropped(api, family):
    invite = api.answer(family["key"], [
        answer_for(family, 0),
        {"id": None, "name": "", "attending": True},
        {"id": None, "name": "Not coming", "attending": False},
    ])
    assert len(invite["guests"]) == 3


def test_a_plus_one_names_their_companion(api, plus_one):
    invite = api.answer(plus_one["key"], [
        answer_for(plus_one, 0),
        {"id": None, "name": "Ioana Marin", "attending": True, "diet": "vegetarian"},
    ])
    assert [g["name"] for g in invite["guests"]] == ["Alexandru Ionescu", "Ioana Marin"]
    assert invite["guests"][1]["source"] == "guest"


def test_a_companion_who_is_dropped_disappears(api, plus_one):
    api.answer(plus_one["key"], [
        answer_for(plus_one, 0),
        {"id": None, "name": "Ioana Marin", "attending": True},
    ])
    invite = api.answer(plus_one["key"], [answer_for(plus_one, 0)])
    assert len(invite["guests"]) == 1


def test_an_id_from_another_invitation_cannot_be_hijacked(api, family, single):
    stranger = single["guests"][0]["id"]
    invite = api.answer(family["key"], [
        {"id": stranger, "name": "Intruder", "attending": True},
    ])
    # Treated as a guest the household added, never as an edit of someone else
    assert [g["name"] for g in invite["guests"]][:3] == ["Paul Duval", "Sophie Duval", "Léa Duval"]
    assert invite["guests"][-1]["source"] == "guest"
    assert api.invite(single["key"]).json()["guests"][0]["name"] == "Marie Pichard"


# ── Bad input ─────────────────────────────────────────────────────────────────

def test_answering_an_unknown_invitation(api):
    assert api.rsvp("NOSUCH99", []).status_code == 404


@pytest.mark.parametrize("payload", [
    {"guests": [{"name": "N" * 200, "attending": True}]},
    {"guests": [{"attending": True, "allergies": "a" * 500}]},
    {"guests": [], "notes": "n" * 2000},
    {"guests": [{"attending": True} for _ in range(30)]},
])
def test_oversized_payloads_are_refused(client, family, payload):
    res = client.post(f"/invite/{family['key']}/rsvp", json=payload)
    assert res.status_code == 422


# ── Older documents ───────────────────────────────────────────────────────────

LEGACY = {
    "key": "OLDKEY22",
    "name": "Old Guest",
    "attending": None,
    "dietary_restrictions": "",
    "notes": "",
    "plus_one": False,
    "plus_one_name": "",
    "plus_one_dietary": "",
    "responded_at": None,
}


def test_an_invitation_from_the_old_format_still_works(api, collection):
    collection.insert_one(dict(LEGACY))

    invite = api.invite("OLDKEY22").json()
    assert [g["name"] for g in invite["guests"]] == ["Old Guest"]

    answered = api.answer("OLDKEY22", [
        {"id": invite["guests"][0]["id"], "attending": True, "diet": "vegan", "choir": True},
    ])
    assert len(answered["guests"]) == 1, "the guest must be updated, not duplicated"
    assert answered["guests"][0]["diet"] == "vegan"
    assert api.stored("OLDKEY22")["guests"][0]["choir"] is True


def test_a_document_whose_guests_have_no_ids_is_answered_not_duplicated(api, collection):
    collection.insert_one({
        "key": "HALFWAY2", "invite_type": "couple", "label": "", "language": "fr",
        "extra_guests_allowed": 0, "notes": "", "responded_at": None,
        "guests": [{"name": "Jean Martin"}, {"name": "Claire Martin"}],
    })

    invite = api.invite("HALFWAY2").json()
    again = api.invite("HALFWAY2").json()
    assert [g["id"] for g in invite["guests"]] == [g["id"] for g in again["guests"]], \
        "ids handed to the RSVP page must be the same on the next read"

    answered = api.answer("HALFWAY2", [
        {"id": invite["guests"][0]["id"], "name": "Jean Martin", "attending": True, "diet": "vegan"},
    ])
    assert [g["name"] for g in answered["guests"]] == ["Jean Martin", "Claire Martin"]
    assert answered["guests"][0]["diet"] == "vegan"


def test_the_dashboard_can_list_old_and_new_side_by_side(api, collection, family):
    collection.insert_one(dict(LEGACY))
    rows = api.responses().json()
    assert {r["key"] for r in rows} == {family["key"], "OLDKEY22"}
    assert all("guests" in r and "invited_count" in r for r in rows)


# ── Database trouble ──────────────────────────────────────────────────────────

def test_a_database_outage_is_reported_as_unavailable(client, monkeypatch):
    from pymongo.errors import PyMongoError

    import main

    class Broken:
        def find_one(self, *a, **k):
            raise PyMongoError("no connection")

        find = update_one = insert_one = delete_one = find_one

    monkeypatch.setattr(main, "invites", Broken())
    res = client.get("/invite/ANYKEY22")
    assert res.status_code == 503
    assert res.json()["detail"] == "Database unavailable"
