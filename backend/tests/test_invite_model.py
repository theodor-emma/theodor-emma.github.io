"""The invitation document itself: construction, derived values, old formats."""

import invite_model as m


def people(*names):
    return [(name, False) for name in names]


# ── Codes ─────────────────────────────────────────────────────────────────────

def test_generated_keys_avoid_confusable_characters():
    keys = [m.gen_key() for _ in range(200)]
    assert all(len(k) == 8 for k in keys)
    assert not set("".join(keys)) & set("ILO01QU2568")
    assert len(set(keys)) > 190  # not a constant, and collisions are rare


def test_clean_key_forgives_how_people_type():
    assert m.clean_key(" abc2-3xyz ") == "ABC23XYZ"
    assert m.clean_key("ABC 23 XYZ") == "ABC23XYZ"
    assert m.clean_key(None) == ""


def test_clean_key_keeps_stray_letters_rather_than_shifting_the_code():
    # Dropping the L would silently turn a typo into a different, valid-looking code
    assert m.clean_key("legacy99") == "LEGACY99"


def test_look_alikes_are_mapped_to_the_character_that_exists():
    assert m.canonical_key("o0q-1il-2568u") == "DDDJJJZSGBV"
    assert set(m.canonical_key(m.gen_key())) <= set(m.KEY_ALPHABET)
    assert all(c not in m.KEY_ALPHABET for c in "01OIL")


# ── Construction ──────────────────────────────────────────────────────────────

def test_new_invite_shapes_a_family():
    invite = m.new_invite([("Paul", False), ("Léa", True)], label="Famille Duval",
                          extra_guests_allowed=2, language="fr")
    assert [(g["name"], g["is_child"]) for g in invite["guests"]] == [("Paul", False), ("Léa", True)]
    assert "invite_type" not in invite
    assert all(g["source"] == "host" for g in invite["guests"])
    assert all(g["attending"] is None and g["diet"] == "none" and g["choir"] is False
               for g in invite["guests"])
    assert invite["extra_guests_allowed"] == 2
    assert invite["last_submitted_at"] is None
    assert invite["first_opened_at"] is None and invite["history"] == []


def test_new_invite_falls_back_to_known_values():
    invite = m.new_invite(people("  Solo  ", "   "), language="klingon")
    assert invite["language"] == "en"
    assert [g["name"] for g in invite["guests"]] == ["Solo"]


def test_clamp_extra_keeps_the_allowance_in_range():
    assert m.clamp_extra(99) == m.MAX_EXTRA_GUESTS
    assert m.clamp_extra(-1) == 0
    assert m.clamp_extra(None) == 0
    assert m.clamp_extra("two") == 0


# ── Derived values ────────────────────────────────────────────────────────────

def test_display_label_prefers_the_label_then_the_names():
    assert m.display_label(m.new_invite(people("A", "B"), label="Famille X")) == "Famille X"
    assert m.display_label(m.new_invite(people("Jean Martin", "Claire Martin"))) \
        == "Jean & Claire Martin"
    assert m.display_label(m.new_invite(people("A", "B", "C"))) == "A, B & C"


def test_a_shared_surname_is_written_once():
    def label(*names):
        return m.display_label(m.new_invite(people(*names)))

    assert label("Paul Duval", "Sophie Duval", "Léa Duval") == "Paul, Sophie & Léa Duval"
    assert label("Anne-Sophie de Mullot de Villenaut", "Mathieu de Mullot de Villenaut") \
        == "Anne-Sophie & Mathieu de Mullot de Villenaut"
    assert label("Jean MARTIN", "Claire Martin") == "Jean & Claire MARTIN"


def test_different_or_missing_surnames_are_kept_in_full():
    def label(*names):
        return m.display_label(m.new_invite(people(*names)))

    assert label("Ana Comorasu", "Adrian Butnar") == "Ana Comorasu & Adrian Butnar"
    assert label("Jean Martin", "Claire Martin", "Léa Dupont") == "Jean Martin, Claire Martin & Léa Dupont"
    assert label("Martin", "Claire Martin") == "Martin & Claire Martin"
    assert label("Solo Martin") == "Solo Martin"


def test_display_label_ignores_guests_the_invitees_added():
    invite = m.new_invite(people("Alex"), extra_guests_allowed=1)
    invite["guests"].append(m.new_guest("Companion", source="guest"))
    assert m.display_label(invite) == "Alex"


def test_counts_only_add_up_after_a_reply():
    invite = m.new_invite([("A", False), ("B", True)])
    assert m.invite_attending(invite) is None
    view = m.admin_invite(invite)
    assert (view["invited_count"], view["attending_count"], view["choir_count"]) == (2, 0, 0)

    invite["last_submitted_at"] = "now"
    invite["guests"][0].update(attending=True, choir=True)
    invite["guests"][1]["attending"] = False
    assert m.invite_attending(invite) is True
    view = m.admin_invite(invite)
    assert (view["invited_count"], view["attending_count"], view["choir_count"]) == (2, 1, 1)
    assert view["children_count"] == 0

    invite["guests"][1]["attending"] = True
    assert m.admin_invite(invite)["children_count"] == 1


def test_public_invite_hides_bookkeeping():
    invite = m.new_invite(people("Solo"))
    public = m.public_invite(invite)
    assert set(public) == {"key", "label", "language", "responded", "notes",
                           "extra_guests_allowed", "extras_are_children",
                           "pizza_party_invited", "guests"}
    assert set(public["guests"][0]) == {"id", "name", "source", "is_child", "attending",
                                        "diet", "allergies", "choir", "brunch", "pizza_party"}


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
    assert [g["name"] for g in invite["guests"]] == ["Old Guest", "Companion"]
    assert not any(g["is_child"] for g in invite["guests"])
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
    assert "invite_type" not in invite
    assert invite["language"] == "en"
    assert invite["extra_guests_allowed"] == 0
    guest = invite["guests"][0]
    assert (guest["diet"], guest["attending"], guest["source"]) == ("none", None, "host")


def test_invitations_saved_with_a_type_keep_their_allowance():
    def extra(invite_type, stored):
        doc = {"key": "K", "invite_type": invite_type, "extra_guests_allowed": stored,
               "guests": [{"name": "A"}]}
        return m.normalize_invite(doc)["extra_guests_allowed"]

    assert extra("single", 3) == 0
    assert extra("couple", 3) == 0
    assert extra("plus_one", 0) == 1
    assert extra("family", 3) == 3


def test_people_saved_before_the_child_flag_are_adults():
    doc = {"key": "K", "extra_guests_allowed": 0, "guests": [{"name": "A"}]}
    assert m.normalize_invite(doc)["guests"][0]["is_child"] is False


def test_an_older_reply_keeps_its_date():
    doc = {"key": "K", "responded_at": "then", "guests": [{"name": "A"}]}
    invite = m.normalize_invite(doc)
    assert invite["last_submitted_at"] == invite["first_submitted_at"] == "then"
    assert m.responded(invite)


def test_changes_cover_only_the_tracked_fields():
    before = m.new_invite(people("A"))
    after = {**before, "notes": "hi", "history": [{"at": "x"}], "last_submitted_at": "now",
             "first_opened_at": "now", "guests": [{**before["guests"][0], "diet": "vegan"}]}
    changes = m.invite_changes(before, after)
    assert [c["field"] for c in changes] == ["notes", "diet"]
    assert "history" not in str(changes)
