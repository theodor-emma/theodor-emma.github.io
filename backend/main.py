from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Wedding RSVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────────────────────

client  = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
db      = client[os.getenv("MONGODB_DB", "wedding")]
invites = db["invites"]

# ── Models ────────────────────────────────────────────────────────────────────

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
    expected = os.getenv("ADMIN_SECRET", "")
    if not expected or admin_key != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    rows = list(invites.find({}, {"_id": 0}))
    # Serialise datetime to ISO string for JSON
    for row in rows:
        if row.get("responded_at"):
            row["responded_at"] = row["responded_at"].isoformat()
    return rows
