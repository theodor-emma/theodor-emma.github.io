"""Shape of an invitation document, shared by the API, the seed and the migration.

One invitation (one code) is a list of people, each with a name and whether
they are a child (12 or younger), plus who else they may bring: either a fixed
number of guests (usually a +1), or "their children" when `extras_are_children`
is set and the children are not known. That covers everyone: a person alone, a
person with a +1 (also a couple where only one name is known), a couple, or a
family with or without known names.

Every person carries their own answer: attending, diet, allergies, whether
they would like to sing in the church choir, whether they will come to the
Sunday brunch and, on invitations with `pizza_party_invited`, to the Friday
pizza party.

An invitation also remembers when it was first opened, first submitted and last
submitted, and keeps a bounded `history` of what changed. The history stores only
the differences in the fields listed below, so it can never contain itself.
"""

from datetime import datetime, timezone
import secrets

# Codes are read from paper and retyped, so of each group of look-alikes only one
# character is ever generated. Older codes used a wider alphabet and stay valid.
KEY_ALPHABET = "ABCDEFGHJKMNPRSTVWXYZ3479"

# What someone may type by mistake → the character it must have been
KEY_LOOKALIKES = str.maketrans({
    "0": "D", "O": "D", "Q": "D",
    "1": "J", "I": "J", "L": "J",
    "2": "Z",
    "5": "S",
    "6": "G",
    "8": "B",
    "U": "V",
})

DIETS = ("none", "vegetarian", "vegan")
LANGUAGES = ("en", "fr", "ro")

MAX_NAMED_GUESTS = 12    # people the hosts name on one invitation
MAX_EXTRA_GUESTS = 8     # people the invitees may add themselves
MAX_RSVP_TEXT_LEN = 99   # any text a guest sends through the RSVP API, except the notes
MAX_NOTES_LEN = 19_999   # the guests' special instructions
MAX_NAME_LEN = MAX_RSVP_TEXT_LEN   # guests may correct their name, so the limits must agree
MAX_EMAIL_LEN = 160
MAX_LABEL_LEN = 120
MAX_ALLERGIES_LEN = 200  # replies saved before the RSVP limit may be longer
MAX_GUESTS = 20
MAX_HISTORY = 100        # most recent changes kept per invitation

# What the history tracks. Timestamps and the history itself are left out on purpose.
TRACKED_INVITE_FIELDS = (
    "label", "language", "email", "responsible",
    "extra_guests_allowed", "extras_are_children", "pizza_party_invited", "notes",
)
TRACKED_GUEST_FIELDS = (
    "name", "source", "is_child", "attending", "diet", "allergies", "choir", "brunch", "pizza_party",
)


def gen_key(n: int = 8) -> str:
    return "".join(secrets.choice(KEY_ALPHABET) for _ in range(n))


def gen_guest_id() -> str:
    return "g" + secrets.token_hex(4)


def clean_email(email: str) -> str:
    """Trim an address; empty when it could not plausibly be one."""
    value = (email or "").strip()
    if not value:
        return ""
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain or any(c.isspace() for c in value):
        return ""
    return value[:MAX_EMAIL_LEN]


def clean_key(key: str) -> str:
    """Codes are printed in uppercase; accept sloppy typing (case, spaces, dashes).

    Anything alphanumeric is kept as typed — dropping stray letters instead would
    silently turn a mistyped code into a different, valid-looking one.
    """
    return "".join(c for c in (key or "").upper() if c.isascii() and c.isalnum())


def canonical_key(key: str) -> str:
    """The code as generated, once look-alike characters are corrected."""
    return clean_key(key).translate(KEY_LOOKALIKES)


# ── Construction ──────────────────────────────────────────────────────────────


def new_guest(name: str, source: str = "host", is_child: bool = False) -> dict:
    return {
        "id":        gen_guest_id(),
        "name":      (name or "").strip()[:MAX_NAME_LEN],
        "source":    source if source in ("host", "guest") else "host",
        "is_child":  is_child is True,
        "attending": None,
        "diet":      "none",
        "allergies": "",
        "choir":     False,
        "brunch":    False,
        "pizza_party": False,
    }


