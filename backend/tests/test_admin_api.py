"""Managing invitations: creating, listing, editing, deleting — and who may."""

import pytest

from conftest import ADMIN, added, adults, child


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

@pytest.mark.parametrize("guests,extra", [
    (adults("Solo"),                              0),   # one person
    (adults("Alex"),                              1),   # a person and a +1
    (adults("Jean", "Claire"),                    0),   # a couple
    (adults("Paul", "Sophie") + [child("Léa")],   0),   # a family, all named
    (adults("Paul", "Sophie"),                    3),   # a family, children unnamed
])
def test_create_each_kind_of_invitation(api, guests, extra):
    invite = api.new(guests=guests, extra_guests_allowed=extra)
    assert "invite_type" not in invite
    assert [{"name": g["name"], "is_child": g["is_child"]} for g in invite["guests"]] == guests
    assert invite["invited_count"] == len(guests)
    assert invite["extra_guests_allowed"] == extra
    assert invite["responded"] is False and invite["attending"] is None


@pytest.mark.parametrize("guests", [[], adults("   "), adults(*[f"P{i}" for i in range(13)])])
def test_an_invitation_needs_a_sensible_number_of_names(api, guests):
    res = api.create(guests=guests)
    assert res.status_code == 400
    assert "invitation needs" in res.json()["detail"]


@pytest.mark.parametrize("extra", [-1, 9])
def test_the_extra_allowance_must_be_in_range(api, extra):
    res = api.create(guests=adults("Solo"), extra_guests_allowed=extra)
    assert res.status_code == 400


def test_blank_names_are_dropped(api):
    invite = api.new(guests=adults("Jean", "   "))
    assert [g["name"] for g in invite["guests"]] == ["Jean"]


def test_and_your_children_needs_no_number(api):
    invite = api.new(guests=adults("Ana", "Paul"), extras_are_children=True)
    assert invite["extras_are_children"] is True
    assert invite["extra_guests_allowed"] == 8


def test_switching_between_children_and_a_number(api, single):
    invite = api.edit(single["key"], extras_are_children=True).json()
    assert (invite["extras_are_children"], invite["extra_guests_allowed"]) == (True, 8)
    invite = api.edit(single["key"], extras_are_children=False).json()
    assert (invite["extras_are_children"], invite["extra_guests_allowed"]) == (False, 0)
    invite = api.edit(single["key"], extras_are_children=False, extra_guests_allowed=1).json()
    assert invite["extra_guests_allowed"] == 1


def test_a_plain_name_still_works(api):
    """The quick-add shorthand the older admin page used."""
    invite = api.new(name="Marie Pichard")
    assert invite["display_label"] == "Marie Pichard"
    assert invite["guests"][0]["is_child"] is False


def test_each_invitation_gets_its_own_code(api):
    keys = {api.new(name=f"Guest {i}")["key"] for i in range(25)}
    assert len(keys) == 25


def test_a_created_invitation_is_written_to_the_database(api, collection):
    invite = api.new(guests=adults("A", "B"), label="Household")
    stored = api.stored(invite["key"])
    assert stored["label"] == "Household"
    assert [g["name"] for g in stored["guests"]] == ["A", "B"]
    assert collection.count_documents({}) == 1


def test_over_long_text_is_refused(api):
    res = api.create(guests=adults("N" * 200))
    assert res.status_code == 422


def test_the_rsvp_limits_do_not_apply_to_the_admin_fields(api):
    invite = api.new(name="Marie", label="L" * 120, email="e" * 140 + "@example.com")
    assert len(invite["label"]) == 120
    assert invite["email"].endswith("@example.com")


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


# ── Who is responsible ────────────────────────────────────────────────────────

def test_an_invitation_can_have_someone_responsible(api):
    invite = api.new(name="Marie", responsible="  Clotilde ")
    assert invite["responsible"] == "Clotilde"
    assert api.stored(invite["key"])["responsible"] == "Clotilde"


def test_who_is_responsible_can_change_and_is_kept_private(api, single):
    assert single["responsible"] == ""
    assert api.edit(single["key"], responsible="Sergiu").json()["responsible"] == "Sergiu"
    assert api.edit(single["key"], label="Marie").json()["responsible"] == "Sergiu"
    assert api.stored(single["key"])["history"][0]["changes"][0]["field"] == "responsible"
    assert "responsible" not in api.invite(single["key"]).json()


# ── Adding a whole list at once ───────────────────────────────────────────────

def test_a_pasted_list_becomes_invitations(api, collection):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={"invites": [
        {"guests": adults("Marie Pichard"), "email": "marie@example.com"},
        {"guests": adults("Jean Martin", "Claire Martin"), "language": "fr"},
        {"guests": adults("Alexandru Ionescu"), "language": "ro", "extra_guests_allowed": 1},
        {"guests": adults("Paul", "Sophie") + [child("Léa")],
         "label": "Famille Duval", "extra_guests_allowed": 2},
    ]})
    assert res.status_code == 200, res.text

    created = res.json()["created"]
    assert created[0]["email"] == "marie@example.com"
    assert created[2]["extra_guests_allowed"] == 1
    assert created[3]["display_label"] == "Famille Duval"
    assert created[3]["guests"][2]["is_child"] is True
    assert collection.count_documents({}) == 4
    assert len({c["key"] for c in created}) == 4


