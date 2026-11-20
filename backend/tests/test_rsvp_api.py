"""What a guest does: open their invitation and answer for everyone on it."""

import pytest

from conftest import added, answer_for


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


def test_look_alike_characters_still_find_the_invitation(api, collection, single):
    collection.update_one({"key": single["key"]}, {"$set": {"key": "DJZSGBVA"}})
    assert api.invite("0lz5-6bua").status_code == 200
    invite = api.answer("o1Z5 68UA", [answer_for(single, 0)])
    assert invite["key"] == "DJZSGBVA"
    assert api.stored("DJZSGBVA")["last_submitted_at"] is not None


def test_codes_from_the_older_alphabet_keep_working(api, collection, single):
    collection.update_one({"key": single["key"]}, {"$set": {"key": "U87J5N3M"}})
    assert api.invite("u87j5n3m").json()["key"] == "U87J5N3M"


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
    assert stored["last_submitted_at"] is not None


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


def test_guests_cannot_rename_or_reage_the_people_we_invited(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, name="Someone Else", is_child=True)])
    assert invite["guests"][0]["name"] == "Paul Duval"
    assert invite["guests"][0]["is_child"] is False


def test_added_guests_need_someone_invited_to_come(api, family):
    invite = api.answer(family["key"], [
        *(answer_for(family, i, attending=False) for i in range(3)),
        added("Max Muster"),
    ])
    assert [g["name"] for g in invite["guests"]] == ["Paul Duval", "Sophie Duval", "Léa Duval"]
    assert not any(g["attending"] for g in invite["guests"])


def test_an_empty_name_leaves_ours_alone(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, name="")])
    assert invite["guests"][0]["name"] == "Paul Duval"


def test_an_answer_can_be_changed_later(api, family):
    api.answer(family["key"], [answer_for(family, 0, diet="vegan", choir=True)])
    invite = api.answer(family["key"], [answer_for(family, 0, diet="none", choir=False)])
    assert invite["guests"][0]["diet"] == "none"
    assert invite["guests"][0]["choir"] is False


def test_brunch_answer_is_stored_and_counted(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, brunch=True),
                                        answer_for(family, 1, brunch=False)])
    assert [g["brunch"] for g in invite["guests"][:2]] == [True, False]
    assert api.responses().json()[0]["brunch_count"] == 1


def test_invited_guests_can_answer_about_the_pizza_party(api):
    invite = api.new(guests=[{"name": "Ana"}, {"name": "Bob"}], extra_guests_allowed=1,
                     pizza_party_invited=True)
    assert api.invite(invite["key"]).json()["pizza_party_invited"] is True
    saved = api.answer(invite["key"], [
        answer_for(invite, 0, pizza_party=True),
        answer_for(invite, 1, pizza_party=False),
        added("Cam", pizza_party=True),
    ])
    assert [g["pizza_party"] for g in saved["guests"]] == [True, False, True]
    assert api.responses().json()[0]["pizza_party_count"] == 2


def test_the_pizza_party_is_off_by_default_and_cannot_be_joined_uninvited(api, family):
    assert family["pizza_party_invited"] is False
    saved = api.answer(family["key"], [answer_for(family, 0, pizza_party=True)])
    assert saved["guests"][0]["pizza_party"] is False


def test_who_is_responsible_does_not_decide_the_pizza_party(api):
    assert api.new(name="Ana", responsible="Emma")["pizza_party_invited"] is False


def test_someone_who_cannot_come_is_not_at_the_pizza_party(api):
    invite = api.new(name="Ana", pizza_party_invited=True)
    saved = api.answer(invite["key"], [answer_for(invite, 0, attending=False, pizza_party=True)])
    assert saved["guests"][0]["pizza_party"] is False


def test_someone_who_cannot_come_is_not_at_the_brunch(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, attending=False, brunch=True)])
    assert invite["guests"][0]["brunch"] is False
    assert api.responses().json()[0]["brunch_count"] == 0


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
        added(" Mamie Duval ", diet="vegan", choir=True),
    ])
    person = invite["guests"][-1]
    assert person["name"] == "Mamie Duval"
    assert person["source"] == "guest"
    assert (person["diet"], person["choir"], person["is_child"]) == ("vegan", True, False)
    assert api.responses().json()[0]["invited_count"] == 3    # additions are not ours
    assert api.responses().json()[0]["attending_count"] == 2