def clamp_extra(requested) -> int:
    if requested is None:
        return 0
    try:
        return max(0, min(MAX_EXTRA_GUESTS, int(requested)))
    except (TypeError, ValueError):
        return 0


def new_invite(
    guests: list,
    label: str = "",
    extra_guests_allowed=None,
    language: str = "en",
    key: str = "",
    email: str = "",
    extras_are_children: bool = False,
    responsible: str = "",
    pizza_party_invited: bool = False,
) -> dict:
    """`guests` is a list of (name, is_child) pairs."""
    people = [(name.strip(), is_child) for name, is_child in guests if (name or "").strip()]
    return {
        "key":                  key or gen_key(),
        "label":                (label or "").strip()[:MAX_LABEL_LEN],
        "language":             language if language in LANGUAGES else "en",
        "email":                clean_email(email),
        "responsible":          (responsible or "").strip()[:MAX_NAME_LEN],
        "guests":               [new_guest(name, is_child=is_child) for name, is_child in people],
        "extra_guests_allowed": MAX_EXTRA_GUESTS if extras_are_children
                                else clamp_extra(extra_guests_allowed),
        "extras_are_children":  extras_are_children,
        "pizza_party_invited":  pizza_party_invited,
        "notes":                "",
        "first_opened_at":      None,
        "first_submitted_at":   None,
        "last_submitted_at":    None,
        "history":              [],
        "created_at":           datetime.now(timezone.utc),
    }


# ── Normalisation (tolerates older documents) ─────────────────────────────────

_LEGACY_DIET_HINTS = (
    ("vegan",       "vegan"),
    ("végétalien",  "vegan"),
    ("vegetarian",  "vegetarian"),
    ("végétarien",  "vegetarian"),
)


