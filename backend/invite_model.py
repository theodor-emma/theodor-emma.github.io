"""Shape of an invitation document, shared by the API, the seed and the migration.

One invitation (one code) covers one or more people:

  single    one named person
  couple    two named people
  plus_one  one named person who may bring one companion they name themselves
  family    a household of named people, optionally allowed to add a few more
            (children, partners) themselves

Every person carries their own answer: attending, diet, allergies and whether
they would like to sing in the church choir.
"""

from datetime import datetime, timezone
import secrets

# Unambiguous alphabet — excludes easily confused characters (I, L, O, 0, 1)
KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

INVITE_TYPES = ("single", "couple", "plus_one", "family")
DIETS = ("none", "vegetarian", "vegan")
LANGUAGES = ("en", "fr", "ro")

# How many people the host names, per invitation type: (min, max)
TYPE_GUEST_RANGE = {
    "single":   (1, 1),
    "couple":   (2, 2),
    "plus_one": (1, 1),
    "family":   (1, 12),
}

# How many people the guests may add themselves, per type: (min, max)
TYPE_EXTRA_RANGE = {
    "single":   (0, 0),
    "couple":   (0, 0),
    "plus_one": (1, 1),
    "family":   (0, 8),
}

MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 160
MAX_LABEL_LEN = 120
MAX_ALLERGIES_LEN = 200
MAX_NOTES_LEN = 1000
MAX_GUESTS = 20


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


# ── Construction ──────────────────────────────────────────────────────────────


def new_guest(name: str, source: str = "host") -> dict:
    return {
        "id":        gen_guest_id(),
        "name":      (name or "").strip()[:MAX_NAME_LEN],
        "source":    source if source in ("host", "guest") else "host",
        "attending": None,
        "diet":      "none",
        "allergies": "",
        "choir":     False,
    }


def clamp_extra(invite_type: str, requested) -> int:
    lo, hi = TYPE_EXTRA_RANGE.get(invite_type, (0, 0))
    if requested is None:
        return lo
    try:
        return max(lo, min(hi, int(requested)))
    except (TypeError, ValueError):
        return lo


def new_invite(
    invite_type: str,
    guest_names: list,
    label: str = "",
    extra_guests_allowed=None,
    language: str = "en",
    key: str = "",
    email: str = "",
) -> dict:
    invite_type = invite_type if invite_type in INVITE_TYPES else "single"
    names = [n.strip() for n in guest_names if (n or "").strip()]
    return {
        "key":                  key or gen_key(),
        "invite_type":          invite_type,
        "label":                (label or "").strip()[:MAX_LABEL_LEN],
        "language":             language if language in LANGUAGES else "en",
        "email":                clean_email(email),
        "guests":               [new_guest(n) for n in names],
        "extra_guests_allowed": clamp_extra(invite_type, extra_guests_allowed),
        "notes":                "",
        "responded_at":         None,
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
    attending = raw.get("attending")
    guest["attending"] = attending if isinstance(attending, bool) else None
    diet = raw.get("diet")
    guest["diet"] = diet if diet in DIETS else "none"
    guest["allergies"] = str(raw.get("allergies") or "")[:MAX_ALLERGIES_LEN]
    guest["choir"] = raw.get("choir") is True
    return guest


def normalize_invite(doc: dict) -> dict:
    """Return `doc` in the current shape, converting the pre-group format if needed."""
    if not doc:
        return doc

    if isinstance(doc.get("guests"), list):
        invite_type = doc.get("invite_type")
        invite_type = invite_type if invite_type in INVITE_TYPES else "single"
        out = {
            "key":                  doc.get("key", ""),
            "invite_type":          invite_type,
            "label":                str(doc.get("label") or "")[:MAX_LABEL_LEN],
            "language":             doc["language"] if doc.get("language") in LANGUAGES else "en",
            "email":                clean_email(doc.get("email", "")),
            "guests":               [_normalize_guest(g, i) for i, g in enumerate(doc["guests"])],
            "extra_guests_allowed": clamp_extra(invite_type, doc.get("extra_guests_allowed")),
            "notes":                str(doc.get("notes") or "")[:MAX_NOTES_LEN],
            "responded_at":         doc.get("responded_at"),
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
        "invite_type":          "plus_one" if had_plus_one else "single",
        "label":                "",
        "language":             "en",
        "email":                clean_email(doc.get("email", "")),
        "guests":               guests,
        "extra_guests_allowed": 1 if had_plus_one else 0,
        "notes":                str(doc.get("notes") or "")[:MAX_NOTES_LEN],
        "responded_at":         doc.get("responded_at"),
        "created_at":           doc.get("created_at"),
    }


# ── Derived values ────────────────────────────────────────────────────────────


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
    if len(names) == 1:
        return names[0]
    return " & ".join([", ".join(names[:-1]), names[-1]])


def responded(invite: dict) -> bool:
    return invite.get("responded_at") is not None


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
        "invite_type":          invite["invite_type"],
        "label":                display_label(invite),
        "language":             invite["language"],
        "responded":            responded(invite),
        "notes":                invite["notes"],
        "extra_guests_allowed": invite["extra_guests_allowed"],
        "guests": [
            {
                "id":        g["id"],
                "name":      g["name"],
                "source":    g["source"],
                "attending": g["attending"],
                "diet":      g["diet"],
                "allergies": g["allergies"],
                "choir":     g["choir"],
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
        "invite_type":          invite["invite_type"],
        "label":                invite["label"],
        "display_label":        display_label(invite),
        "language":             invite["language"],
        "email":                invite["email"],
        "guests":               guests,
        "extra_guests_allowed": invite["extra_guests_allowed"],
        "notes":                invite["notes"],
        "responded":            responded(invite),
        "attending":            invite_attending(invite),
        "invited_count":        len([g for g in guests if g["source"] == "host"]),
        "attending_count":      len(attending),
        "choir_count":          len([g for g in attending if g.get("choir")]),
        "responded_at":         _iso(invite.get("responded_at")),
        "created_at":           _iso(invite.get("created_at")),
    }