def test_one_bad_line_adds_nothing_at_all(api, collection):
    res = api.client.post("/admin/invites/bulk", params=ADMIN, json={"invites": [
        {"guests": adults("Fine")},
        {"guests": adults("Too many"), "extra_guests_allowed": 99},
        {"guests": []},
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
    assert row["children_count"] == 0
    assert row["display_label"] == "Famille Duval"
    assert row["last_submitted_at"] is None
    assert row["history_count"] == 0


def test_dates_are_serialised_for_the_dashboard(api, single):
    api.answer(single["key"], [{"id": single["guests"][0]["id"], "attending": True}])
    row = api.responses().json()[0]
    assert isinstance(row["last_submitted_at"], str)
    assert isinstance(row["first_submitted_at"], str)
    assert row["history_count"] == 1
    assert isinstance(row["created_at"], str)


# ── Editing ───────────────────────────────────────────────────────────────────

def test_renaming_keeps_the_answers_in_place(api, family):
    ids = [g["id"] for g in family["guests"]]
    api.answer(family["key"], [
        {"id": ids[0], "attending": True, "diet": "vegan", "allergies": "nuts", "choir": True},
    ])

    res = api.edit(family["key"], guests=adults("Paul Duval-Martin", "Sophie Duval") + [child("Léa Duval")])
    assert res.status_code == 200
    paul = res.json()["guests"][0]
    assert paul["name"] == "Paul Duval-Martin"
    assert (paul["diet"], paul["allergies"], paul["choir"]) == ("vegan", "nuts", True)


def test_adding_a_person_to_a_household(api, family):
    invite = api.edit(family["key"], guests=[
        {"name": g["name"], "is_child": g["is_child"]} for g in family["guests"]
    ] + [child("Bébé Duval")]).json()
    assert invite["invited_count"] == 4
    assert (invite["guests"][-1]["name"], invite["guests"][-1]["is_child"]) == ("Bébé Duval", True)


def test_someone_can_be_marked_as_a_child_later(api, family):
    invite = api.edit(family["key"], guests=[child("Paul Duval")] + adults("Sophie Duval")).json()
    assert [g["is_child"] for g in invite["guests"]] == [True, False]


def test_editing_cannot_leave_an_invitation_empty(api, family):
    assert api.edit(family["key"], guests=[]).status_code == 400


def test_editing_an_old_invitation_replaces_its_type(api, collection):
    collection.insert_one({"key": "OLDTYPE2", "invite_type": "single", "label": "", "language": "en",
                           "extra_guests_allowed": 0, "notes": "", "responded_at": None,
                           "guests": [{"id": "g0", "name": "Solo", "source": "host"}]})
    assert api.edit("OLDTYPE2", extra_guests_allowed=1).json()["extra_guests_allowed"] == 1
    assert "invite_type" not in api.stored("OLDTYPE2")
    assert api.invite("OLDTYPE2").json()["extra_guests_allowed"] == 1


def test_lowering_the_extra_allowance_drops_surplus_guests(api, family):
    ids = [g["id"] for g in family["guests"]]
    api.answer(family["key"], [
        {"id": ids[0], "attending": True},
        added("Mamie"),
        added("Papi"),
    ])
    assert len(api.invite(family["key"]).json()["guests"]) == 5

    invite = api.edit(family["key"], extra_guests_allowed=0).json()
    assert [g["source"] for g in invite["guests"]] == ["host"] * 3


def test_clearing_the_label_falls_back_to_the_names(api, family):
    invite = api.edit(family["key"], label="").json()
    assert invite["label"] == ""
    assert invite["display_label"] == "Paul, Sophie & Léa Duval"


def test_admin_edits_are_in_the_history(api, single):
    api.edit(single["key"], label="Marie", extra_guests_allowed=1)
    entry = api.stored(single["key"])["history"][-1]
    assert entry["by"] == "admin"
    assert {c["field"] for c in entry["changes"]} == {"label", "extra_guests_allowed"}


def test_removing_the_pizza_invitation_clears_the_answers(api):
    invite = api.new(guests=adults("Ana"), pizza_party_invited=True)
    api.answer(invite["key"], [{"id": invite["guests"][0]["id"], "attending": True, "pizza_party": True}])
    edited = api.edit(invite["key"], pizza_party_invited=False).json()
    assert edited["pizza_party_invited"] is False
    assert edited["guests"][0]["pizza_party"] is False


def test_editing_an_unknown_invitation(api):
    assert api.edit("NOSUCH99", label="x").status_code == 404


# ── Deleting ──────────────────────────────────────────────────────────────────

def test_delete_removes_the_invitation_once(api, single, collection):
    assert api.delete(single["key"]).status_code == 200
    assert collection.count_documents({}) == 0
    assert api.delete(single["key"]).status_code == 404
    assert api.invite(single["key"]).status_code == 404
