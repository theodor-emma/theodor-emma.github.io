from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
import os
import secrets
import string

load_dotenv()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
if not ADMIN_SECRET:
    raise RuntimeError("ADMIN_SECRET must be defined and non-empty")

app = FastAPI(title="Wedding RSVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "DELETE"],
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
    name: str

class RSVPRequest(BaseModel):
    attending: bool
    dietary_restrictions: Optional[str] = ""
    notes:                Optional[str] = ""
    plus_one:             Optional[bool] = False
    plus_one_name:        Optional[str] = ""
    plus_one_dietary:     Optional[str] = ""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/invite/{key}")
def get_invite(key: str):
    invite = invites.find_one({"key": key}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    return {
        "name":                 invite["name"],
        "responded":            invite.get("attending") is not None,
        "attending":            invite.get("attending"),
        "dietary_restrictions": invite.get("dietary_restrictions", ""),
        "notes":                invite.get("notes", ""),
        "plus_one":             invite.get("plus_one", False),
        "plus_one_name":        invite.get("plus_one_name", ""),
        "plus_one_dietary":     invite.get("plus_one_dietary", ""),
    }


@app.post("/invite/{key}/rsvp")
def submit_rsvp(key: str, body: RSVPRequest):
    invite = invites.find_one({"key": key})
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    invites.update_one(
        {"key": key},
        {"$set": {
            "attending":            body.attending,
            "dietary_restrictions": body.dietary_restrictions or "",
            "notes":                body.notes or "",
            "plus_one":             body.plus_one or False,
            "plus_one_name":        body.plus_one_name or "",
            "plus_one_dietary":     body.plus_one_dietary or "",
            "responded_at":         datetime.now(timezone.utc),
        }},
    )
    return {"success": True}


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/responses")
def list_responses(admin_key: str = ""):
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    rows = list(invites.find({}, {"_id": 0}))
    for row in rows:
        if row.get("responded_at"):
            row["responded_at"] = row["responded_at"].isoformat()
    return rows


@app.post("/admin/invites")
def create_invite(body: NewInviteRequest, admin_key: str = ""):
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    invites.insert_one({
        "key":                  key,
        "name":                 name,
        "attending":            None,
        "dietary_restrictions": "",
        "notes":                "",
        "plus_one":             False,
        "plus_one_name":        "",
        "plus_one_dietary":     "",
        "responded_at":         None,
    })
    return {"key": key, "name": name}


@app.delete("/admin/invites/{key}")
def delete_invite(key: str, admin_key: str = ""):
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = invites.delete_one({"key": key})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"success": True}
