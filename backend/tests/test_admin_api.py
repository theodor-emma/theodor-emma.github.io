"""Managing invitations: creating, listing, editing, deleting — and who may."""

import pytest

from conftest import ADMIN


# ── Access ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("get",    "/admin/responses",       None),
    ("post",   "/admin/invites",         {"name": "X"}),
    ("patch",  "/admin/invites/ABC123",  {"label": "X"}),
    ("delete", "/admin/invites/ABC123",  None),
])
def test_admin_routes_need_the_secret(client, method, path, body):
    call = getattr(client, method)
    for params in ({}, {"admin_key": "wrong"}, {"admin_key": ""}):
        res = call(path, params=params, **({"json": body} if body else {}))
        assert res.status_code == 403, f"{method} {path} with {params}"


def test_guest_routes_stay_open(api, single):
    assert api.invite(single["key"]).status_code == 200


# ── Creating ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("invite_type,names,extra,expected_extra", [
    ("single",   ["Solo"],                    0, 0),
    ("couple",   ["Jean", "Claire"],          0, 0),
    ("plus_one", ["Alex"],                    0, 1),   # always exactly one companion
    ("family",   ["A", "B", "C"],             2, 2),
])
def test_create_each_kind_of_invitation(api, invite_type, names, extra, expected_extra):
    invite = api.new(invite_type=invite_type, guest_names=names, extra_guests_allowed=extra)
    assert invite["invite_type"] == invite_type
    assert [g["name"] for g in invite["guests"]] == names
    assert invite["invited_count"] == len(names)
    assert invite["extra_guests_allowed"] == expected_extra
    assert invite["responded"] is False and invite["attending"] is None


@pytest.mark.parametrize("invite_type,names", [
    ("couple", ["Only One"]),
    ("couple", ["One", "Two", "Three"]),
    ("single", ["One", "Two"]),
    ("plus_one", []),
    ("family", []),
])
def test_the_number_of_names_must_match_the_type(api, invite_type, names):
    res = api.create(invite_type=invite_type, guest_names=names)
    assert res.status_code == 400
    assert "invitation needs" in res.json()["detail"]


def test_unknown_type_falls_back_to_a_single_invitation(api):
    invite = api.new(invite_type="banquet", guest_names=["Solo"])
    assert invite["invite_type"] == "single"


def test_blank_names_are_dropped(api):
    res = api.create(invite_type="couple", guest_names=["Jean", "   "])
    assert res.status_code == 400          # only one real name left


def test_a_plain_name_still_works(api):
    """The quick-add shorthand the older admin page used."""
    invite = api.new(name="Marie Pichard")
    assert invite["invite_type"] == "single"
    assert invite["display_label"] == "Marie Pichard"


def test_each_invitation_gets_its_own_code(api):
    keys = {api.new(name=f"Guest {i}")["key"] for i in range(25)}
    assert len(keys) == 25


def test_a_created_invitation_is_written_to_the_database(api, collection):
    invite = api.new(invite_type="family", guest_names=["A", "B"], label="Household")
    stored = api.stored(invite["key"])
    assert stored["label"] == "Household"
    assert [g["name"] for g in stored["guests"]] == ["A", "B"]
    assert collection.count_documents({}) == 1


def test_over_long_text_is_refused(api):
    res = api.create(invite_type="single", guest_names=["N" * 200])
    assert res.status_code == 422


# ── Email address ─────────────────────────────────────────────────────────────

def test_an_invitation_can_carry_an_email_address(api):
    invite = api.new(name="Marie Pichard", email="  Marie@Example.com ")
    assert invite["email"] == "Marie@Example.com"
    assert api.stored(invite["key"])["email"] == "Marie@Example.com"


@pytest.mark.parametrize("bad", ["not-an-address", "@example.com", "marie@", "a b@c.com", "x@y"])
def test_something_that_is_not_an_address_is_not_kept(api, bad):
    assert api.new(name="Marie", email=bad)["email"] == ""


def test_the_address_is_not_handed_to_whoever_has_the_code(api):
    invite = api.new(name="Marie", email="marie@example.com")
    assert "email" not in api.invite(invite["key"]).json()


def test_an_address_can_be_added_and_removed_later(api, single):
    assert api.edit(single["key"], email="later@example.com").json()["email"] == "later@example.com"
    assert api.edit(single["key"], label="Marie").json()["email"] == "later@example.com"  # untouched
    assert api.edit(single["key"], email="").json()["email"] == ""


# ── Adding a whole list at once ───────────────────────────────────────────────