def _split_legacy_dietary(text: str):
    """Legacy free-text dietary strings → (diet, leftover allergies text)."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    diet, rest = "none", []
    for part in parts:
        low = part.lower()
        matched = next((d for hint, d in _LEGACY_DIET_HINTS if hint in low), None)
        if matched and diet == "none":
            diet = matched
        elif matched:
            pass  # already captured a diet; a second one adds nothing
        else:
            rest.append(part)
    return diet, ", ".join(rest)[:MAX_ALLERGIES_LEN]


def _normalize_guest(raw: dict, index: int) -> dict:
    guest = new_guest(raw.get("name", ""), raw.get("source", "host"))
    # Positional fallback, never a fresh random id: the RSVP page sends these ids
    # back and they must survive being normalised twice.
    guest["id"] = raw.get("id") or f"g{index}"
    guest["is_child"] = raw.get("is_child") is True
    attending = raw.get("attending")
    guest["attending"] = attending if isinstance(attending, bool) else None
    diet = raw.get("diet")
    guest["diet"] = diet if diet in DIETS else "none"
    guest["allergies"] = str(raw.get("allergies") or "")[:MAX_ALLERGIES_LEN]
    guest["choir"] = raw.get("choir") is True
    guest["brunch"] = raw.get("brunch") is True
    guest["pizza_party"] = raw.get("pizza_party") is True
    return guest


def _tracking(doc: dict) -> dict:
    """Timestamps and history. `responded_at` is the older name of the last submission."""
    last = doc.get("last_submitted_at") or doc.get("responded_at")
    history = doc.get("history")
    history = history if isinstance(history, list) else []
    return {
        "first_opened_at":    doc.get("first_opened_at"),
        # For older replies the first submission is unknown: the last is the earliest we have
        "first_submitted_at": doc.get("first_submitted_at") or last,
        "last_submitted_at":  last,
        "history":            [e for e in history if isinstance(e, dict)][-MAX_HISTORY:],
    }


def _stored_extra(doc: dict) -> int:
    """Invitations saved with a type keep the allowance that type gave them."""
    if doc.get("extras_are_children") is True:
        return MAX_EXTRA_GUESTS     # however many children there turn out to be
    invite_type = doc.get("invite_type")
    if invite_type is None or invite_type == "family":
        return clamp_extra(doc.get("extra_guests_allowed"))
    return 1 if invite_type == "plus_one" else 0


def normalize_invite(doc: dict) -> dict:
    """Return `doc` in the current shape, converting the pre-group format if needed."""
    if not doc:
        return doc

    if isinstance(doc.get("guests"), list):
        out = {
            "key":                  doc.get("key", ""),
            "label":                str(doc.get("label") or "")[:MAX_LABEL_LEN],
            "language":             doc["language"] if doc.get("language") in LANGUAGES else "en",
            "email":                clean_email(doc.get("email", "")),
            "responsible":          str(doc.get("responsible") or "")[:MAX_NAME_LEN],
            "guests":               [_normalize_guest(g, i) for i, g in enumerate(doc["guests"])],
            "extra_guests_allowed": _stored_extra(doc),
            "extras_are_children":  doc.get("extras_are_children") is True,
            "pizza_party_invited":  doc.get("pizza_party_invited") is True,
            "notes":                str(doc.get("notes") or "")[:MAX_NOTES_LEN],
            **_tracking(doc),
            "created_at":           doc.get("created_at"),
        }
        return out

    # ── Legacy: one row per invitation, with an optional +1 ──
    diet, allergies = _split_legacy_dietary(doc.get("dietary_restrictions", ""))
    main = new_guest(doc.get("name", ""))
    main["id"] = "g0"
    main["attending"] = doc["attending"] if isinstance(doc.get("attending"), bool) else None
    main["diet"] = diet
    main["allergies"] = allergies

    guests = [main]
    had_plus_one = bool(doc.get("plus_one"))
    if had_plus_one:
        p_diet, p_allergies = _split_legacy_dietary(doc.get("plus_one_dietary", ""))
        companion = new_guest(doc.get("plus_one_name") or "", source="guest")
        companion["id"] = "g1"
        companion["attending"] = True
        companion["diet"] = p_diet
        companion["allergies"] = p_allergies
        guests.append(companion)

    return {
        "key":                  doc.get("key", ""),
        "label":                "",
        "language":             "en",
        "email":                clean_email(doc.get("email", "")),
        "responsible":          str(doc.get("responsible") or "")[:MAX_NAME_LEN],
        "guests":               guests,
        "extra_guests_allowed": 1 if had_plus_one else 0,
        "extras_are_children":  False,
        "pizza_party_invited":  False,
        "notes":                str(doc.get("notes") or "")[:MAX_NOTES_LEN],
        **_tracking(doc),
        "created_at":           doc.get("created_at"),
    }


# ── History ───────────────────────────────────────────────────────────────────


def _guest_snapshot(guest: dict) -> dict:
    return {field: guest.get(field) for field in TRACKED_GUEST_FIELDS}


def invite_changes(before: dict, after: dict) -> list:
    """What differs between two versions of an invitation, field by field."""
    changes = [
        {"field": field, "from": before.get(field), "to": after.get(field)}
        for field in TRACKED_INVITE_FIELDS
        if before.get(field) != after.get(field)
    ]

    old = {g["id"]: g for g in before.get("guests", [])}
    new = {g["id"]: g for g in after.get("guests", [])}

    def change(guest: dict, field: str, was, now) -> dict:
        return {"guest_id": guest["id"], "guest_name": guest.get("name", ""),
                "field": field, "from": was, "to": now}

    for guest_id, guest in old.items():
        if guest_id not in new:
            changes.append(change(guest, "guest", _guest_snapshot(guest), None))
    for guest_id, guest in new.items():
        if guest_id not in old:
            changes.append(change(guest, "guest", None, _guest_snapshot(guest)))
            continue
        for field in TRACKED_GUEST_FIELDS:
            if old[guest_id].get(field) != guest.get(field):
                changes.append(change(guest, field, old[guest_id].get(field), guest.get(field)))
    return changes


# ── Derived values ────────────────────────────────────────────────────────────


def _list_names(names: list) -> str:
    if len(names) == 1:
        return names[0]
    return " & ".join([", ".join(names[:-1]), names[-1]])


def _address_names(names: list) -> str:
    """Join names, giving a surname everyone shares only once: "Jean & Claire Martin"."""
    words = [name.split() for name in names]
    shared = 0
    if len(words) > 1:
        # Everyone keeps at least one word of their own
        limit = min(len(w) for w in words) - 1
        while shared < limit and len({w[-1 - shared].casefold() for w in words}) == 1:
            shared += 1
    if not shared:
        return _list_names(names)
    first_names = [" ".join(w[:-shared]) for w in words]
    return _list_names(first_names) + " " + " ".join(words[0][-shared:])


def display_label(invite: dict) -> str:
    """What to address the invitation to."""
    if invite.get("label"):
        return invite["label"]
    # Only the people the hosts named — guest-added companions are not addressees
    names = [
        g["name"]
        for g in invite.get("guests", [])
        if g.get("name") and g.get("source") == "host"
    ]
    if not names:
        return "Guest"
    return _address_names(names)


def responded(invite: dict) -> bool:
    return invite.get("last_submitted_at") is not None


def attending_guests(invite: dict) -> list:
    return [g for g in invite.get("guests", []) if g.get("attending") is True]


def invite_attending(invite: dict):
    """True / False / None (no answer yet) for the invitation as a whole."""
    if not responded(invite):
        return None
    return len(attending_guests(invite)) > 0


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def public_invite(invite: dict) -> dict:
    """What the RSVP page is allowed to see (also used to prefill the form)."""
    return {
        "key":                  invite["key"],
        "label":                display_label(invite),
        "language":             invite["language"],
        "responded":            responded(invite),
        "notes":                invite["notes"],
        "extra_guests_allowed": invite["extra_guests_allowed"],
        "extras_are_children":  invite["extras_are_children"],
        "pizza_party_invited":  invite["pizza_party_invited"],
        "guests": [
            {
                "id":        g["id"],
                "name":      g["name"],
                "source":    g["source"],
                "is_child":  g["is_child"],
                "attending": g["attending"],
                "diet":      g["diet"],
                "allergies": g["allergies"],
                "choir":     g["choir"],
                "brunch":    g["brunch"],
                "pizza_party": g["pizza_party"],
            }
            for g in invite["guests"]
        ],
    }


def admin_invite(invite: dict) -> dict:
    """Invitation plus the counts the dashboard shows."""
    guests = invite["guests"]
    attending = attending_guests(invite)
    return {
        "key":                  invite["key"],
        "label":                invite["label"],
        "display_label":        display_label(invite),
        "language":             invite["language"],
        "email":                invite["email"],
        "responsible":          invite["responsible"],
        "guests":               guests,
        "extra_guests_allowed": invite["extra_guests_allowed"],
        "extras_are_children":  invite["extras_are_children"],
        "pizza_party_invited":  invite["pizza_party_invited"],
        "notes":                invite["notes"],
        "responded":            responded(invite),
        "attending":            invite_attending(invite),
        "invited_count":        len([g for g in guests if g["source"] == "host"]),
        "attending_count":      len(attending),
        "children_count":       len([g for g in attending if g.get("is_child")]),
        "choir_count":          len([g for g in attending if g.get("choir")]),
        "brunch_count":         len([g for g in attending if g.get("brunch")]),
        "pizza_party_count":    len([g for g in attending if g.get("pizza_party")]),
        "first_opened_at":      _iso(invite.get("first_opened_at")),
        "first_submitted_at":   _iso(invite.get("first_submitted_at")),
        "last_submitted_at":    _iso(invite.get("last_submitted_at")),
        "history_count":        len(invite.get("history", [])),
        "created_at":           _iso(invite.get("created_at")),
    }