def test_more_guests_than_offered_is_refused(api, family):
    res = api.rsvp(family["key"], [
        answer_for(family, 0),
        added("One"),
        added("Two"),
        added("Three"),
    ])
    assert res.status_code == 400
    assert "at most 2" in res.json()["detail"]
    assert api.invite(family["key"]).json()["responded"] is False   # nothing was written


def test_someone_added_must_be_an_adult_or_a_child(api, family):
    res = api.rsvp(family["key"], [
        answer_for(family, 0),
        {"id": None, "name": "Mamie", "attending": True},
    ])
    assert res.status_code == 400
    assert "adult or a child" in res.json()["detail"]
    assert api.invite(family["key"]).json()["responded"] is False


def test_a_child_can_be_added_and_is_counted(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0), added("Tom", is_child=True)])
    assert invite["guests"][-1]["is_child"] is True
    assert api.responses().json()[0]["children_count"] == 1


def test_guests_cannot_change_who_the_hosts_marked_as_a_child(api, family):
    invite = api.answer(family["key"], [answer_for(family, 2, is_child=False)])
    assert invite["guests"][2]["is_child"] is True


def test_sons_and_daughters_can_be_children_or_adults(api):
    invite = api.new(name="Ana", extras_are_children=True)
    assert api.invite(invite["key"]).json()["extras_are_children"] is True
    saved = api.answer(invite["key"], [
        answer_for(invite, 0),
        added("Tom", is_child=True),
        added("Zoé", is_child=False),
    ])
    assert [g["is_child"] for g in saved["guests"][1:]] == [True, False]


def test_sons_and_daughters_also_need_an_answer(api):
    invite = api.new(name="Ana", extras_are_children=True)
    res = api.rsvp(invite["key"], [
        answer_for(invite, 0),
        {"id": None, "name": "Tom", "attending": True},
    ])
    assert res.status_code == 400


def test_a_single_invitation_cannot_grow(api, single):
    res = api.rsvp(single["key"], [
        answer_for(single, 0),
        added("Uninvited"),
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
        added("Ioana Marin", diet="vegetarian"),
    ])
    assert [g["name"] for g in invite["guests"]] == ["Alexandru Ionescu", "Ioana Marin"]
    assert invite["guests"][1]["source"] == "guest"


def test_a_companion_who_is_dropped_disappears(api, plus_one):
    api.answer(plus_one["key"], [
        answer_for(plus_one, 0),
        added("Ioana Marin"),
    ])
    invite = api.answer(plus_one["key"], [answer_for(plus_one, 0)])
    assert len(invite["guests"]) == 1


def test_an_id_from_another_invitation_cannot_be_hijacked(api, family, single):
    stranger = single["guests"][0]["id"]
    invite = api.answer(family["key"], [
        answer_for(family, 0),
        {"id": stranger, "name": "Intruder", "is_child": False, "attending": True},
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
    {"guests": [], "notes": "n" * 20_000},
    {"guests": [{"attending": True} for _ in range(30)]},
])
def test_oversized_payloads_are_refused(client, family, payload):
    res = client.post(f"/invite/{family['key']}/rsvp", json=payload)
    assert res.status_code == 422


@pytest.mark.parametrize("guest", [
    {"attending": True, "name": "N" * 100},
    {"attending": True, "allergies": "a" * 100},
    {"attending": True, "diet": "d" * 100},
    {"attending": True, "id": "i" * 100},
    {"attending": "yes"},
    {"attending": True, "surprise": 1},
])
def test_guest_answers_are_validated_strictly(api, family, guest):
    assert api.rsvp(family["key"], [guest]).status_code == 422


def test_text_just_within_the_limits_is_accepted(api, family):
    invite = api.answer(family["key"], [answer_for(family, 0, allergies="a" * 99)], notes="n" * 19_999)
    assert len(invite["notes"]) == 19_999
    assert api.rsvp(family["key"], [], notes="n" * 20_000).status_code == 422


def test_an_over_long_code_is_refused(api):
    assert api.invite("K" * 100).status_code == 422


# ── Bank details ──────────────────────────────────────────────────────────────

def test_bank_details_need_a_valid_code(api, single, monkeypatch):
    monkeypatch.setenv("GIFT_IBAN", "FR76 1234")
    assert api.client.get("/invite/NOSUCH99/gift").status_code == 404
    details = api.client.get(f"/invite/{single['key'].lower()}/gift").json()
    assert details["iban"] == "FR76 1234"
    assert set(details) == {"account_holder", "iban", "bic"}


