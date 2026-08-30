from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List
from dotenv import load_dotenv
import os
import secrets

from invite_model import (
    DIETS,
    INVITE_TYPES,
    LANGUAGES,
    MAX_ALLERGIES_LEN,
    MAX_GUESTS,
    MAX_LABEL_LEN,
    MAX_NAME_LEN,
    MAX_NOTES_LEN,
    TYPE_EXTRA_RANGE,
    TYPE_GUEST_RANGE,
    admin_invite,
    clamp_extra,
    clean_key,
    new_guest,
    new_invite,
    normalize_invite,
    public_invite,
)

load_dotenv()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
if not ADMIN_SECRET:
    raise RuntimeError("ADMIN_SECRET must be defined and non-empty")

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

class NewInviteRequest(BaseModel):
    invite_type:          str = "single"
    guest_names:          List[str] = Field(default_factory=list, max_length=MAX_GUESTS)
    label:                str = Field("", max_length=MAX_LABEL_LEN)
    language:             str = "en"
    extra_guests_allowed: Optional[int] = None
    # Accepted for convenience (single guest, legacy callers / quick add)
    name:                 Optional[str] = Field(None, max_length=MAX_NAME_LEN)


class EditInviteRequest(BaseModel):
    invite_type:          Optional[str] = None
    guest_names:          Optional[List[str]] = Field(None, max_length=MAX_GUESTS)
    label:                Optional[str] = Field(None, max_length=MAX_LABEL_LEN)
    language:             Optional[str] = None
    extra_guests_allowed: Optional[int] = None


class GuestAnswer(BaseModel):
    id:        Optional[str] = None
    name:      str  = Field("", max_length=MAX_NAME_LEN)
    attending: bool = False
    diet:      str  = "none"
    allergies: str  = Field("", max_length=MAX_ALLERGIES_LEN)


class RSVPRequest(BaseModel):
    guests: List[GuestAnswer] = Field(default_factory=list, max_length=MAX_GUESTS)
    notes:  str = Field("", max_length=MAX_NOTES_LEN)

# ── Helpers ───────────────────────────────────────────────────────────────────

def require_admin(admin_key: str) -> None:
    if not secrets.compare_digest(admin_key or "", ADMIN_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


def load_invite(key: str) -> dict:
    cleaned = clean_key(key)
    doc = invites.find_one({"key": cleaned}, {"_id": 0}) if cleaned else None
    if not doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    return normalize_invite(doc)


def validate_shape(invite_type: str, host_names: list, extra_allowed: int) -> None:
    if invite_type not in INVITE_TYPES:
        raise HTTPException(status_code=400, detail="Unknown invitation type")

    lo, hi = TYPE_GUEST_RANGE[invite_type]
    if not (lo <= len(host_names) <= hi):
        raise HTTPException(
            status_code=400,
            detail=(
                f"A '{invite_type}' invitation needs "
                + (f"{lo} name{'s' if lo > 1 else ''}" if lo == hi else f"between {lo} and {hi} names")
                + f" (got {len(host_names)})"
            ),
        )

    elo, ehi = TYPE_EXTRA_RANGE[invite_type]
    if not (elo <= extra_allowed <= ehi):
        raise HTTPException(
            status_code=400,
            detail=f"A '{invite_type}' invitation allows between {elo} and {ehi} extra guests",
        )


def apply_rsvp(invite: dict, body: RSVPRequest) -> dict:
    """Merge the submitted answers into the invitation's guest list."""
    by_id = {g["id"]: g for g in invite["guests"]}
    host_order = [g for g in invite["guests"] if g["source"] == "host"]

    answered: dict = {}
    extras: list = []

    for ans in body.guests:
        diet = ans.diet if ans.diet in DIETS else "none"
        name = (ans.name or "").strip()
        allergies = (ans.allergies or "").strip()
        target = by_id.get(ans.id or "")

        if target and target["source"] == "host":
            guest = dict(target)
            if name:
                guest["name"] = name  # let guests fix a misspelling
            guest["attending"] = bool(ans.attending)
            guest["diet"] = diet
            guest["allergies"] = allergies
            answered[guest["id"]] = guest
        else:
            # Someone the guests added themselves; only keep those who are coming
            if not name or not ans.attending:
                continue
            guest = new_guest(name, source="guest")
            guest["attending"] = True
            guest["diet"] = diet
            guest["allergies"] = allergies
            extras.append(guest)

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
            guests.append({**host, "attending": False})
    guests.extend(extras)

    return {
        "guests":       guests,
        "notes":        (body.notes or "").strip(),
        "responded_at": datetime.now(timezone.utc),
    }

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/invite/{key}")
def get_invite(key: str):
    return public_invite(load_invite(key))


@app.post("/invite/{key}/rsvp")
def submit_rsvp(key: str, body: RSVPRequest):
    invite = load_invite(key)
    update = apply_rsvp(invite, body)
    invites.update_one({"key": invite["key"]}, {"$set": update})
    return public_invite({**invite, **update})


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/responses")
def list_responses(admin_key: str = ""):
    require_admin(admin_key)
    return [admin_invite(normalize_invite(doc)) for doc in invites.find({}, {"_id": 0})]


@app.post("/admin/invites")
def create_invite(body: NewInviteRequest, admin_key: str = ""):
    require_admin(admin_key)

    names = [n.strip() for n in (body.guest_names or []) if (n or "").strip()]
    if not names and body.name and body.name.strip():
        names = [body.name.strip()]

    invite_type = body.invite_type if body.invite_type in INVITE_TYPES else "single"
    extra = clamp_extra(invite_type, body.extra_guests_allowed)
    validate_shape(invite_type, names, extra)

    invite = new_invite(
        invite_type=invite_type,
        guest_names=names,
        label=body.label,
        extra_guests_allowed=extra,
        language=body.language,
    )
    invites.insert_one(dict(invite))
    return admin_invite(invite)


@app.patch("/admin/invites/{key}")
def edit_invite(key: str, body: EditInviteRequest, admin_key: str = ""):
    require_admin(admin_key)
    invite = load_invite(key)

    invite_type = body.invite_type or invite["invite_type"]
    host_guests = [g for g in invite["guests"] if g["source"] == "host"]
    extras      = [g for g in invite["guests"] if g["source"] == "guest"]

    if body.guest_names is not None:
        names = [n.strip() for n in body.guest_names if (n or "").strip()]
        # Keep each position's answers where a person is still on the list
        rebuilt = []
        for i, name in enumerate(names):
            if i < len(host_guests):
                rebuilt.append({**host_guests[i], "name": name[:MAX_NAME_LEN]})
            else:
                rebuilt.append(new_guest(name))
        host_guests = rebuilt

    extra = (
        clamp_extra(invite_type, body.extra_guests_allowed)
        if body.extra_guests_allowed is not None
        else clamp_extra(invite_type, invite["extra_guests_allowed"])
    )
    validate_shape(invite_type, [g["name"] for g in host_guests], extra)

    update = {
        "invite_type":          invite_type,
        "guests":               host_guests + extras[:extra],
        "extra_guests_allowed": extra,
        "label":                (body.label if body.label is not None else invite["label"])[:MAX_LABEL_LEN],
        "language":             body.language if body.language in LANGUAGES else invite["language"],
    }
    invites.update_one({"key": invite["key"]}, {"$set": update})
    return admin_invite({**invite, **update})


@app.delete("/admin/invites/{key}")
def delete_invite(key: str, admin_key: str = ""):
    require_admin(admin_key)

    result = invites.delete_one({"key": clean_key(key)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"success": True}
