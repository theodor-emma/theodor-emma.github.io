"""The invitation document itself: construction, derived values, old formats."""

import invite_model as m


# ── Codes ─────────────────────────────────────────────────────────────────────

def test_generated_keys_avoid_confusable_characters():
    keys = [m.gen_key() for _ in range(200)]
    assert all(len(k) == 8 for k in keys)
    assert not set("".join(keys)) & set("ILO01")
    assert len(set(keys)) > 190  # not a constant, and collisions are rare


def test_clean_key_forgives_how_people_type():
    assert m.clean_key(" abc2-3xyz ") == "ABC23XYZ"
    assert m.clean_key("ABC 23 XYZ") == "ABC23XYZ"
    assert m.clean_key(None) == ""


def test_clean_key_keeps_stray_letters_rather_than_shifting_the_code():
    # Dropping the L would silently turn a typo into a different, valid-looking code
    assert m.clean_key("legacy99") == "LEGACY99"


# ── Construction ──────────────────────────────────────────────────────────────

def test_new_invite_shapes_a_family():
    invite = m.new_invite("family", ["Paul", "Sophie"], label="Famille Duval",
                          extra_guests_allowed=2, language="fr")
    assert invite["invite_type"] == "family"
    assert [g["name"] for g in invite["guests"]] == ["Paul", "Sophie"]
    assert all(g["source"] == "host" for g in invite["guests"])
    assert all(g["attending"] is None and g["diet"] == "none" and g["choir"] is False
               for g in invite["guests"])
    assert invite["extra_guests_allowed"] == 2
    assert invite["responded_at"] is None


def test_new_invite_falls_back_to_known_values():
    invite = m.new_invite("nonsense", ["  Solo  "], language="klingon")
    assert invite["invite_type"] == "single"
    assert invite["language"] == "en"
    assert invite["guests"][0]["name"] == "Solo"


def test_clamp_extra_respects_each_type():
    assert m.clamp_extra("single", 5) == 0        # nobody to add
    assert m.clamp_extra("plus_one", 0) == 1      # always exactly one companion
    assert m.clamp_extra("family", 99) == 8       # capped
    assert m.clamp_extra("family", None) == 0
    assert m.clamp_extra("family", "two") == 0    # unparsable


# ── Derived values ────────────────────────────────────────────────────────────

def test_display_label_prefers_the_label_then_the_names():
    assert m.display_label(m.new_invite("family", ["A", "B"], label="Famille X")) == "Famille X"
    assert m.display_label(m.new_invite("couple", ["Jean Martin", "Claire Martin"])) \
        == "Jean Martin & Claire Martin"
    assert m.display_label(m.new_invite("family", ["A", "B", "C"])) == "A, B & C"


def test_display_label_ignores_guests_the_invitees_added():
    invite = m.new_invite("plus_one", ["Alex"], extra_guests_allowed=1)
    invite["guests"].append(m.new_guest("Companion", source="guest"))
    assert m.display_label(invite) == "Alex"


def test_counts_only_add_up_after_a_reply():
    invite = m.new_invite("couple", ["A", "B"])
    assert m.invite_attending(invite) is None
    view = m.admin_invite(invite)
    assert (view["invited_count"], view["attending_count"], view["choir_count"]) == (2, 0, 0)

    invite["responded_at"] = "now"
    invite["guests"][0].update(attending=True, choir=True)
    invite["guests"][1]["attending"] = False
    assert m.invite_attending(invite) is True
    view = m.admin_invite(invite)
    assert (view["invited_count"], view["attending_count"], view["choir_count"]) == (2, 1, 1)


def test_public_invite_hides_bookkeeping():
    invite = m.new_invite("single", ["Solo"])
    public = m.public_invite(invite)
    assert set(public) == {"key", "invite_type", "label", "language", "responded",
                           "notes", "extra_guests_allowed", "guests"}
    assert set(public["guests"][0]) == {"id", "name", "source", "attending",
                                        "diet", "allergies", "choir"}


# ── Old documents ─────────────────────────────────────────────────────────────

LEGACY = {
    "key": "OLDKEY22",
    "name": "Old Guest",
    "attending": True,
    "dietary_restrictions": "Végétarien, Allergie aux noix",
    "notes": "see you there",
    "plus_one": True,
    "plus_one_name": "Companion",
    "plus_one_dietary": "Vegan",
    "responded_at": None,
}


def test_legacy_document_becomes_a_guest_list():
    invite = m.normalize_invite(LEGACY)
    assert invite["invite_type"] == "plus_one"
    assert [g["name"] for g in invite["guests"]] == ["Old Guest", "Companion"]
    assert invite["guests"][1]["source"] == "guest"
    assert invite["extra_guests_allowed"] == 1


def test_legacy_free_text_diet_splits_into_diet_and_allergies():
    guest = m.normalize_invite(LEGACY)["guests"][0]
    assert guest["diet"] == "vegetarian"
    assert guest["allergies"] == "Allergie aux noix"
    assert guest["choir"] is False


def test_normalising_twice_keeps_the_same_guest_ids():
    # The RSVP page sends these ids back; fresh ones would duplicate the person
    first = m.normalize_invite(LEGACY)
    second = m.normalize_invite(LEGACY)
    assert [g["id"] for g in first["guests"]] == [g["id"] for g in second["guests"]]
    assert m.normalize_invite(first)["guests"][0]["id"] == first["guests"][0]["id"]


def test_guests_without_ids_get_stable_ones():
    """A hand-edited or half-migrated document must not be renumbered on each read."""
    doc = {"key": "K", "invite_type": "couple",
           "guests": [{"name": "A"}, {"name": "B"}]}
    first = [g["id"] for g in m.normalize_invite(doc)["guests"]]
    second = [g["id"] for g in m.normalize_invite(doc)["guests"]]
    assert first == second
    assert len(set(first)) == 2


def test_normalise_repairs_unknown_values():
    invite = m.normalize_invite({
        "key": "K", "invite_type": "wedding-party", "language": "elvish",
        "extra_guests_allowed": 99,
        "guests": [{"name": "A", "diet": "sausages", "attending": "yes", "source": "cat"}],
    })
    assert invite["invite_type"] == "single"
    assert invite["language"] == "en"
    assert invite["extra_guests_allowed"] == 0
    guest = invite["guests"][0]
    assert (guest["diet"], guest["attending"], guest["source"]) == ("none", None, "host")