def test_looking_at_bank_details_changes_nothing(api, single):
    before = api.stored(single["key"])
    api.client.get(f"/invite/{single['key']}/gift")
    assert api.stored(single["key"]) == before


# ── Guessing codes ────────────────────────────────────────────────────────────

def test_too_many_wrong_codes_lock_the_address_out(api, single):
    for i in range(10):
        assert api.invite(f"NOPE{i:04d}").status_code == 404
    res = api.invite(single["key"])
    assert res.status_code == 429
    assert api.client.get(f"/invite/{single['key']}/gift").status_code == 429
    assert api.rsvp(single["key"], []).status_code == 429


def test_opening_a_real_invitation_never_counts(api, single):
    for _ in range(40):
        assert api.invite(single["key"]).status_code == 200


def test_another_address_is_not_affected(api, single):
    import main
    from fastapi.testclient import TestClient
    for i in range(10):
        api.invite(f"NOPE{i:04d}")
    neighbour = TestClient(main.app, client=("198.51.100.7", 50000))
    assert neighbour.get(f"/invite/{single['key']}").status_code == 200


def test_ipv6_is_not_limited(api, single):
    import main
    from fastapi.testclient import TestClient
    v6 = TestClient(main.app, client=("2001:db8::1", 50000))
    for i in range(30):
        assert v6.get(f"/invite/NOPE{i:04d}").status_code == 404
    assert v6.get(f"/invite/{single['key']}").status_code == 200


# ── When things happened ──────────────────────────────────────────────────────

def test_only_the_first_opening_is_recorded(api, single, collection):
    assert api.stored(single["key"])["first_opened_at"] is None
    api.invite(single["key"])
    first = api.stored(single["key"])["first_opened_at"]
    assert first is not None
    collection.update_one({"key": single["key"]}, {"$set": {"first_opened_at": "earlier"}})
    api.invite(single["key"])
    assert api.stored(single["key"])["first_opened_at"] == "earlier"
    assert api.stored(single["key"])["history"] == []


def test_first_and_last_submission(api, single, collection):
    api.answer(single["key"], [answer_for(single, 0)])
    stored = api.stored(single["key"])
    assert stored["first_submitted_at"] == stored["last_submitted_at"]
    assert stored["first_opened_at"] is not None
    collection.update_one({"key": single["key"]},
                          {"$set": {"first_submitted_at": "first", "last_submitted_at": "old"}})
    api.answer(single["key"], [answer_for(single, 0, diet="vegan")])
    stored = api.stored(single["key"])
    assert stored["first_submitted_at"] == "first"
    assert stored["last_submitted_at"] != "old"


def test_timestamps_and_history_stay_private(api, single):
    api.answer(single["key"], [answer_for(single, 0)])
    public = api.invite(single["key"]).json()
    assert not {"history", "first_opened_at", "first_submitted_at", "last_submitted_at"} & set(public)
    assert "history" not in api.responses().json()[0]


# ── History ───────────────────────────────────────────────────────────────────

def test_history_records_what_changed(api, single):
    api.answer(single["key"], [answer_for(single, 0, diet="vegan")], notes="Hello")
    api.answer(single["key"], [answer_for(single, 0, diet="vegetarian")], notes="Hello")
    history = api.stored(single["key"])["history"]
    assert [e["by"] for e in history] == ["guest", "guest"]
    assert [(c["field"], c["from"], c["to"]) for c in history[1]["changes"]] \
        == [("diet", "vegan", "vegetarian")]


def test_replying_with_the_same_answers_adds_nothing(api, plus_one):
    answers = [answer_for(plus_one, 0), added("Ioana Marin")]
    api.answer(plus_one["key"], answers)
    guest_id = api.invite(plus_one["key"]).json()["guests"][1]["id"]
    api.answer(plus_one["key"], answers)
    assert len(api.stored(plus_one["key"])["history"]) == 1
    assert api.invite(plus_one["key"]).json()["guests"][1]["id"] == guest_id


def test_history_keeps_only_the_last_hundred_changes(api, single):
    for i in range(105):
        api.answer(single["key"], [answer_for(single, 0)], notes=f"note {i}")
    history = api.stored(single["key"])["history"]
    assert len(history) == 100
    assert history[-1]["changes"][0]["to"] == "note 104"
    assert history[0]["changes"][0]["to"] == "note 5"


def test_history_never_contains_history(api, single):
    for i in range(3):
        api.answer(single["key"], [answer_for(single, 0)], notes=f"note {i}")
    assert "'history'" not in str(api.stored(single["key"])["history"])


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
