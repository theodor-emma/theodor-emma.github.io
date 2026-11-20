from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
from typing import Annotated, Optional, List
from dotenv import load_dotenv
import os
import secrets

from invite_model import (
    DIETS,
    LANGUAGES,
    MAX_EXTRA_GUESTS,
    MAX_GUESTS,
    MAX_EMAIL_LEN,
    MAX_HISTORY,
    MAX_LABEL_LEN,
    MAX_NAME_LEN,
    MAX_NAMED_GUESTS,
    MAX_NOTES_LEN,
    MAX_RSVP_TEXT_LEN,
    admin_invite,
    canonical_key,
    clean_email,
    clean_key,
    invite_changes,
    new_guest,
    new_invite,
    normalize_invite,
    public_invite,
)

from rate_limit import FailureLimiter

load_dotenv()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
if not ADMIN_SECRET:
    raise RuntimeError("ADMIN_SECRET must be defined and non-empty")

# How many invitations one paste may create
MAX_BULK = 200

app = FastAPI(title="Wedding RSVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────────────────────

client  = MongoClient(
    os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
    serverSelectionTimeoutMS=3000,  # fail fast instead of hanging ~30s
)
db      = client[os.getenv("MONGODB_DB", "wedding")]
invites = db["invites"]


@app.exception_handler(PyMongoError)
def mongo_error_handler(request: Request, exc: PyMongoError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable"},
    )

# ── Models ────────────────────────────────────────────────────────────────────

GuestName = Annotated[str, Field(max_length=MAX_NAME_LEN)]


class InvitedGuest(BaseModel):
    name:     GuestName
    is_child: bool = False


class NewInviteRequest(BaseModel):
    guests:               List[InvitedGuest] = Field(default_factory=list, max_length=MAX_GUESTS)
    label:                str = Field("", max_length=MAX_LABEL_LEN)
    language:             str = "en"
    extra_guests_allowed: int = 0
    # "And your children": no number to give, the allowance is the maximum
    extras_are_children:  bool = False
    pizza_party_invited:  bool = False
    email:                str = Field("", max_length=MAX_EMAIL_LEN)
    responsible:          str = Field("", max_length=MAX_NAME_LEN)
    # Shorthand for one adult
    name:                 Optional[str] = Field(None, max_length=MAX_NAME_LEN)


class EditInviteRequest(BaseModel):
    guests:               Optional[List[InvitedGuest]] = Field(None, max_length=MAX_GUESTS)
    label:                Optional[str] = Field(None, max_length=MAX_LABEL_LEN)
    language:             Optional[str] = None
    extra_guests_allowed: Optional[int] = None
    extras_are_children:  Optional[bool] = None
    pizza_party_invited:  Optional[bool] = None
    email:                Optional[str] = Field(None, max_length=MAX_EMAIL_LEN)
    responsible:          Optional[str] = Field(None, max_length=MAX_NAME_LEN)


class BulkInviteRequest(BaseModel):
    invites: List[NewInviteRequest] = Field(default_factory=list, max_length=MAX_BULK)


# ── What guests send: validated strictly ──

RsvpText = Annotated[str, Field(max_length=MAX_RSVP_TEXT_LEN)]
InviteKey = Annotated[str, Path(max_length=MAX_RSVP_TEXT_LEN)]


class StrictModel(BaseModel):
    """Wrong types and unknown fields are refused, never coerced or ignored."""
    model_config = ConfigDict(strict=True, extra="forbid")


class GuestAnswer(StrictModel):
    id:        Optional[RsvpText] = None
    name:      RsvpText = ""
    # Required for people the invitees add, including their own sons and daughters,
    # who may be adults; the hosts decide it for everyone else
    is_child:  Optional[bool] = None
    attending: bool = False
    diet:      RsvpText = "none"
    allergies: RsvpText = ""
    choir:     bool = False
    brunch:    bool = False
    pizza_party: bool = False


class RSVPRequest(StrictModel):
    guests: List[GuestAnswer] = Field(default_factory=list, max_length=MAX_GUESTS)
    notes:  str = Field("", max_length=MAX_NOTES_LEN)

# ── Helpers ───────────────────────────────────────────────────────────────────

def require_admin(admin_key: str) -> None:
    if not secrets.compare_digest(admin_key or "", ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


def load_invite(key: str) -> dict:
    cleaned = clean_key(key)
    # The exact code first: older codes may contain characters the map rewrites
    doc = invites.find_one({"key": cleaned}, {"_id": 0}) if cleaned else None
    if not doc and cleaned:
        doc = invites.find_one({"key": canonical_key(cleaned)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    return normalize_invite(doc)


# Unknown codes per IPv4 address: at most 10 a minute and 20 an hour
guess_limiter = FailureLimiter()


def guest_invite(key: str, request: Request) -> dict:
    """`load_invite` for the guest routes, which refuse an address guessing codes."""
    host = request.client.host if request.client else ""
    if guess_limiter.blocked(host):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait a few minutes and try again.",
        )
    try:
        return load_invite(key)
    except HTTPException as exc:
        if exc.status_code == 404:
            guess_limiter.record_failure(host)
        raise


def save_changes(invite: dict, update: dict, actor: str, unset: tuple = ()) -> None:
    """Write `update`, and add what it changed to the invitation's history."""
    operations: dict = {"$set": update}
    if unset:
        operations["$unset"] = {field: "" for field in unset}

    changes = invite_changes(invite, {**invite, **update})
    if changes:
        entry = {"at": datetime.now(timezone.utc), "by": actor, "changes": changes}
        operations["$push"] = {"history": {"$each": [entry], "$slice": -MAX_HISTORY}}

    invites.update_one({"key": invite["key"]}, operations)


def named_guests(guests: list) -> list:
    """The (name, is_child) pairs that actually have a name."""
    return [(g.name.strip(), g.is_child) for g in guests if g.name.strip()]


def validate_shape(named_count: int, extra_allowed: int) -> None:
    if not 1 <= named_count <= MAX_NAMED_GUESTS:
        raise HTTPException(
            status_code=400,
            detail=f"An invitation needs between 1 and {MAX_NAMED_GUESTS} names (got {named_count})",
        )
    if not 0 <= extra_allowed <= MAX_EXTRA_GUESTS:
        raise HTTPException(
            status_code=400,
            detail=f"An invitation allows between 0 and {MAX_EXTRA_GUESTS} extra guests",
        )


def apply_rsvp(invite: dict, body: RSVPRequest) -> dict:
    """Merge the submitted answers into the invitation's guest list."""
    by_id = {g["id"]: g for g in invite["guests"]}
    host_order = [g for g in invite["guests"] if g["source"] == "host"]
    # The page does not send ids for people it added: recognise them by name, so
    # replying again does not look like replacing them
    known_extras = {g["name"].casefold(): g for g in invite["guests"] if g["source"] == "guest"}

    # Only invitations asked to the party can answer yes to it
    pizza_invited = invite["pizza_party_invited"]

    answered: dict = {}
    extras: list = []

    for ans in body.guests:
        diet = ans.diet if ans.diet in DIETS else "none"
        name = (ans.name or "").strip()
        allergies = (ans.allergies or "").strip()
        target = by_id.get(ans.id or "")

        if target and target["source"] == "host":
            # The name and age are the hosts' to decide: whatever is sent is ignored
            guest = dict(target)
            guest["attending"] = bool(ans.attending)
            guest["diet"] = diet
            guest["allergies"] = allergies
            guest["choir"] = bool(ans.choir) and bool(ans.attending)
            guest["brunch"] = bool(ans.brunch) and bool(ans.attending)
            guest["pizza_party"] = pizza_invited and ans.pizza_party and ans.attending
            answered[guest["id"]] = guest
        else:
            # Someone the guests added themselves; only keep those who are coming
            if not name or not ans.attending:
                continue
            if ans.is_child is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Please say whether {name} is an adult or a child",
                )
            guest = new_guest(name, source="guest", is_child=ans.is_child)
            known = known_extras.pop(name.casefold(), None)
            if known:
                guest["id"] = known["id"]
            guest["attending"] = True
            guest["diet"] = diet
            guest["allergies"] = allergies
            guest["choir"] = bool(ans.choir)
            guest["brunch"] = bool(ans.brunch)
            guest["pizza_party"] = pizza_invited and ans.pizza_party
            extras.append(guest)

    # People the invitees add only come along with someone who was invited
    if not any(g["attending"] for g in answered.values()):
        extras = []

    if len(extras) > invite["extra_guests_allowed"]:
        raise HTTPException(
            status_code=400,
            detail=f"This invitation allows at most {invite['extra_guests_allowed']} additional guest(s)",
        )

    guests = []
    for host in host_order:
        if host["id"] in answered:
            guests.append(answered[host["id"]])
        else:
            # Not submitted → treat as not attending, keep their details
            guests.append({**host, "attending": False, "choir": False,
                           "brunch": False, "pizza_party": False})
    guests.extend(extras)

    now = datetime.now(timezone.utc)
    return {
        "guests":             guests,
        "notes":              (body.notes or "").strip(),
        "first_opened_at":    invite.get("first_opened_at") or now,
        "first_submitted_at": invite.get("first_submitted_at") or now,
        "last_submitted_at":  now,
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/invite/{key}")
def get_invite(key: InviteKey, request: Request):
    invite = guest_invite(key, request)
    # Typing the code and following a link both arrive here. The filter makes
    # sure only the very first visit is recorded, even with two at once.
    invites.update_one(
        {"key": invite["key"], "first_opened_at": None},
        {"$set": {"first_opened_at": datetime.now(timezone.utc)}},
    )
    return public_invite(invite)


@app.get("/invite/{key}/gift")
def gift_details(key: InviteKey, request: Request):
    """Bank details, only for someone holding a valid invitation code.

    They live in the server's environment, never in the public repository.
    """
    guest_invite(key, request)
    return {
        "account_holder": os.getenv("GIFT_ACCOUNT_HOLDER", "Emma Chirlomez & Theodor Moroianu"),
        "iban":           os.getenv("GIFT_IBAN", "PLACEHOLDER-IBAN"),
        "bic":            os.getenv("GIFT_BIC", "PLACEHOLDER-BIC"),
    }


@app.post("/invite/{key}/rsvp")
def submit_rsvp(key: InviteKey, body: RSVPRequest, request: Request):
    invite = guest_invite(key, request)
    update = apply_rsvp(invite, body)
    save_changes(invite, update, "guest", unset=("responded_at",))
    return public_invite({**invite, **update})


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/responses")
def list_responses(admin_key: str = ""):
    require_admin(admin_key)
    return [admin_invite(normalize_invite(doc)) for doc in invites.find({}, {"_id": 0})]


def build_invite(body: NewInviteRequest) -> dict:
    """Validate one creation request and shape the document it describes."""
    people = named_guests(body.guests)
    if not people and body.name and body.name.strip():
        people = [(body.name.strip(), False)]

    extra = MAX_EXTRA_GUESTS if body.extras_are_children else body.extra_guests_allowed
    validate_shape(len(people), extra)

    return new_invite(
        guests=people,
        label=body.label,
        extra_guests_allowed=extra,
        extras_are_children=body.extras_are_children,
        pizza_party_invited=body.pizza_party_invited,
        language=body.language,
        email=body.email,
        responsible=body.responsible,
    )


@app.post("/admin/invites")
def create_invite(body: NewInviteRequest, admin_key: str = ""):
    require_admin(admin_key)

    invite = build_invite(body)
    invites.insert_one(dict(invite))
    return admin_invite(invite)


@app.post("/admin/invites/bulk")
def create_invites(body: BulkInviteRequest, admin_key: str = ""):
    """Create a whole pasted list at once — all of it, or none of it."""
    require_admin(admin_key)

    if not body.invites:
        raise HTTPException(status_code=400, detail="No invitations to add")

    built, problems = [], []
    for i, entry in enumerate(body.invites):
        try:
            built.append(build_invite(entry))
        except HTTPException as exc:
            problems.append(f"line {i + 1}: {exc.detail}")

    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems[:10]))

    invites.insert_many([dict(inv) for inv in built])
    return {"created": [admin_invite(inv) for inv in built]}


@app.patch("/admin/invites/{key}")
def edit_invite(key: str, body: EditInviteRequest, admin_key: str = ""):
    require_admin(admin_key)
    invite = load_invite(key)

    host_guests = [g for g in invite["guests"] if g["source"] == "host"]
    extras      = [g for g in invite["guests"] if g["source"] == "guest"]

    if body.guests is not None:
        # Keep each position's answers where a person is still on the list
        rebuilt = []
        for i, (name, is_child) in enumerate(named_guests(body.guests)):
            if i < len(host_guests):
                rebuilt.append({**host_guests[i], "name": name, "is_child": is_child})
            else:
                rebuilt.append(new_guest(name, is_child=is_child))
        host_guests = rebuilt

    for_children = (
        body.extras_are_children
        if body.extras_are_children is not None
        else invite["extras_are_children"]
    )
    if for_children:
        extra = MAX_EXTRA_GUESTS
    elif body.extra_guests_allowed is not None:
        extra = body.extra_guests_allowed
    else:
        # Leaving "their children" with no number given means nobody extra
        extra = 0 if invite["extras_are_children"] else invite["extra_guests_allowed"]
    validate_shape(len(host_guests), extra)

    pizza_invited = (
        body.pizza_party_invited
        if body.pizza_party_invited is not None
        else invite["pizza_party_invited"]
    )
    guests = host_guests + extras[:extra]
    if not pizza_invited:
        guests = [{**g, "pizza_party": False} for g in guests]

    update = {
        "guests":               guests,
        "extra_guests_allowed": extra,
        "extras_are_children":  for_children,
        "pizza_party_invited":  pizza_invited,
        "label":                body.label if body.label is not None else invite["label"],
        "language":             body.language if body.language in LANGUAGES else invite["language"],
        "email":                clean_email(body.email) if body.email is not None else invite["email"],
        "responsible":          body.responsible.strip() if body.responsible is not None
                                else invite["responsible"],
    }
    # The allowance is now explicit, so an old type must no longer override it
    save_changes(invite, update, "admin", unset=("invite_type",))
    return admin_invite({**invite, **update})


@app.delete("/admin/invites/{key}")
def delete_invite(key: str, admin_key: str = ""):
    require_admin(admin_key)

    result = invites.delete_one({"key": clean_key(key)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"success": True}