def test_a_pasted_list_becomes_invitations(api, collection):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={"invites": [
        {"invite_type": "single", "guest_names": ["Marie Pichard"], "email": "marie@example.com"},
        {"invite_type": "couple", "guest_names": ["Jean Martin", "Claire Martin"], "language": "fr"},
        {"invite_type": "plus_one", "guest_names": ["Alexandru Ionescu"], "language": "ro"},
        {"invite_type": "family", "guest_names": ["Paul", "Sophie", "Léa"],
         "label": "Famille Duval", "extra_guests_allowed": 2},
    ]})
    assert res.status_code == 200, res.text

    created = res.json()["created"]
    assert [c["invite_type"] for c in created] == ["single", "couple", "plus_one", "family"]
    assert created[0]["email"] == "marie@example.com"
    assert created[2]["extra_guests_allowed"] == 1
    assert created[3]["display_label"] == "Famille Duval"
    assert collection.count_documents({}) == 4
    assert len({c["key"] for c in created}) == 4


def test_one_bad_line_adds_nothing_at_all(api, collection):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={"invites": [
        {"invite_type": "single", "guest_names": ["Fine"]},
        {"invite_type": "couple", "guest_names": ["Only One"]},
        {"invite_type": "family", "guest_names": []},
    ]})
    assert res.status_code == 400
    assert "line 2" in res.json()["detail"] and "line 3" in res.json()["detail"]
    assert collection.count_documents({}) == 0


def test_an_empty_paste_says_so(api):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={"invites": []})
    assert res.status_code == 400


def test_a_very_long_paste_is_refused(api):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={
        "invites": [{"name": f"Guest {i}"} for i in range(300)]})
    assert res.status_code == 422


def test_bulk_needs_the_admin_key(client):
    res = client.post("/admin/invites/bulk", json={"invites": [{"name": "X"}]})
    assert res.status_code == 403


# ── Listing ───────────────────────────────────────────────────────────────────

def test_responses_list_carries_the_dashboard_counts(api, family, single):
    rows = api.responses().json()
    assert {r["key"] for r in rows} == {family["key"], single["key"]}
    row = next(r for r in rows if r["key"] == family["key"])
    assert row["invited_count"] == 3
    assert row["attending_count"] == 0
    assert row["choir_count"] == 0
    assert row["display_label"] == "Famille Duval"
    assert row["responded_at"] is None


def test_dates_are_serialised_for_the_dashboard(api, single):
    api.answer(single["key"], [{"id": single["guests"][0]["id"], "attending": True}])
    row = api.responses().json()[0]
    assert isinstance(row["responded_at"], str)
    assert isinstance(row["created_at"], str)


# ── Editing ───────────────────────────────────────────────────────────────────

def test_renaming_keeps_the_answers_in_place(api, family):
    ids = [g["id"] for g in family["guests"]]
    api.answer(family["key"], [
        {"id": ids[0], "attending": True, "diet": "vegan", "allergies": "nuts", "choir": True},
    ])

    res = api.edit(family["key"], guest_names=["Paul Duval-Martin", "Sophie Duval", "Léa Duval"])
    assert res.status_code == 200
    paul = res.json()["guests"][0]
    assert paul["name"] == "Paul Duval-Martin"
    assert (paul["diet"], paul["allergies"], paul["choir"]) == ("vegan", "nuts", True)


def test_adding_a_person_to_a_household(api, family):
    invite = api.edit(family["key"], guest_names=[g["name"] for g in family["guests"]] + ["Bébé Duval"]).json()
    assert invite["invited_count"] == 4
    assert invite["guests"][-1]["name"] == "Bébé Duval"


def test_changing_type_must_still_fit_the_names(api, family):
    res = api.edit(family["key"], invite_type="single")
    assert res.status_code == 400

    ok = api.edit(family["key"], invite_type="couple", guest_names=["Paul Duval", "Sophie Duval"])
    assert ok.status_code == 200
    assert ok.json()["invite_type"] == "couple"


def test_lowering_the_extra_allowance_drops_surplus_guests(api, family):
    ids = [g["id"] for g in family["guests"]]
    api.answer(family["key"], [
        {"id": ids[0], "attending": True},
        {"id": None, "name": "Mamie", "attending": True},
        {"id": None, "name": "Papi", "attending": True},
    ])
    assert len(api.invite(family["key"]).json()["guests"]) == 5

    invite = api.edit(family["key"], extra_guests_allowed=0).json()
    assert [g["source"] for g in invite["guests"]] == ["host"] * 3


def test_clearing_the_label_falls_back_to_the_names(api, family):
    invite = api.edit(family["key"], label="").json()
    assert invite["label"] == ""
    assert invite["display_label"] == "Paul Duval, Sophie Duval & Léa Duval"


def test_editing_an_unknown_invitation(api):
    assert api.edit("NOSUCH99", label="x").status_code == 404


# ── Deleting ──────────────────────────────────────────────────────────────────

def test_delete_removes_the_invitation_once(api, single, collection):
    assert api.delete(single["key"]).status_code == 200
    assert collection.count_documents({}) == 0
    assert api.delete(single["key"]).status_code == 404
    assert api.invite(single["key"]).status_code == 404
